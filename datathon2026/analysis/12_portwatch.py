"""Stage 12 - movement layer from IMF PortWatch daily chokepoint transits (AIS-based), 2019 - 16 Aug 2026.

Source: IMF PortWatch 'Daily Chokepoint Transit Calls' (portwatch.imf.org), raw extract retrieved via an MIT-licensed public
mirror (github.com/ebiisharifi/hormuz-chokepoint-analytics, data/raw). Only the raw IMF series is used here.

Adds the third layer to the study: presence (SAR radar), identity (AIS match) and now movement (transits); measures how long
shipping disruptions last at chokepoints (as opposed to conflict flare-ups), and how import diversification stretches stock cover.
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from statsmodels.duration.survfunc import SurvfuncRight

from common import C, ROOT, SERIES, TAB, get_metrics, put_metrics, save, table

print("Stage 12: IMF PortWatch movement layer")
M = get_metrics()
pw = pd.read_csv(ROOT / "data/open/imf_portwatch_chokepoints_daily.csv", parse_dates=["date"])
END = pw.date.max()
WAR0 = pd.Timestamp("2026-02-28")
H = pw[pw.portname == "Strait of Hormuz"].set_index("date").sort_index()

# ---------------------------------------------------------------- 1. Hormuz daily transits and the SAR window
base = H.loc["2025-01-01":"2026-02-27", "n_total"].mean()
base_t = H.loc["2025-01-01":"2026-02-27", "n_tanker"].mean()
post = H.loc["2026-03-01":, "n_total"].mean()
post_t = H.loc["2026-03-01":, "n_tanker"].mean()
sar_win = H.loc["2026-03-01":"2026-03-14", "n_total"].mean()
last30 = H.loc[END - pd.Timedelta(days=29):, "n_total"].mean()
fig, ax = plt.subplots(figsize=(9, 3.3))
h = H.loc["2025-09-01":]
ax.bar(h.index, h.n_total, color=C["blue"], width=1.0, alpha=0.35, label="Daily transits (AIS)")
ax.plot(h.index, h.n_total.rolling(7, min_periods=1).mean(), color=C["blue"], lw=1.6, label="7-day mean")
ax.axhline(base, color=C["muted"], ls="--", lw=0.8)
ax.text(h.index[0], base + 3, f"2025 baseline {base:.0f}/day", fontsize=7, color=C["ink2"])
ax.axvspan(pd.Timestamp("2026-03-01"), pd.Timestamp("2026-03-14"), color=C["orange"], alpha=0.18, lw=0)
ax.text(pd.Timestamp("2026-03-02"), base * 1.15, "SAR window\n1-14 Mar", fontsize=7, color=C["orange"])
ax.axvline(pd.Timestamp("2026-03-23"), color=C["green"], lw=0.8, ls=":")
ax.text(pd.Timestamp("2026-03-25"), base * 0.8, "Op Urja Suraksha\nbegins 23 Mar", fontsize=7, color=C["green"])
ax.annotate("late June: partial reopening,\nBrent back to $70; then re-closed", (pd.Timestamp("2026-06-26"), 28),
            xytext=(pd.Timestamp("2026-04-20"), 45), fontsize=7, color=C["ink2"], arrowprops=dict(arrowstyle="-", color=C["muted"], lw=0.6))
ax.set_ylabel("vessels / day")
ax.legend(loc="upper right")
ax.set_title("Strait of Hormuz: daily transits (IMF PortWatch), Sep 2025 - Aug 2026")
save(fig, "f12_1_hormuz_transits")

# ---------------------------------------------------------------- 2. is it Hormuz? all chokepoints, change since the war
ch = []
for p, g in pw.groupby("portname"):
    g = g.set_index("date").n_total
    b = g["2025-03-01":"2025-08-16"].mean()        # same calendar window a year earlier
    a_ = g["2026-03-01":"2026-08-16"].mean()
    if b >= 5:
        ch.append((p, round(b, 1), round(a_, 1), round((a_ / b - 1) * 100, 1)))
ch = pd.DataFrame(ch, columns=["Chokepoint", "Mar-Aug 2025 (per day)", "Mar-Aug 2026 (per day)", "Change %"]).sort_values("Change %")
table(ch, "t12_1_chokepoint_change")
CONTROLS = ["Malacca Strait", "Panama Canal", "Taiwan Strait", "Korea Strait", "Bosporus Strait", "Dover Strait", "Gibraltar Strait"]
ctrl = ch[ch.Chokepoint.isin(CONTROLS)]["Change %"].mean()
fig, ax = plt.subplots(figsize=(9, 4.4))
cols = [C["red"] if p == "Strait of Hormuz" else (C["orange"] if p in ("Bab el-Mandeb Strait", "Suez Canal") else
        (C["green"] if p == "Cape of Good Hope" else C["blue"])) for p in ch.Chokepoint]
ax.barh(ch.Chokepoint, ch["Change %"], color=cols, height=0.65)
ax.axvline(0, color=C["ink2"], lw=0.6)
for i, v in enumerate(ch["Change %"]):
    ax.text(v + (2 if v >= 0 else -2), i, f"{v:+.0f}%", va="center", ha="left" if v >= 0 else "right", fontsize=6.5, color=C["ink2"])
ax.set_xlabel("Change in daily transits, Mar-Aug 2026 vs Mar-Aug 2025 (%)")
ax.grid(axis="y", visible=False)
ax.tick_params(axis="y", labelsize=7)
ax.set_title("Only Hormuz stopped: change in transits at 28 world chokepoints since the war")
save(fig, "f12_2_chokepoints")

# ---------------------------------------------------------------- 3. the evacuation signature: Red Sea vs Cape
q = pw[pw.portname.isin(["Bab el-Mandeb Strait", "Suez Canal", "Cape of Good Hope"])].pivot_table(
    index=pd.Grouper(key="date", freq="W"), columns="portname", values="n_total", aggfunc="mean")
q = q["2023-01-01":]
fig, ax = plt.subplots(figsize=(9, 3))
for c_, col in zip(["Bab el-Mandeb Strait", "Suez Canal", "Cape of Good Hope"], [C["orange"], C["violet"], C["green"]]):
    ax.plot(q.index, q[c_].rolling(4, min_periods=1).mean(), color=col, lw=1.6, label=c_)
ax.axvline(pd.Timestamp("2023-11-19"), color=C["muted"], ls=":", lw=0.8)
ax.text(pd.Timestamp("2023-11-26"), q.max().max() * 0.95, "Red Sea campaign\nbegins", fontsize=7, color=C["ink2"], va="top")
ax.set_ylabel("vessels / day (4-wk mean)")
ax.legend(loc="center right", ncol=1)
ax.set_title("Evacuation in data: the Red Sea emptied and the Cape filled, and it has not reversed")
save(fig, "f12_3_evacuation")
bm_pre = pw[(pw.portname == "Bab el-Mandeb Strait")].set_index("date").n_total["2023-01-01":"2023-10-31"].mean()
bm_post = pw[(pw.portname == "Bab el-Mandeb Strait")].set_index("date").n_total["2024-01-01":].mean()
cg_pre = pw[(pw.portname == "Cape of Good Hope")].set_index("date").n_total["2023-01-01":"2023-10-31"].mean()
cg_post = pw[(pw.portname == "Cape of Good Hope")].set_index("date").n_total["2024-01-01":].mean()

# ---------------------------------------------------------------- 4. how long do SHIPPING disruptions last?
# A disruption starts when the 7-day mean falls below 50% of the chokepoint's median over the prior year. That reference is
# FROZEN for the life of the episode (a rolling baseline would quietly re-define a long disruption as 'normal'), and the episode
# ends only after 14 consecutive days back above the 50% line, so a brief partial reopening does not end the crisis.
eps = []
for p, g in pw.groupby("portname"):
    s = g.set_index("date").n_total.asfreq("D").fillna(0)
    m7 = s.rolling(7).mean().values
    ref_roll = s.rolling(365, min_periods=180).median().shift(7).values
    if np.nanmedian(ref_roll) < 10:
        continue                                      # too thin to define a disruption
    idx = s.index
    in_ep, ref, start, last_low, above = False, None, None, None, 0
    for i in range(len(s)):
        if np.isnan(m7[i]):
            continue
        if not in_ep:
            if not np.isnan(ref_roll[i]) and m7[i] < 0.5 * ref_roll[i]:
                in_ep, ref, start, last_low, above = True, ref_roll[i], i, i, 0
        else:
            if m7[i] < 0.5 * ref:
                last_low, above = i, 0
            else:
                above += 1
                if above >= 14:
                    if last_low - start + 1 >= 7:
                        eps.append((p, idx[start].date(), idx[last_low].date(), last_low - start + 1, 0, round(ref, 1)))
                    in_ep = False
    if in_ep and last_low - start + 1 >= 7:
        eps.append((p, idx[start].date(), idx[-1].date(), len(s) - start, 1, round(ref, 1)))
eps = pd.DataFrame(eps, columns=["Chokepoint", "Start", "End", "Days", "Ongoing at 16 Aug 2026", "Pre-disruption transits/day"])
eps = eps[eps["Pre-disruption transits/day"] >= 10]          # ignore disruptions of very thin traffic
table(eps.sort_values("Days", ascending=False), "t12_2_shipping_disruptions")
sf_ship = SurvfuncRight(eps.Days, 1 - eps["Ongoing at 16 Aug 2026"])
ep_c = pd.read_csv(TAB / "t6_2_episodes.csv")
ep_c = ep_c[ep_c.chokepoint.isin(["Hormuz (littoral)", "Red Sea / Arabian Sea (at sea)"])]
sf_conf = SurvfuncRight(ep_c.weeks * 7, 1 - ep_c.censored)
fig, ax = plt.subplots(figsize=(9, 3.3))
ax.step(np.r_[1, sf_conf.surv_times], np.r_[1, sf_conf.surv_prob], where="post", color=C["orange"], lw=1.8,
        label=f"Conflict flare-ups near chokepoints (ACLED, n={len(ep_c)})")
ax.step(np.r_[1, sf_ship.surv_times], np.r_[1, sf_ship.surv_prob], where="post", color=C["blue"], lw=1.8,
        label=f"Shipping disruptions at chokepoints (PortWatch, n={len(eps)})")
for x_, lab in [(9.5, "SPR"), (74, "national cover 74 d")]:
    ax.axvline(x_, color=C["red"], lw=0.7, ls=":")
    ax.text(x_ + 4, 0.93, lab, fontsize=7, color=C["red"])
ax.set_xscale("log")
ax.set_xlim(1, 900)
ax.set_xticks([1, 7, 14, 30, 74, 180, 365, 700], ["1", "7", "14", "30", "74", "180", "365", "700"])
ax.set_xlabel("Duration (days, log scale)")
ax.set_ylabel("P(still ongoing)")
ax.set_ylim(0, 1.03)
ax.legend(loc="lower left")
ax.set_title("Fighting flares for weeks; the shipping disruption it causes lasts months")
save(fig, "f12_4_duration")

# ---------------------------------------------------------------- 5. diversification stretches stock cover
exp = np.array([0.20, 0.30, 0.45, 0.60])
stocks = {"SPR only (9.5 d)": 9.5, "National cover (74 d)": 74, "Parliamentary target (90 d)": 90}
cov = pd.DataFrame({k: (v / exp).round(0) for k, v in stocks.items()}, index=[f"{int(e * 100)}% of crude via the chokepoint" for e in exp])
table(cov.reset_index(names="Exposure"), "t12_3_effective_cover")
closure_days = (END - pd.Timestamp("2026-03-01")).days + 1
fig, ax = plt.subplots(figsize=(9, 3))
xx = np.linspace(0.15, 0.7, 50)
for (k, v), col in zip(stocks.items(), [C["orange"], C["blue"], C["green"]]):
    ax.plot(xx * 100, v / xx, color=col, lw=1.8, label=k)
ax.axhline(closure_days, color=C["red"], ls="--", lw=0.8)
ax.text(16, closure_days * 1.06, f"Hormuz closure to date: {closure_days}+ days", fontsize=7, color=C["red"])
for e, lab in [(45, "India pre-war\n(~45%)"), (30, "India after rerouting\n(~30%)")]:
    ax.axvline(e, color=C["muted"], ls=":", lw=0.7)
    ax.text(e + 0.5, 520, lab, fontsize=6.5, color=C["ink2"])
ax.set_ylim(0, 650)
ax.set_xlabel("Share of crude supply that passes the closed chokepoint (%)")
ax.set_ylabel("Days the stock can replace the lost share")
ax.legend(loc="upper right", fontsize=7)
ax.set_title("Diversification multiplies stock cover: effective cover = stock days / share exposed")
save(fig, "f12_5_effective_cover")

put_metrics(
    pw_end=f"{END:%d %b %Y}", pw_base=round(float(base), 1), pw_post=round(float(post), 1), pw_drop=round(float((1 - post / base) * 100), 1),
    pw_tank_base=round(float(base_t), 1), pw_tank_post=round(float(post_t), 1), pw_tank_drop=round(float((1 - post_t / base_t) * 100), 1),
    pw_sar_win=round(float(sar_win), 1), pw_sar_win_drop=round(float((1 - sar_win / base) * 100), 1),
    pw_last30_pct=round(float(last30 / base * 100), 1), pw_zero_4mar=int(H.loc["2026-03-04", "n_total"]),
    pw_ctrl_change=round(float(ctrl), 1), pw_hormuz_change=float(ch.set_index("Chokepoint").loc["Strait of Hormuz", "Change %"]),
    pw_cape_change=float(ch.set_index("Chokepoint").loc["Cape of Good Hope", "Change %"]),
    bm_drop=round(float((1 - bm_post / bm_pre) * 100), 0), cape_rise=round(float((cg_post / cg_pre - 1) * 100), 0),
    ship_ep_n=len(eps), ship_ep_median=float(eps.Days.median()), ship_ep_max=int(eps.Days.max()),
    ship_p_gt_74=round(float(sf_ship.surv_prob[np.searchsorted(sf_ship.surv_times, 74, side="right") - 1]), 3),
    ship_ongoing=int(eps["Ongoing at 16 Aug 2026"].sum()), closure_days=int(closure_days),
    cover_74_at30=int(74 / 0.30), cover_74_at45=int(74 / 0.45), cover_spr_at30=int(9.5 / 0.30),
)
print(ch.head(6).to_string(), "\n", ch.tail(4).to_string(), "\nctrl", ctrl, "\n", eps.sort_values("Days", ascending=False).head(12).to_string(),
      "\n", cov, "\nsar win", sar_win, base, "bm", bm_pre, bm_post, "cape", cg_pre, cg_post)
