"""Stage 7 - export a clean star schema for the Power BI (.pbix) submission."""
import pandas as pd

from common import CLEAN, GULF_CONFLICT, INDIA_SEAS, PBI, RED_SEA_CONFLICT, TAB

print("Stage 7: Power BI export")
a = pd.read_parquet(CLEAN / "acled_clean.parquet")
s = pd.read_parquet(CLEAN / "sar_clean.parquet")

dim_admin = (a.groupby("ID").agg(COUNTRY=("COUNTRY", "first"), ADMIN1=("ADMIN1", "first"),
                                 LAT=("CENTROID_LATITUDE", "first"), LON=("CENTROID_LONGITUDE", "first"),
                                 GCC=("GCC", "first"), MARITIME=("MARITIME", "first"),
                                 KM_TO_HORMUZ=("D_Strait of Hormuz", "first"), KM_TO_BAB_EL_MANDEB=("D_Bab-el-Mandeb", "first"),
                                 KM_TO_SUEZ=("D_Suez Canal", "first"))
             .reset_index().rename(columns={"ID": "ADMIN1_ID"}))
fact_conf = a[["WEEK", "ID", "EVENT_TYPE", "SUB_EVENT_TYPE", "DISORDER_TYPE", "EVENTS", "FATALITIES",
               "POP_EXPOSURE_FILLED", "REMOTE_VIOLENCE", "DRONE_MISSILE", "POLITICAL_VIOLENCE"]].rename(
    columns={"ID": "ADMIN1_ID"})

zone = {**{r: "Gulf war zone" for r in GULF_CONFLICT}, **{r: "Red Sea zone" for r in RED_SEA_CONFLICT},
        "Black Sea": "Black Sea war zone", **{r: "India's seas" for r in INDIA_SEAS}}
fact_ves = s.assign(ZONE=s.region.map(zone).fillna("Rest of world"), DETECTION_ID=range(1, len(s) + 1))[
    ["DETECTION_ID", "date", "ts", "scene_id", "lat", "lon", "region", "ZONE", "length_m", "size_class",
     "fishing_score", "matched_category", "dark", "large", "mmsi", "flag", "flag_class", "mmsi_malformed",
     "dist_conflict_km", "conflict_events_500km", "dist_chokepoint_km"]].rename(
    columns={"date": "DATE", "ts": "TIMESTAMP_UTC", "region": "REGION", "dark": "AIS_DARK", "large": "LARGE_100M"})

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
for t in ["t6_ccii_weekly", "t6_2_episodes", "t7_1_dark_by_region", "t7_4_dark_clusters", "t8_3_poi_risk",
          "t9_1_stock_decision", "t8_2_model_cv", "t9_6_iw_matrix", "t9_7_scenarios", "t9_2_robustness"]:
    pd.read_csv(TAB / f"{t}.csv").to_csv(PBI / f"{t}.csv", index=False)
