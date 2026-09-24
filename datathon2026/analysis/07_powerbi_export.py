"""Stage 7 - export a clean star schema for the Power BI (.pbix) submission."""

# =====================================================================================================
# ANNOTATED SOURCE - Stage 7: tables for the Power BI dashboard (.pbix)
# -----------------------------------------------------------------------------------------------------
# Builds a STAR SCHEMA, the standard layout for Power BI:
#   - fact tables (one row per event or per ship detection): FactConflictWeekly, FactVesselDetections,
#     FactChokepointTransits;
#   - dimension tables (look-ups) they link to: DimAdmin1 (province, with coordinates) and DimDate (calendar).
# Also copies the analysis result tables the dashboard pages use, and zips everything into powerbi_tables.zip.
# The step-by-step build is in powerbi/POWERBI_BUILD_GUIDE.md. Runs last in run_all.py.
# =====================================================================================================

import pandas as pd

from common import CLEAN, GULF_CONFLICT, INDIA_SEAS, PBI, RED_SEA_CONFLICT, TAB

print("Stage 7: Power BI export")
a = pd.read_parquet(CLEAN / "acled_clean.parquet")
s = pd.read_parquet(CLEAN / "sar_clean.parquet")

# DimAdmin1: one row per province (ADMIN1) with country, coordinates, GCC/maritime flags and distances to
# chokepoints.
dim_admin = (a.groupby("ID").agg(COUNTRY=("COUNTRY", "first"), ADMIN1=("ADMIN1", "first"),
                                 LAT=("CENTROID_LATITUDE", "first"), LON=("CENTROID_LONGITUDE", "first"),
                                 GCC=("GCC", "first"), MARITIME=("MARITIME", "first"),
                                 KM_TO_HORMUZ=("D_Strait of Hormuz", "first"), KM_TO_BAB_EL_MANDEB=("D_Bab-el-Mandeb", "first"),
                                 KM_TO_SUEZ=("D_Suez Canal", "first"))
             .reset_index().rename(columns={"ID": "ADMIN1_ID"}))
# FactConflictWeekly: one row per week x province x event sub-type, with counts and flags.
fact_conf = a[["WEEK", "ID", "EVENT_TYPE", "SUB_EVENT_TYPE", "DISORDER_TYPE", "EVENTS", "FATALITIES",
               "POP_EXPOSURE_FILLED", "REMOTE_VIOLENCE", "DRONE_MISSILE", "POLITICAL_VIOLENCE"]].rename(
    columns={"ID": "ADMIN1_ID"})

# FactVesselDetections: one row per radar detection, with zone, size, AIS status (AIS_DARK) and conflict
# distances.
zone = {**{r: "Gulf war zone" for r in GULF_CONFLICT}, **{r: "Red Sea zone" for r in RED_SEA_CONFLICT},
        "Black Sea": "Black Sea war zone", **{r: "India's seas" for r in INDIA_SEAS}}
fact_ves = s.assign(ZONE=s.region.map(zone).fillna("Rest of world"), DETECTION_ID=range(1, len(s) + 1))[
    ["DETECTION_ID", "date", "ts", "scene_id", "lat", "lon", "region", "ZONE", "length_m", "size_class",
     "fishing_score", "matched_category", "dark", "large", "mmsi", "flag", "flag_class", "mmsi_malformed",
     "dist_conflict_km", "conflict_events_500km", "dist_chokepoint_km"]].rename(
    columns={"date": "DATE", "ts": "TIMESTAMP_UTC", "region": "REGION", "dark": "AIS_DARK", "large": "LARGE_100M"})

# DimDate: a calendar 2015-2026 with year, quarter, month and the Saturday week start used by ACLED.
dates = pd.DataFrame({"DATE": pd.date_range("2015-01-01", "2026-12-31")})
dates["YEAR"], dates["QUARTER"] = dates.DATE.dt.year, "Q" + dates.DATE.dt.quarter.astype(str)
dates["MONTH"], dates["WEEK_START"] = dates.DATE.dt.strftime("%Y-%m"), dates.DATE - pd.to_timedelta((dates.DATE.dt.dayofweek + 2) % 7, "D")

out = {
    "DimAdmin1.csv": dim_admin, "FactConflictWeekly.csv": fact_conf, "FactVesselDetections.csv": fact_ves,
    "DimDate.csv": dates,
}
for name, df in out.items():
    df.to_csv(PBI / name, index=False)
    print(f"  {name}: {len(df):,} rows")
# Analysis tables used on the dashboard pages (copied unchanged from tables/).
for t in ["t6_ccii_weekly", "t6_2_episodes", "t7_1_dark_by_region", "t7_4_dark_clusters", "t8_3_poi_risk",
          "t9_1_stock_decision", "t8_2_model_cv", "t9_6_iw_matrix", "t9_7_scenarios", "t9_2_robustness", "t9o_1_event_study", "t9o_3_war_premium", "t11_6_signatures", "t11_7_defence_budget", "t12_1_chokepoint_change", "t12_2_shipping_disruptions", "t12_3_effective_cover"]:
    pd.read_csv(TAB / f"{t}.csv").to_csv(PBI / f"{t}.csv", index=False)

# daily chokepoint transits (IMF PortWatch) for the Chokepoint Watch page
# FactChokepointTransits: daily ship crossings at 28 chokepoints since 2023 (IMF PortWatch).
pw = pd.read_csv(PBI.parent / "data" / "open" / "imf_portwatch_chokepoints_daily.csv", parse_dates=["date"])
pw = pw[pw.date >= "2023-01-01"].rename(columns={"date": "DATE", "portname": "CHOKEPOINT", "n_total": "TRANSITS", "n_tanker": "TANKERS"})
pw[["DATE", "CHOKEPOINT", "TRANSITS", "TANKERS"]].sort_values(["CHOKEPOINT", "DATE"]).to_csv(PBI / "FactChokepointTransits.csv", index=False)
print(f"  FactChokepointTransits.csv: {len(pw):,} rows")

# one zip holding every table, as referenced by POWERBI_BUILD_GUIDE.md
import zipfile
with zipfile.ZipFile(PBI / "powerbi_tables.zip", "w", zipfile.ZIP_DEFLATED) as z:
    for f in sorted(PBI.glob("*.csv")):
        z.write(f, f.name)
