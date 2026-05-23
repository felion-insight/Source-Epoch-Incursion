# 源纪元 · 岸线侵入 — 项目文档

**版本**：1.2  
**创建日期**：2026-05-10  
**最近更新**：2026-05-17  
**关联游戏**：AI驱动叙事RPG + 轻模拟经营

---

## 一、项目概述

### 1.1 项目简介

**源纪元·岸线侵入**是一款AI驱动的叙事类游戏，核心玩法为**对话RPG + 轻模拟经营**。游戏采用多层次阴谋结构，从自然灾难表象逐步揭示宇宙级真相。玩家扮演一名被召回边境基地的代理指挥官，在与AI驱动的NPC深度互动中，逐步发现隐藏在世界危机背后的惊人秘密。

### 1.2 核心特色

- **AI驱动的NPC**：每个核心角色拥有独立记忆、人设和隐藏动机，行为与对话动态生成
- **选择影响一切**：玩家的每个选择（对话或经营）都会影响剧情走向、NPC关系及最终结局
- **多层次阴谋揭示**：从表层灾难到宇宙级真相，8个不同结局
- **记忆回溯机制**：NPC会主动引用过往交互，每次对话至少包含一次对历史记录的引用
- **源的独特交互**：完全由AI实时生成，无预设选项，玩家可自由提问

### 1.3 剧情占比

| 模块 | 占比 |
|------|------|
| 剧情对话 | ~70% |
| 模拟经营 | ~30% |

---

## 二、技术架构

### 2.1 项目结构

自顶向下分层：**设计文档 → AI 叙事引擎 → 会话与关卡逻辑 → 静态 Web 前端**。

```
d:/SGC/Source Epoch Incursion/
├── index.html                     # 入口：跳转至 web/explorer/
├── PROJECT_DOCUMENTATION.md       # 本仓库总览与配置说明
├── save/                          # 运行时存档目录（默认 session.json，可用 GAME_SAVE_PATH 覆盖）
│
├── docs/                          # 游戏设计文档（Markdown）
│   ├── gdd_master_outline.md
│   ├── conspiracy_lore_codex.md
│   ├── npc_bible_ai_characters.md
│   ├── management_sim_design.md
│   ├── narrative_structure_blueprint_2026-05-08.md
│   ├── critical_dialogue_nodes_blueprint.md
│   ├── player_variables_endings_matrix.md
│   ├── map_design.md
│   ├── map_tile_art_brief.md
│   ├── NPC_movement.md
│   ├── sim_framework_index.md                       # 静默运营框架总索引（从此进入）
│   ├── sim_narrative_gate_and_sim_layers.md         # 叙事闸门与分层
│   ├── sim_phase_machine_save_contract.md           # 相位状态机与存档契约
│   ├── sim_event_pipeline_taxonomy.md               # 事件管线与叙事分级
│   ├── sim_economy_world_tick_exploration_bridge.md # Tick、岸线、地图桥接
│   ├── sim_facility_tech_and_resource_gameplay.md   # 设施升级树与各资源地图主动玩法
│   ├── sim_data_schema_content_authoring.md         # 数据扩展与策划填表
│   ├── sim_ai_interaction_budgets_sandbox.md        # Sandbox AI 预算与语义限制
│   └── sim_implementation_milestones.md             # 实现里程碑与验收
│
├── narrative_ai/                  # AI 叙事引擎（OpenAI 兼容 API、记忆、Prompt）
│   ├── __main__.py                # CLI：python -m narrative_ai [npc|source|mgmt|beat]
│   ├── user_settings.example.py   # 复制为 user_settings.py（已在 .gitignore）
│   └── data/                      # NPC / 变量 / 世界 JSON
│       ├── npcs.json
│       ├── player_variables.json
│       └── world.json
│
├── game/                          # 剧情图、存档、经营、探索/沙盒、HTTP API（python -m game）
│   ├── __main__.py                # 入口：默认 127.0.0.1:8787；可选子命令 serve
│   ├── web_api.py                 # ThreadingHTTPServer + JSON 路由（大地图 / 经营 / 沙盒）
│   ├── session.py                 # GameSession：剧情状态、资源、记忆指针等
│   ├── default_session.py         # 默认会话单例与并发锁
│   ├── story_graph.py             # story_nodes.json 图遍历与节点逻辑
│   ├── bridge.py                  # narrative_ai 与会话桥接（NPC/源/经营 beat）
│   ├── narrative_map.py           # 设施经营标签、叙事闸门与地图相关选项
│   ├── narrative_progress.py      # 叙事进度辅助
│   ├── hidden_state.py            # 隐藏变量/状态
│   ├── endings.py                 # 结局判定相关
│   ├── management_turn.py         # 经营回合序列化/预览载荷
│   ├── overworld_npcs.py          # 大地图 NPC 行数据与开局上下文
│   ├── explorer_access.py         # 探索区域可达性
│   ├── explorer_objectives.py     # 大地图目标与沙盒目标条
│   ├── expeditions.py             # 远征目录与进行中 UI 载荷
│   ├── sim_sandbox.py             # 沙盒世界日、公告栏、退出条件等
│   ├── sandbox_node_hooks.py      # 叙事节点与沙盒钩子
│   └── data/story_nodes.json
│
└── web/                           # 仅静态资源：大地图 explorer
    └── explorer/
        ├── index.html
        ├── main.js
        └── styles.css
```

`narrative_ai/` 下尚有 `openai_client.py`、`prompt_blocks.py`、`prompts.py`、`schemas.py`、`validators.py` 等；未在上表中逐一枚举的模块可按文件名理解职责。

（若你本地另有 Word 原版设计稿，可自行建 `archive/` 或任意目录保管，不必提交进本仓库。）

### 2.2 核心模块说明

| 模块 | 路径 | 功能说明 |
|------|------|----------|
| **配置管理** | `narrative_ai/config.py` | `NARRATIVE_AI_*` 环境变量与可选 `user_settings.py`（API 地址、模型、密钥等） |
| **NPC代理** | `narrative_ai/npc_agent.py` | 为每个NPC生成动态对话，支持多种模式 |
| **源代理** | `narrative_ai/source_agent.py` | 处理玩家与"源"的特殊交互（低语系统） |
| **记忆系统** | `narrative_ai/memory.py` | 管理NPC的长期/短期记忆和情感状态 |
| **叙事生成** | `narrative_ai/generator.py` | 高级叙事生成接口 |
| **经营系统** | `narrative_ai/management.py` | 经营决策注册与反应规范 |
| **数据加载** | `narrative_ai/loader.py` | 加载NPC、变量、世界设定JSON |
| **游戏 HTTP API** | `game/web_api.py` | 供 `web/explorer` 使用的 JSON API；与会话、沙盒、远征等对接 |

### 2.3 API调用流程

```
用户输入
    ↓
游戏逻辑层（选择对话模式）
    ↓
NpcAgent.generate() / SourceAgent.whisper()
    ↓
Prompt构建（包含：角色设定 + 记忆 + 世界状态）
    ↓
OpenAI兼容API调用 (POST /v1/chat/completions)
    ↓
AI生成回复
    ↓
验证与后处理（记忆回溯检查）
    ↓
返回给用户 + 更新记忆存储
```

---

## 三、世界观与设定

### 3.1 时代背景

**公元2125年，源纪元**

人类在海底发现可自我增殖的能源物质"源"，实现科技爆发。然而，源在深海疯狂增殖并向大陆蔓延，称为"岸线侵入"。人类在全球建立基地，组成最高组织"曙光议会"抗击侵入。

**玩家角色**：前源矿工程师，因一次事故失去队友，被紧急召回担任边境基地代理指挥官。实际身份：早期成功同调者，记忆被清洗。

### 3.2 四层阴谋结构

| 层次 | 揭示时机 | 核心真相 |
|------|----------|----------|
| **第一层** | 游戏中期 | 源是有意识的共生体；曙光议会故意加速岸线侵入以筛选"可同调者"，创造新人类 |
| **第二层** | 游戏后期 | 源是上个宇宙轮回中先驱文明的全部记忆与情感凝聚体；岸线侵入是信息过载的副作用 |
| **第三层** | 结局前置/隐藏 | 源纪元实际已持续230年，人类记忆被多次重置；玩家是唯一的"双向同调者" |
| **第四层** | 中后期介入 | 净空会（摧毁源）、回声集团（强制统一意识）、议会内部分裂 |

### 3.3 三大势力

| 势力 | 代号 | 目标 |
|------|------|------|
| **曙光议会** | Dawn Council | 推动筛选与同调实验，立场内部分裂 |
| **净空会** | Purge Union | 摧毁源，不惜生态代价 |
| **回声集团** | Echo Collective | 强制集体意识统一，视玩家为关键容器 |

---

## 四、NPC系统

### 4.1 核心NPC列表

| ID | 名称 | 表面身份 | 隐藏身份 | 核心秘密 |
|----|------|----------|----------|----------|
| `karen` | 卡伦 | 安全官 | 议会监督员"灰镜" | 监控玩家，可执行清理 |
| `dr_lin` | 林博士 | 首席科学家 | 前筛选计划参与者 | 知道玩家是同调者 |
| `chubby` | 小胖 | 工程师 | 弟弟被关押 | 偷能源维持弟弟生命 |
| `klein` | 克莱因 | 被囚老人 | 议会创始人 | 时间重置、宇宙轮回真相 |
| `echo_7` | 回声-7 | 通讯AI | 回声集团联络AI | 集体意识方案 |
| `jin` | 堇 | 生态研究员 | 净空会特工 | 引爆方案、议会证据 |
| `elizabeth` | 伊丽莎白·莫罗 | 议会主席 | 筛选计划推动者 | 远程通信出现 |
| `source` | 源 | 意识体 | 先驱文明记忆 | 特殊交互系统 |

### 4.2 NPC记忆结构

每个NPC拥有四层记忆系统：

- **长期记忆**：固定的世界观、背景、核心信念（不可变）
- **短期记忆**：最近3-5次与玩家的交互记录
- **情感记忆**：信任值、好感度、恐惧值等数值
- **动态记忆**：玩家造成的变化（如"曾被玩家救助"）

### 4.3 信任值与语言风格

| 信任区间 | 语言风格变化 |
|----------|--------------|
| > 70 | 亲切词、昵称、详细解释 |
| 30-70 | 标准风格 |
| < 30 | 回避、短促、隐藏信息 |

---

## 五、玩家变量系统

### 5.1 核心隐藏变量

| 变量 | 缩写 | 范围 | 说明 |
|------|------|------|------|
| 同调值 | SYNC | 0-100 | 与源的神经连接程度 |
| 人性值 | HUMAN | 0-100 | 对个体生命、自由的珍视程度 |
| 议会信任值 | COUNCIL | 0-100 | 曙光议会对玩家的信任度 |
| 净空会好感度 | PURIFY | 0-100 | 净空会对玩家的好感度 |
| 回声集团渗透度 | ECHO | 0-100 | 回声集团对基地的渗透程度 |
| 岸线侵入进度 | INCURSION | 0-100 | 地图被吞噬的百分比 |
| 记忆重置次数 | RESET | 0/1/2+ | 二周目特殊变量 |
| 源的理解度 | INSIGHT | 0-100 | 隐藏结局判定 |

### 5.2 结局触发条件

游戏共有8个结局，由玩家变量组合决定：

| 编号 | 结局 | 条件概要 |
|------|------|----------|
| 1 | 遗忘之约 | 摧毁源，INCURSION > 60 或 HUMAN < 30 |
| 2 | 新伊甸 | 与源共生，SYNC > 60 且 HUMAN > 50 |
| 3 | 神性监狱 | 成为服务器，SYNC > 80 且 COUNCIL > 60 |
| 4 | 统一寂静 | 支持回声集团，ECHO > 70 且 HUMAN < 40 |
| 5 | 循环继续 | 帮助议会重置，COUNCIL > 70 |
| 6 | 净空 | 引爆源矿，PURIFY > 60 且 INCURSION > 50 |
| 7 | 先驱之路 | 融入源，SYNC > 90 且 INSIGHT > 80 |
| 8 | 真正的救赎 | 源自我终结，INSIGHT > 80 且 HUMAN > 70（隐藏） |

---

## 六、对话系统

### 6.1 生成模式（NpcAgent）

| 模式 | 说明 | 用途 |
|------|------|------|
| `scene_line` | 生成NPC对白 | 场景对话 |
| `branch_options` | 生成2-4个选项 | 分支选择 |
| `custom_reply` | 回答自由文本 | 自定义提问 |
| `management_comment` | 经营决策反应 | 经营系统反馈 |

### 6.2 源的独特交互

**触发条件**：监听站、受损源矿机、高同调梦境

**语言规则**：
- 禁止使用第一人称"我"
- 可用"我们"、省略主语、无主语句
- 句式断裂、诗意隐喻
- 每次回答最多三句
- 温度参数：0.85（较高创造性）

---

## 七、经营系统

### 7.1 核心资源

| 资源 | 说明 | 主要消耗 |
|------|------|----------|
| 能源 | 基地运行基础 | 维持防御、升级建筑 |
| 食物 | 养活人口 | 日常消耗 |
| 医疗物资 | 治疗、稳定同调 | 治疗伤员 |
| 情报点 | 揭示真相 | 解锁真相、联络势力 |

### 7.2 核心设施

| 设施 | 功能 | 关键决策 |
|------|------|----------|
| 通讯阵列 | 交易资源、破译密文 | 加密破解/全频广播 |
| 源矿机 | 产出能源 | 加大开采/限制开采 |
| 医疗实验室 | 治疗、研发 | 神经扫描/同调抑制 |
| 防御工事 | 延缓侵入 | 升级等级 |
| 地下监听站 | 聆听源的低语 | 建造/启用/关闭 |

---

## 八、剧情结构

### 8.1 五幕结构

| 幕次 | 名称 | 时长 | 核心叙事目标 | 情感基调 |
|------|------|------|--------------|----------|
| 序章 | 重返基地 | 1-1.5h | 建立世界观、认识NPC | 压抑、迷茫 |
| 第一幕 | 宁静假象 | 4-5h | 发现异常、建立系统 | 悬疑、不确定 |
| 第二幕 | 裂痕 | 5-6h | 揭露筛选计划、势力介入 | 震惊、道德困境 |
| 第三幕 | 真相 | 4-5h | 揭示源身份、时间重置 | 绝望、哲学冲击 |
| 终幕 | 抉择 | 2-3h | 三方势力选择、结局 | 悲壮、升华 |

**总游戏时长**：约17-23小时（单周目）

### 8.2 关键节点示例

| 节点ID | 名称 | 类型 | 说明 |
|--------|------|------|------|
| PRO-01 | 抵达基地 | 强制 | 卡伦迎接，介绍现状 |
| PRO-04 | 首夜低语 | 软强制 | 梦中听到源的低语 |
| 02-05 | 卡伦的身份 | 强制 | 卡伦暴露"灰镜"身份 |
| 03-02 | 克莱因的遗言 | 强制 | 揭示时间重置真相 |
| FIN-02 | 最终选择 | 强制 | 根据变量显示可用结局 |

---

## 九、开发指南

### 9.1 环境配置

叙事 AI 配置优先读取环境变量 `NARRATIVE_AI_*`；未设置时可写入 **`narrative_ai/user_settings.py`**（从 `user_settings.example.py` 复制，默认在 `.gitignore`）。**请勿将真实 API 密钥提交到仓库。**

```bash
# 设置API地址（默认见 narrative_ai/config.py）
export NARRATIVE_AI_BASE_URL=http://35.220.164.252:3888

# 设置模型（默认）
export NARRATIVE_AI_MODEL=gpt-4o-mini

# 设置API密钥（如服务端要求；示例值请替换为你自己的密钥）
export NARRATIVE_AI_API_KEY=sk-your-key-here

# 超时设置（秒）
export NARRATIVE_AI_TIMEOUT=120

# 干跑模式（不调用API）
export NARRATIVE_AI_DRY_RUN=true

# 游戏 HTTP 服务（可选，默认 127.0.0.1:8787）
export GAME_API_HOST=127.0.0.1
export GAME_API_PORT=8787

# 存档路径（可选，默认仓库根下 save/session.json）
export GAME_SAVE_PATH=/path/to/session.json
```

在 **Windows PowerShell** 中可使用：`$env:NARRATIVE_AI_API_KEY="sk-your-key-here"` 等形式临时设置当前会话变量。

### 9.2 CLI工具使用

```bash
# NPC对话测试（带记忆）
python -m narrative_ai npc

# 源的低语测试
python -m narrative_ai source

# 经营决策反应测试
python -m narrative_ai mgmt

# 叙事节点生成测试
python -m narrative_ai beat
```

静态大地图：先在仓库根启动 `python -m game`（默认 API `http://127.0.0.1:8787`；亦可用等价命令 `python -m game serve`），再在根目录用 `python -m http.server 8080`，浏览器打开 `http://127.0.0.1:8080/web/explorer/`（或根目录 `index.html` 跳转）。

### 9.3 快速示例

```python
from narrative_ai.npc_agent import NpcAgent
from narrative_ai.memory import NpcMemoryStore, SimulationSnapshot, InteractionTurn

# 初始化记忆存储
store = NpcMemoryStore(
    npc_id="karen",
    conspiracy_tier_unlocked=1,
    long_term_notes=["玩家刚查阅过损坏的设备日志。"]
)
store.record_turn(InteractionTurn("player", "玩家坚持要把最后一份医疗包留给伤员。"))
store.emotional.trust = 62.0

# 创建NPC代理
agent = NpcAgent("karen", store)

# 生成对话
sim = SimulationSnapshot(
    resources={"medical": 4, "energy": 22},
    last_decision_tag="supply_medical_first"
)
text = agent.generate(
    mode="scene_line",
    player_context="指挥室简短汇报后，玩家看向你，等待你对资源分配的反应。",
    sim=sim,
    max_tokens=400
)
print(text)
```

---

## 十、文档索引

| 文档 | 路径 | 内容 |
|------|------|------|
| 游戏设计大纲 | `docs/gdd_master_outline.md` | 完整游戏设计，整合所有子文档 |
| 阴谋源典录 | `docs/conspiracy_lore_codex.md` | 四层阴谋设定、势力详情 |
| AI角色表 | `docs/npc_bible_ai_characters.md` | NPC详细人设、AI约束规则 |
| 经营设计 | `docs/management_sim_design.md` | 经营系统、决策映射表 |
| 设施树与地图资源玩法 | `docs/sim_facility_tech_and_resource_gameplay.md` | 设施 DAG、四类资源区域主动玩法、与 API 契约 |
| 叙事蓝图 | `docs/narrative_structure_blueprint_2026-05-08.md` | 五幕结构、章节设计 |
| 对话节点表 | `docs/critical_dialogue_nodes_blueprint.md` | 关键节点骨架 |
| 变量结局表 | `docs/player_variables_endings_matrix.md` | 变量规则、结局条件 |
| 地图设计 | `docs/map_design.md` | 大地图分区与玩法约束 |
| 大地图 NPC 移动 | `docs/NPC_movement.md` | 巡逻/移动规则说明 |
| 地块美术提要 | `docs/map_tile_art_brief.md` | 地图瓦片美术方向 |
| 静默运营框架索引 | `docs/sim_framework_index.md` | 模拟层文档入口 |
| 叙事闸门与分层 | `docs/sim_narrative_gate_and_sim_layers.md` | 叙事与模拟分层 |
| 相位机与存档契约 | `docs/sim_phase_machine_save_contract.md` | 状态机与存档约定 |
| 事件管线与分级 | `docs/sim_event_pipeline_taxonomy.md` | 事件管线、叙事分级 |
| 经济/Tick/探索桥接 | `docs/sim_economy_world_tick_exploration_bridge.md` | Tick、岸线、地图衔接 |
| 数据 schema 与填表 | `docs/sim_data_schema_content_authoring.md` | 数据扩展与策划工作流 |
| Sandbox AI 预算 | `docs/sim_ai_interaction_budgets_sandbox.md` | 沙盒 AI 调用预算与语义限制 |
| 实现里程碑 | `docs/sim_implementation_milestones.md` | 里程碑与验收 |

---

*总览文档最后更新：2026-05-17*
