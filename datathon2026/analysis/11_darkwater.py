"""Stage 11 - Project DARKWATER evidence: presence vs identity, stasis, pass-level robustness, difference-in-differences,
flag-retention shift, the four signatures and the defence-budget framing.

The Strategic Dark Ratio (SDR) is the share of SOLAS-class hulls (>= 100 m) seen by radar that are not matched to AIS.
"""

# =====================================================================================================
# ANNOTATED SOURCE - Stage 11: Project DARKWATER evidence (report sections 7.8-7.10, 10.4, 11-12)
# -----------------------------------------------------------------------------------------------------
# Strategic Dark Ratio (SDR) = share of big hulls (>= 100 m) seen by radar that are NOT matched to AIS.
# Seven tests that turn 'ships went dark' into a judgement a commander can act on:
#   1. PRESENCE vs IDENTITY  Same sea area at Hormuz imaged on 4 and 12 March: did ships leave (radar count
#   falls)
#                            or go silent (AIS count falls faster than radar count)?
#   2. STASIS INDEX          Were dark hulls held in place? Share of hulls with another detection within 100 m
#   on a
#                            different day, compared with a 'crowding null' (days shuffled) to rule out mere
#                            crowding.
#   3. PASS CHECKS           Remove satellite passes that were 100% dark (possible AIS-feed outage); day vs
#   night.
#   4. DIFFERENCE-IN-DIFFERENCES  Did the Gulf darken faster than 11 control seas over the fortnight?
#                            Significance by 5,000 random label shuffles (permutation test).
#   5. FLAG SHIFT            Which registries kept transmitting in week 2 vs week 1 (chi-square)?
#   6. FOUR SIGNATURES       Rule-based label per sea: concealment, attrition/frozen, evacuation,
#   deterrence/compliance.
#   7. DEFENCE BUDGET        The extra oil bill expressed as a share of India's monthly defence budget.
# =====================================================================================================

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.neighbors import BallTree

from common import C, CLEAN, GULF_CONFLICT, ROOT, SERIES, SHADOW, get_metrics, put_metrics, save, table

print("Stage 11: DARKWATER evidence")
s = pd.read_parquet(CLEAN / "sar_clean.parquet")
a = pd.read_parquet(CLEAN / "acled_clean.parquet")
M = get_metrics()
# Seeded random numbers, so the shuffles and nulls give identical results every run.
RNG = np.random.default_rng(11)
# A satellite 'pass' = acquisition date + orbit number, cut out of the Sentinel-1 scene name.
s["pass"] = s.scene_id.str[17:25] + "_" + s.scene_id.str[49:55]        # acquisition date + absolute orbit
s["day"] = (s.date - s.date.min()).dt.days
L = s[s.large].copy()
GULF = GULF_CONFLICT
# Defence allocation, Union Budget 2026-27 (Rs 7.85 lakh crore; PIB).
DEFENCE_BUDGET_LAKH_CR = 7.85   # Union Budget 2026-27, Ministry of Defence allocation (as cited in the DARKWATER staff paper)

# ---------------------------------------------------------------- 1. presence vs identity on a common footprint
# TEST 1 - PRESENCE vs IDENTITY. Take the Hormuz box on the 4 Mar and 12 Mar passes and keep only the
# OVERLAP of the two footprints, so both days cover exactly the same sea (a like-for-like count).
H = s[s.lat.between(24.5, 27.6) & s.lon.between(54.0, 57.6)]           # Strait of Hormuz and approaches
pa, pb = H[H["pass"].str.startswith("20260304")], H[H["pass"].str.startswith("20260312")]
lo, hi = max(pa.lon.min(), pb.lon.min()), min(pa.lon.max(), pb.lon.max())
la, lb = max(pa.lat.min(), pb.lat.min()), min(pa.lat.max(), pb.lat.max())
rows = []
for lab, d in [("4 Mar 2026", pa), ("12 Mar 2026", pb)]:
    w = d[d.lon.between(lo, hi) & d.lat.between(la, lb)]
    big = w[w.large]
    rows.append((lab, len(big), int((~big.dark).sum()), int(big.dark.sum()), int((~w.large).sum())))
pv = pd.DataFrame(rows, columns=["Pass", "Big hulls seen by radar", "Transmitting AIS", "Dark", "Small craft"])
table(pv, "t11_1_presence_identity")
# Percentage change from the first to the second pass.
chg = lambda c: (pv[c].iloc[1] / pv[c].iloc[0] - 1) * 100
fig, ax = plt.subplots(figsize=(9, 3.2))
x = np.arange(2)
ax.bar(x - 0.2, pv["Big hulls seen by radar"], width=0.38, color=C["blue"], label="Big hulls seen by radar (presence)")
ax.bar(x + 0.2, pv["Transmitting AIS"], width=0.38, color=C["orange"], label="Of which transmitting AIS (identity)")
for i in range(2):
    ax.text(i - 0.2, pv["Big hulls seen by radar"].iloc[i] + 6, f"{pv['Big hulls seen by radar'].iloc[i]}", ha="center", fontsize=9)
    ax.text(i + 0.2, pv["Transmitting AIS"].iloc[i] + 6, f"{pv['Transmitting AIS'].iloc[i]}", ha="center", fontsize=9)
ax.set_xticks(x, pv.Pass)
ax.set_ylabel("Hulls >= 100 m")
ax.legend(loc="upper right")
ax.grid(axis="x", visible=False)
ax.text(1.42, pv["Big hulls seen by radar"].iloc[1] * 0.55,
        f"radar: {chg('Big hulls seen by radar'):+.0f}%\nAIS: {chg('Transmitting AIS'):+.0f}%", fontsize=9, color=C["ink"])
ax.set_xlim(-0.6, 1.9)
ax.set_title("Presence vs identity: Strait of Hormuz, same sea area imaged on two passes")
save(fig, "f11_1_presence_identity")

# ---------------------------------------------------------------- 2. stasis index: did the dark ships stop?
# TEST 2 - STASIS: for each hull, is there another radar detection within 100 m on a DIFFERENT day?
# (BallTree with haversine distance; radius in radians = metres / Earth radius.) A high share = ships held at
# anchor.
def stasis(df, radius_m=100):
    """Share of hulls with another radar detection within radius_m on a *different* day."""
    if len(df) < 5:
        return np.nan
    X = np.radians(df[["lat", "lon"]].values)
    tree = BallTree(X, metric="haversine")
    ind = tree.query_radius(X, r=radius_m / 6_371_000)
    days = df.day.values
    return float(np.mean([np.any(days[j] != days[i]) for i, j in enumerate(ind)]))


# Crowding null: shuffle the day labels among the same positions. Crowded anchorages still score high by chance;
# the z-score says how far the real value is above that chance level (z = 5.3 for Gulf dark hulls).
def stasis_null(df, reps=200, radius_m=100):
    """Crowding null: shuffle day labels across hulls (keeps positions and density, destroys identity over time)."""
    out = []
    d = df.copy()
    for _ in range(reps):
        d["day"] = RNG.permutation(df.day.values)
        out.append(stasis(d, radius_m))
    return float(np.mean(out)), float(np.std(out))


# Run the stasis test for dark and transmitting big hulls in five seas (Table t11_2).
st_rows = []
for lab, sel in [("Hormuz + Persian Gulf", L.region.isin({"Strait of Hormuz", "Persian Gulf"})),
                 ("Strait of Malacca", L.region.eq("Strait of Malacca")), ("NW Europe & North Sea", L.region.eq("NW Europe & North Sea")),
                 ("Mediterranean", L.region.eq("Mediterranean")), ("Black Sea", L.region.eq("Black Sea"))]:
    for pop, pm in [("dark", True), ("transmitting", False)]:
        d = L[sel & (L.dark == pm)]
        obs = stasis(d)
        mu, sd = stasis_null(d, reps=100) if len(d) >= 30 else (np.nan, np.nan)
        z = (obs - mu) / sd if sd and sd > 0 else np.nan
        st_rows.append((lab, pop, len(d), round(obs * 100, 1), round(mu * 100, 1) if mu == mu else None, round(z, 1) if z == z else None))
st = pd.DataFrame(st_rows, columns=["Sea", "Population", "Hulls", "Stasis index %", "Crowding null %", "z vs null"])
table(st, "t11_2_stasis")
g_dark = st[(st.Sea == "Hormuz + Persian Gulf") & (st.Population == "dark")].iloc[0]
g_lit = st[(st.Sea == "Hormuz + Persian Gulf") & (st.Population == "transmitting")].iloc[0]
# Count dark big hulls in the Gulf re-seen within 400 m on another day (a looser 'held' count).
held = L[L.region.isin({"Strait of Hormuz", "Persian Gulf"}) & L.dark]
Xh = np.radians(held[["lat", "lon"]].values)
indh = BallTree(Xh, metric="haversine").query_radius(Xh, r=400 / 6_371_000)
held_n = int(sum(np.any(held.day.values[j] != held.day.values[i]) for i, j in enumerate(indh)))

# ---------------------------------------------------------------- 3. pass-level robustness: all-dark passes, day/night
# TEST 3 - PASS CHECKS. A pass where every one of 20+ detections is dark may be an AIS-feed outage, not
# behaviour:
# remove those passes and re-test. Local solar time splits day from night passes (radar sees both equally).
sc = s.groupby("scene_id").agg(n=("dark", "size"), d=("dark", "mean"))
alldark = sc[(sc.n >= 20) & (sc.d == 1)].index
s["lst"] = (s.ts.dt.hour + s.ts.dt.minute / 60 + s.lon / 15) % 24
s["daylight"] = s.lst.between(6, 18)
L = s[s.large].copy()
WAR = GULF | {"Black Sea"}
rr = lambda d: d[d.region.isin(WAR)].dark.mean() / d[~d.region.isin(WAR)].dark.mean()
rb = pd.DataFrame([
    ("All passes", round(L[L.region.isin(GULF)].dark.mean() * 100, 1), round(L[~L.region.isin(WAR)].dark.mean() * 100, 1), round(rr(L), 2)),
    (f"Excluding {len(alldark)} passes that were 100% dark (possible AIS feed outage)",
     round(L[L.region.isin(GULF) & ~L.scene_id.isin(alldark)].dark.mean() * 100, 1),
     round(L[~L.region.isin(WAR) & ~L.scene_id.isin(alldark)].dark.mean() * 100, 1), round(rr(L[~L.scene_id.isin(alldark)]), 2)),
    ("Daylight passes only", round(L[L.region.isin(GULF) & L.daylight].dark.mean() * 100, 1),
     round(L[~L.region.isin(WAR) & L.daylight].dark.mean() * 100, 1), round(rr(L[L.daylight]), 2)),
    ("Night passes only", round(L[L.region.isin(GULF) & ~L.daylight].dark.mean() * 100, 1),
     round(L[~L.region.isin(WAR) & ~L.daylight].dark.mean() * 100, 1), round(rr(L[~L.daylight]), 2)),
], columns=["Check", "Gulf SDR %", "Peaceful seas SDR %", "War-zone relative risk"])
table(rb, "t11_3_pass_robustness")

# ---------------------------------------------------------------- 4. difference-in-differences (scene level, permutation)
# TEST 4 - DIFFERENCE-IN-DIFFERENCES. Unit = one satellite pass over one sea (at least 5 big hulls).
# Regression: SDR = a + b*day + c*Gulf + d*(day x Gulf), weighted by sqrt(hulls).
# d = how much faster the Gulf darkened per day than the control seas (the 'excess trend').
CONTROLS = ["NW Europe & North Sea", "Mediterranean", "Atlantic (other)", "East Asia Seas", "South China Sea", "Strait of Malacca",
            "Southern Indian Ocean", "Arabian Sea", "Bay of Bengal", "Red Sea", "Pacific & Americas (other)"]
u = L[L.region.isin(GULF | set(CONTROLS))].groupby(["scene_id", "region"]).agg(
    sdr=("dark", "mean"), w=("dark", "size"), day=("day", "first")).reset_index()
u = u[u.w >= 5]
u["treat"] = u.region.isin(GULF).astype(float)


def did(df):
    X = np.c_[np.ones(len(df)), df.day, df.treat, df.day * df.treat]
    W = np.sqrt(df.w.values)
    beta = np.linalg.lstsq(X * W[:, None], df.sdr.values * W, rcond=None)[0]
    return beta


b = did(u)
# Permutation test: shuffle which units are 'Gulf' 5,000 times; p = share of shuffles with an excess trend at
# least as big.
perm = []
for _ in range(5000):
    uu = u.copy()
    uu["treat"] = RNG.permutation(u.treat.values)
    perm.append(did(uu)[3])
p_did = float(np.mean(np.abs(perm) >= abs(b[3])))
did_tab = pd.DataFrame([("Control seas trend", round(b[1] * 100, 2)), ("Gulf excess trend (difference-in-differences)", round(b[3] * 100, 2)),
                        ("Permutation p-value (5,000 label shuffles)", round(p_did, 4)),
                        ("Scene-sea units (treated / control)", f"{int(u.treat.sum())} / {int((1 - u.treat).sum())}")],
                       columns=["Quantity", "Value (percentage points per day)"])
table(did_tab, "t11_4_did")

# ---------------------------------------------------------------- 5. who kept transmitting? flag shift week 1 -> week 2
# TEST 5 - FLAG SHIFT among transmitting big hulls in the Gulf: Gulf-littoral flags, shadow-fleet-associated,
# major open registries, other. Week 1 vs week 2, tested with chi-square.
LIT = ["Iran", "UAE", "Saudi Arabia", "Qatar", "Bahrain", "Kuwait", "Iraq", "Oman"]
OPEN = ["Liberia", "Marshall Islands", "Panama"]
lit = L[L.region.isin(GULF) & ~L.dark & L.flag.notna()].copy()
lit["grp"] = np.select([lit.flag.isin(LIT), lit.flag.isin(SHADOW) | lit.flag.isin(["Comoros", "St Kitts & Nevis"]), lit.flag.isin(OPEN)],
                       ["Gulf-littoral flags", "Shadow-fleet-associated", "Major open registries"], "Other flags")
lit["wk"] = np.where(lit.date < "2026-03-08", "Week 1 (1-7 Mar)", "Week 2 (8-14 Mar)")
ft = pd.crosstab(lit.grp, lit.wk)
chi2, pft, _, _ = stats.chi2_contingency(ft)
fts = (ft / ft.sum() * 100).round(1)
fts["n week 1 / week 2"] = [f"{a_} / {b_}" for a_, b_ in zip(ft.iloc[:, 0], ft.iloc[:, 1])]
table(fts.reset_index().rename(columns={"grp": "Flag group (transmitting big hulls, Gulf)"}), "t11_5_flag_shift")
fig, ax = plt.subplots(figsize=(9, 2.9))
order = ["Gulf-littoral flags", "Major open registries", "Shadow-fleet-associated", "Other flags"]
xx = np.arange(len(order))
ax.bar(xx - 0.2, fts.reindex(order).iloc[:, 0], width=0.38, color=C["blue"], label="Week 1 (1-7 Mar)")
ax.bar(xx + 0.2, fts.reindex(order).iloc[:, 1], width=0.38, color=C["orange"], label="Week 2 (8-14 Mar)")
ax.set_xticks(xx, order)
ax.set_ylabel("% of transmitting big hulls")
ax.legend()
ax.grid(axis="x", visible=False)
ax.set_title(f"Who kept transmitting in the Gulf? Flag mix of the lit fleet (chi-square p = {pft:.3f})")
save(fig, "f11_2_flag_shift")

# ---------------------------------------------------------------- 6. four signatures
# TEST 6 - FOUR SIGNATURES. For each sea: number of big hulls, SDR, SDR trend per day and violent events within
# 300 km.
BOX = {"East Med / Suez approaches": (30.0, 37.0, 28.0, 36.5), "Turkish Straits": (40.0, 41.6, 26.0, 29.6)}
def sdr_region(mask):
    d = L[mask]
    return len(d), d.dark.mean() * 100


# Daily trend of SDR in a sea (weighted straight line through pass-level values).
def trend(mask):
    d = L[mask].groupby("scene_id").agg(sdr=("dark", "mean"), w=("dark", "size"), day=("day", "first"))
    d = d[d.w >= 5]
    if len(d) < 4:
        return np.nan
    return np.polyfit(d.day, d.sdr * 100, 1, w=np.sqrt(d.w))[0]


war = a[(a.WEEK >= "2026-02-28") & (a.WEEK <= "2026-03-07") & a.POLITICAL_VIOLENCE & ~a.MARITIME]
cent = war.groupby(["CENTROID_LATITUDE", "CENTROID_LONGITUDE"]).EVENTS.sum().reset_index()
ctree = BallTree(np.radians(cent[["CENTROID_LATITUDE", "CENTROID_LONGITUDE"]].values), metric="haversine")


# Violent events (war weeks 1-2) within 300 km of the sea's median position.
def conflict_near(mask, r_km=300):
    d = L[mask]
    if len(d) == 0:
        return 0
    idx = ctree.query_radius(np.radians([[d.lat.median(), d.lon.median()]]), r=r_km / 6371)[0]
    return int(cent.EVENTS.values[idx].sum())


seas = {"Strait of Hormuz": L.region.eq("Strait of Hormuz"), "Persian Gulf": L.region.eq("Persian Gulf"),
        "Gulf of Oman": L.region.eq("Gulf of Oman"), "Black Sea": L.region.eq("Black Sea"),
        "Red Sea": L.region.eq("Red Sea"), "Bab-el-Mandeb + Gulf of Aden": L.region.isin({"Bab-el-Mandeb", "Gulf of Aden"}),
        **{k: L.lat.between(v[0], v[1]) & L.lon.between(v[2], v[3]) for k, v in BOX.items()},
        "Strait of Malacca": L.region.eq("Strait of Malacca"), "NW Europe & North Sea": L.region.eq("NW Europe & North Sea")}
base = L[~L.region.isin(WAR)].dark.mean() * 100
sig = []
# Signature rules: SDR > 40% = CONCEALMENT; > 25% = ATTRITION/FROZEN; an at-sea threat with a detour available =
# EVACUATION; heavy fighting nearby but SDR at or below baseline = DETERRENCE/COMPLIANCE; otherwise BASELINE.
for k, m in seas.items():
    n_, sdr_ = sdr_region(m)
    tr, cf = trend(m), conflict_near(m)
    at_sea = k in ("Red Sea", "Bab-el-Mandeb + Gulf of Aden")
    if sdr_ > 40:
        lab = "CONCEALMENT"
    elif sdr_ > 25:
        lab = "ATTRITION / FROZEN"
    elif at_sea:
        lab = "EVACUATION"
    elif cf >= 50 and sdr_ <= base:
        lab = "DETERRENCE / COMPLIANCE"
    else:
        lab = "BASELINE"
    sig.append((k, n_, round(sdr_, 1), round(tr, 1) if tr == tr else None, cf, lab))
sig = pd.DataFrame(sig, columns=["Sea", "Big hulls", "SDR %", "Trend pp/day", "Violent events <=300 km (war wks 1-2)", "Signature"])
table(sig, "t11_6_signatures")

# ---------------------------------------------------------------- 7. the oil premium in defence-budget terms
# TEST 7 - DEFENCE-BUDGET FRAMING: monthly oil premium over February = (month price - Feb price) x barrels/day x
# 30.5,
# for two import-volume bases, divided by one month of the defence budget converted to US$.
brent = pd.read_csv(ROOT / "data/open/brent_daily.csv", parse_dates=["Date"]).set_index("Date").Price
fx = pd.read_csv(ROOT / "data/open/inr_usd_daily.csv", parse_dates=["Date"]).set_index("Date")["Exchange rate"]
feb, mar, apr = brent["2026-02"].mean(), brent["2026-03"].mean(), brent["2026-04"].mean()
fx_mar = fx["2026-03"].mean()
monthly_def_usd = DEFENCE_BUDGET_LAKH_CR * 1e12 / 12 / fx_mar / 1e9
db = []
for vol_lab, bpd in [("Net imports, Energy Institute 2024", M["india_bpd"] * 1e6), ("Crude imports ~5.0 mb/d (MoPNG)", 5.0e6)]:
    for mon, px in [("March 2026", mar), ("April 2026", apr)]:
        prem = (px - feb) * bpd * 30.5 / 1e9
        db.append((vol_lab, mon, round(px - feb, 1), round(prem, 2), round(prem / monthly_def_usd, 2)))
db = pd.DataFrame(db, columns=["Import volume basis", "Month", "Premium over Feb (US$/bbl)", "Extra oil bill (US$ bn/month)",
                               "Share of monthly defence budget"])
table(db, "t11_7_defence_budget")

# Headline numbers for the report.
put_metrics(
    pi_radar_1=int(pv.iloc[0, 1]), pi_radar_2=int(pv.iloc[1, 1]), pi_lit_1=int(pv.iloc[0, 2]), pi_lit_2=int(pv.iloc[1, 2]),
    pi_dark_1=int(pv.iloc[0, 3]), pi_dark_2=int(pv.iloc[1, 3]), pi_radar_chg=round(chg("Big hulls seen by radar")),
    pi_lit_chg=round(chg("Transmitting AIS")), pi_small_chg=round(chg("Small craft")),
    pi_dark_share_2=round(pv.iloc[1, 3] / pv.iloc[1, 1] * 100), pi_dark_share_1=round(pv.iloc[0, 3] / pv.iloc[0, 1] * 100),
    stasis_dark=float(g_dark["Stasis index %"]), stasis_lit=float(g_lit["Stasis index %"]),
    stasis_dark_z=g_dark["z vs null"], stasis_lit_z=g_lit["z vs null"], held_400m=held_n,
    alldark_n=len(alldark), rr_excl_alldark=float(rb.iloc[1, 3]), gulf_sdr_day=float(rb.iloc[2, 1]), gulf_sdr_night=float(rb.iloc[3, 1]),
    world_sdr_day=float(rb.iloc[2, 2]), world_sdr_night=float(rb.iloc[3, 2]),
    did_excess=round(float(b[3] * 100), 2), did_control=round(float(b[1] * 100), 2), did_p=p_did,
    flag_p=float(pft), flag_littoral_1=float(fts.loc["Gulf-littoral flags"].iloc[0]), flag_littoral_2=float(fts.loc["Gulf-littoral flags"].iloc[1]),
    flag_shadow_1=float(fts.loc["Shadow-fleet-associated"].iloc[0]) if "Shadow-fleet-associated" in fts.index else 0.0,
    flag_shadow_2=float(fts.loc["Shadow-fleet-associated"].iloc[1]) if "Shadow-fleet-associated" in fts.index else 0.0,
    flag_open_1=float(fts.loc["Major open registries"].iloc[0]), flag_open_2=float(fts.loc["Major open registries"].iloc[1]),
    sdr_baseline=round(float(base), 1), def_budget_lakh_cr=DEFENCE_BUDGET_LAKH_CR, def_monthly_usd_bn=round(monthly_def_usd, 2),
    def_ratio_mar_lo=float(db.iloc[0, 4]), def_ratio_mar_hi=float(db.iloc[2, 4]), def_ratio_apr_hi=float(db.iloc[3, 4]),
    prem_mar_lo=float(db.iloc[0, 3]), prem_mar_hi=float(db.iloc[2, 3]), brent_feb=round(float(feb), 1), brent_mar=round(float(mar), 1),
    brent_apr=round(float(apr), 1),
)
print(pv, "\n", st, "\n", rb, "\n", did_tab, "\n", fts, pft, "\n", sig, "\n", db, "\nheld", held_n)
