"""Write deck/deck_data.json (numbers and series for the PowerPoint) from data/metrics.json, tables/*.csv and the clean catalogue."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
M = json.loads((ROOT / "data/metrics.json").read_text())
T = lambda n: pd.read_csv(ROOT / "tables" / f"{n}.csv")
pop = T("t2_population_by_year").set_index("year")
c = pd.read_parquet(ROOT / "data/clean/satcat.parquet")
p = c[c.OBJECT_TYPE.eq("PAY")]
pay = p.groupby(p.launch.dt.year).size().reindex(range(2010, 2027), fill_value=0)
sl = p[p.constellation.eq("Starlink (US)")].groupby(p.launch.dt.year).size().reindex(range(2010, 2027), fill_value=0)
sh = T("t4_leo_shells")
sh["lo"] = sh["Shell (km)"].str.split("-").str[0].astype(int)
sh = sh[sh.lo.between(200, 1475)]
cs = T("t3_country_share").set_index("Country")
tr, rk, rr = T("t8_trend_forecast"), T("t8_risk_index"), T("t6_reentry_rate")
# intense storms per 30 days by sunspot band (same logic as analysis/06_spaceweather.py)
dst, ss = pd.read_parquet(ROOT / "data/clean/dst.parquet"), pd.read_parquet(ROOT / "data/clean/sunspots.parquet")
rows = []
for per, d in dst.groupby("period"):
    d = d.sort_values("hours").reset_index(drop=True)
    sp = ss[ss.period.eq(per)].sort_values("days")
    d["ssn"] = np.interp(d.hours / 24, sp.days, sp.smoothed_ssn)
    below = d.dst <= -50
    run = (below != below.shift()).cumsum()
    ev = d[below].groupby(run[below]).agg(start=("hours", "first"), mn=("dst", "min"))
    d["block"] = (d.hours // 720).astype(int)
    for b, g in d.groupby("block"):
        if len(g) < 600:
            continue
        e = ev[(ev.start >= g.hours.min()) & (ev.start <= g.hours.max())]
        rows.append((g.ssn.mean(), int((e.mn <= -100).sum())))
b = pd.DataFrame(rows, columns=["ssn", "intense"])
b["band"] = pd.cut(b.ssn, [0, 30, 60, 100, 200], labels=["<30", "30-60", "60-100", ">=100"])
storm = b.groupby("band", observed=True).intense.mean().round(2)
C6 = ["USA", "China", "Russia", "UK", "Japan", "India"]
D = dict(M=M,
         censuses=[["Jan 2014 (CDM)", M["active_2014"]], ["Apr 2020 (UCS)", M["active_2020"]], ["Sep 2026 (catalogue)", M["active_now"]]],
         years=[str(y) for y in pay.index], pay_other=(pay - sl).tolist(), pay_starlink=sl.tolist(),
         country=C6, share14=[float(cs.loc[k, "Jan 2014 (CDM) %"]) for k in C6], share26=[float(cs.loc[k, "Sep 2026 (catalogue) %"]) for k in C6],
         shells=[str(x) for x in sh.lo], sh_active=sh["Active 2026"].tolist(), sh_debris=sh["Debris 2026"].tolist(),
         sh_other=(sh["Objects 2026"] - sh["Active 2026"] - sh["Debris 2026"]).tolist(), sh_2014=sh["Objects 2014"].tolist(),
         asat=T("t4_asat_debris")[["Event", "Date", "Pieces catalogued", "Still in orbit %"]].values.tolist(),
         storm_bands=list(storm.index.astype(str)), storm_vals=storm.tolist(),
         rr_years=[str(y) for y in rr.year], rr_vals=rr.reentry_rate_pct.tolist(),
         pop_years=[str(y) for y in range(2000, 2031)], pop_actual=[int(pop.loc[y, "Payload"]) for y in range(2000, 2027)] + [None] * 4,
         pop_fc=[None] * 26 + [int(pop.loc[2026, "Payload"])] + tr["payloads in orbit (median)"].astype(int).tolist(),
         risk=rk.values.tolist(), scen=T("t8_scenarios_2030").values.tolist(), prem=T("t7_constellation_premium").values.tolist(),
         ml=T("t11_ml_results").values.tolist(), ml_imp=T("t11_ml_importance").head(6).values.tolist(),
         cj=T("t12_conjunction_summary").values.tolist(),
         india_deb=T("t12_india_encounters").query("screen.str.startswith('B')", engine="python").head(6)[["name_a", "name_b", "miss_km", "rel_speed_kms"]].round(2).values.tolist(),
         rob=T("t9_robustness").values.tolist(), score=T("t9_india_scorecard").fillna("-").values.tolist(), ow=T("t9_orbitwatch").values.tolist())
(ROOT / "deck/deck_data.json").write_text(json.dumps(D, default=lambda o: None))
print("deck_data.json written")
