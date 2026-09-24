"""Stage 5 - the contest: military and dual-use satellites, the ISR race and India's position."""

# =====================================================================================================
# ANNOTATED SOURCE - Stage 5: contested space (booklet Chapter 5)
# -----------------------------------------------------------------------------------------------------
# QUESTION  How fast are the major powers building military and intelligence (ISR) capacity in orbit, and where
#           does India stand?
# METHOD    1. CDM 2014 census: military / dual-use satellites by country and mission.
#           2. Catalogue (to Sep 2026): satellites are grouped into programme FAMILIES by their official names
#              (e.g. YAOGAN = Chinese military reconnaissance; USA-nnn = US national-security payloads; COSMOS = Russian
#              military; RISAT/CARTOSAT/EOS/EMISAT/GSAT-7 = Indian ISR and military communications). Name-based
#              grouping is transparent and repeatable but is a LOWER BOUND: covert or commercially-flagged military
#              satellites are missed.
#           3. Launches per year of each family (the build rate) and operational satellites today (the stock).
#           4. India's gap in ISR satellites, and what SBS-III (52 satellites by 2029) closes.
# =====================================================================================================
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import C, CLEAN, SERIES, put_metrics, save, table

print("Stage 5: contest")
c = pd.read_parquet(CLEAN / "satcat.parquet")
cdm = pd.read_parquet(CLEAN / "cdm_satellites.parquet")
p = c[c.OBJECT_TYPE.eq("PAY")].copy()
n = p.OBJECT_NAME.str.upper()

FAM = {  # family -> (country, rule on the name), military-designated or government/dual-use ISR
    "China: Yaogan military reconnaissance": ("China", n.str.startswith("YAOGAN")),
    "China: other state ISR & tech (Gaofen, TJS, Shiyan, Shijian, Tianhui, Yunhai)": (
        "China", n.str.match(r"^(GAOFEN|TJS|SHIYAN|SHIJIAN|SJ-|TIANHUI|YUNHAI|HJS)")),
    "China: commercial imagers (Jilin-1, Superview)": ("China", n.str.match(r"^(JILIN|SUPERVIEW)")),
    "USA: national-security payloads (USA-nnn)": ("USA", n.str.startswith("USA ")),
    "USA: commercial imagers (Planet, Maxar, BlackSky, Capella)": ("USA", n.str.match(r"^(FLOCK|SKYSAT|WORLDVIEW|LEGION|BLACKSKY|CAPELLA)")),
    "Russia: military (Cosmos)": ("Russia", n.str.startswith("COSMOS") & p.OWNER.eq("CIS")),
    "India: ISR & military (RISAT, Cartosat, EOS, EMISAT, GSAT-7)": ("India", n.str.match(r"^(RISAT|CARTOSAT|EOS-|EMISAT|GSAT-7)") & p.OWNER.eq("IND")),
}
p["family"] = "Other"
for fam, (_, rule) in FAM.items():
    p.loc[rule & p.family.eq("Other"), "family"] = fam
fams = list(FAM)
ops = p[p.operational].family.value_counts().reindex(fams, fill_value=0)
since = p[p.launch.dt.year >= 2014].family.value_counts().reindex(fams, fill_value=0)
tab = pd.DataFrame({"Country": [FAM[f][0] for f in fams], "Programme family": fams, "Operational Sep 2026": ops.values,
                    "Launched since 2014": since.values})
table(tab, "t5_isr_families")

yr = p[p.family.ne("Other")].groupby([p.launch.dt.year, "family"]).size().unstack(fill_value=0).reindex(range(2000, 2027), fill_value=0)
cn_isr = yr[[f for f in fams if f.startswith("China") and "commercial" not in f]].sum(axis=1)
us_isr = yr["USA: national-security payloads (USA-nnn)"]
ru_isr = yr["Russia: military (Cosmos)"]
in_isr = yr["India: ISR & military (RISAT, Cartosat, EOS, EMISAT, GSAT-7)"]
fig, ax = plt.subplots(1, 2, figsize=(9, 3.3), gridspec_kw={"width_ratios": [1.15, 1]})
for s_, lab, col in [(cn_isr, "China (state ISR)", C["red"]), (us_isr, "USA (national security)", C["blue"]),
                     (ru_isr, "Russia (Cosmos)", C["muted"]), (in_isr, "India (ISR & military)", C["orange"])]:
    ax[0].plot(s_.index, s_.cumsum(), color=col, lw=2, label=lab)
ax[0].set_title("Cumulative military / state-ISR satellites launched since 2000", fontsize=9)
ax[0].legend(fontsize=7, loc="upper left")
agg = pd.Series({"China": ops[[f for f in fams if f.startswith("China")]].sum(), "USA": ops[[f for f in fams if f.startswith("USA")]].sum(),
                 "Russia": ops[[f for f in fams if f.startswith("Russia")]].sum(), "India": ops[[f for f in fams if f.startswith("India")]].sum(),
                 "India + SBS-III (2029)": ops[[f for f in fams if f.startswith("India")]].sum() + 52})
ax[1].barh(agg.index[::-1], agg.values[::-1], color=[C["aqua"], C["orange"], C["muted"], C["blue"], C["red"]], height=0.6)
for i, v in enumerate(agg.values[::-1]):
    ax[1].text(v + 8, i, f"{v:,}", va="center", fontsize=8)
ax[1].set_title("Operational ISR / military & imaging satellites, Sep 2026", fontsize=9)
ax[1].grid(axis="y", visible=False)
fig.suptitle("The ISR race in orbit: China and the USA build by the hundred; India by the handful", x=0.01, ha="left",
             fontsize=11, fontweight="bold")
fig.tight_layout()
save(fig, "f5_1_isr_race")

# 2014 census: military satellites by country and mission
m14 = cdm[cdm.military_any].groupby(["Country", "Purpose"]).size().rename("n").reset_index()
m14 = m14[m14.Country.isin(["USA", "China", "Russia", "India", "France", "Israel", "UK"])]
m14p = m14.pivot_table(index="Country", columns="Purpose", values="n", aggfunc="sum", fill_value=0)
table(m14p.reset_index(), "t5_military_2014")

put_metrics(
    cn_isr_ops=int(agg["China"]), us_isr_ops=int(agg["USA"]), ru_isr_ops=int(agg["Russia"]), in_isr_ops=int(agg["India"]),
    yaogan_ops=int(ops["China: Yaogan military reconnaissance"]), usa_nnn_ops=int(ops["USA: national-security payloads (USA-nnn)"]),
    cn_isr_launched_since2014=int(since[[f for f in fams if f.startswith("China") and "commercial" not in f]].sum()),
    in_isr_launched_since2014=int(since["India: ISR & military (RISAT, Cartosat, EOS, EMISAT, GSAT-7)"]),
    cn_isr_rate_2023_25=round(float(cn_isr.loc[2023:2025].mean()), 1), in_isr_rate_2023_25=round(float(in_isr.loc[2023:2025].mean()), 1),
    us_nnn_2024_26=int(us_isr.loc[2024:2026].sum()), cn_in_ratio=round(float(agg["China"] / max(agg["India"], 1)), 1),
    sbs3_close=round(float(52 / (agg["China"] - agg["India"])), 3),
)
print(tab.to_string(), "\n", agg, "\n", m14p)
