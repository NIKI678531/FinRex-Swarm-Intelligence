"""Small Hugging Face remote inference client with non-blocking fallback."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from ..config import Config


class HFInferenceClient:
    DEFAULT_FINANCIAL_MODEL = "mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis"
    DEFAULT_EMOTION_MODEL = "tabularisai/multilingual-emotion-classification"
    DEFAULT_BASE_URL = "https://router.huggingface.co/hf-inference/models"

    def __init__(self, token: Optional[str] = None, timeout: Optional[int] = None):
        self.token = token if token is not None else Config.HF_TOKEN
        self.timeout = int(timeout if timeout is not None else Config.HF_TIMEOUT_SECONDS)
        self.enabled = Config.HF_ENABLE_REMOTE_INFERENCE
        self.base_url = Config.HF_INFERENCE_BASE_URL.rstrip("/")
        self.max_items = max(1, Config.HF_MAX_ITEMS_PER_REQUEST)
        self.financial_model = Config.HF_FINANCIAL_SENTIMENT_MODEL
        self.emotion_model = Config.HF_EMOTION_MODEL

    def classify_financial(self, texts: List[str]) -> Dict[str, Any]:
        return self._classify(texts, self.financial_model, "financial_sentiment")

    def classify_emotion(self, texts: List[str]) -> Dict[str, Any]:
        if not Config.HF_ALLOW_NON_COMMERCIAL_MODELS:
            return {
                "task": "emotion",
                "model": self.emotion_model,
                "status": "license_guard",
                "reason": "HF_ALLOW_NON_COMMERCIAL_MODELS must be true for non-commercial emotion models",
                "license": "cc-by-nc-4.0",
                "items": [],
            }
        return self._classify(texts, self.emotion_model, "emotion")

    def _classify(self, texts: List[str], model: str, task: str) -> Dict[str, Any]:
        clean_texts = [text for text in texts if text]
        if not clean_texts:
            return {"task": task, "model": model, "status": "skipped", "reason": "empty input", "items": []}
        if not self.enabled:
            return {"task": task, "model": model, "status": "disabled", "reason": "HF_ENABLE_REMOTE_INFERENCE=false", "items": []}
        if not self.token:
            return {"task": task, "model": model, "status": "skipped", "reason": "HF_TOKEN missing", "items": []}

        items = []
        try:
            for text in clean_texts[:self.max_items]:
                items.append(self._request(model, text[:1200]))
            return {"task": task, "model": model, "status": "ok", "items": items}
        except Exception as exc:  # Remote inference should never block report rendering.
            return {"task": task, "model": model, "status": "fallback", "reason": str(exc), "items": []}

    def _request(self, model: str, text: str) -> Any:
        encoded_model = urllib.parse.quote(model.strip("/"), safe="/")
        url = f"{self.base_url}/{encoded_model}"
        payload = json.dumps({"inputs": text}).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HF {exc.code}: {body[:240]}") from exc


def top_label(result: Any) -> Optional[Dict[str, Any]]:
    """Return the highest scoring label from common HF classification shapes."""
    candidates = result
    if isinstance(candidates, list) and candidates and isinstance(candidates[0], list):
        candidates = candidates[0]
    if not isinstance(candidates, list):
        return None
    labels = [item for item in candidates if isinstance(item, dict) and "label" in item]
    if not labels:
        return None
    return max(labels, key=lambda item: float(item.get("score") or 0))
