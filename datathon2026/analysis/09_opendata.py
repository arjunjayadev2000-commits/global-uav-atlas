"""Stage 9 - economic transmission using open-source data (GitHub-hosted mirrors of public series).

Sources (data/open/):
  brent_daily.csv, wti_daily.csv  - datasets/oil-prices (U.S. EIA spot prices), to 15 Sep 2026
  inr_usd_daily.csv               - datasets/exchange-rates (U.S. Federal Reserve H.10), to 18 Sep 2026
  owid_energy_selected.csv        - Our World in Data energy dataset (Energy Institute Statistical Review), to 2024
Questions: did the conflict move the oil price and the rupee, does conflict intensity lead the oil price, what did
the 2026 war cost India, and did the June 2026 I&W call hold up out-of-sample?
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.tsa.stattools import grangercausalitytests

from common import C, ROOT, SERIES, TAB, get_metrics, put_metrics, save, table

print("Stage 9: open-source economic transmission")
OPEN = ROOT / "data" / "open"
M = get_metrics()
brent = pd.read_csv(OPEN / "brent_daily.csv", parse_dates=["Date"]).set_index("Date").Price.dropna()
brent = brent[brent > 0]
fx = pd.read_csv(OPEN / "inr_usd_daily.csv", parse_dates=["Date"]).set_index("Date")["Exchange rate"].dropna()
owid = pd.read_csv(OPEN / "owid_energy_selected.csv")
cc = pd.read_csv(TAB / "t6_ccii_weekly.csv", parse_dates=["WEEK"]).set_index("WEEK")
DATA_END = pd.Timestamp("2026-06-27")      # last ACLED week; everything after is out-of-sample
WAR0 = pd.Timestamp("2026-02-28")

# ---------------------------------------------------------------- 1. timeline: oil price with conflict markers
fig, ax = plt.subplots(2, 1, figsize=(9, 5.2), sharex=True, gridspec_kw={"height_ratios": [1.6, 1]})
b = brent["2022-01-01":]
ax[0].plot(b.index, b.values, color=C["ink"], lw=1)
for d0, d1, lab in [("2023-11-18", "2024-12-31", "Houthi anti-ship campaign"), ("2026-02-28", "2026-04-11", "2026 war (high-intensity)")]:
    ax[0].axvspan(pd.Timestamp(d0), pd.Timestamp(d1), color=C["orange"], alpha=0.12, lw=0)
    ax[0].text(pd.Timestamp(d0), 128, " " + lab, fontsize=7, color=C["ink2"], va="top")
ax[0].axvline(DATA_END, color=C["blue"], lw=1, ls="--")
ax[0].annotate("27 Jun 2026: conflict data ends;\nI&W matrix = 4 Red -> 'hold buffers'", (DATA_END, 85),
               xytext=(pd.Timestamp("2024-09-01"), 52), fontsize=7, color=C["blue"],
               arrowprops=dict(arrowstyle="-", color=C["blue"], lw=0.6))
ax[0].set_ylabel("Brent, US$/bbl")
ax[0].set_ylim(40, 140)
ax[0].set_title("Brent crude oil (daily)", fontsize=9)
w = cc["2022-01-01":]
ax[1].plot(w.index, w["Hormuz (littoral)"], color=SERIES[0], lw=1, label="Hormuz littoral CCII")
ax[1].plot(w.index, w["Red Sea / Arabian Sea (at sea)"] * 5, color=SERIES[1], lw=1, label="Red Sea at-sea CCII (x5)")
ax[1].set_ylabel("weighted events / wk")
ax[1].legend(loc="upper left")
ax[1].set_title("Chokepoint Conflict Intensity Index (weekly, ACLED)", fontsize=9)
fig.suptitle("Figure  Oil price and chokepoint conflict, 2022-Sep 2026", x=0.01, ha="left", fontsize=11, fontweight="bold")
fig.tight_layout()
save(fig, "f9o_1_brent_timeline")

# ---------------------------------------------------------------- 2. event study
EVENTS = [("7 Oct 2023 (Gaza war)", "2023-10-06"), ("19 Nov 2023 (Red Sea campaign)", "2023-11-17"),
          ("13 Jun 2025 (Israel-Iran strikes)", "2025-06-12"), ("28 Feb 2026 (regional war)", "2026-02-27")]
fig, ax = plt.subplots(figsize=(9, 3.4))
ev_rows = []
for i, (lab, d) in enumerate(EVENTS):
    t0 = brent.index[brent.index.get_indexer([pd.Timestamp(d)], method="pad")[0]]
    k0 = brent.index.get_loc(t0)
    win = brent.iloc[k0 - 5: k0 + 41]
    rel = (win / brent.iloc[k0] - 1) * 100
    ax.plot(np.arange(-5, -5 + len(win)), rel.values, color=SERIES[i], lw=1.6, label=lab)
    ev_rows.append((lab, f"{t0:%d %b %Y}", round(brent.iloc[k0], 1), round(rel.iloc[5 + 5], 1), round(rel.iloc[5 + 20], 1),
                    round(rel.iloc[5:].max(), 1)))
ax.axvline(0, color=C["muted"], lw=0.7, ls=":")
ax.axhline(0, color=C["muted"], lw=0.7)
ax.set_xlabel("Trading days from event (day 0 = last close before the event)")
ax.set_ylabel("Brent change vs day 0 (%)")
ax.legend(fontsize=7.5, loc="upper left")
ax.set_title("Figure  Event study: Brent response to four Middle-East conflict shocks")
save(fig, "f9o_2_event_study")
ev = pd.DataFrame(ev_rows, columns=["Event", "Day 0", "Brent day 0 ($)", "+5 days %", "+20 days %", "Peak within 40 days %"])
table(ev, "t9o_1_event_study")

# ---------------------------------------------------------------- 3. does conflict lead the oil price? (Granger)
wk_b = brent.groupby(brent.index - pd.to_timedelta((brent.index.dayofweek + 2) % 7, "D")).mean()
df = pd.DataFrame({"ret": np.log(wk_b).diff() * 100}).join(np.log1p(cc[["Hormuz (littoral)", "Red Sea / Arabian Sea (at sea)"]]), how="inner").dropna()
df = df[df.index <= DATA_END]
gr = []
for col, lab in [("Hormuz (littoral)", "Hormuz littoral CCII"), ("Red Sea / Arabian Sea (at sea)", "Red Sea at-sea CCII")]:
    res = grangercausalitytests(df[["ret", col]], maxlag=4)
    for lag in (1, 2, 4):
        F, p = res[lag][0]["ssr_ftest"][:2]
        gr.append((f"{lab} -> Brent weekly return", lag, round(F, 2), p))
    # reverse direction as a placebo
    res_r = grangercausalitytests(df[[col, "ret"]], maxlag=2)
    F, p = res_r[2][0]["ssr_ftest"][:2]
    gr.append((f"Brent weekly return -> {lab} (reverse)", 2, round(F, 2), p))
gr = pd.DataFrame(gr, columns=["Direction", "Lags (weeks)", "F", "p-value"])
gr["p-value"] = gr["p-value"].map(lambda p: f"{p:.4f}" if p >= 1e-4 else f"{p:.1e}")
table(gr, "t9o_2_granger")
xc = [(k, df["ret"].corr(df["Hormuz (littoral)"].shift(k))) for k in range(0, 5)]

# ---------------------------------------------------------------- 4. volatility regimes
rv = np.log(brent).diff().rolling(20).std() * np.sqrt(252) * 100
vol_pre = rv["2025-03-01":"2026-02-27"].mean()
vol_war = rv["2026-03-01":"2026-04-30"].mean()

# ---------------------------------------------------------------- 5. rupee pass-through
wk_fx = fx.groupby(fx.index - pd.to_timedelta((fx.index.dayofweek + 2) % 7, "D")).mean()
pt = pd.DataFrame({"b": np.log(wk_b).diff() * 100, "fx": np.log(wk_fx).diff() * 100}).dropna()
pt = pt["2015-01-01":]
lr = stats.linregress(pt.b, pt.fx)
fig, ax = plt.subplots(1, 2, figsize=(9, 3.2), gridspec_kw={"width_ratios": [1.4, 1]})
f_ = fx["2025-01-01":]
ax[0].plot(f_.index, f_.values, color=C["violet"], lw=1.2)
ax[0].axvline(WAR0, color=C["red"], lw=0.8, ls="--")
ax[0].text(WAR0, f_.max() * 0.999, " war", fontsize=7, color=C["red"], va="top")
ax[0].set_ylabel("INR per US$")
ax[0].set_title("Rupee, 2025-Sep 2026 (higher = weaker)", fontsize=9)
ax[1].scatter(pt.b, pt.fx, s=5, color=C["blue"], alpha=0.35, lw=0)
xs = np.linspace(pt.b.min(), pt.b.max(), 10)
ax[1].plot(xs, lr.intercept + lr.slope * xs, color=C["orange"], lw=1.5)
ax[1].set_xlabel("Brent weekly change (%)")
ax[1].set_ylabel("INR/US$ weekly change (%)")
ax[1].set_title(f"Pass-through: beta = {lr.slope:.3f} (p = {lr.pvalue:.0e})", fontsize=9)
fig.suptitle("Figure  The oil shock reaches the rupee", x=0.01, ha="left", fontsize=11, fontweight="bold")
fig.tight_layout()
save(fig, "f9o_3_rupee")

# ---------------------------------------------------------------- 6. India's import dependence (OWID / Energy Institute)
ind = owid[(owid.country == "India") & owid.oil_consumption.notna()].set_index("year")
ind = ind[ind.index >= 1990]
dep = (1 - ind.oil_production / ind.oil_consumption) * 100
fig, ax = plt.subplots(1, 2, figsize=(9, 3.1))
ax[0].fill_between(ind.index, 0, ind.oil_consumption, color=C["orange"], alpha=0.5, lw=0, label="Consumption")
ax[0].fill_between(ind.index, 0, ind.oil_production, color=C["blue"], alpha=0.8, lw=0, label="Domestic production")
ax[0].set_ylabel("TWh (primary energy)")
ax[0].legend(loc="upper left")
ax[0].set_title("India oil consumption vs domestic production", fontsize=9)
ax[1].plot(dep.index, dep.values, color=C["red"], lw=1.8)
ax[1].set_ylim(40, 100)
ax[1].set_ylabel("% of oil consumption imported")
ax[1].set_title(f"Import dependence: {dep.iloc[0]:.0f}% ({dep.index[0]}) -> {dep.iloc[-1]:.0f}% ({dep.index[-1]})", fontsize=9)
fig.suptitle("Figure  India's structural exposure (Energy Institute data via Our World in Data)", x=0.01, ha="left",
             fontsize=11, fontweight="bold")
fig.tight_layout()
save(fig, "f9o_4_india_dependence")
cmp_ = owid[(owid.year == ind.index.max()) & owid.country.isin(["India", "China", "Japan", "South Korea"])].set_index("country")
cmp_dep = (1 - cmp_.oil_production.fillna(0) / cmp_.oil_consumption) * 100

# ---------------------------------------------------------------- 7. the war premium on India's import bill
TWH_PER_BBL = 1.7e-6          # 1 barrel of crude ~ 5.8 MMBtu ~ 1.70 MWh
net_twh = float(ind.oil_consumption.iloc[-1] - ind.oil_production.iloc[-1])
bpd = net_twh / TWH_PER_BBL / 365
base_b = brent["2025-12-01":"2026-02-27"].mean()
war_b = brent["2026-03-01":].mean()
base_fx = fx["2025-12-01":"2026-02-27"].mean()
war_fx = fx["2026-03-01":].mean()
days = (brent.index.max() - pd.Timestamp("2026-03-01")).days + 1
bill_base_usd = base_b * bpd * days / 1e9
bill_war_usd = war_b * bpd * days / 1e9
extra_usd = bill_war_usd - bill_base_usd
extra_inr_cr = (bill_war_usd * war_fx - bill_base_usd * base_fx) * 1e9 / 1e7
per10_usd = 10 * bpd * 365 / 1e9
wp = pd.DataFrame([
    ("India net oil import volume (2024, OWID-derived)", f"{bpd / 1e6:.2f} million bbl/day"),
    ("India oil import dependence (2024)", f"{dep.iloc[-1]:.1f}%"),
    ("Brent, pre-war baseline (1 Dec 2025 - 27 Feb 2026)", f"US$ {base_b:.1f}/bbl"),
    (f"Brent, war period (1 Mar - {brent.index.max():%d %b} 2026)", f"US$ {war_b:.1f}/bbl (+{(war_b / base_b - 1) * 100:.0f}%)"),
    ("INR/US$, pre-war vs war period", f"{base_fx:.2f} -> {war_fx:.2f} ({(war_fx / base_fx - 1) * 100:+.1f}%)"),
    (f"Extra import bill, war period ({days} days), US$", f"~US$ {extra_usd:.0f} billion"),
    ("Extra import bill incl. rupee effect, INR", f"~Rs {extra_inr_cr / 1e5:.1f} lakh crore"),
    ("Sensitivity: every US$10/bbl sustained for a year", f"~US$ {per10_usd:.1f} billion"),
], columns=["Quantity", "Value"])
table(wp, "t9o_3_war_premium")

# ---------------------------------------------------------------- 8. out-of-sample check of the June I&W call
b_cut = brent[:DATA_END].iloc[-1]
b_last = brent.iloc[-1]
b_max_after = brent[DATA_END:].max()
put_metrics(
    brent_prewar=round(float(brent[:WAR0].iloc[-1]), 1), brent_peak_mar=round(float(brent["2026-03-01":"2026-03-31"].max()), 1),
    brent_war_peak=round(float(brent["2026-03-01":].max()), 1), brent_war_peak_date=f"{brent['2026-03-01':].idxmax():%d %b %Y}",
    brent_base=round(float(base_b), 1), brent_war_mean=round(float(war_b), 1), brent_rise_pct=round(float((war_b / base_b - 1) * 100), 0),
    brent_last=round(float(b_last), 1), brent_last_date=f"{brent.index.max():%d %b %Y}", brent_at_cut=round(float(b_cut), 1),
    brent_oos_change=round(float((b_last / b_cut - 1) * 100), 0), brent_oos_max=round(float(b_max_after), 1),
    brent_3wk_rise=round(float((brent["2026-03-20"] / brent[:WAR0].iloc[-1] - 1) * 100), 0),
    vol_pre=round(float(vol_pre), 0), vol_war=round(float(vol_war), 0),
    fx_base=round(float(base_fx), 2), fx_war=round(float(war_fx), 2), fx_last=round(float(fx.iloc[-1]), 2),
    fx_dep_pct=round(float((fx.iloc[-1] / fx[:WAR0].iloc[-1] - 1) * 100), 1),
    passthrough_beta=round(float(lr.slope), 3), passthrough_p=float(lr.pvalue),
    india_dep=round(float(dep.iloc[-1]), 1), india_dep_first=round(float(dep.iloc[0]), 1), india_dep_first_year=int(dep.index[0]),
    india_dep_year=int(dep.index[-1]), india_bpd=round(bpd / 1e6, 2), war_days=days,
    extra_bill_usd_bn=round(float(extra_usd), 0), extra_bill_inr_lakh_cr=round(float(extra_inr_cr / 1e5), 1),
    per10_usd_bn=round(float(per10_usd), 1), dep_china=round(float(cmp_dep.get("China", np.nan)), 0),
    dep_japan=round(float(cmp_dep.get("Japan", np.nan)), 0),
    granger_hz_p1=float(pd.to_numeric(gr["p-value"]).iloc[0]), granger_hz_p2=float(pd.to_numeric(gr["p-value"]).iloc[1]),
    granger_rs_p1=float(pd.to_numeric(gr["p-value"]).iloc[4]), granger_rev_hz=float(pd.to_numeric(gr["p-value"]).iloc[3]),
    xcorr_hz=[round(float(v), 3) for _, v in xc],
    ev_war_20=float(ev.iloc[3]["+20 days %"]), ev_war_peak=float(ev.iloc[3]["Peak within 40 days %"]),
)
print(ev.to_string(), "\n", gr.to_string(), "\n", xc, "\n", wp.to_string(), "\nvol", vol_pre, vol_war, "\nbeta", lr.slope, lr.pvalue,
      "\ndep", dep.tail(3).to_dict(), cmp_dep.round(0).to_dict(), "\nOOS", b_cut, b_last, b_max_after)
