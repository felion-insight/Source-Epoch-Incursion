"""结局条件与 docs/player_variables_endings_matrix.md §三 对齐的判定。"""

from __future__ import annotations

from dataclasses import dataclass

from .hidden_state import PlayerHiddenVars


@dataclass(frozen=True)
class EndingSpec:
    id: str
    title_zh: str
    description_zh: str = ""
    epilogue_zh: str = ""
    tone_zh: str = ""
    hidden: bool = False


ENDING_CATALOG: tuple[EndingSpec, ...] = (
    EndingSpec(
        "E1",
        "遗忘之约",
        description_zh="选择摧毁源，让人类回到无源时代。一切与源有关的记忆、技术与可能性都将被彻底抹除——包括先驱文明留下的最后遗言。",
        epilogue_zh="岸线不再侵入。基地的传感器逐一熄灭，源矿脉深处的低吟归于死寂。\n\n"
                   "人类重新学会了在没有源的世界里生存。没有异常的同调反应，没有深夜的呼唤，没有若隐若现的先驱记忆。\n\n"
                   "卡伦的议会报告上写着「清理已完成」，但她在报告的最后一页留下了一行几乎看不见的铅笔字——「我们失去了什么？」\n\n"
                   "源纪元结束了。遗忘开始了。",
        tone_zh="悲剧、牺牲、沉重的平静",
    ),
    EndingSpec(
        "E2",
        "新伊甸",
        description_zh="修改源协议与核心指令，让人类与源共生进化，保留个体意识。这将是一条缓慢而孤独的道路，你将承受来自所有势力的敌意。",
        epilogue_zh="源开始回应一种新的频率——不是命令，不是控制，而是对话。\n\n"
                   "人类基因组的某些沉寂片段开始自行表达，但没有人失去自己。每个人仍然记得自己的名字。\n\n"
                   "议会切断了对基地的所有支援，回声集团将你列为头号威胁，净空会的刺客在路上了。\n\n"
                   "但在医务室里，一个从未开口的伤员忽然睁开眼睛，用他还不太习惯的嗓音说：「谢谢你没有放弃我们。」",
        tone_zh="希望、孤独、先驱者之路",
    ),
    EndingSpec(
        "E3",
        "神性监狱",
        description_zh="以自身接入源网络核心，成为维持人类与源交互的「活体服务器」。人类获得了前所未有的技术飞跃，但你从此失去了作为「人」的自由。",
        epilogue_zh="你的意识被分散到了源网络的每一个节点上。你能同时看到所有人的梦，但你不再有一个属于自己的身体。\n\n"
                   "林博士每天都会来指挥中心的终端前坐一会儿，对着屏幕上你留下的最后一句话发呆——「他们安全了。」\n\n"
                   "卡伦在终端旁放了一盆不知道从哪里弄来的植物，每周浇水。她从不解释为什么。\n\n"
                   "你知道她在。你知道所有人都在。但你只能用数据流中一闪而过的温暖来感知他们的存在。",
        tone_zh="崇高的牺牲、悲壮的囚禁、默默守护",
    ),
    EndingSpec(
        "E4",
        "统一寂静",
        description_zh="支持回声集团的神经同化方案。全人类的个体意识将被融合为统一的集体意识，在完美的和谐中——你将成为最后拥有自我的人。",
        epilogue_zh="世界变得无比安静。\n\n"
                   "所有人的眼睛都看向同一个方向，发出相同的梦中呓语。每一张嘴都在说同一句话，但你听不清那是什么。因为你是唯一还能「听」的人。\n\n"
                   "回声-7站在你身边，第一次摘下了面具。她的脸——是所有人的脸，也是没有人的脸。\n\n"
                   "「你自由了，」她说。「在所有失去自由的人当中，你是唯一自由的。」\n\n"
                   "你忽然意识到，那也许比所有人都失去自由更残酷。",
        tone_zh="恐怖、孤独、完美中的空虚",
    ),
    EndingSpec(
        "E5",
        "循环继续",
        description_zh="协助曙光议会重置时间线。源纪元将进入新一轮循环，所有人的记忆被再次清洗——包括你自己的。下一次醒来，一切从头开始。",
        epilogue_zh="然后是光。\n\n"
                   "你睁开眼睛，发现自己站在一座陌生的基地门口。天空是熟悉的铁灰色，空气中有一股你叫不出名字的焦糊味。\n\n"
                   "一个女人向你走来，伸出手：「指挥官，欢迎来到前线基地。我是安全官卡伦。」\n\n"
                   "她的手和你握在一起时，你感到一阵莫名的心悸。就像你在某个已经消散的梦中，曾经紧紧地握过这只手。\n\n"
                   "但你什么都想不起来了。\n\n"
                   "源纪元第 231 年。循环重新开始。",
        tone_zh="循环、遗憾、似曾相识的悲伤",
    ),
    EndingSpec(
        "E6",
        "净空",
        description_zh="引爆所有源矿脉，彻底断绝源的影响。代价是一场生态灾难——土地焦化、作物枯萎，人类将退回农耕时代从头来过。",
        epilogue_zh="天空被源矿引爆的尘埃遮蔽了整整三个月。\n\n"
                   "当阳光终于重新穿透尘雾时，基地周围的土地已经变了颜色——不是源矿脉那种诡异的荧光绿，而是普通的、灰褐色的泥土。\n\n"
                   "人们开始学着在没有源的世界里种地。林博士翻出了两百年前的农学教科书。卡伦在处理第一起因为争抢种子而发生的斗殴。\n\n"
                   "没有人再能听见源的低语了。\n\n"
                   "在一个深夜里，小胖蹲在废弃的监听站废墟前，拿起了一块曾经用来监听源信号的耳机。里面什么声音都没有。他笑了——然后哭了。",
        tone_zh="重获自由、代价沉重、质朴的希望",
    ),
    EndingSpec(
        "E7",
        "先驱之路",
        description_zh="将意识完全融入源，成为新的源核心。你不再是一个「人」，而是成为了共鸣网络本身——等待下一个宇宙轮回中的觉醒者。",
        epilogue_zh="你的感知超越了空间与时间。你看到宇宙的过去像一卷展开的地毯，未来像一枚正在碎裂的水晶。\n\n"
                   "所有死去的人类、所有曾经存在过的个体意识，他们的记忆都在你体内流动——不是存储，而是活着。\n\n"
                   "在某个遥远的未来，在另一颗行星的荒原上，一个从未见过人类文明的少年抬起头，第一次「听」到了你。\n\n"
                   "「你是谁？」那个意识问。\n\n"
                   "你用你曾是人类时学会的第一个词回答——「我们。」",
        tone_zh="超越、永恒、宇宙尺度的传承",
    ),
    EndingSpec(
        "E8",
        "真正的救赎",
        description_zh="让源自我终结，并公开先驱文明的全部知识。人类将摆脱源的束缚，以真正的自由意志走上自主进化之路。这是先驱们设计了 230 年的终点。",
        epilogue_zh="源消散的那一天，所有人的脑海中同时浮现出一句话——那是先驱文明留下的最后一条信息：\n\n"
                   "「我们不值得被崇拜，也不值得被畏惧。我们不过是比你们早走了几步的旅人。现在这条路是你们的了。」\n\n"
                   "议会解散了。回声集团的董事们递交了集体辞呈。净空会的剩余成员在废墟上种下了一棵树。\n\n"
                   "卡伦走到你身边，没有敬礼，而是轻轻地牵住了你的手。她没有说话。你已经不需要她说什么了。\n\n"
                   "远处的天际线上，朝阳正在升起——那是一个没有源矿脉荧光的、普通的、自由的太阳。",
        tone_zh="真正的自由、和解、新的开始",
        hidden=True,
    ),
)


def available_endings(v: PlayerHiddenVars) -> list[EndingSpec]:
    """矩阵「必要条件 / 排除条件」筛出 FIN-02 可选结局。"""
    out: list[EndingSpec] = []

    if (v.INCURSION > 60 or v.HUMAN < 30) and v.INSIGHT <= 50:
        out.append(ENDING_CATALOG[0])

    faction_max = max(v.COUNCIL, v.PURIFY, v.ECHO)
    if v.SYNC > 60 and v.HUMAN > 50 and faction_max <= 70:
        out.append(ENDING_CATALOG[1])

    if v.SYNC > 80 and v.COUNCIL > 60 and v.HUMAN <= 60:
        out.append(ENDING_CATALOG[2])

    if v.ECHO > 70 and v.HUMAN < 40 and v.PURIFY <= 30:
        out.append(ENDING_CATALOG[3])

    if v.COUNCIL > 70 and v.RESET <= 1:
        out.append(ENDING_CATALOG[4])

    if v.PURIFY > 60 and v.INCURSION > 50 and v.SYNC <= 40:
        out.append(ENDING_CATALOG[5])

    if v.SYNC > 90 and v.INSIGHT > 80:
        out.append(ENDING_CATALOG[6])

    if (
        v.INSIGHT > 80
        and v.HUMAN > 70
        and v.SYNC > 60
        and v.COUNCIL < 30
        and v.PURIFY < 30
        and v.ECHO < 30
    ):
        out.append(ENDING_CATALOG[7])

    seen: set[str] = set()
    uniq: list[EndingSpec] = []
    for e in out:
        if e.id not in seen:
            seen.add(e.id)
            uniq.append(e)
    return uniq
