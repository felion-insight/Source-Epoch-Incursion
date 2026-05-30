"""轻量 JSON HTTP 服务：供 web 前端大地图与 narrative_ai 接入同一 GameSession。"""

from __future__ import annotations

import json
import os
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse

from narrative_ai.management import resolve_decision
from narrative_ai.memory import InteractionTurn
from narrative_ai.prompt_blocks import source_whisper_scene_zh

from .bridge import (
    apply_management_decision,
    apply_chat_emotional_shift,
    build_simulation_snapshot,
    can_start_conversation_with,
    CHOICE_UNVEIL_TURNS,
    end_conversation,
    flush_management_queue,
    get_conversation_turn_limits,
    narrative_chat_choice_labels,
    narrative_story_beat_system,
    npc_agent_for,
    persist_source_exchange,
    source_session_from,
    start_conversation,
)
from .default_session import get_session, session_lock, set_session
from .explorer_objectives import objectives_upcoming_blurb, player_visible_objectives, prepend_sandbox_objectives_banner
from .explorer_access import explorer_zones_for_session
from .management_turn import serialize_management_preview_payload
from .narrative_map import (
    FACILITY_MANAGEMENT_TAGS,
    facility_relevant_to_node,
    narrative_gate_management_decision_zh,
    npc_is_current_focus,
    upgrade_choice_for_facility,
)
from .overworld_npcs import opening_player_context, overworld_npc_rows
from .session import GameSession
from .world_clock import advance_world_minutes, clock_display_parts, try_purchase_industrial_floodlight
from .sim_sandbox import (
    SANDBOX_NPC_CALLS_SOFT_CAP_DAY,
    append_bulletin_zh,
    can_exit_sandbox,
    next_world_day,
    sandbox_days_elapsed,
    sandbox_min_remaining_days,
)
from .expeditions import expedition_catalog_payload, expeditions_active_ui_payload, start_expedition
from .facility_tech_tree import build_facility_tech_hints_for_sandbox, build_tech_tree_payload
from .facility_sim_ops import (
    build_facility_sim_overlay,
    claim_facility_idle,
    compact_facility_idle_bank_preview,
    facility_sim_overlays_snapshot,
)
from .underground_workshop import (
    assign_npc as workshop_assign_npc,
    build_device as workshop_build_device,
    build_workshop_snapshot,
    construct_workshop,
    deliver_task as workshop_deliver_task,
    demolish_device as workshop_demolish_device,
    move_device as workshop_move_device,
    discover_blueprint as workshop_discover_blueprint,
    export_to_base as workshop_export_to_base,
    execute_trade as workshop_execute_trade,
    import_source_ore as workshop_import_source_ore,
    rehabilitate_workshop,
    rest_npc as workshop_rest_npc,
    set_delegation as workshop_set_delegation,
    set_production_caps as workshop_set_production_caps,
    set_device_recipe as workshop_set_device_recipe,
    toggle_device as workshop_toggle_device,
    upgrade_device as workshop_upgrade_device,
    workshop_entry_pass,
    workshop_leave,
)
from .resource_activities import (
    activity_explorer_gate_ok,
    build_activity_catalog_for_session,
    build_activity_catalog_payload,
    can_run_activity,
    get_activity,
    simulate_activity_outcome,
)
from .dispatch_system import (
    DISPATCH_NPC_INFO,
    DispatchSession,
    FacilityStatus,
    build_dispatch_status_payload,
    build_facility_status_payload,
    get_facility_default,
    simulate_dispatch_auto_decision,
)
import random


# Explorer 设施工作台：`GET /api/health` 明示能力；便于确认进程是否加载了「本仓库这份」web_api
FACILITY_SIM_OVERLAYS_API = True
# HTTP 响应头：旧进程不会带该项；用它区分浏览器实际连到哪台 listener
HTTP_IDENTITY_HEADER = "X-Epoch-Incursion-Api"
HTTP_IDENTITY_VALUE = "epoch-incursion-20260517-clock"


def _game_repo_root() -> Path:
    """game/web_api.py 上一级目录 = 仓库根（含 narrative_ai / web）。"""
    return Path(__file__).resolve().parents[1]


def _diag_build_plain_body() -> bytes:
    lines = [
        "epoch-incursion-game-api",
        f"build_tag={HTTP_IDENTITY_VALUE}",
        f"facility_sim_overlays={str(bool(FACILITY_SIM_OVERLAYS_API)).lower()}",
        f"web_api_py={Path(__file__).resolve()}",
        f"repo_root_guess={_game_repo_root()}",
        "",
        "If you only see {\"ok\": true} on /api/health: wrong Python process. cd to repo_root_guess, then: python -u -m game",
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _norm_api_path(raw_path: str) -> str:
    """
    统一为「仅路径」形式，与路由表匹配。
    兼容：绝对 URI 请求行、查询串、URL 编码、重复斜杠、首尾空白。
    """
    raw = (raw_path or "/").strip()
    if raw.startswith("http://") or raw.startswith("https://"):
        p = urlparse(raw).path or "/"
    else:
        p = raw.split("?", 1)[0]
    p = unquote(p)
    while "//" in p:
        p = p.replace("//", "/")
    p = p.rstrip("/")
    if not p.startswith("/"):
        p = "/" + p
    return p if p else "/"


# POST 路由清单（供 GET /api/routes 与 404 提示）
# 存档已迁移至前端 localStorage，后端不再自动读写磁盘文件。
# 保留 GameSession.save_file/load_file 方法供调试用途，但 API 不再调用。


def _attach_autosave(sess: GameSession) -> None:
    """no-op：存档已迁移至前端 localStorage。"""
    pass


def _load_session_from_disk(set_sess: Callable[[GameSession], None]) -> None:
    """no-op：存档已迁移至前端 localStorage，后端启动时始终使用全新会话。"""
    pass


POST_ROUTE_PATHS: tuple[str, ...] = (
    "/api/choice",
    "/api/advance",
    "/api/narrative/action",
    "/api/npc/check",
    "/api/facility/check",
    "/api/npc/opening",
    "/api/npc/generate",
    "/api/npc/chat",
    "/api/source/whisper",
    "/api/management",
    "/api/session/reset",
    "/api/session/load",
    "/api/session/delete",
    "/api/sim/enter_sandbox",
    "/api/sim/exit_sandbox",
    "/api/sim/advance_world_day",
    "/api/sim/advance_clock",
    "/api/sim/purchase_floodlight",
    "/api/expedition/start",
    "/api/sim/expedition/start",
    # 模拟经营新功能路由
    "/api/sim/facility/tech_tree",
    "/api/sim/activity/catalog",
    "/api/sim/activity/run",
    "/api/sim/facility/claim_idle",
    "/api/sim/workshop/enter",
    "/api/sim/workshop/leave",
    "/api/sim/workshop/construct",
    "/api/sim/workshop/build",
    "/api/sim/workshop/upgrade",
    "/api/sim/workshop/demolish",
    "/api/sim/workshop/move",
    "/api/sim/workshop/toggle",
    "/api/sim/workshop/assign_npc",
    "/api/sim/workshop/set_recipe",
    "/api/sim/workshop/delegate",
    "/api/sim/workshop/set_caps",
    "/api/sim/workshop/import_source_ore",
    "/api/sim/workshop/export",
    "/api/sim/workshop/deliver_task",
    "/api/sim/workshop/trade",
    "/api/sim/workshop/rest_npc",
    "/api/sim/workshop/rehabilitate",
    "/api/sim/west_shaft/enter",
    "/api/sim/dispatch/start",
    "/api/sim/dispatch/cancel",
    "/api/sim/morale/modify",
)

DEBUG_POST_ROUTES: tuple[str, ...] = ("/api/debug/jump_node",)
DEBUG_GET_ROUTES: tuple[str, ...] = ("/api/debug/story_graph",)


def _debug_api_enabled() -> bool:
    v = (os.environ.get("GAME_DEBUG_API") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _post_routes_all() -> list[str]:
    out = list(POST_ROUTE_PATHS)
    if _debug_api_enabled():
        out.extend(DEBUG_POST_ROUTES)
    return out


def _workshop_api_payload(sess: GameSession) -> dict[str, Any]:
    snap = build_workshop_snapshot(sess)
    payload = _state_payload(sess)
    payload["ok"] = True
    payload["workshop"] = snap
    payload["west_shaft"] = snap
    payload["underground_workshop"] = snap
    payload["west_shaft_sim"] = snap
    return payload


def _management_recent_zh(sess: GameSession) -> list[dict[str, str]]:
    """最近决算记录（新→旧），供大地图简报。"""
    rows: list[dict[str, str]] = []
    for t in reversed(sess.applied_management_tags[-14:]):
        spec = resolve_decision(t)
        rows.append({"tag": t, "label_zh": spec.label_zh if spec else t})
    return rows


def _sandbox_state_block(sess: GameSession) -> dict[str, Any]:
    pend = sess.management_queue_pending
    lines = list(sess.sandbox_bulletin_zh or [])
    return {
        "story_phase": sess.story_phase,
        "world_day": int(sess.world_day),
        "sandbox_generation": int(sess.sandbox_generation),
        "sandbox_days_elapsed": sandbox_days_elapsed(sess),
        "sandbox_min_remaining_days": sandbox_min_remaining_days(sess),
        "sandbox_auto_resume": bool(getattr(sess, "sandbox_auto_resume", False)),
        "sandbox_auto_resume_day": getattr(sess, "sandbox_auto_resume_day", None),
        "bulletin_tail_zh": lines[-14:],
        "management_pending_queue_tags": list(pend),
        "sandbox_npc_quota": {
            "used_today": int(sess.sandbox_npc_calls_this_day),
            "cap": int(SANDBOX_NPC_CALLS_SOFT_CAP_DAY),
        },
        "expeditions_active": expeditions_active_ui_payload(sess),
        "expedition_catalog": expedition_catalog_payload(sess),
        "resource_activity_catalog": (
            build_activity_catalog_for_session(sess)
            if str(sess.story_phase or "").strip() == "Sandbox"
            else []
        ),
        "facility_idle_bank": (
            compact_facility_idle_bank_preview(getattr(sess, "facility_idle_bank", {}))
            if str(sess.story_phase or "").strip() == "Sandbox"
            else {}
        ),
        "facility_tech_hints": build_facility_tech_hints_for_sandbox(sess),
        "sandbox_ops_unlocked": bool(getattr(sess, "sandbox_ops_unlocked", False)),
    }


def _narrative_block(sess: GameSession) -> dict[str, Any]:
    n = sess.current_node()
    choices = [{"id": c.id, "label_zh": c.label_zh} for c in sess.get_active_choices()]
    fin_endings: list[dict[str, Any]] | None = None
    if n.id == "FIN-02":
        fin_endings = sess.fin02_choices()
    fin03_epilogue: dict[str, Any] | None = None
    if n.id == "FIN-03":
        from .endings import ENDING_CATALOG, EndingSpec
        # FIN-03 需展示所选结局的后日谈
        last_ending = getattr(sess, "_last_ending_id", None) or None
        found: EndingSpec | None = None
        if last_ending:
            for e in ENDING_CATALOG:
                if e.id == last_ending:
                    found = e
                    break
        if found is None and sess.completed_nodes and "FIN-02" in sess.completed_nodes:
            # 兜底：从可用结局中取第一个
            ends = sess.fin02_choices()
            last_ending = ends[0]["ending_id"] if ends else None
            if last_ending:
                for e in ENDING_CATALOG:
                    if e.id == last_ending:
                        found = e
                        break
        if found:
            fin03_epilogue = {
                "ending_id": found.id,
                "title_zh": found.title_zh,
                "description_zh": found.description_zh,
                "epilogue_zh": found.epilogue_zh,
                "tone_zh": found.tone_zh,
            }
    hints: dict[str, Any] = {}
    for fid in (
        "helipad",
        "command",
        "comm",
        "mine",
        "lab",
        "defense",
        "listen",
        "purify_grove",
        "sunk_lab",
    ):
        mtags_raw = FACILITY_MANAGEMENT_TAGS.get(fid, [])
        mtags_ui: list[dict[str, Any]] = []
        for row in mtags_raw:
            tg = str(row.get("tag") or "")
            if narrative_gate_management_decision_zh(sess, tg):
                continue
            mtags_ui.append(
                {
                    "tag": tg,
                    "label_zh": str(row.get("label_zh") or ""),
                    "preview": serialize_management_preview_payload(
                        tg,
                        sess.resources,
                        sess.hidden,
                        sess.applied_management_tags,
                        pending_tags=sess.management_queue_pending,
                    ),
                }
            )
        hints[fid] = {
            "story_relevant": facility_relevant_to_node(sess, fid),
            "upgrade_choice_id": upgrade_choice_for_facility(sess, fid),
            "management_tags": mtags_ui,
        }
    return {
        "node_id": n.id,
        "title_zh": n.title_zh,
        "act": n.act,
        "chapter": n.chapter,
        "kind": n.kind,
        "objectives_player_zh": prepend_sandbox_objectives_banner(sess.story_phase, player_visible_objectives(n), sess),
        "objectives_upcoming_blurb_zh": objectives_upcoming_blurb(sess),
        "npc_focus": n.npc_focus,
        "choices": choices,
        "fin_endings": fin_endings,
        "fin03_epilogue": fin03_epilogue,
        "can_advance_default": sess.advance_default_allowed(),
        "advance_blocked_reason_zh": sess.advance_default_blocked_reason_zh(),
        "story_navigation_blocked_zh": sess.story_navigation_blocked_reason_zh(),
        "memory_flash_lines_zh": list(n.memory_flash_lines_zh or []),
        "pre_dialogue": n.pre_dialogue,
        "facility_hints": hints,
        "sandbox": _sandbox_state_block(sess),
    }


def _state_payload(sess: GameSession) -> dict[str, Any]:
    # 构建设施状态payload
    facility_status_payload = {}
    for fid in ("comm", "mine", "lab", "defense", "listen"):
        stored = sess.facility_status.get(fid)
        if stored:
            facility_status_payload[fid] = stored
        else:
            # 使用默认值
            default = get_facility_default(fid)
            facility_status_payload[fid] = {
                "facility_id": default.facility_id,
                "tier": default.tier,
                "condition": default.condition,
                "efficiency_mult": default.efficiency_mult,
                "branch_choice": default.branch_choice,
                "is_active": default.is_active,
                "breakdown_risk": default.breakdown_risk,
            }
    # 构建委任状态payload
    dispatch_session = DispatchSession(
        npc_id=sess.dispatched_npc,
        dispatch_day=sess.dispatch_start_day,
    )
    dispatch_payload = build_dispatch_status_payload(dispatch_session, sess.world_day)
    return {
        "session": sess.to_json(),
        "narrative": _narrative_block(sess),
        "overworld_npcs": overworld_npc_rows(sess),
        "explorer_zones": explorer_zones_for_session(sess),
        "management_recent": _management_recent_zh(sess),
        "sandbox": _sandbox_state_block(sess),
        # 模拟经营新系统状态
        "morale": sess.morale,
        "facility_status": facility_status_payload,
        "activity_cooldowns": dict(sess.activity_cooldowns),
        "dispatch": dispatch_payload,
        "facility_sim_overlays": facility_sim_overlays_snapshot(sess),
        "west_shaft_sim": build_workshop_snapshot(sess),
        "underground_workshop": build_workshop_snapshot(sess),
        "world_clock": clock_display_parts(sess),
    }


def _apply_identity_headers(handler: BaseHTTPRequestHandler) -> None:
    handler.send_header(HTTP_IDENTITY_HEADER, HTTP_IDENTITY_VALUE)


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    n = int(handler.headers.get("Content-Length") or 0)
    if n <= 0:
        return {}
    raw = handler.rfile.read(n).decode("utf-8")
    return json.loads(raw) if raw else {}


def _send_json(handler: BaseHTTPRequestHandler, status: int, obj: Any) -> None:
    try:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    except (TypeError, ValueError) as enc_err:
        body = json.dumps(
            {"error": "response_not_json_serializable", "detail": str(enc_err)},
            ensure_ascii=False,
        ).encode("utf-8")
        status = 500
    try:
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        handler.send_header("Access-Control-Allow-Headers", "Content-Type")
        _apply_identity_headers(handler)
        handler.end_headers()
        handler.wfile.write(body)
        handler.wfile.flush()
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass


def _player_context_for_npc(sess: GameSession, npc_id: str, extra: str | None = None) -> str:
    n = sess.current_node()
    bullets = "\n".join(f"- {t}" for t in sess.get_active_must_deliver_zh())
    base = (
        f"当前关键节点：{n.id}《{n.title_zh}》。\n"
        f"必达信息（须在语气中落实或呼应，勿直接照念清单）：\n{bullets}\n"
        f"玩家正在大地图与「{npc_id}」对话。"
    )
    if extra:
        base += f"\n玩家输入/动作：{extra.strip()}"
    return base


def make_handler(get_sess: Callable[[], GameSession], set_sess: Callable[[GameSession], None]) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            if os.environ.get("GAME_API_QUIET") == "1":
                return
            super().log_message(format, *args)

        def do_OPTIONS(self) -> None:  # noqa: N802
            # BaseHTTPRequestHandler 须先 send_response；否则浏览器 CORS 预检无效，Explorer 会因带 JSON Content-Type 的 GET 而整页「无法同步」
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, HEAD, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
            self.send_header("Access-Control-Max-Age", "86400")
            self.send_header("Vary", "Origin")
            _apply_identity_headers(self)
            self.end_headers()

        def do_HEAD(self) -> None:  # noqa: N802
            """HEAD 请求：返回与 GET 相同的头（部分 CDN/边缘代理会发 HEAD 探测）。"""
            # 复用 GET 路径分发，但只写响应头
            p = urlparse(self.path)
            path = _norm_api_path(p.path)
            if path in ("/", "/api/state", "/api/health", "/api/ping", "/api/build", "/api/routes"):
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
            elif path in ("/favicon.ico", "/robots.txt"):
                self.send_response(204)
            else:
                self.send_response(404)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, HEAD, OPTIONS")
            _apply_identity_headers(self)
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            try:
                self._explorer_dispatch_get()
            except Exception as e:
                traceback.print_exc()
                try:
                    _send_json(
                        self,
                        500,
                        {"error": str(e), "type": type(e).__name__, "route": "GET"},
                    )
                except Exception:
                    pass

        def _explorer_dispatch_get(self) -> None:
            p = urlparse(self.path)
            path = _norm_api_path(p.path)
            sess = get_sess()
            if path in ("/", ""):
                _send_json(
                    self,
                    200,
                    {
                        "service": "epoch-incursion-game-api",
                        "state": "GET /api/state",
                        "health": "GET /api/health （旧进程可能只剩 ok:true）",
                        "ping": "GET /api/ping （纯文本自检，浏览器易读全文件）",
                        "build": "GET /api/build （JSON 构建信息）",
                        "routes": "GET /api/routes",
                        "hint": "剧情浏览器页请单独用静态服务器打开 web/explorer/，本端口只提供 JSON API。",
                    },
                )
            elif path == "/api/state":
                with session_lock():
                    pl = _state_payload(sess)
                _send_json(self, 200, pl)
            elif path == "/api/health":
                _send_json(
                    self,
                    200,
                    {
                        "ok": True,
                        # 若为 false 或未出现该项，说明你连到的进程不是当前仓库新版本 API
                        "facility_sim_overlays": bool(FACILITY_SIM_OVERLAYS_API),
                        "loaded_web_api": str(Path(__file__).resolve()),
                        "repo_root_guess": str(_game_repo_root()),
                        "ping_txt": "/api/ping",
                    },
                )
            elif path == "/api/ping":
                body_txt = _diag_build_plain_body()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body_txt)))
                self.send_header("Access-Control-Allow-Origin", "*")
                _apply_identity_headers(self)
                self.end_headers()
                self.wfile.write(body_txt)
                self.wfile.flush()
            elif path == "/api/build":
                _send_json(
                    self,
                    200,
                    {
                        "ok": True,
                        "build_tag": HTTP_IDENTITY_VALUE,
                        "facility_sim_overlays": bool(FACILITY_SIM_OVERLAYS_API),
                        "loaded_web_api": str(Path(__file__).resolve()),
                        "repo_root_guess": str(_game_repo_root()),
                    },
                )
            elif path == "/api/routes":
                _send_json(
                    self,
                    200,
                    {
                        "get": ["/", "/api/state", "/api/health", "/api/ping", "/api/build", "/api/routes"
                                ] + (list(DEBUG_GET_ROUTES) if _debug_api_enabled() else []),
                        "post": _post_routes_all(),
                        "debug_api_enabled": _debug_api_enabled(),
                    },
                )
            elif path == "/api/debug/story_graph":
                if not _debug_api_enabled():
                    _send_json(self, 403, {"ok": False, "error": "debug_disabled"})
                else:
                    g = sess.graph()
                    nodes_out: list[dict[str, Any]] = []
                    for nid, ns in sorted(g.items()):
                        nodes_out.append({
                            "node_id": nid,
                            "title_zh": ns.title_zh,
                            "act": ns.act,
                            "chapter": ns.chapter,
                            "kind": ns.kind,
                        })
                    _send_json(self, 200, {"ok": True, "current_node_id": sess.current_node_id, "nodes": nodes_out})
            elif path == "/api/npc/opening":
                _send_json(
                    self,
                    200,
                    {
                        "note": "此地址仅支持 POST；在浏览器地址栏打开会得到 GET，已改为返回本说明。",
                        "method": "POST",
                        "content_type": "application/json",
                        "example_body": {
                            "npc_id": "karen",
                            "story_focus": True,
                            "max_tokens": 520,
                        },
                    },
                )
            elif path in ("/favicon.ico", "/robots.txt"):
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
            else:
                _send_json(
                    self,
                    404,
                    {
                        "error": "not_found",
                        "method": "GET",
                        "normalized_path": path,
                        "raw_path": self.path,
                        "requestline": getattr(self, "requestline", ""),
                        "hint": "剧情 API 的 POST 接口见 GET /api/routes",
                    },
                )

        def do_POST(self) -> None:  # noqa: N802
            p = urlparse(self.path)
            path = _norm_api_path(p.path)
            sess = get_sess()
            try:
                body = _read_json(self)
            except json.JSONDecodeError:
                _send_json(self, 400, {"error": "invalid_json"})
                return

            try:
                if path == "/api/choice":
                    with session_lock():
                        gated = sess.story_navigation_blocked_reason_zh()
                        if gated:
                            _send_json(
                                self,
                                400,
                                {
                                    "ok": False,
                                    "error": "story_navigation_blocked",
                                    "reason_zh": gated,
                                    **_state_payload(sess),
                                },
                            )
                            return
                        cid = str(body.get("choice_id") or "")
                        nxt = sess.apply_choice(cid if cid else None)
                        _send_json(self, 200, {"ok": True, "next_node_id": nxt, **_state_payload(sess)})
                elif path == "/api/advance":
                    with session_lock():
                        if not sess.advance_default_allowed():
                            reason = sess.advance_default_blocked_reason_zh() or "当前不可沿默认线推进。"
                            _send_json(
                                self,
                                400,
                                {
                                    "ok": False,
                                    "error": "advance_blocked",
                                    "reason_zh": reason,
                                    **_state_payload(sess),
                                },
                            )
                            return
                        nxt = sess.advance_default()
                        _send_json(self, 200, {"ok": True, "next_node_id": nxt, **_state_payload(sess)})
                elif path == "/api/narrative/action":
                    with session_lock():
                        kind = str(body.get("kind") or "").strip()
                        if not kind:
                            _send_json(
                                self,
                                400,
                                {
                                    "ok": False,
                                    "error": "missing_kind",
                                    "reason_zh": "请求 JSON 缺少 kind，或服务端未读到正文（请确认 POST 使用 application/json 且含正文）。",
                                    **_state_payload(sess),
                                },
                            )
                        elif kind == "decrypt_datastick":
                            via = str(body.get("via") or "").strip()
                            ok_ad, err_zh = sess.apply_decrypt_datastick(via=via)
                            if not ok_ad:
                                _send_json(
                                    self,
                                    400,
                                    {"ok": False, "error": "narrative_action_rejected", "reason_zh": err_zh or "", **_state_payload(sess)},
                                )
                            else:
                                _send_json(self, 200, {"ok": True, **_state_payload(sess)})
                        elif kind == "theater_ack":
                            tid = str(body.get("node_id") or body.get("nodeId") or "").strip()
                            ok_th, err_th = sess.apply_theater_ack(tid)
                            if not ok_th:
                                _send_json(
                                    self,
                                    400,
                                    {"ok": False, "error": "narrative_action_rejected", "reason_zh": err_th or "", **_state_payload(sess)},
                                )
                            else:
                                _send_json(self, 200, {"ok": True, **_state_payload(sess)})
                        elif kind == "advance_clock":
                            try:
                                delta_nc = int(body.get("minutes"))
                            except (TypeError, ValueError):
                                _send_json(
                                    self,
                                    400,
                                    {
                                        "ok": False,
                                        "error": "invalid_minutes",
                                        "reason_zh": "请在 JSON 中提供整数 minutes。",
                                        **_state_payload(sess),
                                    },
                                )
                            else:
                                if delta_nc < 0 or delta_nc > 1560:
                                    _send_json(
                                        self,
                                        400,
                                        {
                                            "ok": False,
                                            "error": "minutes_out_of_range",
                                            "reason_zh": "一次推进分钟数过大或为负。",
                                            **_state_payload(sess),
                                        },
                                    )
                                else:
                                    wc_nc = advance_world_minutes(sess, delta_nc)
                                    if delta_nc >= 60:
                                        append_bulletin_zh(
                                            sess, f"时间推进 {delta_nc} 分钟，基地时钟 {wc_nc['display_zh']}。"
                                        )
                                    _send_json(
                                        self,
                                        200,
                                        {"ok": True, "world_clock": wc_nc, **_state_payload(sess)},
                                    )
                        elif kind == "purchase_floodlight":
                            ok_pf, err_pf = try_purchase_industrial_floodlight(sess)
                            if not ok_pf:
                                _send_json(
                                    self,
                                    400,
                                    {
                                        "ok": False,
                                        "error": "purchase_rejected",
                                        "reason_zh": err_pf or "",
                                        **_state_payload(sess),
                                    },
                                )
                            else:
                                _send_json(self, 200, {"ok": True, **_state_payload(sess)})
                        else:
                            _send_json(
                                self,
                                400,
                                {
                                    "error": "unknown_action",
                                    "hint": (
                                        "supported: decrypt_datastick, theater_ack, advance_clock, purchase_floodlight"
                                    ),
                                    "reason_zh": f"未知的 kind「{kind}」。",
                                    **_state_payload(sess),
                                },
                            )
                    return
                elif path == "/api/debug/jump_node":
                    if not _debug_api_enabled():
                        _send_json(
                            self,
                            403,
                            {
                                "ok": False,
                                "error": "debug_disabled",
                                "reason_zh": "未启用调试接口：启动 API 前设置环境变量 GAME_DEBUG_API=1（或 true/yes/on）。",
                                "hint_zh": "未启用调试接口：启动 API 前设置环境变量 GAME_DEBUG_API=1（或 true/yes/on）。",
                                **_state_payload(sess),
                            },
                        )
                        return
                    with session_lock():
                        nid = str(body.get("node_id") or "").strip()
                        if not nid:
                            _send_json(self, 400, {"error": "missing_node_id"})
                        else:
                            rc = body.get("reset_completed")
                            reset_completed = True if rc is None else bool(rc)
                            try:
                                sess.debug_jump_to_node(nid, reset_completed=reset_completed)
                            except KeyError:
                                _send_json(self, 400, {"error": "unknown_node_id", "node_id": nid})
                            else:
                                _send_json(self, 200, {"ok": True, "jumped_to": nid, **_state_payload(sess)})
                    return
                elif path == "/api/npc/check":
                    npc_id = str(body.get("npc_id") or "")
                    ok = bool(npc_id) and npc_is_current_focus(sess, npc_id)
                    _send_json(
                        self,
                        200,
                        {
                            "ok": True,
                            "npc_id": npc_id,
                            "is_story_focus": ok,
                            "narrative": _narrative_block(sess),
                        },
                    )
                elif path == "/api/facility/check":
                    with session_lock():
                        fid = str(body.get("facility_id") or "")
                        rel = facility_relevant_to_node(sess, fid) if fid else False
                        uq = upgrade_choice_for_facility(sess, fid) if fid else None
                        overlay = (
                            build_facility_sim_overlay(sess, fid)
                            if fid
                            else {"enabled": False, "workbench_supported": False, "facility_id": ""}
                        )
                        _send_json(
                            self,
                            200,
                            {
                                "ok": True,
                                "facility_id": fid,
                                "story_relevant": rel,
                                "upgrade_choice_id": uq,
                                "sim_facility_overlay": overlay,
                                "narrative": _narrative_block(sess),
                            },
                        )
                    return
                elif path == "/api/npc/opening":
                    npc_id = str(body.get("npc_id") or "")
                    story_focus = bool(body.get("story_focus"))
                    if not npc_id:
                        _send_json(self, 400, {"error": "missing_npc_id"})
                        return
                    with session_lock():
                        if (
                            sess.story_phase.strip() == "Sandbox"
                            and int(sess.sandbox_npc_calls_this_day) >= SANDBOX_NPC_CALLS_SOFT_CAP_DAY
                        ):
                            _send_json(
                                self,
                                400,
                                {
                                    "ok": False,
                                    "error": "sandbox_npc_quota_exceeded",
                                    "reason_zh": (
                                        f"本基地日静默交流配额已用尽（{SANDBOX_NPC_CALLS_SOFT_CAP_DAY} 次）；"
                                        "推进一天或结束静默再继续。"
                                    ),
                                    **_state_payload(sess),
                                },
                            )
                            return
                        ctx = opening_player_context(sess, npc_id, story_focus=story_focus)
                        agent = npc_agent_for(sess, npc_id)
                        sim = build_simulation_snapshot(sess)
                        beat = narrative_story_beat_system(sess) if story_focus else None
                        try:
                            text = agent.generate(
                                mode="scene_line",
                                player_context=ctx,
                                sim=sim,
                                max_tokens=int(body.get("max_tokens") or 520),
                                story_beat_system=beat,
                            )
                        except RuntimeError:
                            # AI 后端过载/不可用时，返回降级占位文本，不阻断游戏
                            traceback.print_exc()
                            text = "“……（通信受阻，信号断断续续）……”"
                        st = sess.get_memory_store(npc_id)
                        st.record_turn(InteractionTurn("npc", text[:600]))
                        sess.save_memory_store(st)
                        if sess.story_phase.strip() == "Sandbox":
                            sess.sandbox_npc_calls_this_day = int(sess.sandbox_npc_calls_this_day) + 1
                        _send_json(self, 200, {"ok": True, "text": text, **_state_payload(sess)})
                    return
                elif path == "/api/npc/generate":
                    npc_id = str(body.get("npc_id") or "")
                    mode = str(body.get("mode") or "scene_line")
                    extra = body.get("context")
                    if not npc_id:
                        _send_json(self, 400, {"error": "missing_npc_id"})
                        return
                    with session_lock():
                        if (
                            sess.story_phase.strip() == "Sandbox"
                            and int(sess.sandbox_npc_calls_this_day) >= SANDBOX_NPC_CALLS_SOFT_CAP_DAY
                        ):
                            _send_json(
                                self,
                                400,
                                {
                                    "ok": False,
                                    "error": "sandbox_npc_quota_exceeded",
                                    "reason_zh": (
                                        f"本基地日静默交流配额已用尽（{SANDBOX_NPC_CALLS_SOFT_CAP_DAY} 次）；"
                                        "推进一天或结束静默再继续。"
                                    ),
                                    **_state_payload(sess),
                                },
                            )
                            return
                        ctx = str(extra) if extra else _player_context_for_npc(sess, npc_id)
                        agent = npc_agent_for(sess, npc_id)
                        sim = build_simulation_snapshot(sess)
                        try:
                            text = agent.generate(
                                mode=mode,  # type: ignore[arg-type]
                                player_context=ctx,
                                sim=sim,
                                max_tokens=int(body.get("max_tokens") or 500),
                                story_beat_system=narrative_story_beat_system(sess),
                            )
                        except RuntimeError:
                            traceback.print_exc()
                            text = "“……（通信受阻，信号断断续续）……”"
                        st = sess.get_memory_store(npc_id)
                        st.record_turn(InteractionTurn("npc", text[:600]))
                        sess.save_memory_store(st)
                        if sess.story_phase.strip() == "Sandbox":
                            sess.sandbox_npc_calls_this_day = int(sess.sandbox_npc_calls_this_day) + 1
                        _send_json(self, 200, {"ok": True, "text": text, **_state_payload(sess)})
                    return
                elif path == "/api/npc/chat":
                    npc_id = str(body.get("npc_id") or "")
                    player_text = str(body.get("player_text") or "").strip()
                    action = str(body.get("action") or "send").strip()  # send | start | end
                    if not npc_id:
                        _send_json(self, 400, {"error": "missing_npc_id"})
                        return
                    if action == "end":
                        with session_lock():
                            end_conversation(sess)
                            _send_json(self, 200, {"ok": True, "conversation_ended": True, **_state_payload(sess)})
                        return
                    if not player_text and action != "start":
                        _send_json(self, 400, {"error": "missing_player_text"})
                        return
                    with session_lock():
                        # 检查该 NPC 是否已主动结束对话（不允许再次发起）
                        if action == "start":
                            can_start, block_reason = can_start_conversation_with(sess, npc_id)
                            if not can_start:
                                _send_json(
                                    self,
                                    200,
                                    {
                                        "ok": True,
                                        "conversation_blocked": True,
                                        "reason_zh": block_reason,
                                        **_state_payload(sess),
                                    },
                                )
                                return

                        # 检查静默期配额
                        if (
                            sess.story_phase.strip() == "Sandbox"
                            and int(sess.sandbox_npc_calls_this_day) >= SANDBOX_NPC_CALLS_SOFT_CAP_DAY
                        ):
                            _send_json(
                                self,
                                400,
                                {
                                    "ok": False,
                                    "error": "sandbox_npc_quota_exceeded",
                                    "reason_zh": (
                                        f"本基地日静默交流配额已用尽（{SANDBOX_NPC_CALLS_SOFT_CAP_DAY} 次）；"
                                        "推进一天或结束静默再继续。"
                                    ),
                                    **_state_payload(sess),
                                },
                            )
                            return

                        # 初始化或恢复对话
                        current_conv_npc = sess.active_conversation_npc
                        if action == "start" or (current_conv_npc and current_conv_npc != npc_id):
                            start_conversation(sess, npc_id)
                        elif not current_conv_npc:
                            start_conversation(sess, npc_id)

                        # 记录玩家输入
                        sess.conversation_history.append({
                            "role": "player",
                            "text": player_text,
                        })

                        # 获取剧情上下文
                        node = sess.current_node()
                        choice_labels = narrative_chat_choice_labels(sess)

                        # 调用 AI
                        agent = npc_agent_for(sess, npc_id)
                        sim = build_simulation_snapshot(sess)
                        soft_limit, hard_limit = get_conversation_turn_limits(sess)
                        fallback_text = "“……（通信受阻，信号断断续续）……”"
                        try:
                            result = agent.chat_turn(
                                player_text=player_text if player_text else "（玩家走近，等待回应）",
                                conversation_history=sess.conversation_history[:-1],  # 不包括刚加的这一条
                                choice_labels=choice_labels,
                                node_id=node.id,
                                node_title_zh=node.title_zh,
                                must_deliver_zh=sess.get_active_must_deliver_zh(),
                                sim=sim,
                                turn_number=sess.conversation_turn_count + 1,  # 即将进行的轮次
                                soft_limit=soft_limit,
                                hard_limit=hard_limit,
                            )
                        except RuntimeError:
                            traceback.print_exc()
                            # AI 不可用时返回降级文本
                            from narrative_ai.npc_agent import ChatTurnResult
                            result = ChatTurnResult(
                                npc_text=fallback_text,
                                topic_status="on_topic",
                            )
                        sess.conversation_history.append({
                            "role": "npc",
                            "text": result.npc_text,
                        })
                        sess.conversation_turn_count += 1

                        # 是否为对话的第一轮（action: "start" 触发的初始回话）
                        is_first_turn = (sess.conversation_turn_count == 1)

                        # ── 处理话题状态 ──
                        topic_status = result.topic_status
                        conversation_closed = False
                        if topic_status == "off_topic":
                            if not is_first_turn:
                                sess.conversation_off_topic_count += 1
                        elif topic_status == "on_topic":
                            # 重回正题 → 重置偏离计数
                            if sess.conversation_off_topic_count > 0:
                                sess.conversation_off_topic_count = max(0, sess.conversation_off_topic_count - 1)
                        elif topic_status == "resolved":
                            # NPC 明确表达了结束对话的意图 —— 但不允许在第一轮就结束
                            if not is_first_turn:
                                conversation_closed = True

                        # ── close_signal：AI 内部判断对话该结束了（不依赖台词中的告别语）──
                        if result.close_signal and not conversation_closed and not is_first_turn:
                            conversation_closed = True

                        # 应用情绪变化
                        emotional_applied = {}
                        if result.emotional_shift:
                            emotional_applied = apply_chat_emotional_shift(sess, npc_id, result.emotional_shift)

                        # 记录到 NPC 记忆
                        st = sess.get_memory_store(npc_id)
                        summary = f"[自由对话 #{sess.conversation_turn_count}] {player_text[:200]}"
                        st.record_turn(InteractionTurn("player", summary))
                        st.record_turn(InteractionTurn("npc", result.npc_text[:600]))
                        sess.save_memory_store(st)

                        if sess.story_phase.strip() == "Sandbox":
                            sess.sandbox_npc_calls_this_day = int(sess.sandbox_npc_calls_this_day) + 1

                        # ── 选项浮现信号 ──
                        # 到达浮现阈值时，告知前端可以显示剧情选项
                        unveil_choices = (
                            sess.conversation_turn_count >= CHOICE_UNVEIL_TURNS
                            and not result.story_resolved
                            and bool(choice_labels)
                        )

                        # ── 如果 AI 已自然收束到选项，或 NPC 主动结束对话，清理对话状态 ──
                        if result.story_resolved:
                            end_conversation(sess)
                        elif conversation_closed:
                            # NPC 主动结束对话（不通过选项），标记为不可再发起
                            end_conversation(sess, closed_by_npc=True)

                        response_body: dict[str, Any] = {
                            "ok": True,
                            "npc_text": result.npc_text,
                            "topic_status": topic_status,
                            "off_topic_count": sess.conversation_off_topic_count,
                            "turn_count": sess.conversation_turn_count,
                            "emotional_shift": result.emotional_shift,
                            "emotional_applied": emotional_applied,
                            "redirection_hint": result.redirection_hint,
                            "story_resolved": result.story_resolved,
                            "suggested_choices": result.suggested_choices,
                            "close_signal": result.close_signal,
                            "conversation_npc": npc_id,
                            "unveil_choices": unveil_choices,
                            "conversation_closed": conversation_closed,
                            **_state_payload(sess),
                        }
                        _send_json(self, 200, response_body)
                    return
                elif path == "/api/management":
                    tag = str(body.get("tag") or "")
                    if not tag:
                        _send_json(self, 400, {"error": "missing_tag"})
                        return
                    with session_lock():
                        ok, rej, queued = apply_management_decision(sess, tag)
                        if not ok:
                            _send_json(
                                self,
                                400,
                                {
                                    "ok": False,
                                    "error": "management_rejected",
                                    "reason_zh": rej or "无法执行该项经营决议",
                                    "tag": tag,
                                    **_state_payload(sess),
                                },
                            )
                            return
                        _send_json(self, 200, {"ok": True, "management_queued": queued, **_state_payload(sess)})
                    return
                elif path == "/api/sim/enter_sandbox":
                    with session_lock():
                        sp = str(sess.story_phase or "").strip()
                        if sp == "Sandbox":
                            _send_json(
                                self,
                                400,
                                {
                                    "ok": False,
                                    "error": "already_sandbox",
                                    "reason_zh": "已在静默运营期中。",
                                    **_state_payload(sess),
                                },
                            )
                            return
                        nid = str(sess.current_node_id or "").strip()
                        if nid in ("FIN-02", "FIN-03"):
                            _send_json(
                                self,
                                400,
                                {
                                    "ok": False,
                                    "error": "sandbox_forbidden_at_node",
                                    "reason_zh": "终局抉择与结局演出节点不可手动进入静默。",
                                    **_state_payload(sess),
                                },
                            )
                            return
                        if not bool(getattr(sess, "sandbox_ops_unlocked", False)):
                            _send_json(
                                self,
                                400,
                                {
                                    "ok": False,
                                    "error": "sandbox_not_unlocked",
                                    "reason_zh": "静默运营尚未在剧情中开放；请先推进主线至相应节点后再试。",
                                    **_state_payload(sess),
                                },
                            )
                            return
                        mw = body.get("min_world_days")
                        sess.sandbox_min_world_days = (
                            None if mw is None else max(0, int(mw))  # type: ignore[arg-type]
                        )
                        sess.story_phase = "Sandbox"
                        sess.sandbox_ops_unlocked = True
                        sess.sandbox_generation = int(sess.sandbox_generation) + 1
                        sess.sandbox_enter_world_day = int(sess.world_day)
                        append_bulletin_zh(sess, f"基地进入静默运营节律——第 {sess.world_day} 日。")
                        _send_json(self, 200, {"ok": True, **_state_payload(sess)})
                    return
                elif path == "/api/sim/exit_sandbox":
                    with session_lock():
                        force_exit = bool(body.get("force"))
                        allowed, cerr = can_exit_sandbox(sess, force=force_exit)
                        if not allowed:
                            _send_json(
                                self,
                                400,
                                {"ok": False, "error": "sandbox_exit_blocked", "reason_zh": cerr or "", **_state_payload(sess)},
                            )
                            return
                        drained, ferr = flush_management_queue(sess)
                        if ferr:
                            _send_json(
                                self,
                                400,
                                {"ok": False, "error": "management_queue_blocked", "reason_zh": ferr, **_state_payload(sess)},
                            )
                            return
                        sess.story_phase = "StoryBeat"
                        sess.sandbox_enter_world_day = None
                        sess.sandbox_min_world_days = None
                        sess.sandbox_auto_resume = False
                        sess.sandbox_auto_resume_day = None
                        if drained:
                            append_bulletin_zh(sess, f"静默结束：决算队列落地 {len(drained)} 项。")
                        else:
                            append_bulletin_zh(sess, "静默结束：暂无挂起决算队列。")
                        _send_json(
                            self,
                            200,
                            {"ok": True, "sandbox_flushed_tags": drained, **_state_payload(sess)},
                        )
                    return
                elif path == "/api/sim/advance_world_day":
                    with session_lock():
                        tick_pack = next_world_day(sess)
                        _send_json(self, 200, {"ok": True, **tick_pack, **_state_payload(sess)})
                    return
                elif path == "/api/sim/advance_clock":
                    with session_lock():
                        try:
                            delta = int(body.get("minutes"))
                        except (TypeError, ValueError):
                            _send_json(
                                self,
                                400,
                                {
                                    "ok": False,
                                    "error": "invalid_minutes",
                                    "reason_zh": "请在 JSON 中提供整数 minutes。",
                                    **_state_payload(sess),
                                },
                            )
                            return
                        if delta < 0 or delta > 1560:
                            _send_json(
                                self,
                                400,
                                {
                                    "ok": False,
                                    "error": "minutes_out_of_range",
                                    "reason_zh": "一次推进分钟数过大或为负。",
                                    **_state_payload(sess),
                                },
                            )
                            return
                        wc = advance_world_minutes(sess, delta)
                        if delta >= 60:
                            append_bulletin_zh(sess, f"时间推进 {delta} 分钟，基地时钟 {wc['display_zh']}。")
                        _send_json(self, 200, {"ok": True, "world_clock": wc, **_state_payload(sess)})
                    return
                elif path == "/api/sim/purchase_floodlight":
                    with session_lock():
                        ok_f, err_f = try_purchase_industrial_floodlight(sess)
                        if not ok_f:
                            _send_json(
                                self,
                                400,
                                {"ok": False, "error": "purchase_rejected", "reason_zh": err_f or "", **_state_payload(sess)},
                            )
                            return
                        _send_json(self, 200, {"ok": True, **_state_payload(sess)})
                    return
                elif path in ("/api/expedition/start", "/api/sim/expedition/start"):
                    with session_lock():
                        leader = str(body.get("leader_npc_id") or body.get("leader") or "").strip()
                        dest = str(body.get("destination_id") or body.get("dest_id") or "").strip()
                        ok_ex, err_ex, row_ex = start_expedition(sess, leader, dest)
                        if not ok_ex:
                            _send_json(
                                self,
                                400,
                                {
                                    "ok": False,
                                    "error": "expedition_rejected",
                                    "reason_zh": err_ex or "无法签发远征。",
                                    **_state_payload(sess),
                                },
                            )
                            return
                        _send_json(
                            self,
                            200,
                            {"ok": True, "expedition": row_ex, **_state_payload(sess)},
                        )
                    return
                elif path == "/api/source/whisper":
                    q = str(body.get("question") or "").strip() or "……"
                    from narrative_ai.source_agent import SourceAgent

                    src = SourceAgent()
                    s = source_session_from(sess)
                    n = sess.current_node()
                    scene = source_whisper_scene_zh(n.id, n.title_zh, sess.get_active_must_deliver_zh())
                    extra = body.get("extra_world")
                    merged = f"{scene}\n{extra}" if extra else scene
                    try:
                        ans = src.whisper(question=q, session=s, extra_world=merged)
                    except RuntimeError:
                        traceback.print_exc()
                        ans = "……（源的回声被淹没在噪声中）……"
                    persist_source_exchange(sess, q, ans)
                    _send_json(self, 200, {"ok": True, "text": ans, **_state_payload(sess)})
                elif path == "/api/session/reset":
                    with session_lock():
                        fresh = GameSession()
                        _attach_autosave(fresh)
                        set_sess(fresh)
                        _send_json(self, 200, {"ok": True, **_state_payload(get_sess())})
                    return
                elif path == "/api/session/load":
                    raw = body.get("session")
                    if not isinstance(raw, dict):
                        _send_json(self, 400, {"error": "missing_session_object"})
                        return
                    with session_lock():
                        loaded = GameSession.from_json(raw)
                        _attach_autosave(loaded)
                        set_sess(loaded)
                        _send_json(self, 200, {"ok": True, **_state_payload(get_sess())})
                    return
                elif path == "/api/session/delete":
                    with session_lock():
                        fresh = GameSession()
                        _attach_autosave(fresh)
                        set_sess(fresh)
                        _send_json(
                            self,
                            200,
                            {
                                "ok": True,
                                "deleted": True,
                                **_state_payload(get_sess()),
                            },
                        )
                    return
                # === 模拟经营新功能路由 ===
                elif path == "/api/sim/facility/tech_tree":
                    """获取设施科技树"""
                    fid = str(body.get("facility_id") or "").strip()
                    if not fid:
                        _send_json(self, 400, {"error": "missing_facility_id"})
                        return
                    with session_lock():
                        applied_set = frozenset(sess.applied_management_tags)
                        pending_set = frozenset(sess.management_queue_pending)
                        sandbox = sess.story_phase.strip() == "Sandbox"
                        tree_payload = build_tech_tree_payload(
                            fid, applied_set, pending_set, sandbox
                        )
                        _send_json(self, 200, {"ok": True, "tech_tree": tree_payload, **_state_payload(sess)})
                    return
                elif path == "/api/sim/activity/catalog":
                    """获取资源活动目录"""
                    region_id = body.get("region_id")
                    if region_id:
                        region_id = str(region_id).strip() or None
                    with session_lock():
                        catalog = build_activity_catalog_payload(region_id=region_id)
                        _send_json(self, 200, {"ok": True, "activity_catalog": catalog, **_state_payload(sess)})
                    return
                elif path == "/api/sim/activity/run":
                    """执行资源活动"""
                    activity_id = str(body.get("activity_id") or "").strip()
                    if not activity_id:
                        _send_json(self, 400, {"error": "missing_activity_id"})
                        return
                    with session_lock():
                        # 检查相位
                        if sess.story_phase.strip() != "Sandbox":
                            _send_json(
                                self, 400, {
                                    "ok": False,
                                    "error": "not_in_sandbox",
                                    "reason_zh": "资源活动仅在静默运营期内可用。",
                                    **_state_payload(sess),
                                }
                            )
                            return
                        activity = get_activity(activity_id)
                        if not activity:
                            _send_json(self, 400, {"error": "unknown_activity"})
                            return
                        gate_ok_go, gate_msg = activity_explorer_gate_ok(sess, activity)
                        if not gate_ok_go:
                            _send_json(
                                self,
                                400,
                                {
                                    "ok": False,
                                    "error": "activity_region_locked",
                                    "reason_zh": gate_msg or "目标区域门禁未开放。",
                                    **_state_payload(sess),
                                },
                            )
                            return
                        # 检查冷却
                        cooldowns = getattr(sess, "activity_cooldowns", {})
                        can_run, reason = can_run_activity(
                            activity_id, sess.world_day, cooldowns
                        )
                        if not can_run:
                            _send_json(
                                self, 400, {
                                    "ok": False,
                                    "error": "activity_on_cooldown",
                                    "reason_zh": reason,
                                    **_state_payload(sess),
                                }
                            )
                            return
                        # 消耗资源
                        if sess.resources.energy < activity.cost_energy or sess.resources.food < activity.cost_food:
                            _send_json(
                                self, 400, {
                                    "ok": False,
                                    "error": "insufficient_resources",
                                    "reason_zh": "资源不足以执行该活动。",
                                    **_state_payload(sess),
                                }
                            )
                            return
                        if sess.resources.energy < activity.cost_energy or sess.resources.food < activity.cost_food:
                            _send_json(
                                self, 400, {
                                    "ok": False,
                                    "error": "insufficient_resources",
                                    "reason_zh": "资源不足以执行该活动。",
                                    **_state_payload(sess),
                                }
                            )
                            return
                        sess.resources.apply(
                            energy=-activity.cost_energy, food=-activity.cost_food
                        )
                        # 计算结果（成功/失败）
                        roll = random.random()
                        success = roll >= activity.risk_failure
                        outcome = simulate_activity_outcome(activity, success)
                        sess.resources.apply(**outcome)
                        # 更新冷却
                        cooldowns[activity_id] = sess.world_day
                        sess.activity_cooldowns = cooldowns
                        # 更新简报
                        if success:
                            reward_str = "、".join([f"{k}+{v}" for k, v in outcome.items() if v > 0])
                            suffix = reward_str if reward_str else "已记入资源"
                            append_bulletin_zh(
                                sess, f"资源活动「{activity.run_kind_zh}」完成：{suffix}。"
                            )
                        else:
                            append_bulletin_zh(
                                sess,
                                f"资源活动「{activity.run_kind_zh}」受挫：行前成本已消耗，未取得预期增益。",
                            )
                        _send_json(
                            self, 200, {
                                "ok": True,
                                "activity_success": success,
                                "outcome": outcome,
                                "activity_id": activity_id,
                                **_state_payload(sess),
                            }
                        )
                    return
                elif path == "/api/sim/facility/claim_idle":
                    fid_claim = str(body.get("facility_id") or "").strip()
                    if not fid_claim:
                        _send_json(self, 400, {"error": "missing_facility_id"})
                        return
                    with session_lock():
                        ok_c, cerr, payout = claim_facility_idle(sess, fid_claim)
                        if not ok_c:
                            _send_json(
                                self,
                                400,
                                {
                                    "ok": False,
                                    "error": "facility_idle_claim_blocked",
                                    "reason_zh": cerr or "",
                                    **_state_payload(sess),
                                },
                            )
                            return
                        line_claim = "、".join(f"{k}+{v}" for k, v in payout.items())
                        append_bulletin_zh(
                            sess,
                            f"工作台·积存领取：{line_claim}（设施 {fid_claim}）。",
                        )
                        _send_json(
                            self,
                            200,
                            {
                                "ok": True,
                                "facility_id": fid_claim,
                                "claimed": payout,
                                **_state_payload(sess),
                            },
                        )
                    return

                elif path in ("/api/sim/workshop/enter", "/api/sim/west_shaft/enter"):
                    with session_lock():
                        workshop_discover_blueprint(sess)
                        workshop_entry_pass(sess)
                        _send_json(self, 200, _workshop_api_payload(sess))
                    return
                elif path == "/api/sim/workshop/leave":
                    with session_lock():
                        workshop_leave(sess)
                        _send_json(self, 200, {"ok": True, **_state_payload(sess)})
                    return
                elif path == "/api/sim/workshop/construct":
                    with session_lock():
                        ok_c, cerr = construct_workshop(sess)
                        if not ok_c:
                            _send_json(
                                self,
                                400,
                                {
                                    "ok": False,
                                    "error": "workshop_construct_blocked",
                                    "reason_zh": cerr or "",
                                    **_state_payload(sess),
                                },
                            )
                            return
                        _send_json(self, 200, _workshop_api_payload(sess))
                    return
                elif path == "/api/sim/workshop/build":
                    x = int(body.get("x", -1))
                    y = int(body.get("y", -1))
                    dtype = str(body.get("device_type") or "").strip()
                    with session_lock():
                        ok_b, berr = workshop_build_device(sess, x, y, dtype)
                        if not ok_b:
                            _send_json(
                                self,
                                400,
                                {
                                    "ok": False,
                                    "error": "workshop_build_blocked",
                                    "reason_zh": berr or "",
                                    **_state_payload(sess),
                                },
                            )
                            return
                        _send_json(self, 200, _workshop_api_payload(sess))
                    return
                elif path == "/api/sim/workshop/upgrade":
                    x, y = int(body.get("x", -1)), int(body.get("y", -1))
                    with session_lock():
                        ok_u, uerr = workshop_upgrade_device(sess, x, y)
                        if not ok_u:
                            _send_json(
                                self,
                                400,
                                {"ok": False, "error": "workshop_upgrade_blocked", "reason_zh": uerr or "", **_state_payload(sess)},
                            )
                            return
                        _send_json(self, 200, _workshop_api_payload(sess))
                    return
                elif path == "/api/sim/workshop/demolish":
                    x, y = int(body.get("x", -1)), int(body.get("y", -1))
                    with session_lock():
                        ok_d, derr = workshop_demolish_device(sess, x, y)
                        if not ok_d:
                            _send_json(
                                self,
                                400,
                                {"ok": False, "error": "workshop_demolish_blocked", "reason_zh": derr or "", **_state_payload(sess)},
                            )
                            return
                        _send_json(self, 200, _workshop_api_payload(sess))
                    return
                elif path == "/api/sim/workshop/move":
                    from_x = int(body.get("from_x", body.get("x", -1)))
                    from_y = int(body.get("from_y", body.get("y", -1)))
                    to_x = int(body.get("to_x", -1))
                    to_y = int(body.get("to_y", -1))
                    with session_lock():
                        ok_m, merr = workshop_move_device(sess, from_x, from_y, to_x, to_y)
                        if not ok_m:
                            _send_json(
                                self,
                                400,
                                {"ok": False, "error": "workshop_move_blocked", "reason_zh": merr or "", **_state_payload(sess)},
                            )
                            return
                        _send_json(self, 200, _workshop_api_payload(sess))
                    return
                elif path == "/api/sim/workshop/toggle":
                    x, y = int(body.get("x", -1)), int(body.get("y", -1))
                    with session_lock():
                        ok_t, terr = workshop_toggle_device(sess, x, y)
                        if not ok_t:
                            _send_json(
                                self,
                                400,
                                {"ok": False, "error": "workshop_toggle_blocked", "reason_zh": terr or "", **_state_payload(sess),
                                },
                            )
                            return
                        _send_json(self, 200, _workshop_api_payload(sess))
                    return
                elif path == "/api/sim/workshop/assign_npc":
                    x, y = int(body.get("x", -1)), int(body.get("y", -1))
                    npc_id = str(body.get("npc_id") or "").strip()
                    with session_lock():
                        ok_a, aerr = workshop_assign_npc(sess, x, y, npc_id)
                        if not ok_a:
                            _send_json(
                                self,
                                400,
                                {"ok": False, "error": "workshop_assign_blocked", "reason_zh": aerr or "", **_state_payload(sess)},
                            )
                            return
                        _send_json(self, 200, _workshop_api_payload(sess))
                    return
                elif path == "/api/sim/workshop/set_recipe":
                    x, y = int(body.get("x", -1)), int(body.get("y", -1))
                    recipe = str(body.get("recipe") or "default").strip()
                    with session_lock():
                        ok_r, rerr = workshop_set_device_recipe(sess, x, y, recipe)
                        if not ok_r:
                            _send_json(
                                self,
                                400,
                                {"ok": False, "error": "workshop_recipe_blocked", "reason_zh": rerr or "", **_state_payload(sess)},
                            )
                            return
                        _send_json(self, 200, _workshop_api_payload(sess))
                    return
                elif path == "/api/sim/workshop/delegate":
                    enabled = bool(body.get("enabled", False))
                    with session_lock():
                        workshop_set_delegation(sess, enabled)
                        _send_json(self, 200, _workshop_api_payload(sess))
                    return
                elif path == "/api/sim/workshop/set_caps":
                    caps = body.get("caps")
                    enabled = body.get("enabled")
                    with session_lock():
                        workshop_set_production_caps(
                            sess,
                            caps if isinstance(caps, dict) else None,
                            enabled if "enabled" in body else None,
                        )
                        _send_json(self, 200, _workshop_api_payload(sess))
                    return
                elif path == "/api/sim/workshop/import_source_ore":
                    amount = int(body.get("amount", 1) or 1)
                    with session_lock():
                        ok_i, ierr = workshop_import_source_ore(sess, amount)
                        if not ok_i:
                            _send_json(
                                self,
                                400,
                                {"ok": False, "error": "workshop_import_blocked", "reason_zh": ierr or "", **_state_payload(sess)},
                            )
                            return
                        _send_json(self, 200, _workshop_api_payload(sess))
                    return
                elif path == "/api/sim/workshop/export":
                    resource = str(body.get("resource") or "").strip()
                    amount = int(body.get("amount", 1) or 1)
                    with session_lock():
                        ok_e, eerr, exp = workshop_export_to_base(sess, resource, amount)
                        if not ok_e:
                            _send_json(
                                self,
                                400,
                                {"ok": False, "error": "workshop_export_blocked", "reason_zh": eerr or "", **_state_payload(sess)},
                            )
                            return
                        _send_json(self, 200, {**_workshop_api_payload(sess), "export_result": exp})
                    return
                elif path == "/api/sim/workshop/deliver_task":
                    task_id = str(body.get("task_id") or "").strip()
                    with session_lock():
                        ok_dt, dterr, delivery = workshop_deliver_task(sess, task_id)
                        if not ok_dt:
                            _send_json(
                                self,
                                400,
                                {"ok": False, "error": "workshop_task_blocked", "reason_zh": dterr or "", **_state_payload(sess)},
                            )
                            return
                        _send_json(self, 200, {**_workshop_api_payload(sess), "delivery_result": delivery})
                    return
                elif path == "/api/sim/workshop/trade":
                    trade_id = str(body.get("trade_id") or "").strip()
                    with session_lock():
                        ok_tr, terr, payout = workshop_execute_trade(sess, trade_id)
                        if not ok_tr:
                            _send_json(
                                self,
                                400,
                                {"ok": False, "error": "workshop_trade_blocked", "reason_zh": terr or "", **_state_payload(sess)},
                            )
                            return
                        _send_json(self, 200, {**_workshop_api_payload(sess), "trade_result": payout})
                    return
                elif path == "/api/sim/workshop/rest_npc":
                    npc_id = str(body.get("npc_id") or "").strip()
                    with session_lock():
                        ok_r, rerr = workshop_rest_npc(sess, npc_id)
                        if not ok_r:
                            _send_json(
                                self,
                                400,
                                {"ok": False, "error": "workshop_rest_blocked", "reason_zh": rerr or "", **_state_payload(sess)},
                            )
                            return
                        _send_json(self, 200, _workshop_api_payload(sess))
                    return
                elif path == "/api/sim/workshop/rehabilitate":
                    with session_lock():
                        ok_rb, rberr = rehabilitate_workshop(sess)
                        if not ok_rb:
                            _send_json(
                                self,
                                400,
                                {"ok": False, "error": "workshop_rehab_blocked", "reason_zh": rberr or "", **_state_payload(sess)},
                            )
                            return
                        _send_json(self, 200, _workshop_api_payload(sess))
                    return
                elif path == "/api/sim/dispatch/start":
                    """开始委任NPC代管基地"""
                    npc_id = str(body.get("npc_id") or "").strip()
                    if not npc_id:
                        _send_json(self, 400, {"error": "missing_npc_id"})
                        return
                    if npc_id not in DISPATCH_NPC_INFO:
                        _send_json(
                            self, 400, {
                                "ok": False,
                                "error": "invalid_dispatcher",
                                "reason_zh": f"无法委任 {npc_id}，仅支持：karen（卡伦）、dr_lin（林博士）。",
                                **_state_payload(sess),
                            }
                        )
                        return
                    with session_lock():
                        if sess.story_phase.strip() != "Sandbox":
                            _send_json(
                                self, 400, {
                                    "ok": False,
                                    "error": "not_in_sandbox",
                                    "reason_zh": "委任功能仅在静默运营期内可用。",
                                    **_state_payload(sess),
                                }
                            )
                            return
                        # 已有委任则取消
                        if sess.dispatched_npc:
                            append_bulletin_zh(sess, f"已取消对{sess.dispatched_npc}的委任。")
                        sess.dispatched_npc = npc_id
                        sess.dispatch_start_day = sess.world_day
                        info = DISPATCH_NPC_INFO[npc_id]
                        append_bulletin_zh(
                            sess, f"已委任 {info['label_zh']} 代管基地。策略：{info['strategy_zh']}"
                        )
                        _send_json(
                            self, 200, {
                                "ok": True,
                                "dispatch_started": npc_id,
                                "dispatch_day": sess.world_day,
                                **_state_payload(sess),
                            }
                        )
                    return
                elif path == "/api/sim/dispatch/cancel":
                    """取消委任"""
                    with session_lock():
                        if not sess.dispatched_npc:
                            _send_json(
                                self, 400, {
                                    "ok": False,
                                    "error": "no_active_dispatch",
                                    "reason_zh": "当前没有进行中的委任。",
                                    **_state_payload(sess),
                                }
                            )
                            return
                        old_dispatcher = sess.dispatched_npc
                        sess.dispatched_npc = None
                        info = DISPATCH_NPC_INFO.get(old_dispatcher, {})
                        append_bulletin_zh(
                            sess, f"已取消对{info.get('label_zh', old_dispatcher)}的委任。"
                        )
                        _send_json(
                            self, 200, {
                                "ok": True,
                                "dispatch_cancelled": old_dispatcher,
                                **_state_payload(sess),
                            }
                        )
                    return
                elif path == "/api/sim/morale/modify":
                    """修改士气值（用于特定剧情事件或玩家决策）"""
                    delta = int(body.get("delta", 0))
                    reason = str(body.get("reason") or "").strip()
                    with session_lock():
                        old_morale = sess.morale
                        sess.morale = max(0, min(100, sess.morale + delta))
                        if reason:
                            append_bulletin_zh(
                                sess, f"士气变化（{old_morale}→{sess.morale}）：{reason}"
                            )
                        _send_json(
                            self, 200, {
                                "ok": True,
                                "morale_before": old_morale,
                                "morale_after": sess.morale,
                                "delta": delta,
                                **_state_payload(sess),
                            }
                        )
                    return
                else:
                    _send_json(
                        self,
                        404,
                        {
                            "error": "not_found",
                            "method": "POST",
                            "normalized_path": path,
                            "raw_path": self.path,
                            "requestline": getattr(self, "requestline", ""),
                            "post_routes": _post_routes_all(),
                            "hint": "路径必须与上表完全一致（区分大小写）。若从浏览器地址栏测试 opening，请改用 POST 或先看 GET /api/npc/opening 说明。",
                        },
                    )
            except Exception as e:  # noqa: BLE001
                _send_json(self, 500, {"error": str(e), "type": type(e).__name__})

    return Handler


class GameAPIServer(ThreadingHTTPServer):
    """实例级 reuse，避免改动 ThreadingHTTPServer 全局类属性（测试/多模块同进程更安全）。"""

    allow_reuse_address = True


def run_server(host: str | None = None, port: int | None = None) -> None:
    h = host or os.environ.get("GAME_API_HOST", "127.0.0.1")
    p = int(port or os.environ.get("GAME_API_PORT", "8787"))
    # 存档已迁移至前端 localStorage，后端启动时始终使用全新会话
    Handler = make_handler(get_session, set_session)
    httpd = GameAPIServer((h, p), Handler)
    api_src = Path(__file__).resolve()
    repo = _game_repo_root()
    print(f"Game API pid={os.getpid()}: http://{h}:{p}/  （GET /api/state, POST /api/choice …）")
    print(f"已加载模块 game.web_api ← {api_src}")
    print(f"推断仓库根 repo_root_guess ← {repo} （应用在此目录启动：cd 到这里再 python -u -m game）")
    print(
        f"自检：① GET /api/ping 为多行文本；任一响应头应含 X-Epoch-Incursion-Api: {HTTP_IDENTITY_VALUE}；② GET /api/health 含 facility_sim_overlays。"
    )
    print(
        f"若仍为 404/旧 JSON：多半是别的进程抢先占端口。请核对本次 pid={os.getpid()} "
        f"是否为监听 {p} 的进程（PowerShell：`Get-NetTCPConnection -LocalPort {p} -State Listen | Select-Object OwningProcess`）。"
    )
    print("也可用仓库根目录的 run_game_api.ps1 / run_game_api.cmd 双击启动（自动 cd，避免 cd /d 报错）。")
    print(f"远征签发: POST /api/expedition/start （别名为 POST /api/sim/expedition/start）")
    if _debug_api_enabled():
        print("调试接口已启用：POST /api/debug/jump_node（环境变量 GAME_DEBUG_API=1）")
    httpd.serve_forever()
