# 设施升级树与各资源「区域主动玩法」规格

**版本**：1.0  
**关联游戏**：源纪元 · 岸线侵入  
**最后更新**：2026-05-17  

---

## 1. 文档目的

在既不推翻「轻量化、叙事驱动」总原则的前提下，补足两类可玩纵深：

1. **设施定向升级树（Tech Tree‑lite）**：多设施各自拥有可见的**前置关系**与**互斥分支**，策划可填表维护；账本表现仍对齐现有经营 tag 管线。  
2. **四类核心资源各自的「去往特定区域的主动玩法」**：玩家在地图上**亲力亲为**的操作循环（短时、可重复、有冷却或与基地日挂钩），作为主要资源入口之一；与静默 tick、决算、远征并存而非替代叙事。

关联索引见 [sim_framework_index.md](./sim_framework_index.md)。实现验收见本节末与 [sim_implementation_milestones.md](./sim_implementation_milestones.md) **M6 / M7**。

---

## 2. 与现有系统的关系（契约）

| 现有模块 | 本规格如何挂载 |
|----------|----------------|
| `FACILITY_MANAGEMENT_TAGS`（`game/narrative_map.py`） | 树节点 **`unlocks_management_tag`** 或 **`requires_applied_tags`** 与表中 `tag` 一一对应；UI 展示的「层级」不改变 tag 语义。 |
| `POST /api/management` + `narrative_ai.management` | 玩家点选「树叶」等价于勾选对应决策：**仍经由 management 决算**（静默期可走队列，见闸门文档）。 |
| `applied_management_tags` | 已生效 tag 列表即**已点亮节点集合**；树布局仅用于可视化与门禁计算。 |
| 叙事闸门 (`narrative_gate_management_decision_zh` 等） | **优先于**树木可见性：`blocked` 的节点不展示或可展示为锁定态并附 `reason_zh`。 |
| `explorer_access` / 区域锁 | 「区域主动玩法」绑定的 **`region_id`** 与 [map_design.md](./map_design.md) 表格一致；未解锁区域玩法入口隐藏或灰显。 |
| 远征 (`game/expeditions.py`) | 远征偏 **委托 + 延迟结算**；本规格「主动玩法」偏 **就地操作 + 即时/短周期反馈**。二者可共用同一门禁；命名上区分开。 |

---

## 3. 设施升级树（Tech Tree‑lite）

### 3.1 设计原则

- **树是 DAG（有向无环图）**：允许合并前置，不允许环；分支可互斥（`group_exclusivity`）。  
- **深度可控**：单层设施建议 **≤4 可见深度**，避免演变成传统 4X 科技树复杂度。  
- **叙事仍为收益主因**：节点的「解锁对话 / 解锁结局条件 / 改变世界状态」优先级高于数值 buff。  
- **与旧版措辞对齐**：[`management_sim_design.md`](./management_sim_design.md) 原为「线性或少分支」；本规格定义为**可策划填表的分支可视化**，不改变「不搞生存数值地狱」的初衷。

### 3.2 节点数据字段（策划表 → JSON）

每条树节点最少包含：

| 字段 | 类型 | 说明 |
|------|------|------|
| `tech_id` | `string` | 唯一键（如 `comm_encrypt_v1`） |
| `facility_id` | `string` | 与地图设施 id 对齐（如 `comm`、`mine`、`lab`） |
| `label_zh` | `string` | UI 标题 |
| `body_zh` | `string` | 可选：风险提示 / 叙事摘要 |
| `parent_tech_ids` | `string[]` | 前置节点；空表示树根 |
| `unlocks_management_tag` | `string \| null` | 与现有 `FACILITY_MANAGEMENT_TAGS.tag` 一致；叶子通常必填 |
| `cost_preview` | `object` | 与 `management_turn` / 预览 Payload 对齐的静态摘要（能耗、补给等） |
| `mutually_exclusive_group` | `string \| null` | 同组至多生效一个 **`unlocks_management_tag`**（已实现后锁定同组其它） |
| `sandbox_policy_override` | `enum \| null` | 可选：覆盖单行 `sandbox_policy`；缺省则用 management 注册表全局策略 |
| `map_highlight` | `boolean` | 是否在大地图设施上显示「可研发」角标 |

**树根**可由程序合成：对每个 `facility_id` 自动生成虚拟根 `facility_{id}_root`（不占 tag），仅需 `tutorial_copy_zh` 文案。

### 3.3 UI 行为建议

- **StoryBeat**：仅高亮当前剧情允许立项的枝叶；闸门原因走现有中文 `reason_zh`。  
- **Sandbox**：展示整棵已解锁前缀子图；被 `sandbox_policy=block_ui` 的节点显示锁图标。  
- **决算页**：可同时提供「扁平 tag 列表」（旧习惯）与「树状视图」（新习惯）切换，避免强迫老玩家重新学习路径。

---

## 4. 四类资源 × 地图区域 × 主动玩法

### 4.1 总原则

- 每种 **`energy` / `food` / `medical` / `intel`** 至少绑定 **一类**主推**区域玩法**（可随幕次解锁更多变种）。  
- 玩法应为 **可数步完成**的操作（走位、时点、简短 QTE、分拣、频段对齐等——具体形态由关卡/前端迭代），服务端只校验：**区域、相位、冷却、门禁、奖励包 ID**。  
- 奖励默认为 **`EXPLORE_LOOT_NONLEDGER`** 量级（见 [sim_economy_world_tick_exploration_bridge.md](./sim_economy_world_tick_exploration_bridge.md) §3）；不得静默直送硬核主线真相。

### 4.2 映射表（v1 草案，可调数值）

以下为**与设计意图对齐的默认挂载**；`region_id` 须与 [`map_design.md`](./map_design.md) 及 `explorer_access` 中的 zone slug 对齐（若代码使用 snake_case，表里统一即）。

| 资源 | 主推 `region_id`（示例） | 玩法关键词（占位） | 典型风险 / 克制 |
|------|--------------------------|---------------------|----------------|
| **能源** `energy` | 源矿 `mine`，进阶：废弃矿场深层 `mine_deep` | **开采节奏 / Overload 取舍**：高产出拉高岸线增速 | 与 `mine_deepen`、`mine_limit` 标签数值联动 |
| **补给** `food` | 海岸防线–后勤动线（可用 `defense` 接单或增设 `shore_cave`） | **巡逻收集 / 潮汐窗口跑腿**（与时间锁对齐） | 失败仅损失时间与小幅士气，不降主线不可逆旗标 |
| **医疗** `medical` | 医疗实验室 `lab`（野外：废墟急救点可后置） | **分拣伤员 / 配给校准**短时交互 | 产出上限低，防止刷穿医疗困局叙事 |
| **情报** `intel` | 通讯阵列 `comm`；进阶：回声塔 `echo_beacon`、`listen` | **信道解谜 / 片段重组**（多步非 AI 调用） | 与 `comm_array_encrypt` 等标签叠乘时减量避免通胀 |

远征（`game/expeditions.py`）可视为 **intel/energy** 的补充委托渠道，地图上仍保留「本地操作」以降低纯菜单感。

### 4.3 服务端动作原型（不改变现有路由命名亦可）

建议使用统一前缀，便于网关与 Telemetry：

| 动作 | 说明 |
|------|------|
| `POST /api/explore/resource_run`（拟议） | body：`region_id`、`run_kind`、`client_ticks`（可选）。返回：`payout`、`cooldown_until_day`。 |
| 若不愿增路由 | 可暂挂 `POST /api/narrative/action` 的 **`kind`** 枚举扩充（须在 [sim_event_pipeline_taxonomy.md](./sim_event_pipeline_taxonomy.md) 登记 StoryTag）。 |

### 4.4 冷却与岸线

- 每类玩法独立 **`cooldown_world_days`** 或 **`per_sandbox_generation_cap`**，防止沙盘磨穿。  
- 能源类高收入尝试须带 **`INCURSION` 瞬时或累计修正**声明（与岸线文档一致）。

---

## 5. 内容 authoring 落点

- 设施树：**模板 D** 见更新后的 [sim_data_schema_content_authoring.md](./sim_data_schema_content_authoring.md)。  
- 区域玩法：**模板 E** 同上。  

---

## 6. 非目标（本轮明确不做）

- 完整「无上限」科研树或跨设施超级树（保持 **按设施多张 DAG**）。  
- 完全不经过闸门的账本写入。  
- 用区域玩法**替代**关键剧情必选演出。

---

## 7. 版本历史

| 日期 | 版本 | 摘要 |
|------|------|------|
| 2026-05-17 | 1.0 | 初稿：设施 DAG + 四资源区域主动玩法 + 契约表 |
