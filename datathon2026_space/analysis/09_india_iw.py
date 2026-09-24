"""Stage 9 - India's position, robustness of the findings, and the ORBITWATCH indicators-and-warnings matrix."""

# =====================================================================================================
# ANNOTATED SOURCE - Stage 9: so what for India (booklet Chapters 9-10)
# -----------------------------------------------------------------------------------------------------
# 1. INDIA SCORECARD - India against China and the USA on every measure computed in Stages 2-8.
# 2. LAUNCH CAPACITY - orbital launches per year from Indian, Chinese and US soil (access to space is the bottleneck).
# 3. ROBUSTNESS - each headline finding re-checked by an independent route (a second source or a second method).
# 4. ORBITWATCH - seven indicators with Amber/Red thresholds and the action to take on Red, so the study becomes a
#    standing monitor rather than a one-off report.
# =====================================================================================================
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import C, CLEAN, TAB, get_metrics, put_metrics, save, table

print("Stage 9: India, robustness, ORBITWATCH")
M = get_metrics()
lc = pd.read_csv(TAB / "t2_launches_by_country.csv").set_index("year")
pop = pd.read_csv(TAB / "t2_population_by_year.csv").set_index("year")

# ---------------------------------------------------------------- 1. India scorecard
sc = pd.DataFrame([
    ("Active satellites, Sep 2026", M["in_now"], M["cn_now"], M["us_now"]),
    ("Active satellites, Jan 2014 (CDM)", M["in_2014"], M["cn_2014"], M["us_2014"]),
    ("Military / state-ISR satellites operational", M["in_isr_ops"], M["cn_isr_ops"], M["us_isr_ops"]),
    ("Orbital launches in 2025", M["launches_2025_in"], M["launches_2025_cn"], M["launches_2025_us"]),
    ("GEO satellites in the 40-110 E arc (2020)", M["geo_arc_in20"], M["geo_arc_cn20"], None),
], columns=["Measure", "India", "China", "USA"])
table(sc, "t9_india_scorecard")

# ---------------------------------------------------------------- 2. launch capacity
l = lc.loc[2010:2026, ["USA", "China", "India"]]
fig, ax = plt.subplots(figsize=(9, 2.9))
for col, colr in zip(["USA", "China", "India"], [C["blue"], C["red"], C["orange"]]):
    ax.plot(l.index, l[col], marker="o", ms=3.5, color=colr, lw=1.8, label=col)
ax.set_ylabel("orbital launches per year")
ax.legend(loc="upper left")
ax.set_title("Access to space: orbital launches per year by launching country (2026 = to 21 Sep)")
save(fig, "f9_1_launch_capacity")
in_avg = float(l.India.loc[2021:2025].mean())
cn_avg = float(l.China.loc[2021:2025].mean())

# ---------------------------------------------------------------- 3. robustness of the headline findings
rob = pd.DataFrame([
    ("Growth of orbit", f"{M['active_mult']:.0f}x active satellites 2014-2026",
     f"UNOOSA registrations track catalogue launches (r = {M['unoosa_corr']:.3f}); UCS 2020 census sits on the same curve", "Confirmed"),
    ("Collision risk", f"index x{M['risk_ratio']:.0f} since 2014", "Same result with 25 km shells and with objects' mean altitude; "
     "the densest shell holds mostly working satellites, the second band mostly debris", "Confirmed (relative index)"),
    ("ISR race", f"China {M['cn_isr_ops']} vs India {M['in_isr_ops']} state ISR/military satellites",
     "Name-based lower bound; excluding commercial imagers the ratio stays above 20:1", "Confirmed (lower bound)"),
    ("Space weather", f"intense-storm odds x{M['storm_mult']:.0f} at high solar activity",
     f"Poisson rate ratio {M['storm_irr50']:.2f} per +50 sunspots (p < 0.001); Spearman rho {M['storm_rho']:.2f}", "Confirmed"),
    ("Solar cycle in debris decay", f"re-entry cycle of {M['reentry_period']:.0f} years",
     "Found blind by periodogram; matches the ~11-year solar cycle (SILSO maxima)", "Confirmed"),
    ("Forecast to 2030", f"~{M['fc_2030_mid'] / 1000:.0f}k payloads (statistical) vs {M['sc_base'] / 1000:.0f}k working (base scenario)",
     f"Back-test error {M['fc_bt_mape']:.1f}% over 2022-2026; two independent routes agree", "Moderate confidence"),
], columns=["Finding", "Result", "Independent check", "Verdict"])
table(rob, "t9_robustness")

# ---------------------------------------------------------------- 4. ORBITWATCH indicators and warnings
yoy = float(pop.Payload.loc[2025] / pop.Payload.loc[2024] - 1)


def rag(v, amber, red, higher_is_worse=True):
    if not higher_is_worse:
        v, amber, red = -v, -amber, -red
    return "RED" if v >= red else ("AMBER" if v >= amber else "GREEN")


iw = pd.DataFrame([
    ("O1 Collision-risk index, LEO (2014 = 1)", "Catalogue, weekly", f"x{M['risk_ratio']:.0f}", "x3", "x5", rag(M["risk_ratio"], 3, 5),
     "Red: conjunction screening for every Indian LEO satellite; manoeuvre fuel budgeted"),
    ("O2 Payloads in orbit, growth per year", "Catalogue, monthly", f"{yoy:.0%}", "10%", "20%", rag(yoy, 0.10, 0.20),
     "Red: file spectrum and orbital-slot claims early; shell planning for SBS-III"),
    ("O3 Chinese state-ISR satellites launched per year (3-yr mean)", "Catalogue, monthly", f"{M['cn_isr_rate_2023_25']:.0f}", "15", "30",
     rag(M["cn_isr_rate_2023_25"], 15, 30), "Red: assume persistent overhead ISR on the northern border; deception and concealment drills"),
    ("O4 India's share of active satellites", "Catalogue, quarterly", f"{M['in_share_now']:.1f}%", "< 3%", "< 1%",
     rag(M["in_share_now"], 3, 1, higher_is_worse=False), "Red: fast-track SBS-III and commercial constellations; buy capacity"),
    ("O5 Intense geomagnetic storm odds per 30 days (sunspot number >= 100, as in 2023-25)", "NOAA / ISRO SSA, daily", f"{M['p_intense_hi']:.0%}", "15%", "30%",
     rag(M["p_intense_hi"], 0.15, 0.30), "Red: storm drill for LEO fleet; hold launch windows; GNSS-degraded mode"),
    ("O6 Anti-satellite tests in the last 5 years", "Open source", "1 (2021)", ">= 1", ">= 2", "AMBER",
     "Red: debris-hazard review of Indian orbits; diplomatic push on a destructive-test moratorium"),
    ("O7 GEO arc over India: satellites 40-110 E", "UCS / ITU, yearly", f"{M['geo_arc20']}", "120", "150", rag(M["geo_arc20"], 120, 150),
     "Red: protect Indian GEO slots and filings at ITU; interference monitoring"),
], columns=["Indicator", "Source / cadence", "Latest value", "Amber at", "Red at", "Status", "Action on Red"])
table(iw, "t9_orbitwatch")

put_metrics(
    in_launch_avg=round(in_avg, 1), cn_launch_avg=round(cn_avg, 1), launch_ratio=round(cn_avg / max(in_avg, 0.1), 0),
    pay_yoy=round(yoy, 3), ow_red=int((iw.Status == "RED").sum()), ow_amber=int((iw.Status == "AMBER").sum()),
)
print(sc, "\n", iw[["Indicator", "Latest value", "Status"]].to_string(), "\nlaunch avg", in_avg, cn_avg)
