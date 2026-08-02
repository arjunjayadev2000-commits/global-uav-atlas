"""Typed record objects exchanged between agents.

These are deliberately thin dataclasses rather than an ORM: the pipeline is
batch oriented, the SQL lives in :mod:`app.schemas`, and keeping the transport
objects plain makes them trivial to serialise into the audit log.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from app.utils import (
    clean_text,
    normalize_country,
    normalize_name,
    stable_id,
)

# Canonical vocabulary -------------------------------------------------------

DOMAIN_MILITARY = "Military"
DOMAIN_CIVIL = "Civilian / Commercial"
DOMAIN_DUAL = "Dual-use"
DOMAIN_RESEARCH = "Research / Experimental"
DOMAIN_UNKNOWN = "Unknown"

DOMAINS = (
    DOMAIN_MILITARY,
    DOMAIN_CIVIL,
    DOMAIN_DUAL,
    DOMAIN_RESEARCH,
    DOMAIN_UNKNOWN,
)

VERIFICATION_VERIFIED = "Verified"
VERIFICATION_PROBABLE = "Probable"
VERIFICATION_NEEDS = "Needs Verification"

IDENTITY_MATCH = "match"
IDENTITY_PROBABLE = "probable match"
IDENTITY_UNCERTAIN = "uncertain"
IDENTITY_MISMATCH = "mismatch"
IDENTITY_UNVERIFIED = "unverified"


_DOMAIN_ALIASES = {
    "military": DOMAIN_MILITARY,
    "military / government": DOMAIN_MILITARY,
    "military/government": DOMAIN_MILITARY,
    "defence": DOMAIN_MILITARY,
    "defense": DOMAIN_MILITARY,
    "government": DOMAIN_MILITARY,
    "civilian": DOMAIN_CIVIL,
    "civil": DOMAIN_CIVIL,
    "commercial": DOMAIN_CIVIL,
    "civilian / commercial": DOMAIN_CIVIL,
    "civilian/commercial": DOMAIN_CIVIL,
    "consumer": DOMAIN_CIVIL,
    "dual use": DOMAIN_DUAL,
    "dual-use": DOMAIN_DUAL,
    "dual": DOMAIN_DUAL,
    "research": DOMAIN_RESEARCH,
    "experimental": DOMAIN_RESEARCH,
    "research / experimental": DOMAIN_RESEARCH,
    "academic": DOMAIN_RESEARCH,
}


def normalize_domain(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return DOMAIN_UNKNOWN
    key = text.lower().strip()
    if key in _DOMAIN_ALIASES:
        return _DOMAIN_ALIASES[key]
    for alias, canonical in _DOMAIN_ALIASES.items():
        if alias in key:
            return canonical
    return DOMAIN_UNKNOWN


@dataclass(slots=True)
class RawDiscovery:
    """A candidate record exactly as a source presented it.

    Raw discoveries are never edited: canonicalisation happens downstream so the
    original evidence stays auditable.
    """

    raw_name: str
    source_dataset: str
    source_url: str = ""
    external_ref: str = ""
    raw_country: str = ""
    raw_manufacturer: str = ""
    domain: str = ""
    category: str = ""
    status: str = ""
    variant: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def normalized_name(self) -> str:
        return normalize_name(self.raw_name)

    @property
    def fingerprint(self) -> str:
        """Stable identity of *this observation* (source + name + variant)."""
        return stable_id(
            self.source_dataset,
            self.normalized_name,
            normalize_name(self.variant),
            self.external_ref,
        )

    def to_row(self, *, discovery_run_id: int | None, source_id: int | None, created_at: str) -> dict[str, Any]:
        return {
            "discovery_run_id": discovery_run_id,
            "source_id": source_id,
            "source_dataset": self.source_dataset,
            "source_url": self.source_url,
            "external_ref": self.external_ref,
            "raw_name": self.raw_name,
            "normalized_name": self.normalized_name,
            "raw_country": self.raw_country,
            "raw_manufacturer": self.raw_manufacturer,
            "domain": self.domain,
            "category": self.category,
            "status": self.status,
            "variant": self.variant,
            "payload_json": json.dumps(self.payload, ensure_ascii=False, default=str),
            "fingerprint": self.fingerprint,
            "processed": 0,
            "created_at": created_at,
        }


@dataclass(slots=True)
class PlatformRecord:
    """A canonical platform ready to be written to ``platforms``."""

    canonical_name: str
    country: str = "Unknown"
    manufacturer: str = ""
    domain: str = DOMAIN_UNKNOWN
    category: str = ""
    airframe_type: str = ""
    status: str = ""
    family: str = ""
    variant: str = ""
    aliases: list[str] = field(default_factory=list)
    model_codes: list[str] = field(default_factory=list)
    first_seen_year: int | None = None
    introduced_year: int | None = None
    retired_year: int | None = None
    description_short: str = ""
    verification_status: str = VERIFICATION_NEEDS
    confidence_score: float = 0.0
    origin_confidence: str = ""
    participating_countries: list[str] = field(default_factory=list)
    production_country: str = ""

    def __post_init__(self) -> None:
        self.canonical_name = clean_text(self.canonical_name)
        self.domain = normalize_domain(self.domain)
        country, participants = normalize_country(self.country)
        self.country = country
        if participants and not self.participating_countries:
            self.participating_countries = participants

    @property
    def normalized_name(self) -> str:
        return normalize_name(self.canonical_name)

    @property
    def public_id(self) -> str:
        return "UAV-" + stable_id(self.normalized_name).upper()[:12]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ImageCandidate:
    """One licensed image candidate for a platform, pre-download."""

    platform_id: int
    platform_name: str
    source_url: str
    source_page_url: str = ""
    title: str = ""
    photographer: str = ""
    license_name: str = ""
    license_url: str = ""
    attribution_text: str = ""
    width: int = 0
    height: int = 0
    mime_type: str = ""
    file_size: int = 0
    description: str = ""
    categories: list[str] = field(default_factory=list)
    provider: str = ""
    score: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LicenseVerdict:
    acceptable: bool
    license_name: str
    license_url: str
    is_public_domain: bool
    commercial_use: bool | None
    modification_allowed: bool | None
    attribution_text: str
    reason: str = ""


@dataclass(slots=True)
class ValidationVerdict:
    ok: bool
    reason: str = ""
    width: int = 0
    height: int = 0
    mime_type: str = ""
    sha256: str = ""
    perceptual_hash: str = ""


@dataclass(slots=True)
class IdentityVerdict:
    verdict: str
    confidence: float
    explanation: str
    method: str = "metadata"
