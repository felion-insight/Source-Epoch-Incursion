# AI 交互预算与 Sandbox 语义约束

**版本**：1.0  
**关联游戏**：源纪元 · 岸线侵入  
**最后更新**：2026-05-17  

---

## 1. 适用范围

- `narrative_ai/` 侧的 NPC、源低语（若玩家在 Silent 仍可与源轻度交互）。
- 「经营决策后立即评论」、[management_sim_design.md](./management_sim_design.md) §9 的 NPC 碎碎念。
- 「临时访客 NPC」全文生成。

本文件不写具体 Prompt；只规定**频率、信息量、与账本隔离**的工程约束。

---

## 2. 碎碎念配额（沿用并收紧为工程契约）

对齐经营文档经济性控制，并加上 **Sandbox multiplier**：

| 场景 | 上限建议 |
|------|----------|
| 单次经营决策后触发的 NPC 评论 | ≤ 2 条 |
| 每游戏日内总评论（全体 NPC） | ≤ 3 条（StoryBeat） / ≤ 5 条（Sandbox） |
| 玩家在 Silent 「仅跑图未经营」时每游戏日 NPC 主动联系 | ≤ 1 条 | 

**超限行为**：降级为简报一行 `FLAVOR_BULLETIN`，不呼叫 API。

---

## 3. 语义约束「信息预算」

在 `Sandbox + FLAVOR_AI_CHAT` 类别下，模型输出应经由后处理过滤器（关键词/主题模型均可）阻拦下列内容落入玩家可见正文：

| 阻拦类 | 例子 |
|--------|------|
| 新势力首秀真名与其完整阴谋陈述 | 「回声集团已全盘掌控你」但若 Beat 未到 |
| 下一幕才有的硬证据文件名/编号 | 未在静默期授权的道具 |
| 直接揭示尚未发生的强制事件桥段 | 「三天后小胖会求你」 |

**允许**：情绪化抱怨、对已发生事实的评论、对已可见资源的讨价还价。

若必须「吐硬线索」，将输出路由为 **QueuedBriefing**，在下一 `StoryBeat` 以正式渠道宣读。

---

## 4. 临时 NPC（Sandbox）

对齐 [management_sim_design.md](./management_sim_design.md) §9.2：

| 字段 | 约束 |
|------|------|
| 存续时长 | 短（单次到访或单次 exped 周期内） |
| 记忆写入 | 只写访客短期记忆存储；不写主线账本变量 |
| 可给予奖励类型 | `EXPLORE_LOOT_NONLEDGER`、小额 `intel` |
| Spawn 频次 | Per `sandbox_session` 上限次数 + RNG |

---

## 5. 「源的低语」在 Sandbox

若在静默期保留源交互：

- **默认**：低语只允许 `FLAVOR` + 轻度 `ModifyPlayerVariable`（如同调微幅波动），**禁止**账本真相一次性Dump。
- 需要「猛料」时必须 `queue`。

---

## 6. Telemetry（可选）

| 字段 | 用途 |
|------|------|
| `sandbox_api_calls_day` | 监测成本 |
| `blocked_leak_attempts` | 过滤器拦住的关键字次数 |
