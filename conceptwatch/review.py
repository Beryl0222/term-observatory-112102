"""编辑复核台账与决定套用。

复核决定按 work+edition 登记，套用前先核对片段是否仍存在、证据是否仍有效：
- 决定指向的版本被更正或撤回 -> 决定置 STALE，留档可查但不再套用；
- 片段仍在才把 AMBIGUOUS 记录改为 CONFIRMED；
- 重新使用的席位拿到的是新片段新决定，不会冒领旧决定。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .corpus import Corpus
from .linguistics import find_sense_cues
from .models import (
    DecisionState,
    EditorialDecision,
    EditionStatus,
    Sighting,
    SightingStatus,
)
from .registry import Registry


@dataclass
class DecisionReport:
    applied: list[EditorialDecision]
    stale: list[tuple[EditorialDecision, str]]


class ReviewLedger:
    def __init__(self) -> None:
        self._decisions: dict[str, EditorialDecision] = {}

    @classmethod
    def from_file(cls, path: str | Path, registry: Registry) -> "ReviewLedger":
        """desk.json 的复核账只写自然语言结论，义项按与扫描相同的资源线索
        从复核文本中推断，保证编辑与机器使用同一套语言习惯。"""
        ledger = cls()
        version = registry.latest()
        sense_ids = [s.sense_id for s in version.senses]
        rows = json.loads(Path(path).read_text(encoding="utf-8"))
        for row in rows:
            if row.get("kind") != "review":
                continue
            if "sense_override" in row:
                sense_id = row["sense_override"]
            else:
                hits = find_sense_cues(row.get("text", ""), sense_ids, "zh")
                if len(hits) != 1:
                    raise ValueError(
                        f"复核记录 {row['id']} 的义项无法唯一推断：{hits}")
                sense_id = next(iter(hits))
            ledger.add(EditorialDecision(
                decision_id=row["id"],
                work_id=row["work"],
                edition_id=row["edition"],
                sense_id=sense_id,
                note=row.get("text", ""),
            ))
        return ledger

    def add(self, decision: EditorialDecision) -> None:
        if decision.decision_id in self._decisions:
            raise ValueError(f"重复的复核决定 ID：{decision.decision_id}")
        self._decisions[decision.decision_id] = decision

    @property
    def decisions(self) -> tuple[EditorialDecision, ...]:
        return tuple(self._decisions.values())

    def get(self, decision_id: str) -> EditorialDecision:
        return self._decisions[decision_id]

    def for_work(self, work_id: str) -> tuple[EditorialDecision, ...]:
        return tuple(d for d in self._decisions.values()
                     if d.work_id == work_id)

    def apply(self, sightings_by_edition: dict[str, list[Sighting]],
              corpus: Corpus) -> DecisionReport:
        """把有效决定套用到扫描结果，返回套用/失效报告。原地更新 sighting。"""
        applied: list[EditorialDecision] = []
        stale: list[tuple[EditorialDecision, str]] = []
        for decision in self._decisions.values():
            edition = corpus.edition(decision.edition_id)
            status = corpus.status_of(edition)
            if status in (EditionStatus.SUPERSEDED, EditionStatus.RETRACTED):
                reason = {
                    "superseded": "原件已被同文种更正版取代",
                    "retracted": "原件已被撤回，原文不再可见",
                }[status.value]
                decision.state = DecisionState.STALE
                decision.stale_reason = reason
                stale.append((decision, reason))
                continue
            # 可挂接的研究性片段：存疑记录改判；与决定同义项的已确认记录
            # 表示编辑认可扫描结论，同样挂接以便席位溯源。
            targets = [
                s for s in sightings_by_edition.get(decision.edition_id, [])
                if s.work_id == decision.work_id
                and s.status in (SightingStatus.AMBIGUOUS,
                                 SightingStatus.CONFIRMED)
                and (s.status == SightingStatus.AMBIGUOUS
                     or s.sense_id == decision.sense_id)
            ]
            if not targets:
                decision.state = DecisionState.STALE
                decision.stale_reason = "当前文本中没有可套用的对应片段"
                stale.append((decision, decision.stale_reason))
                continue
            touched: list[str] = []
            for sighting in targets:
                if sighting.status == SightingStatus.CONFIRMED:
                    updated = sighting.with_decision(decision.decision_id,
                                                     sighting.sense_id)
                else:
                    updated = sighting.with_decision(decision.decision_id,
                                                     decision.sense_id)
                idx = sightings_by_edition[decision.edition_id].index(sighting)
                sightings_by_edition[decision.edition_id][idx] = updated
                touched.append(updated.sighting_id)
            decision.state = DecisionState.ACTIVE
            decision.sighting_ids = tuple(touched)
            applied.append(decision)
        return DecisionReport(applied=applied, stale=stale)
