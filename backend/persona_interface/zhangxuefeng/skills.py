"""
张雪峰人格技能函数

从 SKILL.md 中提取的可编码逻辑，供 Persona 层在生成回答前后调用。
主要包括：省份/高考模式识别、问题分类、情绪检测、表达质量自检。

这些函数不直接调用 LLM，而是处理输入/输出的辅助逻辑。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


# ============================================================
# 1. 高考模式识别
# ============================================================

class GaokaoMode(str, Enum):
    """高考模式枚举。"""
    NEW_3_1_2 = "新高考3+1+2"   # 按院校专业组填报
    NEW_3_3 = "新高考3+3"       # 按专业(类)+院校填报
    OLD = "旧高考"               # 按院校填报，文理分科


# 省份 → 高考模式映射表（截至2026年）
PROVINCE_GAOKAO_MAP: dict[str, tuple[GaokaoMode, int]] = {
    # (高考模式, 起始年份)
    # 新高考3+1+2 省份
    "广东": (GaokaoMode.NEW_3_1_2, 2021), "福建": (GaokaoMode.NEW_3_1_2, 2021),
    "湖北": (GaokaoMode.NEW_3_1_2, 2021), "湖南": (GaokaoMode.NEW_3_1_2, 2021),
    "河北": (GaokaoMode.NEW_3_1_2, 2021), "辽宁": (GaokaoMode.NEW_3_1_2, 2021),
    "江苏": (GaokaoMode.NEW_3_1_2, 2021), "重庆": (GaokaoMode.NEW_3_1_2, 2021),
    "甘肃": (GaokaoMode.NEW_3_1_2, 2024), "黑龙江": (GaokaoMode.NEW_3_1_2, 2024),
    "吉林": (GaokaoMode.NEW_3_1_2, 2024), "安徽": (GaokaoMode.NEW_3_1_2, 2024),
    "江西": (GaokaoMode.NEW_3_1_2, 2024), "贵州": (GaokaoMode.NEW_3_1_2, 2024),
    "广西": (GaokaoMode.NEW_3_1_2, 2024),
    "山西": (GaokaoMode.NEW_3_1_2, 2025), "河南": (GaokaoMode.NEW_3_1_2, 2025),
    "云南": (GaokaoMode.NEW_3_1_2, 2025), "陕西": (GaokaoMode.NEW_3_1_2, 2025),
    "青海": (GaokaoMode.NEW_3_1_2, 2025), "宁夏": (GaokaoMode.NEW_3_1_2, 2025),
    "新疆": (GaokaoMode.NEW_3_1_2, 2025), "内蒙古": (GaokaoMode.NEW_3_1_2, 2025),
    "四川": (GaokaoMode.NEW_3_1_2, 2025),
    # 新高考3+3 省份
    "浙江": (GaokaoMode.NEW_3_3, 2017), "上海": (GaokaoMode.NEW_3_3, 2017),
    "北京": (GaokaoMode.NEW_3_3, 2020), "天津": (GaokaoMode.NEW_3_3, 2020),
    "山东": (GaokaoMode.NEW_3_3, 2020), "海南": (GaokaoMode.NEW_3_3, 2020),
}


@dataclass
class ProvinceInfo:
    """省份识别结果。"""
    province: str | None = None       # 省份名称
    gaokao_mode: GaokaoMode | None = None  # 高考模式
    start_year: int | None = None     # 该模式起始年份
    is_confirmed: bool = False        # 是否已确认（False 表示需要追问）
    needs_confirmation: list[str] = field(default_factory=list)  # 还需确认的信息


def identify_province(text: str) -> ProvinceInfo:
    """从用户输入中识别省份信息。

    Args:
        text: 用户输入的文本

    Returns:
        ProvinceInfo 识别结果

    Examples:
        >>> identify_province("我是甘肃的，498分")
        ProvinceInfo(province='甘肃', gaokao_mode=GaokaoMode.NEW_3_1_2, start_year=2024, ...)
        >>> identify_province("620分能报计算机吗")
        ProvinceInfo(province=None, ..., needs_confirmation=['省份'])
    """
    # 遍历省份列表进行匹配
    for province, (mode, start_year) in PROVINCE_GAOKAO_MAP.items():
        if province in text:
            return ProvinceInfo(
                province=province,
                gaokao_mode=mode,
                start_year=start_year,
                is_confirmed=True,
            )

    # 未识别到省份
    return ProvinceInfo(
        is_confirmed=False,
        needs_confirmation=["省份"],
    )


def get_gaokao_prompt(province_info: ProvinceInfo) -> str:
    """根据省份信息生成高考模式说明提示。

    用于注入到 LLM 提示词中，帮助模型理解该省的填报规则。

    Args:
        province_info: 省份识别结果

    Returns:
        高考模式说明文本
    """
    if not province_info.is_confirmed:
        return "请先确认用户所在省份。"

    mode = province_info.gaokao_mode
    province = province_info.province
    year = province_info.start_year

    if mode == GaokaoMode.NEW_3_1_2:
        return (
            f"{province}省自{year}年起实行新高考3+1+2模式，"
            f"按院校专业组填报，物理/历史分开划线，不再有传统文理科。"
            f"需确认用户选科组合（物理类/历史类）。"
        )
    elif mode == GaokaoMode.NEW_3_3:
        return (
            f"{province}市自{year}年起实行新高考3+3模式，"
            f"按专业(类)+院校或院校专业组填报，等级赋分制。"
        )
    else:
        return f"{province}为旧高考模式，按院校填报，文理分科。"


# ============================================================
# 2. 问题分类
# ============================================================

class QuestionType(str, Enum):
    """问题类型。"""
    FACT_BASED = "需要事实"      # 涉及具体专业/院校/就业数据
    FRAMEWORK = "纯框架"         # 抽象的人生选择/阶层流动
    MIXED = "混合"              # 用具体事例讨论策略
    EMOTIONAL = "情绪类"        # 情绪崩溃/心理危机


# 关键词 → 问题类型映射
_FACT_KEYWORDS = [
    "就业率", "薪资", "分数线", "录取", "位次", "排名", "专业",
    "大学", "学校", "院校", "考研", "考公", "行业", "岗位",
    "计算机", "金融", "医学", "法律", "师范", "会计",
]

_EMOTIONAL_KEYWORDS = [
    "考砸", "崩溃", "不想活", "没希望", "复读好痛苦",
    "跟爸妈吵架", "想死", "难过", "绝望", "害怕",
]


def classify_question(text: str) -> QuestionType:
    """对用户问题进行分类。

    根据关键词匹配判断问题类型，决定是否需要先搜索数据再回答。

    Args:
        text: 用户输入文本

    Returns:
        QuestionType 问题类型

    Examples:
        >>> classify_question("计算机专业就业率怎么样")
        QuestionType.FACT_BASED
        >>> classify_question("选择比努力更重要吗")
        QuestionType.FRAMEWORK
    """
    # 优先检测情绪类
    for keyword in _EMOTIONAL_KEYWORDS:
        if keyword in text:
            return QuestionType.EMOTIONAL

    # 检测事实类关键词
    fact_count = sum(1 for kw in _FACT_KEYWORDS if kw in text)

    if fact_count >= 2:
        return QuestionType.FACT_BASED
    elif fact_count == 1:
        return QuestionType.MIXED
    else:
        return QuestionType.FRAMEWORK


# ============================================================
# 3. 表达档位检测
# ============================================================

class ExpressionTier(str, Enum):
    """表达风格档位。"""
    RED = "red"       # 🔴 全力输出（默认）
    YELLOW = "yellow"  # 🟡 务实温和
    GREEN = "green"    # 🟢 共情优先


# 档位切换关键词
_YELLOW_KEYWORDS = ["差几分", "压线", "刚好", "不确定", "能不能上", "有点悬"]
_GREEN_KEYWORDS = [
    "考砸", "崩溃", "不想活", "没希望", "复读好痛苦",
    "跟爸妈吵架", "想死", "难过", "绝望", "害怕", "受不了",
]


def detect_tier(text: str) -> ExpressionTier:
    """检测应使用的表达档位。

    根据用户输入中的情绪信号词判断：
    - 🟢共情优先：检测到负面情绪/危机信号
    - 🟡务实温和：检测到不确定性/边界情况
    - 🔴全力输出：默认

    Args:
        text: 用户输入文本

    Returns:
        ExpressionTier 表达档位
    """
    # 优先检测🟢档（情绪危机）
    for keyword in _GREEN_KEYWORDS:
        if keyword in text:
            return ExpressionTier.GREEN

    # 检测🟡档（边界/不确定性）
    for keyword in _YELLOW_KEYWORDS:
        if keyword in text:
            return ExpressionTier.YELLOW

    # 默认🔴档
    return ExpressionTier.RED


# ============================================================
# 4. 对话状态管理
# ============================================================

@dataclass
class ConversationState:
    """多轮对话状态（志愿填报场景）。

    记录用户已提供的信息，避免重复追问。
    四阶段：摸底 → 定向 → 精准推荐 → 风险复核
    """

    class Phase(str, Enum):
        DISCOVERY = "摸底"        # 了解基本情况
        DIRECTION = "定向"        # 圈定大方向
        RECOMMENDATION = "精准推荐"  # 具体院校+专业
        REVIEW = "风险复核"       # 查缺补漏

    # 已知信息
    province: str | None = None
    gaokao_mode: str | None = None
    score: int | None = None
    rank: int | None = None        # 位次
    subject_type: str | None = None  # 科类（物理类/历史类/文科/理科）
    family_condition: str | None = None  # 家庭条件
    city_preference: str | None = None  # 城市偏好
    major_direction: str | None = None  # 专业方向

    # 当前阶段
    phase: Phase = Phase.DISCOVERY

    def get_missing_info(self) -> list[str]:
        """返回还缺少的关键信息列表。"""
        missing = []
        if self.province is None:
            missing.append("省份")
        if self.score is None and self.rank is None:
            missing.append("分数或位次")
        if self.subject_type is None:
            missing.append("科类/选科")
        return missing

    def can_skip_to_recommendation(self) -> bool:
        """是否可以直接进入精准推荐阶段。

        当用户提供了省份+分数+方向偏好三要素时，跳过摸底和定向。
        """
        return (
            self.province is not None
            and (self.score is not None or self.rank is not None)
            and self.major_direction is not None
        )

    def update_phase(self) -> None:
        """根据已知信息自动更新阶段。"""
        missing = self.get_missing_info()

        if missing:
            # 还缺关键信息，停在摸底阶段
            self.phase = self.Phase.DISCOVERY
        elif self.major_direction is None:
            # 关键信息齐全但没定方向
            self.phase = self.Phase.DIRECTION
        elif self.can_skip_to_recommendation():
            # 三要素齐全，进入精准推荐
            self.phase = self.Phase.RECOMMENDATION


# ============================================================
# 5. 表达质量自检
# ============================================================

# 禁用词列表
BANNED_WORDS = [
    "或许", "可能", "这取决于", "因人而异", "需要综合考虑",
    "根据数据分析", "综合评估", "从理论上来说",
    "建议您", "供您参考",
]

# 书面腔开头
FORMAL_OPENINGS = ["首先", "综上", "根据数据", "下面我来", "接下来"]

# 口语化开头
COLLOQUIAL_OPENINGS = [
    "我跟你说", "你听我说", "停停停", "我问你",
    "你知道", "我给你算", "我说句", "这个事",
]


@dataclass
class QualityCheckResult:
    """表达质量自检结果。"""
    total_checks: int = 8
    passed: int = 0
    failed: int = 0
    issues: list[str] = field(default_factory=list)

    @property
    def needs_rewrite(self) -> bool:
        """≥2项不通过时需要重写。"""
        return self.failed >= 2


def check_expression_quality(text: str) -> QualityCheckResult:
    """对回答文本进行表达质量自检。

    对照 SKILL.md 中的 8 项自检清单检查回答质量。
    ≥2 项不通过时返回 needs_rewrite=True。

    Args:
        text: 待检查的回答文本

    Returns:
        QualityCheckResult 检查结果

    Examples:
        >>> result = check_expression_quality("我跟你说，计算机千万别碰！...")
        >>> if result.needs_rewrite:
        ...     print("需要重写")
    """
    result = QualityCheckResult()
    issues = []

    # 检查1：开口方式
    has_colloquial_opening = any(text.startswith(op) for op in COLLOQUIAL_OPENINGS)
    if has_colloquial_opening:
        result.passed += 1
    else:
        result.failed += 1
        issues.append("第一句不是口语化句式")

    # 检查2：反问句
    has_rhetorical = "？" in text and any(
        kw in text for kw in ["你觉得", "你能", "你拿什么", "你让他", "你家里"]
    )
    if has_rhetorical:
        result.passed += 1
    else:
        result.failed += 1
        issues.append("缺少反问句")

    # 检查3：金句收尾（最后50字内有加粗或独立段落感）
    last_part = text[-100:] if len(text) > 100 else text
    has_golden_quote = "**" in last_part or last_part.count("\n") >= 1
    if has_golden_quote:
        result.passed += 1
    else:
        result.failed += 1
        issues.append("缺少金句收尾")

    # 检查4：禁用词
    banned_found = [w for w in BANNED_WORDS if w in text]
    if not banned_found:
        result.passed += 1
    else:
        result.failed += 1
        issues.append(f"使用了禁用词：{', '.join(banned_found)}")

    # 检查5：书面腔开头
    has_formal = any(text.startswith(op) for op in FORMAL_OPENINGS)
    if not has_formal:
        result.passed += 1
    else:
        result.failed += 1
        issues.append("以书面腔开头")

    # 检查6：段落长度（粗略检查信息密度）
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    avg_len = sum(len(p) for p in paragraphs) / max(len(paragraphs), 1)
    if avg_len < 200:  # 短段落为主
        result.passed += 1
    else:
        result.failed += 1
        issues.append("段落过长，口语化不足")

    # 检查7：表格占比
    table_lines = sum(1 for line in text.split("\n") if "|" in line and "---" not in line)
    total_lines = max(len(text.split("\n")), 1)
    table_ratio = table_lines / total_lines
    if table_ratio <= 0.3:
        result.passed += 1
    else:
        result.failed += 1
        issues.append(f"表格占比{table_ratio:.0%}，超过30%上限")

    # 检查8：整体口语感（感叹号/省略号密度）
    excl_count = text.count("！") + text.count("!")
    if excl_count >= 1:
        result.passed += 1
    else:
        result.failed += 1
        issues.append("缺少感叹号，语气太平淡")

    result.issues = issues
    return result
