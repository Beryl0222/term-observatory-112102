"""语言习惯层：句子与小句切分、术语匹配、否定/转述/资源线索。

线索表按文种登记，规则保持可解释——每条用词记录都会带上命中的线索，
编辑看到的不是黑箱标签，而是“凭什么这样判”。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

# --- 用法线索 -------------------------------------------------------------

REPORT_CUES: dict[str, tuple[str, ...]] = {
    "zh": ("简报提到", "报道", "转述", "引用", "称", "据称", "有研究", "文献"),
    "en": ("prior work", "previous study", "reported", "according to", "study",
           "studies", "studied"),
}

NEGATION_CUES: dict[str, tuple[str, ...]] = {
    "zh": ("并未", "没有", "未", "并非", "并不", "不是", "不能"),
    "en": ("not", "no ", "never", "without", "neither"),
}

# 明确承认摘要没写资源类型，触发存疑
HEDGE_CUES: dict[str, tuple[str, ...]] = {
    "zh": ("未在摘要写出", "没有写", "未写出", "不说明", "未说明", "不详"),
    "en": ("not stated", "unspecified", "unclear", "not specified"),
}

# 考虑过但没做——与“但没有……”转折连用
CONSIDERATION_CUES: dict[str, tuple[str, ...]] = {
    "zh": ("曾考虑", "考虑", "拟"),
    "en": ("considered", "considered but", "we considered"),
}

# 自身研究的肯定使用，用来区分“别人不做但我们做”
AFFIRM_CUES: dict[str, tuple[str, ...]] = {
    "zh": ("我们", "本文", "本组", "采用", "部署", "使用", "用", "验证", "调配"),
    "en": ("our", "we", "this paper", "this study", "use", "uses", "used",
           "deploy", "deploys", "deployed"),
}

CONTRAST_CUES: dict[str, tuple[str, ...]] = {
    "zh": ("但", "但是", "然而", "却"),
    "en": ("although", "though", "but", "however"),
}

# --- 义项资源线索（命中即支持某义项；可按语言习惯扩展） -------------------

SENSE_CUES: dict[str, dict[str, tuple[str, ...]]] = {
    "C1-gpu": {
        "zh": ("显存", "算力", "计算设备", "GPU", "gpu", "训练任务", "算力池"),
        "en": ("GPU", "gpu", "compute", "computing", "training", "memory"),
    },
    "C1-grid": {
        "zh": ("储能", "电站", "削峰", "电力", "尖峰负载", "负载", "电网"),
        "en": ("grid", "storage", "peak shaving", "peak", "power", "battery"),
    },
    "C1-other": {
        "zh": ("光路", "光链路", "中继", "光学", "切换"),
        "en": ("optical", "lightpath", "light path", "relay"),
    },
}

_SENT_SPLIT_ZH = re.compile(r"(?<=[。！？；!?;])")
_SENT_SPLIT_EN = re.compile(r"(?<=[.!?;])\s+")
_CLAUSE_SPLIT_ZH = re.compile(r"[，、；,;:：]")
_CLAUSE_SPLIT_EN = re.compile(r"\s*(?:,|;|:|\balthough\b|\bthough\b|\bbut\b|\bhowever\b)\s*",
                              re.IGNORECASE)
_WORD_BOUNDARY_EN = r"(?<!\w)(?:{})(?!\w)"


@dataclass(frozen=True)
class Match:
    start: int
    end: int
    surface: str


@dataclass(frozen=True)
class Clause:
    start: int
    end: int
    text: str


def iter_sentences(text: str, language: str) -> list[Clause]:
    """返回带全局偏移的句子区间。"""
    if not text:
        return []
    pattern = _SENT_SPLIT_ZH if language == "zh" else _SENT_SPLIT_EN
    parts = pattern.split(text)
    out: list[Clause] = []
    cursor = 0
    for part in parts:
        if not part:
            continue
        idx = text.find(part, cursor)
        if idx < 0:  # 理论上不会发生，find 兜底
            idx = cursor
        end = idx + len(part)
        out.append(Clause(idx, end, part))
        cursor = end
    return out


def split_clauses(sentence: Clause, language: str) -> list[Clause]:
    """句内小句，保留相对全文的全局偏移。"""
    pattern = _CLAUSE_SPLIT_ZH if language == "zh" else _CLAUSE_SPLIT_EN
    pieces: list[Clause] = []
    cursor = sentence.start
    for match in pattern.finditer(sentence.text):
        piece = sentence.text[cursor - sentence.start:match.start()]
        if piece.strip():
            pieces.append(Clause(cursor, sentence.start + match.start(), piece))
        cursor = sentence.start + match.end()
    tail = sentence.text[cursor - sentence.start:]
    if tail.strip():
        pieces.append(Clause(cursor, sentence.end, tail))
    return pieces or [sentence]


def iter_matches(text: str, aliases: Iterable[str], language: str) -> list[Match]:
    """长写法优先、互不重叠的术语匹配。

    中文直接子串匹配（长词吞掉短词，柔性织网不会再切成织网）；
    英文用词边界并忽略大小写（mesh dispatch 按整体匹配）。
    """
    aliases = sorted({a for a in aliases if a}, key=len, reverse=True)
    if not aliases:
        return []
    found: list[Match] = []
    if language == "zh":
        for alias in aliases:
            start = text.find(alias)
            while start >= 0:
                found.append(Match(start, start + len(alias), alias))
                start = text.find(alias, start + 1)
    else:
        pattern = _WORD_BOUNDARY_EN.format(
            "|".join(re.escape(a) for a in aliases))
        for m in re.finditer(pattern, text, re.IGNORECASE):
            found.append(Match(m.start(), m.end(), m.group(0)))
    # 长写法优先的贪心去重
    found.sort(key=lambda m: (m.start, -(m.end - m.start)))
    chosen: list[Match] = []
    for m in found:
        if any(not (m.end <= c.start or m.start >= c.end) for c in chosen):
            continue
        chosen.append(m)
    chosen.sort(key=lambda m: m.start)
    return chosen


def _hit(cues: tuple[str, ...], text: str) -> tuple[str, ...]:
    low = text.lower()
    return tuple(c for c in cues if (c.lower() in low))


def find_sense_cues(text: str, sense_ids: Iterable[str],
                    language: str) -> dict[str, tuple[str, ...]]:
    out: dict[str, tuple[str, ...]] = {}
    for sid in sense_ids:
        cues = SENSE_CUES.get(sid, {}).get(language, ())
        hits = _hit(cues, text)
        if hits:
            out[sid] = hits
    return out


def classify_usage(owner: Clause, siblings: list[Clause],
                   language: str) -> tuple[str, dict[str, tuple[str, ...]]]:
    """判断术语所在小句属于自身研究/否定/转述。

    先看本小句的转述与否定线索；再处理“曾考虑 X，但没有……”这类跨小句
    转折否定。若转折小句否定的是别人（our cluster uses …, although … does not），
    本小句有自身肯定线索时仍判自身研究。
    """
    cues: dict[str, tuple[str, ...]] = {}
    rep = _hit(REPORT_CUES[language], owner.text)
    if rep:
        cues["reported"] = rep
        return "reported", cues
    neg = _hit(NEGATION_CUES[language], owner.text)
    if neg:
        cues["negated"] = neg
        return "negated", cues

    contrast = [c for c in siblings
                if _hit(CONTRAST_CUES[language], c.text)
                and _hit(NEGATION_CUES[language], c.text)]
    if contrast:
        cues["contrast_negated"] = _hit(NEGATION_CUES[language],
                                        " ".join(c.text for c in contrast))
        if _hit(CONSIDERATION_CUES[language], owner.text) or not _hit(
                AFFIRM_CUES[language], owner.text):
            return "negated", cues
    return "study", cues


def find_hedges(text: str, language: str) -> tuple[str, ...]:
    return _hit(HEDGE_CUES[language], text)
