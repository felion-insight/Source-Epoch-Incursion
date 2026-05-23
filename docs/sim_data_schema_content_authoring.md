# 数据字段扩展与内容填表指南

**版本**：1.1  
**关联游戏**：源纪元 · 岸线侵入  
**最后更新**：2026-05-17  

---

## 1. 目的

在不推翻 [management_sim_design.md](./management_sim_design.md) 的前提下，为 **静默期的可玩深度**增补最小数据结构，并与 **[sim_facility_tech_and_resource_gameplay.md](./sim_facility_tech_and_resource_gameplay.md)** 中的设施 DAG、区域主动玩法表对齐；策划用**可加列的表格**维护与 Sandbox 相容的内容。

---

## 2. 建议新增 / 收紧的存档字段

### 2.1 资源与日耗

| 字段 | 类型 | 说明 |
|------|------|------|
| `resources.energy/med/food/intel` | `number` | 沿用 |
| `daily_upkeep_rates` | `Record<ResourceId, number>` | 静默期每游戏日基准消耗 |
| `morale` | `number` | 可选：士气独立轴，或与食物/事件挂钩 |

### 2.2 设施（在五设施之外增加运行时状态）

对每个 `facility_id`：

| 字段 | 类型 | 说明 |
|------|------|------|
| `tier` | `int` | 等级 |
| `branch_choice` | `string \| null` | 分叉选择 |
| `condition` | `0..100` | 耐久/工况；低阈值触发故障事件 |
| `efficiency_mult` | `float` | 临时修正 |
| `tech_frontier_hint` | `string[]` | **可选**：已可见但未立项的 `tech_id`（缓存用；可不存盘而由 DAG+tag 推导） |

与设施 DAG 的策划表对齐见 **[sim_facility_tech_and_resource_gameplay.md](./sim_facility_tech_and_resource_gameplay.md)** 与本文件上文「§6 · 模板 D」。

### 2.3 委派 / 远征队列

| 字段 | 类型 | 说明 |
|------|------|------|
| `expeditions[]` | 列表 | `{ id, leader_npc, destination_region, depart_day, arrival_day, status, payout_ref }` |
| `dispatched_staff` | `Set<npc_id>` | UI 占用：哪些人外出不可对话 |

---

## 3. 策划表模板 A：`StoryBeat ↔ Sandbox 楔子`

每张幕 / 每张表可复制一行：

| act | chapter | after_beat_id | sandbox_min_days | sandbox_exit_modes | soft_goal_ids | notes |
|-----|---------|---------------|------------------|---------------------|---------------|-------|
| 1 | CH1 | BEAT_PG_009 | 2 | TIME_MIN_ELAPSED,PLAYER_REQUEST_BRIEFING | GATHER_MED,GIFT_REPAIR_KIT | |

`soft_goal_ids`：非强制，仅占 UI 「建议事项」列表。

---

## 4. 策划表模板 B：经营决策行扩展

在现有「经营决策与剧情映射表」每行末尾追加：

| sandbox_policy | story_tags | delivery | queue_target_beat |

说明：

| 列 | 可选值 |
|----|--------|
| `sandbox_policy` | `allow` / `block_ui` / `queue` |
| `story_tags` | 逗号分隔，枚举见 [sim_event_pipeline_taxonomy.md](./sim_event_pipeline_taxonomy.md) |
| `delivery` | `immediate` / `queued` |
| `queue_target_beat` | beat_id 或 `NEXT` |

---

## 5. 策划表模板 C：静默期探索目标（与地图对齐）

| region_id（见 map_design） | lock_type | sandbox_eligible | soft_goal copy | payout_bundle_id |
|-----------------------------|-----------|------------------|----------------|------------------|

---

## 6. 策划表模板 D：设施科技节点（DAG 行）

与 [sim_facility_tech_and_resource_gameplay.md](./sim_facility_tech_and_resource_gameplay.md) §3.2 一一对应；每行一叶或中间节点均可。

| tech_id | facility_id | label_zh | parent_tech_ids（逗号） | unlocks_management_tag \| NULL | mutually_exclusive_group \| NULL | sandbox_policy_override \| NULL |

---

## 7. 策划表模板 E：区域资源主动玩法

| activity_id | region_id | primary_resource | run_kind_zh | cooldown_world_days | payout_bundle_id | incursion_notes | sandbox_eligible |

说明：`payout_bundle_id` 需在事件管线文档中对应 `EXPLORE_LOOT_NONLEDGER` 或等价非账本包；硬核真相不得从此表直送。

---

## 8. AI 碎碎念挂载点（可选）

为每条经营决策可加：

| npc_hint_weights | cooldown_group |

详见 [sim_ai_interaction_budgets_sandbox.md](./sim_ai_interaction_budgets_sandbox.md)。

---

## 9. JSON 补丁示例（草稿，非最终实现）

以下为 `world.json` 风格补丁示意，字段名可被程序映射改名：

```json
{
  "story_phase": "Sandbox",
  "current_beat_id": "ACT1_CH2_POST_INTRUSION",
  "economy": {
    "daily_upkeep": {"food": 3, "energy": 5},
    "facilities": {
      "comms_array": {"tier": 1, "condition": 78, "branch_choice": null}
    },
    "expeditions": [
      {"id": "exp_014", "leader": "chubby", "region": "abandoned_mine_surface", "depart_day": 12, "arrival_day": 14, "status": "traveling"}
    ]
  }
}
```
