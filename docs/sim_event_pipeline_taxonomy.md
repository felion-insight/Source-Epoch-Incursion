# 事件管线与叙事分级 taxonomy

**版本**：1.0  
**关联游戏**：源纪元 · 岸线侵入  
**最后更新**：2026-05-17  

---

## 1. 设计目标

所有会改变世界的玩家动作（对话选项、建造升级、委派、探索结算、外交开关）都应走同一套：**「动作 → EffectBundle → 过滤器（按 StoryPhase）→ 持久化与应用」**。  
避免出现「某一个脚本路径可以绕过 Sandbox 闸门写主线账本」。

---

## 2. EffectBundle（逻辑块）

### 2.1 建议结构（概念）

每条玩家动作产出 0～N 个原子效果 `AtomicEffect`，组合为 `EffectBundle`：

```
EffectBundle:
  source: PlayerActionRef         # 来源：哪位 UI / 对话节点
  story_tags: StoryTag[]         # 用于分级与 QA
  world_effects: AtomicEffect[]  # 对世界 JSON 的修改
  npc_memory_hints: Hint[]       # 给 AI/NPC 的提示（可选）
  narrative_delivery: Immediate | Queued | SuppressedInSandbox
```

### 2.2 AtomicEffect（示例类型）

| 类型 | 说明 | Sandbox 默认 |
|------|------|----------------|
| `ModifyResource` | 四类资源增减 | 允许 |
| `ModifyFacility` | 等级、分支、耐久 | 允许（若附带账本级叙事见下） |
| `ModifyIncursion` | 岸线速率 / 刻度 | 允许 |
| `UnlockRegion` | 地图区域 | **通常禁止**或对白名单条目允许 |
| `SetPlayerVariable` | 隐藏变量、结局相关 | **禁止或 Queued**，见 taxonomy |
| `SpawnMainQuestNode` | 新必选主线 | **禁止** |
| `SpawnSideContent` | 支线 / 碎片化叙事 | **条件性允许** |
| `TriggerCinematicOrBriefing_LedgerClass` | 账本级简报 | **Queued** → 下一 Beat |
| `SpawnTemporaryNpc` | 临时 NPC（AI） | **条件性允许**，见 budgets 文档 |

---

## 3. StoryTag 分级（对白名单机器的输入）

建议使用稳定枚举（实现可转成字符串）。

| StoryTag ID | 中文名 | Sandbox 投放策略 |
|-------------|--------|-------------------|
| `LEDGER_MAIN` | 主线账本 | 禁止即时；若源自动作为经营后果则 **Queued** 到 StoryBeat |
| `LEDGER_FACTION_FIRST_CONTACT` | 势力首次登场 | **禁止**/Queued |
| `BRANCH_EXCLUSIVE` | 互斥大招（如多方不可同时反悔） | **Queued** |
| `PRESSURE_WORLD` | 纯压力变化（岸线、渗透率） | 允许 |
| `FLAVOR_AI_CHAT` | AI 碎碎念 | 允许（配额限制） |
| `FLAVOR_BULLETIN` | 简报一行 | 允许 |
| `EXPLORE_LOOT_NONLEDGER` | 非账本探索掉落 | 允许 |
| `SIDE_NONLEDGER` | 非账本支线火花 | **条件**：不得包含结局关键字/新势力真名首秀 |
| `TEMP_NPC_ENCOUNTER` | 临时访客 | **条件**：遵守信息预算 |

 taxonomy 与本表一致的策划表存放在 [sim_data_schema_content_authoring.md](./sim_data_schema_content_authoring.md)。

---

## 4. Sandbox 过滤器（伪代码）

```text
function apply(action, bundle, phase):
  if phase == StoryBeat:
    apply_all(bundle.world_effects)
    dispatch_narrative(bundle.narrative_delivery)
    return

  # Sandbox
  for effect in bundle.world_effects:
    if classification(effect) is SAFE_UNDER_SANDBOX:
      apply(effect)
    else:
      enqueue_for_next_beat(effect)

  for narrative in bundle.narrative_delivery:
    if narrative is ImmediateFlavorOnly:
      dispatch_with_budget(narrative)
    else:
      enqueue_for_next_beat(narrative)
```

---

## 5. 存量「经营→剧情映射表」的迁移建议

[management_sim_design.md](./management_sim_design.md) 第一节表里，每一行经营决策建议增加三列：

| 新增列 | 说明 |
|--------|------|
| `sandbox_policy` | `allow` / `block` / `queue` |
| `story_tags` | 上文枚举 |
| `notes` | 是否允许在 Sandbox UI 灰色禁用并提示「将在下次简报结算」 |

这样程序与叙事可以同源维护，避免口述规则漂移。
