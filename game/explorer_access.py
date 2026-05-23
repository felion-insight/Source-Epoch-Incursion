"""大地图探索区域：与 docs/map_design.md 锁定类型对齐（剧情 / 信息 / 能力 / 资源 / 时间）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .narrative_map import LISTEN_ANCHOR_NODES
from .session import GameSession


def _done(sess: GameSession, node_id: str) -> bool:
    return node_id in sess.completed_nodes


def _active_or_done(sess: GameSession, node_id: str) -> bool:
    return sess.current_node_id == node_id or _done(sess, node_id)


def _night_window_unlocked(sess: GameSession) -> bool:
    """设计文档：海岸线洞穴于游戏内 21:00–次日 5:00 开放。"""
    m = int(getattr(sess, "world_minute_of_day", 8 * 60) or 0)
    m = max(0, min(1439, m))
    hh = m // 60
    return hh >= 21 or hh < 5


@dataclass(frozen=True)
class _Zone:
    id: str
    x: float
    y: float
    w: float
    h: float
    lock_type: str
    label_zh: str
    info_hidden: bool
    blocked_reason_zh: str
    is_unlocked: Callable[[GameSession], bool]


# 几何与 web/explorer/main.js WORLD=6400×4800、设施片区一致
_ZONES: tuple[_Zone, ...] = (
    _Zone(
        id="mine_deep",
        x=3180,
        y=830,
        w=520,
        h=120,
        lock_type="ability",
        label_zh="废弃矿场 · 深层",
        info_hidden=False,
        blocked_reason_zh="黑暗过深：需工业探照灯（消耗 500 能源购置，或经营「加大开采深度」等决策解锁照明与支护）。",
        is_unlocked=lambda s: s.plot.has("mine_deep_lit") or s.plot.has("floodlight_equipped"),
    ),
    _Zone(
        id="listen_station_vault",
        # 与 web/explorer/main.js 中 FACILITIES.listen.core 一致（勿覆盖东侧接驳路）
        x=3668,
        y=2186,
        w=340,
        h=280,
        lock_type="resource",
        label_zh="地下监听站 · 核心舱",
        info_hidden=False,
        blocked_reason_zh="尚未建造并启用监听核心（需消耗 50 能源：设施面板「地下监听站：建造并启用」）。",
        is_unlocked=lambda s: s.plot.has("listen_station_built")
        or (s.current_node_id in LISTEN_ANCHOR_NODES),
    ),
    _Zone(
        id="coastal_cave",
        x=1380,
        y=2580,
        w=420,
        h=320,
        lock_type="time",
        label_zh="海岸线洞穴",
        info_hidden=False,
        blocked_reason_zh="入口仅在夜间低潮显露（游戏内 21:00–次日 5:00）。请使用侧栏「推进游戏时间」调至夜间，或等待夜间时段。",
        is_unlocked=_night_window_unlocked,
    ),
    _Zone(
        id="parliament_outpost",
        x=5080,
        y=1540,
        w=520,
        h=520,
        lock_type="info",
        label_zh="议会前哨站废墟",
        info_hidden=True,
        blocked_reason_zh="坐标未解密：需卡伦倒戈后提供议会隐蔽哨所情报。",
        is_unlocked=lambda s: bool(s.hidden.karen_defected),
    ),
    _Zone(
        id="echo_beacon",
        x=400,
        y=1540,
        w=560,
        h=560,
        lock_type="info",
        label_zh="回声集团信标塔",
        info_hidden=True,
        blocked_reason_zh="信号被遮蔽：需接受回声集团场外援助，或通讯阵列异常线索（升级通讯阵列相关分支）。",
        is_unlocked=lambda s: s.plot.has("echo_route_hint") or s.plot.has("echo_aid_accepted"),
    ),
    _Zone(
        id="purify_sanctuary",
        x=3040,
        y=3760,
        w=420,
        h=260,
        lock_type="info",
        label_zh="净空会圣树",
        info_hidden=True,
        blocked_reason_zh="地图无标记：完成「堇的生态课」支线节点后标注生态圣地坐标。",
        is_unlocked=lambda s: _active_or_done(s, "01-06"),
    ),
    _Zone(
        id="klein_sunk_lab",
        x=3360,
        y=400,
        w=320,
        h=260,
        lock_type="story",
        label_zh="沉没实验室 · 深层羁押区",
        info_hidden=False,
        blocked_reason_zh="隔离协议：需第三幕钥匙卡剧情（小胖或林博士授权）。推进至「寻找克莱因」后方可进入。",
        is_unlocked=lambda s: _active_or_done(s, "03-01") or _done(s, "03-02"),
    ),
)


def zone_is_unlocked(sess: GameSession, zone_id: str) -> bool:
    """供远征等系统复用 `_ZONES` 的门禁表达式；未知 id 视为未解锁。"""
    for z in _ZONES:
        if z.id == zone_id:
            return z.is_unlocked(sess)
    return False


def zone_blocked_reason_zh(sess: GameSession, zone_id: str) -> str | None:
    """仅当该区在登记表中且**当前未解锁**时返回中文门禁说明。"""
    for z in _ZONES:
        if z.id == zone_id:
            if z.is_unlocked(sess):
                return None
            return z.blocked_reason_zh or "当前暂不可进入该区域。"
    return None


def explorer_zones_for_session(sess: GameSession) -> list[dict[str, Any]]:
    """供 GET /api/state：几何与锁定状态（客户端碰撞 + 绘图 + 提示）。"""
    out: list[dict[str, Any]] = []
    for z in _ZONES:
        unlocked = z.is_unlocked(sess)
        blocked = not unlocked
        show_real_label = not (z.info_hidden and blocked)
        out.append(
            {
                "id": z.id,
                "x": z.x,
                "y": z.y,
                "w": z.w,
                "h": z.h,
                "blocks_movement": blocked,
                "lock_type": z.lock_type if blocked else "none",
                "reason_zh": z.blocked_reason_zh if blocked else "",
                "label_zh": z.label_zh,
                "show_label": show_real_label,
                "display_label_zh": "？？？" if not show_real_label else z.label_zh,
            }
        )
    return out
