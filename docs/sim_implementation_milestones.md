# 实现里程碑与验收清单

**版本**：1.1  
**关联游戏**：源纪元 · 岸线侵入  
**最后更新**：2026-05-17  

---

## 里程碑 M0 — 相位状态机雏形

**交付**：

- 全局可读写 `story_phase`、`current_beat_id`。
- 读档后能恢复相位；Sandbox 不出现新必选主线 HUD。

**验收**：

- 手动强制 `Sandbox`，连续游玩 15 分钟，无新主线必选节点挂载（除已存在的过期任务）。

---

## 里程碑 M1 — EffectBundle 过滤器

**交付**：

- 所有「会改世界 JSON / 存档」的路径通过统一管线。
- `LEDGER_MAIN` Tag 的动作在 Sandbox 或被拒或入队。

**验收**：

- QA 作弊：仅在 Sandbox 连点十次「加密模块安装」——若叙事规定应触发议会线，必须通过 `queued_effects` 在下一 Beat 才出现账本表现。

---

## 里程碑 M2 — EconomyTick 与简报

**交付**：

- 实现 [sim_economy_world_tick_exploration_bridge.md](./sim_economy_world_tick_exploration_bridge.md) 中 tick 序列的最小子集：**产出→消耗→岸线→简报**。

**验收**：

- Sandbox 过夜后资源净值变化可解释；简报能列出昨夜摘要。

---

## 里程碑 M3 — 探索与经济桥（web / game）

**交付**：

- 大地图explorer或等价模块能读取「区域解锁 + 锁类型」，Silent 仅能完成 Sandbox Eligible 的目标。
- 探索掉落走 `EXPLORE_LOOT_NONLEDGER`。

**验收**：

- [map_design.md](./map_design.md) 所列「资源锁」目标可在 Silent 内攒齐门票款项（数值另调）。

---

## 里程碑 M4 — Narrative_AI 配额

**交付**：

- [sim_ai_interaction_budgets_sandbox.md](./sim_ai_interaction_budgets_sandbox.md) 中的配额与简略过滤器。

**验收**：

- 单次经营连续触发不产生 API 爆破；过滤器日志可追溯。

---

## 里程碑 M5 — 内容迁移

**交付**：

- [management_sim_design.md](./management_sim_design.md) 第一节所有行补齐 `sandbox_policy` / `story_tags`（可先人工 CSV）。

**验收**：

- 「加大开采」「接受回声援助」等在 Silent 的规则与文档一致且无程序特例。

---

## 里程碑 M6 — 设施科技 DAG（数据 + UI）

**交付**：

- 按 [sim_facility_tech_and_resource_gameplay.md](./sim_facility_tech_and_resource_gameplay.md) §3：至少 **1** 座设施挂载可载入的 DAG（JSON / 表导出均可）。
- 大地图或决算分页可切换到「树状视图」，`unlocks_management_tag` 立项仍走 `POST /api/management`。
- 已应用的 tag 能使对应节点点亮；互斥组在第二项尝试时拒收或队列（与闸门一致）。

**验收**：

- StoryBeat / Sandbox 下锁定原因与闸门文档一致；无「静默偷跑主线账本」的路径。

---

## 里程碑 M7 — 四类资源区域主动玩法（各 1 条竖切）

**交付**：

- 每种资源至少有 **一条**可调 `activity_id`：门禁校验、`payout_bundle_id`、**冷却**，与 [sim_data_schema_content_authoring.md](./sim_data_schema_content_authoring.md) 模板 **E** 一行对齐。
- 前端：在对应 `region_id` 内需 **玩家操作**（不限初版表现力，但不得以纯菜单替代走位/时点之一）。

**验收**：

- 连续挂机刷取触发冷却；岸线修正与 [sim_economy_world_tick_exploration_bridge.md](./sim_economy_world_tick_exploration_bridge.md) §3.1 声明一致。
- 「下一幕专有真相」仍不可由此直送。

---

## 代码挂载点（以当前仓库为参考）

以下为**调查起点**，文件名以仓库实际为准：

| 预期职责 | 可能路径 |
|----------|----------|
| 剧情节点 | `game/data/story_nodes.json`、`game/__main__.py` |
| 经营与 AI | `narrative_ai/management.py` |
| 世界快照 | `narrative_ai/data/world.json` |
| CLI / beat | `narrative_ai/__main__.py`（beat 模式） |

实现完成后应在本文件勾选里程碑，或在 issue / 项目管理工具中开立对应条目。
