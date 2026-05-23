# 叙事相位状态机与存档契约

**版本**：1.0  
**关联游戏**：源纪元 · 岸线侵入  
**最后更新**：2026-05-17  

---

## 1. 状态机（逻辑）

```
                    ┌─────────────────────────────────┐
                    │         StoryBeat               │
                    │  （主线节拍 / 必选叙事可用）      │
                    └────────────────┬────────────────┘
                                     │
              节拍结束 / 设计者显式切换到静默期
                                     ▼
                    ┌─────────────────────────────────┐
                    │           Sandbox               │
                    │ （静默运营；不投新必选主线顶点） │
                    └────────────────┬────────────────┘
                                     │
        退场条件满足 + 触发「进入下一节拍」（玩家触发或系统自动）
                                     ▼
                              StoryBeat  ……
```

### 1.1 切换触发（建议具备的几种模式）

策划可为每一章配置其一或组合：

| 模式 ID | 说明 | UX 提示 |
|---------|------|---------|
| `PLAYER_REQUEST_BRIEFING` | 玩家主动触发「收听指挥部简报 / 召开会议」→ 若无硬门槛则切入下一 Beat | 给玩家控制感 |
| `PREREQ_SATISFIED` | 资源 / 情报 / 建筑等级等达标后，系统提示「可以推进」，由玩家确认 | 防误触 |
| `TIME_MIN_ELAPSED` | 静默期至少度过 N 游戏日（或等价 tick） | 防「太短像读条」 |
| `INCURSION_THRESHOLD` | 岸线推进达到某刻度自动请求进入 Beat（制造紧迫感） | 与压力锅联动 |

**原则**：静默结束**不一定要**惩罚玩家；但需要**可读的信号**让玩家知道「为什么现在可以开会了」。

### 1.2 插队与回溯

- **Sandbox 中段禁止**：一般不推荐在 Sandbox 中段插入账本级主线，除非将整个相位切回 StoryBeat（全屏信号 + 存档点）。
- **Queued effects**：玩家在 Sandbox 发起的某类经营动作可写入 `queued_story_payload`，在进入下一 StoryBeat **第一帧**应用（见下文存档字段）。

---

## 2. 存档 / 运行时契约（字段建议）

以下字段名为**契约级建议**，落地时可映射到现有 `world.json`/存档格式。

### 2.1 叙事闸门

| 字段 | 类型 | 说明 |
|------|------|------|
| `story_phase` | `enum`: `StoryBeat \| Sandbox` | 当前相位 |
| `current_beat_id` | `string` | 与蓝图、剧情图对应的节拍 ID |
| `sandbox_session_id` | `int` | 静默期会话计数（QA、遥测） |
| `sandbox_enter_world_day` | `int` | 进入 Sandbox 时的世界日 |
| `sandbox_min_world_days` | `int \| null` | 本段静默最短世界日 |

### 2.2 退场与队列

| 字段 | 类型 | 说明 |
|------|------|------|
| `story_exit_mode` | `string[]` | 本章节配置的退场模式列表 |
| `next_beat_ready` | `bool` | 前置是否已满足（不含玩家确认） |
| `queued_effects[]` | `EffectBundleRef[]` | 待在下个 Beat 应用的效果引用 |
| `player_suppress_next_beat` | `bool` | 可选：玩家选择「再等一天」 |

### 2.3 经济与探索（快照必须可续）

参见 [sim_data_schema_content_authoring.md](./sim_data_schema_content_authoring.md)。最低限度：`resources`、`facilities`、`incursion`、`unlocked_regions`、`expeditions`。

---

## 3. QA 校验清单（相位）

- 从 Sandbox 存档读档后：**不会**凭空出现未解锁的主线必选任务。
- 在 StoryBeat 中快速存档：**不会**丢失 `sandbox_min_world_days` 等配置意图。
- `queued_effects` 必须在下一 Beat **可观测地结算**或有明确丢弃规则（丢弃需日志）。
