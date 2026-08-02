#!/usr/bin/env python3
"""Probe every configured source host and print the allowlist the pipeline needs.

Run this before `python run.py --images` in a restricted network. It reports, per
host, whether the pipeline can reach it, and ends with a copy-pasteable list of
the hosts an administrator would need to permit for a complete build.

Exit code 0 = every host reachable; 1 = at least one host blocked.
"""

from __future__ import annotations

import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crawlers.http import FetchError, HttpClient  # noqa: E402
from crawlers.public_sources import load_registry  # noqa: E402

#: Hosts the image pipeline needs beyond what the source registry lists.
IMAGE_HOSTS = [
    ("commons.wikimedia.org", "Wikimedia Commons API - image search and licence metadata"),
    ("upload.wikimedia.org", "Wikimedia Commons file store - the image bytes themselves"),
]


def hosts_from_registry() -> list[tuple[str, str]]:
    registry = load_registry()
    found: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(url: str, description: str) -> None:
        host = urllib.parse.urlparse(url).netloc
        if host and host not in seen:
            seen.add(host)
            found.append((host, description))

    for source in registry.get("sources", []):
        add(source.get("url", ""), f"{source.get('title', source.get('id'))} (tier {source.get('credibility_tier')})")
    for site in registry.get("manufacturer_sites", []):
        add(site.get("url", ""), f"{site.get('manufacturer')} official product pages (tier 1)")
    for source in registry.get("government_sources", []):
        add(source.get("url", ""), f"{source.get('title')} (tier 1)")
    return found


def probe(client: HttpClient, host: str) -> tuple[bool, str]:
    """Reachable means *the host answered*, whatever it said.

    A bare `GET /` often returns 400 or 404 on an API host - that is still proof
    the connection was permitted. Only a proxy refusal means blocked.
    """
    url = f"https://{host}/"
    try:
        response = client.get(url, use_cache=False, max_bytes=65536, allow_robots_bypass=True)
    except FetchError as exc:
        if "egress policy" in str(exc):
            return False, "blocked by network egress policy (403 at the proxy)"
        if getattr(exc, "status", None) is not None:
            return True, f"HTTP {exc.status} (host answered)"
        return False, str(exc)[:110]
    except Exception as exc:
        return False, str(exc)[:110]
    return True, f"HTTP {response.status}"


def main() -> int:
    client = HttpClient()

    targets: list[tuple[str, str]] = []
    seen: set[str] = set()
    for host, description in hosts_from_registry() + IMAGE_HOSTS:
        if host not in seen:
            seen.add(host)
            targets.append((host, description))

    print(f"Probing {len(targets)} host(s)\n")
    blocked: list[tuple[str, str]] = []
    for host, description in targets:
        ok, detail = probe(client, host)
        mark = "reachable" if ok else "BLOCKED  "
        print(f"  {mark}  {host:<34} {description}")
        if not ok:
            blocked.append((host, detail))
        else:
            print(f"             {'':<34} {detail}")

    print()
    if not blocked:
        print("Every configured host is reachable. Run: python run.py --all --resume")
        return 0

    print(f"{len(blocked)} host(s) unreachable:\n")
    for host, detail in blocked:
        print(f"  {host:<34} {detail}")

    print("\nAllowlist to request from whoever administers this network:\n")
    for host, _ in blocked:
        print(f"  {host}")

    print(
        "\nThe two Wikimedia hosts are the ones that unblock photographs; the rest\n"
        "extend platform coverage. Without them, use:\n"
        "  python scripts/prepare_image_manifest.py   # build a fill-in manifest\n"
        "  python run.py --sideload-images            # ingest files you licensed yourself"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
