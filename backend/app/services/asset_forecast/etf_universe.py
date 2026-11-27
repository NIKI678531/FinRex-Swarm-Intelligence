"""ETF universe loader.

Loads ``etf_universe.yaml`` and exposes a small query API used by the
forecast service. Falls back to a minimal hard-coded universe if PyYAML
is not installed, so the module always imports.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional

_YAML_PATH = os.path.join(os.path.dirname(__file__), "etf_universe.yaml")


def _load_yaml() -> Dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError:
        return _fallback_universe()
    if not os.path.exists(_YAML_PATH):
        return _fallback_universe()
    with open(_YAML_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not data.get("products"):
        return _fallback_universe()
    return data


def _fallback_universe() -> Dict[str, Any]:
    return {
        "products": [
            {"code": "3033.HK", "yahoo": "3033.HK", "market": "HK", "currency": "HKD",
             "name_zh": "南方东英恒生科技指数 ETF", "name_en": "CSOP Hang Seng TECH Index ETF",
             "asset_class": "equity", "theme_tags": ["china_policy", "tech_growth"],
             "risk_tier": "high", "tradable": True},
            {"code": "3034.HK", "yahoo": "3034.HK", "market": "HK", "currency": "HKD",
             "name_zh": "南方东英纳斯达克100 ETF", "name_en": "CSOP NASDAQ 100 ETF",
             "asset_class": "equity", "theme_tags": ["us_tech", "tech_growth"],
             "risk_tier": "high", "tradable": True},
            {"code": "3066.HK", "yahoo": "3066.HK", "market": "HK", "currency": "HKD",
             "name_zh": "南方东英比特币期货 ETF", "name_en": "CSOP Bitcoin Futures ETF",
             "asset_class": "crypto", "theme_tags": ["crypto"],
             "risk_tier": "very_high", "tradable": True},
            {"code": "3199.HK", "yahoo": "3199.HK", "market": "HK", "currency": "HKD",
             "name_zh": "工银南方东英中国国债+政金债 ETF",
             "name_en": "ICBC CSOP FTSE Chinese Government & Policy Bank Bond Index ETF",
             "asset_class": "fixed_income", "theme_tags": ["macro_risk", "safe_haven"],
             "risk_tier": "low", "tradable": True},
        ],
        "theme_aliases": {},
    }


class EtfUniverse:
    """Lightweight in-memory ETF master data."""

    _data: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    @classmethod
    def _ensure(cls) -> Dict[str, Any]:
        if cls._data is None:
            cls._data = _load_yaml()
        return cls._data

    @classmethod
    def reload(cls) -> None:
        cls._data = None
        cls._ensure()

    # ------------------------------------------------------------------
    @classmethod
    def all_products(cls) -> List[Dict[str, Any]]:
        return list(cls._ensure().get("products", []))

    @classmethod
    def tradable_products(cls) -> List[Dict[str, Any]]:
        return [p for p in cls.all_products() if p.get("tradable")]

    @classmethod
    def by_code(cls, code: str) -> Optional[Dict[str, Any]]:
        if not code:
            return None
        wanted = code.upper().strip()
        for p in cls.all_products():
            if (p.get("code") or "").upper() == wanted:
                return p
            if (p.get("yahoo") or "").upper() == wanted:
                return p
        return None

    @classmethod
    def by_theme(cls, theme_key: str, tradable_only: bool = True) -> List[Dict[str, Any]]:
        """Return all products whose ``theme_tags`` include the given theme.

        Honors ``theme_aliases`` so callers can pass either the universe
        tag or a ``report_strategy.THEME_RULES`` key.
        """
        if not theme_key:
            return []
        aliases = cls._ensure().get("theme_aliases", {}) or {}
        targets = set([theme_key])
        for canonical, members in aliases.items():
            if theme_key == canonical or theme_key in (members or []):
                targets.add(canonical)
                targets.update(members or [])
        pool = cls.tradable_products() if tradable_only else cls.all_products()
        return [p for p in pool if targets.intersection(p.get("theme_tags") or [])]

    @classmethod
    def by_themes(cls, theme_keys: Iterable[str], tradable_only: bool = True) -> List[Dict[str, Any]]:
        """Union of products across multiple themes, deduped by code."""
        seen: Dict[str, Dict[str, Any]] = {}
        for key in theme_keys or []:
            for product in cls.by_theme(key, tradable_only=tradable_only):
                seen.setdefault(product["code"], product)
        return list(seen.values())
