"""Stage 1 - load, validate, clean and feature-engineer the CDM datasets and the open-source catalogues."""

# =====================================================================================================
# ANNOTATED SOURCE - Stage 1: data preparation (booklet Chapter 1 and Annex B)
# -----------------------------------------------------------------------------------------------------
# CDM DATASETS (data/raw)
#   satellites.csv   1,167 active satellites (a census of about January 2014): owner, users, purpose, orbit, mass,
#                    power, launch date (Excel serial day), design life, contractor, launch site and vehicle.
#   labels.csv       hourly Dst geomagnetic index (nT) for three anonymised periods (space weather).
#   sunspots.csv     smoothed sunspot number for the same periods (solar activity).
#   fire_*_M6.csv    1.25 million MODIS fire detections (Terra and Aqua satellites), 2010-2020: what an Earth-
#                    observation constellation actually delivers on the ground.
# OPEN SOURCES (data/open)
#   satcat.csv       CelesTrak satellite catalogue to 21 Sep 2026 (70,793 objects: payloads, rocket bodies, debris).
#   ucs_2020.xls     UCS Satellite Database, 1 April 2020 (2,670 active satellites) - a second census.
#   unoosa_objects_launched.csv   objects launched per country per year (UNOOSA via Our World in Data).
# Every cleaning step is logged (Table: cleaning log).
# =====================================================================================================
import numpy as np
import pandas as pd

from common import CLEAN, OPEN, OWNER, RAW, SITE, SNAPSHOT_CDM, constellation, put_metrics, regime, table

print("Stage 1: preprocessing")
log = []

# ============================================================ CDM satellite census (2014)
s = pd.read_csv(RAW / "satellites.csv")
log.append(("CDM satellites", "Rows loaded", len(s)))
s["launch"] = pd.to_datetime(s.Date_of_Launch, unit="D", origin="1899-12-30", errors="coerce")   # Excel serial days
log.append(("CDM satellites", "Launch dates converted from Excel serial numbers (1 missing)", int(s.launch.isna().sum())))
# Users: fix the misspelling and keep the first-named user as the primary user; flag any military involvement.
s["Users"] = s.Users.str.replace("Commerical", "Commercial").str.strip()
s["user_primary"] = s.Users.str.split("/").str[0]
s["military_any"] = s.Users.str.contains("Military")
# Purpose groups (the 30+ raw labels folded into seven families a commander recognises)
def purpose_group(p):
    p = str(p)
    if "Communications" in p:
        return "Communications"
    if any(k in p for k in ("Navigation", "Global Positioning")):
        return "Navigation"
    # ISR (reconnaissance, surveillance, SIGINT) is folded into Earth observation: UCS 2020 files military imagers under
    # 'Earth Observation', so a separate ISR class would not compare across censuses. Military use is tracked via Users.
    if any(k in p for k in ("Reconnaissance", "Surveillance", "Signals", "Early Warning", "Electronic",
                            "Earth Observation", "Remote Sensing", "Earth Science", "Meteorology", "Imaging")):
        return "Earth observation & ISR"
    if "Technology" in p:
        return "Technology demonstration"
    if "Science" in p or "Physics" in p or "Astro" in p:
        return "Science"
    return "Other"
s["purpose_group"] = s.Purpose.map(purpose_group)
# Physical sanity checks: an orbital period under 80 minutes or an inclination above pi radians is impossible.
bad_period = s.Period_minutes < 80
bad_incl = s.Inclination_radians > np.pi
log.append(("CDM satellites", "Impossible orbital periods (< 80 min) set to missing", int(bad_period.sum())))
log.append(("CDM satellites", "Impossible inclinations (> 180 deg) set to missing", int(bad_incl.sum())))
s.loc[bad_period, "Period_minutes"] = np.nan
s.loc[bad_incl, "Inclination_radians"] = np.nan
s["incl_deg"] = np.degrees(s.Inclination_radians)
s["geo_lon_deg"] = np.degrees(s.longitude_radians_of_geo)
s.loc[s.geo_lon_deg > 180, "geo_lon_deg"] -= 360
s["age_yrs"] = (SNAPSHOT_CDM - s.launch).dt.days / 365.25
s["beyond_design_life"] = s.age_yrs > s.Anticipated_Lifetime
s["Country"] = s.Country_of_Operator.replace({"China (PR)": "China", "United Kingdom": "UK"})
s.to_parquet(CLEAN / "cdm_satellites.parquet", index=False)
log.append(("CDM satellites", "Rows after cleaning", len(s)))

# ============================================================ UCS 2020 census (open source)
u = pd.read_excel(OPEN / "ucs_2020.xls")
u = u.rename(columns={"Country of Operator/Owner": "Country", "Class of Orbit": "Class_of_Orbit",
                      "Longitude of GEO (degrees)": "geo_lon_deg", "Date of Launch": "launch", "Launch Mass (kg.)": "mass"})
u = u[u["Name of Satellite, Alternate Names"].notna()].copy()
u["Users"] = u.Users.astype(str).str.replace("Commerical", "Commercial").str.strip()
u["military_any"] = u.Users.str.contains("Military")
u["purpose_group"] = u.Purpose.map(purpose_group)
u["Country"] = u.Country.astype(str).str.strip().replace({"China": "China", "United Kingdom": "UK"})
u["Class_of_Orbit"] = u.Class_of_Orbit.astype(str).str.strip().str.upper().replace({"ELLIPTICAL": "Elliptical"})
u[["Country", "Users", "Purpose", "purpose_group", "military_any", "Class_of_Orbit", "geo_lon_deg", "launch", "mass"]].to_parquet(
    CLEAN / "ucs2020.parquet", index=False)
log.append(("UCS 2020", "Active satellites", len(u)))

# ============================================================ CelesTrak SATCAT (open source, to Sep 2026)
c = pd.read_csv(OPEN / "satcat.csv", low_memory=False)
log.append(("SATCAT", "Objects catalogued (1957 - Sep 2026)", len(c)))
c = c[c.ORBIT_CENTER.eq("EA")].copy()                 # Earth-orbiting objects only (drop lunar, solar, planetary)
log.append(("SATCAT", "Earth-orbiting objects kept", len(c)))
c["launch"] = pd.to_datetime(c.LAUNCH_DATE, errors="coerce")
c["decay"] = pd.to_datetime(c.DECAY_DATE, errors="coerce")
c["type"] = c.OBJECT_TYPE.map({"PAY": "Payload", "R/B": "Rocket body", "DEB": "Debris", "UNK": "Unknown"})
c["owner"] = c.OWNER.map(OWNER).fillna("Other")
c["site_country"] = c.LAUNCH_SITE.map(SITE).fillna("Other")
c["launch_id"] = c.OBJECT_ID.str[:8]                  # e.g. 2026-051 = the 51st orbital launch of 2026
c["constellation"] = np.where(c.OBJECT_TYPE.eq("PAY"), c.OBJECT_NAME.map(constellation), "")
c["alt_mean"] = (c.APOGEE + c.PERIGEE) / 2
c["regime"] = regime(c.PERIGEE.fillna(-1), c.APOGEE.fillna(-1), c.PERIOD.fillna(-1))
c["operational"] = c.OPS_STATUS_CODE.isin(["+", "P", "B", "S", "X"])   # CelesTrak: operational, partially, backup, spare, extended
missing_elems = c.APOGEE.isna().sum()
log.append(("SATCAT", "Objects without orbital elements (kept; excluded from altitude work)", int(missing_elems)))
c.drop(columns=["LAUNCH_DATE", "DECAY_DATE"]).to_parquet(CLEAN / "satcat.parquet", index=False)

# ============================================================ space weather (CDM)
dst = pd.read_csv(RAW / "labels.csv")
dst["hours"] = pd.to_timedelta(dst.timedelta).dt.total_seconds() / 3600
ss = pd.read_csv(RAW / "sunspots.csv")
ss["days"] = pd.to_timedelta(ss.timedelta).dt.days
dst.to_parquet(CLEAN / "dst.parquet", index=False)
ss.to_parquet(CLEAN / "sunspots.parquet", index=False)
log.append(("Space weather", "Hourly Dst values (3 periods)", len(dst)))
log.append(("Space weather", "Monthly smoothed sunspot values", len(ss)))

# ============================================================ MODIS fire detections (CDM)
cols = ["latitude", "longitude", "brightness", "acq_date", "acq_time", "satellite", "confidence", "frp", "daynight", "type"]
fa = pd.read_csv(RAW / "fire_archive_M6_156000.csv", usecols=cols)
fn = pd.read_csv(RAW / "fire_nrt_M6_156000.csv", usecols=[c_ for c_ in cols if c_ != "type"])
fn["type"] = -1                                       # near-real-time file carries no source type
f = pd.concat([fa.assign(stream="archive"), fn.assign(stream="near real time")], ignore_index=True)
log.append(("MODIS fires", "Detections loaded (archive + near real time)", len(f)))
d0 = f.duplicated(["latitude", "longitude", "acq_date", "acq_time", "satellite"]).sum()
f = f.drop_duplicates(["latitude", "longitude", "acq_date", "acq_time", "satellite"])
log.append(("MODIS fires", "Duplicate detections removed", int(d0)))
f["date"] = pd.to_datetime(f.acq_date)
f["confidence"] = pd.to_numeric(f.confidence, errors="coerce")
f.to_parquet(CLEAN / "fires.parquet", index=False)
log.append(("MODIS fires", "Rows after cleaning", len(f)))

table(pd.DataFrame(log, columns=["Dataset", "Step", "Count"]), "t1_cleaning_log")
put_metrics(
    cdm_n=len(s), cdm_first=f"{s.launch.min():%Y}", cdm_last=f"{s.launch.max():%d %b %Y}",
    cdm_countries=int(s.Country.nunique()), cdm_military=int(s.military_any.sum()),
    ucs20_n=len(u), satcat_n=int(len(c)), satcat_last=f"{c.launch.max():%d %b %Y}",
    fires_n=int(len(f)), fires_first=f"{f.date.min():%b %Y}", fires_last=f"{f.date.max():%b %Y}",
    dst_n=int(len(dst)), bad_period=int(bad_period.sum()), bad_incl=int(bad_incl.sum()),
)
print(pd.DataFrame(log))
