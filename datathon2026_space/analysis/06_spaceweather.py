"""Stage 6 - space weather: solar activity, geomagnetic storms and what they do to satellites and debris."""

# =====================================================================================================
# ANNOTATED SOURCE - Stage 6: the natural adversary (booklet Chapter 6)
# -----------------------------------------------------------------------------------------------------
# QUESTIONS 1. How much more often do dangerous geomagnetic storms occur when the Sun is active? (CDM Dst + sunspots)
#           2. Does the solar cycle show up in how fast objects fall out of orbit? (catalogue re-entries)
# METHOD    - Dst (disturbance storm-time index, nT): storms are runs of hours with Dst <= -50 (moderate), an event is
#             'intense' if its minimum is <= -100 nT and 'severe' if <= -200 nT (NOAA/Gonzalez classes).
#           - Each hour is matched to the nearest smoothed sunspot number; data are cut into 30-day blocks; a Poisson
#             regression gives the change in intense-storm rate per 50 sunspots; Spearman correlation as a check.
#           - Re-entry rate = debris + rocket bodies re-entering in a year / those in low orbit at the start of the year.
#             A periodogram of the de-trended rate finds its dominant cycle without being told the answer.
# =====================================================================================================
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import signal, stats

from common import C, CLEAN, put_metrics, save, table

print("Stage 6: space weather")
dst = pd.read_parquet(CLEAN / "dst.parquet")
ss = pd.read_parquet(CLEAN / "sunspots.parquet")

# ---------------------------------------------------------------- 1. storms vs solar activity (CDM)
rows, blocks = [], []
for per, d in dst.groupby("period"):
    d = d.sort_values("hours").reset_index(drop=True)
    sp = ss[ss.period.eq(per)].sort_values("days")
    d["ssn"] = np.interp(d.hours / 24, sp.days, sp.smoothed_ssn)          # sunspot number at each hour
    below = d.dst <= -50
    run = (below != below.shift()).cumsum()
    ev = d[below].groupby(run[below]).agg(start=("hours", "first"), mn=("dst", "min"), ssn=("ssn", "mean"), dur=("dst", "size"))
    for _, e in ev.iterrows():
        rows.append((per, e.start, e.mn, e.ssn, e.dur))
    d["block"] = (d.hours // (24 * 30)).astype(int)
    for b, g in d.groupby("block"):
        if len(g) < 24 * 25:
            continue
        e_b = ev[(ev.start >= g.hours.min()) & (ev.start <= g.hours.max())]
        blocks.append((per, b, g.ssn.mean(), g.dst.min(), int((e_b.mn <= -100).sum()), int((e_b.mn <= -50).sum())))
events = pd.DataFrame(rows, columns=["period", "start_h", "min_dst", "ssn", "hours"])
blk = pd.DataFrame(blocks, columns=["period", "block", "ssn", "min_dst", "intense", "moderate_plus"])
X = sm.add_constant(blk.ssn / 50)
pois = sm.GLM(blk.intense, X, family=sm.families.Poisson()).fit()
irr = float(np.exp(pois.params.iloc[1]))                                   # rate ratio per +50 sunspots
rho, prho = stats.spearmanr(blk.ssn, blk.min_dst)
hi, lo = blk[blk.ssn >= 100], blk[blk.ssn < 30]
p_hi, p_lo = float((hi.intense > 0).mean()), float((lo.intense > 0).mean())
cls = pd.DataFrame({"Class": ["Moderate (-50 to -100 nT)", "Intense (-100 to -200 nT)", "Severe (<= -200 nT)"],
                    "Events": [int(((events.min_dst <= -50) & (events.min_dst > -100)).sum()),
                               int(((events.min_dst <= -100) & (events.min_dst > -200)).sum()), int((events.min_dst <= -200).sum())]})
table(cls, "t6_storm_classes")
per_tab = dst.groupby("period").agg(hours=("dst", "size"), min_dst=("dst", "min")).join(
    ss.groupby("period").smoothed_ssn.mean().rename("mean_ssn")).join(events.groupby("period").size().rename("storm_events")).round(1)
table(per_tab.reset_index(), "t6_periods")

fig, ax = plt.subplots(1, 2, figsize=(9, 3.2), gridspec_kw={"width_ratios": [1.35, 1]})
a = dst[dst.period.eq("train_a")]
ax[0].plot(a.hours / 24 / 365.25, a.dst, color=C["blue"], lw=0.4)
for thr, lab in [(-100, "intense"), (-200, "severe")]:
    ax[0].axhline(thr, color=C["red"], lw=0.6, ls="--")
    ax[0].text(0.02, thr - 25, lab, fontsize=7, color=C["red"])
ax[0].set_xlabel("years into period A (high solar activity)")
ax[0].set_ylabel("Dst (nT)")
ax[0].set_title("Hourly geomagnetic disturbance (Dst)", fontsize=9)
bins = [0, 30, 60, 100, 200]
blk["band"] = pd.cut(blk.ssn, bins, labels=["<30", "30-60", "60-100", ">=100"])
g = blk.groupby("band", observed=True).intense.agg(["mean", "count"])
ax[1].bar(g.index.astype(str), g["mean"], color=[C["aqua"], C["yellow"], C["orange"], C["red"]], width=0.6)
for i, (m, n_) in enumerate(zip(g["mean"], g["count"])):
    ax[1].text(i, m + 0.02, f"{m:.2f}\n(n={n_})", ha="center", fontsize=7)
ax[1].set_xlabel("smoothed sunspot number")
ax[1].set_ylabel("intense storms per 30 days")
ax[1].grid(axis="x", visible=False)
ax[1].set_title("Storm rate rises with solar activity", fontsize=9)
fig.suptitle("The Sun is the one adversary nobody can deter", x=0.01, ha="left", fontsize=11, fontweight="bold")
fig.tight_layout()
save(fig, "f6_1_storms")

# ---------------------------------------------------------------- 2. the solar cycle in re-entries (catalogue)
c = pd.read_parquet(CLEAN / "satcat.parquet")
leo = c[c.OBJECT_TYPE.isin(["DEB", "R/B"])]
yrs = np.arange(1965, 2026)
rate = []
for y in yrs:
    t0, t1 = pd.Timestamp(f"{y}-01-01"), pd.Timestamp(f"{y}-12-31")
    pop = leo[(leo.launch < t0) & (leo.decay.isna() | (leo.decay >= t0)) & (leo.PERIGEE < 2000)]
    dec = pop[pop.decay.between(t0, t1)]
    rate.append(len(dec) / max(len(pop), 1) * 100)
rate = pd.Series(rate, index=yrs)
lr = np.log(rate)
det = lr - np.poly1d(np.polyfit(yrs, lr, 2))(yrs)
f_, pw = signal.periodogram(det.values, fs=1.0, detrend="linear")
mask = f_ > 0
period_peak = float(1 / f_[mask][np.argmax(pw[mask])])
SOLAR_MAX = [1968.9, 1979.9, 1989.6, 2001.9, 2014.3, 2024.8]           # SILSO smoothed maxima
table(pd.DataFrame({"year": yrs, "reentry_rate_pct": rate.round(2).values}), "t6_reentry_rate")
fig, ax = plt.subplots(figsize=(9, 2.9))
ax.plot(rate.index, rate.values, color=C["violet"], lw=1.8)
for m in SOLAR_MAX:
    ax.axvline(m, color=C["orange"], lw=0.8, ls=":")
ax.text(SOLAR_MAX[0] + 0.3, rate.max() * 0.95, "dotted = solar maxima (SILSO)", fontsize=7, color=C["orange"])
ax.set_ylabel("% of low-orbit debris and\nrocket bodies re-entering")
ax.annotate("2022: Russian ASAT debris\nre-enters", (2022, rate.loc[2022]), xytext=(2008, rate.max() * 0.85), fontsize=7, color=C["ink2"],
            arrowprops=dict(arrowstyle="-", color=C["muted"], lw=0.6))
ax.set_title(f"The solar cycle in the debris record: re-entries peak every ~{period_peak:.0f} years, at solar maximum")
save(fig, "f6_2_reentry_cycle")
near_max = rate[[int(round(m)) for m in SOLAR_MAX if int(round(m)) in rate.index]].mean()
near_min = rate[[y for y in [1976, 1986, 1996, 2008, 2019] if y in rate.index]].mean()
put_metrics(
    storm_events=len(events), storm_intense=int((events.min_dst <= -100).sum()), storm_severe=int((events.min_dst <= -200).sum()),
    dst_min=int(dst.dst.min()), storm_irr50=round(irr, 2), storm_irr_p=float(pois.pvalues.iloc[1]),
    storm_rho=round(float(rho), 2), storm_rho_p=float(prho), p_intense_hi=round(p_hi, 2), p_intense_lo=round(p_lo, 2),
    storm_mult=round(p_hi / max(p_lo, 0.01), 1), reentry_period=round(period_peak, 1),
    reentry_max=round(float(near_max), 1), reentry_min=round(float(near_min), 1),
)
print(cls, "\n", per_tab, "\nIRR", irr, pois.pvalues.iloc[1], "rho", rho, prho, "p hi/lo", p_hi, p_lo, "\nperiod", period_peak, near_max, near_min)
