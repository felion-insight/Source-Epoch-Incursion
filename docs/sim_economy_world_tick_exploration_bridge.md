# 经济 tick、世界时钟与探索桥接规格

**版本**：1.1  
**关联游戏**：源纪元 · 岸线侵入  
**最后更新**：2026-05-17  

---

## 1. Tick 优先级（单次「世界步进」建议顺序）

在任一游戏日分段或固定 tick（如每实时 30 秒）内，按下列顺序结算，可避免竞态：

1. **WorldClock**：推进世界时间刻度；刷新昼夜与时间锁相关标志。
2. **EconomyTick — 前置维护**：委派「出发/到达」、故障判定种子。
3. **EconomyTick — 产出**：源矿机等基础产出。
4. **EconomyTick — 消耗**：食物、士气、运维（若已实现）、基地人口假设成本。
5. **EconomyTick — 岸线**：按 [management_sim_design.md](./management_sim_design.md) 动态压力规则滚动侵入进度（可被防御、开采策略修正）。
6. **EconomyTick — 简报生成**：写入非账本 `FLAVOR_BULLETIN` 条目队列。
7. **StoryScheduler**（仅 StoryBeat 或未处于「暂停投递」状态时）：检视待播队列；Sandbox 跳过非 flavor 投递。

Silent 期中 **1～6 不停**，**第 7 步对主线关闭**。

---

## 2. WorldClock 与地图

[map_design.md](./map_design.md) 定义的锁：**剧情锁 / 信息锁 / 能力锁 / 时间锁 / 资源锁**。  
静默期的设计意图是让玩家主要攻克 **资源锁、能力锁、时间锁**，把 **剧情锁 / 信息锁** 留给 StoryBeat。

| 锁类型 | Sandbox 用途 |
|--------|----------------|
| 时间锁 | 玩家安排睡眠/巡逻/快进（若产品有快进）以对齐开放时间窗 |
| 资源锁 | 静默期软目标：**攒门票**（例如地下监听站的能源开销） |
| 能力锁 | 静默期软目标：**购装备 / 改建**（例如探照灯） |
| 信息锁 | 通常由 Beat 给与坐标线索；Silent 只做「已知地点的跑腿」 |

---

## 3. 探索回报分层

静默期 exploration 掉落应偏好：

| 掉落类型 | 示例 | StoryTag |
|----------|------|----------|
| 资源包 | 能源/食物/医疗/情报小额 | `EXPLORE_LOOT_NONLEDGER` |
| 环境叙事碎片 | 日记残页（已脱敏或未触发账本） | `SIDE_NONLEDGER` 条件 |
| 地图 QoL | 捷径、瞭望点、低风险战斗 | `PRESSURE_WORLD` 可有可无 |
| 「下一幕专有真相」 | 议会真名首秀、新势力登场 | **不得**作为 Silent 开箱直接获得 |

若在探索中必须奖励「硬核线索」，使用 **Queued** 模式：玩家在 Silent 开箱 → 仅在下一 StoryBeat 的简报中带出。

### 3.1 四类资源的「地图主动玩法」与经济桥

在 tick 之外的**玩家即时操作回报**默认归类为 **`EXPLORE_LOOT_NONLEDGER`** 小额包（或策划登记的 `payout_bundle_id`），须满足：

- **区域门禁**已通过（与 [map_design.md](./map_design.md) 一致）；
- **冷却 / 上限**由各 `activity_id` 配置（参见 [sim_data_schema_content_authoring.md](./sim_data_schema_content_authoring.md) 模板 **E** 与总体规格 **[sim_facility_tech_and_resource_gameplay.md](./sim_facility_tech_and_resource_gameplay.md) §4**）；
- 能源类高收入须声明对 **`INCURSION`**（岸线）的瞬时或滑动修正，纳入 §1 _tick 序列中岸线步的输入。

Silent 期中 tick 的第 5 步岸线结算**不受影响**——主动玩法仅是额外注水阀；设计者应避免与 `EconomyTick` 固定产出双倍通胀。

---

## 4. 岸线侵入与静默长度的关系

岸线系统在 Silent 仍可推进，用以：

- **防止**玩家长时间停在 Silent 无伤磨资源；
- 给「什么时候该回去开会」制造**自然紧迫感**。

建议每幕配置：

| 参数 | 作用 |
|------|------|
| `sandbox_incursion_mult` | 静默期岸线速率倍率（可 >1 加压） |
| `sandbox_incursion_cap_behavior` | 触顶后：强制 Beat 邀约 / 仅 UI 告警 |

---

## 5. 「委任」在 Silent 的角色

参见 [management_sim_design.md](./management_sim_design.md) 第 6 节。**卡伦 / 林博士委任**在 Silent 中特别适合作为：

- 「我想专注探索」的低操作模式；
- 与 AI 碎碎念结合的**人格化运营差异**。

实现上可将委任简化为：**改变 EconomyTick 的默认策略向量**（偏防御 vs 偏研究），不产生主线账本——除非设计者显式为该委任条目挂了 `LEDGER_*` Tag（则应 `queue`）。
