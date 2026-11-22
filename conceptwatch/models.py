"""核心数据类与枚举。标识规则集中在此，避免各模块各自造 ID。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Optional


class UsageType(str, Enum):
    """文献自身对术语的使用方式。只有 STUDY 可计入证据。"""

    STUDY = "study"        # 本文自身研究中使用
    NEGATED = "negated"    # 否定用法（考虑过但未做、并未用于……）
    REPORTED = "reported"  # 仅转述/引用其他研究


class SightingStatus(str, Enum):
    CONFIRMED = "confirmed"  # 义项已确定（含编辑复核决定）
    AMBIGUOUS = "ambiguous"  # 义项存疑，候选见 candidate_senses
    NEGATED = "negated"
    REPORTED = "reported"


class EditionStatus(str, Enum):
    CURRENT = "current"        # 该文种当前有效版本
    SUPERSEDED = "superseded"  # 被同文种更大 serial 的重发取代
    RETRACTED = "retracted"    # 该文种被撤回（原文不再展示）


class DecisionState(str, Enum):
    ACTIVE = "active"  # 指向的片段仍存在且证据有效
    STALE = "stale"    # 原件被更正/撤回或片段消失，决定留档但不再套用


@dataclass(frozen=True)
class Sense:
    sense_id: str
    aliases: tuple[str, ...]
    notes: str


@dataclass(frozen=True)
class RegistryVersion:
    """词表的一个生效月版本。parent 相同的连续版本构成概念谱系。"""

    registry_id: str
    month: str
    parent: str
    senses: tuple[Sense, ...]


@dataclass(frozen=True)
class Edition:
    """一份摘要传输记录（一个文种的一个 serial）。"""

    edition_id: str
    work_id: str
    month: str
    serial: int
    language: str
    field: str
    text: str
    received_at: str
    retracted: bool

    @property
    def cell(self) -> tuple[str, str]:
        return self.field, self.language


@dataclass
class Sighting:
    """一次术语出现及其解释。sighting_id 由原件 ID 与字符区间确定性生成，
    重复扫描保持稳定，编辑决定据此挂接，不会冒领到别的片段。"""

    sighting_id: str
    edition_id: str
    work_id: str
    month: str
    field: str
    language: str
    registry_id: str
    surface: str
    start: int
    end: int
    snippet: str
    sentence: str
    usage: UsageType
    status: SightingStatus
    candidate_senses: tuple[str, ...]
    sense_id: Optional[str]
    cues: dict[str, tuple[str, ...]]
    reasons: tuple[str, ...]
    decision_id: Optional[str] = None

    @staticmethod
    def make_id(edition_id: str, start: int, end: int, surface: str) -> str:
        return f"{edition_id}#{start}-{end}:{surface}"

    def with_decision(self, decision_id: str, sense_id: str) -> "Sighting":
        return replace(
            self,
            status=SightingStatus.CONFIRMED,
            sense_id=sense_id,
            decision_id=decision_id,
            reasons=self.reasons + (f"编辑复核 {decision_id} 判定为 {sense_id}",),
        )


@dataclass
class EditorialDecision:
    decision_id: str
    work_id: str
    edition_id: str
    sense_id: str
    note: str
    state: DecisionState = DecisionState.ACTIVE
    stale_reason: Optional[str] = None
    sighting_ids: tuple[str, ...] = ()


@dataclass
class SeatAssignment:
    """一个抽核席位的编排结果。"""

    slot_id: str
    sense_id: str
    month: str
    field: str
    seat_index: int
    edition_id: Optional[str]      # None 表示席位空缺
    work_id: Optional[str]
    sighting_id: Optional[str]
    decision_id: Optional[str]
    note: str = ""


@dataclass
class MonthStat:
    month: str
    denominator: int
    low_works: tuple[str, ...]
    high_works: tuple[str, ...]
    pending_works: tuple[str, ...]

    @property
    def low(self) -> int:
        return len(self.low_works)

    @property
    def high(self) -> int:
        return len(self.high_works)


@dataclass
class SenseTrend:
    sense_id: str
    stats: dict[str, MonthStat]
    delta_low: int
    delta_high: int

    def rate_low(self, month: str) -> Optional[float]:
        st = self.stats[month]
        return None if st.denominator == 0 else st.low / st.denominator

    def rate_high(self, month: str) -> Optional[float]:
        st = self.stats[month]
        return None if st.denominator == 0 else st.high / st.denominator


@dataclass
class ComparisonResult:
    month_a: str
    month_b: str
    comparable: bool
    reason: Optional[str]
    shared_cells: tuple[tuple[str, str], ...]
    excluded_cells: dict[str, tuple[tuple[str, str], ...]]
    denominators: dict[str, int]
    sense_trends: dict[str, SenseTrend]
    concept_trend: SenseTrend
    out_of_scope_works: tuple[str, ...]
