"""Stage 3 - Chokepoint Conflict Intensity Index (CCII), forecasting and survival of disruption episodes."""

# =====================================================================================================
# ANNOTATED SOURCE - Stage 3: chokepoint stress, forecast and crisis duration (report Chapter 6)
# -----------------------------------------------------------------------------------------------------
# QUESTIONS 1. How much violence threatens each sea lane, week by week?  -> Chokepoint Conflict Intensity Index
# (CCII)
#           2. Will Hormuz stay under stress over the next quarter?          -> ARIMA forecast + 4,000
#           simulations
#           3. Once a sea lane is in crisis, how long does the crisis last?  -> survival analysis (Kaplan-Meier,
#           Cox)
# INPUT     data/clean/acled_clean.parquet.
# OUTPUT    Figures 6.1-6.5; tables t6_ccii_weekly, t6_1-t6_4; metrics (thresholds, forecast, survival numbers).
# PLAIN WORDS The CCII is a 'thermometer' of violence per sea lane. A crisis ('episode') is a run of weeks above
#           that lane's own danger line (its 2015-2022 average + 3 standard deviations). Survival analysis then
#           asks
#           what share of crises are still going after N weeks - the same maths used for equipment failure
#           times.
# =====================================================================================================

import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from statsmodels.duration.hazard_regression import PHReg
from statsmodels.duration.survfunc import SurvfuncRight, survdiff
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.statespace.sarimax import SARIMAX

from common import C, CLEAN, SERIES, put_metrics, save, table

warnings.filterwarnings("ignore")
print("Stage 3: chokepoint index")
a = pd.read_parquet(CLEAN / "acled_clean.parquet")
pv = a[a.POLITICAL_VIOLENCE].copy()
# Stand-off strikes are the mode that reaches shipping (missiles, drones, shore artillery) -> weight 1.5.
# Weighting: stand-off strikes (missiles, drones, artillery) can reach ships, so they count 1.5; other violence
# counts 1.
pv["W"] = pv.EVENTS * np.where(pv.REMOTE_VIOLENCE, 1.5, 1.0)

# Each theatre is measured where its threat to shipping actually shows up in the data:
#  - Hormuz: littoral violence within 500 km of the strait (Iran, UAE, Oman, Qatar coasts);
#  - Red Sea / Arabian Sea: ACLED's at-sea 'North Indian Ocean' events (Houthi anti-ship campaign) -
#    Yemen's *land* war would swamp the signal and is falling while sea attacks rise (Figure 6.5);
#  - East Med and Black Sea: ACLED's at-sea events for those waters.
# Which events belong to which sea lane (theatre). Each is a rule applied to the data rows.
CP = {
    "Hormuz (littoral)": lambda d: (d["D_Strait of Hormuz"] <= 500) & ~d.MARITIME,
    "Red Sea / Arabian Sea (at sea)": lambda d: d.ADMIN1.eq("North Indian Ocean"),
    "East Med (at sea)": lambda d: d.ADMIN1.eq("Eastern Mediterranean Sea"),
    "Black Sea (at sea)": lambda d: d.ADMIN1.eq("Wider Black Sea Region"),
}
# Weekly index per theatre (weeks with no events = 0).
weeks = pd.date_range(pv.WEEK.min(), pv.WEEK.max(), freq="7D")
ccii = pd.DataFrame(index=weeks)
for name, sel in CP.items():
    ccii[name] = pv[sel(pv)].groupby("WEEK").W.sum().reindex(weeks, fill_value=0)
# Baseline = 2015-2022, the 'normal' years before the Gaza war and the Red Sea campaign.
base = ccii[(ccii.index >= "2015-01-01") & (ccii.index < "2023-01-01")]
# Disruption threshold per theatre: baseline mean + 3 SD, never below 3 weighted events/week.
THR = np.maximum(base.mean() + 3 * base.std(), 3.0)
# z-score = how many standard deviations above normal. ccii_idx is a 0-100 version (not used for decisions).
z = (ccii - base.mean()) / base.std()
ccii_idx = (ccii / ccii.quantile(0.99) * 100).clip(upper=100)   # 0-100 scale, capped at the 99th pct
table(ccii.assign(**{f"{c} z": z[c].round(2) for c in ccii}).reset_index(names="WEEK"), "t6_ccii_weekly")

# Figure 6.1: the four theatre series with their danger lines; shaded = weeks above the line.
fig, axes = plt.subplots(4, 1, figsize=(9, 7.4), sharex=True)
for ax, (c, col) in zip(axes, zip(ccii.columns, SERIES)):
    ax.plot(ccii.index, ccii[c], color=col, lw=1)
    thr = THR[c]
    ax.axhline(thr, color=C["muted"], ls="--", lw=0.7)
    ax.fill_between(ccii.index, thr, ccii[c], where=ccii[c] > thr, color=col, alpha=0.25)
    ax.set_title(f"{c}  (dashed = disruption threshold, baseline + 3 SD)", fontsize=9)
    ax.set_ylabel("weighted events")
fig.suptitle("Figure 6.1  Chokepoint Conflict Intensity Index (weekly), 2015-2026", x=0.01, ha="left",
             fontsize=11, fontweight="bold")
fig.tight_layout()
save(fig, "f6_1_ccii")

# ---------------------------------------------------------------- 6.2 recent window, z-scores
# Figure 6.2: each theatre divided by its own threshold (1.0 = at the danger line), smoothed over 4 weeks, on a
# log-like scale.
rz = (ccii / THR).rolling(4, min_periods=1).mean()
rz = rz[rz.index >= "2023-06-01"]
fig, ax = plt.subplots(figsize=(9, 3.2))
for c, col in zip(rz.columns, SERIES):
    ax.plot(rz.index, rz[c], color=col, lw=1.4, label=c)
ax.axhline(1, color=C["muted"], ls="--", lw=0.7)
ax.text(rz.index[0], 1.3, "1.0 = disruption threshold", fontsize=7, color=C["ink2"])
ax.set_yscale("symlog", linthresh=1)
ax.set_ylim(0, 60)
for d, lab, yy in [("2023-10-07", "7 Oct 2023", 30), ("2023-11-19", "Houthi anti-ship\ncampaign", 8), ("2026-02-28", "Iran war", 30)]:
    ax.axvline(pd.Timestamp(d), color=C["muted"], lw=0.6, ls=":")
    ax.text(pd.Timestamp(d), yy, " " + lab, fontsize=7, color=C["ink2"])
ax.set_ylabel("index / threshold (4-wk mean)")
ax.legend(loc="upper left", ncol=3, bbox_to_anchor=(0, -0.1))
ax.set_title("Figure 6.2  Theatre stress relative to its own disruption threshold (4-week rolling mean)")
save(fig, "f6_2_ccii_z")

# ---------------------------------------------------------------- 6.3 forecasting (Hormuz)
# FORECASTING (Hormuz).
# Work on log(1 + x) so large spikes do not dominate. Hold back the last 12 weeks (H) as a test set
# and compare three models on how well they predict those unseen weeks (a 'back-test'):
#   naive = repeat the last value; Holt ETS = exponential smoothing with a damped trend;
#   ARIMA(1,0,1) = this week depends on last week and last week's surprise, plus a constant.
HZ = "Hormuz (littoral)"
y = np.log1p(ccii[HZ])
H = 12
train, test = y[:-H], y[-H:]
res = {}
naive = np.repeat(train.iloc[-1], H)
res["Naive (last value)"] = naive
ets = ExponentialSmoothing(train, trend="add", damped_trend=True).fit()
res["Holt damped-trend ETS"] = ets.forecast(H).values
sar = SARIMAX(train, order=(1, 0, 1), trend="c").fit(disp=False)
res["ARIMA(1,0,1)"] = sar.forecast(H).values
# Back-test score: MAE (average absolute error) and RMSE (penalises big misses more), in weighted events per
# week.
bt = []
for k, v in res.items():
    e = np.expm1(v) - np.expm1(test.values)
    bt.append((k, round(np.mean(np.abs(e)), 1), round(np.sqrt(np.mean(e ** 2)), 1)))
bt = pd.DataFrame(bt, columns=["Model", "MAE (weighted events/wk)", "RMSE"])
table(bt, "t6_1_backtest")
best = bt.sort_values("MAE (weighted events/wk)").iloc[0].Model
# Refit ARIMA on all data and forecast 13 weeks (to end-September 2026) with an 80% interval.
final = SARIMAX(y, order=(1, 0, 1), trend="c").fit(disp=False)
fc = final.get_forecast(13)
mean, ci = np.expm1(fc.predicted_mean), np.expm1(fc.conf_int(alpha=0.2))
fidx = pd.date_range(y.index[-1] + pd.Timedelta(days=7), periods=13, freq="7D")
fig, ax = plt.subplots(figsize=(9, 3.2))
hist = ccii[HZ][ccii.index >= "2025-01-01"]
ax.plot(hist.index, hist.values, color=C["blue"], lw=1.4, label="Observed")
ax.plot(fidx, mean.values, color=C["orange"], lw=1.6, label="ARIMA(1,0,1) forecast")
ax.fill_between(fidx, ci.iloc[:, 0].values, ci.iloc[:, 1].values, color=C["orange"], alpha=0.18, label="80% interval")
ax.axhline(THR[HZ], color=C["muted"], ls="--", lw=0.7)
ax.text(hist.index[0], THR[HZ] * 1.06, "disruption threshold", fontsize=7, color=C["ink2"])
ax.legend(loc="upper left")
ax.set_ylabel("weighted events / week")
ax.set_title("Figure 6.3  Hormuz CCII: 13-week forecast to end-Sep 2026")
save(fig, "f6_3_forecast")
put_metrics(fc_best_model=best, fc_end_mean=round(float(mean.iloc[-1]), 1),
            fc_end_lo=round(float(ci.iloc[-1, 0]), 1), fc_end_hi=round(float(ci.iloc[-1, 1]), 1),
            hormuz_thr=round(float(THR[HZ]), 1),
            fc_prob_above_thr=None)

# probability that a forecast week exceeds the disruption threshold (simulation from the fitted model)
# Monte Carlo: simulate 4,000 possible futures from the fitted model (seeded, so results repeat exactly)
# and count the share in which Hormuz crosses its danger line at least once.
sims = final.simulate(nsimulations=13, repetitions=4000, anchor="end", rng=np.random.default_rng(0))
sims = np.expm1(np.asarray(sims).reshape(13, -1))
p_any = float((sims > THR[HZ]).any(axis=0).mean())
put_metrics(fc_prob_above_thr=round(p_any, 3))

# ---------------------------------------------------------------- 6.4 survival of disruption episodes
# EPISODES: turn each weekly series into a list of crises.
rows = []
for c in ccii.columns:
    s = ccii[c]
    above = (s > THR[c]).astype(int)
    # merge one-week dips (a lull inside a crisis is not an end of the crisis)
    # A single quiet week inside a crisis is treated as part of it (a lull is not the end of a crisis).
    above = ((above + above.shift(1, fill_value=0) * above.shift(-1, fill_value=0)) > 0).astype(int)
    # Number the consecutive runs of 'above' weeks; each run is one episode with a start, end, length and peak.
    # censored = 1 when the episode was still going at the end of the data (its true length is unknown, only 'at
    # least').
    run_id = (above.diff().fillna(above.iloc[0]) == 1).cumsum()
    for rid, grp in s[above == 1].groupby(run_id[above == 1]):
        rows.append(dict(chokepoint=c, start=grp.index[0], end=grp.index[-1], weeks=len(grp),
                         peak=grp.max(), censored=int(grp.index[-1] == s.index[-1]),
                         post2023=int(grp.index[0] >= pd.Timestamp("2023-10-01"))))
ep = pd.DataFrame(rows)
ep["event"] = 1 - ep.censored
table(ep.assign(start=ep.start.dt.date, end=ep.end.dt.date).round(1), "t6_2_episodes")

fig, ax = plt.subplots(figsize=(9, 3.4))
# KAPLAN-MEIER survival curve: for each duration t, the estimated share of crises lasting longer than t.
# It handles the censored (still ongoing) episodes correctly. Curves are drawn per theatre (if 5+ episodes)
# and for all theatres together; red lines mark India's SPR (~9.5 days) and total oil cover (~74 days).
km_all = SurvfuncRight(ep.weeks, ep.event)
km_tab = []
for i, (c, g) in enumerate(ep.groupby("chokepoint", sort=False)):
    sf = SurvfuncRight(g.weeks, g.event)
    t = np.r_[0, sf.surv_times]
    p = np.r_[1, sf.surv_prob]
    km_tab.append((c, len(g), int(g.censored.sum()), g.weeks.median(), g.weeks.max()))
    if len(g) < 5:          # too few episodes to draw a meaningful curve
        continue
    ax.step(t, p, where="post", color=SERIES[i], lw=1.8, label=f"{c} (n={len(g)})")
t = np.r_[0, km_all.surv_times]
p = np.r_[1, km_all.surv_prob]
ax.step(t, p, where="post", color=C["ink"], lw=1, ls="--", label=f"All chokepoints (n={len(ep)})")
for wk_, lab in [(74 / 7, "India total oil cover ~74 d"), (9.5 / 7, "SPR only ~9.5 d")]:
    ax.axvline(wk_, color=C["red"], lw=0.8, ls=":")
    ax.text(wk_ + 0.3, 0.9, lab, fontsize=7, color=C["red"], rotation=90, va="top")
ax.set_xlabel("Episode duration (weeks)")
ax.set_ylabel("P(disruption still ongoing)")
ax.set_ylim(0, 1.03)
ax.legend(loc="upper right")
ax.set_title("Figure 6.4  Kaplan-Meier survival of chokepoint disruption episodes")
save(fig, "f6_4_km")


# Read the survival curve at time t (e.g. the share of crises that outlast the SPR).
def surv_at(sf, t):
    idx = np.searchsorted(sf.surv_times, t, side="right") - 1
    return 1.0 if idx < 0 else float(sf.surv_prob[idx])


km_tab = pd.DataFrame(km_tab, columns=["Chokepoint", "Episodes", "Censored (ongoing)", "Median weeks", "Longest weeks"])
table(km_tab, "t6_3_km_summary")
# Log-rank test: do the theatres have different crisis durations?
lr_stat, lr_p = survdiff(ep.weeks, ep.event, ep.chokepoint)
# Cox PH - does the post-Oct-2023 era lengthen episodes? does the chokepoint matter?
# COX proportional-hazards model: which factors make a crisis end sooner or later?
# HR (hazard ratio) < 1 means crises end more slowly, i.e. last longer. post2023 tests whether the era since
# October 2023 produces longer crises.
X = pd.get_dummies(ep[["chokepoint"]], drop_first=True).astype(float)
X["post2023"] = ep.post2023.astype(float)
cox = PHReg(ep.weeks.values, X.values, status=ep.event.values).fit()
cox_tab = pd.DataFrame({"Covariate": X.columns, "coef": cox.params.round(3), "HR = exp(coef)": np.exp(cox.params).round(3),
                        "p-value": cox.pvalues.round(3)})
cox_tab["HR 95% CI"] = [f"{np.exp(l):.2f} - {np.exp(h):.2f}" for l, h in cox.conf_int()]
table(cox_tab, "t6_4_cox")
# Headline numbers: episode counts, median/longest duration, share outlasting the SPR and 74-day cover, test
# results,
# and the war-time multiplier for Hormuz and the Red Sea.
put_metrics(
    ep_n=len(ep), ep_median_wk=float(ep.weeks.median()), ep_mean_wk=round(float(ep.weeks.mean()), 1),
    ep_max_wk=int(ep.weeks.max()), ep_censored=int(ep.censored.sum()),
    km_p_gt_spr=round(surv_at(km_all, 9.5 / 7), 3), km_p_gt_74d=round(surv_at(km_all, 74 / 7), 3),
    km_p_gt_4wk=round(surv_at(km_all, 4), 3), logrank_chi2=round(float(lr_stat), 2), logrank_p=round(float(lr_p), 3),
    cox_post2023_hr=round(float(np.exp(cox.params[-1])), 3), cox_post2023_p=round(float(cox.pvalues[-1]), 3),
    thr=THR.round(1).to_dict(),
    hormuz_war_mult=round(float(ccii.loc["2026-02-28":"2026-04-04", HZ].mean() / base[HZ].mean()), 1),
    redsea_2024_mult=round(float(ccii.loc["2023-11-18":"2024-12-31", "Red Sea / Arabian Sea (at sea)"].mean() / base["Red Sea / Arabian Sea (at sea)"].mean()), 1),
)
print(bt, "\n", km_tab, "\n", cox_tab, "\nlogrank", lr_stat, lr_p)

# ---------------------------------------------------------------- 6.5 Red Sea: violence moves offshore
# Figure 6.5: the Red Sea threat moved offshore - stand-off strikes on Yemen's coast vs violence at sea, per
# year.
yem = pv[(pv["D_Bab-el-Mandeb"] <= 500) & ~pv.MARITIME & pv.REMOTE_VIOLENCE].groupby("YEAR").EVENTS.sum()
sea = pv[pv.ADMIN1.eq("North Indian Ocean")].groupby("YEAR").EVENTS.sum().reindex(yem.index, fill_value=0)
fig, ax = plt.subplots(1, 2, figsize=(9, 3))
ax[0].bar(yem.index, yem.values, color=C["blue"], width=0.7)
ax[0].set_title("Stand-off strikes on land, Yemen littoral (<=500 km of Bab-el-Mandeb)", fontsize=8.5)
ax[1].bar(sea.index, sea.values, color=C["orange"], width=0.7)
ax[1].set_title("Political violence at sea (North Indian Ocean incl. Red Sea)", fontsize=8.5)
for x in ax:
    x.grid(axis="x", visible=False)
    x.set_xticks(yem.index[::2])
fig.suptitle("Figure 6.5  Red Sea theatre - the violence moved offshore after 2023", x=0.01, ha="left",
             fontsize=11, fontweight="bold")
fig.tight_layout()
save(fig, "f6_5_offshore")
put_metrics(yem_land_2019=int(yem.get(2019, 0)), yem_land_2025=int(yem.get(2025, 0)),
            sea_2022=int(sea.get(2022, 0)), sea_2024=int(sea.get(2024, 0)))
