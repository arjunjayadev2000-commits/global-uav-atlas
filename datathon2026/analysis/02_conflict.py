"""Stage 2 - descriptive & diagnostic analytics of the Middle-East conflict system (ACLED)."""

# =====================================================================================================
# ANNOTATED SOURCE - Stage 2: the conflict picture (report Chapter 5, 'The Storm Gathers')
# -----------------------------------------------------------------------------------------------------
# QUESTION  How did violence in the Middle East change, when did the 'battle rhythm' shift, and did the
#           war reach the Gulf states and the sea?
# INPUT     data/clean/acled_clean.parquet (from Stage 1).
# OUTPUT    Figures 5.1-5.8, tables t5_1-t5_3, metrics (war ratio, change-points, drone share, GCC spill-over
# ...).
# METHODS   - Descriptive charts (annual totals, event mix, country-by-year heat map, war-period map).
#           - Change-point detection (PELT): finds the weeks where average weekly violence jumped.
#           - Linear trend (regression) of the stand-off-strike share.
#           - Mann-Whitney U test: are war weeks more violent than the pre-war year? (no normality assumed)
# =====================================================================================================

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import ruptures as rpt
from scipy import stats

from common import C, CHOKEPOINTS, CLEAN, SERIES, basemap_ax, put_metrics, save, table

print("Stage 2: conflict analytics")
a = pd.read_parquet(CLEAN / "acled_clean.parquet")
# Most of the analysis uses political violence only (battles, explosions, violence against civilians), not
# protests. WAR0 = start of the 2026 war.
pv = a[a.POLITICAL_VIOLENCE]
WAR0 = pd.Timestamp("2026-02-28")

# ---------------------------------------------------------------- 5.1 annual trend (two panels)
# Figure 5.1: events and fatalities per year; the 2026 bar (partial year) is shown in orange.
yr = a[a.YEAR <= 2026].groupby("YEAR")[["EVENTS", "FATALITIES"]].sum()
fig, ax = plt.subplots(1, 2, figsize=(9, 3.1))
cols = [C["blue"]] * (len(yr) - 1) + [C["orange"]]
ax[0].bar(yr.index, yr.EVENTS / 1000, color=cols, width=0.7)
ax[0].set_title("Events per year ('000)")
ax[1].bar(yr.index, yr.FATALITIES / 1000, color=cols, width=0.7)
ax[1].set_title("Reported fatalities per year ('000)")
for x in ax:
    x.set_xticks(yr.index[::2])
    x.grid(axis="x", visible=False)
ax[0].annotate("2024 peak\n(Gaza, Red Sea)", (2024, yr.EVENTS[2024] / 1000), xytext=(2019.3, 85),
               fontsize=7.5, color=C["ink2"], arrowprops=dict(arrowstyle="-", color=C["muted"], lw=0.6))
ax[1].text(2026, yr.FATALITIES[2026] / 1000 + 3, "2026\n(to 27 Jun)", ha="center", fontsize=7, color=C["ink2"])
fig.suptitle("Figure 5.1  Middle-East conflict volume, 2015-2026", x=0.01, ha="left", fontsize=11, fontweight="bold")
fig.tight_layout()
save(fig, "f5_1_annual")

# ---------------------------------------------------------------- 5.2 event-type composition
# Figure 5.2 and Table 5.1: each year's mix of event types as percentages (stacked bars).
comp = a[a.YEAR <= 2026].pivot_table(index="YEAR", columns="EVENT_TYPE", values="EVENTS", aggfunc="sum").fillna(0)
share = comp.div(comp.sum(axis=1), axis=0) * 100
order = ["Explosions/Remote violence", "Battles", "Violence against civilians", "Riots", "Protests", "Strategic developments"]
fig, ax = plt.subplots(figsize=(9, 3.4))
bottom = np.zeros(len(share))
for i, col in enumerate(order):
    ax.bar(share.index, share[col], bottom=bottom, color=SERIES[i], width=0.72, label=col,
           edgecolor="white", linewidth=1)
    bottom += share[col].values
ax.set_ylabel("% of all events")
ax.set_ylim(0, 100)
ax.legend(ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.1))
ax.grid(axis="x", visible=False)
ax.set_title("Figure 5.2  Event-type mix by year - remote violence (air, drone, missile, artillery) dominates")
save(fig, "f5_2_eventmix")
table(share.round(1).reset_index(), "t5_1_eventmix_share")

# ---------------------------------------------------------------- 5.3 country x year heatmap
# Figure 5.3: heat map of political violence, country x year, on a log scale so small and large countries both
# show.
hm = pv[pv.YEAR <= 2026].pivot_table(index="COUNTRY", columns="YEAR", values="EVENTS", aggfunc="sum").fillna(0)
hm = hm.loc[hm.sum(axis=1).sort_values(ascending=False).index]
fig, ax = plt.subplots(figsize=(9, 5))
im = ax.imshow(np.log10(hm.values + 1), cmap="Blues", aspect="auto")
ax.set_xticks(range(hm.shape[1]), hm.columns)
ax.set_yticks(range(hm.shape[0]), hm.index)
ax.grid(False)
for i in range(hm.shape[0]):
    for j in range(hm.shape[1]):
        v = hm.values[i, j]
        if v >= 1:
            ax.text(j, i, f"{v/1000:.1f}k" if v >= 1000 else f"{int(v)}", ha="center", va="center", fontsize=6,
                    color="white" if np.log10(v + 1) > 3 else C["ink"])
cb = fig.colorbar(im, ax=ax, fraction=0.025)
cb.set_label("log10(events + 1)")
ax.set_title("Figure 5.3  Political-violence events by country and year")
save(fig, "f5_3_heatmap")

# ---------------------------------------------------------------- 5.4 weekly series + change points
# Figure 5.4: CHANGE-POINT DETECTION.
# 1. Build the weekly series of political-violence events (missing weeks = 0).
# 2. Scale it by its standard deviation so the penalty below is unit-free.
# 3. PELT (Pruned Exact Linear Time, Killick et al. 2012) with an 'l2' cost searches every possible split and
# keeps
#    the splits that reduce the within-segment squared error by more than the penalty (pen=12).
#    jump=1 lets a change-point fall on any week; min_size=3 stops one-week 'regimes'.
# The result: the weeks when the average level shifted (7 Oct 2023, 28 Feb 2026, 11 Apr 2026).
wk = pv.groupby("WEEK").EVENTS.sum().asfreq("7D", fill_value=0)
sig = wk.values.astype(float) / wk.values.std()
algo = rpt.Pelt(model="l2", min_size=3, jump=1).fit(sig.reshape(-1, 1))
bk = algo.predict(pen=12)
cps = [wk.index[b] for b in bk[:-1]]
fig, ax = plt.subplots(figsize=(9, 3.2))
ax.plot(wk.index, wk.values, color=C["blue"], lw=1.1)
seg_start = 0
for b in bk:
    seg = wk.iloc[seg_start:b]
    ax.hlines(seg.mean(), seg.index[0], seg.index[-1], color=C["orange"], lw=2)
    seg_start = b
for cp in cps:
    ax.axvline(cp, color=C["muted"], lw=0.6, ls=":")
ax.set_ylabel("Political-violence events / week")
ax.set_title("Figure 5.4  Weekly political violence with detected regime shifts (PELT change-points)")
ax.text(0.01, 0.92, "orange = regime mean between change-points", transform=ax.transAxes, fontsize=7.5, color=C["ink2"])
save(fig, "f5_4_changepoints")
# Table 5.2: the mean and spread of weekly violence inside each regime.
seg_tab = []
edges = [0] + bk
for i in range(len(bk)):
    seg = wk.iloc[edges[i]:edges[i + 1]]
    seg_tab.append((f"{seg.index[0]:%d %b %Y}", f"{seg.index[-1]:%d %b %Y}", len(seg), round(seg.mean(), 0), round(seg.std(), 0)))
seg_tab = pd.DataFrame(seg_tab, columns=["From", "To", "Weeks", "Mean events/wk", "SD"])
table(seg_tab, "t5_2_regimes")

# ---------------------------------------------------------------- 5.5 drone / missile share
# Figure 5.5: share of political violence delivered by stand-off weapons (air/drone strikes, shelling/missiles),
# per quarter. A straight-line regression (linregress) measures the trend.
q = pv.groupby([pd.Grouper(key="WEEK", freq="QS"), "DRONE_MISSILE"]).EVENTS.sum().unstack().fillna(0)
q = q[q.index <= "2026-04-01"]
dshare = q[True] / q.sum(axis=1) * 100
fig, ax = plt.subplots(figsize=(9, 3))
ax.plot(dshare.index, dshare.values, color=C["violet"], marker="o", ms=3)
ax.fill_between(dshare.index, 0, dshare.values, color=C["violet"], alpha=0.08)
ax.set_ylim(0, 100)
ax.set_ylabel("% of political violence")
ax.set_title("Figure 5.5  Share of stand-off strikes (air/drone strike + shelling/missile) in political violence")
lr = stats.linregress(np.arange(len(dshare)), dshare.values)
save(fig, "f5_5_drone_share")

# ---------------------------------------------------------------- 5.6 GCC spill-over
# Figure 5.6: violence inside the six GCC states, week by week, to show the war reaching the energy coast.
g = a[a.GCC & a.POLITICAL_VIOLENCE & (a.WEEK >= "2025-06-01")]
gw = g.pivot_table(index="WEEK", columns="COUNTRY", values="EVENTS", aggfunc="sum").fillna(0)
gw = gw[gw.sum().sort_values(ascending=False).index]
fig, ax = plt.subplots(figsize=(9, 3.2))
bottom = np.zeros(len(gw))
for i, c in enumerate(gw.columns):
    ax.bar(gw.index, gw[c], bottom=bottom, width=5.5, color=SERIES[i], label=c, edgecolor="white", linewidth=0.5)
    bottom += gw[c].values
ax.axvline(WAR0, color=C["red"], lw=0.8, ls="--")
ax.text(WAR0, ax.get_ylim()[1] * 0.92, "  28 Feb 2026: war begins", color=C["red"], fontsize=7.5)
ax.legend(ncol=6, loc="upper center", bbox_to_anchor=(0.5, -0.1))
ax.set_ylabel("Events / week")
ax.grid(axis="x", visible=False)
ax.set_title("Figure 5.6  Political violence inside GCC states - the war reaches the energy coast")
save(fig, "f5_6_gcc")
# GCC multiplier = average weekly events in the 6 war weeks / average weekly events in the pre-war year (52
# weeks).
pre = a[a.GCC & a.POLITICAL_VIOLENCE & (a.WEEK >= "2025-02-28") & (a.WEEK < WAR0)].EVENTS.sum() / 52
dur = a[a.GCC & a.POLITICAL_VIOLENCE & (a.WEEK >= WAR0) & (a.WEEK < "2026-04-11")].EVENTS.sum() / 6
put_metrics(gcc_pre_wk=round(pre, 1), gcc_war_wk=round(dur, 1), gcc_multiplier=round(dur / max(pre, 0.1), 1))

# ---------------------------------------------------------------- 5.7 war-period map
# Figure 5.7 and Table 5.3: map of where violence fell during the war (bubble size = events, colour =
# fatalities).
wp = pv[(pv.WEEK >= WAR0) & (pv.WEEK < "2026-04-11")]
mp = wp.groupby(["ADMIN1", "COUNTRY", "CENTROID_LATITUDE", "CENTROID_LONGITUDE"]).agg(
    EVENTS=("EVENTS", "sum"), FAT=("FATALITIES", "sum")).reset_index()
fig, ax = plt.subplots(figsize=(9, 6))
basemap_ax(ax, 8, 42, 28, 66, res="l", grid=5)
sc = ax.scatter(mp.CENTROID_LONGITUDE, mp.CENTROID_LATITUDE, s=np.sqrt(mp.EVENTS) * 7, c=np.log10(mp.FAT + 1),
                cmap="Reds", vmin=0, vmax=3, edgecolor="white", linewidth=0.6, alpha=0.9, zorder=5)
for cp in ["Strait of Hormuz", "Bab-el-Mandeb", "Suez Canal"]:
    la, lo = CHOKEPOINTS[cp]
    ax.plot(lo, la, marker="D", color=C["blue"], ms=7, mec="white", zorder=6)
    ax.annotate(cp, (lo, la), xytext=(6, -10), textcoords="offset points", fontsize=8, color=C["blue"], fontweight="bold")
lev = mp[mp.CENTROID_LONGITUDE < 38.5]
ax.annotate(f"Levant front (Lebanon, Israel, Palestine, Syria W)\n{lev.EVENTS.sum():,} events, {lev.FAT.sum():,} fatalities",
            (35.5, 33.3), xytext=(29, 38.8), fontsize=7.5, color=C["ink"],
            arrowprops=dict(arrowstyle="-", color=C["muted"], lw=0.6))
for _, r in mp[mp.CENTROID_LONGITUDE >= 38.5].nlargest(6, "EVENTS").iterrows():
    ax.annotate(f"{r.ADMIN1} ({r.EVENTS:,})", (r.CENTROID_LONGITUDE, r.CENTROID_LATITUDE), xytext=(6, 4),
                textcoords="offset points", fontsize=7, color=C["ink"])
cb = fig.colorbar(sc, ax=ax, fraction=0.03, pad=0.04)
cb.set_label("log10(fatalities + 1)")
ax.set_title("Figure 5.7  Political violence, 28 Feb - 10 Apr 2026 (bubble = events, colour = fatalities)")
save(fig, "f5_7_war_map")
table(mp.sort_values("EVENTS", ascending=False).head(15)[["COUNTRY", "ADMIN1", "EVENTS", "FAT"]]
      .rename(columns={"FAT": "FATALITIES"}), "t5_3_top_admin1_war")

# ---------------------------------------------------------------- 5.8 maritime conflict
# Figure 5.8: conflict at sea - events per year by sea area and by type (the Red Sea / Indian Ocean campaign).
m = a[a.MARITIME]
mt = m.pivot_table(index="YEAR", columns="ADMIN1", values="EVENTS", aggfunc="sum").fillna(0)
ms = m.groupby("SUB_EVENT_TYPE").EVENTS.sum().sort_values()
fig, ax = plt.subplots(1, 2, figsize=(9, 3.3), gridspec_kw={"width_ratios": [1.2, 1]})
bottom = np.zeros(len(mt))
for i, c in enumerate(mt.columns):
    ax[0].bar(mt.index, mt[c], bottom=bottom, color=SERIES[i], label=c, width=0.7, edgecolor="white", linewidth=0.8)
    bottom += mt[c].values
ax[0].legend(loc="upper left")
ax[0].set_title("At-sea events per year")
ax[0].grid(axis="x", visible=False)
ms = ms[ms >= 10]
ax[1].barh(ms.index, ms.values, color=C["blue"], height=0.6)
ax[1].set_title("At-sea events by sub-type (2015-26)")
ax[1].grid(axis="y", visible=False)
fig.suptitle("Figure 5.8  Conflict at sea - the Red Sea/Indian Ocean campaign", x=0.01, ha="left", fontsize=11, fontweight="bold")
fig.tight_layout()
save(fig, "f5_8_maritime")

# ---------------------------------------------------------------- statistics: pre-war vs war
# STATISTICAL TEST: war weeks vs the pre-war year.
# Mann-Whitney U compares two groups without assuming a bell curve. 'greater' tests whether war weeks are
# higher.
# The ratio of the two weekly means gives the headline '2.9 times'.
base = pv[(pv.WEEK >= "2025-02-28") & (pv.WEEK < WAR0)].groupby("WEEK").EVENTS.sum()
war = pv[(pv.WEEK >= WAR0) & (pv.WEEK < "2026-04-11")].groupby("WEEK").EVENTS.sum()
post = pv[(pv.WEEK >= "2026-04-11")].groupby("WEEK").EVENTS.sum()
mw = stats.mannwhitneyu(war, base, alternative="greater")
iran = pv[pv.COUNTRY == "Iran"].groupby("WEEK").EVENTS.sum()
# Store the headline numbers used in the report text.
put_metrics(
    pv_base_wk=round(base.mean(), 0), pv_war_wk=round(war.mean(), 0), pv_post_wk=round(post.mean(), 0),
    pv_war_ratio=round(war.mean() / base.mean(), 2), mw_p=float(mw.pvalue), mw_U=float(mw.statistic),
    changepoints=[f"{c:%d %b %Y}" for c in cps], drone_share_first=round(dshare.iloc[0], 1),
    drone_share_last=round(dshare.iloc[-1], 1), drone_share_slope_pp_per_q=round(lr.slope, 2),
    drone_share_r2=round(lr.rvalue ** 2, 2), drone_share_p=float(lr.pvalue),
    maritime_2023=int(mt.loc[2023].sum()), maritime_2024=int(mt.loc[2024].sum()),
    maritime_2022=int(mt.loc[2022].sum()), maritime_2025=int(mt.loc[2025].sum()),
    maritime_2026=int(mt.loc[2026].sum()), maritime_total=int(m.EVENTS.sum()),
    iran_riot_fat_jan26=int(a[(a.COUNTRY == "Iran") & (a.WEEK == "2026-01-03")].FATALITIES.sum()),
    iran_war_events=int(wp[wp.COUNTRY == "Iran"].EVENTS.sum()), iran_war_fat=int(wp[wp.COUNTRY == "Iran"].FATALITIES.sum()),
    iran_pre_wk=round(iran[(iran.index >= "2025-02-28") & (iran.index < WAR0)].mean(), 1),
    war_events_total=int(wp.EVENTS.sum()), war_fat_total=int(wp.FATALITIES.sum()),
    yr_2024_events=int(yr.EVENTS[2024]), yr_2025_events=int(yr.EVENTS[2025]), yr_2026_events=int(yr.EVENTS[2026]),
    yr_2017_fat=int(yr.FATALITIES[2017]),
    war_countries=int(wp[wp.EVENTS > 0].COUNTRY.nunique()),
)
print(seg_tab)
print("MW p", mw.pvalue, "ratio", war.mean() / base.mean())
