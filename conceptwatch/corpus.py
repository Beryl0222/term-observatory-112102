"""语料库：文献身份、多文种版本、重发更正、撤回与交齐回执。

身份规则：
- work（文献 ID）在收录方重发时沿用；不同语言版本是同一 work 的不同 edition；
- 同一文种 serial 更大的重发取代旧版（SUPERSEDED），旧版留痕但不再是有效证据；
- retract 只撤回相应文种（RETRACTED），其他文种仍然有效；
- 一份更正不能抹掉另一文种仍然有效的证据。
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .models import Edition, EditionStatus


class Corpus:
    def __init__(self) -> None:
        self._editions: dict[str, Edition] = {}
        self._works: dict[str, list[str]] = defaultdict(list)
        self._complete_cells: dict[str, set[tuple[str, str]]] = defaultdict(set)

    # ---- 装载 -----------------------------------------------------------

    @classmethod
    def from_file(cls, path: str | Path, desk_path: str | Path | None = None) -> "Corpus":
        corpus = cls()
        rows = json.loads(Path(path).read_text(encoding="utf-8"))
        for row in rows:
            corpus.ingest(row)
        if desk_path is not None:
            for row in json.loads(Path(desk_path).read_text(encoding="utf-8")):
                if row.get("kind") == "receipt":
                    for field, language in row["complete"]:
                        corpus.mark_complete(row["month"], field, language)
        return corpus

    def ingest(self, row: dict) -> Edition:
        edition = Edition(
            edition_id=row["id"],
            work_id=row["work"],
            month=row["month"],
            serial=int(row["serial"]),
            language=row["language"],
            field=row["field"],
            text=row.get("text", "") or "",
            received_at=row.get("received_at", ""),
            retracted=bool(row.get("retract", False)),
        )
        if edition.edition_id in self._editions:
            raise ValueError(f"重复的传输记录 ID：{edition.edition_id}")
        self._editions[edition.edition_id] = edition
        self._works[edition.work_id].append(edition.edition_id)
        return edition

    def mark_complete(self, month: str, field: str, language: str) -> None:
        self._complete_cells[month].add((field, language))

    # ---- 基础查询 -------------------------------------------------------

    @property
    def editions(self) -> tuple[Edition, ...]:
        return tuple(self._editions.values())

    def edition(self, edition_id: str) -> Edition:
        return self._editions[edition_id]

    def work_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._works))

    def editions_of(self, work_id: str) -> tuple[Edition, ...]:
        return tuple(self._editions[i]
                     for i in sorted(self._works[work_id],
                                     key=lambda i: (self._editions[i].language,
                                                    self._editions[i].serial)))

    def month_of(self, work_id: str) -> str:
        months = {e.month for e in self.editions_of(work_id)}
        if len(months) != 1:
            raise ValueError(f"文献 {work_id} 跨归属月：{months}")
        return next(iter(months))

    def status_of(self, edition: Edition) -> EditionStatus:
        same_lang = [e for e in self.editions_of(edition.work_id)
                     if e.language == edition.language]
        later = [e for e in same_lang if e.serial > edition.serial]
        # 撤回通知（retract=true 的后续文种记录）会撤回此前的同一文种版本
        if edition.retracted or any(e.retracted for e in later):
            return EditionStatus.RETRACTED
        if later:  # 非撤回的更大 serial 即更正重发
            return EditionStatus.SUPERSEDED
        return EditionStatus.CURRENT

    def current_editions(self, work_id: str) -> tuple[Edition, ...]:
        """当前有效版本（每文种至多一份；被撤回或被取代的版本不出现）。"""
        return tuple(e for e in self.editions_of(work_id)
                     if self.status_of(e) == EditionStatus.CURRENT)

    def visible_text(self, edition_id: str) -> str | None:
        """读者视图：撤回件（含被撤回通知撤回的原件）原文不再可见。"""
        edition = self._editions[edition_id]
        if self.status_of(edition) == EditionStatus.RETRACTED:
            return None
        return edition.text

    def history(self, work_id: str) -> list[dict]:
        """完整版本史，供“旧版说了什么、为何被取代/撤回”回查。"""
        out = []
        for edition in self.editions_of(work_id):
            status = self.status_of(edition)
            out.append({
                "edition_id": edition.edition_id,
                "language": edition.language,
                "serial": edition.serial,
                "field": edition.field,
                "status": status.value,
                "text_visible": not edition.retracted,
                "received_at": edition.received_at,
            })
        return out

    # ---- 语料格与交齐 ---------------------------------------------------

    def complete_cells(self, month: str) -> set[tuple[str, str]]:
        return set(self._complete_cells.get(month, set()))

    def shared_complete_cells(self, month_a: str,
                              month_b: str) -> set[tuple[str, str]]:
        """两个月都交齐、两边都覆盖的学科×文种——比较口径的覆盖交集。"""
        return self.complete_cells(month_a) & self.complete_cells(month_b)

    def excluded_cells(self, month: str,
                       shared: set[tuple[str, str]]) -> set[tuple[str, str]]:
        return self.complete_cells(month) - shared

    def works_in_cells(self, month: str,
                       cells: set[tuple[str, str]]) -> tuple[str, ...]:
        out = set()
        for work_id in self._works:
            if self.month_of(work_id) != month:
                continue
            for edition in self.current_editions(work_id):
                if edition.cell in cells:
                    out.add(work_id)
                    break
        return tuple(sorted(out))

    def valid_works(self, month: str,
                    cells: set[tuple[str, str]]) -> tuple[str, ...]:
        """分母：交齐格内、当前仍有效（至少一个文种未撤回）的文献。"""
        return self.works_in_cells(month, cells)
