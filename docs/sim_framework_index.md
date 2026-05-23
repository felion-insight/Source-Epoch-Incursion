# 模拟经营 / 静默运营期 — 文档索引

**关联游戏**：源纪元 · 岸线侵入  
**目的**：在主线节拍之间插入**可玩的经营与探索留白**，并让实现与文案有统一的契约可参考。  
**最后更新**：2026-05-17

---

## 阅读顺序（建议）

| 顺序 | 文档 | 适合读者 |
|------|------|----------|
| 1 | [sim_narrative_gate_and_sim_layers.md](./sim_narrative_gate_and_sim_layers.md) | 全体：闸门、三套时钟、分层架构 |
| 2 | [sim_phase_machine_save_contract.md](./sim_phase_machine_save_contract.md) | 程序 / 系统设计：相位与存档契约 |
| 3 | [sim_event_pipeline_taxonomy.md](./sim_event_pipeline_taxonomy.md) | 程序 / 叙事策划：事件管道与分级 |
| 4 | [sim_economy_world_tick_exploration_bridge.md](./sim_economy_world_tick_exploration_bridge.md) | 系统 / 关卡：经济与探索、岸线、昼夜 |
| 5 | [sim_facility_tech_and_resource_gameplay.md](./sim_facility_tech_and_resource_gameplay.md) | 策划 / 程序：设施升级树与各资源地图主动玩法规格 |
| 6 | [sim_data_schema_content_authoring.md](./sim_data_schema_content_authoring.md) | 策划填表：数据扩展与表格模板 |
| 7 | [sim_ai_interaction_budgets_sandbox.md](./sim_ai_interaction_budgets_sandbox.md) | 叙事 / AI：`narrative_ai` 侧的预算与限制 |
| 8 | [sim_implementation_milestones.md](./sim_implementation_milestones.md) | 制作人 / 程序：里程碑与验收 |

---

## 与存量设计文档的关系

| 存量文档 | 关系 |
|----------|------|
| [management_sim_design.md](./management_sim_design.md) | 资源四类、设施五类、岸线侵入等**内容真相源**；本框架规定**何时允许这些决策撬动主线**；§3 与 [sim_facility_tech_and_resource_gameplay.md](./sim_facility_tech_and_resource_gameplay.md) 的树状展示规格对齐 |
| [sim_facility_tech_and_resource_gameplay.md](./sim_facility_tech_and_resource_gameplay.md) | **设施 DAG / 分支表**与各资源**地图主动玩法**的契约；不替代 management 表中 tag 语义 |
| [narrative_structure_blueprint_2026-05-08.md](./narrative_structure_blueprint_2026-05-08.md) | 幕 / 章节 / 强制事件序列 → 在每个序列之间配置 **Sandbox 楔子** |
| [map_design.md](./map_design.md) | 区域锁 → **静默期主攻目标清单**（资源锁、能力锁、时间锁） |
| [gdd_master_outline.md](./gdd_master_outline.md) | 类型与叙事占比的总体目标 |
| [critical_dialogue_nodes_blueprint.md](./critical_dialogue_nodes_blueprint.md) | 关键对话节点应尽量落在 **`StoryBeat` 相位** |
| [player_variables_endings_matrix.md](./player_variables_endings_matrix.md) | 结局变量；本框架的事件管道需写明**是否会写隐藏变量** |
| [NPC_movement.md](./NPC_movement.md) | NPC 在空间中的行为规则；委派 / 远征 UI 可参考 |

---

## 仓库内对接代码（占位引用）

以下内容以仓库当前结构为准，实现时请以实际模块名为准：

- `game/`：剧情节点、存档、可能与经营 tick 同框的逻辑（见项目根目录 `PROJECT_DOCUMENTATION.md`）
- `narrative_ai/management.py`：经营决策与 AI 反应规范
- `narrative_ai/data/world.json`、玩家变量等：世界状态与结局相关变量

详细对接任务见 [sim_implementation_milestones.md](./sim_implementation_milestones.md)。
