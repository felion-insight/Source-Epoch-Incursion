"""会话状态：当前节点、资源、隐藏变量、阴谋层、各 NPC 记忆存储。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from narrative_ai.memory import NpcMemoryStore

from .endings import available_endings
from .hidden_state import BaseResources, PlayerHiddenVars, PlotFlags
from .story_graph import NodeSpec, load_story_graph


@dataclass
class GameSession:
    """游戏逻辑层单会话（可序列化）。不依赖 demo/。"""

    current_node_id: str = "PRO-01"
    hidden: PlayerHiddenVars = field(default_factory=PlayerHiddenVars)
    resources: BaseResources = field(default_factory=BaseResources)
    plot: PlotFlags = field(default_factory=PlotFlags)
    conspiracy_tier_unlocked: int = 0
    last_management_tag: str | None = None
    last_decision_label_zh: str | None = None
    # 已执行的经营决议（同一 tag 仅能生效一次；互斥组见 management_turn）。
    applied_management_tags: list[str] = field(default_factory=list)
    chose_destroy_source: bool = False
    completed_nodes: list[str] = field(default_factory=list)
    npc_memory: dict[str, dict[str, Any]] = field(default_factory=dict)
    # 与「源」低语的往返记录（格式同 SourceSession.lines，便于存档恢复）
    source_lines: list[str] = field(default_factory=list)

    # 静默运营期（Sandbox）与时间轴 · 对齐 docs/sim_phase_machine_save_contract.md
    story_phase: str = "StoryBeat"
    world_day: int = 1
    #: 游戏内一日中的分钟数 0–1439（与 docs/map_design.md 时间锁、NPC_movement 对齐）
    world_minute_of_day: int = 8 * 60
    sandbox_generation: int = 0
    #: 静默运营是否在剧情中已向玩家开放（含自动切入后）；为 False 时不应提供手动进入静默。
    sandbox_ops_unlocked: bool = False
    sandbox_enter_world_day: int | None = None
    sandbox_min_world_days: int | None = None
    sandbox_bulletin_zh: list[str] = field(default_factory=list)
    management_queue_pending: list[str] = field(default_factory=list)
    sandbox_npc_calls_this_day: int = 0
    expeditions_active: list[dict[str, object]] = field(default_factory=list)

    # 模拟经营新系统 · 对齐 docs/sim_data_schema_content_authoring.md
    # 士气系统
    morale: int = 75  # 0-100，士气值
    # 设施状态
    facility_status: dict[str, dict[str, Any]] = field(default_factory=dict)
    # 设施面板可领取的「积存」挂机池（静默期内按日累加）；与 economy_tick 主账本并行
    facility_idle_bank: dict[str, dict[str, int]] = field(default_factory=dict)
    # 活动冷却追踪
    activity_cooldowns: dict[str, int] = field(default_factory=dict)
    # 委任状态
    dispatched_npc: str | None = None  # 当前委任的NPC
    dispatch_start_day: int = 0

    _graph: dict[str, NodeSpec] | None = field(default=None, repr=False)

    def graph(self) -> dict[str, NodeSpec]:
        if self._graph is None:
            self._graph = load_story_graph()
        return self._graph

    def current_node(self) -> NodeSpec:
        g = self.graph()
        if self.current_node_id not in g:
            raise KeyError(self.current_node_id)
        return g[self.current_node_id]

    def get_memory_store(self, npc_id: str) -> NpcMemoryStore:
        if npc_id in self.npc_memory:
            blob = self.npc_memory[npc_id]
            store = NpcMemoryStore(
                npc_id=npc_id,
                long_term_notes=list(blob.get("long_term_notes") or []),
                conspiracy_tier_unlocked=int(blob.get("conspiracy_tier_unlocked", self.conspiracy_tier_unlocked)),
            )
            store.emotional.trust = float(blob.get("trust", store.emotional.trust))
            store.plot_flags = set(blob.get("plot_flags") or [])
            return store
        return NpcMemoryStore(npc_id=npc_id, conspiracy_tier_unlocked=self.conspiracy_tier_unlocked)

    def save_memory_store(self, store: NpcMemoryStore) -> None:
        self.npc_memory[store.npc_id] = {
            "long_term_notes": list(store.long_term_notes),
            "conspiracy_tier_unlocked": store.conspiracy_tier_unlocked,
            "trust": store.emotional.trust,
            "plot_flags": list(store.plot_flags),
        }

    def _apply_npc_trust(self, deltas: dict[str, float]) -> None:
        for npc_id, d in deltas.items():
            st = self.get_memory_store(npc_id)
            st.emotional.trust = max(0.0, min(100.0, st.emotional.trust + float(d)))
            self.save_memory_store(st)

    def _enter_node_effects(self, node: NodeSpec) -> None:
        for k, v in node.on_enter_hidden.items():
            self.hidden.apply_delta(k, v)
        if "conspiracy_tier" in node.on_enter_plot:
            self.conspiracy_tier_unlocked = max(
                self.conspiracy_tier_unlocked,
                int(node.on_enter_plot["conspiracy_tier"]),
            )

    def enter_current(self) -> None:
        node = self.current_node()
        if node.id == "02-01":
            self.plot.discard("datastick_decrypt_complete")
        if node.id == "02-02":
            self.plot.discard("memory_flash_02_02_ack")
        self._enter_node_effects(node)
        from .sandbox_node_hooks import apply_node_sandbox_automation

        apply_node_sandbox_automation(self, node)

    def story_navigation_blocked_reason_zh(self) -> str | None:
        """静默运营期内禁止主线推进（抉择 / 一键推进）。"""
        if str(self.story_phase or "").strip() == "Sandbox":
            return "当前为静默运营期：暂不开放主线选项与一键推进。"
        return None

    def advance_default_allowed(self) -> bool:
        """无分支节点是否允许 POST /api/advance（含剧情门闩）。"""
        if self.story_navigation_blocked_reason_zh():
            return False
        node = self.current_node()
        if node.id == "FIN-02" or node.choices or node.next is None:
            return False
        if node.id == "02-01" and not self.plot.has("datastick_decrypt_complete"):
            return False
        if node.id == "02-02" and not self.plot.has("memory_flash_02_02_ack"):
            return False
        return True

    def advance_default_blocked_reason_zh(self) -> str | None:
        if self.story_navigation_blocked_reason_zh():
            return self.story_navigation_blocked_reason_zh()
        node = self.current_node()
        if node.id == "02-01" and not self.plot.has("datastick_decrypt_complete"):
            return "须先在医疗实验室完成加密数据棒的离线解密，或与林博士现场确认解密结果。"
        if node.id == "02-02" and not self.plot.has("memory_flash_02_02_ack"):
            return "请先完整观看记忆闪回演出（全屏演出会自动弹出）；结束后方可推进。"
        return None

    def apply_decrypt_datastick(self, *, via: str) -> tuple[bool, str | None]:
        """第二幕 02-01：在实验室或与林博士交互后标记解密完成。"""
        if via not in frozenset({"lab", "dr_lin"}):
            return False, "无效的解密场合。"
        if self.current_node_id != "02-01":
            return False, "当前剧情节点不需要解密数据棒。"
        if self.plot.has("datastick_decrypt_complete"):
            return True, None
        self.plot.enable("datastick_decrypt_complete")
        return True, None

    def apply_theater_ack(self, node_id: str) -> tuple[bool, str | None]:
        """节点专属剧场/闪回观看完毕确认（当前实现：02-02 记忆闪回）。"""
        nid = (node_id or "").strip()
        if not nid:
            return False, "缺少剧场节点标识 node_id。"
        try:
            cur_id = self.current_node().id.strip()
        except KeyError:
            return False, "剧情节点无效（存档可能损坏），请尝试重置会话。"
        if nid != cur_id:
            return (
                False,
                f"剧场确认失败：与服务器当前节点不一致（请刷新页面）。当前「{cur_id}」，请求「{nid}」。",
            )
        if cur_id != "02-02":
            return False, "当前节点不需要剧场确认。"
        if self.plot.has("memory_flash_02_02_ack"):
            return True, None
        self.plot.enable("memory_flash_02_02_ack")
        return True, None

    def _resolve_next(self, node: NodeSpec, choice_id: str | None) -> str | None:
        nxt = node.next
        if node.choices and choice_id:
            for c in node.choices:
                if c.id == choice_id:
                    nxt = c.next
                    break
        if nxt and nxt in self.graph():
            n = self.graph()[nxt]
            if n.requires_flags_any and not any(self.plot.has(f) for f in n.requires_flags_any):
                return n.skip_to or n.next
        return nxt

    def apply_choice(self, choice_id: str | None) -> str | None:
        node = self.current_node()
        if node.id == "FIN-02":
            if not choice_id or not choice_id.startswith("ending:"):
                raise ValueError("FIN-02 需要结局选择 id：ending:E1 …")
            self.completed_nodes.append(node.id)
            self.current_node_id = "FIN-03"
            self.enter_current()
            return self.current_node_id

        if node.choices:
            if not choice_id:
                raise ValueError("该节点需要选择 choice_id")
            chosen = next((c for c in node.choices if c.id == choice_id), None)
            if chosen is None:
                raise KeyError(choice_id)
            for k, v in chosen.hidden_deltas.items():
                self.hidden.apply_delta(k, v)
            if chosen.resource_deltas:
                self.resources.apply(**chosen.resource_deltas)
            if chosen.npc_trust:
                self._apply_npc_trust(chosen.npc_trust)
            for f in chosen.flags_add:
                self.plot.enable(f)
                if f == "karen_defected":
                    self.hidden.karen_defected = True
        elif choice_id:
            raise ValueError("该节点无选项")

        self.completed_nodes.append(node.id)
        nxt = self._resolve_next(node, choice_id)
        if not nxt:
            return None
        self.current_node_id = nxt
        self.enter_current()
        return self.current_node_id

    def advance_default(self) -> str | None:
        """无分支节点：沿默认 next 前进。"""
        node = self.current_node()
        if node.id == "FIN-02":
            raise ValueError("FIN-02 需选择结局（见 fin02_choices）")
        if node.choices:
            raise ValueError("有分支的节点不可 advance_default")
        if not self.advance_default_allowed():
            raise ValueError(self.advance_default_blocked_reason_zh() or "当前不可沿默认线推进")
        self.completed_nodes.append(node.id)
        nxt = self._resolve_next(node, None)
        if not nxt:
            return None
        self.current_node_id = nxt
        self.enter_current()
        return self.current_node_id

    def fin02_choices(self) -> list[tuple[str, str]]:
        ends = available_endings(self.hidden)
        return [(f"ending:{e.id}", f"走向：{e.title_zh}" + ("（隐藏）" if e.hidden else "")) for e in ends]

    def to_json(self) -> dict[str, Any]:
        return {
            "current_node_id": self.current_node_id,
            "hidden": asdict(self.hidden),
            "resources": asdict(self.resources),
            "plot": {"flags": sorted(self.plot.flags)},
            "conspiracy_tier_unlocked": self.conspiracy_tier_unlocked,
            "last_management_tag": self.last_management_tag,
            "last_decision_label_zh": self.last_decision_label_zh,
            "applied_management_tags": list(self.applied_management_tags),
            "chose_destroy_source": self.chose_destroy_source,
            "completed_nodes": list(self.completed_nodes),
            "npc_memory": dict(self.npc_memory),
            "source_lines": list(self.source_lines),
            "story_phase": self.story_phase,
            "world_day": int(self.world_day),
            "world_minute_of_day": int(self.world_minute_of_day),
            "sandbox_generation": int(self.sandbox_generation),
            "sandbox_ops_unlocked": bool(self.sandbox_ops_unlocked),
            "sandbox_enter_world_day": self.sandbox_enter_world_day,
            "sandbox_min_world_days": self.sandbox_min_world_days,
            "sandbox_bulletin_zh": list(self.sandbox_bulletin_zh),
            "management_queue_pending": list(self.management_queue_pending),
            "sandbox_npc_calls_this_day": int(self.sandbox_npc_calls_this_day),
            "expeditions_active": list(self.expeditions_active),
            # 新增模拟经营系统字段
            "morale": int(self.morale),
            "facility_status": dict(self.facility_status),
            "facility_idle_bank": dict(self.facility_idle_bank),
            "activity_cooldowns": dict(self.activity_cooldowns),
            "dispatched_npc": self.dispatched_npc,
            "dispatch_start_day": int(self.dispatch_start_day),
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> GameSession:
        h = data.get("hidden") or {}
        hv = PlayerHiddenVars(
            SYNC=float(h.get("SYNC", 15)),
            HUMAN=float(h.get("HUMAN", 55)),
            COUNCIL=float(h.get("COUNCIL", 50)),
            PURIFY=float(h.get("PURIFY", 20)),
            ECHO=float(h.get("ECHO", 15)),
            INCURSION=float(h.get("INCURSION", 25)),
            RESET=int(h.get("RESET", 0)),
            INSIGHT=float(h.get("INSIGHT", 10)),
            karen_defected=bool(h.get("karen_defected", False)),
            chubby_quest_complete=bool(h.get("chubby_quest_complete", False)),
        )
        r = data.get("resources") or {}
        res = BaseResources(
            energy=int(r.get("energy", 80)),
            food=int(r.get("food", 70)),
            medical=int(r.get("medical", 40)),
            intel=int(r.get("intel", 10)),
        )
        pf = PlotFlags(flags=set((data.get("plot") or {}).get("flags") or []))
        raw_ops = data.get("sandbox_ops_unlocked")
        if raw_ops is None:
            sandbox_ops_unlocked = bool(
                int(data.get("sandbox_generation", 0) or 0) > 0
                or str(data.get("story_phase", "") or "").strip() == "Sandbox"
            )
        else:
            sandbox_ops_unlocked = bool(raw_ops)
        s = cls(
            current_node_id=str(data.get("current_node_id", "PRO-01")).strip(),
            hidden=hv,
            resources=res,
            plot=pf,
            conspiracy_tier_unlocked=int(data.get("conspiracy_tier_unlocked", 0)),
            last_management_tag=data.get("last_management_tag"),
            last_decision_label_zh=data.get("last_decision_label_zh"),
            applied_management_tags=list(data.get("applied_management_tags") or []),
            chose_destroy_source=bool(data.get("chose_destroy_source", False)),
            completed_nodes=list(data.get("completed_nodes") or []),
            npc_memory=dict(data.get("npc_memory") or {}),
            source_lines=list(data.get("source_lines") or []),
            story_phase=str(data.get("story_phase", "StoryBeat") or "StoryBeat").strip(),
            world_day=int(data.get("world_day", 1) or 1),
            world_minute_of_day=int(data.get("world_minute_of_day", 8 * 60) or 8 * 60),
            sandbox_generation=int(data.get("sandbox_generation", 0) or 0),
            sandbox_ops_unlocked=sandbox_ops_unlocked,
            sandbox_enter_world_day=data.get("sandbox_enter_world_day"),
            sandbox_min_world_days=data.get("sandbox_min_world_days"),
            sandbox_bulletin_zh=list(data.get("sandbox_bulletin_zh") or []),
            management_queue_pending=list(data.get("management_queue_pending") or []),
            sandbox_npc_calls_this_day=int(data.get("sandbox_npc_calls_this_day", 0) or 0),
            expeditions_active=list(data.get("expeditions_active") or []),
            # 新增模拟经营系统字段
            morale=int(data.get("morale", 75)),
            facility_status=dict(data.get("facility_status") or {}),
            facility_idle_bank=dict(data.get("facility_idle_bank") or {}),
            activity_cooldowns=dict(data.get("activity_cooldowns") or {}),
            dispatched_npc=data.get("dispatched_npc"),
            dispatch_start_day=int(data.get("dispatch_start_day", 0) or 0),
        )
        if s.sandbox_enter_world_day is not None:
            s.sandbox_enter_world_day = int(s.sandbox_enter_world_day)
        if s.sandbox_min_world_days is not None:
            s.sandbox_min_world_days = int(s.sandbox_min_world_days)
        s.world_minute_of_day = max(0, min(1439, int(s.world_minute_of_day)))
        return s

    def debug_jump_to_node(self, node_id: str, *, reset_completed: bool = True) -> None:
        """调试专用：跳到图中任意节点并 enter_current。调用方须自行校验权限（如 GAME_DEBUG_API）。"""
        if node_id not in self.graph():
            raise KeyError(node_id)
        if reset_completed:
            self.completed_nodes = []
        else:
            self.completed_nodes = [x for x in self.completed_nodes if x != node_id]
        self.current_node_id = node_id.strip()
        self.enter_current()

    def save_file(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_json(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load_file(cls, path: Path) -> GameSession:
        return cls.from_json(json.loads(path.read_text(encoding="utf-8")))
