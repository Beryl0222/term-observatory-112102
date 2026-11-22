"""扫描引擎：按登记的概念、义项和语言习惯识别用词。

每条用词记录（Sighting）都带原文片段、所在句子、命中线索、实际指向或
存疑原因。否定用法与仅转述他人的用法单独成类，不充当证据。
"""

from __future__ import annotations

from .linguistics import (
    classify_usage,
    find_hedges,
    find_sense_cues,
    iter_matches,
    iter_sentences,
    split_clauses,
)
from .models import (
    Edition,
    RegistryVersion,
    Sighting,
    SightingStatus,
    UsageType,
)
from .registry import Registry


def _snippet(text: str, start: int, end: int, radius: int = 12) -> str:
    lo = max(0, start - radius)
    hi = min(len(text), end + radius)
    prefix = "…" if lo > 0 else ""
    suffix = "…" if hi < len(text) else ""
    return f"{prefix}{text[lo:hi]}{suffix}"


def _scan(edition: Edition, version: RegistryVersion,
          registry: Registry) -> list[Sighting]:
    sightings: list[Sighting] = []
    aliases = registry.aliases(version)
    sense_ids = [s.sense_id for s in version.senses]

    for sentence in iter_sentences(edition.text, edition.language):
        clauses = split_clauses(sentence, edition.language)
        # 先逐小句判定用法。转述/否定小句里的资源词不参与义项判定，
        # 避免“别人没做 grid”污染本文自身 mesh dispatch 的归属。
        clause_usage: dict[int, tuple[str, dict]] = {}
        study_parts: list[str] = []
        for idx, clause in enumerate(clauses):
            usage, usage_cues = classify_usage(
                clause, [c for j, c in enumerate(clauses) if j != idx],
                edition.language,
            )
            clause_usage[idx] = (usage, usage_cues)
            if usage == "study":
                study_parts.append(clause.text)
        study_cue_map = find_sense_cues(" ".join(study_parts), sense_ids,
                                        edition.language)

        for idx, clause in enumerate(clauses):
            usage, usage_cues = clause_usage[idx]
            for match in iter_matches(clause.text, aliases, edition.language):
                g_start = clause.start + match.start
                g_end = clause.start + match.end
                senses = registry.resolve_alias(match.surface, version)
                candidate_ids = tuple(s.sense_id for s in senses)
                reasons: list[str] = []
                status: SightingStatus
                sense_id: str | None = None

                if usage == "reported":
                    status = SightingStatus.REPORTED
                    reasons.append(
                        f"转述线索 {list(usage_cues['reported'])}，"
                        "仅引用其他研究，不计入本文证据")
                elif usage == "negated":
                    status = SightingStatus.NEGATED
                    cues = usage_cues.get("negated") or \
                        usage_cues.get("contrast_negated") or ()
                    reasons.append(f"否定线索 {list(cues)}，本文未实际采用")
                else:
                    hedges = find_hedges(sentence.text, edition.language)
                    if hedges:
                        status = SightingStatus.AMBIGUOUS
                        reasons.append(
                            f"摘要明示资源类型未交代（{list(hedges)}），"
                            f"候选义项 {list(candidate_ids)} 无法定夺")
                    else:
                        hinted = tuple(sid for sid in candidate_ids
                                       if sid in study_cue_map)
                        if len(hinted) == 1:
                            status = SightingStatus.CONFIRMED
                            sense_id = hinted[0]
                            reasons.append(
                                f"资源线索 {list(study_cue_map[hinted[0]])} "
                                f"唯一支持 {sense_id}")
                        elif len(hinted) > 1:
                            status = SightingStatus.AMBIGUOUS
                            reasons.append(
                                "同一研究句内出现多个义项的资源线索 "
                                f"{ {k: list(v) for k, v in study_cue_map.items()} }，"
                                "归属待定")
                        elif len(candidate_ids) == 1:
                            status = SightingStatus.CONFIRMED
                            sense_id = candidate_ids[0]
                            reasons.append(
                                f"写法“{match.surface}”只在 {sense_id} 登记，"
                                "属强写法")
                        else:
                            status = SightingStatus.AMBIGUOUS
                            reasons.append(
                                f"写法“{match.surface}”对应多个义项 "
                                f"{list(candidate_ids)}，且句内无资源线索，"
                                f"学科“{edition.field}”仅作参考不能定案")

                sightings.append(Sighting(
                    sighting_id=Sighting.make_id(
                        edition.edition_id, g_start, g_end, match.surface),
                    edition_id=edition.edition_id,
                    work_id=edition.work_id,
                    month=edition.month,
                    field=edition.field,
                    language=edition.language,
                    registry_id=version.registry_id,
                    surface=match.surface,
                    start=g_start,
                    end=g_end,
                    snippet=_snippet(edition.text, g_start, g_end),
                    sentence=sentence.text,
                    usage=UsageType(usage),
                    status=status,
                    candidate_senses=candidate_ids,
                    sense_id=sense_id,
                    cues={**study_cue_map, **usage_cues},
                    reasons=tuple(reasons),
                ))
    return sightings


def scan_edition(edition: Edition, registry: Registry,
                 version: RegistryVersion | None = None) -> list[Sighting]:
    """扫描一份摘要。默认用当前最新词表——比较月份时两月同口径。"""
    version = version or registry.latest()
    return _scan(edition, version, registry)


def scan_editions(editions: list[Edition], registry: Registry,
                  version: RegistryVersion | None = None) -> dict[str, list[Sighting]]:
    version = version or registry.latest()
    return {e.edition_id: scan_edition(e, registry, version) for e in editions}
