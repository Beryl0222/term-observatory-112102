"""月份比较：同一份现行词表、相同的学科×文种覆盖下做两月对比。

规则对应编辑部要求：
- 两个月都按本次采用的义项范围重扫，旧口径留在出刊快照里解释；
- 分母是各月交齐且两边都覆盖的语料格中的有效文献（按 work 去重）；
- 交集为空时明确“不能比较”，不产出趋势数字；
- 存疑片段不给零：每个义项给出 low（确定证据）与 high（确定+未决归属）
  的文献区间；概念合计按 work 去重，同一篇不会在两个义项间重复计入。
"""

from __future__ import annotations

from .corpus import Corpus
from .models import (
    ComparisonResult,
    MonthStat,
    Sighting,
    SightingStatus,
    SenseTrend,
)
from .registry import Registry


def _study_sightings(work_id: str, current_editions: list[str],
                     sightings_by_edition: dict[str, list[Sighting]]
                     ) -> list[Sighting]:
    out: list[Sighting] = []
    for edition_id in current_editions:
        for sighting in sightings_by_edition.get(edition_id, []):
            if sighting.work_id != work_id:
                continue
            if sighting.status in (SightingStatus.CONFIRMED,
                                   SightingStatus.AMBIGUOUS):
                out.append(sighting)
    return out


def _month_stats(month: str, works: tuple[str, ...], corpus: Corpus,
                 sightings_by_edition: dict[str, list[Sighting]],
                 sense_ids: tuple[str, ...]) -> tuple[
        dict[str, MonthStat], MonthStat]:
    current_map = {w: [e.edition_id for e in corpus.current_editions(w)]
                   for w in works}
    low_by_sense: dict[str, set[str]] = {s: set() for s in sense_ids}
    high_by_sense: dict[str, set[str]] = {s: set() for s in sense_ids}
    pending: set[str] = set()

    for work_id, edition_ids in current_map.items():
        study = _study_sightings(work_id, edition_ids, sightings_by_edition)
        confirmed_senses = {s.sense_id for s in study
                            if s.status == SightingStatus.CONFIRMED}
        ambiguous_senses: set[str] = set()
        for s in study:
            if s.status == SightingStatus.AMBIGUOUS:
                ambiguous_senses.update(s.candidate_senses)
                pending.add(work_id)
        for sid in sense_ids:
            if sid in confirmed_senses:
                low_by_sense[sid].add(work_id)
                high_by_sense[sid].add(work_id)
            elif sid in ambiguous_senses:
                high_by_sense[sid].add(work_id)

    stats: dict[str, MonthStat] = {}
    for sid in sense_ids:
        stats[sid] = MonthStat(
            month=month,
            denominator=len(works),
            low_works=tuple(sorted(low_by_sense[sid])),
            high_works=tuple(sorted(high_by_sense[sid])),
            pending_works=tuple(sorted(pending & high_by_sense[sid])),
        )

    concept_low = set().union(*low_by_sense.values())
    concept_high = set().union(*high_by_sense.values())
    concept = MonthStat(
        month=month,
        denominator=len(works),
        low_works=tuple(sorted(concept_low)),
        high_works=tuple(sorted(concept_high)),
        pending_works=tuple(sorted(pending)),
    )
    return stats, concept


def compare_months(month_a: str, month_b: str, corpus: Corpus,
                   registry: Registry,
                   sightings_by_edition: dict[str, list[Sighting]]
                   ) -> ComparisonResult:
    version = registry.latest()  # 两月同口径：统一采用现行版本
    sense_ids = tuple(s.sense_id for s in version.senses)
    shared = corpus.shared_complete_cells(month_a, month_b)

    if not shared:
        return ComparisonResult(
            month_a=month_a,
            month_b=month_b,
            comparable=False,
            reason=("两个月交齐的学科×文种没有交集，无法在相同覆盖下比较；"
                    "请先补齐供数方回执"),
            shared_cells=(),
            excluded_cells={
                month_a: tuple(sorted(corpus.complete_cells(month_a))),
                month_b: tuple(sorted(corpus.complete_cells(month_b))),
            },
            denominators={month_a: 0, month_b: 0},
            sense_trends={},
            concept_trend=SenseTrend(
                sense_id=version.parent,
                stats={},
                delta_low=0,
                delta_high=0,
            ),
            out_of_scope_works=(),
        )

    works_a = corpus.valid_works(month_a, shared)
    works_b = corpus.valid_works(month_b, shared)
    stats_a, concept_a = _month_stats(month_a, works_a, corpus,
                                      sightings_by_edition, sense_ids)
    stats_b, concept_b = _month_stats(month_b, works_b, corpus,
                                      sightings_by_edition, sense_ids)

    trends: dict[str, SenseTrend] = {}
    for sid in sense_ids:
        trends[sid] = SenseTrend(
            sense_id=sid,
            stats={month_a: stats_a[sid], month_b: stats_b[sid]},
            delta_low=stats_b[sid].low - stats_a[sid].low,
            delta_high=stats_b[sid].high - stats_a[sid].high,
        )
    concept_trend = SenseTrend(
        sense_id=version.parent,
        stats={month_a: concept_a, month_b: concept_b},
        delta_low=concept_b.low - concept_a.low,
        delta_high=concept_b.high - concept_a.high,
    )

    in_scope = set(works_a) | set(works_b)
    all_works = {w for w in corpus.work_ids()}
    out_of_scope = tuple(sorted(
        w for w in all_works
        if corpus.month_of(w) in (month_a, month_b) and w not in in_scope
    ))

    return ComparisonResult(
        month_a=month_a,
        month_b=month_b,
        comparable=True,
        reason=None,
        shared_cells=tuple(sorted(shared)),
        excluded_cells={
            month_a: tuple(sorted(corpus.excluded_cells(month_a, shared))),
            month_b: tuple(sorted(corpus.excluded_cells(month_b, shared))),
        },
        denominators={month_a: len(works_a), month_b: len(works_b)},
        sense_trends=trends,
        concept_trend=concept_trend,
        out_of_scope_works=out_of_scope,
    )
