"""Optional open-source datasets that extend the two supplied files.

The competition explicitly invites participants to go beyond the uploaded data.
This module is the sanctioned route for doing that: each source is declared with
its citation, licence and the join key that makes it usable, and each fetch is
wrapped so that an offline or firewalled environment degrades to a clear message
rather than a stack trace. Nothing in the core pipeline depends on any of them -
the analysis is complete without network access - but each one deepens a specific
result, and the deepening is stated rather than implied.

Usage::

    python -m dcsc.ingest.external --list
    python -m dcsc.ingest.external --fetch imf_portwatch_chokepoints
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from ..config import DATA_RAW
from ..io_utils import get_logger

LOG = get_logger("dcsc.ingest.external")


@dataclass(frozen=True)
class Source:
    key: str
    name: str
    publisher: str
    url: str
    licence: str
    join_key: str
    why: str
    needs_auth: bool = False


SOURCES: tuple[Source, ...] = (
    Source(
        key="imf_portwatch_chokepoints",
        name="Daily Chokepoint Transit Calls",
        publisher="IMF PortWatch (IMF / Oxford Economics)",
        url="https://portwatch.imf.org/datasets",
        licence="Open, attribution required",
        join_key="chokepoint name -> config/chokepoints.json id",
        why=(
            "Gives daily transit counts and cargo tonnage per chokepoint back to 2019. "
            "It converts this project's 14-day traffic *level* into a *change*, which is the "
            "single biggest limitation of the supplied detection window."
        ),
    ),
    Source(
        key="unctad_maritime",
        name="Review of Maritime Transport statistics",
        publisher="UNCTADstat",
        url="https://unctadstat.unctad.org/datacentre/",
        licence="Open, attribution required",
        join_key="country / route",
        why=(
            "Supplies fleet, trade-volume and freight-rate context, so a throughput deficit "
            "can be expressed in tonnes and in freight cost rather than in detections."
        ),
    ),
    Source(
        key="acled_full",
        name="ACLED event-level export",
        publisher="Armed Conflict Location & Event Data Project",
        url="https://acleddata.com/data-export-tool/",
        licence="Free for non-commercial use with registration and citation",
        join_key="event date, admin1, event_type",
        why=(
            "The supplied file is a weekly admin-unit aggregate. The event-level export carries "
            "point coordinates and actor names, which would replace the centroid approximation "
            "that currently limits conflict-to-lane distances to hundreds of kilometres."
        ),
        needs_auth=True,
    ),
    Source(
        key="gfw_sar_global",
        name="Global Fishing Watch SAR detections and AIS",
        publisher="Global Fishing Watch",
        url="https://globalfishingwatch.org/data-download/",
        licence="CC BY-SA 4.0 (API key required)",
        join_key="scene id, detection position",
        why=(
            "Extends the detection window beyond the supplied fortnight and adds vessel-identity "
            "attributes, which would let the dark-spot classifier be validated out of time as "
            "well as out of space."
        ),
        needs_auth=True,
    ),
    Source(
        key="kaggle_harboriq",
        name="HarborIQ maritime traffic intelligence (ships_cleaned.csv)",
        publisher="Kaggle - kavyachauhan05",
        url="https://www.kaggle.com/datasets/kavyachauhan05/harboriq-maritime-traffic-intelligence",
        licence="Per Kaggle dataset terms",
        join_key="MMSI",
        why=(
            "Listed in the competition's own 'Data Links' document. Provides vessel particulars "
            "against MMSI, which would let the matched half of the detection set be broken down "
            "by flag, type and age - the natural next cut of the dark-fleet question."
        ),
        needs_auth=True,
    ),
    Source(
        key="kaggle_mmsi_daily",
        name="MMSI daily AIS CSVs",
        publisher="Kaggle - artemsmirnov1109",
        url="https://www.kaggle.com/datasets/artemsmirnov1109/mmsidailycsvs10v22020",
        licence="Per Kaggle dataset terms",
        join_key="MMSI, date",
        why=(
            "A dense AIS track history, useful for asking whether a vessel that appears dark in "
            "one corridor was transmitting normally days earlier elsewhere - the strongest "
            "available evidence that a switch-off was deliberate."
        ),
        needs_auth=True,
    ),
    Source(
        key="kaggle_indian_ocean_sar",
        name="Indian Ocean SAR vessel detections",
        publisher="Kaggle - shubh5106",
        url="https://www.kaggle.com/datasets/shubh5106/indian-ocean-sar-vessel-detections",
        licence="Per Kaggle dataset terms",
        join_key="scene id",
        why="The published source of the supplied detection file; kept here for provenance.",
        needs_auth=True,
    ),
    Source(
        key="natural_earth_coastline",
        name="Natural Earth 1:110m coastline",
        publisher="Natural Earth",
        url="https://www.naturalearthdata.com/downloads/110m-physical-vectors/",
        licence="Public domain",
        join_key="geometry",
        why=(
            "Would add a conventional basemap and a true distance-to-coast feature. The maps here "
            "use the detection cloud instead, which needs no dependency and no download."
        ),
    ),
)


def list_sources() -> list[dict]:
    return [s.__dict__ for s in SOURCES]


def fetch(key: str, dest: Path | None = None, timeout: int = 30) -> Path | None:
    """Attempt a download. Returns the path written, or None with a clear log line.

    Sources marked ``needs_auth`` are never fetched automatically: they require a
    registered account or an API key, and quietly failing on a login wall is worse
    than saying so.
    """
    source = next((s for s in SOURCES if s.key == key), None)
    if source is None:
        raise KeyError(f"unknown source '{key}'; try --list")
    if source.needs_auth:
        LOG.warning(
            "%s requires an account or API key. Download manually from %s and place it in %s",
            source.name,
            source.url,
            DATA_RAW,
        )
        return None

    dest = dest or DATA_RAW / f"{key}.raw"
    try:
        import urllib.request

        LOG.info("fetching %s from %s", source.name, source.url)
        with urllib.request.urlopen(source.url, timeout=timeout) as response:
            dest.write_bytes(response.read())
        LOG.info("wrote %s (%d bytes)", dest, dest.stat().st_size)
        return dest
    except Exception as exc:
        LOG.warning(
            "could not fetch %s (%s). The pipeline does not need it; download manually from %s if wanted.",
            source.name,
            exc.__class__.__name__,
            source.url,
        )
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="print the declared open sources")
    parser.add_argument("--fetch", metavar="KEY", help="attempt to download one source")
    args = parser.parse_args(argv)

    if args.list or not args.fetch:
        print(json.dumps(list_sources(), indent=2))
        return 0
    fetch(args.fetch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
