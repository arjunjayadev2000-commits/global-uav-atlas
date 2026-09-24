"""Stage 6 - prescriptive analytics: how many days of stock cover a chokepoint disruption?

Uses the empirical (Kaplan-Meier) distribution of disruption-episode durations from Stage 3.
For a stock level of S days, the expected number of *uncovered* days in a disruption is the
area under the survival curve beyond S:   E[(T - S)+] = integral_S^inf S(t) dt.
"""

# =====================================================================================================
# ANNOTATED SOURCE - Stage 6: how much stock is enough? (report sections 13.5-13.6, Figure 13.2)
# -----------------------------------------------------------------------------------------------------
# QUESTION  If a sea lane is disrupted, how many days of fuel/stock must be held so that we rarely run short?
# IDEA      Stage 3 gave the survival curve S(t): the share of disruptions still going after t days.
#           - Risk of running dry with S days of stock = S(S days)   (share of disruptions that outlast the
#           stock)
#           - Expected shortfall = the area under the survival curve beyond the stock level
#             = the average number of days per disruption that the stock does NOT cover.
#           The 'knee' is the stock level beyond which one more day of stock removes less than 0.25 uncovered
#           days:
#           past this point extra stock buys little, which is where the 35-45-day recommendation comes from.
# INPUT     tables/t6_2_episodes.csv (Stage 3), Hormuz and Red Sea episodes only.
# OUTPUT    Figure f9_1_stock_cover, table t9_1_stock_decision, metrics.
# =====================================================================================================

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from statsmodels.duration.survfunc import SurvfuncRight

from common import C, SERIES, TAB, put_metrics, save, table

print("Stage 6: decision model")
ep = pd.read_csv(TAB / "t6_2_episodes.csv")
ep = ep[ep.chokepoint.isin(["Hormuz (littoral)", "Red Sea / Arabian Sea (at sea)"])]
# Episode lengths converted from weeks to days.
days = ep.weeks * 7


# Kaplan-Meier curve as step points (time, probability), starting at (0, 1).
def km_curve(t, e):
    sf = SurvfuncRight(t, e)
    return np.r_[0, sf.surv_times], np.r_[1, sf.surv_prob]


# Expected uncovered days for stock S: add up the survival probability for every day from S to the horizon.
def exp_shortfall(times, probs, S, tmax):
    """Area under the KM step function from S to tmax (tail beyond last observation held flat to tmax)."""
    grid = np.arange(S, tmax + 1)
    idx = np.searchsorted(times, grid, side="right") - 1
    return probs[idx].sum()


# Horizon: 26 weeks, the longest observed Middle-East at-sea disruption.
T_MAX = 26 * 7        # cap horizon at the longest observed ME at-sea disruption (~6 months)
stock = np.arange(0, 121, 1)
fig, ax = plt.subplots(1, 2, figsize=(9, 3.3))
res = {}
# Compute both curves for every stock level from 0 to 120 days, for all episodes and for Hormuz only.
for i, (name, g) in enumerate([("All Gulf + Red Sea episodes", ep), ("Hormuz only", ep[ep.chokepoint.str.startswith("Hormuz")])]):
    t, p = km_curve(g.weeks * 7, 1 - g.censored)
    es = np.array([exp_shortfall(t, p, S, T_MAX) for S in stock])
    pex = np.array([p[np.searchsorted(t, S, side="right") - 1] for S in stock])
    res[name] = (es, pex)
    ax[0].plot(stock, pex * 100, color=SERIES[i], label=name)
    ax[1].plot(stock, es, color=SERIES[i], label=name)
# Reference lines: SPR (~9.5 days), 30 and 45 days, national cover (~74 days).
for x_, lab in [(9.5, "SPR"), (30, "30 d"), (45, "45 d"), (74, "national\n~74 d")]:
    for a_ in ax:
        a_.axvline(x_, color=C["muted"], ls=":", lw=0.7)
    ax[0].text(x_ + 1, 92, lab, fontsize=6.5, color=C["ink2"], va="top")
ax[0].set_ylabel("% of disruptions outlasting stock")
ax[0].set_xlabel("Stock held (days of consumption)")
ax[0].set_ylim(0, 100)
ax[0].set_title("Risk of running dry", fontsize=9)
ax[1].set_ylabel("Expected uncovered days per disruption")
ax[1].set_xlabel("Stock held (days of consumption)")
ax[1].set_title("Expected shortfall", fontsize=9)
ax[1].legend(fontsize=7)
fig.suptitle("Figure 9.1  Prescriptive stock-cover curve from observed disruption durations", x=0.01, ha="left",
             fontsize=11, fontweight="bold")
fig.tight_layout()
save(fig, "f9_1_stock_cover")

# Table t9_1: the decision table at the stock levels a planner would discuss.
es, pex = res["All Gulf + Red Sea episodes"]
rows = []
for S in [0, 10, 15, 30, 45, 60, 74, 90]:
    rows.append((S, round(pex[S] * 100, 1), round(es[S], 1), round((1 - es[S] / es[0]) * 100, 1)))
dt = pd.DataFrame(rows, columns=["Stock (days)", "P(disruption outlasts stock) %", "Expected uncovered days",
                                 "Shortfall avoided vs zero stock %"])
table(dt, "t9_1_stock_decision")
# knee: smallest stock at which the marginal day of stock removes < 0.25 uncovered days
# Knee = first stock level where one extra day removes less than 0.25 uncovered days.
marg = -np.diff(es)
knee = int(np.argmax(marg < 0.25))
put_metrics(stock_knee_days=knee, stock_p_at_30=float(round(pex[30] * 100, 1)), stock_p_at_45=float(round(pex[45] * 100, 1)),
            stock_p_at_74=float(round(pex[74] * 100, 1)), stock_p_at_10=float(round(pex[10] * 100, 1)),
            stock_es_0=float(round(es[0], 1)), stock_es_30=float(round(es[30], 1)), stock_es_45=float(round(es[45], 1)),
            stock_es_74=float(round(es[74], 1)))
print(dt, "\nknee", knee)
