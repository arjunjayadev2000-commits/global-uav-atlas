"""Source crawlers.

Each module exposes ``discover(...) -> list[RawDiscovery]`` (and, for image
providers, ``search_images(...)``) so the discovery agent can treat every source
uniformly.  All network traffic goes through :mod:`crawlers.http`.
"""

from __future__ import annotations

__all__ = [
    "http",
    "wikimedia",
    "manufacturer",
    "government",
    "regulatory",
    "public_sources",
]
