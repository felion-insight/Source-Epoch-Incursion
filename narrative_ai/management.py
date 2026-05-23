from __future__ import annotations

from dataclasses import dataclass

# Keys align with game code you may use later; labels match design doc intent.
DECISION_REGISTRY: dict[str, dict[str, object]] = {
    "comm_array_encrypt": {
        "label_zh": "通讯阵列：安装加密破解模块",
        "hint": "破译议会密文，牵扯「灰镜」监视；卡伦紧张，林博士惊讶，回声可能首次接入。",
        "reactors": [("dr_lin", "惊讶与不安"), ("karen", "紧张戒备"), ("echo_7", "可能趁机接触")],
    },
    "comm_array_broadcast": {
        "label_zh": "通讯阵列：安装全频广播系统",
        "hint": "吸引净空会与公众注意力；舆论与敌意上升。",
        "reactors": [("karen", "反对或要求解释"), ("jin", "兴趣上升")],
    },
    "mine_deepen": {
        "label_zh": "源矿机：加大开采深度",
        "hint": "能源增加、岸线侵入加速；林博士反对，小胖可能私心感谢。",
        "reactors": [("dr_lin", "惊恐与劝告"), ("chubby", "矛盾感激"), ("karen", "关注风险")],
    },
    "mine_limit": {
        "label_zh": "源矿机：限制开采",
        "hint": "岸线暂缓、能源紧缺压力；议会谴责线可接。",
        "reactors": [("dr_lin", "宽慰"), ("karen", "施压或务实劝恢复")],
    },
    "lab_neural_scan": {
        "label_zh": "医疗/实验室：加装神经扫描仪",
        "hint": "可能发现卡伦体内芯片，摊牌导火索。",
        "reactors": [("karen", "极度紧张"), ("dr_lin", "支持科学")],
    },
    "lab_sync_suppressor": {
        "label_zh": "医疗/实验室：研发同调抑制器",
        "hint": "同调降低，净空会可能索要技术。",
        "reactors": [("dr_lin", "内心矛盾"), ("jin", "试探合作")],
    },
    "defense_fortify": {
        "label_zh": "防御工事：提升至坚固",
        "hint": "岸线减速，回声渗透风险。",
        "reactors": [("karen", "赞许"), ("dr_lin", "担忧资源透支")],
    },
    "listen_station_on": {
        "label_zh": "地下监听站：建造并启用",
        "hint": "同调飙升，源的低语加深；回声干扰。",
        "reactors": [("dr_lin", "忧心"), ("chubby", "好奇"), ("karen", "反对"), ("echo_7", "敌意干扰")],
    },
    "supply_medical_first": {
        "label_zh": "资源分配：优先医疗伤员",
        "hint": "士气与支线线索倾向小胖线；卡伦或认为浪费。",
        "reactors": [("chubby", "感激"), ("karen", "抱怨或务实质疑")],
    },
    "reject_echo_aid": {
        "label_zh": "拒绝回声集团能源援助",
        "hint": "独立立场；回声恼怒与报复尝试。",
        "reactors": [("echo_7", "冷漠威胁"), ("karen", "暗中认可独立")],
    },
    "accept_echo_aid": {
        "label_zh": "接受回声集团援助",
        "hint": "被监听与渗透加深。",
        "reactors": [("karen", "反对"), ("dr_lin", "警告")],
    },
    "purge_partial_mine": {
        "label_zh": "同意净空会部分引爆源矿",
        "hint": "与林博士激烈对峙；堇信任上升。",
        "reactors": [("jin", "感激与加重托付"), ("dr_lin", "愤怒失望")],
    },
}


@dataclass(frozen=True)
class ManagementReactionSpec:
    tag: str
    label_zh: str
    player_facing_hint: str
    reactors: tuple[tuple[str, str], ...]


def resolve_decision(tag: str) -> ManagementReactionSpec | None:
    row = DECISION_REGISTRY.get(tag)
    if row is None:
        return None
    return ManagementReactionSpec(
        tag=tag,
        label_zh=str(row["label_zh"]),
        player_facing_hint=str(row["hint"]),
        reactors=tuple(row["reactors"]),  # type: ignore[arg-type]
    )
