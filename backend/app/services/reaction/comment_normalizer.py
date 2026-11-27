"""Normalize event and comment inputs for reaction analysis."""

from __future__ import annotations

import re
from html import unescape
from typing import Any, Dict, Iterable, List, Tuple

from .schema import ReactionComment, ReactionEvent


TAG_RE = re.compile(r"<[^>]+>")


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    text = unescape(TAG_RE.sub(" ", text))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _first_non_empty(row: Dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        val = clean_text(row.get(key))
        if val:
            return val
    return ""


def normalize_event(payload: Dict[str, Any]) -> ReactionEvent:
    event = payload.get("event") or {}
    selected = payload.get("selected_articles") or payload.get("articles") or []
    first_article = selected[0] if selected and isinstance(selected[0], dict) else {}

    title = clean_text(event.get("title") or first_article.get("title") or payload.get("title"))
    content = clean_text(
        event.get("content")
        or first_article.get("content")
        or first_article.get("body")
        or payload.get("content")
        or payload.get("simulation_requirement")
    )

    source = clean_text(event.get("source") or first_article.get("source") or payload.get("source") or "manual")
    return ReactionEvent(
        title=title,
        content=content,
        source=source or "manual",
        url=clean_text(event.get("url") or event.get("link") or first_article.get("link")),
        author=clean_text(event.get("author") or first_article.get("author")),
        published_at=clean_text(event.get("published_at") or event.get("date") or first_article.get("date")),
        metadata={
            "selected_article_ids": [a.get("id") for a in selected if isinstance(a, dict) and a.get("id")],
            "selected_articles_count": len(selected) if isinstance(selected, list) else 0,
        },
    )


def _comment_from_dict(row: Dict[str, Any], default_source: str = "unknown") -> ReactionComment | None:
    text = _first_non_empty(row, ("text", "content", "body", "comment", "comment_text", "message"))
    if not text:
        return None
    return ReactionComment(
        text=text,
        source=clean_text(row.get("source") or default_source),
        author=_first_non_empty(row, ("author", "author_name", "user", "username", "screen_name")),
        created_at=_first_non_empty(row, ("created_at", "publish_time", "date", "timestamp")),
        like_count=_safe_int(row.get("like_count") or row.get("likes") or row.get("upvotes")),
        reply_count=_safe_int(row.get("reply_count") or row.get("replies")),
        metadata={k: v for k, v in row.items() if k not in {"text", "content", "body", "comment"}},
    )


def normalize_comments(payload: Dict[str, Any]) -> List[ReactionComment]:
    comments: List[ReactionComment] = []

    for item in payload.get("comments") or []:
        if isinstance(item, str):
            text = clean_text(item)
            if text:
                comments.append(ReactionComment(text=text, source=payload.get("source") or "paste"))
        elif isinstance(item, dict):
            comment = _comment_from_dict(item, default_source=payload.get("source") or "unknown")
            if comment:
                comments.append(comment)

    pasted = payload.get("pasted_text") or payload.get("comments_text") or ""
    if isinstance(pasted, str) and pasted.strip():
        for line in re.split(r"[\r\n]+", pasted):
            text = clean_text(line)
            if text:
                comments.append(ReactionComment(text=text, source="paste"))

    for article in payload.get("selected_articles") or payload.get("articles") or []:
        if not isinstance(article, dict):
            continue
        for raw in article.get("comments") or article.get("comment_items") or []:
            if isinstance(raw, str):
                text = clean_text(raw)
                if text:
                    comments.append(ReactionComment(text=text, source=article.get("source") or "article"))
            elif isinstance(raw, dict):
                comment = _comment_from_dict(raw, default_source=article.get("source") or "article")
                if comment:
                    comments.append(comment)

    return _dedupe_comments(comments)


def _dedupe_comments(comments: List[ReactionComment]) -> List[ReactionComment]:
    seen = set()
    result: List[ReactionComment] = []
    for comment in comments:
        key = re.sub(r"\s+", " ", comment.text.lower()).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(comment)
    return result


def normalize_payload(payload: Dict[str, Any]) -> Tuple[ReactionEvent, List[ReactionComment]]:
    return normalize_event(payload), normalize_comments(payload)
