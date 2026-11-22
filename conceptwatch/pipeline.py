"""端到端流水线与命令行：词表 -> 扫描 -> 复核 -> 比较 -> 抽核 -> 出刊视图。"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .audit import AuditPlan, build_audit_plan, load_slots
from .compare import compare_months
from .corpus import Corpus
from .detect import scan_editions
from .models import SightingStatus
from .publish import explain_historical, freeze_issue, load_historical_bulletins
from .registry import Registry
from .review import ReviewLedger


@dataclass
class PipelineResult:
    registry: Registry
    corpus: Corpus
    ledger: ReviewLedger
    sightings: dict
    decision_report: object
    comparison: object
    audit_plan: AuditPlan
    issue: object
    historical: list


def run_pipeline(data_dir: str | Path,
                 month_a: str, month_b: str) -> PipelineResult:
    data_dir = Path(data_dir)
    registry = Registry.from_file(data_dir / "lexicon.json")
    corpus = Corpus.from_file(data_dir / "abstracts.json",
                              desk_path=data_dir / "desk.json")
    ledger = ReviewLedger.from_file(data_dir / "desk.json", registry)

    # 两月统一采用现行词表重扫（旧口径只在旧刊快照里解释）
    sightings = scan_editions(list(corpus.editions), registry)
    decision_report = ledger.apply(sightings, corpus)

    comparison = compare_months(month_a, month_b, corpus, registry, sightings)
    slots = load_slots(data_dir / "desk.json")
    audit_plan = build_audit_plan(slots, sightings, corpus,
                                  excluded_works=comparison.out_of_scope_works)
    issue = freeze_issue(f"{month_a} 至 {month_b} 概念趋势工作稿",
                         "2026-11-22", registry, comparison, audit_plan)
    historical = [
        explain_historical(b, corpus, registry)
        for b in load_historical_bulletins(data_dir / "desk.json")
    ]
    return PipelineResult(registry, corpus, ledger, sightings,
                          decision_report, comparison, audit_plan, issue,
                          historical)


# --- 人类可读报告 ---------------------------------------------------------

def _fmt_rate(rate) -> str:
    return "不可比" if rate is None else f"{rate:.1%}"


def render_report(result: PipelineResult) -> str:
    cmp_ = result.comparison
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("研究概念趋势工作稿（按文献去重，否定/转述不计证据）")
    lines.append("=" * 72)

    if not cmp_.comparable:
        lines.append(f"不能比较：{cmp_.reason}")
        return "\n".join(lines)

    lines.append(f"比较月份：{cmp_.month_a} -> {cmp_.month_b}")
    lines.append(f"共同覆盖（学科×文种）：{list(cmp_.shared_cells)}")
    for month, cells in cmp_.excluded_cells.items():
        if cells:
            lines.append(f"  {month} 未纳入比较的格：{list(cells)}（覆盖不对齐）")
    lines.append(f"分母（交齐格内有效文献）：{cmp_.denominators}")
    if cmp_.out_of_scope_works:
        lines.append(f"覆盖外文献（不进分母与席位）："
                     f"{list(cmp_.out_of_scope_works)}")
    lines.append("")

    for sid, trend in cmp_.sense_trends.items():
        notes = result.registry.sense(sid).notes
        lines.append(f"【义项 {sid}】{notes}")
        for month in (cmp_.month_a, cmp_.month_b):
            st = trend.stats[month]
            lines.append(
                f"  {month}  确定 {st.low} 篇 / 上限 {st.high} 篇"
                f"（分母 {st.denominator}，"
                f"占比 {_fmt_rate(st.low / st.denominator) if st.denominator else '—'}"
                f" ~ {_fmt_rate(st.high / st.denominator) if st.denominator else '—'}）"
                f"  确定:{list(st.low_works)} 存疑待定:{list(st.pending_works)}")
        lines.append(f"  变化区间：{trend.delta_low:+d} ~ {trend.delta_high:+d} 篇"
                     "（存疑不计零，也不跨义项重复计入同一篇）")
        lines.append("")

    c = cmp_.concept_trend
    lines.append(f"【概念合计 {c.sense_id}（按文献去重）】")
    for month in (cmp_.month_a, cmp_.month_b):
        st = c.stats[month]
        lines.append(f"  {month}  确定 {st.low} ~ 上限 {st.high} 篇 / 分母 {st.denominator}")
    lines.append(f"  变化区间：{c.delta_low:+d} ~ {c.delta_high:+d} 篇")
    lines.append("")

    lines.append("抽核席位（每格可点回原文；同一篇不跨变化占用）：")
    for a in result.audit_plan.assignments:
        if a.edition_id:
            lines.append(
                f"  {a.sense_id} | {a.month} {a.field} 第{a.seat_index}席 -> "
                f"{a.edition_id}/{a.work_id} 片段 {a.sighting_id}"
                + (f" [复核 {a.decision_id}]" if a.decision_id else ""))
        else:
            lines.append(f"  {a.sense_id} | {a.month} {a.field} 第{a.seat_index}席 -> 空缺（{a.note}）")
    for note in result.audit_plan.missing_cells:
        lines.append(f"  {note}")
    lines.append("")

    lines.append("送人审的存疑片段（不占确定席位）：")
    for s in result.audit_plan.review_queue:
        lines.append(f"  {s.edition_id}/{s.work_id} “{s.snippet}” 候选 {list(s.candidate_senses)}")
        for reason in s.reasons:
            lines.append(f"      - {reason}")
    lines.append("")

    lines.append("复核决定台账：")
    for d in result.ledger.decisions:
        lines.append(f"  {d.decision_id} {d.work_id} -> {d.sense_id or '（未解析）'} "
                     f"[{d.state.value}] {d.stale_reason or ''}")
    lines.append("")

    lines.append("已发旧刊回查（撤回原文不再展示）：")
    for h in result.historical:
        lines.append(f"  旧刊 {h['bulletin_id']}（{h['released']}，口径 {h['legacy_registry']['id']}）"
                     f"当时计数 {h['published_ratios']}")
        for e in h["evidence_entries"]:
            lines.append(f"      {e['edition_id']}/{e['work_id']}: {e['current_status']}，{e['evidence_note']}")
    return "\n".join(lines)


def render_sightings(result: PipelineResult) -> str:
    lines = ["全部用词记录（含否定与转述，附原文片段与判定理由）："]
    for edition_id in sorted(result.sightings):
        edition = result.corpus.edition(edition_id)
        status = result.corpus.status_of(edition).value
        lines.append(f"\n{edition_id} ({edition.work_id} {edition.language} "
                     f"{edition.field} serial={edition.serial} [{status}])")
        if edition.retracted:
            lines.append("  撤回件，无原文展示，扫描不产出证据。")
            continue
        for s in result.sightings[edition_id]:
            tag = {
                SightingStatus.CONFIRMED: f"确认->{s.sense_id}",
                SightingStatus.AMBIGUOUS: f"存疑{list(s.candidate_senses)}",
                SightingStatus.NEGATED: "否定",
                SightingStatus.REPORTED: "转述",
            }[s.status]
            lines.append(f"  [{s.usage.value}|{tag}] “{s.surface}” @ {s.start}-{s.end}  {s.snippet}")
            for reason in s.reasons:
                lines.append(f"      · {reason}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="研究概念趋势与语料回查工具")
    parser.add_argument("--data", default="data", help="三份 JSON 资料所在目录")
    parser.add_argument("--month-a", default="2026-08")
    parser.add_argument("--month-b", default="2026-09")
    parser.add_argument("--sightings", action="store_true",
                        help="输出每篇摘要的逐条用词记录")
    parser.add_argument("--json", action="store_true",
                        help="以 JSON 输出工作稿快照")
    args = parser.parse_args(argv)

    result = run_pipeline(args.data, args.month_a, args.month_b)
    if args.json:
        print(json.dumps(asdict(result.issue), ensure_ascii=False, indent=2))
    elif args.sightings:
        print(render_sightings(result))
    else:
        print(render_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
