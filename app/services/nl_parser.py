"""
Rule-based natural language parser.
Converts plain-English queries into filter dicts for the profiles endpoint.
"""

import re
from typing import Optional


COUNTRY_MAP: dict[str, str] = {
    # West Africa
    "nigeria": "NG",
    "niger": "NE",
    "ghana": "GH",
    "benin": "BJ",
    "togo": "TG",
    "senegal": "SN",
    "mali": "ML",
    "burkina faso": "BF",
    "ivory coast": "CI",
    "cote d'ivoire": "CI",
    "liberia": "LR",
    "sierra leone": "SL",
    "guinea": "GN",
    "guinea bissau": "GW",
    "gambia": "GM",
    "cape verde": "CV",
    "mauritania": "MR",
    # East Africa
    "kenya": "KE",
    "ethiopia": "ET",
    "tanzania": "TZ",
    "uganda": "UG",
    "rwanda": "RW",
    "burundi": "BI",
    "somalia": "SO",
    "djibouti": "DJ",
    "eritrea": "ER",
    "south sudan": "SS",
    "sudan": "SD",
    # Central Africa
    "cameroon": "CM",
    "chad": "TD",
    "central african republic": "CF",
    "democratic republic of congo": "CD",
    "drc": "CD",
    "congo": "CG",
    "gabon": "GA",
    "equatorial guinea": "GQ",
    "sao tome and principe": "ST",
    # Southern Africa
    "south africa": "ZA",
    "zimbabwe": "ZW",
    "zambia": "ZM",
    "mozambique": "MZ",
    "angola": "AO",
    "namibia": "NA",
    "botswana": "BW",
    "lesotho": "LS",
    "eswatini": "SZ",
    "swaziland": "SZ",
    "madagascar": "MG",
    "malawi": "MW",
    # North Africa
    "egypt": "EG",
    "morocco": "MA",
    "algeria": "DZ",
    "tunisia": "TN",
    "libya": "LY",
    # Other common
    "united states": "US",
    "usa": "US",
    "uk": "GB",
    "united kingdom": "GB",
    "france": "FR",
    "germany": "DE",
    "india": "IN",
    "china": "CN",
    "brazil": "BR",
    "canada": "CA",
    "australia": "AU",
}


def _extract_country(q: str) -> Optional[str]:
    """Return ISO-2 code if a country name is found in the query."""
    q_lower = q.lower()

    for name in sorted(COUNTRY_MAP, key=len, reverse=True):
        pattern = r"\b" + re.escape(name) + r"\b"
        if re.search(pattern, q_lower):
            return COUNTRY_MAP[name]
    return None


def _extract_gender(q: str) -> Optional[str]:
    q_lower = q.lower()
    has_male = bool(re.search(r"\b(male|males|men|man)\b", q_lower))
    has_female = bool(re.search(r"\b(female|females|women|woman|girl|girls)\b", q_lower))
    if has_male and has_female:
        return None  
    if has_male:
        return "male"
    if has_female:
        return "female"
    return None


def _extract_age_group(q: str) -> Optional[str]:
    q_lower = q.lower()
    if re.search(r"\b(teenager|teenagers|teen|teens)\b", q_lower):
        return "teenager"
    if re.search(r"\b(adult|adults)\b", q_lower):
        return "adult"
    if re.search(r"\b(senior|seniors|elderly|elder)\b", q_lower):
        return "senior"
    if re.search(r"\b(child|children|kid|kids)\b", q_lower):
        return "child"
    return None


def _extract_age_bounds(q: str) -> tuple[Optional[int], Optional[int]]:
    """Return (min_age, max_age) from phrases like 'above 30', 'below 20', 'young'."""
    q_lower = q.lower()
    min_age: Optional[int] = None
    max_age: Optional[int] = None

    
    if re.search(r"\byoung\b", q_lower):
        min_age = 16
        max_age = 24

    m = re.search(r"\b(?:above|over|older than|at least)\s+(\d+)", q_lower)
    if m:
        min_age = int(m.group(1))

    m = re.search(r"\b(?:below|under|younger than|at most)\s+(\d+)", q_lower)
    if m:
        max_age = int(m.group(1))

    m = re.search(r"\bbetween\s+(\d+)\s+and\s+(\d+)", q_lower)
    if m:
        min_age = int(m.group(1))
        max_age = int(m.group(2))

    return min_age, max_age


def parse_natural_language(q: str) -> Optional[dict]:
    """
    Parse a natural language query into a filter dict.
    Returns None if no recognisable filters are found.
    """
    if not q or not q.strip():
        return None

    gender = _extract_gender(q)
    age_group = _extract_age_group(q)
    min_age, max_age = _extract_age_bounds(q)
    country_id = _extract_country(q)

    filters = {}
    if gender:
        filters["gender"] = gender
    if age_group:
        filters["age_group"] = age_group
    if min_age is not None:
        filters["min_age"] = min_age
    if max_age is not None:
        filters["max_age"] = max_age
    if country_id:
        filters["country_id"] = country_id

    return filters if filters else None
