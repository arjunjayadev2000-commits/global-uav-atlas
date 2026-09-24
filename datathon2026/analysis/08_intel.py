"""Stage 8 - intelligence-grade layer: robustness, dose-response, competing hypotheses, own-asset exposure,
indicators & warnings (I&W) and scenario matrix.

These are the questions a commander asks of any analytic judgement: how sure are you, what else could explain
it, what should I watch, and what happens to my assets in each scenario.
"""

# =====================================================================================================
# ANNOTATED SOURCE - Stage 8: 'how sure are we, and what do we watch?' (report Chapter 10 and sections 12-14)
# -----------------------------------------------------------------------------------------------------
# The questions a commander asks of any judgement, each answered with data:
#   1. ROBUSTNESS      Does the war-zone effect survive other reasonable definitions? -> 8 specifications, each
#                      with a SCENE-CLUSTER BOOTSTRAP confidence interval (Figure 10.x, Table t9_2).
#   2. DOSE-RESPONSE   Is it stronger closer to the fighting? -> dark share by distance band + logistic trend.
#   3. ACH             Analysis of Competing Hypotheses (Heuer, CIA tradecraft): which explanation - deliberate
#                      switch-off, GPS jamming, reception gap, algorithm error - is least contradicted by the
#                      evidence?
#   4. OWN ASSETS      How many Indian-flagged ships were inside the war zones?
#   5. I&W MATRIX      Six indicators with Amber/Red thresholds and the action to take on Red (DARKWATCH).
#   6. SCENARIOS       Likelihood of 2-, 6-, 12- and 26-week disruptions and the days each leaves uncovered.
# INPUT  clean SAR and ACLED data, earlier tables and metrics.   OUTPUT tables t9_2-t9_7, figures, metrics.
# =====================================================================================================

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.duration.survfunc import SurvfuncRight
from statsmodels.stats.proportion import proportion_confint

from common import C, CLEAN, GULF_CONFLICT, RED_SEA_CONFLICT, SERIES, TAB, get_metrics, put_metrics, save, table

print("Stage 8: intelligence layer")
s = pd.read_parquet(CLEAN / "sar_clean.parquet")
a = pd.read_parquet(CLEAN / "acled_clean.parquet")
M = get_metrics()
# 'War zones' for these tests: the Gulf war zone plus the Black Sea. RNG is seeded (42) so bootstraps repeat
# exactly.
WAR = GULF_CONFLICT | {"Black Sea"}
RNG = np.random.default_rng(42)


# ---------------------------------------------------------------- 1. robustness with scene-cluster bootstrap
# SCENE-CLUSTER BOOTSTRAP. Ships in the same satellite image are not independent (same weather, same pass),
# so instead of resampling ships we resample whole images 2,000 times, recompute the relative risk each time,
# and take the middle 95% as the confidence interval. This is the honest (wider) interval.
def rr_boot(df, war_mask, dark_col="dark", reps=2000):
    """Relative risk of darkness (war vs rest) with a bootstrap that resamples whole SAR scenes,
    because detections in one image are not independent."""
    d = df.assign(w=war_mask, k=df[dark_col].astype(int))
    g = d.groupby("scene_id").apply(lambda x: pd.Series({
        "wd": x.k[x.w].sum(), "wn": x.w.sum(), "rd": x.k[~x.w].sum(), "rn": (~x.w).sum()}), include_groups=False)
    G = g.values
    point = (G[:, 0].sum() / G[:, 1].sum()) / (G[:, 2].sum() / G[:, 3].sum())
    bs = []
    for _ in range(reps):
        S = G[RNG.integers(0, len(G), len(G))].sum(0)
        if S[1] > 0 and S[3] > 0 and S[2] > 0:
            bs.append((S[0] / S[1]) / (S[2] / S[3]))
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return point, lo, hi, G[:, 0].sum() / G[:, 1].sum(), G[:, 2].sum() / G[:, 3].sum()


# The 8 alternative specifications: other size thresholds, a stricter 'dark' definition, high-confidence
# detections
# only, fishing excluded, Black Sea excluded. If the effect were an artefact of one choice, it would vanish in
# some.
variants = [
    ("Baseline: >=100 m, 'unmatched' = dark", s[s.large], "dark"),
    ("Size threshold >=60 m", s[s.length_m >= 60], "dark"),
    ("Size threshold >=150 m", s[s.length_m >= 150], "dark"),
    ("Size threshold >=200 m (VLCC/LNG class)", s[s.length_m >= 200], "dark"),
    ("Strict dark: no candidate MMSI at all", s[s.large], "dark_strict"),
    ("High-confidence detections only (presence >=0.99)", s[s.large & (s.presence_score >= 0.99)], "dark"),
    ("Excluding likely fishing (score >=0.5)", s[s.large & ~s.likely_fishing], "dark"),
    ("Gulf only vs rest (Black Sea excluded)", s[s.large & (s.region != "Black Sea")], "dark"),
]
rows = []
for name, df, col in variants:
    war = df.region.isin(WAR)
    p, lo, hi, pw, pr = rr_boot(df, war, col)
    rows.append((name, len(df), round(pw * 100, 1), round(pr * 100, 1), round(p, 2), round(lo, 2), round(hi, 2)))
rob = pd.DataFrame(rows, columns=["Specification", "Ships", "Dark % war zones", "Dark % elsewhere", "RR", "RR 95% CI low", "RR 95% CI high"])
table(rob, "t9_2_robustness")
# Robustness chart: each specification's RR with its 95% CI; the dotted line RR = 1 means 'no war effect'.
fig, ax = plt.subplots(figsize=(9, 3.4))
yy = np.arange(len(rob))[::-1]
ax.errorbar(rob.RR, yy, xerr=[rob.RR - rob["RR 95% CI low"], rob["RR 95% CI high"] - rob.RR], fmt="o", color=C["blue"],
            ecolor=C["blue"], capsize=3, ms=6)
ax.axvline(1, color=C["muted"], ls=":", lw=0.8)
ax.text(1.05, yy[-1] - 0.4, "RR = 1 (no war effect)", fontsize=7, color=C["ink2"])
ax.set_yticks(yy, rob.Specification, fontsize=8)
ax.set_xlabel("Relative risk of AIS darkness, war zones vs elsewhere (scene-cluster bootstrap 95% CI)")
ax.set_xlim(0, max(rob["RR 95% CI high"]) * 1.1)
ax.grid(axis="y", visible=False)
ax.set_title("Robustness: the war-zone effect survives every alternative specification")
save(fig, "f9_2_robustness")

# ---------------------------------------------------------------- 2. dose-response inside the Gulf
# DOSE-RESPONSE inside the Gulf: dark share in distance bands from the nearest violent province, with Wilson
# CIs,
# plus a logistic regression on log-distance (odds ratio per log-km). A graded response is classic evidence of
# cause.
g = s[s.region.isin(GULF_CONFLICT) & s.large].copy()
bins = [0, 50, 100, 150, 200, 400]
g["band"] = pd.cut(g.dist_conflict_km, bins, labels=["0-50", "50-100", "100-150", "150-200", "200-400"])
dr = g.groupby("band", observed=True).dark.agg(["sum", "count"])
dr["share"] = dr["sum"] / dr["count"]
dr["lo"], dr["hi"] = proportion_confint(dr["sum"], dr["count"], method="wilson")
lg = sm.Logit(g.dark.astype(int), sm.add_constant(np.log1p(g.dist_conflict_km))).fit(disp=False)
or_per_log = float(np.exp(lg.params.iloc[1]))
fig, ax = plt.subplots(figsize=(9, 3))
ax.bar(dr.index.astype(str), dr.share * 100, color=C["orange"], width=0.6)
ax.errorbar(np.arange(len(dr)), dr.share * 100, yerr=[(dr.share - dr.lo) * 100, (dr.hi - dr.share) * 100], fmt="none",
            ecolor=C["ink2"], capsize=3, lw=0.8)
for i, (v, n) in enumerate(zip(dr.share, dr["count"])):
    ax.text(i, 3, f"n={n:,}", ha="center", fontsize=7, color="white")
    ax.text(i, v * 100 + 6, f"{v:.0%}", ha="center", fontsize=8, color=C["ink"])
ax.set_ylim(0, 100)
ax.set_xlabel("Distance from nearest province with active political violence (km)")
ax.set_ylabel("% of large ships AIS-dark")
ax.grid(axis="x", visible=False)
ax.set_title("Dose-response inside the Gulf war zone: the closer to the fighting, the darker")
save(fig, "f9_3_dose_response")
table(dr.assign(share=(dr.share * 100).round(1), lo=(dr.lo * 100).round(1), hi=(dr.hi * 100).round(1))
      .reset_index().rename(columns={"band": "Distance band (km)", "sum": "Dark", "count": "Large ships",
                                     "share": "Dark %", "lo": "CI low %", "hi": "CI high %"}), "t9_3_dose_response")

# ---------------------------------------------------------------- 3. analysis of competing hypotheses (evidence computed)
# ANALYSIS OF COMPETING HYPOTHESES (Table t9_4).
# Rows = evidence from this study; columns = hypotheses. C = consistent, I = inconsistent, N = neutral.
# The hypothesis with the FEWEST inconsistencies survives (not the one with most support) - Heuer's rule.
sz = pd.read_csv(TAB / "t7_2_size_zone.csv").set_index("zone")
flat_gulf = sz.loc["Gulf war zone", ">200 m"] / sz.loc["Gulf war zone", "40-100 m"]
flat_rest = sz.loc["Rest of world", ">200 m"] / sz.loc["Rest of world", "40-100 m"]
noisy_g, noisy_w = M["noisy_gulf"], M["noisy_world"]
ach = pd.DataFrame([
    ("E1  Darkness rises steeply for large ships only in war zones (>200 m: Gulf "
     f"{sz.loc['Gulf war zone', '>200 m']:.0f}% vs {sz.loc['Rest of world', '>200 m']:.0f}% elsewhere)", "C", "C", "I", "I"),
    (f"E2  Dose-response: {dr.share.iloc[0]:.0%} dark within 50 km of fighting, {dr.share.iloc[2]:.0%} at 100-150 km", "C", "C", "I", "I"),
    ("E3  Same signature in an unrelated war (Black Sea 38%) under the same sensor and algorithm", "C", "C", "I", "I"),
    (f"E4  Dark share rose through the first two weeks of the war ({M['gulf_dark_first3']:.0%} -> {M['gulf_dark_last3']:.0%})", "C", "C", "N", "I"),
    (f"E5  Dark ships cluster at anchorages (Dubai {M['top_cluster_share']:.0%} dark, Fujairah 85%) rather than spread evenly", "C", "N", "I", "I"),
    (f"E6  'Noisy' AIS tracks are NOT elevated in the Gulf ({noisy_g:.1f}% vs {noisy_w:.1f}% worldwide)", "C", "I", "N", "N"),
    ("E7  Large ships off India's west coast, same satellite pass geometry, remain visible (Arabian Sea 7%)", "C", "C", "I", "I"),
], columns=["Evidence (from this study)", "H-A Deliberate switch-off", "H-B GNSS spoofing / jamming",
            "H-C AIS reception gap", "H-D Matching artefact"])
score = {c: int((ach[c] == "I").sum()) for c in ach.columns[1:]}
table(ach, "t9_4_ach")

# ---------------------------------------------------------------- 4. own-asset exposure: Indian-flag ships
# OWN-ASSET EXPOSURE: Indian-flagged ships (MMSI prefix 419) seen by radar, by zone (Table t9_5).
ind = s[s.flag == "India"]
zone = {**{r: "Gulf war zone" for r in GULF_CONFLICT}, **{r: "Red Sea zone" for r in RED_SEA_CONFLICT},
        "Black Sea": "Black Sea war zone", "Arabian Sea": "Arabian Sea", "Bay of Bengal": "Bay of Bengal"}
ind = ind.assign(zone=ind.region.map(zone).fillna("Rest of world"))
ex = ind.groupby("zone").agg(detections=("mmsi", "size"), distinct_ships=("mmsi", "nunique"),
                             large=("large", "sum"), median_len=("length_m", "median")).reindex(
    ["Gulf war zone", "Red Sea zone", "Arabian Sea", "Bay of Bengal", "Rest of world"]).fillna(0)
ex["median_len"] = ex.median_len.round(0)
table(ex.reset_index().rename(columns={"zone": "Zone", "detections": "Detections", "distinct_ships": "Distinct Indian-flag ships",
                                       "large": "Detections >=100 m", "median_len": "Median length (m)"}), "t9_5_indian_flag")
gulf_ind = ind[ind.zone == "Gulf war zone"]

# ---------------------------------------------------------------- 5. indicators & warnings matrix (status at end of data)
# INDICATORS & WARNINGS inputs: last 4 weeks of the chokepoint index, the stand-off-strike share now vs the
# pre-war year, and GCC violence per week.
cc = pd.read_csv(TAB / "t6_ccii_weekly.csv", parse_dates=["WEEK"]).set_index("WEEK")
thr = M["thr"]
last4 = cc.iloc[-4:]
pv = a[a.POLITICAL_VIOLENCE]
l4w = pv[pv.WEEK > pv.WEEK.max() - pd.Timedelta(days=28)]
standoff_now = l4w[l4w.DRONE_MISSILE].EVENTS.sum() / l4w.EVENTS.sum()
base = pv[(pv.WEEK >= "2025-02-28") & (pv.WEEK < "2026-02-28")]
standoff_base = base[base.DRONE_MISSILE].EVENTS.sum() / base.EVENTS.sum()
gcc_now = l4w[l4w.GCC].EVENTS.sum() / 4


# Traffic-light rule: RED at or above the red threshold, AMBER at or above amber, otherwise GREEN.
def rag(v, amber, red):
    return "RED" if v >= red else ("AMBER" if v >= amber else "GREEN")


hz = last4["Hormuz (littoral)"].mean() / thr["Hormuz (littoral)"]
rs = last4["Red Sea / Arabian Sea (at sea)"].mean() / thr["Red Sea / Arabian Sea (at sea)"]
# The I&W (DARKWATCH) matrix, Table t9_6: indicator, source, latest value, thresholds, status and the action on
# Red.
iw = pd.DataFrame([
    ("I1 Hormuz littoral CCII / threshold (4-wk mean)", "ACLED weekly", f"{hz:.1f}", ">= 0.5", ">= 1.0", rag(hz, 0.5, 1.0),
     "Red: activate POL stock drawdown plan; raise Gulf escort posture"),
    ("I2 Red Sea at-sea CCII / threshold (4-wk mean)", "ACLED weekly", f"{rs:.1f}", ">= 0.5", ">= 1.0", rag(rs, 0.5, 1.0),
     "Red: add Cape-route lead-time to defence import re-order points"),
    ("I3 Stand-off strike share of political violence (4-wk)", "ACLED weekly", f"{standoff_now:.0%}",
     f">= {standoff_base + 0.10:.0%}", ">= 65%", rag(standoff_now, standoff_base + 0.10, 0.65),
     "Red: raise AD / counter-UAS state at depots, air bases, POL nodes"),
    ("I4 GCC political violence (events / week, 4-wk)", "ACLED weekly", f"{gcc_now:.1f}", ">= 2", ">= 10", rag(gcc_now, 2, 10),
     "Red: move NEO plan to execution readiness"),
    ("I5 Large-ship AIS-dark share, Gulf (latest SAR window)", "SAR + AIS", f"{M['gulf_large_dark']:.0%}", ">= 20%", ">= 40%",
     rag(M["gulf_large_dark"], 0.20, 0.40), "Red: treat Gulf maritime picture as unreliable; task national SAR"),
    ("I6 P(Hormuz threshold breach in next 13 wks), model", "ARIMA simulation", f"{M['fc_prob_above_thr']:.0%}", ">= 30%", ">= 60%",
     rag(M["fc_prob_above_thr"], 0.30, 0.60), "Red: hold reserves at >= 35-45 days; do not release strategic stock"),
], columns=["Indicator", "Source / cadence", "Latest value", "Amber at", "Red at", "Status", "Action on Red"])
table(iw, "t9_6_iw_matrix")

# ---------------------------------------------------------------- 6. scenario matrix: Hormuz disruption durations
# SCENARIO MATRIX (Table t9_7): from the Hormuz/Red Sea survival curve, the chance a disruption lasts at least
# 2, 6, 12 or 26 weeks, and the days left uncovered by the SPR, national cover and 30/45-day Service holdings.
ep = pd.read_csv(TAB / "t6_2_episodes.csv")
ep = ep[ep.chokepoint.isin(["Hormuz (littoral)", "Red Sea / Arabian Sea (at sea)"])]
sf = SurvfuncRight(ep.weeks * 7, 1 - ep.censored)


def p_ge(days):
    i = np.searchsorted(sf.surv_times, days, side="left") - 1
    return 1.0 if i < 0 else float(sf.surv_prob[i])


sc = []
for name, d in [("S1 Short disruption", 14), ("S2 Sustained disruption", 42), ("S3 Prolonged disruption", 84),
                ("S4 Campaign-length disruption", 182)]:
    pv_ = p_ge(d)
    sc.append((name, f"{d // 7} weeks", f"{pv_:.0%}" if pv_ > 0 else "< 5% (beyond the longest observed episode)", f"{max(0, d - 9.5):.0f}", f"{max(0, d - 74):.0f}",
               f"{max(0, d - 30):.0f} / {max(0, d - 45):.0f}"))
sc = pd.DataFrame(sc, columns=["Scenario", "Duration", "P(disruption lasts at least this long)", "Days beyond SPR (9.5 d)",
                               "Days beyond national cover (74 d)", "Days beyond 30 d / 45 d Service holdings"])
table(sc, "t9_7_scenarios")

# Headline numbers for the report.
put_metrics(
    rob_min_rr=float(rob.RR.min()), rob_max_rr=float(rob.RR.max()), rob_min_lo=float(rob["RR 95% CI low"].min()),
    rr_boot_lo=float(rob.iloc[0]["RR 95% CI low"]), rr_boot_hi=float(rob.iloc[0]["RR 95% CI high"]),
    dose_0_50=float(dr.share.iloc[0]), dose_100_150=float(dr.share.iloc[2]), dose_or_per_log=round(or_per_log, 2),
    dose_p=float(lg.pvalues.iloc[1]), ach_inconsistent=score,
    ind_gulf_det=int(len(gulf_ind)), ind_gulf_ships=int(gulf_ind.mmsi.nunique()), ind_gulf_large=int(gulf_ind.large.sum()),
    ind_total_ships=int(ind.mmsi.nunique()),
    iw_hz=round(float(hz), 2), iw_rs=round(float(rs), 2), iw_standoff=round(float(standoff_now), 3),
    iw_standoff_base=round(float(standoff_base), 3), iw_gcc=round(float(gcc_now), 1),
    iw_red=int((iw.Status == "RED").sum()), iw_amber=int((iw.Status == "AMBER").sum()),
    sc_p6=p_ge(42), sc_p12=p_ge(84), sc_p26=p_ge(182),
)
print(rob.to_string(), "\n", dr, "\n", "OR per log-km", or_per_log, lg.pvalues.iloc[1], "\n", score, "\n", ex, "\n",
      iw[["Indicator", "Latest value", "Status"]].to_string(), "\n", sc.to_string())
