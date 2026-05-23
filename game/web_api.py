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
    build_simulation_snapshot,
    flush_management_queue,
    narrative_story_beat_system,
    npc_agent_for,
    persist_source_exchange,
    source_session_from,
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
# 默认存档文件路径（可通过环境变量 GAME_SAVE_PATH 自定义）
_SAVE_FILE_DEFAULT = Path(__file__).resolve().parent.parent / "save" / "session.json"


def _get_save_file_path() -> Path:
    """获取存档文件路径，支持环境变量覆盖。"""
    env_path = os.environ.get("GAME_SAVE_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return _SAVE_FILE_DEFAULT


POST_ROUTE_PATHS: tuple[str, ...] = (
    "/api/choice",
    "/api/advance",
    "/api/narrative/action",
    "/api/npc/check",
    "/api/facility/check",
    "/api/npc/opening",
    "/api/npc/generate",
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
    "/api/sim/dispatch/start",
    "/api/sim/dispatch/cancel",
    "/api/sim/morale/modify",
)

DEBUG_POST_ROUTES: tuple[str, ...] = ("/api/debug/jump_node",)


def _debug_api_enabled() -> bool:
    v = (os.environ.get("GAME_DEBUG_API") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _post_routes_all() -> list[str]:
    out = list(POST_ROUTE_PATHS)
    if _debug_api_enabled():
        out.extend(DEBUG_POST_ROUTES)
    return out


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
    choices = [{"id": c.id, "label_zh": c.label_zh} for c in (n.choices or [])]
    fin_endings: list[dict[str, str]] | None = None
    if n.id == "FIN-02":
        fin_endings = [{"id": cid, "label_zh": lab} for cid, lab in sess.fin02_choices()]
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
        "objectives_player_zh": prepend_sandbox_objectives_banner(sess.story_phase, player_visible_objectives(n)),
        "objectives_upcoming_blurb_zh": objectives_upcoming_blurb(sess),
        "npc_focus": n.npc_focus,
        "choices": choices,
        "fin_endings": fin_endings,
        "can_advance_default": sess.advance_default_allowed(),
        "advance_blocked_reason_zh": sess.advance_default_blocked_reason_zh(),
        "story_navigation_blocked_zh": sess.story_navigation_blocked_reason_zh(),
        "memory_flash_lines_zh": list(n.memory_flash_lines_zh or []),
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
    bullets = "\n".join(f"- {t}" for t in n.must_deliver_zh)
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
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
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
                        "get": ["/", "/api/state", "/api/health", "/api/ping", "/api/build", "/api/routes"],
                        "post": _post_routes_all(),
                        "debug_api_enabled": _debug_api_enabled(),
                    },
                )
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
                        text = agent.generate(
                            mode="scene_line",
                            player_context=ctx,
                            sim=sim,
                            max_tokens=int(body.get("max_tokens") or 520),
                            story_beat_system=beat,
                        )
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
                        text = agent.generate(
                            mode=mode,  # type: ignore[arg-type]
                            player_context=ctx,
                            sim=sim,
                            max_tokens=int(body.get("max_tokens") or 500),
                            story_beat_system=narrative_story_beat_system(sess),
                        )
                        st = sess.get_memory_store(npc_id)
                        st.record_turn(InteractionTurn("npc", text[:600]))
                        sess.save_memory_store(st)
                        if sess.story_phase.strip() == "Sandbox":
                            sess.sandbox_npc_calls_this_day = int(sess.sandbox_npc_calls_this_day) + 1
                        _send_json(self, 200, {"ok": True, "text": text, **_state_payload(sess)})
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
                        append_bulletin_zh(sess, f"静默运营 #{sess.sandbox_generation} 开始——基地时钟：第 {sess.world_day} 日。")
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
                    scene = source_whisper_scene_zh(n.id, n.title_zh, n.must_deliver_zh)
                    extra = body.get("extra_world")
                    merged = f"{scene}\n{extra}" if extra else scene
                    ans = src.whisper(question=q, session=s, extra_world=merged)
                    persist_source_exchange(sess, q, ans)
                    _send_json(self, 200, {"ok": True, "text": ans, **_state_payload(sess)})
                elif path == "/api/session/reset":
                    with session_lock():
                        set_sess(GameSession())
                        _send_json(self, 200, {"ok": True, **_state_payload(get_sess())})
                    return
                elif path == "/api/session/load":
                    raw = body.get("session")
                    if not isinstance(raw, dict):
                        _send_json(self, 400, {"error": "missing_session_object"})
                        return
                    with session_lock():
                        set_sess(GameSession.from_json(raw))
                        _send_json(self, 200, {"ok": True, **_state_payload(get_sess())})
                    return
                elif path == "/api/session/delete":
                    save_path = _get_save_file_path()
                    existed = save_path.exists()
                    with session_lock():
                        if existed:
                            save_path.unlink()
                        set_sess(GameSession())
                        _send_json(
                            self,
                            200,
                            {
                                "ok": True,
                                "deleted": existed,
                                "save_path": str(save_path),
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
