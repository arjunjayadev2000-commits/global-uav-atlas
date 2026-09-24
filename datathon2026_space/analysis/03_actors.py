"""Stage 3 - who owns orbit: countries, operators, users and purposes, 2014 vs 2020 vs 2026."""

# =====================================================================================================
# ANNOTATED SOURCE - Stage 3: the actors (booklet Chapter 3)
# -----------------------------------------------------------------------------------------------------
# QUESTION  Whose satellites fill the sky, what are they for, and is control of orbit spreading out or concentrating?
# METHOD    - Share of active satellites by country in the three censuses (CDM 2014, UCS 2020, catalogue 2026).
#           - Herfindahl-Hirschman Index (HHI = sum of squared shares, 0-10,000): the standard market-concentration
#             measure. Above 2,500 = 'highly concentrated'. Computed for countries and for constellations/operators.
#           - Users (civil, commercial, government, military) and purposes in the CDM census and UCS 2020.
#           - Ageing: share of 2014 satellites already beyond their design life (a fleet-renewal pressure).
# =====================================================================================================
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import C, CLEAN, SERIES, put_metrics, save, table

print("Stage 3: actors")
cdm = pd.read_parquet(CLEAN / "cdm_satellites.parquet")
u20 = pd.read_parquet(CLEAN / "ucs2020.parquet")
c = pd.read_parquet(CLEAN / "satcat.parquet")
now = c[c.operational & c.OBJECT_TYPE.eq("PAY")].copy()


def hhi(counts):
    s = counts / counts.sum() * 100
    return float((s ** 2).sum())


def norm_country(x):
    x = str(x)
    if x.startswith("USA"):
        return "USA"
    if x.startswith("China"):
        return "China"
    if x.startswith("Russia"):
        return "Russia"
    if x.startswith("India"):
        return "India"
    if x in ("ESA", "Multinational", "International") or "/" in x:
        return "Multinational"
    return x


cdm["C"] = cdm.Country.map(norm_country)
u20["C"] = u20.Country.map(norm_country)
now["C"] = now.owner.replace({"Europe (ESA/EU)": "Multinational", "Intelsat": "Multinational", "Globalstar": "USA", "Orbcomm": "USA"})
FOCUS = ["USA", "China", "Russia", "UK", "Japan", "India", "Multinational"]
share = pd.DataFrame({
    "Jan 2014 (CDM)": cdm.C.value_counts(),
    "Apr 2020 (UCS)": u20.C.value_counts(),
    "Sep 2026 (catalogue)": now.C.value_counts(),
}).fillna(0)
share_pct = share / share.sum() * 100
tab = share.loc[FOCUS].astype(int).assign(**{f"{k} %": share_pct.loc[FOCUS, k].round(1) for k in share.columns})
tab.loc["All others"] = (share.sum() - share.loc[FOCUS].sum()).tolist() + (100 - share_pct.loc[FOCUS].sum()).round(1).tolist()
table(tab.reset_index(names="Country"), "t3_country_share")

fig, ax = plt.subplots(1, 2, figsize=(9, 3.4), gridspec_kw={"width_ratios": [1.25, 1]})
x = np.arange(len(FOCUS))
for i, col in enumerate(share.columns):
    ax[0].bar(x + (i - 1) * 0.27, share_pct.loc[FOCUS, col], width=0.26, color=[C["blue"], C["aqua"], C["orange"]][i], label=col)
ax[0].set_xticks(x, FOCUS, fontsize=7.5, rotation=20)
ax[0].set_ylabel("% of active satellites")
ax[0].legend(fontsize=7)
ax[0].grid(axis="x", visible=False)
ax[0].set_title("Share of active satellites by country", fontsize=9)
cons = now.constellation.value_counts()
op_share = pd.concat([cons.drop("Other").head(6), pd.Series({"All other satellites": cons.get("Other", 0)})])
ax[1].barh(op_share.index[::-1], op_share.values[::-1], color=[C["muted"]] + [C["blue"]] * 5 + [C["red"]], height=0.6)
for i, v in enumerate(op_share.values[::-1]):
    ax[1].text(v + 150, i, f"{v:,}", va="center", fontsize=7)
ax[1].set_title("Active satellites by constellation, Sep 2026", fontsize=9)
ax[1].grid(axis="y", visible=False)
ax[1].tick_params(axis="y", labelsize=7.5)
fig.suptitle("Orbit is concentrating: one country, and one company, now hold most active satellites", x=0.01, ha="left",
             fontsize=11, fontweight="bold")
fig.tight_layout()
save(fig, "f3_1_actors")

# ---------------------------------------------------------------- users and purposes
def users_group(x):
    x = str(x)
    if "Military" in x:
        return "Military (incl. dual-use)"
    if x.startswith("Commercial"):
        return "Commercial"
    if x.startswith("Government"):
        return "Government"
    if x.startswith("Civil"):
        return "Civil"
    return "Other"


ug = pd.DataFrame({"Jan 2014 (CDM)": cdm.Users.map(users_group).value_counts(normalize=True) * 100,
                   "Apr 2020 (UCS)": u20.Users.map(users_group).value_counts(normalize=True) * 100}).fillna(0).round(1)
pg = pd.DataFrame({"Jan 2014 (CDM)": cdm.purpose_group.value_counts(normalize=True) * 100,
                   "Apr 2020 (UCS)": u20.purpose_group.value_counts(normalize=True) * 100}).fillna(0).round(1)
table(ug.reset_index(names="Users"), "t3_users")
table(pg.reset_index(names="Purpose"), "t3_purpose")
mil_by = pd.DataFrame({"Military share 2014 %": cdm.groupby("C").military_any.mean() * 100,
                       "Satellites 2014": cdm.C.value_counts(),
                       "Military share 2020 %": u20.groupby("C").military_any.mean() * 100,
                       "Satellites 2020": u20.C.value_counts()}).loc[["USA", "China", "Russia", "India", "Japan", "UK", "France", "Israel"]].round(1)
table(mil_by.reset_index(names="Country"), "t3_military_share")
fig, ax = plt.subplots(1, 2, figsize=(9, 3.1))
for k, (d, ttl) in enumerate([(pg, "Purpose"), (mil_by[["Military share 2014 %", "Military share 2020 %"]], "Military / dual-use share by country (%)")]):
    d.plot.barh(ax=ax[k], color=[C["blue"], C["aqua"]], width=0.7, legend=(k == 0))
    ax[k].set_title(ttl, fontsize=9)
    ax[k].grid(axis="y", visible=False)
    ax[k].tick_params(axis="y", labelsize=7.5)
    ax[k].invert_yaxis()
    ax[k].set_ylabel('')
ax[0].set_xlabel("% of active satellites")
ax[0].legend(fontsize=7)
fig.suptitle("What satellites are for, and how military they are", x=0.01, ha="left", fontsize=11, fontweight="bold")
fig.tight_layout()
save(fig, "f3_2_users_purpose")

# ---------------------------------------------------------------- ageing of the 2014 fleet
known = cdm[cdm.Anticipated_Lifetime.notna()]
beyond = known.beyond_design_life.mean()
beyond_geo = known[known.Class_of_Orbit.eq("GEO")].beyond_design_life.mean()
put_metrics(
    hhi_country_2014=round(hhi(share["Jan 2014 (CDM)"]), 0), hhi_country_2020=round(hhi(share["Apr 2020 (UCS)"]), 0),
    hhi_country_now=round(hhi(share["Sep 2026 (catalogue)"]), 0),
    hhi_constellation_now=round(hhi(now.constellation.where(now.constellation.ne("Other"), now.OBJECT_NAME)
                                    .value_counts()), 0),
    us_share_2014=round(float(share_pct.loc["USA", "Jan 2014 (CDM)"]), 1), us_share_now=round(float(share_pct.loc["USA", "Sep 2026 (catalogue)"]), 1),
    cn_share_2014=round(float(share_pct.loc["China", "Jan 2014 (CDM)"]), 1), cn_share_now=round(float(share_pct.loc["China", "Sep 2026 (catalogue)"]), 1),
    in_share_2014=round(float(share_pct.loc["India", "Jan 2014 (CDM)"]), 1), in_share_now=round(float(share_pct.loc["India", "Sep 2026 (catalogue)"]), 2),
    cn_now=int(share.loc["China", "Sep 2026 (catalogue)"]), in_now=int(share.loc["India", "Sep 2026 (catalogue)"]),
    us_now=int(share.loc["USA", "Sep 2026 (catalogue)"]), ru_now=int(share.loc["Russia", "Sep 2026 (catalogue)"]),
    cn_2014=int(share.loc["China", "Jan 2014 (CDM)"]), us_2014=int(share.loc["USA", "Jan 2014 (CDM)"]), in_2014=int(share.loc["India", "Jan 2014 (CDM)"]),
    mil_share_2014=round(float(ug.loc["Military (incl. dual-use)", "Jan 2014 (CDM)"]), 1),
    mil_share_2020=round(float(ug.loc["Military (incl. dual-use)", "Apr 2020 (UCS)"]), 1),
    comm_share_2014=round(float(ug.loc["Commercial", "Jan 2014 (CDM)"]), 1), comm_share_2020=round(float(ug.loc["Commercial", "Apr 2020 (UCS)"]), 1),
    beyond_life=round(float(beyond), 3), beyond_life_geo=round(float(beyond_geo), 3),
    mil_cn_2014=round(float(mil_by.loc["China", "Military share 2014 %"]), 0), mil_ru_2014=round(float(mil_by.loc["Russia", "Military share 2014 %"]), 0),
    mil_in_2014=round(float(mil_by.loc["India", "Military share 2014 %"]), 0), mil_us_2014=round(float(mil_by.loc["USA", "Military share 2014 %"]), 0),
)
print(tab, "\n", ug, "\n", pg, "\n", mil_by, "\nbeyond", beyond, beyond_geo)
