"""
根据自然语言提示词调用上游图像接口（与 Epoch Incursion / web/explorer 美术管线对齐）。

后端（环境变量 IMAGE_GEN_BACKEND 或 --backend）：
  gemini          POST {BASE}/v1beta/models/{model}:generateContent
  openai-chat     POST {OPENAI_BASE_URL}/v1/chat/completions
  openai-images   POST {OPENAI_BASE_URL}/v1/images/generations（兼容旧 OpenAI 图像网关）

配置：仓库根目录 `.env.txt`、`.env`，其次 `tools/` 下同名文件。

Base URL（**通常只在 .env 配一份 `OPENAI_BASE_URL`**）：
  - **扩写**（gpt-4o-mini）与 **openai-chat / openai-images** 均使用 **`OPENAI_BASE_URL`**。
  - **`IMAGE_GEN_BACKEND=gemini`**：若 **未** 设置 `GEMINI_BASE_URL`，则 **自动使用与 `OPENAI_BASE_URL` 相同的地址**（同一网关）；仅在直连 Google 时再单独设 `GEMINI_BASE_URL`（不设 `OPENAI_BASE_URL` 时仍默认为官方 `generativelanguage.googleapis.com`）。
  - 极少数情况下扩写要走别的 host：才需要 **`OPENAI_PROMPT_LLM_BASE_URL`**。

密钥（**一份即可**，都放在 `.env` 里即可）：
  默认使用 **`OPENAI_API_KEY`**：
  - **提示词扩写**（gpt-4o-mini，`/v1/chat/completions`）与生图里的 **openai-chat / openai-images** 都用它访问 **`OPENAI_BASE_URL`**。
  - **`IMAGE_GEN_BACKEND=gemini`** 时：若未设置 `GEMINI_API_KEY` / `GOOGLE_API_KEY`，会 **回退使用同一 `OPENAI_API_KEY`**（适合网关统一转发的情况）。
  若使用 **Google 官方** Gemini API，请设置 `GEMINI_API_KEY`；不设时则用 **`OPENAI_API_KEY`** 访问 Gemini 路径（常见于自建网关）。

用法：
    python tools/generate_image_nl.py --backend gemini --preset road
    python tools/generate_image_nl.py --all-map-tiles
    IMAGE_GEN_BACKEND=openai-chat python tools/generate_image_nl.py "……"

提示词两阶段（默认开启）：
    先用 gpt-4o-mini 请求 **`OPENAI_BASE_URL` + /v1/chat/completions**（密钥 **`OPENAI_API_KEY`**），
    再将英文 prompt 发到当前生图后端（**Gemini 默认与前者同一 BASE**，除非单独配置了 `GEMINI_BASE_URL`）。
    关闭扩写：`--no-refine-prompt` 或 `IMAGE_PROMPT_LLM=0`。
    扩写模型：`IMAGE_PROMPT_LLM_MODEL`（默认 gpt-4o-mini）；仅当扩写 host 不同时：`OPENAI_PROMPT_LLM_BASE_URL`。

速度与分辨率：默认 512×512、quality=low（openai-images）、默认 --prefer-b64（仅 openai-images）。

画风参考图（风格条件生成，非传统神经网络 style transfer）：
  1. 用 Pillow 对参考图抠背景（可 --no-style-ref-remove-bg 跳过）
  2. 默认铺浅灰底后再 base64 送入 Gemini inlineData（可 --no-style-ref-flatten 保留透明）
  3. `--preset facility` 且未指定时，自动使用 `assets/facilities_generated/_test_helipad.png`
  环境变量：`IMAGE_STYLE_REF`、`IMAGE_STYLE_REF_AUTO=0` 关闭自动参考。
"""

from __future__ import annotations

import argparse
import base64
import importlib.util
import io
import json
import os
import random
import re
import http.client
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode, urlparse

def _add_prefer_b64_args(parser: argparse.ArgumentParser) -> None:
    """默认优先 b64（少一跳下载）；兼容无 BooleanOptionalAction 的旧版 Python。"""
    if hasattr(argparse, "BooleanOptionalAction"):
        parser.add_argument(
            "--prefer-b64",
            action=argparse.BooleanOptionalAction,
            default=True,
            help="（openai-images）默认 b64_json；Gemini / openai-chat 忽略",
        )
    else:
        parser.set_defaults(prefer_b64=True)
        g = parser.add_mutually_exclusive_group()
        g.add_argument("--prefer-b64", action="store_true", dest="prefer_b64", help=argparse.SUPPRESS)
        g.add_argument("--no-prefer-b64", action="store_false", dest="prefer_b64", help="关闭 b64（仅 openai-images）")


TOOLS_DIR = Path(__file__).resolve().parent
REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_FAST_SIZE = "512x512"
DEFAULT_FAST_QUALITY = "low"

DEFAULT_GEMINI_BASE = "https://generativelanguage.googleapis.com"
DEFAULT_IMAGE_MODEL = "gemini-3.1-flash-image-preview"
DEFAULT_GEMINI_IMAGE_MODEL = DEFAULT_IMAGE_MODEL

# 设施画风参考图（先抠图再作为 Gemini 多模态输入，做风格条件生成）
DEFAULT_FACILITY_STYLE_REF = REPO_ROOT / "assets" / "facilities_generated" / "_test_helipad.png"

STYLE_REF_INSTRUCTION = (
    "REFERENCE IMAGE (style reference only): Match its pixel-art palette, lighting, pixel density, "
    "and industrial military sci-fi mood — BUT the camera MUST be orthographic top-down (bird's eye), "
    "axis-aligned and square to the map grid (no isometric skew, no 3/4 angle, no rotation). "
    "Draw a completely NEW building from the description below (different layout/silhouette); "
    "do NOT copy the reference camera angle or structure.\n\n"
)

GAME_ART_STYLE_ZH = (
    "【游戏素材约束】源纪元·岸线基地：近未来科幻+日式像素风（pixel art）。"
    "核心画风：16-bit像素游戏风格，类似超任/GBA时代的像素RPG，色块分明、边缘锐利、有像素颗粒感。"
    "冷色调、低饱和科幻氛围。"
    "正交俯视（top-down），单一纹理贴图，无缝平铺或可裁切为方形地块；"
    "边缘须能与相邻块对齐拼接；画面中无文字、无水印、无角色、无 UI。"
    "像素格可见但不过粗，每个像素单元清晰可辨。"
    "分辨率适中即可（后续在游戏内缩放至约 40px 格网）。"
)

FACILITY_ART_STYLE_ZH = (
    "【建筑素材约束】源纪元·岸线基地设施：用于大地图格网（约 40px/格）的独立建筑贴图，"
    "16-bit/32-bit 像素风（pixel art），画风可对齐参考样张的配色与工业质感。"
    "★ 视角（最重要）：严格正交俯视（orthographic top-down / bird's eye），"
    "建筑物与画面边框平行、不倾斜、不旋转、无等距透视（no isometric）、无 3/4 斜视角；"
    "呈现屋顶与占地轮廓为主的「正」向贴图，便于按矩形格网对齐摆放。"
    "★ 配色：克制冷色调——钢蓝、板岩灰、深青绿为主，低饱和；"
    "用有限色板做顶面明暗，避免霓虹过曝。"
    "★ 光照：轻微左上方向光，主要在屋顶平面表现体积，侧面可见度极低（顶视为主）。"
    "★ 细节：工业军事科幻——金属屋面、天线、管道、舱盖等，用顶视可辨认的剪影表达；"
    "体量紧凑、外轮廓清晰，适合缩放后仍可读。"
    "★ 构图：建筑居中，占画面约 50–60%，四边与画布边平行（轴对齐）；"
    "背景为统一纯色（浅灰或深蓝灰），无地面纹理、道路、天空、植被；"
    "无文字、无水印、无角色、无 UI（设施自有顶视符号除外）。"
    "像素格清晰、边缘锐利。"
)

PORTRAIT_ART_STYLE_ZH = (
    "【角色立绘约束】源纪元·岸线基地角色：日式二次元像素风。"
    "核心画风：16-bit像素角色立绘，类似GBA/NDS时代像素JRPG的人物肖像风格，"
    "人物五官用有限像素点勾勒，大眼睛、简洁发型线条、色块分明有像素锯齿边缘。"
    "半身构图（胸像）、角色正对观众或略侧身。背景为纯暗色或极简渐变色块。"
    "服装为近未来科幻实用风格（军旅/科研/工装），用像素色块表现面料褶皱。"
    "配色偏冷调低饱和，符合游戏末世科幻氛围。"
    "画面中无文字、无水印、无品牌标志；角色表情符合人物性格设定。"
    "分辨率约256×256至512×512即可（清晰像素颗粒可见）。"
)

ICON_ART_STYLE_ZH = (
    "【图标素材约束】源纪元·岸线基地UI图标：日式二次元像素风。"
    "核心画风：16-bit像素图标，类似经典JRPG的item/技能图标，"
    "色块分明的像素符号，边缘有像素锯齿感，强调明暗面与高光点的像素表现。"
    "★ 意义明确：仅一个中心符号，一眼可辨其功能（如闪电=能源、齿轮=零件、"
    "十字=医疗、眼睛=情报、钻头=采矿、熔炉=冶炼）；禁止复杂场景、多物体堆砌或抽象花纹。"
    "★ 背景必须全透明（alpha=0），严禁任何底色、圆形/方形底衬、描边外框、阴影底板、"
    "渐变铺底或棋盘格示意；符号悬浮在完全透明的画布上。"
    "★ 图标主体居中，占画面约 70–80%，四周留均匀透明边距。"
    "冷色调科幻氛围，关键元素可用暖色（橙/黄）小面积亮点。"
    "画面中无文字、无字母、无水印；风格统一。"
    "分辨率约64×64至128×128即可（清晰像素颗粒可见）。"
)

# gpt-4o-mini 等：仅输出一段可直接给生图模型的英文 prompt
PROMPT_REFINE_SYSTEM = """You are a prompt engineer for AI image generation targeting game production assets.
The user message contains a brief, possibly in Chinese, with art direction for "Epoch Incursion" coastal sci-fi base game.

CRITICAL ART STYLE: Japanese anime pixel art, 16-bit style like SNES/GBA era pixel JRPGs (not modern HD). Think "Chrono Trigger" or "Final Fantasy VI" pixel sprites/portraits. Key characteristics: visible pixel grid, sharp color blocking, limited color palette per asset, visible pixel edges, chunky pixels.

Assets may be:
- Map tiles: top-down seamless textures for grid-based game
- Character portraits: half-body pixel portraits facing viewer
- Icons: small pixel icons for UI (32-128px equivalent) — MUST have transparent background, no colored circles/squares behind the icon, icon floats on alpha channel
- Buildings: complete standalone ORTHOGRAPHIC top-down pixel facility sprites for a square grid overworld map (40px tiles). Axis-aligned, no rotation, no isometric skew, no 3/4 view — roof and footprint dominant. Style may echo reference palette/industrial mood but camera must be straight top-down. NOT cropped from a scene. Solid uniform backdrop only; NO terrain, grass, roads, sky.

Write ONE compact English prompt optimized for an image model: concrete visual nouns, lighting, materials, camera angle, and constraints (no text, no watermark, no characters in tile/icon shots, seamless/tileable edges where it is a ground texture). For buildings MUST include "pixel art, 16-bit, orthographic top-down, axis-aligned, retro game sprite".

For icons: explicitly require "transparent background, no background circle". For buildings: "orthographic top-down, axis-aligned, muted cool palette, industrial military sci-fi, solid plain backdrop for cutout".

Output ONLY the final prompt paragraph. No markdown, no quotes, no preamble."""

MAP_TILE_PRESETS: dict[str, dict[str, Any]] = {
    "void": {
        "label": "T_VOID 野地基底",
        "hint_zh": (
            "像素风深蓝灰荒地基底，RGB基调约(14,22,36)；"
            "像素颗粒清晰的风化地表、砂砾硬土纹理、极低对比；"
            "与可走路面区分明显；勿画粗大轮廓。"
            "16-bit像素RPG荒野地面风格，有微妙的像素噪点和材质变化。"
        ),
        "default_size": DEFAULT_FAST_SIZE,
        "default_quality": DEFAULT_FAST_QUALITY,
    },
    "road": {
        "label": "T_ROAD 可走铺装路面",
        "hint_zh": (
            "像素风冷灰硬化路面，RGB基调约(48,54,68)，略偏蓝；"
            "像素颗粒清晰的轻微修补裂缝、车辙、导向刻痕；"
            "勿画半截建筑；图案对称或可平铺。"
            "16-bit像素RPG城镇路面风格，像素色块分明。"
        ),
        "default_size": DEFAULT_FAST_SIZE,
        "default_quality": DEFAULT_FAST_QUALITY,
    },
    "build": {
        "label": "T_BUILD 建筑占格",
        "hint_zh": (
            "像素风深蓝灰屋面体量，RGB基调约(26,32,44)，比路面更暗略冷；"
            "像素色块表现的抽象方块屋顶或幕墙暗示；勿画可辨认门窗剧情细节。"
            "16-bit像素RPG建筑物屋顶风格，像素边缘锐利。"
        ),
        "default_size": DEFAULT_FAST_SIZE,
        "default_quality": DEFAULT_FAST_QUALITY,
    },
}

MAP_TILE_PRESET_ORDER: tuple[str, ...] = ("void", "road", "build")

# ── NPC 立绘预设 ──────────────────────────────────────────────
NPC_PORTRAIT_PRESETS: dict[str, dict[str, Any]] = {
    "karen": {
        "label": "卡伦（Karen）",
        "visual_zh": (
            "二次元像素风女性角色立绘，约35岁，前特种部队出身。"
            "短发干练，冷峻面容，像素风格大眼睛略带疲惫感。"
            "身穿深蓝灰战术夹克与基地安全官制服，用像素色块表现肩章与装备带。"
            "半身构图，站姿挺拔微侧。眼神锐利但深处藏有愧疚与迷茫。"
            "16-bit像素JRPG角色肖像风格，色块分明有像素锯齿边缘。"
        ),
        "color_hint": "主色调冷蓝灰 #4a6fa5，服装深藏青偏灰，肤色略苍白。",
        "default_size": "512x512",
    },
    "dr_lin": {
        "label": "林博士（Dr. Lin）",
        "visual_zh": (
            "二次元像素风男性角色立绘，约50岁，科研主管。"
            "微瘦体型，像素风格细框眼镜，额头眼角有皱纹用暗色像素点表现。"
            "白色实验大褂内搭灰色高领衫，像素色块表现口袋与数据板。"
            "姿态微驼略疲惫，眼神悲悯柔和有知识分子的忧郁气质。"
            "16-bit像素JRPG学者角色肖像风格。"
        ),
        "color_hint": "主色调灰绿 #5a9078，白大褂+灰内搭，暖灰肤色。",
        "default_size": "512x512",
    },
    "chubby": {
        "label": "小胖（Chubby）",
        "visual_zh": (
            "二次元像素风男性角色立绘，约28岁，体格微胖壮实。"
            "圆脸带胡茬用像素点表现，深橙色工装连体服（上半身拉链半开露灰色T恤），"
            "像素色块表现油污痕迹。手持大扳手，脸上挂憨厚笑容但眼角有隐藏紧张。"
            "16-bit像素JRPG工匠角色肖像风格，暖色调。"
        ),
        "color_hint": "主色调暖棕橙 #b8924a，油污工装+灰T恤，偏暖肤色。",
        "default_size": "512x512",
    },
    "klein": {
        "label": "克莱因（Klein）",
        "visual_zh": (
            "二次元像素风老年男性角色立绘，约75岁，极度衰老虚弱。"
            "苍白稀疏白发用亮灰像素表现，深陷眼窝用暗色像素阴影。"
            "破旧灰色囚服或简易病号服，像素色块表现褶皱与磨损。"
            "双手瘦骨嶙峋扶膝，眼神浑浊但偶闪锐利清明之光。"
            "16-bit像素JRPG贤者角色肖像风格，暗沉色调。"
        ),
        "color_hint": "主色调暗灰 #5c5e72，灰白囚服，病态苍白肤色，整体低饱和。",
        "default_size": "512x512",
    },
    "echo_7": {
        "label": "回声-7（Echo-7）",
        "visual_zh": (
            "二次元像素风AI角色立绘，无人类形体。"
            "表现为16-bit像素风格的全息投影——数据流与几何光纹构成的抽象人脸。"
            "半透明蓝紫霓虹像素光束编织成人脸轮廓，无瞳孔的发光眼窝。"
            "深色数码背景，飘浮像素代码或信号波形。"
            "构图居中对称，传递非人/机器的冷静与距离感。"
        ),
        "color_hint": "主色调紫蓝 #7a5cb8，霓虹像素光效+深色数码背景，冷色调。",
        "default_size": "512x512",
    },
    "jin": {
        "label": "堇（Jin）",
        "visual_zh": (
            "二次元像素风女性角色立绘，约25岁，面容清秀友善。"
            "齐肩黑发用像素块表现，发梢微卷。"
            "浅灰绿生态研究服，像素色块表现领口植物徽章与挽起的袖口。"
            "手中轻捧一株发光小植物。表情温和笑容自然，但眼神深处有不易察觉的锐利。"
            "16-bit像素JRPG角色肖像风格。"
        ),
        "color_hint": "主色调柔和绿 #5a9e6e，浅灰绿研究服+深发，暖肤色。",
        "default_size": "512x512",
    },
    "elizabeth": {
        "label": "伊丽莎白·莫罗（Elizabeth Morrow）",
        "visual_zh": (
            "二次元像素风女性角色立绘，约55岁，高贵端庄。"
            "银灰色短发利落后梳用像素块表现，五官线条分明。"
            "深紫红议会高领礼服，像素色块表现金属徽章与厚重布料。"
            "全息投影/通讯屏幕中的像素画面，周围有微弱像素扫描线/光晕。"
            "表情自信威严，嘴角微扬带说服力，目光直视观众如同审视。"
            "16-bit像素JRPG女帝/领袖角色肖像风格。"
        ),
        "color_hint": "主色调深紫红 #944a62，议会礼服+银灰发，冷肤色。",
        "default_size": "512x512",
    },
    "source": {
        "label": "源（Source）",
        "visual_zh": (
            "二次元像素风非人抽象存在立绘，幽蓝与青绿交织的量子态像素光雾。"
            "人形剪影轮廓但内部为流动的像素星河/记忆碎片/微光粒子旋涡。"
            "深色虚空背景，像素光雾边缘有信号衰减/像素化效果。"
            "传递「既非善亦非恶」的超越性存在感，悲伤与希望并存。"
            "16-bit像素RPG中类似最终boss/神祇的表现风格。"
        ),
        "color_hint": "主色调青蓝渐变，像素光雾+虚空背景，非具象。",
        "default_size": "512x512",
    },
}

NPC_PORTRAIT_ORDER: tuple[str, ...] = (
    "karen", "dr_lin", "chubby", "klein", "echo_7", "jin", "elizabeth", "source",
)

FACILITY_CORE: dict[str, tuple[str, int, int]] = {

    "sunk_lab": ("沉没实验室", 460, 260),
    "mine_ruins": ("废弃矿场表层", 480, 300),
    "helipad": ("停机坪", 260, 160),
    "echo_site": ("回声集团信标塔", 320, 280),
    "parliament_ruin": ("议会前哨站废墟", 340, 280),
    "defense": ("海岸防线", 420, 300),
    "command": ("基地核心", 380, 300),
    "lab": ("医疗实验室", 360, 300),
    "shore_cave": ("海岸线洞穴", 280, 220),
    "comm": ("通讯阵列", 360, 260),
    "listen": ("地下监听站", 340, 280),
    "mine": ("源矿采集点", 460, 300),
    "purify_grove": ("净空会圣树", 380, 280),
}

# ── 图标预设（工坊设备 / 资源 / UI）─────────────────────────
ICON_PRESETS: dict[str, dict[str, Any]] = {
    # ── 工坊设备图标（8个） ──
    "icon_miner": {
        "label": "工坊设备图标 · 采矿机（miner）",
        "visual_zh": (
            "16-bit像素风采矿设备图标：俯视钻头或爪形机械臂符号，冷灰金属质感，"
            "橙黄指示灯用亮色像素点缀。像素几何构成，识别度高。透明背景。"
        ),
        "default_size": "128x128",
    },
    "icon_smelter": {
        "label": "工坊设备图标 · 冶炼厂（smelter）",
        "visual_zh": (
            "16-bit像素风冶炼设备图标：熔炉或坩埚符号，暗红/橙热光从底部透出，"
            "像素色块表现耐热合金六角形外壳。像素几何构成。透明背景。"
        ),
        "default_size": "128x128",
    },
    "icon_assembler": {
        "label": "工坊设备图标 · 组装机（assembler）",
        "visual_zh": (
            "16-bit像素风组装设备图标：机械臂与传送带符号，齿轮咬合意象，"
            "蓝灰金属像素质感，关节处亮蓝指示灯。像素几何构成。透明背景。"
        ),
        "default_size": "128x128",
    },
    "icon_refiner": {
        "label": "工坊设备图标 · 精炼厂（refiner）",
        "visual_zh": (
            "16-bit像素风精炼设备图标：蒸馏塔或离心机符号，层叠圆筒结构，"
            "管道连接，青蓝化学光泽用像素高光表现。像素几何构成。透明背景。"
        ),
        "default_size": "128x128",
    },
    "icon_printer": {
        "label": "工坊设备图标 · 3D打印机（printer）",
        "visual_zh": (
            "16-bit像素风3D打印设备图标：打印喷头与正在成型的像素晶格结构符号，"
            "光束从喷头射向下方未完成物体。像素几何构成。透明背景。"
        ),
        "default_size": "128x128",
    },
    "icon_power_plant": {
        "label": "工坊设备图标 · 发电站（power_plant）",
        "visual_zh": (
            "16-bit像素风发电站图标：闪电与涡轮符号组合，放射状能量波纹，"
            "电光蓝/白像素主色。像素几何构成。透明背景。"
        ),
        "default_size": "128x128",
    },
    "icon_power_core": {
        "label": "工坊设备图标 · 能量核心（power_core）",
        "visual_zh": (
            "16-bit像素风能量核心图标：中心发光球体被环形约束装置包围，"
            "脉冲波纹向外扩散，蓝白强光像素高亮。像素几何构成。透明背景。"
        ),
        "default_size": "128x128",
    },
    "icon_storage": {
        "label": "工坊设备图标 · 仓库（storage）",
        "visual_zh": (
            "16-bit像素风存储设施图标：货箱或容器符号，堆叠立方体，"
            "冷灰金属像素质感，黄色标记线。像素几何构成。透明背景。"
        ),
        "default_size": "128x128",
    },
    # ── 资源图标（5个） ──
    "icon_resource_energy": {
        "label": "资源图标 · 能源（energy）",
        "visual_zh": (
            "16-bit像素风能源资源图标：发光电池或闪电符号，电光蓝/白渐变，"
            "能量波纹轮廓用像素表现。像素几何构成。透明背景。"
        ),
        "default_size": "128x128",
    },
    "icon_resource_parts": {
        "label": "资源图标 · 零件（parts）",
        "visual_zh": (
            "16-bit像素风零件资源图标：齿轮与螺母符号组合，金属灰/银像素质感，"
            "精密机械感。像素几何构成。透明背景。"
        ),
        "default_size": "128x128",
    },
    "icon_resource_food": {
        "label": "资源图标 · 食物（food）",
        "visual_zh": (
            "16-bit像素风食物资源图标：营养胶囊或水培叶形符号，青绿色调，"
            "简约有机像素曲线。像素几何构成。透明背景。"
        ),
        "default_size": "128x128",
    },
    "icon_resource_medical": {
        "label": "资源图标 · 医疗（medical）",
        "visual_zh": (
            "16-bit像素风医疗资源图标：十字与DNA双螺旋融合符号，青蓝色调，"
            "干净利落的像素医疗感。像素几何构成。透明背景。"
        ),
        "default_size": "128x128",
    },
    "icon_resource_intel": {
        "label": "资源图标 · 情报（intel）",
        "visual_zh": (
            "16-bit像素风情报资源图标：眼睛与数据流符号组合，紫蓝霓虹像素色调，"
            "信号波纹与扫描线元素。像素几何构成。透明背景。"
        ),
        "default_size": "128x128",
    },
    # ── 面板/UI图标（6个） ──
    "icon_tab_current": {
        "label": "面板图标 · 当前（Current）",
        "visual_zh": (
            "16-bit像素风UI面板图标：时钟或圆点指示器符号，青绿像素发光，简洁醒目。"
            "透明背景，适合按钮/tab尺寸的像素UI。"
        ),
        "default_size": "64x64",
    },
    "icon_tab_upcoming": {
        "label": "面板图标 · 后续（Upcoming）",
        "visual_zh": (
            "16-bit像素风UI面板图标：日历或向前箭头符号，蓝灰像素光泽，简洁。"
            "透明背景，适合按钮/tab尺寸的像素UI。"
        ),
        "default_size": "64x64",
    },
    "icon_tab_management": {
        "label": "面板图标 · 决算（Management）",
        "visual_zh": (
            "16-bit像素风UI面板图标：齿轮或仪表盘符号，橙黄像素光泽，简洁。"
            "透明背景，适合按钮/tab尺寸的像素UI。"
        ),
        "default_size": "64x64",
    },
    "icon_tab_explore": {
        "label": "面板图标 · 探索（Explore）",
        "visual_zh": (
            "16-bit像素风UI面板图标：指南针或雷达符号，青蓝像素光泽，简洁。"
            "透明背景，适合按钮/tab尺寸的像素UI。"
        ),
        "default_size": "64x64",
    },
    "icon_tab_dossier": {
        "label": "面板图标 · 档案（Dossier）",
        "visual_zh": (
            "16-bit像素风UI面板图标：文件夹或档案柜符号，紫灰像素光泽，简洁。"
            "透明背景，适合按钮/tab尺寸的像素UI。"
        ),
        "default_size": "64x64",
    },
    "icon_tab_tutorial": {
        "label": "面板图标 · 教程（Tutorial）",
        "visual_zh": (
            "16-bit像素风UI面板图标：问号或灯泡符号，柔和蓝像素光，简洁。"
            "透明背景，适合按钮/tab尺寸的像素UI。"
        ),
        "default_size": "64x64",
    },
    # ── Favicon ──
    "icon_favicon": {
        "label": "网站图标 · Favicon",
        "visual_zh": (
            "16-bit像素风游戏favicon：极小简化像素符号——字母'E'与'源'之意的融合："
            "一个发光像素圆环包裹中央菱形晶体或眼形核心，青蓝渐变，"
            "透明背景。简约、识别度高、适合16~32px像素显示。"
        ),
        "default_size": "64x64",
    },
}

# 分类排序
ICON_WORKSHOP_ORDER: tuple[str, ...] = (
    "icon_miner", "icon_smelter", "icon_assembler", "icon_refiner",
    "icon_printer", "icon_power_plant", "icon_power_core", "icon_storage",
)
ICON_RESOURCE_ORDER: tuple[str, ...] = (
    "icon_resource_energy", "icon_resource_parts", "icon_resource_food",
    "icon_resource_medical", "icon_resource_intel",
)
ICON_TAB_ORDER: tuple[str, ...] = (
    "icon_tab_current", "icon_tab_upcoming", "icon_tab_management",
    "icon_tab_explore", "icon_tab_dossier", "icon_tab_tutorial",
)
ICON_MISC_ORDER: tuple[str, ...] = ("icon_favicon",)
ICON_ALL_ORDER: tuple[str, ...] = (
    ICON_WORKSHOP_ORDER + ICON_RESOURCE_ORDER + ICON_TAB_ORDER + ICON_MISC_ORDER
)
FACILITY_ORDER: tuple[str, ...] = tuple(FACILITY_CORE.keys())

DATA_URI_RE = re.compile(r"data:image/([^;]+);base64,([A-Za-z0-9+/=\s]+)", re.IGNORECASE)


def pick_facility_image_size(logical_w: int, logical_h: int) -> str:
    """根据设施实际占地比例计算生成图尺寸，保持宽高比与原图一致。"""
    max_dim = 1024
    if logical_w >= logical_h:
        w = min(logical_w, max_dim)
        h = max(int(w * logical_h / logical_w), 1)
    else:
        h = min(logical_h, max_dim)
        w = max(int(h * logical_w / logical_h), 1)
    # 对齐偶数像素
    w = (w // 2) * 2
    h = (h // 2) * 2
    return f"{w}x{h}"


def build_facility_prompt(facility_id: str, scale: int, extra_user: str) -> tuple[str, str]:
    fid = facility_id.strip().lower()
    if fid not in FACILITY_CORE:
        known = ", ".join(sorted(FACILITY_CORE.keys()))
        raise ValueError(f"未知 facility-id：{facility_id!r}。可选：{known}")
    name, w, h = FACILITY_CORE[fid]
    lw, lh = w * scale, h * scale
    size = pick_facility_image_size(lw, lh)
    core = (
        f"【完整的独立建筑像素贴图】id={fid}（{name}）。"
        f"这是一个独立建筑物的完整像素图，不是从大场景中裁切的局部——建筑的整体轮廓必须在画面中完整呈现。"
        f"逻辑占地约 {w}×{h}px（当前 scale={scale} → 目标约 {lw}×{lh}），"
        f"生成图实际尺寸为 {size}，宽高比 {lw}:{lh} 请严格匹配。"
        f"16-bit正交俯视（orthographic top-down）像素设施，建筑与画布轴对齐、不倾斜不旋转；"
        f"以屋顶与占地轮廓为主，冷钢蓝/板岩灰低饱和；工业科幻顶视剪影细节。"
        f"像素色块分明、边缘锐利；无文字无角色（设施顶视符号除外）。"
        f"★ 用于大地图矩形格网对齐摆放；仅建筑主体 + 统一纯色背景，无地面/道路/天空/植被。"
        f"★ 禁止等距透视与 3/4 斜视角；建筑完整轮廓居中，便于后期抠透明底。"
    )
    parts = [p for p in (extra_user.strip(), FACILITY_ART_STYLE_ZH, core) if p]
    prompt = "\n\n".join(parts)
    return prompt, size


def apply_map_preset(preset_name: str, extra_user: str) -> tuple[str, str, str]:
    key = preset_name.strip().lower()
    if key not in MAP_TILE_PRESETS:
        opts = ", ".join(sorted(MAP_TILE_PRESETS.keys()))
        raise ValueError(f"未知 preset：{preset_name!r}。可选：{opts}")
    p = MAP_TILE_PRESETS[key]
    hint = str(p["hint_zh"])
    label = str(p["label"])
    default_size = str(p["default_size"])
    default_quality = str(p.get("default_quality") or DEFAULT_FAST_QUALITY)
    parts = [p for p in (extra_user.strip(), GAME_ART_STYLE_ZH, f"【{label}】{hint}") if p]
    return "\n\n".join(parts), default_size, default_quality


def apply_npc_portrait_preset(npc_id: str, extra_user: str) -> tuple[str, str, str]:
    """为 NPC 构建角色立绘提示词。"""
    nid = npc_id.strip().lower()
    if nid not in NPC_PORTRAIT_PRESETS:
        opts = ", ".join(sorted(NPC_PORTRAIT_PRESETS.keys()))
        raise ValueError(f"未知 NPC id：{npc_id!r}。可选：{opts}")
    p = NPC_PORTRAIT_PRESETS[nid]
    label = str(p["label"])
    visual = str(p["visual_zh"])
    color = str(p.get("color_hint", ""))
    default_size = str(p.get("default_size", "512x768"))
    parts = [
        extra_user.strip(),
        PORTRAIT_ART_STYLE_ZH,
        f"【角色：{label}】{visual}",
        color,
    ]
    prompt = "\n\n".join([part for part in parts if part])
    return prompt, default_size, DEFAULT_FAST_QUALITY


def apply_icon_preset(icon_id: str, extra_user: str) -> tuple[str, str, str]:
    """为图标构建提示词。"""
    iid = icon_id.strip().lower()
    if iid not in ICON_PRESETS:
        opts = ", ".join(sorted(ICON_PRESETS.keys()))
        raise ValueError(f"未知 icon id：{icon_id!r}。可选：{opts}")
    p = ICON_PRESETS[iid]
    label = str(p["label"])
    visual = str(p["visual_zh"])
    default_size = str(p.get("default_size", "256x256"))
    parts = [
        extra_user.strip(),
        ICON_ART_STYLE_ZH,
        f"【{label}】{visual}",
    ]
    prompt = "\n\n".join([part for part in parts if part])
    return prompt, default_size, DEFAULT_FAST_QUALITY


def _load_dotenv_file(path: Path, *, override: bool = False) -> None:
    if not path.is_file():
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        if not key:
            continue
        if not override and key in os.environ and os.environ[key] != "":
            continue
        os.environ[key] = val


def bootstrap_env() -> None:
    ordered = [
        REPO_ROOT / ".env.txt",
        REPO_ROOT / ".env",
        TOOLS_DIR / ".env.txt",
        TOOLS_DIR / ".env",
    ]
    try:
        from dotenv import load_dotenv

        for p in ordered:
            load_dotenv(p)
    except ImportError:
        for p in ordered:
            _load_dotenv_file(p, override=False)


def normalize_backend(raw: str) -> str:
    s = (raw or "").strip().lower().replace("_", "-")
    aliases = {
        "openai": "openai-chat",
        "chat": "openai-chat",
        "chat-completions": "openai-chat",
        "images": "openai-images",
        "openai-image": "openai-images",
        "openai-images-api": "openai-images",
        "google": "gemini",
        "gemini-image": "gemini",
    }
    return aliases.get(s, s)


def size_to_gemini_aspect_ratio(size: str) -> str:
    """将 WxH 粗映射为 Gemini imageConfig 常用 aspectRatio 字符串。"""
    override = os.getenv("GEMINI_IMAGE_ASPECT_RATIO", "").strip()
    if override:
        return override
    s = size.lower().replace(" ", "")
    if "x" not in s:
        return "1:1"
    a, _, b = s.partition("x")
    try:
        w, h = float(a), float(b)
    except ValueError:
        return "1:1"
    if h <= 0:
        return "1:1"
    r = w / h
    if abs(r - 1.0) < 0.08:
        return "1:1"
    if r >= 1.45:
        return "16:9"
    if r <= 0.69:
        return "9:16"
    if r >= 1.1:
        return "4:3"
    return "3:4"


def read_runtime_config() -> dict[str, Any]:
    """聚合后端、Base URL、密钥、超时等。

    若 `.env` 中只配置了 OPENAI_BASE_URL，则 Gemini 生图默认指向同一 BASE（与扩写、OpenAI 生图一致）。
    """
    bootstrap_env()
    backend = normalize_backend(os.getenv("IMAGE_GEN_BACKEND", "gemini"))
    if backend not in ("gemini", "openai-chat", "openai-images"):
        backend = "gemini"

    raw_post = os.getenv("OPENAI_TIMEOUT", "1800").strip()
    post_timeout: float | None
    if raw_post in {"", "0", "none", "None", "inf"}:
        post_timeout = None
    else:
        post_timeout = float(raw_post)
    download_timeout = float(os.getenv("OPENAI_DOWNLOAD_TIMEOUT", "120"))

    openai_base_env = os.getenv("OPENAI_BASE_URL", "").strip().rstrip("/")
    openai_base = openai_base_env or "http://35.220.164.252:3888"

    gemini_explicit = os.getenv("GEMINI_BASE_URL", "").strip().rstrip("/")
    if gemini_explicit:
        gemini_base = gemini_explicit
    elif openai_base_env:
        gemini_base = openai_base_env
    else:
        gemini_base = DEFAULT_GEMINI_BASE

    gemini_model = os.getenv("GEMINI_IMAGE_MODEL", DEFAULT_GEMINI_IMAGE_MODEL).strip() or DEFAULT_GEMINI_IMAGE_MODEL
    gemini_key = (
        os.getenv("GEMINI_API_KEY", "").strip()
        or os.getenv("GOOGLE_API_KEY", "").strip()
        or os.getenv("OPENAI_API_KEY", "").strip()
    )
    gemini_auth = os.getenv("GEMINI_AUTH", "").strip().lower()
    if gemini_auth not in ("query", "header", "bearer", ""):
        gemini_auth = "query"
    if not gemini_auth:
        host = urlparse(gemini_base).netloc.lower()
        gemini_auth = "query" if "googleapis.com" in host else "bearer"

    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    image_model_default = (
        os.getenv("GEMINI_IMAGE_MODEL", "").strip()
        or os.getenv("OPENAI_IMAGE_MODEL", "").strip()
        or DEFAULT_IMAGE_MODEL
    )
    openai_chat_model = (
        os.getenv("OPENAI_CHAT_MODEL", "").strip()
        or os.getenv("OPENAI_MODEL", "").strip()
        or image_model_default
    )
    openai_image_model = os.getenv("OPENAI_IMAGE_MODEL", image_model_default).strip() or image_model_default

    prompt_refine_base = os.getenv("OPENAI_PROMPT_LLM_BASE_URL", "").strip().rstrip("/") or openai_base
    prompt_refine_model = os.getenv("IMAGE_PROMPT_LLM_MODEL", "deepseek-ai/DeepSeek-R1").strip() or "deepseek-ai/DeepSeek-R1"
    raw_refine_to = os.getenv("OPENAI_PROMPT_REFINE_TIMEOUT", "120").strip()
    prompt_refine_timeout: float | None
    if raw_refine_to in {"", "0", "none", "None", "inf"}:
        prompt_refine_timeout = None
    else:
        prompt_refine_timeout = float(raw_refine_to)
    try:
        prompt_refine_temperature = float(os.getenv("IMAGE_PROMPT_LLM_TEMPERATURE", "0.65"))
    except ValueError:
        prompt_refine_temperature = 0.65

    return {
        "backend": backend,
        "post_timeout": post_timeout,
        "download_timeout": download_timeout,
        "gemini_base": gemini_base,
        "gemini_model": gemini_model,
        "gemini_key": gemini_key,
        "gemini_auth": gemini_auth,
        "openai_base": openai_base,
        "openai_key": openai_key,
        "openai_chat_model": openai_chat_model,
        "openai_image_model": openai_image_model,
        "prompt_refine_base": prompt_refine_base,
        "prompt_refine_model": prompt_refine_model,
        "prompt_refine_timeout": prompt_refine_timeout,
        "prompt_refine_temperature": prompt_refine_temperature,
    }


def generations_endpoint_openai_images(base_url: str) -> str:
    rel = os.getenv("OPENAI_IMAGE_GENERATIONS_PATH", "v1/images/generations").strip().strip("/").lstrip("/")
    return f"{base_url.rstrip('/')}/{rel}"


def chat_completions_endpoint(base_url: str) -> str:
    rel = os.getenv("OPENAI_CHAT_COMPLETIONS_PATH", "v1/chat/completions").strip().strip("/").lstrip("/")
    return f"{base_url.rstrip('/')}/{rel}"


def extract_assistant_text_from_chat_completion(result: dict[str, Any]) -> str:
    choices = result.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    ch0 = choices[0]
    if not isinstance(ch0, dict):
        return ""
    msg = ch0.get("message")
    if not isinstance(msg, dict):
        return ""
    content = msg.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") in ("text", "output_text") and isinstance(part.get("text"), str):
                chunks.append(part["text"])
        return "".join(chunks).strip()
    return ""


def strip_markdown_fences(text: str) -> str:
    t = text.strip()
    if not t.startswith("```"):
        return t
    lines = t.split("\n")
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def refine_image_prompt_with_llm(
    draft_brief: str,
    cfg: dict[str, Any],
    *,
    model: str,
    timeout: float | None,
    retries: int,
    retry_delay: float,
    retry_jitter: float,
    temperature: float,
) -> str:
    endpoint = chat_completions_endpoint(cfg["prompt_refine_base"])
    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": PROMPT_REFINE_SYSTEM},
            {
                "role": "user",
                "content": (
                    "Brief / constraints for one game asset image:\n\n"
                    f"{draft_brief}\n\n"
                    "Produce the single English image-generation prompt."
                ),
            },
        ],
        "temperature": max(0.0, min(2.0, temperature)),
    }
    key = cfg["openai_key"]
    result = _post_json_retry_ex(
        endpoint,
        body,
        bearer=key,
        extra_headers=None,
        timeout=timeout,
        retries=max(1, retries),
        retry_delay=max(0.0, retry_delay),
        retry_jitter=max(0.0, retry_jitter),
    )
    text = strip_markdown_fences(extract_assistant_text_from_chat_completion(result))
    if not text:
        raise RuntimeError(f"LLM 未返回可用正文：{json.dumps(result, ensure_ascii=False)[:800]}")
    return text


def gemini_generate_content_url(base_url: str, model_id: str) -> str:
    rel = os.getenv("GEMINI_GENERATE_CONTENT_PATH", "").strip()
    if rel:
        return f"{base_url.rstrip('/')}/{rel.lstrip('/')}"
    mid = quote(model_id, safe="")
    return f"{base_url.rstrip('/')}/v1beta/models/{mid}:generateContent"


def _post_json_ex(
    url: str,
    body: dict[str, Any],
    *,
    bearer: str | None,
    extra_headers: dict[str, str] | None,
    timeout: float | None,
) -> dict[str, Any]:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {detail}") from e
    except http.client.IncompleteRead as e:
        raise RuntimeError(f"IncompleteRead（响应截断，可重试）: {e}") from e
    return json.loads(raw) if raw.strip() else {}


def _post_json_retry_ex(
    url: str,
    body: dict[str, Any],
    *,
    bearer: str | None,
    extra_headers: dict[str, str] | None,
    timeout: float | None,
    retries: int,
    retry_delay: float,
    retry_jitter: float,
) -> dict[str, Any]:
    last: BaseException | None = None
    for attempt in range(1, retries + 1):
        try:
            return _post_json_ex(url, body, bearer=bearer, extra_headers=extra_headers, timeout=timeout)
        except (RuntimeError, urllib.error.URLError, TimeoutError, OSError, http.client.IncompleteRead) as e:
            last = e
            msg = str(e).lower()
            retryable = isinstance(e, urllib.error.URLError) or isinstance(e, TimeoutError) or isinstance(e, http.client.IncompleteRead)
            if isinstance(e, RuntimeError):
                retryable = any(x in msg for x in ("502", "503", "504", "timeout", "timed out", "incomplete"))
            if attempt >= retries or not retryable:
                raise
            sleep_s = retry_delay * attempt + random.uniform(0, retry_jitter)
            print(f"[retry] 第 {attempt}/{retries} 次失败（{e}），{sleep_s:.1f}s 后重试…", file=sys.stderr)
            time.sleep(sleep_s)
    assert last is not None
    raise last


def _download_binary(img_url: str, timeout: float) -> bytes:
    req = urllib.request.Request(img_url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _guess_ext_from_content(data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return ".png"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data.startswith(b"RIFF") and b"WEBP" in data[:12]:
        return ".webp"
    return ".bin"


def _find_bg_from_corners(img) -> tuple[int, int, int]:
    """从边缘（四角+四边）采样找背景色。
    比全图频率更可靠：图标/建筑主体通常居中，边缘大概率是背景。"""
    from collections import Counter

    pixels = img.load()
    w, h = img.size
    margin = max(2, min(w, h) // 20)
    samples: list[tuple[int, int, int]] = []
    # 上下边
    for x in range(w):
        for y in range(margin):
            samples.append(pixels[x, y][:3])
        for y in range(h - margin, h):
            samples.append(pixels[x, y][:3])
    # 左右边（去重角）
    for y in range(margin, h - margin):
        for x in range(margin):
            samples.append(pixels[x, y][:3])
        for x in range(w - margin, w):
            samples.append(pixels[x, y][:3])

    qf = 256 / 8
    ctr: Counter = Counter()
    for r, g, b in samples:
        ctr[(int(r / qf), int(g / qf), int(b / qf))] += 1
    if not ctr:
        return (0, 0, 0)
    dq = ctr.most_common(1)[0][0]
    return tuple(max(0, min(255, int((v + 0.5) * qf))) for v in dq)  # type: ignore[return-value]


def _make_edges_transparent(img, edge_width: int) -> None:
    """将图片最外层 edge_width 像素强制设为 alpha=0（参考 Pixel Eternal remove_background.py）。"""
    if edge_width <= 0:
        return
    pixels = img.load()
    width, height = img.size
    for y in range(height):
        for x in range(width):
            if (x < edge_width or x >= width - edge_width or
                    y < edge_width or y >= height - edge_width):
                pixel = pixels[x, y]
                pixels[x, y] = (pixel[0], pixel[1], pixel[2], 0)


def _erode_isolated_opaque(img) -> int:
    """形态学腐蚀：4-邻域有 ≥3 个透明邻居的不透明像素 → 透明。清理单像素噪点。"""
    pixels = img.load()
    w, h = img.size
    to_clear: list[tuple[int, int]] = []
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            if pixels[x, y][3] == 0:
                continue
            transparent_neighbors = 0
            for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                if pixels[x + dx, y + dy][3] == 0:
                    transparent_neighbors += 1
            if transparent_neighbors >= 3:
                to_clear.append((x, y))
    for x, y in to_clear:
        p = pixels[x, y]
        pixels[x, y] = (p[0], p[1], p[2], 0)
    return len(to_clear)


def _remove_background_rgba(img, tolerance: int = 100, edge_width: int = 2) -> Any:
    """移除 AI 生成图的纯色背景，转为透明。

    策略：边缘采样找背景色 → BFS flood-fill 从四边开始泛洪 → 只移除与边缘连通的背景
    → 边缘强制透明 → 腐蚀孤立像素。
    BFS 比全局遍历更精确：不会误伤主体内部与背景色相近的像素。
    tolerance 默认 100（AI 生成背景有微妙变化，需要大容差才能覆盖）。"""
    from collections import deque

    bg_color = _find_bg_from_corners(img)
    target_rgb = bg_color[:3]
    print(f"[bg-removal] 边缘采样背景色: RGB{target_rgb}", file=sys.stderr)

    tol2 = tolerance ** 2
    pixels = img.load()
    w, h = img.size
    visited = bytearray(w * h)
    q: deque[tuple[int, int]] = deque()

    def _idx(x: int, y: int) -> int:
        return y * w + x

    def _is_bg(px) -> bool:
        return sum((a - b) ** 2 for a, b in zip(px[:3], target_rgb)) <= tol2

    # 四边入队
    for x in range(w):
        for y in (0, h - 1):
            q.append((x, y))
            visited[_idx(x, y)] = 1
    for y in range(1, h - 1):
        for x in (0, w - 1):
            q.append((x, y))
            visited[_idx(x, y)] = 1

    removed = 0
    while q:
        x, y = q.popleft()
        px = pixels[x, y]
        if _is_bg(px):
            pixels[x, y] = (px[0], px[1], px[2], 0)
            removed += 1
            for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    ni = _idx(nx, ny)
                    if not visited[ni]:
                        visited[ni] = 1
                        q.append((nx, ny))

    print(f"[bg-removal] BFS 移除连通背景: {removed} 像素", file=sys.stderr)

    # 边缘强制透明
    if edge_width > 0:
        _make_edges_transparent(img, edge_width)

    # 腐蚀孤立不透明像素（清理残留噪点）
    n_eroded = _erode_isolated_opaque(img)
    if n_eroded:
        print(f"[bg-removal] 腐蚀清理孤立像素: {n_eroded} 个", file=sys.stderr)

    return img


def _load_rgba_image(raw_img: bytes):
    import importlib

    spec = importlib.util.find_spec("PIL")
    if spec is None:
        return None
    from PIL import Image

    img = Image.open(io.BytesIO(raw_img))
    if img.mode in ("RGB", "P", "L", "1", "CMYK"):
        return img.convert("RGBA")
    if img.mode not in ("RGBA", "LA"):
        return img.convert("RGBA")
    return img


def _rgba_image_to_png_bytes(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False)
    return buf.getvalue()


def _flatten_rgba_on_color(img, bg_rgb: tuple[int, int, int] = (240, 240, 240)):
    """将透明底叠到纯色上，便于多模态 API 识别 sprite（避免透明通道显示异常）。"""
    from PIL import Image

    bg = Image.new("RGBA", img.size, (*bg_rgb, 255))
    flat = Image.alpha_composite(bg, img.convert("RGBA"))
    return flat.convert("RGB")


def _to_png_bytes(
    raw_img: bytes,
    tolerance: int = 30,
    edge_width: int = 1,
    *,
    remove_bg: bool = True,
) -> bytes:
    """将任意图片格式 raw bytes 转为 PNG bytes。PIL 不可用时回退原始数据。"""
    try:
        img = _load_rgba_image(raw_img)
        if img is None:
            print("[warn] PIL/Pillow 未安装，无法处理透明底。请 pip install Pillow", file=sys.stderr)
            return raw_img
        if remove_bg:
            img = _remove_background_rgba(img, tolerance=tolerance, edge_width=edge_width)
        return _rgba_image_to_png_bytes(img)
    except Exception as e:
        print(f"[warn] 图片转透明PNG失败（{e}），保留原始格式。", file=sys.stderr)
        return raw_img


def prepare_style_reference(
    path: Path,
    *,
    remove_bg: bool,
    flatten: bool,
    tolerance: int,
    edge_width: int,
) -> tuple[bytes, str] | None:
    """读取参考图：可选抠图 → 可选铺浅灰底 → 返回供 Gemini inlineData 使用的 PNG。"""
    if not path.is_file():
        print(f"[style-ref] 参考图不存在：{path}", file=sys.stderr)
        return None
    raw = path.read_bytes()
    try:
        img = _load_rgba_image(raw)
        if img is None:
            print("[style-ref] 需要 Pillow 处理参考图。", file=sys.stderr)
            return raw, "image/png"
        if remove_bg:
            img = _remove_background_rgba(img, tolerance=tolerance, edge_width=edge_width)
            print(f"[style-ref] 已抠图：{path.name}", file=sys.stderr)
        if flatten:
            img = _flatten_rgba_on_color(img)
            print("[style-ref] 透明底已铺浅灰底后送入模型（仅作风格参考）", file=sys.stderr)
            return _rgba_image_to_png_bytes(img.convert("RGB")), "image/png"
        return _rgba_image_to_png_bytes(img), "image/png"
    except Exception as e:
        print(f"[style-ref] 处理失败（{e}），尝试原图。", file=sys.stderr)
        return raw, "image/png"


def resolve_style_reference(args: argparse.Namespace, preset: str) -> tuple[bytes, str] | None:
    if getattr(args, "no_style_ref", False):
        return None
    explicit = (getattr(args, "style_ref", "") or os.getenv("IMAGE_STYLE_REF", "")).strip()
    if preset == "icon":
        return None
    auto_facility = preset == "facility" and os.getenv("IMAGE_STYLE_REF_AUTO", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    path_s = explicit
    if not path_s and auto_facility and DEFAULT_FACILITY_STYLE_REF.is_file():
        path_s = str(DEFAULT_FACILITY_STYLE_REF)
    if not path_s:
        return None
    path = Path(path_s)
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    remove_bg = not getattr(args, "no_style_ref_remove_bg", False)
    flatten = not getattr(args, "no_style_ref_flatten", False)
    return prepare_style_reference(
        path,
        remove_bg=remove_bg,
        flatten=flatten,
        tolerance=int(getattr(args, "bg_tolerance", 30)),
        edge_width=int(getattr(args, "bg_edge_width", 1)),
    )


def _mime_to_ext(mime: str) -> str:
    m = (mime or "").lower().split(";")[0].strip()
    sub = m.split("/")[-1] if "/" in m else "png"
    if sub == "jpeg":
        return ".jpg"
    if sub in ("png", "jpg", "webp", "gif"):
        return f".{sub}"
    return ".png"


def _deep_collect_gemini_inline_parts(obj: Any, acc: list[tuple[bytes, str]]) -> None:
    if isinstance(obj, dict):
        inline = obj.get("inlineData") or obj.get("inline_data")
        if isinstance(inline, dict):
            raw_b64 = inline.get("data")
            mime = str(inline.get("mimeType") or inline.get("mime_type") or "image/png")
            if isinstance(raw_b64, str):
                try:
                    acc.append((base64.b64decode(raw_b64), mime))
                except (ValueError, TypeError):
                    pass
        for v in obj.values():
            _deep_collect_gemini_inline_parts(v, acc)
    elif isinstance(obj, list):
        for x in obj:
            _deep_collect_gemini_inline_parts(x, acc)


def extract_images_gemini(result: dict[str, Any]) -> list[tuple[bytes, str]]:
    acc: list[tuple[bytes, str]] = []
    _deep_collect_gemini_inline_parts(result, acc)
    candidates = result.get("candidates")
    if isinstance(candidates, list):
        for c in candidates:
            if not isinstance(c, dict):
                continue
            content = c.get("content")
            if isinstance(content, dict):
                parts = content.get("parts")
                if isinstance(parts, list):
                    for p in parts:
                        if not isinstance(p, dict):
                            continue
                        if isinstance(p.get("text"), str):
                            _extract_from_text_blob(p["text"], acc)
    return acc


def _extract_from_text_blob(text: str, acc: list[tuple[bytes, str]]) -> None:
    for m in DATA_URI_RE.finditer(text):
        mime_part = m.group(1).strip().lower()
        mime = f"image/{mime_part}" if "/" not in mime_part else mime_part
        try:
            acc.append((base64.b64decode(m.group(2)), mime))
        except (ValueError, TypeError):
            pass


def extract_images_openai_chat(result: dict[str, Any]) -> list[tuple[bytes, str]]:
    """解析 chat/completions：兼容 inlineData、data: URL、OpenAI images 风格 data[]。"""
    acc: list[tuple[bytes, str]] = []
    _deep_collect_gemini_inline_parts(result, acc)
    choices = result.get("choices")
    if isinstance(choices, list):
        for ch in choices:
            if not isinstance(ch, dict):
                continue
            msg = ch.get("message")
            if isinstance(msg, dict):
                content = msg.get("content")
                if isinstance(content, str):
                    _extract_from_text_blob(content, acc)
                    try:
                        parsed = json.loads(content)
                        _deep_collect_gemini_inline_parts(parsed, acc)
                        data_list = parsed.get("data") if isinstance(parsed, dict) else None
                        if isinstance(data_list, list):
                            for item in data_list:
                                if isinstance(item, dict) and item.get("b64_json"):
                                    try:
                                        acc.append((base64.b64decode(str(item["b64_json"])), "image/png"))
                                    except (ValueError, TypeError):
                                        pass
                    except (json.JSONDecodeError, TypeError):
                        pass
                elif isinstance(content, list):
                    for part in content:
                        if not isinstance(part, dict):
                            continue
                        if part.get("type") == "image_url" and isinstance(part.get("image_url"), dict):
                            u = part["image_url"].get("url")
                            if isinstance(u, str) and u.startswith("data:"):
                                _extract_from_text_blob(u, acc)
    return acc


def extract_images_openai_images(result: dict[str, Any], download_timeout: float) -> list[tuple[bytes, str]]:
    out: list[tuple[bytes, str]] = []
    data_list = result.get("data")
    if not isinstance(data_list, list):
        return out
    for item in data_list:
        if not isinstance(item, dict):
            continue
        if item.get("b64_json"):
            try:
                out.append((base64.b64decode(str(item["b64_json"])), "image/png"))
            except (ValueError, TypeError):
                pass
        elif item.get("url"):
            try:
                raw = _download_binary(str(item["url"]), download_timeout)
                out.append((raw, "image/unknown"))
            except (urllib.error.URLError, TimeoutError, OSError):
                pass
    return out


def build_gemini_request_body(
    prompt: str,
    size: str,
    merge_extra: dict[str, Any],
    *,
    style_ref: tuple[bytes, str] | None = None,
) -> dict[str, Any]:
    aspect = size_to_gemini_aspect_ratio(size)
    gen_cfg: dict[str, Any] = {"responseModalities": ["IMAGE"]}
    if os.getenv("GEMINI_USE_ASPECT_RATIO", "1").strip().lower() not in {"0", "false", "no", ""}:
        gen_cfg["imageConfig"] = {"aspectRatio": aspect}
    parts: list[dict[str, Any]] = []
    if style_ref:
        ref_bytes, mime = style_ref
        parts.append(
            {
                "inlineData": {
                    "mimeType": mime,
                    "data": base64.b64encode(ref_bytes).decode("ascii"),
                }
            }
        )
        parts.append({"text": STYLE_REF_INSTRUCTION + prompt})
    else:
        parts.append({"text": prompt})
    body: dict[str, Any] = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": gen_cfg,
    }
    if merge_extra:
        for k, v in merge_extra.items():
            if k in body and isinstance(body[k], dict) and isinstance(v, dict):
                body[k] = {**body[k], **v}
            else:
                body[k] = v
    return body


def gemini_request_url_and_headers(cfg: dict[str, Any], api_key: str) -> tuple[str, dict[str, str], str | None]:
    url = gemini_generate_content_url(cfg["gemini_base"], cfg["gemini_model"])
    auth = cfg["gemini_auth"]
    extra: dict[str, str] = {}
    bearer: str | None = None
    if auth == "query":
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}{urlencode({'key': api_key})}"
    elif auth == "header":
        extra["x-goog-api-key"] = api_key
    else:
        bearer = api_key
    return url, extra, bearer


def _safe_filename_from_prompt(prompt: str) -> str:
    s = "".join(c if c.isalnum() or c in "._- " else "_" for c in prompt.strip())
    return "_".join(s.split())[:80] or "image"


def default_out_dir_for_preset(preset: str, facility_id: str) -> str:
    if preset == "facility" and facility_id:
        return str(REPO_ROOT / "assets" / "facilities_generated")
    if preset == "portrait" and facility_id:
        return str(REPO_ROOT / "assets" / "portraits_generated")
    if preset == "icon" and facility_id:
        return str(REPO_ROOT / "assets" / "icons_generated")
    if preset in MAP_TILE_PRESETS:
        return str(REPO_ROOT / "assets" / "map_tiles_generated")
    return "generated_images"


def prompt_refine_enabled(args: argparse.Namespace) -> bool:
    if getattr(args, "no_refine_prompt", False):
        return False
    return os.getenv("IMAGE_PROMPT_LLM", "1").strip().lower() not in {"0", "false", "no", "off"}


def parse_merge_extra_args(extra_json_arg: str) -> tuple[dict[str, Any] | None, int]:
    if not (extra_json_arg or "").strip():
        return {}, 0
    try:
        loaded = json.loads(extra_json_arg)
        if not isinstance(loaded, dict):
            print("extra-json 须为 JSON 对象")
            return None, 1
        return loaded, 0
    except (json.JSONDecodeError, ValueError) as e:
        print(f"解析 --extra-json 失败：{e}")
        return None, 1


def generate_once(
    cfg: dict[str, Any],
    backend: str,
    args: argparse.Namespace,
    *,
    preset: str,
    facility_id: str,
    user_prompt: str,
    merge_extra: dict[str, Any],
    post_timeout: float | None,
    download_timeout: float,
    dry_run: bool,
    filename_stem: str | None = None,
    batch_label: str | None = None,
) -> int:
    """执行单次：简报 → 扩写 → 生图 → 保存。filename_stem 非空时作为文件名主干（如 tile_void）。"""
    default_quality_from_preset = ""
    suggested_size = os.getenv("OPENAI_IMAGE_SIZE") or DEFAULT_FAST_SIZE
    try:
        if preset in MAP_TILE_PRESETS:
            full_prompt, suggested_size, default_quality_from_preset = apply_map_preset(preset, user_prompt)
        elif preset == "facility":
            full_prompt, suggested_size = build_facility_prompt(facility_id, args.scale, user_prompt)
            default_quality_from_preset = DEFAULT_FAST_QUALITY
        elif preset == "portrait" and facility_id:
            full_prompt, suggested_size, default_quality_from_preset = apply_npc_portrait_preset(facility_id, user_prompt)
        elif preset == "icon" and facility_id:
            full_prompt, suggested_size, default_quality_from_preset = apply_icon_preset(facility_id, user_prompt)
        elif preset in ("portrait", "icon") and not facility_id:
            print(f"使用 --preset {preset} 时必须提供 --npc-id / --icon-id。")
            return 1
        else:
            full_prompt = user_prompt
            if not full_prompt:
                print("提示词为空。")
                return 1
    except ValueError as e:
        print(str(e))
        return 1

    if not full_prompt:
        print("提示词为空。")
        return 1

    image_prompt = full_prompt
    if prompt_refine_enabled(args):
        if not cfg["openai_key"]:
            print("[refine] 缺少 OPENAI_API_KEY（请在仓库 .env 配置；与生图共用同一密钥）。", file=sys.stderr)
        else:
            refine_model = (args.refine_model or cfg["prompt_refine_model"]).strip()
            ep = chat_completions_endpoint(cfg["prompt_refine_base"])
            tag = f" [{batch_label}]" if batch_label else ""
            print(f"[refine]{tag} POST {ep}\nmodel={refine_model!r}（简报 → 英文生图 prompt）", flush=True)
            try:
                image_prompt = refine_image_prompt_with_llm(
                    full_prompt,
                    cfg,
                    model=refine_model,
                    timeout=cfg["prompt_refine_timeout"],
                    retries=max(1, min(args.retries, 5)),
                    retry_delay=max(0.0, args.retry_delay),
                    retry_jitter=max(0.0, args.retry_jitter),
                    temperature=float(cfg["prompt_refine_temperature"]),
                )
                print(f"[refine]{tag} 生图提示词：\n{image_prompt}\n", flush=True)
            except (RuntimeError, OSError, urllib.error.URLError, TimeoutError, ValueError, TypeError) as e:
                print(f"[refine]{tag} 扩写失败，回退原始简报：{e}", file=sys.stderr)
                image_prompt = full_prompt

    style_ref_preview = resolve_style_reference(args, preset)

    if dry_run:
        tag = f" [{batch_label}]" if batch_label else ""
        print(f"[DRY_RUN]{tag} backend={backend}")
        if style_ref_preview:
            print("[DRY_RUN] style_ref=on（参考图将随请求发送）")
        print(f"draft brief:\n{full_prompt[:1600]}" + ("…" if len(full_prompt) > 1600 else ""))
        if image_prompt != full_prompt:
            print(f"\nrefined image prompt:\n{image_prompt[:1600]}" + ("…" if len(image_prompt) > 1600 else ""))
        return 0

    size = (args.size or suggested_size or DEFAULT_FAST_SIZE).strip()
    quality = (args.quality or os.getenv("OPENAI_IMAGE_QUALITY") or default_quality_from_preset or "").strip()

    style_ref = style_ref_preview
    if style_ref and backend not in ("gemini", "openai-chat"):
        print("[style-ref] 仅 gemini / openai-chat 支持参考图，已忽略。", file=sys.stderr)

    all_saved: list[tuple[bytes, str]] = []

    try:
        if backend == "gemini":
            api_key = cfg["gemini_key"]
            if not api_key:
                print("缺少 API 密钥：请在 .env 配置 OPENAI_API_KEY（Gemini 未单独配置 GEMINI_API_KEY 时将使用该密钥）。")
                return 1
            model_id = (args.model or cfg["gemini_model"]).strip()
            gemini_cfg = {**cfg, "gemini_model": model_id}
            url, extra_h, bearer = gemini_request_url_and_headers(gemini_cfg, api_key)
            tag = f"[{batch_label}] " if batch_label else ""
            ref_note = " +style_ref" if style_ref else ""
            print(
                f"{tag}POST {url.split('?')[0]} …\nmodel={model_id!r} aspect≈{size_to_gemini_aspect_ratio(size)!r} n={args.n}{ref_note}",
                flush=True,
            )
            for _ in range(args.n):
                body = build_gemini_request_body(
                    image_prompt,
                    size,
                    merge_extra,
                    style_ref=style_ref if backend == "gemini" else None,
                )
                result = _post_json_retry_ex(
                    url,
                    body,
                    bearer=bearer,
                    extra_headers=extra_h or None,
                    timeout=post_timeout,
                    retries=max(1, args.retries),
                    retry_delay=max(0.0, args.retry_delay),
                    retry_jitter=max(0.0, args.retry_jitter),
                )
                imgs = extract_images_gemini(result)
                if not imgs:
                    print(f"未解析到图片：{json.dumps(result, ensure_ascii=False)[:1400]}")
                    return 3
                all_saved.extend(imgs)

        elif backend == "openai-chat":
            api_key = cfg["openai_key"]
            if not api_key:
                print("缺少 OPENAI_API_KEY（仓库 .env；与生图、扩写共用）。")
                return 1
            model = (args.model or cfg["openai_chat_model"]).strip()
            endpoint = chat_completions_endpoint(cfg["openai_base"])
            tag = f"[{batch_label}] " if batch_label else ""
            ref_note = " +style_ref" if style_ref else ""
            print(f"{tag}POST {endpoint}\nmodel={model!r} n={args.n}{ref_note}", flush=True)
            for _ in range(args.n):
                if style_ref:
                    ref_bytes, mime = style_ref
                    b64 = base64.b64encode(ref_bytes).decode("ascii")
                    content: list[dict[str, Any]] = [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"},
                        },
                        {"type": "text", "text": STYLE_REF_INSTRUCTION + image_prompt},
                    ]
                else:
                    content = image_prompt
                body_chat: dict[str, Any] = {
                    "model": model,
                    "messages": [{"role": "user", "content": content}],
                }
                body_chat.update(merge_extra)
                result = _post_json_retry_ex(
                    endpoint,
                    body_chat,
                    bearer=api_key,
                    extra_headers=None,
                    timeout=post_timeout,
                    retries=max(1, args.retries),
                    retry_delay=max(0.0, args.retry_delay),
                    retry_jitter=max(0.0, args.retry_jitter),
                )
                imgs = extract_images_openai_chat(result)
                if not imgs:
                    print(f"未解析到图片：{json.dumps(result, ensure_ascii=False)[:1400]}")
                    return 3
                all_saved.extend(imgs)

        elif backend == "openai-images":
            api_key = cfg["openai_key"]
            if not api_key:
                print("缺少 OPENAI_API_KEY（仓库 .env；与生图、扩写共用）。")
                return 1
            model = (args.model or cfg["openai_image_model"]).strip()
            endpoint = generations_endpoint_openai_images(cfg["openai_base"])
            body_img: dict[str, Any] = {
                "model": model,
                "prompt": image_prompt,
                "n": args.n,
                "size": size,
            }
            if quality:
                body_img["quality"] = quality
            if args.prefer_b64 and "imagen" not in model.lower():
                body_img["response_format"] = "b64_json"
            body_img.update(merge_extra)
            tag = f"[{batch_label}] " if batch_label else ""
            print(f"{tag}POST {endpoint}\nmodel={model!r} size={size!r} n={args.n}", flush=True)
            result = _post_json_retry_ex(
                endpoint,
                body_img,
                bearer=api_key,
                extra_headers=None,
                timeout=post_timeout,
                retries=max(1, args.retries),
                retry_delay=max(0.0, args.retry_delay),
                retry_jitter=max(0.0, args.retry_jitter),
            )
            imgs = extract_images_openai_images(result, download_timeout)
            if not imgs:
                print(f"未在响应中找到图片：{json.dumps(result, ensure_ascii=False)[:1200]}")
                return 3
            all_saved.extend(imgs)

        else:
            print(f"未知后端：{backend}")
            return 1

    except (RuntimeError, urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"调用失败：{e}")
        return 2

    out_dir_s = args.out_dir.strip() or default_out_dir_for_preset(preset, facility_id)
    out_dir = Path(out_dir_s)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    if filename_stem:
        stem = filename_stem
    else:
        stem = _safe_filename_from_prompt(user_prompt or full_prompt[:120])
        if preset == "facility" and facility_id:
            stem = f"facility_{facility_id}_{args.scale}x_{stem}".strip("_")
        elif preset == "portrait" and facility_id:
            stem = f"portrait_{facility_id}".strip("_")
        elif preset == "icon" and facility_id:
            stem = f"icon_{facility_id}".strip("_")

    saved_paths: list[str] = []
    for i, (raw_img, mime) in enumerate(all_saved):
        # ── 统一转为 PNG（支持 α 通道透明），PIL 不可用时回退原始格式 ──
        bg_tol = getattr(args, "bg_tolerance", 30)
        bg_ew = getattr(args, "bg_edge_width", 1)
        png_bytes = _to_png_bytes(raw_img, tolerance=bg_tol, edge_width=bg_ew)
        ext = ".png"
        if args.out and len(all_saved) == 1 and i == 0:
            dest = Path(args.out).with_suffix(".png")
        elif args.out:
            p = Path(args.out)
            dest = p.with_stem(f"{p.stem}_{i + 1}").with_suffix(".png")
        else:
            dest = out_dir / f"{stem}_{ts}_{i + 1}{ext}"
        if not dest.suffix:
            dest = dest.with_suffix(".png")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(png_bytes)
        saved_paths.append(str(dest.resolve()))

    if not saved_paths:
        print("未保存任何文件。")
        return 4

    for pth in saved_paths:
        print(f"已保存：{Path(pth).resolve()}")

    return 0


def main() -> int:
    preset_choices = sorted(MAP_TILE_PRESETS.keys()) + ["facility", "portrait", "icon"]
    parser = argparse.ArgumentParser(description="游戏美术生图：Gemini generateContent / OpenAI chat / OpenAI images")
    parser.add_argument("prompt", nargs="?", default="", help="画面描述（可与 --preset 合并）")
    parser.add_argument(
        "--backend",
        "-b",
        default="",
        choices=["", "gemini", "openai-chat", "openai-images"],
        help="覆盖 IMAGE_GEN_BACKEND（默认 gemini，模型 gemini-3.1-flash-image-preview）",
    )
    parser.add_argument(
        "--preset",
        "-p",
        default="",
        choices=["", *preset_choices],
        help="void / road / build / facility / portrait / icon",
    )
    parser.add_argument("--facility-id", default="", help="--preset facility / portrait / icon 时指定目标 ID")
    parser.add_argument("--scale", type=int, default=2, choices=[1, 2], help="设施 scale（@2×）")
    parser.add_argument("--model", "-m", default="", help="覆盖当前后端模型（Gemini / chat / images）")
    parser.add_argument("--size", "-s", default="", help=f"尺寸 WxH；Gemini 映射为 aspectRatio（默认 {DEFAULT_FAST_SIZE}）")
    parser.add_argument("--n", type=int, default=1, choices=[1, 2, 3, 4], help="张数（Gemini 多次请求）")
    parser.add_argument("--quality", "-q", default="", help="仅 openai-images：low/medium/high")
    parser.add_argument("--out", "-o", default="", help="单张输出路径")
    parser.add_argument("--out-dir", default="", help="输出目录")
    parser.add_argument("--timeout", type=float, default=-1.0, help="POST 超时秒；-1 用 OPENAI_TIMEOUT；0 不限")
    parser.add_argument("--download-timeout", type=float, default=-1.0, help="-1 用 OPENAI_DOWNLOAD_TIMEOUT")
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--retry-delay", type=float, default=12.0)
    parser.add_argument("--retry-jitter", type=float, default=6.0)
    parser.add_argument("--extra-json", default="", help="合并到生图请求 JSON 顶层（高级）")
    parser.add_argument(
        "--bg-tolerance",
        type=int,
        default=80,
        help="背景移除容差（欧几里得距离平方，0-255，默认 80）。AI 生成背景有微妙变化，值越大移除越激进",
    )
    parser.add_argument(
        "--bg-edge-width",
        type=int,
        default=2,
        help="边缘强制透明宽度（像素，默认 2）。强制将画面最外层 N 像素设为透明",
    )
    parser.add_argument(
        "--style-ref",
        default="",
        help="画风参考图路径；设施 preset 默认用 assets/facilities_generated/_test_helipad.png",
    )
    parser.add_argument(
        "--no-style-ref",
        action="store_true",
        help="禁用参考图（不做人像/风格条件生成）",
    )
    parser.add_argument(
        "--no-style-ref-remove-bg",
        action="store_true",
        help="参考图不抠背景，原图送入模型",
    )
    parser.add_argument(
        "--no-style-ref-flatten",
        action="store_true",
        help="参考图抠图后保持透明通道（默认铺浅灰底再送入 API）",
    )
    parser.add_argument(
        "--no-refine-prompt",
        action="store_true",
        help="跳过对话模型扩写，直接把简报发给生图后端",
    )
    parser.add_argument(
        "--refine-model",
        default="",
        help="扩写提示词用的 chat 模型（默认 IMAGE_PROMPT_LLM_MODEL=gpt-4o-mini）",
    )
    parser.add_argument(
        "--all-map-tiles",
        action="store_true",
        help="一键依次生成 void / road / build 三种地砖贴图",
    )
    parser.add_argument(
        "--all-facilities",
        action="store_true",
        help="一键依次生成全部 13 个设施贴图",
    )
    parser.add_argument(
        "--all-npc-portraits",
        action="store_true",
        help="一键依次生成全部 8 个 NPC 立绘（含源）",
    )
    parser.add_argument(
        "--all-icons",
        action="store_true",
        help="一键依次生成全部 20 个图标（工坊设备+资源+面板+favicon）",
    )
    parser.add_argument(
        "--all-workshop-icons",
        action="store_true",
        help="一键依次生成全部 8 个工坊设备图标",
    )
    parser.add_argument(
        "--all-resource-icons",
        action="store_true",
        help="一键依次生成 5 个资源图标",
    )
    parser.add_argument(
        "--all-tab-icons",
        action="store_true",
        help="一键依次生成 6 个面板图标",
    )
    parser.add_argument(
        "--all-assets",
        action="store_true",
        help="一键生成所有缺失美术资源（地图瓦片+设施+NPC立绘+全部图标）",
    )
    parser.add_argument(
        "--missing-icons",
        action="store_true",
        help="补全所有尚未生成的图标（扫描 assets/icons_generated/，仅生成缺失的）",
    )
    _add_prefer_b64_args(parser)
    args = parser.parse_args()

    # ── 展开 --all-assets ──
    if args.all_assets:
        args.all_map_tiles = True
        args.all_facilities = True
        args.all_npc_portraits = True
        args.all_icons = True

    # ── 统计批处理标记 ──
    batch_flags = [
        args.all_map_tiles,
        args.all_facilities,
        args.all_npc_portraits,
        args.all_icons,
        args.all_workshop_icons,
        args.all_resource_icons,
        args.all_tab_icons,
        args.missing_icons,
    ]
    batch_count = sum(1 for b in batch_flags if b)

    user_prompt = (args.prompt or "").strip()
    preset = (args.preset or "").strip().lower()
    facility_id = (args.facility_id or "").strip().lower()

    if batch_count > 1:
        # --all-assets 允许组合（已展开为多个子标记）
        if not args.all_assets:
            print("注意：同时指定了多个批处理标记，将依次执行。")
    if batch_count == 1 and not args.all_assets:
        # 单个批处理标记不需要冲突检查
        pass

    if batch_count > 0:
        if preset or facility_id:
            print("错误：批处理标记不能与 --preset / --facility-id 同时使用。")
            return 1
        if args.out:
            print("错误：批处理不要使用 -o（自动命名输出文件）。")
            return 1

    if preset == "facility" and not facility_id:
        print("使用 --preset facility 时必须提供 --facility-id。")
        return 1
    if preset == "portrait" and not facility_id:
        print("使用 --preset portrait 时必须提供 --facility-id（NPC id）。可选："
              + ", ".join(NPC_PORTRAIT_ORDER))
        return 1
    if preset == "icon" and not facility_id:
        print("使用 --preset icon 时必须提供 --facility-id（图标 id）。可选："
              + ", ".join(ICON_ALL_ORDER))
        return 1

    if not batch_count:
        if preset not in MAP_TILE_PRESETS and preset not in ("facility", "portrait", "icon") and not user_prompt:
            print("请输入描述（单行），或使用 --preset / 批处理标记：")
            try:
                user_prompt = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n已取消。")
                return 1

    cfg = read_runtime_config()
    backend = normalize_backend(args.backend or cfg["backend"])

    post_timeout = cfg["post_timeout"]
    if args.timeout >= 0:
        post_timeout = None if args.timeout == 0 else args.timeout

    download_timeout = cfg["download_timeout"]
    if args.download_timeout >= 0:
        download_timeout = args.download_timeout

    merge_extra, mex_rc = parse_merge_extra_args(args.extra_json)
    if mex_rc != 0:
        return mex_rc

    dry = os.getenv("OPENAI_DRY_RUN", "").strip().lower() in {"1", "true", "yes"}

    # ── 辅助：执行一个批处理列表 ──
    def _run_batch(
        batch_name: str,
        items: tuple[str, ...],
        preset_mode: str,
        out_dir_hint_key: str,
        filename_stem_prefix: str,
        use_scale: bool = False,
    ) -> int:
        out_hint = str(REPO_ROOT / "assets" / out_dir_hint_key)
        print(f"[batch] {batch_name}：{', '.join(items)} → {out_hint}", flush=True)
        worst = 0
        for item in items:
            label = ""
            if preset_mode == "portrait":
                label = NPC_PORTRAIT_PRESETS.get(item, {}).get("label", item)
            elif preset_mode == "icon":
                label = ICON_PRESETS.get(item, {}).get("label", item)
            elif preset_mode == "facility":
                label = FACILITY_CORE.get(item, (item, 0, 0))[0]
            elif preset_mode in MAP_TILE_PRESETS:
                label = MAP_TILE_PRESETS.get(item, {}).get("label", item)
            else:
                label = item
            print(f"\n{'=' * 60}\n[batch] {item} — {label}\n{'=' * 60}", flush=True)
            stem = f"{filename_stem_prefix}{item}"
            rc = generate_once(
                cfg, backend, args,
                preset=preset_mode,
                facility_id=item if preset_mode in ("facility", "portrait", "icon") else "",
                user_prompt=user_prompt,
                merge_extra=merge_extra,
                post_timeout=post_timeout,
                download_timeout=download_timeout,
                dry_run=dry,
                filename_stem=stem,
                batch_label=item,
            )
            worst = max(worst, rc)
            if rc != 0:
                print(f"[batch] {item} 未成功（exit {rc}），继续下一个…", file=sys.stderr)
        return worst

    # ── 检测已生成的图标，返回缺失列表 ──
    def _find_missing_icons() -> list[str]:
        icons_dir = REPO_ROOT / "assets" / "icons_generated"
        existing: set[str] = set()
        if icons_dir.is_dir():
            for f in icons_dir.iterdir():
                if f.is_file() and f.suffix.lower() == ".png":
                    # 文件名格式: icon_{icon_id}_timestamp_N.png
                    name = f.stem  # e.g. icon_icon_miner_1779883849_1
                    # 提取 icon_id：去掉前缀 "icon_" 和后缀时间戳
                    parts = name.split("_")
                    # 格式: icon_ + {preset_key} + timestamp + serial
                    # 例如: "icon_icon_miner_1779883849_1" → "icon_miner"
                    # 实际格式: icon_ + preset_key → parts=["icon","icon_miner","1779883849","1"] 或 ["icon","icon","miner","timestamp","1"]
                    # 如果以 "icon_icon_" 开头，去掉第一个 "icon_" 前缀
                    if name.startswith("icon_icon_"):
                        stem_id = name[len("icon_icon_"):]  # e.g. "miner_1779883849_1"
                    elif name.startswith("icon_"):
                        stem_id = name[len("icon_"):]
                    else:
                        continue
                    # 去掉末尾的时间戳和序号 → 还原 icon_id
                    # 时间戳是纯数字，倒数第二个 _ 之前的部分是 icon_id
                    parts = stem_id.rsplit("_", 2)
                    if len(parts) >= 2 and parts[-1].isdigit() and parts[-2].isdigit():
                        icon_id = "_".join(parts[:-2])  # 处理带下划线的 id 如 "resource_energy"
                    elif len(parts) >= 1 and parts[-1].isdigit():
                        icon_id = "_".join(parts[:-1])
                    else:
                        icon_id = stem_id
                    if icon_id:
                        # 文件名解析出的 id 可能不带 "icon_" 前缀，补上再匹配
                        if icon_id in ICON_PRESETS:
                            existing.add(icon_id)
                        elif f"icon_{icon_id}" in ICON_PRESETS:
                            existing.add(f"icon_{icon_id}")
        missing = [iid for iid in ICON_ALL_ORDER if iid not in existing]
        return missing

    # ── 执行各批处理 ──
    batch_results: list[int] = []

    if args.all_map_tiles:
        batch_results.append(_run_batch(
            "一键地砖", MAP_TILE_PRESET_ORDER, "void",
            "map_tiles_generated", "tile_",
        ))

    if args.all_facilities:
        batch_results.append(_run_batch(
            "一键设施贴图", FACILITY_ORDER, "facility",
            "facilities_generated", "facility_",
        ))

    if args.all_npc_portraits:
        batch_results.append(_run_batch(
            "一键NPC立绘", NPC_PORTRAIT_ORDER, "portrait",
            "portraits_generated", "portrait_",
        ))

    if args.all_icons:
        batch_results.append(_run_batch(
            "一键全部图标", ICON_ALL_ORDER, "icon",
            "icons_generated", "icon_",
        ))
    else:
        if args.all_workshop_icons:
            batch_results.append(_run_batch(
                "一键工坊设备图标", ICON_WORKSHOP_ORDER, "icon",
                "icons_generated", "icon_",
            ))
        if args.all_resource_icons:
            batch_results.append(_run_batch(
                "一键资源图标", ICON_RESOURCE_ORDER, "icon",
                "icons_generated", "icon_",
            ))
        if args.all_tab_icons:
            batch_results.append(_run_batch(
                "一键面板图标", ICON_TAB_ORDER, "icon",
                "icons_generated", "icon_",
            ))

    if args.missing_icons:
        missing = _find_missing_icons()
        if not missing:
            print("所有图标已齐全，无需补全。")
        else:
            print(f"已生成 {len(ICON_ALL_ORDER) - len(missing)}/{len(ICON_ALL_ORDER)} 个，缺失 {len(missing)} 个：{', '.join(missing)}")
            batch_results.append(_run_batch(
                "补全缺失图标", tuple(missing), "icon",
                "icons_generated", "icon_",
            ))

    if batch_results:
        return max(batch_results)

    # ── 单次生成 ──
    return generate_once(
        cfg, backend, args,
        preset=preset,
        facility_id=facility_id,
        user_prompt=user_prompt,
        merge_extra=merge_extra,
        post_timeout=post_timeout,
        download_timeout=download_timeout,
        dry_run=dry,
        filename_stem=None,
        batch_label=None,
    )


if __name__ == "__main__":
    sys.exit(main())
