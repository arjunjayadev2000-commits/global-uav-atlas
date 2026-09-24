"""Stage 1 - load, validate, clean and feature-engineer both datasets."""

# =====================================================================================================
# ANNOTATED SOURCE - Stage 1: data preparation (report Chapter 4, 'Data')
# -----------------------------------------------------------------------------------------------------
# INPUT   data/raw: ACLED Middle-East weekly aggregates (Excel) and the Sentinel-1 SAR vessel detections (CSV).
# OUTPUT  data/clean/acled_clean.parquet and sar_clean.parquet (cleaned, with new columns);
#         tables t4_1-t4_4 (dataset summaries, cleaning log, attribute dictionary); metrics.
# STEPS   1. ACLED: drop exact duplicates, drop the partial 2014 week, check for negative counts, fill missing
#            population exposure, and add flags (GCC state, at sea, stand-off strike, political violence)
#            plus the distance from each province to every chokepoint.
#         2. SAR: drop duplicate detections, keep only confident detections (presence >= 0.80), check the
#            MMSI identity number, and add: dark / not dark, size class, sea region, flag state, distance
#            to the nearest chokepoint.
#         3. Link the two datasets: for every ship, the distance to the nearest province with war-time
#            political violence (1-7 Mar 2026) and the number of violent events within 500 km.
# KEY IDEA 'Dark' = the radar saw a hull, but no AIS identity signal could be matched to it.
#          Large ships (>= 100 m) must carry AIS by law (SOLAS), so a dark large ship is a meaningful signal.
# =====================================================================================================

import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

from common import (ACLED_XLSX, CLEAN, SAR_CSV, CHOKEPOINTS, assign_region, flag_class,
                    haversine_km, mmsi_flag, put_metrics, table)

print("Stage 1: preprocessing")
# Cleaning log: every step records how many rows it touched. It is printed and saved as Table 4.3, so an
# assessor can audit the cleaning.
log = []

# ============================================================ ACLED (conflict)
# ---- ACLED conflict data ----
a = pd.read_excel(ACLED_XLSX)
n0 = len(a)
log.append(("ACLED", "Rows loaded", n0))
# Remove rows that are exact copies of another row.
dups = a.duplicated().sum()
a = a.drop_duplicates()
log.append(("ACLED", "Exact duplicate rows removed", int(dups)))
# The file carries a single 2014-12-27 week (partial ramp-up of coverage); ACLED ME coverage is
# complete from 2015 onwards, so analysis windows start 2015-01-03.
early = (a.WEEK < "2015-01-01").sum()
a = a[a.WEEK >= "2015-01-01"]
log.append(("ACLED", "Pre-2015 partial-coverage rows dropped", int(early)))
# Sanity check: event and fatality counts can never be negative (none were found).
neg = ((a.EVENTS < 0) | (a.FATALITIES < 0)).sum()
log.append(("ACLED", "Negative counts found", int(neg)))
# Population exposure is missing where ACLED could not compute it (mostly sea / sparse areas).
# Missing population exposure: fill with the median of the same province over time; if the province never has a
# value (mostly sea areas), use 0.
miss_pop = a.POPULATION_EXPOSURE.isna().sum()
a["POP_EXPOSURE_FILLED"] = a.groupby("ID").POPULATION_EXPOSURE.transform(lambda s: s.fillna(s.median()))
a["POP_EXPOSURE_FILLED"] = a["POP_EXPOSURE_FILLED"].fillna(0)
log.append(("ACLED", "Population exposure NaNs imputed (ADMIN1 median, else 0)", int(miss_pop)))
a["YEAR"] = a.WEEK.dt.year
# New analysis flags (True/False columns):
#   MARITIME = event recorded at sea; REMOTE_VIOLENCE and DRONE_MISSILE = stand-off attacks (air/drone strike,
#   shelling/missile); POLITICAL_VIOLENCE = excludes peaceful protest; GCC = one of the six Gulf states.
a["MARITIME"] = a.COUNTRY.isin(["Indian Ocean", "Mediterranean Sea"])
a["REMOTE_VIOLENCE"] = a.EVENT_TYPE.eq("Explosions/Remote violence")
a["DRONE_MISSILE"] = a.SUB_EVENT_TYPE.isin(["Air/drone strike", "Shelling/artillery/missile attack"])
a["POLITICAL_VIOLENCE"] = a.DISORDER_TYPE.str.contains("Political violence")
GCC = ["Saudi Arabia", "United Arab Emirates", "Qatar", "Kuwait", "Bahrain", "Oman"]
a["GCC"] = a.COUNTRY.isin(GCC)
# Distance of each ADMIN1 centroid to every chokepoint (km).
# Distance (km) from each province centre to each chokepoint: used for the chokepoint conflict index in Stage 3.
for cp, (la, lo) in CHOKEPOINTS.items():
    a["D_" + cp] = haversine_km(a.CENTROID_LATITUDE.values, a.CENTROID_LONGITUDE.values, la, lo)
a.to_parquet(CLEAN / "acled_clean.parquet", index=False)
log.append(("ACLED", "Rows after cleaning", len(a)))

# Table 4.1: a one-glance summary of the conflict dataset.
acled_summary = pd.DataFrame({
    "Parameter": ["Study period", "Weeks covered", "Countries / sea areas", "ADMIN1 units",
                  "Event-type classes", "Sub-event classes", "Total events", "Total fatalities",
                  "Rows (country-admin1-week-subevent)"],
    "Value": [f"{a.WEEK.min():%d %b %Y} - {a.WEEK.max():%d %b %Y}", a.WEEK.nunique(), a.COUNTRY.nunique(),
              a.ID.nunique(), a.EVENT_TYPE.nunique(), a.SUB_EVENT_TYPE.nunique(),
              f"{a.EVENTS.sum():,}", f"{a.FATALITIES.sum():,}", f"{len(a):,}"],
})
table(acled_summary, "t4_1_acled_summary")

# ============================================================ SAR vessel detections
# ---- Sentinel-1 SAR ship detections ----
s = pd.read_csv(SAR_CSV)
log.append(("SAR", "Rows loaded", len(s)))
# The same ship at the same spot in the same satellite image is one ship: remove repeats.
d = s.duplicated(["scene_id", "lat", "lon"]).sum()
s = s.drop_duplicates(["scene_id", "lat", "lon"])
log.append(("SAR", "Duplicate detections (same scene & position) removed", int(d)))
s["ts"] = pd.to_datetime(s.timestamp.str.replace(" UTC", "", regex=False))
s["date"] = s.ts.dt.normalize()
# Sanity check on coordinates (none were invalid).
bad_geo = (~s.lat.between(-90, 90) | ~s.lon.between(-180, 180)).sum()
log.append(("SAR", "Invalid coordinates", int(bad_geo)))
# Keep only detections the radar model is at least 80% sure are vessels; weaker ones may be waves, rocks or
# noise.
low_conf = (s.presence_score < 0.8).sum()
s = s[s.presence_score >= 0.8]
log.append(("SAR", "Low-confidence detections dropped (presence < 0.80)", int(low_conf)))
# MMSI validity: 9-digit MIDs 2xx-7xx are ship stations; anything else is malformed/spoof-suspect.
# MMSI check: a real ship's identity number has 9 digits and starts with 2-7. Anything else is malformed and
# possibly spoofed.
s["mmsi_valid"] = s.mmsi.between(200_000_000, 799_999_999)
s["mmsi_malformed"] = s.mmsi.notna() & ~s.mmsi_valid
log.append(("SAR", "Malformed MMSI values flagged (outside 2xx-7xx MID range)", int(s.mmsi_malformed.sum())))
# AIS status. 'unmatched' = SAR saw a hull but no AIS track could be confidently associated.
# THE KEY VARIABLE. dark = True when the radar saw a hull but no AIS track could be matched to it.
# dark_strict is a stricter version (no MMSI at all), used in the robustness checks.
s["dark"] = s.matched_category.eq("unmatched")
s["dark_strict"] = s.mmsi.isna()
# Large = 100 m or more: merchant ships and tankers that must carry AIS under the SOLAS convention.
s["large"] = s.length_m >= 100          # merchant/tanker class - AIS carriage mandatory under SOLAS
s["mid_size"] = s.length_m.between(40, 100)
s["size_class"] = pd.cut(s.length_m, [0, 25, 40, 100, 200, 500],
                         labels=["<25 m", "25-40 m", "40-100 m", "100-200 m", ">200 m"])
s["likely_fishing"] = s.fishing_score >= 0.5
# Add the sea region, flag state and flag class for every detection (helpers in common.py).
s["region"] = assign_region(s.lat.values, s.lon.values)
s["flag"] = mmsi_flag(s.mmsi.where(s.mmsi_valid)).values
s["flag_class"] = s.flag.map(flag_class)
for cp, (la, lo) in CHOKEPOINTS.items():
    s["D_" + cp] = haversine_km(s.lat.values, s.lon.values, la, lo)
# Distance to the nearest chokepoint = the smallest of the individual distances.
s["dist_chokepoint_km"] = s[[c for c in s.columns if c.startswith("D_")]].min(axis=1)

# --- conflict exposure of every detection (ACLED weeks overlapping 1-14 Mar 2026)
# At-sea ACLED rows carry a nominal basin centroid, not a real position -> land/littoral ADMIN1s only.
# ---- Linking ships to the war ----
# War-time political violence on land/coast in the first war week. At-sea ACLED rows are left out because they
# carry a nominal basin centre, not a real position.
war = a[(a.WEEK >= "2026-02-28") & (a.WEEK <= "2026-03-07") & a.POLITICAL_VIOLENCE & ~a.MARITIME]
cent = war.groupby(["ID", "CENTROID_LATITUDE", "CENTROID_LONGITUDE"]).EVENTS.sum().reset_index()
# A BallTree is a fast spatial index. With the 'haversine' metric it measures true distances on the globe, so
# each of 106,533 ships finds its nearest violent province in milliseconds.
tree = BallTree(np.radians(cent[["CENTROID_LATITUDE", "CENTROID_LONGITUDE"]].values), metric="haversine")
X = np.radians(s[["lat", "lon"]].values)
dist, _ = tree.query(X, k=1)
s["dist_conflict_km"] = dist[:, 0] * 6371
# Count the violent events within 500 km of each ship (radius in radians = km / Earth radius). log1p gives a
# smoother version for the model.
ind = tree.query_radius(X, r=500 / 6371)
ev = cent.EVENTS.values
s["conflict_events_500km"] = [ev[i].sum() for i in ind]
s["log_conflict_500"] = np.log1p(s.conflict_events_500km)

s.to_parquet(CLEAN / "sar_clean.parquet", index=False)
log.append(("SAR", "Rows after cleaning", len(s)))

# Table 4.2 (SAR dataset summary), Table 4.3 (cleaning log) and Table 4.4 (attribute dictionary).
sar_summary = pd.DataFrame({
    "Parameter": ["Observation window", "Sentinel-1 scenes", "Vessel detections",
                  "Detections matched to AIS", "Detections with no AIS match ('dark')",
                  "Median vessel length (m)", "Large vessels (>=100 m)", "Distinct MMSIs",
                  "Sea regions defined"],
    "Value": [f"{s.ts.min():%d %b %Y} - {s.ts.max():%d %b %Y}", f"{s.scene_id.nunique():,}", f"{len(s):,}",
              f"{(~s.dark).sum():,} ({(~s.dark).mean():.1%})", f"{s.dark.sum():,} ({s.dark.mean():.1%})",
              f"{s.length_m.median():.0f}", f"{s.large.sum():,}", f"{s.mmsi.nunique():,}",
              s.region.nunique()],
})
table(sar_summary, "t4_2_sar_summary")
table(pd.DataFrame(log, columns=["Dataset", "Step", "Count"]), "t4_3_cleaning_log")

attr = pd.DataFrame([
    ("scene_id", "SAR", "Sentinel-1A scene identifier (image footprint)"),
    ("timestamp", "SAR", "Image acquisition time (UTC)"),
    ("lat / lon", "SAR", "Detected hull position"),
    ("presence_score", "SAR", "CNN confidence that the object is a vessel (0-1)"),
    ("length_m", "SAR", "Estimated hull length from SAR backscatter"),
    ("mmsi", "SAR", "AIS identity of the matched track (blank when none)"),
    ("matching_score", "SAR", "Confidence of the SAR-AIS association"),
    ("fishing_score", "SAR", "Model probability that the hull is a fishing vessel"),
    ("matched_category", "SAR", "AIS vessel class, or 'unmatched' (AIS-dark)"),
    ("WEEK", "ACLED", "Week (Saturday start) of aggregation"),
    ("COUNTRY / ADMIN1", "ACLED", "Location of events (incl. 'Indian Ocean', 'Mediterranean Sea')"),
    ("EVENT_TYPE / SUB_EVENT_TYPE", "ACLED", "6 event types, 25 sub-event types"),
    ("EVENTS / FATALITIES", "ACLED", "Counts per week-location-type"),
    ("POPULATION_EXPOSURE", "ACLED", "Population within reach of events"),
    ("CENTROID_LAT/LON", "ACLED", "ADMIN1 centroid used for geo-joins"),
], columns=["Attribute", "Dataset", "Description"])
table(attr, "t4_4_attributes")

# Store the headline dataset numbers used in the report text.
put_metrics(
    acled_rows=len(a), acled_events=int(a.EVENTS.sum()), acled_fat=int(a.FATALITIES.sum()),
    acled_weeks=int(a.WEEK.nunique()), acled_admin1=int(a.ID.nunique()),
    sar_rows=len(s), sar_scenes=int(s.scene_id.nunique()), sar_dark_share=float(s.dark.mean()),
    sar_dark_strict_share=float(s.dark_strict.mean()), sar_large=int(s.large.sum()),
    sar_large_dark_share=float(s[s.large].dark.mean()), sar_low_conf_dropped=int(low_conf),
    sar_mmsi_malformed=int(s.mmsi_malformed.sum()), sar_distinct_mmsi=int(s.mmsi.nunique()),
    war_centroids=len(cent),
)
print(pd.DataFrame(log))
