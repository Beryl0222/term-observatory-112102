"""词表登记：版本、义项索引、别名解析与拆分谱系。

同一写法在多个义项登记时解析为多个候选（如“织网”可指算力或电网协同）；
只在单个义项登记的写法为强写法（如“柔性织网”）。
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .models import RegistryVersion, Sense


class Registry:
    def __init__(self, versions: list[RegistryVersion]):
        self._versions = sorted(versions, key=lambda v: v.month)
        self._by_id = {v.registry_id: v for v in self._versions}
        self._by_month: dict[str, list[RegistryVersion]] = defaultdict(list)
        for v in self._versions:
            self._by_month[v.month].append(v)

    # ---- 构造与加载 -----------------------------------------------------

    @classmethod
    def from_file(cls, path: str | Path) -> "Registry":
        rows = json.loads(Path(path).read_text(encoding="utf-8"))
        versions: list[RegistryVersion] = []
        for row in rows:
            senses = tuple(
                Sense(
                    sense_id=s["sense"],
                    aliases=tuple(s["aliases"]),
                    notes=s["notes"],
                )
                for s in row["senses"]
            )
            versions.append(RegistryVersion(
                registry_id=row["id"],
                month=row["month"],
                parent=row["parent"],
                senses=senses,
            ))
        return cls(versions)

    # ---- 查询 -----------------------------------------------------------

    @property
    def versions(self) -> tuple[RegistryVersion, ...]:
        return tuple(self._versions)

    def get(self, registry_id: str) -> RegistryVersion:
        return self._by_id[registry_id]

    def latest(self) -> RegistryVersion:
        return self._versions[-1]

    def versions_for_month(self, month: str) -> tuple[RegistryVersion, ...]:
        """该月生效的所有版本（含当月新登记版本）。"""
        return tuple(v for v in self._versions if v.month <= month)

    def lineage(self, registry_id: str) -> tuple[RegistryVersion, ...]:
        """同一 parent 口径下的全部版本，按生效月排序。

        旧概念拆成两个义项后，旧版本仍可打开，已发表旧刊物据此解释旧口径。
        """
        parent = self._by_id[registry_id].parent
        return tuple(v for v in self._versions if v.parent == parent)

    def aliases(self, version: RegistryVersion) -> tuple[str, ...]:
        out: set[str] = set()
        for s in version.senses:
            out.update(s.aliases)
        return tuple(sorted(out, key=len, reverse=True))

    def resolve_alias(self, surface: str,
                      version: RegistryVersion) -> tuple[Sense, ...]:
        """写法解析：命中的义项可能有多个（歧义），也可能只有一个（强写法）。"""
        return tuple(s for s in version.senses if surface in s.aliases)

    def sense(self, sense_id: str) -> Sense:
        for v in self._versions:
            for s in v.senses:
                if s.sense_id == sense_id:
                    return s
        raise KeyError(sense_id)

    def senses_of(self, version: RegistryVersion) -> tuple[Sense, ...]:
        return version.senses

    def alias_index(self, version: RegistryVersion) -> dict[str, tuple[str, ...]]:
        index: dict[str, set[str]] = defaultdict(set)
        for s in version.senses:
            for alias in s.aliases:
                index[alias].add(s.sense_id)
        return {a: tuple(sorted(ids)) for a, ids in index.items()}
