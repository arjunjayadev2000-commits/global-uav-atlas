"""Shared paths, chart style, look-up tables and helpers for the Theme 6.1 (satellites) analysis."""

# =====================================================================================================
# ANNOTATED SOURCE - common.py (shared toolkit imported by every stage)
# -----------------------------------------------------------------------------------------------------
# Paths, one chart style for every figure, the metrics store (data/metrics.json: every number quoted in the
# booklet and the deck is written here and read back by the report builders), and the look-up tables that
# turn catalogue codes into readable names (owner codes -> countries, launch-site codes -> countries,
# satellite names -> constellations).
# =====================================================================================================
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW, OPEN, CLEAN = ROOT / "data" / "raw", ROOT / "data" / "open", ROOT / "data" / "clean"
FIG, TAB, PBI = ROOT / "figures", ROOT / "tables", ROOT / "powerbi"
METRICS = ROOT / "data" / "metrics.json"
for p in (CLEAN, FIG, TAB, PBI):
    p.mkdir(parents=True, exist_ok=True)

SNAPSHOT_CDM = pd.Timestamp("2014-01-31")     # the CDM satellite table is an active-satellite census of about this date
SNAPSHOT_UCS20 = pd.Timestamp("2020-04-01")   # UCS Satellite Database, 1 April 2020 edition (open source)
CATALOGUE_DATE = pd.Timestamp("2026-09-21")   # last launch in the open SATCAT mirror used here
EARTH_R = 6371.0

# ---------------------------------------------------------------- chart style (same house style as the Theme 6.2 study)
C = {"blue": "#2a78d6", "orange": "#eb6834", "aqua": "#1baf7a", "yellow": "#eda100", "magenta": "#e87ba4",
     "green": "#008300", "violet": "#4a3aa7", "red": "#e34948", "ink": "#0b0b0b", "ink2": "#52514e",
     "muted": "#8a8984", "grid": "#e4e3df", "land": "#ecebe6", "sea": "#fcfcfb", "navy": "#1f3b5c"}
SERIES = [C["blue"], C["orange"], C["aqua"], C["yellow"], C["magenta"], C["green"], C["violet"], C["red"]]
plt.rcParams.update({
    "font.family": "Liberation Sans", "font.size": 9, "axes.titlesize": 10.5, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "axes.labelsize": 9, "axes.edgecolor": C["muted"], "axes.labelcolor": C["ink2"],
    "xtick.color": C["ink2"], "ytick.color": C["ink2"], "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": C["grid"], "grid.linewidth": 0.6, "axes.axisbelow": True,
    "legend.frameon": False, "legend.fontsize": 8, "figure.dpi": 110, "savefig.dpi": 200, "savefig.bbox": "tight",
    "lines.linewidth": 1.8,
})


def save(fig, name):
    """Save a chart as figures/<name>.png (captions and numbers are added by the booklet)."""
    fig.savefig(FIG / f"{name}.png", facecolor="white")
    plt.close(fig)
    print("  fig ->", name)


def table(df, name, index=False):
    """Save a result table as tables/<name>.csv."""
    df.to_csv(TAB / f"{name}.csv", index=index)
    print("  tab ->", name)


def put_metrics(**kw):
    """Add headline numbers to data/metrics.json (read by the booklet, deck and Word builders)."""
    m = json.loads(METRICS.read_text()) if METRICS.exists() else {}
    m.update({k: (v.item() if hasattr(v, "item") else v) for k, v in kw.items()})
    METRICS.write_text(json.dumps(m, indent=2, default=str))


def get_metrics():
    return json.loads(METRICS.read_text())


# ---------------------------------------------------------------- look-up tables
# SATCAT owner codes -> country / bloc (CelesTrak convention; CIS = Russia and the former USSR)
OWNER = {"US": "USA", "CIS": "Russia", "PRC": "China", "IND": "India", "JPN": "Japan", "FR": "France", "UK": "UK",
         "ESA": "Europe (ESA/EU)", "EUME": "Europe (ESA/EU)", "EUTE": "Europe (ESA/EU)", "GER": "Germany", "IT": "Italy",
         "SPN": "Spain", "CA": "Canada", "SKOR": "South Korea", "ISRA": "Israel", "IRAN": "Iran", "TURK": "Turkey",
         "UAE": "UAE", "AUS": "Australia", "ARGN": "Argentina", "BRAZ": "Brazil", "SING": "Singapore",
         "PAKI": "Pakistan", "NKOR": "North Korea", "ROC": "Taiwan", "FIN": "Finland", "LUXE": "Luxembourg",
         "SES": "Luxembourg", "ITSO": "Intelsat", "GLOB": "Globalstar", "ORB": "Orbcomm", "O3B": "Luxembourg",
         "TBD": "Unknown", "ISS": "ISS partners"}
# launch-site codes -> launching country
SITE = {"AFETR": "USA", "AFWTR": "USA", "WLPIS": "USA", "KODAK": "USA", "KWAJ": "USA", "SEAL": "Sea Launch",
        "PLMSC": "Russia", "TYMSC": "Russia", "VOSTO": "Russia", "KYMSC": "Russia", "DLS": "Russia", "SVOBO": "Russia",
        "TAISC": "China", "JSC": "China", "XICLF": "China", "WSC": "China", "YSLA": "China", "SCSLA": "China",
        "SRILR": "India", "FRGUI": "Europe", "TANSC": "Japan", "KSCUT": "Japan", "RLLB": "New Zealand",
        "NSC": "South Korea", "SEMLS": "Iran", "SMTS": "Iran", "YAVNE": "Israel", "SNMLP": "Italy/Kenya",
        "HGSTR": "Algeria/France", "ERAS": "USA (air launch)", "WRAS": "USA (air launch)"}
# satellite-name prefixes -> constellation / programme
CONSTELLATION = [("STARLINK", "Starlink (US)"), ("ONEWEB", "OneWeb (UK)"), ("KUIPER", "Kuiper (US)"),
                 ("QIANFAN", "Qianfan (China)"), ("HULIANWANG", "Guowang (China)"), ("GUOWANG", "Guowang (China)"),
                 ("YAOGAN", "Yaogan ISR (China)"), ("FLOCK", "Planet Flock (US)"), ("LEMUR", "Spire Lemur (US)"),
                 ("IRIDIUM", "Iridium (US)"), ("GLOBALSTAR", "Globalstar (US)"), ("ORBCOMM", "Orbcomm (US)"),
                 ("JILIN", "Jilin-1 (China)"), ("GAOFEN", "Gaofen (China)")]


def constellation(name):
    n = str(name).upper()
    for key, lab in CONSTELLATION:
        if n.startswith(key):
            return lab
    return "Other"


def regime(perigee, apogee, period):
    """Orbit regime from catalogue elements: LEO / MEO / GEO / HEO."""
    perigee, apogee, period = map(np.asarray, (perigee, apogee, period))
    out = np.full(len(perigee), "Other", dtype=object)
    out[(apogee < 2000)] = "LEO"
    out[(perigee >= 2000) & (apogee < 34000)] = "MEO"
    out[(period >= 1400) & (period <= 1480) & (perigee > 34000)] = "GEO"
    out[(perigee < 2000) & (apogee >= 2000)] = "HEO"
    return out
