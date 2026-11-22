"""抽核席位编排。

栏目用语料清单（desk.json 的 slots）安排每个拟发表变化的抽核席位：
- 两个月、关键学科都要见证据；有效候选不足时明确缺哪一格；
- 同一篇 work 不能同时充当两个变化的独立抽核证据（全局占用）；
- 语义未决的文献只进人审队列，不能充当确定证据占满席位；
- 复核改变词义后重新协调：工作稿趋势与席位占用一起重算。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .corpus import Corpus
from .models import EditionStatus, SeatAssignment, Sighting, SightingStatus


@dataclass(frozen=True)
class SlotSpec:
    slot_id: str
    sense_id: str
    priority: int
    month: str
    field: str
    seats: int


@dataclass
class AuditPlan:
    assignments: list[SeatAssignment]
    review_queue: list[Sighting]
    missing_cells: list[str]
    excluded_works: tuple[str, ...]

    def by_sense(self, sense_id: str) -> list[SeatAssignment]:
        return [a for a in self.assignments if a.sense_id == sense_id]

    def occupied_works(self) -> set[str]:
        return {a.work_id for a in self.assignments if a.work_id}


def load_slots(path: str | Path) -> list[SlotSpec]:
    slots: list[SlotSpec] = []
    for row in json.loads(Path(path).read_text(encoding="utf-8")):
        if row.get("kind") != "slots":
            continue
        for month, fld, seats in row["cells"]:
            slots.append(SlotSpec(
                slot_id=row["id"],
                sense_id=row["sense"],
                priority=int(row["priority"]),
                month=month,
                field=fld,
                seats=int(seats),
            ))
    return slots


def _eligible(sightings_by_edition: dict[str, list[Sighting]],
              sense_id: str, month: str, fld: str,
              blocked_works: set[str], corpus: Corpus) -> list[Sighting]:
    out: list[Sighting] = []
    for sightings in sightings_by_edition.values():
        for s in sightings:
            if s.month != month or s.field != fld:
                continue
            if s.status != SightingStatus.CONFIRMED or s.sense_id != sense_id:
                continue
            if s.work_id in blocked_works:
                continue
            # 只有当前有效版本能充当抽核证据：更正取代件与撤回件排除
            edition = corpus.edition(s.edition_id)
            if corpus.status_of(edition) != EditionStatus.CURRENT:
                continue
            out.append(s)
    # 确定性顺序：先收先排（edition 再片段位置），保证重跑结果稳定
    out.sort(key=lambda s: (s.edition_id, s.start))
    return out


def _review_queue(sightings_by_edition: dict[str, list[Sighting]],
                  corpus: Corpus) -> list[Sighting]:
    queue = [s for sightings in sightings_by_edition.values()
             for s in sightings if s.status == SightingStatus.AMBIGUOUS]
    queue = [s for s in queue
             if corpus.status_of(corpus.edition(s.edition_id))
             == EditionStatus.CURRENT]
    queue.sort(key=lambda s: (s.month, s.edition_id, s.start))
    return queue


def build_audit_plan(slots: list[SlotSpec],
                     sightings_by_edition: dict[str, list[Sighting]],
                     corpus: Corpus,
                     excluded_works: tuple[str, ...] = ()) -> AuditPlan:
    assignments: list[SeatAssignment] = []
    blocked: set[str] = set(excluded_works)
    missing: list[str] = []

    for slot in sorted(slots, key=lambda x: (x.priority, x.slot_id, x.month)):
        candidates = _eligible(sightings_by_edition, slot.sense_id,
                               slot.month, slot.field, blocked, corpus)
        for index in range(slot.seats):
            if index < len(candidates):
                chosen = candidates[index]
                blocked.add(chosen.work_id)  # 全局独占，其他变化不能再用
                assignments.append(SeatAssignment(
                    slot_id=slot.slot_id,
                    sense_id=slot.sense_id,
                    month=slot.month,
                    field=slot.field,
                    seat_index=index + 1,
                    edition_id=chosen.edition_id,
                    work_id=chosen.work_id,
                    sighting_id=chosen.sighting_id,
                    decision_id=chosen.decision_id,
                    note=("经编辑复核确认" if chosen.decision_id
                          else "资源线索唯一，扫描确认"),
                ))
            else:
                any_candidate = _eligible(sightings_by_edition, slot.sense_id,
                                          slot.month, slot.field,
                                          set(excluded_works), corpus)
                missing.append(
                    f"缺席：{slot.sense_id} 在 {slot.month} / {slot.field} "
                    f"第 {index + 1} 席无有效确定证据"
                    + ("（候选文献被其他变化的席位占用）" if any_candidate
                       else "（存疑文献已送人审或证据已失效，不能占确定席位）"))
                assignments.append(SeatAssignment(
                    slot_id=slot.slot_id,
                    sense_id=slot.sense_id,
                    month=slot.month,
                    field=slot.field,
                    seat_index=index + 1,
                    edition_id=None,
                    work_id=None,
                    sighting_id=None,
                    decision_id=None,
                    note="席位空缺",
                ))

    return AuditPlan(
        assignments=assignments,
        review_queue=_review_queue(sightings_by_edition, corpus),
        missing_cells=missing,
        excluded_works=tuple(sorted(excluded_works)),
    )


def recoordinate(slots: list[SlotSpec],
                 sightings_by_edition: dict[str, list[Sighting]],
                 corpus: Corpus,
                 excluded_works: tuple[str, ...] = ()) -> AuditPlan:
    """编辑复核一处词义后的重新协调入口：趋势由 compare 重算，
    席位由本函数按最新确认结果整体重排（旧决定不会被新席位冒领）。"""
    return build_audit_plan(slots, sightings_by_edition, corpus,
                            excluded_works)
