"""Image validation: decode, measure, hash and reject unusable files.

Checks performed on every downloaded file:

* the bytes actually decode as an image (``PIL.Image.verify`` then a real load)
* MIME type is a raster format the atlas can embed
* width meets the absolute minimum (500 px) and is scored against the preferred
  minimum (800 px)
* aspect ratio is plausible for a photograph, not a banner strip or a thin crop
* SHA-256 exact-duplicate detection
* perceptual-hash near-duplicate detection, so the same photo cannot be reused
  for two unrelated platforms

Derivatives (thumbnail, atlas image, optional WebP) are produced here too.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.db import connect, query
from app.logging import AgentLogger
from app.models import ValidationVerdict
from app.utils import sha256_bytes

LOG = AgentLogger("image_validation_agent")
AGENT = "image_validation_agent"

ACCEPTED_MIME = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}

MIN_ASPECT = 0.4
MAX_ASPECT = 4.0
#: Hamming distance at or below which two perceptual hashes are "the same photo".
PHASH_DUPLICATE_DISTANCE = 6


def _pillow() -> Any:
    from PIL import Image  # imported lazily so unit tests can run without Pillow

    return Image


def perceptual_hash(image: Any) -> str:
    """64-bit average hash. Uses ``imagehash`` when available, else a local dhash."""
    try:
        import imagehash

        return str(imagehash.phash(image))
    except ImportError:
        grey = image.convert("L").resize((9, 8))
        pixels = list(grey.getdata())
        bits = []
        for row in range(8):
            for col in range(8):
                left = pixels[row * 9 + col]
                right = pixels[row * 9 + col + 1]
                bits.append("1" if left > right else "0")
        return f"{int(''.join(bits), 2):016x}"


def hamming(a: str, b: str) -> int:
    """Hamming distance between two hex hash strings (max distance if unusable)."""
    if not a or not b or len(a) != len(b):
        return 64
    try:
        return bin(int(a, 16) ^ int(b, 16)).count("1")
    except ValueError:
        return 64


def validate_bytes(data: bytes, *, declared_mime: str = "") -> ValidationVerdict:
    """Decode and measure raw image bytes without touching the filesystem."""
    settings = get_settings()
    if not data:
        return ValidationVerdict(False, "empty response body")
    if len(data) > settings.image_max_bytes:
        return ValidationVerdict(False, f"file larger than {settings.image_max_bytes} bytes")

    Image = _pillow()
    try:
        probe = Image.open(io.BytesIO(data))
        probe.verify()  # structural check, invalidates the object
        image = Image.open(io.BytesIO(data))
        image.load()  # full decode: catches truncated files
    except Exception as exc:
        return ValidationVerdict(False, f"file does not decode as an image: {exc}")

    fmt = (image.format or "").lower()
    mime = {"jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(fmt, declared_mime)
    if mime not in ACCEPTED_MIME:
        return ValidationVerdict(False, f"unsupported image type: {mime or fmt or 'unknown'}")

    width, height = image.size
    if width < settings.image_min_width:
        return ValidationVerdict(
            False,
            f"width {width}px below absolute minimum {settings.image_min_width}px",
            width,
            height,
            mime,
        )
    if height <= 0:
        return ValidationVerdict(False, "zero height", width, height, mime)

    aspect = width / height
    if not (MIN_ASPECT <= aspect <= MAX_ASPECT):
        return ValidationVerdict(
            False, f"implausible aspect ratio {aspect:.2f}", width, height, mime
        )

    return ValidationVerdict(
        ok=True,
        reason="",
        width=width,
        height=height,
        mime_type=mime,
        sha256=sha256_bytes(data),
        perceptual_hash=perceptual_hash(image),
    )


def find_exact_duplicate(sha256: str, *, exclude_platform_id: int | None = None) -> dict[str, Any] | None:
    rows = query(
        "SELECT id, platform_id, local_path FROM images WHERE sha256=? AND validation_status='ok'",
        (sha256,),
    )
    for row in rows:
        if exclude_platform_id is not None and int(row["platform_id"]) == exclude_platform_id:
            continue
        return dict(row)
    return None


def find_perceptual_duplicate(
    phash: str, *, exclude_platform_id: int | None = None, distance: int = PHASH_DUPLICATE_DISTANCE
) -> dict[str, Any] | None:
    """Reject the same photograph being used for two unrelated platforms."""
    if not phash:
        return None
    rows = query(
        """
        SELECT i.id, i.platform_id, i.perceptual_hash, p.canonical_name
        FROM images i JOIN platforms p ON p.id = i.platform_id
        WHERE i.perceptual_hash IS NOT NULL AND i.validation_status='ok'
        """
    )
    for row in rows:
        if exclude_platform_id is not None and int(row["platform_id"]) == exclude_platform_id:
            continue
        if hamming(phash, row["perceptual_hash"]) <= distance:
            return dict(row)
    return None


def build_derivatives(
    source_path: Path,
    *,
    destination_dir: Path,
    stem: str,
) -> dict[str, str]:
    """Create thumbnail / atlas / WebP derivatives next to the original."""
    settings = get_settings()
    Image = _pillow()
    destination_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, str] = {}

    with Image.open(source_path) as image:
        rgb = image.convert("RGB")

        atlas_path = destination_dir / f"{stem}.atlas.jpg"
        atlas = rgb.copy()
        atlas.thumbnail((settings.atlas_image_width, settings.atlas_image_width), Image.LANCZOS)
        atlas.save(atlas_path, "JPEG", quality=86, optimize=True, progressive=True)
        outputs["atlas_path"] = str(atlas_path)

        thumb_path = destination_dir / f"{stem}.thumb.jpg"
        thumb = rgb.copy()
        thumb.thumbnail((settings.thumbnail_width, settings.thumbnail_width), Image.LANCZOS)
        thumb.save(thumb_path, "JPEG", quality=82, optimize=True)
        outputs["thumbnail_path"] = str(thumb_path)

        if settings.generate_webp:
            try:
                webp_path = destination_dir / f"{stem}.atlas.webp"
                atlas.save(webp_path, "WEBP", quality=82, method=4)
                outputs["webp_path"] = str(webp_path)
            except Exception as exc:
                LOG.debug("webp derivative skipped for %s: %s", stem, exc)

    return outputs


def revalidate_stored() -> dict[str, Any]:
    """Re-check every stored image on disk (used after a partial/interrupted run)."""
    conn = connect()
    stats = {"checked": 0, "ok": 0, "missing": 0, "corrupt": 0}
    for row in query("SELECT id, local_path FROM images WHERE local_path IS NOT NULL", conn=conn):
        stats["checked"] += 1
        path = Path(row["local_path"])
        if not path.is_file():
            stats["missing"] += 1
            conn.execute(
                "UPDATE images SET validation_status='missing', selected_for_atlas=0, "
                "rejection_reason='file missing on disk' WHERE id=?",
                (row["id"],),
            )
            continue
        verdict = validate_bytes(path.read_bytes())
        if verdict.ok:
            stats["ok"] += 1
        else:
            stats["corrupt"] += 1
            conn.execute(
                "UPDATE images SET validation_status='invalid', selected_for_atlas=0, "
                "rejection_reason=? WHERE id=?",
                (verdict.reason, row["id"]),
            )
    LOG.info("revalidation: %s", stats)
    LOG.event("image_revalidation", **stats)
    return stats


def run() -> dict[str, Any]:
    return revalidate_stored()
