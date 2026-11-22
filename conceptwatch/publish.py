"""出刊快照与读者视图。

- 出刊时冻结词表版本、分母、趋势区间与抽核席位，之后语料再变化也不改旧刊；
- 历史 bulletin 只保留限期元数据，打开时回到当时的旧口径，并结合当前语料
  标注哪些证据现已不可用；
- 撤回件原文不再展示，旧刊仍能解释当时如何计入。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .audit import AuditPlan
from .compare import ComparisonResult
from .corpus import Corpus
from .models import EditionStatus
from .registry import Registry


@dataclass
class IssueSnapshot:
    title: str
    released: str
    registry_id: str
    parent: str
    month_a: str
    month_b: str
    shared_cells: tuple[tuple[str, str], ...]
    denominators: dict[str, int]
    sense_trends: dict[str, dict[str, Any]]
    concept_trend: dict[str, Any]
    audit: list[dict[str, Any]]
    review_queue: list[dict[str, Any]]
    missing_cells: list[str]


def freeze_issue(title: str, released: str, registry: Registry,
                 comparison: ComparisonResult,
                 audit_plan: AuditPlan) -> IssueSnapshot:
    def stat_dict(month: str, st) -> dict[str, Any]:
        return {
            "denominator": st.denominator,
            "low": st.low,
            "high": st.high,
            "low_works": list(st.low_works),
            "high_works": list(st.high_works),
            "pending_works": list(st.pending_works),
        }

    sense_trends: dict[str, dict[str, Any]] = {}
    for sid, trend in comparison.sense_trends.items():
        sense_trends[sid] = {
            "delta_low": trend.delta_low,
            "delta_high": trend.delta_high,
            "months": {m: stat_dict(m, st)
                       for m, st in trend.stats.items()},
        }
    concept = comparison.concept_trend
    return IssueSnapshot(
        title=title,
        released=released,
        registry_id=registry.latest().registry_id,
        parent=registry.latest().parent,
        month_a=comparison.month_a,
        month_b=comparison.month_b,
        shared_cells=comparison.shared_cells,
        denominators=dict(comparison.denominators),
        sense_trends=sense_trends,
        concept_trend={
            "delta_low": concept.delta_low,
            "delta_high": concept.delta_high,
            "months": {m: stat_dict(m, st)
                       for m, st in concept.stats.items()},
        },
        audit=[
            {
                "sense_id": a.sense_id,
                "month": a.month,
                "field": a.field,
                "seat": a.seat_index,
                "work_id": a.work_id,
                "edition_id": a.edition_id,
                "sighting_id": a.sighting_id,
                "decision_id": a.decision_id,
                "note": a.note,
            }
            for a in audit_plan.assignments
        ],
        review_queue=[
            {
                "work_id": s.work_id,
                "edition_id": s.edition_id,
                "snippet": s.snippet,
                "candidate_senses": list(s.candidate_senses),
                "reasons": list(s.reasons),
            }
            for s in audit_plan.review_queue
        ],
        missing_cells=list(audit_plan.missing_cells),
    )


def load_historical_bulletins(path: str | Path) -> list[dict]:
    return [row for row in json.loads(Path(path).read_text(encoding="utf-8"))
            if row.get("kind") == "bulletin"]


def explain_historical(bulletin: dict, corpus: Corpus,
                       registry: Registry) -> dict[str, Any]:
    """打开旧刊：保留当时口径与计数，并逐条标注证据现状。

    读者不会再看到撤回原文；被更正的版本标注“已被取代”，
    同时说明其他文种证据是否仍然有效。
    """
    legacy = registry.get(bulletin["lexicon"])
    entries: list[dict[str, Any]] = []
    for edition_id in bulletin["editions"]:
        edition = corpus.edition(edition_id)
        status = corpus.status_of(edition)
        entry: dict[str, Any] = {
            "edition_id": edition_id,
            "work_id": edition.work_id,
            "status_at_release": "计入",
            "current_status": status.value,
            "text_visible": corpus.visible_text(edition_id) is not None,
        }
        if status == EditionStatus.RETRACTED:
            entry["evidence_note"] = (
                "该文种已被撤回，原文不再展示；旧刊当时按有效证据计入，"
                "现标记为证据不可用")
        elif status == EditionStatus.SUPERSEDED:
            current = [e for e in corpus.current_editions(edition.work_id)
                       if e.language == edition.language]
            entry["evidence_note"] = (
                "该版本已被同文种更正版取代，其证据不再有效；"
                + (f"更正版 {current[0].edition_id} 的扫描结果另行计入"
                   if current else "且无后续有效版本"))
        else:
            entry["evidence_note"] = "证据仍有效"
        entries.append(entry)

    return {
        "bulletin_id": bulletin["id"],
        "released": bulletin["released"],
        "legacy_registry": {
            "id": legacy.registry_id,
            "month": legacy.month,
            "parent": legacy.parent,
            "senses": [
                {"sense_id": s.sense_id, "notes": s.notes}
                for s in legacy.senses
            ],
        },
        "basis": bulletin["basis"],
        "published_ratios": dict(bulletin["ratios"]),
        "work_refs": list(bulletin["work_refs"]),
        "evidence_entries": entries,
    }
