"""Stage 7 - what satellites buy you: 1.25 million MODIS fire detections as a case study in Earth-observation value."""

# =====================================================================================================
# ANNOTATED SOURCE - Stage 7: the value of eyes in orbit (booklet Chapter 7)
# -----------------------------------------------------------------------------------------------------
# The CDM fire files are detections by the MODIS sensors on two NASA satellites: Terra (morning pass) and Aqua
# (afternoon pass), over the United States, Sep 2010 - Sep 2020. They are used here as a controlled experiment in
# what an Earth-observation constellation delivers, with lessons for military ISR:
#   1. THE CONSTELLATION PREMIUM - put every detection on a 0.1-degree grid, one cell per day. Which fraction of fire
#      cell-days did only one satellite see? That is what a single satellite would have missed.
#   2. PERSISTENCE - thermal sensors see at night; persistent static heat sources (type 2) are industrial sites
#      (steel mills, smelters, refineries); a volcano (type 1) is watched through its whole eruption to the day it ends.
#   3. SURGE DETECTION - a seasonal baseline (median of the same month in earlier years) and z-scores flag abnormal
#      months, the same logic as an indicators-and-warnings watch.
# =====================================================================================================
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import C, CLEAN, put_metrics, save, table

print("Stage 7: Earth-observation value")
f = pd.read_parquet(CLEAN / "fires.parquet")

# ---------------------------------------------------------------- 1. the constellation premium
a = f[f.stream.eq("archive")].copy()
a["cellday"] = ((a.latitude / 0.1).round().astype(int).astype(str) + "_" + (a.longitude / 0.1).round().astype(int).astype(str)
                + "_" + a.acq_date)
seen = a.groupby("cellday").satellite.agg(lambda x: "+".join(sorted(set(x))))
prem = seen.value_counts(normalize=True).rename({"Aqua": "Aqua only", "Terra": "Terra only", "Aqua+Terra": "Both"})
table(prem.mul(100).round(1).rename("% of fire cell-days").rename_axis("Seen by").reset_index(), "t7_constellation_premium")
night = float((f.daynight == "N").mean())

# ---------------------------------------------------------------- 2. seasonality and surge detection
mon = f.groupby(pd.Grouper(key="date", freq="MS")).size()
mon = mon[mon.index >= "2010-10-01"]
base = mon.groupby(mon.index.month).transform(lambda s: s.expanding().median().shift(1))
spread = mon.groupby(mon.index.month).transform(lambda s: s.expanding().std().shift(1))
z = ((mon - base) / spread).replace([np.inf, -np.inf], np.nan)
surges = z[z > 2].sort_values(ascending=False)
table(pd.DataFrame({"month": mon.index.strftime("%b %Y"), "detections": mon.values, "baseline": base.round(0).values,
                    "z": z.round(2).values}), "t7_monthly_surge")

# ---------------------------------------------------------------- 3. persistent sources: industry and a volcano
t2 = a[a.type.eq(2)].copy()
t2["cell"] = t2.latitude.round(0).astype(int).astype(str) + "N " + (-t2.longitude.round(0)).astype(int).astype(str) + "W"
top_ind = t2.groupby("cell").agg(detections=("frp", "size"), months_active=("date", lambda s: s.dt.to_period("M").nunique())).sort_values(
    "detections", ascending=False).head(8)
NAMES = {"42N 87W": "Gary / Chicago steel belt", "33N 111W": "Arizona copper smelting (Phoenix area)", "43N 112W": "Pocatello, Idaho (phosphate plants)",
         "42N 83W": "Detroit (steel)", "41N 82W": "Cleveland (steel)", "31N 88W": "Mobile, Alabama (industry, port)"}
top_ind["likely source"] = [NAMES.get(i, "industrial site") for i in top_ind.index]
table(top_ind.reset_index(names="1-degree cell"), "t7_industrial_heat")
v = a[a.type.eq(1) & a.latitude.between(18.8, 20.3) & a.longitude.between(-156, -154.7)]
v_last = v.date.max()
vy = v.groupby(v.date.dt.to_period("Q")).size()

fig, ax = plt.subplots(1, 3, figsize=(9, 3.1), gridspec_kw={"width_ratios": [0.85, 1.4, 1.05]})
order = ["Aqua only", "Terra only", "Both"]
ax[0].bar(order, prem.reindex(order) * 100, color=[C["blue"], C["aqua"], C["violet"]], width=0.6)
for i, val in enumerate(prem.reindex(order) * 100):
    ax[0].text(i, val + 1, f"{val:.0f}%", ha="center", fontsize=8, fontweight="bold")
ax[0].set_ylabel("% of fire cell-days")
ax[0].set_title("Who saw each fire-day?", fontsize=9)
ax[0].grid(axis="x", visible=False)
ax[0].tick_params(axis="x", labelsize=7.5)
ax[1].plot(mon.index, mon.values / 1000, color=C["orange"], lw=1.2)
for d_, zz in surges.head(3).items():
    ax[1].annotate(f"{d_:%b %Y}\nz = {zz:.1f}", (d_, mon[d_] / 1000), xytext=(-10, -4), textcoords="offset points", fontsize=6.5,
                   ha="right", color=C["red"])
ax[1].set_ylabel("detections per month ('000)")
ax[1].set_title("Seasonal rhythm and abnormal surges", fontsize=9)
ax[2].bar(vy.index.to_timestamp(), vy.values, width=80, color=C["red"])
ax[2].set_title("Kilauea: the 2018 eruption and its end", fontsize=9)
ax[2].tick_params(axis="x", labelsize=7, rotation=30)
ax[2].set_ylabel("detections per quarter")
fig.suptitle("What two satellites deliver: coverage, persistence and early warning (MODIS, 2010-2020)", x=0.01, ha="left",
             fontsize=11, fontweight="bold")
fig.tight_layout()
save(fig, "f7_1_eo_value")

# map of all detections (context)
fig, ax = plt.subplots(figsize=(9, 3.6))
hb = ax.hexbin(f.longitude, f.latitude, gridsize=(180, 50), bins="log", cmap="YlOrRd", mincnt=1, extent=(-170, -65, 18, 71))
ax.set_xlim(-170, -65)
ax.set_ylim(18, 71)
ax.set_xlabel("longitude")
ax.set_ylabel("latitude")
fig.colorbar(hb, ax=ax, fraction=0.025, label="detections (log)")
ax.grid(False)
ax.set_title(f"{len(f):,} fire and heat detections by Terra and Aqua over the USA, 2010-2020")
save(fig, "f7_2_fire_map")

put_metrics(
    prem_single=round(float(prem.get("Aqua only", 0) + prem.get("Terra only", 0)), 3), prem_both=round(float(prem.get("Both", 0)), 3),
    prem_aqua_only=round(float(prem.get("Aqua only", 0)), 3), prem_terra_only=round(float(prem.get("Terra only", 0)), 3),
    night_share=round(night, 3), surge_top=f"{surges.index[0]:%b %Y}", surge_top_z=round(float(surges.iloc[0]), 1), surges_n=int(len(surges)),
    sep2020=int(mon.get(pd.Timestamp("2020-09-01"), 0)), kilauea_last=f"{v_last:%b %Y}", kilauea_n=int(len(v)),
    industrial_cells=int(t2.cell.nunique()), industrial_top=top_ind["likely source"].iloc[0],
)
print(prem, "\nnight", night, "\n", surges.head(6), "\n", top_ind, "\nkilauea last", v_last)
