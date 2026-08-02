"""Licence agent: decide whether an image may be redistributed in the atlas.

The atlas is published as a whole work (PDF, HTML, exports), so an image is only
acceptable when the licence permits redistribution *and* - unless explicitly
relaxed - commercial use and modification (images are resized and re-encoded for
the atlas, which is a modification).

Rejected outright:

* all-rights-reserved / non-free / fair-use tags
* NonCommercial terms (unless ``UAV_ALLOW_NC_LICENSES=1``)
* NoDerivatives terms (the atlas resizes every image)
* missing provenance: no licence name, or no source page to attribute back to

Every decision is written to ``verification_events`` so the licence chain can be
audited later.
"""

from __future__ import annotations

import re
from typing import Any

from app.config import get_settings
from app.logging import AgentLogger
from app.models import ImageCandidate, LicenseVerdict
from app.utils import clean_text

LOG = AgentLogger("image_license_agent")
AGENT = "image_license_agent"

PD_RE = re.compile(
    r"(public[ -]?domain|\bcc0\b|\bpdm\b|^pd[- ]|\bpd-us\b|\bpd-old\b|"
    r"no known copyright|copyright[- ]free|works of the (us|u\.s\.) federal government)",
    re.IGNORECASE,
)
CC_BY_RE = re.compile(r"cc[ -]?by(?![ -]?nc)(?:[ -]?sa)?(?:[ -]?\d(?:\.\d)?)?", re.IGNORECASE)
NC_RE = re.compile(r"(non[- ]?commercial|cc[ -]?by[ -]?nc|\bnc\b)", re.IGNORECASE)
ND_RE = re.compile(r"(no[ -]?deriv\w*|cc[ -]?by[ -]?nd|\bnd\b)", re.IGNORECASE)
UNFREE_RE = re.compile(
    r"(all rights reserved|fair ?use|non[- ]?free|copyrighted|"
    r"editorial use only|rights[- ]managed|©\s*\d{4})",
    re.IGNORECASE,
)
SA_RE = re.compile(r"share[- ]?alike|cc[ -]?by[ -]?sa", re.IGNORECASE)

#: Government works that are public domain by statute or explicit policy.
GOV_PD_HOSTS = (
    "dvidshub.net",
    ".mil",
    "nasa.gov",
    "defense.gov",
    "af.mil",
    "navy.mil",
    "army.mil",
    "usgs.gov",
    "noaa.gov",
)


def build_attribution(candidate: ImageCandidate, license_name: str) -> str:
    """Compose the attribution string stored with the image and printed in the atlas."""
    author = clean_text(candidate.photographer) or "Unknown author"
    title = clean_text(candidate.title) or "Untitled"
    provider = clean_text(candidate.provider) or "source"
    parts = [f"{title} by {author}"]
    if license_name:
        parts.append(license_name)
    parts.append(f"via {provider}")
    if candidate.source_page_url:
        parts.append(candidate.source_page_url)
    return " — ".join(parts)


def evaluate(candidate: ImageCandidate) -> LicenseVerdict:
    """Return the redistribution verdict for one image candidate."""
    settings = get_settings()
    license_name = clean_text(candidate.license_name)
    haystack = " ".join(
        [license_name, candidate.attribution_text, candidate.description, candidate.license_url]
    )
    page = (candidate.source_page_url or candidate.source_url or "").lower()

    if not candidate.source_page_url and not candidate.source_url:
        return LicenseVerdict(
            False, license_name, candidate.license_url, False, None, None, "",
            "missing provenance: no source page or file URL",
        )

    is_gov_pd = any(host in page for host in GOV_PD_HOSTS)

    if UNFREE_RE.search(haystack) and not PD_RE.search(haystack) and not is_gov_pd:
        return LicenseVerdict(
            False, license_name, candidate.license_url, False, False, False, "",
            f"incompatible rights statement: {license_name or 'all rights reserved'}",
        )

    if not license_name and not is_gov_pd:
        return LicenseVerdict(
            False, "", candidate.license_url, False, None, None, "",
            "no licence metadata published with the file",
        )

    if NC_RE.search(haystack) and not settings.allow_noncommercial_licenses:
        return LicenseVerdict(
            False, license_name, candidate.license_url, False, False, None, "",
            "NonCommercial licence: incompatible with redistributable atlas",
        )

    if ND_RE.search(haystack) and not PD_RE.search(haystack):
        return LicenseVerdict(
            False, license_name, candidate.license_url, False, None, False, "",
            "NoDerivatives licence: the atlas resizes and re-encodes every image",
        )

    public_domain = bool(PD_RE.search(haystack)) or is_gov_pd
    creative_commons = bool(CC_BY_RE.search(haystack))

    if not (public_domain or creative_commons):
        return LicenseVerdict(
            False, license_name, candidate.license_url, False, None, None, "",
            f"unrecognised licence, cannot establish reuse basis: {license_name!r}",
        )

    effective_name = license_name or ("Public domain (US government work)" if is_gov_pd else "")
    return LicenseVerdict(
        acceptable=True,
        license_name=effective_name,
        license_url=candidate.license_url,
        is_public_domain=public_domain,
        commercial_use=True,
        modification_allowed=True,
        attribution_text=build_attribution(candidate, effective_name),
        reason=(
            "public domain"
            if public_domain
            else ("Creative Commons ShareAlike" if SA_RE.search(haystack) else "Creative Commons Attribution")
        ),
    )


def verdict_to_row(verdict: LicenseVerdict) -> dict[str, Any]:
    """Project a verdict onto the ``images`` table columns."""
    return {
        "license_name": verdict.license_name or None,
        "license_url": verdict.license_url or None,
        "attribution_text": verdict.attribution_text or None,
        "is_public_domain": int(verdict.is_public_domain),
        "commercial_use": None if verdict.commercial_use is None else int(verdict.commercial_use),
        "modification_allowed": None
        if verdict.modification_allowed is None
        else int(verdict.modification_allowed),
        "license_verified": int(verdict.acceptable),
    }


def run(candidates: list[ImageCandidate]) -> list[tuple[ImageCandidate, LicenseVerdict]]:
    """Evaluate a batch, keeping the pairing for the caller."""
    results = [(candidate, evaluate(candidate)) for candidate in candidates]
    accepted = sum(1 for _, v in results if v.acceptable)
    LOG.debug("licence screening: %d/%d acceptable", accepted, len(results))
    return results
