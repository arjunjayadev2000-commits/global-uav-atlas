"""Stage 10 - export a star schema and the analysis tables for the Power BI (.pbix) submission."""

# =====================================================================================================
# ANNOTATED SOURCE - Stage 10: Power BI tables (see powerbi/POWERBI_BUILD_GUIDE.md)
# -----------------------------------------------------------------------------------------------------
# Fact tables: FactCatalogue (every catalogued object with type, owner, orbit, launch and re-entry dates),
# FactSatellites2014 (the CDM census), FactPopulationYear, FactLaunches, FactStormDaily (Dst by day),
# FactFiresMonthly. Dimension: DimDate. Plus the analysis tables used on the dashboard pages. Runs last.
# =====================================================================================================
import zipfile

import pandas as pd

from common import CLEAN, PBI, TAB

print("Stage 10: Power BI export")
c = pd.read_parquet(CLEAN / "satcat.parquet")
cat = c[["OBJECT_NAME", "NORAD_CAT_ID", "type", "owner", "site_country", "constellation", "launch", "decay", "regime",
         "PERIGEE", "APOGEE", "INCLINATION", "alt_mean", "operational"]].rename(columns={"launch": "LAUNCH_DATE", "decay": "DECAY_DATE"})
cdm = pd.read_parquet(CLEAN / "cdm_satellites.parquet")
s14 = cdm[["Name", "Country", "Operator_Owner", "Users", "user_primary", "military_any", "Purpose", "purpose_group", "Class_of_Orbit",
           "Perigee_km", "Apogee_km", "incl_deg", "geo_lon_deg", "Launch_Mass_kg", "Power_watts", "launch", "Anticipated_Lifetime",
           "age_yrs", "beyond_design_life", "Launch_Site", "Launch_Vehicle", "Country_of_Contractor"]].rename(columns={"launch": "LAUNCH_DATE"})
dst = pd.read_parquet(CLEAN / "dst.parquet")
dst["day"] = (dst.hours // 24).astype(int)
dd = dst.groupby(["period", "day"]).dst.min().rename("min_dst").reset_index()
f = pd.read_parquet(CLEAN / "fires.parquet")
fm = f.groupby([pd.Grouper(key="date", freq="MS"), "satellite", "daynight"]).size().rename("detections").reset_index()
dates = pd.DataFrame({"DATE": pd.date_range("1957-01-01", "2026-12-31")})
dates["YEAR"], dates["DECADE"] = dates.DATE.dt.year, (dates.DATE.dt.year // 10 * 10).astype(str) + "s"
out = {"FactCatalogue.csv": cat, "FactSatellites2014.csv": s14, "FactStormDaily.csv": dd, "FactFiresMonthly.csv": fm, "DimDate.csv": dates}
for name, df in out.items():
    df.to_csv(PBI / name, index=False)
    print(f"  {name}: {len(df):,} rows")
for t in sorted(TAB.glob("t*.csv")):
    pd.read_csv(t).to_csv(PBI / t.name, index=False)
with zipfile.ZipFile(PBI / "powerbi_tables.zip", "w", zipfile.ZIP_DEFLATED) as z:
    for p in sorted(PBI.glob("*.csv")):
        z.write(p, p.name)
