"""Stage 2 - the crowd: how many objects are in orbit, how fast it grew, and who launches."""

# =====================================================================================================
# ANNOTATED SOURCE - Stage 2: proliferation (booklet Chapter 2)
# -----------------------------------------------------------------------------------------------------
# QUESTION  How crowded has orbit become since the CDM census of 2014, and when did the growth change gear?
# METHOD    1. Rebuild the on-orbit population at every year-end from the catalogue: an object is in orbit at date t
#              if it was launched on or before t and had not re-entered by t. Split into payloads, rocket bodies, debris.
#           2. Three independent censuses of ACTIVE satellites anchor the story: CDM (Jan 2014), UCS (Apr 2020) and
#              the catalogue's operational flag (Sep 2026).
#           3. Payloads launched per year and orbital launches per year (one launch = one international designator),
#              by launching country; UNOOSA registrations as a cross-check.
#           4. Change-point detection (PELT) on payloads launched per year finds when the growth regime changed;
#              compound annual growth rate (CAGR) before and after.
# =====================================================================================================
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import ruptures as rpt

from common import C, CATALOGUE_DATE, CLEAN, OPEN, SERIES, put_metrics, save, table

print("Stage 2: growth")
c = pd.read_parquet(CLEAN / "satcat.parquet")
cdm = pd.read_parquet(CLEAN / "cdm_satellites.parquet")
u20 = pd.read_parquet(CLEAN / "ucs2020.parquet")


def on_orbit(df, t):
    """Objects in orbit at date t."""
    return df[(df.launch <= t) & (df.decay.isna() | (df.decay > t))]


# ---------------------------------------------------------------- 1. year-end population
years = list(range(1957, 2026))
rows = []
for y in years + [2026]:
    t = CATALOGUE_DATE if y == 2026 else pd.Timestamp(f"{y}-12-31")
    o = on_orbit(c, t)
    rows.append({"year": y, **o.type.value_counts().to_dict(), "total": len(o)})
pop = pd.DataFrame(rows).fillna(0).set_index("year")[["Payload", "Rocket body", "Debris", "Unknown", "total"]].astype(int)
table(pop.reset_index(), "t2_population_by_year")

fig, ax = plt.subplots(figsize=(9, 3.4))
ax.stackplot(pop.index, pop.Payload, pop["Rocket body"], pop.Debris, colors=[C["blue"], C["yellow"], C["orange"]],
             labels=["Payloads (working or dead)", "Rocket bodies", "Catalogued debris"], alpha=0.9)
for yr, lab, yy in [(2007, "2007: Chinese ASAT test", 0.55), (2009, "2009: Iridium-Cosmos collision", 0.72),
                    (2019, "2019: mega-constellations begin", 0.88)]:
    ax.axvline(yr, color=C["muted"], lw=0.6, ls=":")
    ax.text(yr - 0.4, pop.total.max() * yy, lab, fontsize=7, color=C["ink2"], ha="right")
ax.set_ylabel("objects in orbit (year end)")
ax.set_xlim(1957, 2026.8)
ax.legend(loc="upper left")
ax.set_title("Objects in Earth orbit, 1957-2026 (CelesTrak catalogue)")
save(fig, "f2_1_population")

# ---------------------------------------------------------------- 2. three censuses of ACTIVE satellites
act_now = int(c.operational.sum())
cens = pd.DataFrame([("Jan 2014", "CDM dataset (census of active satellites)", len(cdm)),
                     ("Apr 2020", "UCS Satellite Database (open source)", len(u20)),
                     (f"{CATALOGUE_DATE:%b %Y}", "CelesTrak catalogue, operational flag (open source)", act_now)],
                    columns=["Date", "Source", "Active satellites"])
table(cens, "t2_active_censuses")
starlink_now = int((c.operational & c.constellation.eq("Starlink (US)")).sum())
fig, ax = plt.subplots(figsize=(9, 3))
bars = ax.bar(cens.Date, cens["Active satellites"], color=[C["blue"], C["blue"], C["orange"]], width=0.55)
ax.bar(cens.Date.iloc[-1], starlink_now, color=C["red"], width=0.55, label="of which Starlink")
for b, v in zip(bars, cens["Active satellites"]):
    ax.text(b.get_x() + b.get_width() / 2, v + 250, f"{v:,}", ha="center", fontsize=9, fontweight="bold")
ax.legend(loc="upper left")
ax.set_ylabel("active satellites")
ax.grid(axis="x", visible=False)
ax.set_title(f"Active satellites: {len(cdm):,} (2014) to {act_now:,} (2026) - {act_now / len(cdm):.0f} times in 12 years")
save(fig, "f2_2_censuses")

# ---------------------------------------------------------------- 3. launches and payloads per year
p = c[c.OBJECT_TYPE.eq("PAY")]
pay_y = p.groupby(p.launch.dt.year).size().reindex(range(1957, 2027), fill_value=0)
starlink_y = p[p.constellation.eq("Starlink (US)")].groupby(p.launch.dt.year).size().reindex(pay_y.index, fill_value=0)
launch = c.drop_duplicates("launch_id")
launch = launch[launch.launch_id.str.match(r"^\d{4}-\d{3}$")]
lc = launch.groupby([launch.launch.dt.year, "site_country"]).size().unstack(fill_value=0)
top = ["USA", "China", "Russia", "Europe", "India", "Japan", "New Zealand"]
lc = lc.reindex(columns=top + [x for x in lc.columns if x not in top]).fillna(0)
lc["Others"] = lc.drop(columns=top).sum(axis=1)
lc = lc[top + ["Others"]]
table(lc.reset_index().rename(columns={"launch": "year"}), "t2_launches_by_country")
fig, ax = plt.subplots(1, 2, figsize=(9, 3.3), gridspec_kw={"width_ratios": [1.1, 1]})
ax[0].bar(pay_y.index, pay_y - starlink_y, color=C["blue"], width=0.85, label="Other payloads")
ax[0].bar(pay_y.index, starlink_y, bottom=pay_y - starlink_y, color=C["red"], width=0.85, label="Starlink")
ax[0].set_xlim(1990, 2026.8)
ax[0].legend(loc="upper left")
ax[0].set_title("Payloads launched per year", fontsize=9)
l2 = lc.loc[2000:]
bottom = np.zeros(len(l2))
for i, col in enumerate(l2.columns):
    ax[1].bar(l2.index, l2[col], bottom=bottom, color=(SERIES + ["#b5b4ae"])[i], width=0.85, label=col)
    bottom += l2[col].values
ax[1].legend(fontsize=6.5, ncol=2, loc="upper left")
ax[1].set_title("Orbital launches per year, by launching country", fontsize=9)
for a in ax:
    a.grid(axis="x", visible=False)
fig.suptitle(f"The launch rate changed gear after 2019 (2026 = to {CATALOGUE_DATE:%d %b})", x=0.01, ha="left",
             fontsize=11, fontweight="bold")
fig.tight_layout()
save(fig, "f2_3_launch_rate")

# ---------------------------------------------------------------- 4. regime change and growth rates
sig = pay_y.loc[1990:2025].values.astype(float)
bk = rpt.Pelt(model="l2", min_size=3, jump=1).fit((sig / sig.std()).reshape(-1, 1)).predict(pen=3)
cps = [int(pay_y.loc[1990:2025].index[b]) for b in bk[:-1]]
cagr = lambda a, b: (pay_y[b] / pay_y[a]) ** (1 / (b - a)) - 1
un = pd.read_csv(OPEN / "unoosa_objects_launched.csv")
un_world = un[un.Entity.eq("World")].set_index("Year").num_objects
cross = pd.DataFrame({"SATCAT payloads": pay_y, "UNOOSA registered objects": un_world}).loc[2000:2023].dropna()
r_cross = float(np.corrcoef(cross.iloc[:, 0], cross.iloc[:, 1])[0, 1])

put_metrics(
    pop_2014=int(pop.loc[2013, "total"]), pop_now=int(pop.loc[2026, "total"]), pay_orbit_now=int(pop.loc[2026, "Payload"]),
    deb_now=int(pop.loc[2026, "Debris"]), rb_now=int(pop.loc[2026, "Rocket body"]),
    active_2014=len(cdm), active_2020=len(u20), active_now=act_now, active_mult=round(act_now / len(cdm), 1),
    starlink_now=starlink_now, starlink_share=round(starlink_now / act_now, 3),
    pay_2013=int(pay_y[2013]), pay_2019=int(pay_y[2019]), pay_2025=int(pay_y[2025]), pay_2026_ytd=int(pay_y[2026]),
    launches_2025=int(lc.loc[2025].sum()), launches_2013=int(lc.loc[2013].sum()),
    launches_2025_us=int(lc.loc[2025, "USA"]), launches_2025_cn=int(lc.loc[2025, "China"]), launches_2025_in=int(lc.loc[2025, "India"]),
    growth_cps=cps, cagr_2000_2013=round(cagr(2000, 2013) * 100, 1), cagr_2019_2025=round(cagr(2019, 2025) * 100, 1),
    unoosa_corr=round(r_cross, 3), starlink_share_2025_launched=round(float(starlink_y[2025] / pay_y[2025]), 3),
)
print(pop.tail(4), "\n", cens, "\n", lc.tail(3), "\ncps", cps, "cagr", cagr(2000, 2013), cagr(2019, 2025), "corr", r_cross)
