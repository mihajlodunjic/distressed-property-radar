from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal

LOCATION_VERSION = "location_rules_v1"

_BLOCK_RE = re.compile(r"\bblok\s*(?P<number>\d{1,3})\b", re.IGNORECASE)
_MICROZONE_PATTERNS = (
    ("bezanijska kosa", "Bezanijska kosa"),
    ("belville", "Belville"),
    ("savski kej", "Savski kej"),
    ("zemunske kapije", "Zemunske kapije"),
    ("gornji grad", "Gornji grad"),
    ("prvomajska", "Prvomajska"),
    ("altina", "Altina"),
    ("galenika", "Galenika"),
    ("retenzija", "Retenzija"),
)


@dataclass(frozen=True)
class NormalizedLocation:
    country_code: str | None
    city: str | None
    municipality: str | None
    neighborhood: str | None
    micro_location: str | None
    location_precision: str
    location_confidence: Decimal
    rules_version: str = LOCATION_VERSION


def normalize_location_text(*values: object) -> NormalizedLocation:
    source_text = _clean_joined_text(values)
    comparable_text = _comparable_text(source_text)

    city = "Beograd" if _has_belgrade_signal(comparable_text) else None
    municipality = _municipality(comparable_text)
    neighborhood = _microzone(comparable_text)
    micro_location = neighborhood or _clean_text(source_text)

    if neighborhood is not None:
        precision = "MICROZONE"
        confidence = Decimal("0.9000")
    elif municipality is not None:
        precision = "MUNICIPALITY"
        confidence = Decimal("0.5500")
    elif city is not None:
        precision = "CITY"
        confidence = Decimal("0.3500")
    else:
        precision = "UNKNOWN"
        confidence = Decimal("0.0000")
        micro_location = None

    return NormalizedLocation(
        country_code="RS" if city or municipality or neighborhood else None,
        city=city,
        municipality=municipality,
        neighborhood=neighborhood,
        micro_location=micro_location,
        location_precision=precision,
        location_confidence=confidence,
    )


def _microzone(text: str) -> str | None:
    block_match = _BLOCK_RE.search(text)
    if block_match is not None:
        return f"Blok {block_match.group('number')}"
    for pattern, canonical_name in _MICROZONE_PATTERNS:
        if pattern in text:
            return canonical_name
    return None


def _municipality(text: str) -> str | None:
    if "novi beograd" in text or "new belgrade" in text:
        return "Novi Beograd"
    if "zemun" in text:
        return "Zemun"
    return None


def _has_belgrade_signal(text: str) -> bool:
    return "beograd" in text or "belgrade" in text or "zemun" in text


def _clean_joined_text(values: tuple[object, ...]) -> str:
    return " ".join(text for text in (_clean_text(value) for value in values) if text is not None)


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).replace("-", " ").split())
    return text or None


def _comparable_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.lower())
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_text.replace("-", " ").split())
