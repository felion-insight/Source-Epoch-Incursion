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
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import random
import re
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
DEFAULT_GEMINI_IMAGE_MODEL = "gemini-3.1-flash-image-preview"

GAME_ART_STYLE_ZH = (
    "【游戏素材约束】源纪元·岸线基地：近未来、偏冷色、低饱和科幻。"
    "正交俯视（top-down），单一纹理贴图，无缝平铺或可裁切为方形地块；"
    "边缘须能与相邻块对齐拼接；画面中无文字、无水印、无角色、无 UI。"
    "分辨率适中即可（后续在游戏内缩放至约 40px 格网）。"
)

# gpt-4o-mini 等：仅输出一段可直接给生图模型的英文 prompt
PROMPT_REFINE_SYSTEM = """You are a prompt engineer for AI image generation targeting game production (tiles / textures).
The user message contains a brief, possibly in Chinese, with art direction for "Epoch Incursion" coastal sci-fi base assets.

Write ONE compact English prompt optimized for an image model: concrete visual nouns, lighting, materials, camera (top-down orthogonal), and constraints (no text, no watermark, no characters, no UI, seamless/tileable edges where it is a ground texture).

Output ONLY the final prompt paragraph. No markdown, no quotes, no preamble."""

MAP_TILE_PRESETS: dict[str, dict[str, Any]] = {
    "void": {
        "label": "T_VOID 野地基底",
        "hint_zh": (
            "深蓝灰荒地基底，RGB 基调约 (14,22,36)；风化地表、砂砾硬土、极低对比；"
            "与可走路面区分明显；勿画粗大轮廓。"
        ),
        "default_size": DEFAULT_FAST_SIZE,
        "default_quality": DEFAULT_FAST_QUALITY,
    },
    "road": {
        "label": "T_ROAD 可走铺装路面",
        "hint_zh": (
            "冷灰硬化路面，RGB 基调约 (48,54,68)，略偏蓝；可有轻微修补痕、噪点；"
            "勿画半截建筑；图案对称或可平铺。"
        ),
        "default_size": DEFAULT_FAST_SIZE,
        "default_quality": DEFAULT_FAST_QUALITY,
    },
    "build": {
        "label": "T_BUILD 建筑占格",
        "hint_zh": (
            "更深蓝灰屋面/体量剪影，RGB 基调约 (26,32,44)，比路面更暗略冷；"
            "抽象方块屋顶或幕墙暗示即可；勿画可辨认门窗剧情细节。"
        ),
        "default_size": DEFAULT_FAST_SIZE,
        "default_quality": DEFAULT_FAST_QUALITY,
    },
}

MAP_TILE_PRESET_ORDER: tuple[str, ...] = ("void", "road", "build")

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

DATA_URI_RE = re.compile(r"data:image/([^;]+);base64,([A-Za-z0-9+/=\s]+)", re.IGNORECASE)


def pick_facility_image_size(logical_w: int, logical_h: int) -> str:
    _ = logical_w, logical_h
    return DEFAULT_FAST_SIZE


def build_facility_prompt(facility_id: str, scale: int, extra_user: str) -> tuple[str, str]:
    fid = facility_id.strip().lower()
    if fid not in FACILITY_CORE:
        known = ", ".join(sorted(FACILITY_CORE.keys()))
        raise ValueError(f"未知 facility-id：{facility_id!r}。可选：{known}")
    name, w, h = FACILITY_CORE[fid]
    lw, lh = w * scale, h * scale
    size = pick_facility_image_size(lw, lh)
    core = (
        f"【设施占位贴图】id={fid}（{name}）。逻辑占地约 {w}×{h}px（当前 scale={scale} → 目标约 {lw}×{lh}）。"
        f"俯视屋顶/体量块，冷灰科幻，低饱和；无文字无角色。"
        f"生成图长宽比请接近 {lw}:{lh}，后续人工可对齐 game core 矩形。"
    )
    parts = [p for p in (extra_user.strip(), GAME_ART_STYLE_ZH, core) if p]
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
    openai_chat_model = (
        os.getenv("OPENAI_CHAT_MODEL", "").strip()
        or os.getenv("OPENAI_MODEL", "").strip()
        or "gpt-4o"
    )
    openai_image_model = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2").strip() or "gpt-image-2"

    prompt_refine_base = os.getenv("OPENAI_PROMPT_LLM_BASE_URL", "").strip().rstrip("/") or openai_base
    prompt_refine_model = os.getenv("IMAGE_PROMPT_LLM_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"
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
        except (RuntimeError, urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
            msg = str(e).lower()
            retryable = isinstance(e, urllib.error.URLError) or isinstance(e, TimeoutError)
            if isinstance(e, RuntimeError):
                retryable = any(x in msg for x in ("502", "503", "504", "timeout", "timed out"))
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


def build_gemini_request_body(prompt: str, size: str, merge_extra: dict[str, Any]) -> dict[str, Any]:
    aspect = size_to_gemini_aspect_ratio(size)
    gen_cfg: dict[str, Any] = {"responseModalities": ["IMAGE"]}
    if os.getenv("GEMINI_USE_ASPECT_RATIO", "1").strip().lower() not in {"0", "false", "no", ""}:
        gen_cfg["imageConfig"] = {"aspectRatio": aspect}
    body: dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
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

    if dry_run:
        tag = f" [{batch_label}]" if batch_label else ""
        print(f"[DRY_RUN]{tag} backend={backend}")
        print(f"draft brief:\n{full_prompt[:1600]}" + ("…" if len(full_prompt) > 1600 else ""))
        if image_prompt != full_prompt:
            print(f"\nrefined image prompt:\n{image_prompt[:1600]}" + ("…" if len(image_prompt) > 1600 else ""))
        return 0

    size = (args.size or suggested_size or DEFAULT_FAST_SIZE).strip()
    quality = (args.quality or os.getenv("OPENAI_IMAGE_QUALITY") or default_quality_from_preset or "").strip()

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
            print(f"{tag}POST {url.split('?')[0]} …\nmodel={model_id!r} aspect≈{size_to_gemini_aspect_ratio(size)!r} n={args.n}", flush=True)
            for _ in range(args.n):
                body = build_gemini_request_body(image_prompt, size, merge_extra)
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
            print(f"{tag}POST {endpoint}\nmodel={model!r} n={args.n}", flush=True)
            for _ in range(args.n):
                body_chat: dict[str, Any] = {
                    "model": model,
                    "messages": [{"role": "user", "content": image_prompt}],
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
            if args.prefer_b64:
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

    saved_paths: list[str] = []
    for i, (raw_img, mime) in enumerate(all_saved):
        ext = _mime_to_ext(mime) if mime != "image/unknown" else _guess_ext_from_content(raw_img)
        if args.out and len(all_saved) == 1 and i == 0:
            dest = Path(args.out)
        elif args.out:
            p = Path(args.out)
            dest = p.with_stem(f"{p.stem}_{i + 1}")
        else:
            dest = out_dir / f"{stem}_{ts}_{i + 1}{ext}"
        if not dest.suffix:
            dest = dest.with_suffix(_guess_ext_from_content(raw_img))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw_img)
        saved_paths.append(str(dest.resolve()))

    if not saved_paths:
        print("未保存任何文件。")
        return 4

    for pth in saved_paths:
        print(f"已保存：{Path(pth).resolve()}")

    return 0


def main() -> int:
    preset_choices = sorted(MAP_TILE_PRESETS.keys()) + ["facility"]
    parser = argparse.ArgumentParser(description="游戏美术生图：Gemini generateContent / OpenAI chat / OpenAI images")
    parser.add_argument("prompt", nargs="?", default="", help="画面描述（可与 --preset 合并）")
    parser.add_argument(
        "--backend",
        "-b",
        default="",
        choices=["", "gemini", "openai-chat", "openai-images"],
        help="覆盖 IMAGE_GEN_BACKEND（默认 gemini）",
    )
    parser.add_argument(
        "--preset",
        "-p",
        default="",
        choices=["", *preset_choices],
        help="void / road / build / facility",
    )
    parser.add_argument("--facility-id", default="", help="--preset facility 时必填")
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
        help="一键依次生成 void / road / build 三种地砖贴图（对齐 map_tile_art_brief）；勿与 --preset/-o 同用",
    )
    _add_prefer_b64_args(parser)
    args = parser.parse_args()

    user_prompt = (args.prompt or "").strip()
    preset = (args.preset or "").strip().lower()
    facility_id = (args.facility_id or "").strip().lower()

    if args.all_map_tiles:
        if preset or facility_id:
            print("错误：--all-map-tiles 不能与 --preset / --facility-id 同时使用。")
            return 1
        if args.out:
            print("错误：--all-map-tiles 不要使用 -o（输出文件名为 tile_<void|road|build>_时间戳）。")
            return 1

    if preset == "facility" and not facility_id:
        print("使用 --preset facility 时必须提供 --facility-id。")
        return 1

    if not args.all_map_tiles:
        if preset not in MAP_TILE_PRESETS and preset != "facility" and not user_prompt:
            print("请输入描述（单行），或使用 --preset / --all-map-tiles：")
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

    if args.all_map_tiles:
        out_hint = default_out_dir_for_preset("void", "")
        print(f"[batch] 一键地砖：{', '.join(MAP_TILE_PRESET_ORDER)} → {out_hint}", flush=True)
        worst = 0
        for tp in MAP_TILE_PRESET_ORDER:
            label = MAP_TILE_PRESETS[tp]["label"]
            print(f"\n{'=' * 60}\n[batch] {tp} — {label}\n{'=' * 60}", flush=True)
            rc = generate_once(
                cfg,
                backend,
                args,
                preset=tp,
                facility_id="",
                user_prompt=user_prompt,
                merge_extra=merge_extra,
                post_timeout=post_timeout,
                download_timeout=download_timeout,
                dry_run=dry,
                filename_stem=f"tile_{tp}",
                batch_label=tp,
            )
            worst = max(worst, rc)
            if rc != 0:
                print(f"[batch] {tp} 未成功（exit {rc}），继续下一种…", file=sys.stderr)
        return worst

    return generate_once(
        cfg,
        backend,
        args,
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
