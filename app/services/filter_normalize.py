"""
Deterministic canonical form for profile list/search filters.
Same logical query must yield the same cache key regardless of wording or param ordering.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Optional


_FILTER_KEYS = (
    "gender",
    "age_group",
    "country_id",
    "min_age",
    "max_age",
    "min_gender_probability",
    "min_country_probability",
    "sort_by",
    "order",
    "page",
    "limit",
)


def _norm_str(s: str) -> str:
    return s.strip().lower()


def _norm_country(code: str) -> str:
    return code.strip().upper()


def _norm_prob(v: Any) -> Optional[float]:
    if v is None:
        return None
    x = float(v)
    return round(x, 9)


def canonicalize_profile_filters(filters: Mapping[str, Any]) -> dict[str, Any]:
    """
    Build a stable dict: sorted keys, normalised string casing, numeric rounding.
    Only includes keys that are present with non-None values (after normalisation).
    """
    out: dict[str, Any] = {}

    g = filters.get("gender")
    if g is not None and str(g).strip() != "":
        out["gender"] = _norm_str(str(g))

    ag = filters.get("age_group")
    if ag is not None and str(ag).strip() != "":
        out["age_group"] = _norm_str(str(ag))

    cid = filters.get("country_id")
    if cid is not None and str(cid).strip() != "":
        out["country_id"] = _norm_country(str(cid))

    ma = filters.get("min_age")
    if ma is not None:
        out["min_age"] = int(ma)

    xa = filters.get("max_age")
    if xa is not None:
        out["max_age"] = int(xa)

    mgp = filters.get("min_gender_probability")
    if mgp is not None:
        p = _norm_prob(mgp)
        if p is not None:
            out["min_gender_probability"] = p

    mcp = filters.get("min_country_probability")
    if mcp is not None:
        p = _norm_prob(mcp)
        if p is not None:
            out["min_country_probability"] = p

    sb = filters.get("sort_by")
    if sb is not None and str(sb).strip() != "":
        out["sort_by"] = str(sb).strip().lower()

    od = filters.get("order")
    if od is not None and str(od).strip() != "":
        o = str(od).strip().lower()
        if o in ("asc", "desc"):
            out["order"] = o

    pg = filters.get("page")
    if pg is not None:
        out["page"] = int(pg)

    lim = filters.get("limit")
    if lim is not None:
        out["limit"] = int(lim)

    # Fixed key order for JSON stability
    return {k: out[k] for k in _FILTER_KEYS if k in out}


def cache_key_segment(filters: dict[str, Any]) -> str:
    """Stable string for hashing (no whitespace drift)."""
    return json.dumps(filters, sort_keys=True, separators=(",", ":"))


def build_profiles_cache_key(route: str, filters: dict[str, Any]) -> str:
    """route: 'list' | 'search'"""
    base = cache_key_segment(filters)
    h = hashlib.sha256(f"{route}:{base}".encode("utf-8")).hexdigest()[:32]
    return f"insighta:profiles:{route}:{h}"
