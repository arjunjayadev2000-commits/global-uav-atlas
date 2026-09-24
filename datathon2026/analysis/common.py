"""Shared paths, styling, geography and helpers for the Datathon-2026 analysis."""

# =====================================================================================================
# ANNOTATED SOURCE - common.py (shared toolkit imported by every analysis stage)
# -----------------------------------------------------------------------------------------------------
# WHAT IT DOES   Holds everything the stages share so that each number and chart is made the same way:
#                folder paths, chart styling, the save helpers, the metrics store, the sea-region and
#                chokepoint geography, the distance formula, the base map, and the MMSI-to-flag decoder.
# WHY IT MATTERS Every figure and every number quoted in the reports comes through the helpers here.
#                'put_metrics' writes each headline number to data/metrics.json; the report builders read
#                that file, so no number in the PDF or Word files is typed by hand.
# =====================================================================================================

import json
from pathlib import Path

import matplotlib
# 'Agg' draws charts straight to image files (no screen needed), so the pipeline runs on any server.
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Folder layout. ROOT is the datathon2026 folder; everything else is found relative to it, so the project can be
# copied anywhere.
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
CLEAN = ROOT / "data" / "clean"
FIG = ROOT / "figures"
TAB = ROOT / "tables"
PBI = ROOT / "powerbi"
METRICS = ROOT / "data" / "metrics.json"
# Create output folders on first run.
for p in (CLEAN, FIG, TAB, PBI):
    p.mkdir(parents=True, exist_ok=True)

# The two datasets supplied by CDM: ACLED conflict aggregates and the Sentinel-1 SAR vessel detections.
ACLED_XLSX = RAW / "Middle-East_aggregated_data_up_to_week_of-2026-06-27.xlsx"
SAR_CSV = RAW / "indian ocean vessel - Mar 26.csv"

# ---------------------------------------------------------------- styling
# Categorical order from the validated reference palette (dataviz skill).
# Colour palette. Blue and orange are the main pair; red is kept for warnings. The same colours are used in
# every chart.
C = {
    "blue": "#2a78d6", "orange": "#eb6834", "aqua": "#1baf7a", "yellow": "#eda100",
    "magenta": "#e87ba4", "green": "#008300", "violet": "#4a3aa7", "red": "#e34948",
    "ink": "#0b0b0b", "ink2": "#52514e", "muted": "#8a8984", "grid": "#e4e3df",
    "land": "#ecebe6", "sea": "#fcfcfb",
}
SERIES = [C["blue"], C["orange"], C["aqua"], C["yellow"], C["magenta"], C["green"], C["violet"], C["red"]]

# One house style for all charts: clean axes, light grid, left-aligned bold titles, 200 dpi output for print.
plt.rcParams.update({
    "font.family": "Liberation Sans", "font.size": 9, "axes.titlesize": 10.5,
    "axes.titleweight": "bold", "axes.titlelocation": "left", "axes.labelsize": 9,
    "axes.edgecolor": C["muted"], "axes.labelcolor": C["ink2"], "xtick.color": C["ink2"],
    "ytick.color": C["ink2"], "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": C["grid"], "grid.linewidth": 0.6, "axes.axisbelow": True,
    "legend.frameon": False, "legend.fontsize": 8, "figure.dpi": 110, "savefig.dpi": 200,
    "savefig.bbox": "tight", "lines.linewidth": 1.8,
})


# Save a chart as figures/<name>.png. Figure numbers are stripped from chart titles because the report adds its
# own numbered captions.
def save(fig, name):
    # Captions ("Figure x.y ...") are set in the report; charts keep only the descriptive title.
    import re
    strip = lambda s: re.sub(r"^Figure \d+\.\d+\s+", "", s)
    for ax in fig.axes:
        ax.set_title(strip(ax.get_title(loc="left")), loc="left")
    if fig._suptitle is not None:
        fig._suptitle.set_text(strip(fig._suptitle.get_text()))
    fig.savefig(FIG / f"{name}.png", facecolor="white")
    plt.close(fig)
    print("  fig ->", name)


# Save a result table as tables/<name>.csv. The report and the Power BI export read these files.
def table(df, name, index=False):
    df.to_csv(TAB / f"{name}.csv", index=index)
    print("  tab ->", name)


# Add or overwrite headline numbers in data/metrics.json (e.g. put_metrics(hormuz_large_dark=0.74)).
# The report builders read this file, so the text always matches the latest run.
def put_metrics(**kw):
    m = json.loads(METRICS.read_text()) if METRICS.exists() else {}
    m.update({k: (v.item() if hasattr(v, "item") else v) for k, v in kw.items()})
    METRICS.write_text(json.dumps(m, indent=2, default=str))


# Read all headline numbers back (used by later stages that build on earlier results).
def get_metrics():
    return json.loads(METRICS.read_text())


# ---------------------------------------------------------------- geography
# Maritime chokepoints (approximate centre points).
# Approximate centre points (latitude, longitude) of the maritime chokepoints used for distances.
CHOKEPOINTS = {
    "Strait of Hormuz": (26.57, 56.25),
    "Bab-el-Mandeb": (12.58, 43.33),
    "Suez Canal": (30.45, 32.35),
    "Strait of Malacca": (2.50, 101.20),
    "Bosphorus": (41.12, 29.07),
    "Strait of Gibraltar": (35.95, -5.60),
    "Taiwan Strait": (24.50, 119.50),
    "Cape of Good Hope": (-34.40, 18.50),
}

# Sea regions as (name, lat_min, lat_max, lon_min, lon_max); first match wins.
# Sea regions as boxes: (name, lat_min, lat_max, lon_min, lon_max). Order matters: the small boxes (Hormuz, Bab-
# el-Mandeb) come first so a ship inside them is not swallowed by the larger sea around them.
REGIONS = [
    ("Strait of Hormuz", 25.6, 27.3, 55.4, 57.3),
    ("Bab-el-Mandeb", 11.8, 13.4, 42.6, 43.9),
    ("Persian Gulf", 23.5, 30.6, 47.5, 56.6),
    ("Gulf of Oman", 21.8, 25.8, 56.6, 61.8),
    ("Red Sea", 13.4, 30.0, 32.0, 43.6),
    ("Gulf of Aden", 10.4, 15.6, 43.6, 51.6),
    ("Arabian Sea", -2.0, 25.8, 51.6, 77.6),
    ("Bay of Bengal", 4.0, 23.5, 77.6, 94.5),
    ("Strait of Malacca", -1.5, 7.5, 94.5, 104.6),
    ("South China Sea", -1.5, 23.5, 104.6, 121.5),
    ("East Asia Seas", 23.5, 46.0, 117.0, 146.0),
    ("Black Sea", 40.5, 47.5, 27.2, 42.0),
    ("Mediterranean", 30.0, 46.0, -6.0, 37.0),
    ("NW Europe & North Sea", 46.0, 72.0, -15.0, 32.0),
    ("Southern Indian Ocean", -45.0, -2.0, 30.0, 120.0),
    ("Atlantic (other)", -60.0, 72.0, -80.0, -6.0),
]
REGION_ORDER = [r[0] for r in REGIONS] + ["Pacific & Americas (other)"]
# Regions treated as India's maritime neighbourhood / Gulf conflict zone.
# Groupings used throughout: the Gulf war zone, the Red Sea zone and India's own seas.
GULF_CONFLICT = {"Strait of Hormuz", "Persian Gulf", "Gulf of Oman"}
RED_SEA_CONFLICT = {"Bab-el-Mandeb", "Red Sea", "Gulf of Aden"}
INDIA_SEAS = {"Arabian Sea", "Bay of Bengal"}


# Give every ship detection a sea-region name: walk the boxes in order; the first box that contains the point
# wins. Anything outside all boxes is 'Pacific & Americas (other)'.
def assign_region(lat, lon):
    out = np.full(len(lat), "Pacific & Americas (other)", dtype=object)
    done = np.zeros(len(lat), bool)
    for name, a, b, c, d in REGIONS:
        m = (~done) & (lat >= a) & (lat < b) & (lon >= c) & (lon < d)
        out[m] = name
        done |= m
    return out


# Great-circle distance in km between two points on the Earth (the 'haversine' formula, Earth radius 6,371 km).
# Works on whole columns at once.
def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


# Draw a plain base map (land, sea, coast, borders, lat/lon grid) on a chart axis, for the map figures.
def basemap_ax(ax, llcrnrlat, urcrnrlat, llcrnrlon, urcrnrlon, res="l", grid=10):
    from mpl_toolkits.basemap import Basemap
    m = Basemap(projection="cyl", llcrnrlat=llcrnrlat, urcrnrlat=urcrnrlat,
                llcrnrlon=llcrnrlon, urcrnrlon=urcrnrlon, resolution=res, ax=ax)
    m.drawmapboundary(fill_color=C["sea"], linewidth=0.4)
    m.fillcontinents(color=C["land"], lake_color=C["sea"], zorder=0)
    m.drawcoastlines(linewidth=0.35, color="#a5a39c")
    m.drawcountries(linewidth=0.25, color="#c3c2b7")
    if grid:
        m.drawparallels(np.arange(-90, 91, grid), labels=[1, 0, 0, 0], linewidth=0.2,
                        color="#d4d3cd", fontsize=7, dashes=[1, 2])
        m.drawmeridians(np.arange(-180, 181, grid), labels=[0, 0, 0, 1], linewidth=0.2,
                        color="#d4d3cd", fontsize=7, dashes=[1, 2])
    ax.grid(False)
    return m


# ---------------------------------------------------------------- MMSI -> flag
# MMSI decoder. The first three digits of a ship's 9-digit MMSI are its Maritime Identification Digits (MID),
# which name the flag state (ITU table). Example: 419 = India, 636 = Liberia.
MID = {
    "Cyprus": [209, 210, 212], "Germany": [211, 218], "Denmark": [219, 220], "Spain": [224, 225],
    "France": [226, 227, 228], "Malta": [215, 229, 248, 249, 256], "Finland": [230],
    "United Kingdom": [232, 233, 234, 235], "Gibraltar": [236], "Greece": [237, 239, 240, 241],
    "Netherlands": [244, 245, 246], "Italy": [247], "Ireland": [250], "Luxembourg": [253],
    "Portugal": [255, 263], "Norway": [257, 258, 259], "Poland": [261], "Sweden": [265, 266],
    "Turkey": [271], "Ukraine": [272], "Russia": [273], "Estonia": [276], "Latvia": [275],
    "Lithuania": [277], "Belgium": [205], "Croatia": [238], "Antigua & Barbuda": [304, 305],
    "Bahamas": [308, 309, 311], "Bermuda": [310], "Belize": [312], "Barbados": [314],
    "Canada": [316], "Cayman Islands": [319], "Jamaica": [339], "St Kitts & Nevis": [341],
    "Mexico": [345], "Honduras": [334], "USA": [338, 366, 367, 368, 369],
    "Panama": [351, 352, 353, 354, 355, 356, 357, 370, 371, 372, 373, 374],
    "St Vincent & Grenadines": [375, 376, 377], "Saudi Arabia": [403], "Bangladesh": [405],
    "Bahrain": [408], "China": [412, 413, 414], "Taiwan": [416], "Sri Lanka": [417], "India": [419],
    "Iran": [422], "Azerbaijan": [423], "Iraq": [425], "Israel": [428], "Japan": [431, 432],
    "Kazakhstan": [436], "Jordan": [438], "South Korea": [440, 441], "North Korea": [445],
    "Kuwait": [447], "Lebanon": [450], "Maldives": [455], "Mongolia": [457], "Oman": [461],
    "Pakistan": [463], "Qatar": [466], "Syria": [468], "UAE": [470, 471], "Yemen": [473, 475],
    "Hong Kong": [477], "Australia": [503], "Palau": [511], "New Zealand": [512],
    "Cambodia": [514, 515], "Cook Islands": [518], "Indonesia": [525], "Malaysia": [533],
    "Marshall Islands": [538], "Philippines": [548], "Singapore": [563, 564, 565, 566],
    "Thailand": [567], "Tuvalu": [572], "Vietnam": [574], "Vanuatu": [576, 577],
    "South Africa": [601], "Benin": [610], "Cameroon": [613], "Comoros": [616, 620],
    "Djibouti": [621], "Egypt": [622], "Gabon": [626], "Liberia": [636, 637], "Kenya": [634],
    "Mauritius": [645], "Nigeria": [657], "Sao Tome & Principe": [668], "Seychelles": [664],
    "Sierra Leone": [667], "Togo": [671], "Tanzania": [677], "Eswatini": [669],
    "Guinea-Bissau": [630], "Equatorial Guinea": [631], "Brazil": [710], "Argentina": [701],
    "Chile": [725], "Peru": [760], "Uruguay": [770], "Moldova": [214], "Georgia": [213],
}
MID_TO_FLAG = {mid: flag for flag, mids in MID.items() for mid in mids}

# ITF "flags of convenience" list (subset covering the registries decoded above).
# Flags of convenience (ITF list): open registries used by owners from other countries.
FOC = {"Antigua & Barbuda", "Bahamas", "Barbados", "Belize", "Bermuda", "Cambodia", "Cayman Islands",
       "Comoros", "Cyprus", "Equatorial Guinea", "Georgia", "Gibraltar", "Honduras", "Jamaica",
       "Lebanon", "Liberia", "Malta", "Marshall Islands", "Mauritius", "Moldova", "Mongolia",
       "North Korea", "Panama", "Sao Tome & Principe", "St Kitts & Nevis", "St Vincent & Grenadines",
       "Sri Lanka", "Vanuatu", "Tuvalu"}
# Registries repeatedly named in open-source reporting on post-2022 sanctions-evasion ("shadow") fleets.
# Registries repeatedly named in open-source reporting on the post-2022 sanctions-evasion ('shadow') tanker
# fleet. Used only as a group-level indicator, never as proof about any one ship.
SHADOW = {"Gabon", "Cameroon", "Comoros", "Sierra Leone", "Togo", "Cook Islands", "Palau", "Benin",
          "Djibouti", "Eswatini", "Guinea-Bissau", "Sao Tome & Principe", "Tanzania"}


# MMSI -> flag state. Only 9-digit numbers in the ship-station range (200,000,000-799,999,999) are decoded;
# others return None.
def mmsi_flag(mmsi):
    s = pd.Series(mmsi)
    mid = (s // 1_000_000).where(s.between(200_000_000, 799_999_999))
    return mid.map(lambda x: MID_TO_FLAG.get(int(x), "Other/undecoded") if pd.notna(x) else None)


# Flag state -> one of four classes: Shadow-fleet-associated, Flag of convenience, National flag,
# Other/undecoded.
def flag_class(flag):
    if flag is None or (isinstance(flag, float) and np.isnan(flag)):
        return None
    if flag in SHADOW:
        return "Shadow-fleet-associated"
    if flag in FOC:
        return "Flag of convenience"
    if flag == "Other/undecoded":
        return "Other/undecoded"
    return "National flag"
