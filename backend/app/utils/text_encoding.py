"""Utilities for repairing common mojibake before it reaches users or LLMs."""

from __future__ import annotations

from typing import Any


_GBK_MARKERS = (
    "锛",
    "鍚",
    "妯",
    "嫙",
    "绛",
    "瀹",
    "寮",
    "鐢",
    "熸",
    "℃",
    "銆",
    "鈥",
    "鉁",
    "鉂",
    "鏋",
    "瑙",
    "勬",
    "犺",
    "撳",
    "戞",
)

_LATIN1_MARKERS = (
    "Ã",
    "Â",
    "â€",
    "æ",
    "å",
    "ç",
)


def _badness(text: str) -> int:
    if not text:
        return 0

    score = text.count("\ufffd") * 8
    score += sum(4 for ch in text if 0x80 <= ord(ch) <= 0x9F)
    score += sum(text.count(marker) * 3 for marker in _GBK_MARKERS)
    score += sum(text.count(marker) * 2 for marker in _LATIN1_MARKERS)
    return score


def _try_decode(text: str, source_encoding: str) -> str | None:
    try:
        candidate = text.encode(source_encoding).decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None
    return candidate


def repair_text(value: str) -> str:
    """Repair UTF-8 text that was accidentally decoded as GBK/latin1/cp1252.

    The function is intentionally conservative: it only accepts a candidate when
    the mojibake score improves materially, so normal Chinese/English text is
    left unchanged.
    """
    if not isinstance(value, str) or not value:
        return value

    current = value
    for _ in range(2):
        before = _badness(current)
        if before == 0:
            break

        best = current
        best_score = before
        for encoding in ("latin1", "cp1252", "gb18030"):
            candidate = _try_decode(current, encoding)
            if candidate is None or candidate == current:
                continue
            candidate_score = _badness(candidate)
            if candidate_score + 2 < best_score:
                best = candidate
                best_score = candidate_score

        if best == current:
            break
        current = best

    return current


def repair_data(value: Any) -> Any:
    """Recursively repair strings inside JSON-like data."""
    if isinstance(value, str):
        return repair_text(value)
    if isinstance(value, list):
        return [repair_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(repair_data(item) for item in value)
    if isinstance(value, dict):
        return {key: repair_data(item) for key, item in value.items()}
    return value
