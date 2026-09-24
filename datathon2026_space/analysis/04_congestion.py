"""Stage 4 - congestion: where orbit is crowded, how collision risk has grown, and how long weapon debris stays."""

# =====================================================================================================
# ANNOTATED SOURCE - Stage 4: congestion (booklet Chapter 4)
# -----------------------------------------------------------------------------------------------------
# QUESTIONS 1. Which altitudes are crowded, and how has that changed since the 2014 census?
#           2. How much has collision risk grown? A kinetic-gas model says collisions in a shell scale with the square of
#              the number of objects divided by the shell's volume (n^2 / V); summed over shells this gives a relative
#              COLLISION-RISK INDEX (2014 = 1.0). It is a relative index, not a probability.
#           3. How crowded is the geostationary arc above India?
#           4. Anti-satellite (ASAT) tests and collisions: how many pieces each made and how long they stay in orbit.
#              Debris lifetime depends on altitude, so a low-altitude test cleans itself up; a high one lasts decades.
# =====================================================================================================
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import C, CATALOGUE_DATE, CLEAN, EARTH_R, SERIES, SNAPSHOT_CDM, put_metrics, save, table

print("Stage 4: congestion")
c = pd.read_parquet(CLEAN / "satcat.parquet")
cdm = pd.read_parquet(CLEAN / "cdm_satellites.parquet")
u20 = pd.read_parquet(CLEAN / "ucs2020.parquet")


def on_orbit(df, t):
    return df[(df.launch <= t) & (df.decay.isna() | (df.decay > t))]


# ---------------------------------------------------------------- 1-2. LEO shells and the collision-risk index
W = 25                                                # shell thickness, km
edges = np.arange(200, 2000 + W, W)
vol = 4 / 3 * np.pi * ((EARTH_R + edges[1:]) ** 3 - (EARTH_R + edges[:-1]) ** 3)   # km^3 per shell


def shells(df):
    leo = df[(df.APOGEE < 2000) & df.alt_mean.notna()]
    out = {}
    for t in ["Payload", "Debris", "Rocket body"]:
        out[t] = np.histogram(leo[leo.type.eq(t)].alt_mean, edges)[0]
    out["All"] = np.histogram(leo.alt_mean, edges)[0]
    out["Active"] = np.histogram(leo[leo.operational].alt_mean, edges)[0] if "operational" in leo else 0
    return pd.DataFrame(out, index=edges[:-1])


s14, s26 = shells(on_orbit(c, SNAPSHOT_CDM)), shells(on_orbit(c, CATALOGUE_DATE))
risk = lambda n: float((n ** 2 / vol).sum())
risk_ratio = risk(s26.All.values) / risk(s14.All.values)
dens = s26.All / vol * 1e9                             # objects per billion km^3
peak_shell = int(s26.All.idxmax())
band = s26.loc[450:475]                                  # the live crowd: Starlink shells lowered to ~480 km
dead = s26.loc[750:875]                                  # the dead crowd: debris of the 2007 ASAT test and 2009 collision
tab = pd.DataFrame({"Shell (km)": [f"{a}-{a + W}" for a in s26.index], "Objects 2014": s14.All.values, "Objects 2026": s26.All.values,
                    "Active 2026": s26.Active.values, "Debris 2026": s26.Debris.values,
                    "Density 2026 (per 10^9 km^3)": dens.round(1).values})
table(tab[tab["Objects 2026"] > 0], "t4_leo_shells")

fig, ax = plt.subplots(figsize=(9, 3.6))
x = s26.index + W / 2
ax.bar(x, s26.Payload, width=W * 0.9, color=C["blue"], label="Payloads 2026")
ax.bar(x, s26["Rocket body"], bottom=s26.Payload, width=W * 0.9, color=C["yellow"], label="Rocket bodies 2026")
ax.bar(x, s26.Debris, bottom=s26.Payload + s26["Rocket body"], width=W * 0.9, color=C["orange"], label="Debris 2026")
ax.step(x, s14.All, where="mid", color=C["ink"], lw=1.2, label="All objects, Jan 2014")
ax.set_xlim(200, 1500)
ax.set_xlabel("mean altitude (km), 25 km shells")
ax.set_ylabel("objects in shell")
ax.legend(loc="upper right")
ax.text(812, dead.All.max() * 1.25, "the dead crowd: debris\nat 750-900 km", fontsize=7.5, color=C["ink2"], ha="center")
ax.annotate(f"the live crowd: {band.All.sum():,} objects at 450-500 km,\n{band.Active.sum() / band.All.sum():.0%} of them working satellites", (500, s26.All.max() * 0.9), xytext=(620, s26.All.max() * 0.8),
            fontsize=7.5, color=C["ink2"], arrowprops=dict(arrowstyle="-", color=C["muted"], lw=0.6))
ax.set_title(f"Low Earth orbit by altitude: 2014 vs 2026 (collision-risk index x{risk_ratio:.0f})")
save(fig, "f4_1_leo_shells")

# ---------------------------------------------------------------- 3. the geostationary arc above India
geo14 = cdm[cdm.Class_of_Orbit.eq("GEO") & cdm.geo_lon_deg.notna()]
geo20 = u20[u20.Class_of_Orbit.eq("GEO") & pd.to_numeric(u20.geo_lon_deg, errors="coerce").notna()].copy()
geo20["geo_lon_deg"] = pd.to_numeric(geo20.geo_lon_deg)
bins = np.arange(-180, 185, 5)
h14 = np.histogram(geo14.geo_lon_deg, bins)[0]
h20 = np.histogram(geo20.geo_lon_deg, bins)[0]
ARC = (40, 110)                                        # arc visible from and used by India (GSAT/INSAT between ~48E and ~93.5E)
arc14 = int(geo14.geo_lon_deg.between(*ARC).sum())
arc20 = int(geo20.geo_lon_deg.between(*ARC).sum())
ind_geo = geo14[geo14.Country.eq("India")]
arc_by = geo20[geo20.geo_lon_deg.between(*ARC)].Country.map(lambda x: "China" if str(x).startswith("China") else x).value_counts().head(8)
table(arc_by.rename("GEO satellites 40-110E (2020)").rename_axis("Country").reset_index(), "t4_geo_arc_india")
fig, ax = plt.subplots(figsize=(9, 2.9))
ax.bar(bins[:-1] + 2.5, h20, width=4.5, color=C["aqua"], label="Apr 2020 (UCS)")
ax.step(bins[:-1] + 2.5, h14, where="mid", color=C["ink"], lw=1.1, label="Jan 2014 (CDM)")
ax.axvspan(*ARC, color=C["orange"], alpha=0.12, lw=0)
ax.text(ARC[0] + 1, max(h20) * 0.95, "arc used by India\n(40-110 E)", fontsize=7, color=C["orange"], va="top")
ax.plot(ind_geo.geo_lon_deg, np.full(len(ind_geo), -0.8), "v", color=C["red"], ms=5, label="Indian GEO satellites (2014)")
ax.set_xlabel("longitude of geostationary slot (degrees; east positive)")
ax.set_ylabel("satellites per 5 deg")
ax.set_xlim(-180, 180)
ax.legend(loc="upper left", fontsize=7)
ax.set_title("The geostationary belt: slots over the Indian Ocean region are among the most crowded")
save(fig, "f4_2_geo_arc")

# ---------------------------------------------------------------- 4. weapon tests and collisions: debris persistence
EV = [("FENGYUN 1C DEB", "China ASAT test", "2007-01-11"), ("COSMOS 2251 DEB", "Iridium-Cosmos collision (Russian debris)", "2009-02-10"),
      ("IRIDIUM 33 DEB", "Iridium-Cosmos collision (US debris)", "2009-02-10"), ("USA 193 DEB", "US ASAT intercept", "2008-02-21"),
      ("MICROSAT-R DEB", "India ASAT test (Mission Shakti)", "2019-03-27"), ("COSMOS 1408 DEB", "Russia ASAT test", "2021-11-15")]
rows, curves = [], {}
for name, lab, d0 in EV:
    d = c[c.OBJECT_NAME.eq(name)]
    t0 = pd.Timestamp(d0)
    life = ((d.decay.fillna(CATALOGUE_DATE) - t0).dt.days / 365.25).clip(lower=0)
    alive = d.decay.isna()
    yrs = (CATALOGUE_DATE - t0).days / 365.25
    alt = float(d.alt_mean.median()) if d.alt_mean.notna().any() else np.nan
    rows.append((lab, f"{t0:%b %Y}", len(d), int(alive.sum()), round(alive.mean() * 100, 1), round(yrs, 1),
                 round(float(life[~alive].median()), 1) if (~alive).any() else None))
    grid = np.linspace(0, yrs, 200)
    curves[lab] = (grid, [((life > g) | alive).mean() if g >= yrs - 1e-9 else (life > g).mean() for g in grid])
asat = pd.DataFrame(rows, columns=["Event", "Date", "Pieces catalogued", "Still in orbit (Sep 2026)", "Still in orbit %",
                                   "Years since", "Median years to re-entry (re-entered pieces)"])
table(asat, "t4_asat_debris")
fig, ax = plt.subplots(figsize=(9, 3.2))
cols = {"China ASAT test": C["red"], "Iridium-Cosmos collision (Russian debris)": C["violet"], "Iridium-Cosmos collision (US debris)": C["blue"],
        "US ASAT intercept": C["aqua"], "India ASAT test (Mission Shakti)": C["orange"], "Russia ASAT test": C["yellow"]}
for lab, (g, v) in curves.items():
    ax.plot(g, np.array(v) * 100, color=cols[lab], lw=1.8, label=lab)
ax.set_xlabel("years after the event")
ax.set_ylabel("% of catalogued pieces still in orbit")
ax.set_ylim(0, 102)
ax.legend(fontsize=7, loc="center right")
ax.set_title("Debris from weapon tests: altitude decides whether it clears in months or stays for decades")
save(fig, "f4_3_asat_debris")

fy = asat.set_index("Event").loc["China ASAT test"]
ms = asat.set_index("Event").loc["India ASAT test (Mission Shakti)"]
ru = asat.set_index("Event").loc["Russia ASAT test"]
put_metrics(
    risk_ratio=round(risk_ratio, 1), peak_shell=f"{peak_shell}-{peak_shell + W}", peak_shell_n=int(s26.All.max()),
    band_now=int(band.All.sum()), band_2014=int(s14.loc[450:475].All.sum()),
    dead_now=int(dead.All.sum()), dead_debris_share=round(float(dead.Debris.sum() / dead.All.sum()), 3),
    band_active_share=round(float(band.Active.sum() / band.All.sum()), 3),
    leo_now=int(s26.All.sum()), leo_2014=int(s14.All.sum()),
    geo_arc14=arc14, geo_arc20=arc20, geo_arc_share20=round(arc20 / len(geo20), 3), geo_total20=len(geo20),
    geo_arc_cn20=int(arc_by.get("China", 0)), geo_arc_in20=int(arc_by.get("India", 0)),
    fy1c_pieces=int(fy["Pieces catalogued"]), fy1c_alive=int(fy["Still in orbit (Sep 2026)"]), fy1c_alive_pct=float(fy["Still in orbit %"]),
    shakti_pieces=int(ms["Pieces catalogued"]), shakti_alive=int(ms["Still in orbit (Sep 2026)"]),
    shakti_median_yrs=float(ms["Median years to re-entry (re-entered pieces)"]),
    ru1408_pieces=int(ru["Pieces catalogued"]), ru1408_alive=int(ru["Still in orbit (Sep 2026)"]),
)
print(asat.to_string(), "\nrisk", risk_ratio, "peak", peak_shell, "arc", arc14, arc20, len(geo20), "\n", arc_by)
