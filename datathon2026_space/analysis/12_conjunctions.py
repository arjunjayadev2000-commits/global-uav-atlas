"""Stage 12 - close-approach (conjunction) screening from current orbital elements, using the SGP4 propagator."""

# =====================================================================================================
# ANNOTATED SOURCE - Stage 12: close-approach screening (booklet Chapter 4, Technical Annex T11)
# -----------------------------------------------------------------------------------------------------
# DATA   Current orbital elements (CCSDS OMM, the modern form of 'two-line elements') published by CelesTrak, via a
#        public mirror (data/open/omm). The public mirror refreshed its satellite groups on different dates, so two
#        screenings are run, each inside the window where its elements are fresh (no element set older than ~3 days):
#          A. TRAFFIC: all 16,468 active satellites against each other, 24 h from 31 Aug 2026 12:00 UTC.
#          B. DEBRIS THREAT: freshly-tracked satellites (Earth observation incl. India's, weather, military, science,
#             stations, amateur, new launches) against the four largest debris clouds (Chinese ASAT test, Iridium-Cosmos
#             collision, Russian ASAT test), 24 h from 23 Sep 2026 12:00 UTC.
# METHOD 1. SGP4 (the standard propagator for these elements) gives every object's position every 10 seconds.
#        2. COARSE FILTER: at each step a k-d tree finds every pair closer than 80 km. 80 km is enough: two objects
#           closing at up to 15 km/s move at most 75 km relative to each other between 10-second samples.
#        3. REFINE: for each candidate pair, positions every second around the closest sample, then the time and
#           distance of closest approach from the linearised relative motion (TCA and miss distance).
#        4. Report encounters with miss distance < 5 km (screening threshold) and < 1 km (high interest), with
#           relative speed. Same-constellation neighbours flying in formation (relative speed < 0.5 km/s) are
#           separated from true crossing encounters, as are docked spacecraft (e.g. ISS modules).
# LIMITS Public elements are accurate to roughly 1 km; this is SCREENING (like CelesTrak SOCRATES), not the
#        covariance-based collision probability an operator computes before a manoeuvre.
# =====================================================================================================
import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from sgp4 import omm
from sgp4.api import Satrec, SatrecArray, jday

from common import C, CLEAN, OPEN, put_metrics, save, table

print("Stage 12: conjunction screening")
SAT = pd.read_parquet(CLEAN / "satcat.parquet").set_index("NORAD_CAT_ID")
DEBRIS = ["fengyun-1c-debris", "cosmos-2251-debris", "iridium-33-debris", "cosmos-1408-debris"]
FRESH = ["resource", "weather", "military", "science", "stations", "analyst", "planet", "spire", "cubesat", "iridium-NEXT",
         "sarsat", "engineering", "geodetic", "radar", "amateur", "satnogs", "x-comm", "other-comm", "argos", "dmc",
         "education", "last-30-days"]


def load(groups):
    recs = {}
    for g in groups:
        for r in json.load(open(OPEN / "omm" / f"{g}.json")):
            k = r["NORAD_CAT_ID"]
            if k not in recs or r["EPOCH"] > recs[k]["EPOCH"]:
                recs[k] = r
    out = []
    for k, r in recs.items():
        if r["MEAN_MOTION"] < 11.25 or r["ECCENTRICITY"] > 0.25:        # low Earth orbit only (period under ~128 min)
            continue
        s = Satrec()
        omm.initialize(s, {kk: str(v) for kk, v in r.items()})
        out.append((k, r["OBJECT_NAME"], r["EPOCH"], s))
    return out


def screen(objs, t0, hours=24, dt=10.0, R=80.0, chunk=360):
    ids = np.array([o[0] for o in objs])
    arr = SatrecArray([o[3] for o in objs])
    jd0, fr0 = jday(*t0)
    n_steps = int(hours * 3600 / dt)
    best = {}
    for c0 in range(0, n_steps, chunk):
        steps = np.arange(c0, min(c0 + chunk, n_steps))
        e, r, _ = arr.sgp4(np.full(len(steps), jd0), fr0 + steps * dt / 86400)
        r[e != 0] = 1e9                                                  # failed propagations are parked far away
        frames = []
        for j, st in enumerate(steps):
            p = r[:, j, :]
            pairs = cKDTree(p).query_pairs(R, output_type="ndarray")
            if len(pairs):
                d = np.linalg.norm(p[pairs[:, 0]] - p[pairs[:, 1]], axis=1)
                frames.append(pd.DataFrame({"a": pairs[:, 0], "b": pairs[:, 1], "d": d, "step": st}))
        if frames:
            f = pd.concat(frames).sort_values("d").drop_duplicates(["a", "b"])
            for a, b, d, st in f.itertuples(index=False):
                if (a, b) not in best or d < best[(a, b)][0]:
                    best[(a, b)] = (d, st)
        print(f"    steps {c0}-{steps[-1]}: {len(best):,} candidate pairs")
    rows = []
    for (a, b), (d, st) in best.items():
        ts = st * dt + np.arange(-dt, dt + 1, 1.0)                        # 1-second refinement around the closest sample
        jd = np.full(len(ts), jd0)
        fr = fr0 + ts / 86400
        ea, ra, va = objs[a][3].sgp4_array(jd, fr)
        eb, rb, vb = objs[b][3].sgp4_array(jd, fr)
        if ea.any() or eb.any():
            continue
        dr, dv = ra - rb, va - vb
        k = int(np.argmin(np.linalg.norm(dr, axis=1)))
        tau = np.clip(-np.dot(dr[k], dv[k]) / max(np.dot(dv[k], dv[k]), 1e-9), -1, 1)   # linearised time of closest approach
        miss = float(np.linalg.norm(dr[k] + dv[k] * tau))
        if miss < 5.0:
            alt = float(np.linalg.norm((ra[k] + rb[k]) / 2)) - 6378.137
            rows.append((ids[a], ids[b], objs[a][1], objs[b][1], miss, float(np.linalg.norm(dv[k])), alt, ts[k] + tau))
    return pd.DataFrame(rows, columns=["id_a", "id_b", "name_a", "name_b", "miss_km", "rel_speed_kms", "alt_km", "t_s"])


def tag(df):
    def info(i, name):
        row = SAT.loc[i] if i in SAT.index else None
        typ = row["type"] if row is not None else "Payload"
        own = row["owner"] if row is not None else "Other"
        con = row["constellation"] if row is not None and row["constellation"] else ""
        if "DEB" in str(name):
            typ = "Debris"
        return typ, own, con
    ia = [info(i, n) for i, n in zip(df.id_a, df.name_a)]
    ib = [info(i, n) for i, n in zip(df.id_b, df.name_b)]
    df["type_a"], df["owner_a"], df["con_a"] = zip(*ia) if len(ia) else ([], [], [])
    df["type_b"], df["owner_b"], df["con_b"] = zip(*ib) if len(ib) else ([], [], [])
    same = (df.con_a == df.con_b) & (df.con_a != "") & (df.con_a != "Other")
    # relative speed under 0.5 km/s = flying together (formation, or docked like the ISS modules): not a crossing
    df["kind"] = np.select([df.type_a.eq("Debris") | df.type_b.eq("Debris"), df.rel_speed_kms < 0.5, same],
                           ["Satellite vs debris", "Co-orbiting (formation or docked)", "Same constellation, crossing"],
                           "Different operators, crossing")
    df["india"] = df.owner_a.eq("India") | df.owner_b.eq("India")
    return df


# ---------------------------------------------------------------- A. traffic among all active satellites
A_objs = load(["active"])
print(f"  A: {len(A_objs):,} active LEO satellites")
A = tag(screen(A_objs, (2026, 8, 31, 12, 0, 0)))
# ---------------------------------------------------------------- B. debris threat to freshly-tracked satellites
B_objs = load(FRESH + DEBRIS)
print(f"  B: {len(B_objs):,} objects (fresh satellites + debris clouds)")
B = tag(screen(B_objs, (2026, 9, 23, 12, 0, 0)))
B = B[B.kind.eq("Satellite vs debris") & ~(B.type_a.eq("Debris") & B.type_b.eq("Debris"))]

allc = pd.concat([A.assign(screen="A: active vs active (31 Aug-1 Sep)"), B.assign(screen="B: satellites vs debris clouds (23-24 Sep)")])
summ = allc.groupby(["screen", "kind"]).agg(encounters_5km=("miss_km", "size"), under_1km=("miss_km", lambda s: int((s < 1).sum())),
                                            median_rel_speed=("rel_speed_kms", "median")).round(2).reset_index()
table(summ, "t12_conjunction_summary")
top = allc[~allc.kind.eq("Co-orbiting (formation or docked)")].sort_values("miss_km").head(20)
table(top[["screen", "name_a", "name_b", "kind", "miss_km", "rel_speed_kms", "alt_km"]].round(3), "t12_closest_encounters")
ind = allc[allc.india]
table(ind[["screen", "name_a", "name_b", "kind", "miss_km", "rel_speed_kms", "alt_km"]].sort_values("miss_km").round(3), "t12_india_encounters")

cross = allc[~allc.kind.eq("Co-orbiting (formation or docked)")]
fig, ax = plt.subplots(1, 2, figsize=(9, 3.2), gridspec_kw={"width_ratios": [1.3, 1]})
bins = np.arange(200, 1300, 25)
kinds = ["Different operators, crossing", "Same constellation, crossing", "Satellite vs debris"]
for k, col in zip(kinds, [C["orange"], C["blue"], C["red"]]):
    h = np.histogram(cross[cross.kind.eq(k)].alt_km, bins)[0]
    ax[0].step(bins[:-1] + 12.5, np.where(h > 0, h, np.nan), where="mid", color=col, lw=1.8, label=f"{k} ({int(h.sum()):,})")
ax[0].set_yscale("log")                                     # log scale so the debris encounters show beside the Starlink traffic
ax[0].set_xlabel("altitude of encounter (km)")
ax[0].set_ylabel("encounters closer than 5 km")
ax[0].legend(fontsize=7)
ax[0].set_title("Where close approaches happen (24-hour screenings)", fontsize=9)
ax[1].hist(cross.rel_speed_kms, bins=np.arange(0, 16, 0.5), color=C["violet"])
ax[1].set_xlabel("relative speed at closest approach (km/s)")
ax[1].set_ylabel("encounters")
ax[1].set_title("How fast they pass", fontsize=9)
fig.suptitle("Close-approach screening from current orbital elements (SGP4)", x=0.01, ha="left", fontsize=11, fontweight="bold")
fig.tight_layout()
save(fig, "f12_1_conjunctions")

g = lambda df, k: int(df.kind.eq(k).sum())
put_metrics(
    cj_A_n=len(A_objs), cj_B_n=len(B_objs), cj_A_total=len(A), cj_A_coorbit=g(A, "Co-orbiting (formation or docked)"),
    cj_A_cross_same=g(A, "Same constellation, crossing"), cj_A_cross_diff=g(A, "Different operators, crossing"),
    cj_A_under1=int((A[~A.kind.eq("Co-orbiting (formation or docked)")].miss_km < 1).sum()),
    cj_B_total=len(B), cj_B_under1=int((B.miss_km < 1).sum()), cj_cross_total=len(cross),
    cj_B_india=int(B.india.sum()), cj_A_india=int(A[~A.kind.eq("Co-orbiting (formation or docked)")].india.sum()),
    cj_cross_starlink_share=round(float((cross.con_a.eq("Starlink (US)") | cross.con_b.eq("Starlink (US)")).mean()), 3) if len(cross) else 0,
    cj_india=int(len(ind)), cj_india_min=round(float(ind.miss_km.min()), 2) if len(ind) else None,
    cj_median_speed=round(float(cross.rel_speed_kms.median()), 1) if len(cross) else None,
    cj_min_miss=round(float(cross.miss_km.min()), 3) if len(cross) else None,
    cj_peak_alt=int(pd.Series(cross.alt_km // 25 * 25).mode().iloc[0]) if len(cross) else None,
)
print(summ.to_string(), "\n", top.head(10)[["name_a", "name_b", "kind", "miss_km", "rel_speed_kms", "alt_km"]].to_string(), "\nIndia\n", ind.head(10).to_string())
