"""情绪打分 Provider。

策略（按优先级，可通过 ``SENTIMENT_MODEL`` env 强制选择）：
1. ``prior_sentiment`` 字段直通（StockTwits Bullish/Bearish 用户自标注） → ±0.6 compound
2. Azure OpenAI gpt-5.4-mini 批量 JSON 打分（首选，使用 ``LLM_BOOST_*`` 配置）
3. HF FinBERT（DistilRoberta financial-sentiment）
4. 本地词典 VADER-lite

无新依赖：复用 ``..utils.llm_client.LLMClient`` 调 Azure；磁盘缓存 24h。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ...config import Config
from ..hf_inference import HFInferenceClient, top_label

logger = logging.getLogger("finrex.financial.sentiment_provider")

# ── env helpers ──

def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _sentiment_model_preference() -> str:
    """``llm`` | ``finbert`` | ``vader_lite``."""
    v = (os.environ.get("SENTIMENT_MODEL") or "llm").strip().lower()
    if v not in {"llm", "finbert", "vader_lite"}:
        return "llm"
    return v


# ── LLM cache ──

def _cache_root() -> str:
    base = getattr(Config, "UPLOAD_ROOT", None) or os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "uploads"
    )
    root = os.path.abspath(os.path.join(base, "sentiment_cache"))
    os.makedirs(root, exist_ok=True)
    return root


_CACHE_TTL_SECONDS = 24 * 3600


def _cache_key(text: str, model: str) -> str:
    h = hashlib.sha1(f"{model}::{text}".encode("utf-8")).hexdigest()
    return h


def _cache_get(text: str, model: str) -> Optional[Dict[str, Any]]:
    key = _cache_key(text, model)
    path = os.path.join(_cache_root(), f"{key}.json")
    if not os.path.exists(path):
        return None
    if (time.time() - os.path.getmtime(path)) > _CACHE_TTL_SECONDS:
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def _cache_set(text: str, model: str, payload: Dict[str, Any]) -> None:
    key = _cache_key(text, model)
    path = os.path.join(_cache_root(), f"{key}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001
        logger.debug("sentiment cache write failed: %s", exc)


# ── 本地 fallback 词典（VADER-lite） ──
_POSITIVE_WORDS = {
    "bull", "bullish", "rally", "surge", "gain", "gains", "up", "rise", "rises", "soar",
    "soars", "beat", "beats", "outperform", "outperforms", "strong", "growth", "boost",
    "upgrade", "upgrades", "breakout", "record", "high", "highs", "buy", "long",
    "上涨", "看涨", "走高", "突破", "强势", "利好", "增长", "买入", "做多",
}
_NEGATIVE_WORDS = {
    "bear", "bearish", "drop", "drops", "fall", "falls", "down", "decline", "declines",
    "plunge", "plunges", "crash", "miss", "misses", "weak", "loss", "losses", "downgrade",
    "downgrades", "sell", "short", "low", "lows", "warning", "risk", "risks", "fear",
    "看跌", "下跌", "走低", "暴跌", "亏损", "利空", "卖出", "做空", "风险", "崩盘",
}


def _vader_lite(text: str) -> Dict[str, float]:
    """简化版 VADER：返回 {pos, neg, neu, compound}，compound ∈ [-1, 1]。"""
    text_l = text.lower()
    zh_pos = sum(1 for w in _POSITIVE_WORDS if any("\u4e00" <= ch <= "\u9fff" for ch in w) and w in text_l)
    zh_neg = sum(1 for w in _NEGATIVE_WORDS if any("\u4e00" <= ch <= "\u9fff" for ch in w) and w in text_l)
    tokens = re.findall(r"[A-Za-z]+|[\u4e00-\u9fff]", text_l)
    if not tokens:
        return {"pos": 0.0, "neg": 0.0, "neu": 1.0, "compound": 0.0}
    pos = zh_pos + sum(1 for t in tokens if t in _POSITIVE_WORDS)
    neg = zh_neg + sum(1 for t in tokens if t in _NEGATIVE_WORDS)
    total = max(len(tokens), 1)
    pos_ratio = pos / total
    neg_ratio = neg / total
    neu_ratio = max(0.0, 1.0 - pos_ratio - neg_ratio)
    compound = max(-1.0, min(1.0, (pos - neg) / max(pos + neg + 1.0, 1.0)))
    return {
        "pos": round(pos_ratio, 4),
        "neg": round(neg_ratio, 4),
        "neu": round(neu_ratio, 4),
        "compound": round(compound, 4),
    }


def _hf_to_compound(label: str, score: float) -> float:
    """将 HF 分类结果折算为 [-1, 1] compound 分数。"""
    label_l = (label or "").lower()
    if "pos" in label_l or "bull" in label_l or label_l in {"positive", "label_2"}:
        return float(score)
    if "neg" in label_l or "bear" in label_l or label_l in {"negative", "label_0"}:
        return -float(score)
    return 0.0


def _build_sentiment_record(compound: float, label: Optional[str] = None) -> Dict[str, float]:
    compound = max(-1.0, min(1.0, compound))
    if label is None:
        label = (
            "positive" if compound > 0.1 else
            "negative" if compound < -0.1 else
            "neutral"
        )
    return {
        "compound": round(compound, 4),
        "pos": round(max(compound, 0.0), 4),
        "neg": round(max(-compound, 0.0), 4),
        "neu": round(1.0 - abs(compound), 4),
        "label": label,
    }


def _prior_to_compound(prior: Optional[str]) -> Optional[float]:
    if not prior:
        return None
    p = str(prior).strip().lower()
    if p in {"bullish", "positive", "bull"}:
        return 0.6
    if p in {"bearish", "negative", "bear"}:
        return -0.6
    return None


# ── LLM batch scorer ──

_LLM_BATCH_SIZE = int(os.environ.get("SENTIMENT_LLM_BATCH_SIZE", "20"))


def _llm_client() -> Optional[Any]:
    """Build an LLMClient bound to the BOOST (mini) deployment if available."""
    if not _env_bool("LLM_BOOST_ENABLED", False):
        # Fall back to main LLM if boost is off but main key is present.
        if not getattr(Config, "LLM_API_KEY", None):
            return None
        try:
            from ...utils.llm_client import LLMClient
            return LLMClient()
        except Exception as exc:  # noqa: BLE001
            logger.debug("LLM client init failed (main): %s", exc)
            return None

    api_key = os.environ.get("LLM_BOOST_API_KEY") or getattr(Config, "LLM_API_KEY", None)
    base_url = os.environ.get("LLM_BOOST_BASE_URL") or getattr(Config, "LLM_BASE_URL", None)
    model = os.environ.get("LLM_BOOST_MODEL_NAME") or getattr(Config, "LLM_MODEL_NAME", None)
    deployment = os.environ.get("LLM_BOOST_DEPLOYMENT_NAME") or model
    if not api_key:
        return None
    try:
        from ...utils.llm_client import LLMClient
        return LLMClient(api_key=api_key, base_url=base_url, model=model, deployment_name=deployment)
    except Exception as exc:  # noqa: BLE001
        logger.debug("LLM client init failed (boost): %s", exc)
        return None


def _llm_batch_score(texts: List[str], client: Any) -> Optional[List[Optional[Dict[str, Any]]]]:
    """Score ``texts`` in chunks of ``_LLM_BATCH_SIZE``; preserves order, ``None`` on per-item parse fail.

    Returns ``None`` if the LLM call fails at the request level (so the caller
    can fall through to FinBERT / vader).
    """
    if not texts:
        return []
    out: List[Optional[Dict[str, Any]]] = []
    model_tag = "llm_finsentiment_v1"

    for start in range(0, len(texts), _LLM_BATCH_SIZE):
        chunk = texts[start:start + _LLM_BATCH_SIZE]

        # Cache check per item
        cached_results: List[Optional[Dict[str, Any]]] = [_cache_get(t, model_tag) for t in chunk]
        missing_indices = [i for i, c in enumerate(cached_results) if c is None]

        if missing_indices:
            payload_items = [{"idx": i, "text": chunk[i][:600]} for i in missing_indices]
            system = (
                "You score financial news / social posts for short-term equity direction. "
                "Return STRICT JSON: {\"items\":[{\"idx\":int,\"direction\":\"bullish|bearish|neutral\","
                "\"score\":float in [-1,1], \"rationale\":str}]}. "
                "score=+1 strongly bullish, -1 strongly bearish, 0 neutral. "
                "Focus on price/earnings/guidance/macro impact, ignore generic chatter."
            )
            user = "Score the following items:\n" + json.dumps(payload_items, ensure_ascii=False)

            try:
                parsed = client.chat_json(
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                    temperature=0.0,
                    max_tokens=900,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("LLM sentiment batch failed: %s", exc)
                return None

            llm_items = parsed.get("items") if isinstance(parsed, dict) else None
            if not isinstance(llm_items, list):
                logger.warning("LLM sentiment returned non-list payload")
                return None
            indexed: Dict[int, Dict[str, Any]] = {}
            for it in llm_items:
                if not isinstance(it, dict):
                    continue
                try:
                    idx_val = int(it.get("idx"))
                except (TypeError, ValueError):
                    continue
                score_raw = it.get("score")
                try:
                    score = float(score_raw)
                except (TypeError, ValueError):
                    score = 0.0
                direction = (it.get("direction") or "neutral").strip().lower()
                if direction not in {"bullish", "bearish", "neutral"}:
                    direction = "neutral"
                rationale = (it.get("rationale") or "").strip()[:160]
                indexed[idx_val] = {"direction": direction, "score": max(-1.0, min(1.0, score)), "rationale": rationale}

            for local_i in missing_indices:
                entry = indexed.get(local_i)
                if entry is None:
                    cached_results[local_i] = None
                    continue
                _cache_set(chunk[local_i], model_tag, entry)
                cached_results[local_i] = entry

        out.extend(cached_results)
    return out


class SentimentProvider:
    """情绪打分聚合器。"""

    def __init__(self, hf_client: Optional[HFInferenceClient] = None):
        self.hf = hf_client or HFInferenceClient()

    def score_corpus(
        self,
        items: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """对 news/comments item 列表打分。

        Args:
            items: list of {title, text, published_at, site, ...}

        Returns:
            {
                "ok": bool,
                "model": "hf_finbert" | "local_vader_lite",
                "scored_items": [
                    {**item, "sentiment": {"compound", "pos", "neg", "neu", "label"}}
                ],
                "summary": {
                    "count": int,
                    "avg_compound": float,
                    "pos_ratio": float,
                    "neg_ratio": float,
                    "neu_ratio": float,
                    "label": "bullish|bearish|neutral",
                },
                "timeline": [{"published_at", "compound"}],   # 按时间升序
            }
        """
        clean = [it for it in items if (it.get("text") or it.get("title"))]
        if not clean:
            return self._empty_result("local_vader_lite")

        # Step 1 — prior_sentiment fast-path (StockTwits user tags)
        prior_results: List[Optional[Dict[str, float]]] = []
        needs_score: List[Tuple[int, str]] = []
        for idx, it in enumerate(clean):
            prior = _prior_to_compound(it.get("prior_sentiment"))
            if prior is not None:
                prior_results.append(_build_sentiment_record(prior, label="positive" if prior > 0 else "negative"))
                continue
            prior_results.append(None)
            text = (it.get("title", "") + " " + it.get("text", "")).strip()
            needs_score.append((idx, text))

        preference = _sentiment_model_preference()

        scored: List[Dict[str, Any]] = []
        model_used = "local_vader_lite"

        llm_records: List[Optional[Dict[str, Any]]] = []
        hf_compounds: List[Optional[float]] = []

        # Step 2 — LLM batch scoring
        if preference == "llm" and needs_score:
            client = _llm_client()
            if client is not None:
                texts_only = [t for _, t in needs_score]
                llm_out = _llm_batch_score(texts_only, client)
                if llm_out is not None:
                    llm_records = llm_out
                    model_used = "llm_finsentiment"

        # Step 3 — HF FinBERT fallback for items LLM didn't cover (or preference=finbert)
        unmet_indices: List[int] = []
        if preference == "llm" and llm_records:
            for j, rec in enumerate(llm_records):
                if rec is None:
                    unmet_indices.append(j)
        elif preference == "llm" and not llm_records and needs_score:
            unmet_indices = list(range(len(needs_score)))
        elif preference == "finbert":
            unmet_indices = list(range(len(needs_score)))

        if unmet_indices:
            texts_subset = [needs_score[j][1] for j in unmet_indices]
            hf_result = self.hf.classify_financial(texts_subset)
            hf_items = hf_result.get("items") or []
            if hf_result.get("status") == "ok" and len(hf_items) == len(texts_subset):
                if model_used == "local_vader_lite":
                    model_used = "hf_finbert"
                hf_compounds = [None] * len(needs_score)
                for j, raw in zip(unmet_indices, hf_items):
                    top = top_label(raw) or {}
                    label = top.get("label", "neutral")
                    sc = float(top.get("score") or 0.0)
                    hf_compounds[j] = _hf_to_compound(label, sc)

        # Step 4 — assemble per-item record (prior > llm > hf > vader)
        score_iter_idx = 0
        for idx, it in enumerate(clean):
            if prior_results[idx] is not None:
                rec = prior_results[idx]
                scored.append({**it, "sentiment": rec, "sentiment_source": "prior"})
                continue
            local_i = score_iter_idx
            score_iter_idx += 1
            text = needs_score[local_i][1]
            chosen: Optional[Dict[str, float]] = None
            source = "vader_lite"
            if llm_records and local_i < len(llm_records) and llm_records[local_i] is not None:
                entry = llm_records[local_i]
                rec = _build_sentiment_record(float(entry["score"]), label=entry.get("direction"))
                chosen = rec
                source = "llm"
            if chosen is None and hf_compounds and local_i < len(hf_compounds) and hf_compounds[local_i] is not None:
                chosen = _build_sentiment_record(float(hf_compounds[local_i]))
                source = "hf_finbert"
            if chosen is None:
                vl = _vader_lite(text)
                chosen = _build_sentiment_record(vl["compound"])
                source = "vader_lite"
                if model_used == "local_vader_lite":
                    pass  # already
            scored.append({**it, "sentiment": chosen, "sentiment_source": source})

        return self._aggregate(scored, model_used)

    @staticmethod
    def _empty_result(model: str) -> Dict[str, Any]:
        return {
            "ok": False,
            "model": model,
            "scored_items": [],
            "summary": {
                "count": 0,
                "avg_compound": 0.0,
                "pos_ratio": 0.0,
                "neg_ratio": 0.0,
                "neu_ratio": 1.0,
                "label": "neutral",
            },
            "timeline": [],
        }

    @staticmethod
    def _aggregate(scored: List[Dict[str, Any]], model: str) -> Dict[str, Any]:
        n = len(scored)
        if n == 0:
            return SentimentProvider._empty_result(model)

        weighted_sum = 0.0
        weight_total = 0.0
        compounds: List[float] = []
        for s in scored:
            c = float(s["sentiment"]["compound"])
            w = float(s.get("weight") or 1.0)
            if w <= 0:
                w = 0.1
            weighted_sum += c * w
            weight_total += w
            compounds.append(c)
        avg = weighted_sum / weight_total if weight_total else 0.0
        pos = sum(1 for c in compounds if c > 0.1) / n
        neg = sum(1 for c in compounds if c < -0.1) / n
        neu = max(0.0, 1.0 - pos - neg)

        if avg > 0.15:
            label = "bullish"
        elif avg < -0.15:
            label = "bearish"
        else:
            label = "neutral"

        timeline = []
        for s in scored:
            ts = s.get("published_at") or ""
            timeline.append({
                "published_at": ts,
                "compound": s["sentiment"]["compound"],
                "title": s.get("title", "")[:80],
            })
        timeline.sort(key=lambda x: x["published_at"])

        return {
            "ok": True,
            "model": model,
            "scored_items": scored,
            "summary": {
                "count": n,
                "avg_compound": round(avg, 4),
                "pos_ratio": round(pos, 4),
                "neg_ratio": round(neg, 4),
                "neu_ratio": round(neu, 4),
                "label": label,
            },
            "timeline": timeline,
        }
