"""Stage 8 - the trajectory to 2030: statistical trend, announced constellations, and the collision-risk index."""

# =====================================================================================================
# ANNOTATED SOURCE - Stage 8: prediction (booklet Chapter 8)
# -----------------------------------------------------------------------------------------------------
# The theme asks for 'trends and predictions towards the future trajectory'. Two independent routes:
#   A. STATISTICAL: Holt's damped-trend exponential smoothing on the log of payloads in orbit (year-end 2000-2026),
#      with an 80% interval from 2,000 simulated futures (seeded). Back-tested by fitting to 2000-2021 and forecasting
#      2022-2026 (error reported).
#   B. BOTTOM-UP SCENARIOS: working satellites in 2030 built from the announced mega-constellations (Starlink, Kuiper,
#      Guowang, Qianfan) plus everything else, under Low / Base / High deployment assumptions (stated in the table).
#   C. CONGESTION 2030: each scenario's new satellites are placed in their announced altitude shells and the
#      collision-risk index (sum over 25-km shells of n^2 / volume, 2014 = 1) is recomputed.
# =====================================================================================================
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from common import C, CATALOGUE_DATE, CLEAN, EARTH_R, SNAPSHOT_CDM, TAB, put_metrics, save, table

print("Stage 8: forecast")
pop = pd.read_csv(TAB / "t2_population_by_year.csv").set_index("year")
c = pd.read_parquet(CLEAN / "satcat.parquet")
y = np.log(pop.Payload.loc[2000:2026].astype(float))
y.index = pd.RangeIndex(2000, 2027)

# ---------------------------------------------------------------- A. statistical trend with back-test
def fit(series):
    return ExponentialSmoothing(series.values, trend="add", damped_trend=True).fit(optimized=True)

bt = fit(y.loc[:2021])
bt_fc = np.exp(bt.forecast(5))
bt_err = float(np.mean(np.abs(bt_fc - pop.Payload.loc[2022:2026].values) / pop.Payload.loc[2022:2026].values) * 100)
m = fit(y)
H = 4
sims = m.simulate(H, repetitions=2000, error="add", rng=np.random.default_rng(1))
sims = np.exp(np.asarray(sims))
fc_mid = np.exp(m.forecast(H))
fc_lo, fc_hi = np.percentile(sims, 10, axis=1), np.percentile(sims, 90, axis=1)
fyrs = np.arange(2027, 2027 + H)
table(pd.DataFrame({"year": fyrs, "payloads in orbit (median)": fc_mid.round(0), "80% low": fc_lo.round(0), "80% high": fc_hi.round(0)}),
      "t8_trend_forecast")

# ---------------------------------------------------------------- B. bottom-up scenarios for 2030 (working satellites)
now = c[c.operational & c.OBJECT_TYPE.eq("PAY")]
cur = now.constellation.value_counts()
mega = ["Starlink (US)", "Kuiper (US)", "Guowang (China)", "Qianfan (China)"]
others_now = int(len(now) - cur.reindex(mega).fillna(0).sum())
growth_others = {"Low": 0.03, "Base": 0.07, "High": 0.12}                  # annual growth of all other satellites
SC = {  # working satellites in 2030; filings: Starlink ~19,400 authorised, Kuiper 3,236, Guowang 12,992, Qianfan ~14,000
    "Low": {"Starlink (US)": 12000, "Kuiper (US)": 1600, "Guowang (China)": 800, "Qianfan (China)": 800},
    "Base": {"Starlink (US)": 15000, "Kuiper (US)": 3236, "Guowang (China)": 3000, "Qianfan (China)": 3000},
    "High": {"Starlink (US)": 19400, "Kuiper (US)": 3236, "Guowang (China)": 6500, "Qianfan (China)": 6500},
}
rows = []
for k, d in SC.items():
    oth = others_now * (1 + growth_others[k]) ** 4
    rows.append({"Scenario": k, **{m_: v for m_, v in d.items()}, "All other satellites": round(oth), "Total 2030": round(sum(d.values()) + oth)})
sc = pd.DataFrame(rows)
table(sc, "t8_scenarios_2030")

# ---------------------------------------------------------------- C. collision-risk index in 2030
W = 25
edges = np.arange(200, 2000 + W, W)
vol = 4 / 3 * np.pi * ((EARTH_R + edges[1:]) ** 3 - (EARTH_R + edges[:-1]) ** 3)


def leo_hist(df):
    d = df[(df.APOGEE < 2000) & df.alt_mean.notna()]
    return np.histogram(d.alt_mean, edges)[0].astype(float)


def on_orbit(df, t):
    return df[(df.launch <= t) & (df.decay.isna() | (df.decay > t))]


n14, n26 = leo_hist(on_orbit(c, SNAPSHOT_CDM)), leo_hist(on_orbit(c, CATALOGUE_DATE))
risk = lambda n: float((n ** 2 / vol).sum())
r14 = risk(n14)
SHELL = {"Starlink (US)": (450, 575), "Kuiper (US)": (575, 650), "Guowang (China)": (1100, 1175), "Qianfan (China)": (1050, 1125)}
oth_leo = leo_hist(now[now.constellation.eq("Other")])
risk_rows = [("Jan 2014", 1.0), (f"{CATALOGUE_DATE:%b %Y}", risk(n26) / r14)]
for k, d in SC.items():
    n = n26.copy()
    for m_, v in d.items():
        add = max(v - cur.get(m_, 0), 0)
        lo_, hi_ = SHELL[m_]
        idx = (edges[:-1] >= lo_) & (edges[:-1] < hi_)
        n[idx] += add / idx.sum()
    n += oth_leo / max(oth_leo.sum(), 1) * (sc.set_index("Scenario").loc[k, "All other satellites"] - others_now) * (oth_leo.sum() / max(others_now, 1))
    risk_rows.append((f"2030 {k}", risk(n) / r14))
rk = pd.DataFrame(risk_rows, columns=["Point", "Collision-risk index (2014 = 1)"]).round(1)
table(rk, "t8_risk_index")

fig, ax = plt.subplots(1, 2, figsize=(9, 3.3), gridspec_kw={"width_ratios": [1.3, 1]})
ax[0].plot(pop.loc[2000:2026].index, pop.Payload.loc[2000:2026] / 1000, color=C["blue"], lw=2, label="payloads in orbit (catalogue)")
ax[0].plot(fyrs, fc_mid / 1000, color=C["orange"], lw=2, ls="--", label="statistical trend (damped)")
ax[0].fill_between(fyrs, fc_lo / 1000, fc_hi / 1000, color=C["orange"], alpha=0.18, label="80% interval")
for k, col in zip(["Low", "Base", "High"], [C["aqua"], C["violet"], C["red"]]):
    v = sc.set_index("Scenario").loc[k, "Total 2030"] / 1000
    ax[0].plot([2030], [v], "o", color=col, ms=7)
    ax[0].text(2030.4, v, f"{k}: {v:.0f}k", fontsize=7, va="center", color=col)
ax[0].set_xlim(2000, 2033.2)
ax[0].set_ylabel("thousand satellites")
ax[0].legend(fontsize=7, loc="upper left")
ax[0].set_title("Payloads in orbit and 2030 scenarios", fontsize=9)
ax[1].bar(rk.Point, rk["Collision-risk index (2014 = 1)"], color=[C["muted"], C["blue"], C["aqua"], C["violet"], C["red"]], width=0.6)
for i, v in enumerate(rk["Collision-risk index (2014 = 1)"]):
    ax[1].text(i, v + 0.5, f"x{v:.0f}" if v >= 2 else "x1", ha="center", fontsize=8, fontweight="bold")
ax[1].tick_params(axis="x", labelsize=7, rotation=20)
ax[1].set_title("Collision-risk index (LEO, 2014 = 1)", fontsize=9)
ax[1].grid(axis="x", visible=False)
fig.suptitle("The trajectory: tens of thousands of satellites by 2030, and a sky many times riskier", x=0.01, ha="left",
             fontsize=11, fontweight="bold")
fig.tight_layout()
save(fig, "f8_1_forecast")

scs = sc.set_index("Scenario")
put_metrics(
    fc_2030_mid=int(round(fc_mid[-1], -2)), fc_2030_lo=int(round(fc_lo[-1], -2)), fc_2030_hi=int(round(fc_hi[-1], -2)), fc_bt_mape=round(bt_err, 1),
    sc_low=int(scs.loc["Low", "Total 2030"]), sc_base=int(scs.loc["Base", "Total 2030"]), sc_high=int(scs.loc["High", "Total 2030"]),
    others_now=others_now, risk_now=float(rk.iloc[1, 1]), risk_2030_low=float(rk.iloc[2, 1]), risk_2030_base=float(rk.iloc[3, 1]),
    risk_2030_high=float(rk.iloc[4, 1]),
)
print(sc.to_string(), "\n", rk, "\ntrend", fc_mid, fc_lo, fc_hi, "backtest MAPE", bt_err)
