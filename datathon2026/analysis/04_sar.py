"""Stage 4 - maritime traffic and AIS-dark analytics from Sentinel-1 SAR vessel detections."""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.cluster import DBSCAN
from statsmodels.stats.proportion import proportion_confint

from common import (C, CHOKEPOINTS, CLEAN, GULF_CONFLICT, INDIA_SEAS, RED_SEA_CONFLICT, SERIES,
                    basemap_ax, haversine_km, put_metrics, save, table)

print("Stage 4: SAR / AIS-dark analytics")
s = pd.read_parquet(CLEAN / "sar_clean.parquet")
ZONE = {**{r: "Gulf war zone" for r in GULF_CONFLICT}, **{r: "Red Sea zone" for r in RED_SEA_CONFLICT},
        "Black Sea": "Black Sea war zone", **{r: "India's seas" for r in INDIA_SEAS}}
s["zone"] = s.region.map(ZONE).fillna("Rest of world")
ZONES = ["Gulf war zone", "Black Sea war zone", "Red Sea zone", "India's seas", "Rest of world"]

# ---------------------------------------------------------------- 7.1 global map
fig, ax = plt.subplots(figsize=(9, 4.6))
basemap_ax(ax, -60, 75, -180, 180, res="c", grid=30)
lit = s[~s.dark].sample(frac=0.35, random_state=1)
drk = s[s.dark].sample(frac=0.35, random_state=1)
ax.scatter(lit.lon, lit.lat, s=0.4, color=C["blue"], alpha=0.35, lw=0, label="AIS-matched", rasterized=True)
ax.scatter(drk.lon, drk.lat, s=0.4, color=C["orange"], alpha=0.45, lw=0, label="AIS-dark (unmatched)", rasterized=True)
for cp, (la, lo) in CHOKEPOINTS.items():
    ax.plot(lo, la, marker="D", color=C["ink"], ms=3.5, mec="white", mew=0.5)
ax.legend(loc="lower left", markerscale=12)
ax.set_title("Figure 7.1  Sentinel-1 vessel detections, 1-14 March 2026 (35% sample plotted)")
save(fig, "f7_1_global_map")

# ---------------------------------------------------------------- 7.2 dark share by region with CIs
def rate_table(df, by):
    g = df.groupby(by).dark.agg(["sum", "count"])
    lo, hi = proportion_confint(g["sum"], g["count"], method="wilson")
    g["share"], g["lo"], g["hi"] = g["sum"] / g["count"], lo, hi
    return g


allv = rate_table(s, "region")
large = rate_table(s[s.large], "region")
order = large.sort_values("share").index
conflict_regions = GULF_CONFLICT | RED_SEA_CONFLICT | {"Black Sea"}
fig, ax = plt.subplots(1, 2, figsize=(9, 4.6), sharey=True)
for k, (tab, ttl) in enumerate([(allv, "All detected vessels"), (large, "Large vessels (>= 100 m)")]):
    tab = tab.reindex(order)
    cols = [C["orange"] if r in conflict_regions else (C["violet"] if r in INDIA_SEAS else C["blue"]) for r in tab.index]
    ax[k].barh(tab.index, tab.share * 100, color=cols, height=0.65)
    ax[k].errorbar(tab.share * 100, np.arange(len(tab)), xerr=[(tab.share - tab.lo) * 100, (tab.hi - tab.share) * 100],
                   fmt="none", ecolor=C["ink2"], lw=0.7, capsize=1.5)
    for i, (v, n, hi_) in enumerate(zip(tab.share, tab["count"], tab.hi)):
        ax[k].text(hi_ * 100 + 1.5, i, f"{v:.0%}  (n={n:,})", va="center", fontsize=6.5, color=C["ink2"])
    ax[k].set_xlim(0, 110)
    ax[k].set_title(ttl, fontsize=9.5)
    ax[k].set_xlabel("% with no AIS match (95% Wilson CI)")
    ax[k].grid(axis="y", visible=False)
fig.suptitle("Figure 7.2  AIS-dark share by sea region - orange: war zones, violet: India's seas",
             x=0.01, ha="left", fontsize=11, fontweight="bold")
fig.tight_layout()
save(fig, "f7_2_dark_by_region")
rt = allv[["count", "share"]].join(large[["count", "share", "lo", "hi"]], rsuffix="_large")
rt.columns = ["Detections", "Dark share (all)", "Large vessels", "Dark share (large)", "CI low", "CI high"]
rt = rt.sort_values("Dark share (large)", ascending=False)
table(rt.round(3).reset_index(names="Region"), "t7_1_dark_by_region")

# chi-square: large-vessel darkness, conflict regions vs rest
L = s[s.large]
ct = pd.crosstab(L.region.isin(conflict_regions), L.dark)
chi2, pchi, _, _ = stats.chi2_contingency(ct)
p_conf = L[L.region.isin(conflict_regions)].dark.mean()
p_rest = L[~L.region.isin(conflict_regions)].dark.mean()
rr = p_conf / p_rest
odds = (ct.loc[True, True] / ct.loc[True, False]) / (ct.loc[False, True] / ct.loc[False, False])
gulf_large = L[L.region.isin(GULF_CONFLICT)].dark.mean()
rest_large = L[L.region.isin(set(L.region) - conflict_regions - INDIA_SEAS)].dark.mean()

# ---------------------------------------------------------------- 7.3 size class x zone
sz = s.groupby(["zone", "size_class"], observed=True).dark.mean().unstack()[["<25 m", "25-40 m", "40-100 m", "100-200 m", ">200 m"]]
sz = sz.reindex(ZONES)
fig, ax = plt.subplots(figsize=(9, 3.3))
w = 0.16
x = np.arange(sz.shape[1])
for i, z in enumerate(ZONES):
    ax.bar(x + (i - 2) * w, sz.loc[z] * 100, width=w * 0.92, color=SERIES[i], label=z)
ax.set_xticks(x, sz.columns)
ax.set_xlabel("Estimated hull length")
ax.set_ylabel("% AIS-dark")
ax.legend(ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.2))
ax.grid(axis="x", visible=False)
ax.set_title("Figure 7.3  Darkness by vessel size: small craft are dark everywhere; big ships are dark only in war zones")
save(fig, "f7_3_size_zone")
table((sz * 100).round(1).reset_index(), "t7_2_size_zone")


# ---------------------------------------------------------------- Getis-Ord Gi* helper
def gi_star(cells, value, res):
    """Gi* z-scores on a lat/lon grid; neighbours = cells within 1.5 grid steps (queen + self)."""
    xy = cells[["gy", "gx"]].values
    xv = cells[value].values
    n, xbar, S = len(xv), xv.mean(), xv.std()
    out = np.zeros(n)
    for i in range(n):
        wmask = (np.abs(xy[:, 0] - xy[i, 0]) <= 1) & (np.abs(xy[:, 1] - xy[i, 1]) <= 1)
        W = wmask.sum()
        num = xv[wmask].sum() - xbar * W
        den = S * np.sqrt((n * W - W ** 2) / (n - 1))
        out[i] = num / den if den > 0 else 0
    return out


def grid(df, res, min_n):
    d = df.assign(gy=np.floor(df.lat / res).astype(int), gx=np.floor(df.lon / res).astype(int))
    g = d.groupby(["gy", "gx"]).agg(n=("dark", "size"), dark=("dark", "sum")).reset_index()
    g = g[g.n >= min_n].copy()
    g["share"] = g.dark / g.n
    g["lat"], g["lon"] = (g.gy + 0.5) * res, (g.gx + 0.5) * res
    g["gi"] = gi_star(g, "share", res)
    return g


# ---------------------------------------------------------------- 7.4 Gulf / Arabian Sea hot spots (large vessels)
box = s[s.lat.between(10, 31) & s.lon.between(40, 78) & (s.length_m >= 60)]
gg = grid(box, 0.5, 4)
fig, ax = plt.subplots(1, 2, figsize=(9, 4))
for k, (col, cmap, lab, vmin, vmax) in enumerate([("share", "Oranges", "AIS-dark share", 0, 1),
                                                  ("gi", "RdBu_r", "Gi* z-score", -4, 4)]):
    basemap_ax(ax[k], 10, 31, 40, 78, res="l", grid=10)
    sc = ax[k].scatter(gg.lon, gg.lat, c=gg[col], cmap=cmap, vmin=vmin, vmax=vmax, s=16, marker="s", lw=0)
    cb = fig.colorbar(sc, ax=ax[k], orientation="horizontal", fraction=0.05, pad=0.08)
    cb.set_label(lab)
ax[0].set_title("Dark share, vessels >= 60 m (0.5 deg cells)", fontsize=9)
ax[1].set_title("Getis-Ord Gi* hot spots (z > 1.96 = significant)", fontsize=9)
fig.suptitle("Figure 7.4  AIS dark spots in India's western approaches", x=0.01, ha="left", fontsize=11, fontweight="bold")
fig.tight_layout()
save(fig, "f7_4_gulf_hotspots")
hot = gg[gg.gi > 1.96]

# ---------------------------------------------------------------- 7.5 global hot spot map (1 deg, large vessels)
gl = grid(s[s.length_m >= 60], 1.0, 5)
fig, ax = plt.subplots(figsize=(9, 4.6))
basemap_ax(ax, -60, 75, -180, 180, res="c", grid=30)
cold = gl[gl.gi <= 1.96]
ax.scatter(cold.lon, cold.lat, s=3, color="#c3c2b7", marker="s", lw=0, label="not significant")
h = gl[gl.gi > 1.96]
sc = ax.scatter(h.lon, h.lat, c=h.gi, cmap="Reds", vmin=1.96, vmax=6, s=6, marker="s", lw=0)
cb = fig.colorbar(sc, ax=ax, fraction=0.025)
cb.set_label("Gi* z-score (hot spots)")
ax.set_title("Figure 7.5  Global hot spots of AIS-dark ships >= 60 m (1 deg cells, Gi* > 1.96)")
save(fig, "f7_5_global_hotspots")
gl["region"] = pd.Series(dtype=object)
from common import assign_region
gl["region"] = assign_region(gl.lat.values, gl.lon.values)
hot_by_region = gl[gl.gi > 1.96].groupby("region").size().sort_values(ascending=False)
table(hot_by_region.rename("Hot-spot cells").reset_index(), "t7_3_hotspot_cells")

# ---------------------------------------------------------------- 7.6 DBSCAN clusters of dark large vessels
GAZ = {  # reference anchorages / ports for naming clusters
    "Fujairah / Khor Fakkan anchorage": (25.2, 56.45), "Strait of Hormuz (Bandar Abbas-Qeshm)": (26.9, 56.2),
    "Dubai / Jebel Ali": (25.1, 55.0), "Ras Tanura / Dammam": (26.6, 50.2), "Kuwait / Iraq (Basra)": (29.5, 48.5),
    "Ras Laffan / Doha (Qatar)": (25.6, 51.8), "Kharg Island (Iran)": (29.2, 50.3), "Abu Dhabi / Ruwais": (24.4, 53.3),
    "Sohar / Muscat (Oman)": (24.0, 57.3), "Singapore Strait / EOPL Johor": (1.3, 104.2), "Port Klang": (2.9, 101.3),
    "Novorossiysk / Kerch (Russia)": (44.9, 37.3), "Odesa (Ukraine)": (46.3, 30.9), "Bosphorus / Istanbul": (41.0, 29.0),
    "Laconian Gulf (Greece)": (36.6, 22.8), "Port Said / Suez": (31.0, 32.4), "Jeddah": (21.5, 39.1),
    "Mumbai / JNPT": (18.9, 72.8), "Kandla / Mundra (Gulf of Kutch)": (22.8, 70.0), "Chennai": (13.1, 80.3),
    "Kolkata / Haldia": (21.8, 88.1), "Karachi": (24.8, 66.9), "Colombo": (6.95, 79.8), "Chittagong": (22.2, 91.8),
    "Shanghai / Ningbo": (30.8, 122.3), "Hong Kong / Pearl River": (22.2, 113.9), "Busan": (35.1, 129.1),
    "Qingdao": (36.0, 120.4), "Kaohsiung / Taiwan Strait": (23.5, 119.8), "Tianjin / Bohai": (38.8, 118.4),
    "Rotterdam / North Sea": (52.0, 3.9), "Gibraltar / Algeciras": (36.1, -5.4), "Malta": (35.9, 14.5),
    "Ceuta / Tangier": (35.8, -5.5), "Lome (Togo)": (6.1, 1.3), "Lagos": (6.4, 3.4), "Durban": (-29.9, 31.1),
    "Batam / Riau": (1.1, 104.0), "Ho Chi Minh / Vung Tau": (10.3, 107.1), "Manila Bay": (14.5, 120.8),
    "Chabahar / Gwadar": (25.2, 61.0), "Aden": (12.8, 45.0), "Hodeidah (Yemen)": (14.8, 42.9),
}
gnames = list(GAZ)
glat = np.array([GAZ[k][0] for k in gnames])
glon = np.array([GAZ[k][1] for k in gnames])
D = s[s.dark & s.large].copy()
db = DBSCAN(eps=25 / 6371, min_samples=15, metric="haversine").fit(np.radians(D[["lat", "lon"]].values))
D["cl"] = db.labels_
cl = D[D.cl >= 0].groupby("cl").agg(n=("lat", "size"), lat=("lat", "mean"), lon=("lon", "mean"),
                                    med_len=("length_m", "median"), days=("date", "nunique")).reset_index()
# share of all large vessels in the cluster footprint that are dark
L_all = s[s.large]
shares = []
for _, r in cl.iterrows():
    near = haversine_km(L_all.lat.values, L_all.lon.values, r.lat, r.lon) <= 30
    shares.append(L_all[near].dark.mean())
cl["dark_share_local"] = shares
dist = np.array([haversine_km(glat, glon, r.lat, r.lon) for _, r in cl.iterrows()])
cl["nearest_ref"] = [gnames[i] if dist[j, i] < 250 else f"{r.lat:.1f}N {r.lon:.1f}E"
                     for j, (i, (_, r)) in enumerate(zip(dist.argmin(1), cl.iterrows()))]
cl["region"] = assign_region(cl.lat.values, cl.lon.values)
cl = cl.sort_values("n", ascending=False)
cl["rank"] = np.arange(1, len(cl) + 1)
table(cl.head(15)[["rank", "nearest_ref", "region", "n", "dark_share_local", "med_len", "days", "lat", "lon"]]
      .rename(columns={"nearest_ref": "Cluster (nearest reference)", "n": "Dark large vessels",
                       "dark_share_local": "Dark share of large ships within 30 km", "med_len": "Median length (m)",
                       "days": "Days observed", "rank": "#"}).round(2), "t7_4_dark_clusters")
fig, ax = plt.subplots(figsize=(9, 4.6))
basemap_ax(ax, -40, 60, -20, 140, res="c", grid=20)
noise = D[D.cl < 0]
ax.scatter(noise.lon, noise.lat, s=1, color="#b5b4ae", lw=0, rasterized=True, label="dark large vessel (unclustered)")
sc = ax.scatter(cl.lon, cl.lat, s=np.sqrt(cl.n) * 9, c=cl.dark_share_local, cmap="Oranges", vmin=0, vmax=1,
                edgecolor=C["ink"], linewidth=0.5, zorder=5)
cl["rank"] = np.arange(1, len(cl) + 1)
for _, r in cl.head(10).iterrows():
    ax.annotate(str(r["rank"]), (r.lon, r.lat), xytext=(0, 0), textcoords="offset points", fontsize=6.5,
                ha="center", va="center", color="white", fontweight="bold", zorder=7)
cb = fig.colorbar(sc, ax=ax, fraction=0.025)
cb.set_label("dark share of large ships in cluster")
ax.legend(loc="lower left", markerscale=5)
ax.set_title("Figure 7.6  DBSCAN clusters of AIS-dark ships >= 100 m (eps 25 km, min 15); numbers = cluster rank")
save(fig, "f7_6_dbscan")

# ---------------------------------------------------------------- 7.7 Gulf daily traffic & darkness
gz = s[s.region.isin(GULF_CONFLICT)]
day = gz.groupby("date").agg(det=("dark", "size"), dark=("dark", "mean"), scenes=("scene_id", "nunique"),
                             large=("large", "sum"))
day["per_scene"] = day.det / day.scenes
fig, ax = plt.subplots(1, 2, figsize=(9, 3))
ax[0].bar(day.index, day.per_scene, color=C["blue"], width=0.7)
ax[0].set_title("Detections per SAR scene (Gulf war zone)", fontsize=9)
ax[1].plot(day.index, day.dark * 100, color=C["orange"], marker="o", ms=4)
ax[1].set_ylim(0, 100)
ax[1].set_title("% of detections AIS-dark", fontsize=9)
for x_ in ax:
    x_.tick_params(axis="x", rotation=45, labelsize=7)
fig.suptitle("Figure 7.7  Daily picture in the Gulf, 1-14 March 2026 (weeks 1-2 of the war)", x=0.01, ha="left",
             fontsize=11, fontweight="bold")
fig.tight_layout()
save(fig, "f7_7_gulf_daily")
tr = stats.spearmanr(np.arange(len(day)), day.dark)

# ---------------------------------------------------------------- 7.8 flag states of AIS-visible ships
fz = s[s.flag_class.notna() & s.large]
fc = pd.crosstab(fz.zone, fz.flag_class, normalize="index").reindex(ZONES) * 100
fcols = ["National flag", "Flag of convenience", "Shadow-fleet-associated", "Other/undecoded"]
fc = fc.reindex(columns=fcols).fillna(0)
fig, ax = plt.subplots(figsize=(9, 2.8))
left = np.zeros(len(fc))
for i, c in enumerate(fcols):
    ax.barh(fc.index, fc[c], left=left, color=SERIES[i], label=c, height=0.6, edgecolor="white", linewidth=1)
    for j, v in enumerate(fc[c]):
        if v >= 6:
            ax.text(left[j] + v / 2, j, f"{v:.0f}%", ha="center", va="center", fontsize=7, color="white")
    left += fc[c].values
ax.set_xlim(0, 100)
ax.invert_yaxis()
ax.legend(ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.15))
ax.grid(axis="y", visible=False)
ax.set_title("Figure 7.8  Registry of AIS-visible large ships (MMSI MID decode)")
save(fig, "f7_8_flags")
table(fc.round(1).reset_index(), "t7_5_flag_class")
top_flags_gulf = fz[fz.zone == "Gulf war zone"].flag.value_counts(normalize=True).head(10) * 100
top_flags_world = fz[fz.zone == "Rest of world"].flag.value_counts(normalize=True)
tf = pd.DataFrame({"Gulf war zone %": top_flags_gulf.round(1),
                   "Rest of world %": top_flags_world.reindex(top_flags_gulf.index).fillna(0).mul(100).round(1)})
table(tf.reset_index(names="Flag"), "t7_6_top_flags_gulf")

# ---------------------------------------------------------------- 7.9 identity integrity
m = s[s.mmsi_valid & ~s.dark].sort_values(["mmsi", "ts"]).copy()
g = m.groupby("mmsi")
m["plat"], m["plon"], m["pts"] = g.lat.shift(), g.lon.shift(), g.ts.shift()
m = m.dropna(subset=["plat"])
m["km"] = haversine_km(m.lat.values, m.lon.values, m.plat.values, m.plon.values)
m["hrs"] = (m.ts - m.pts).dt.total_seconds() / 3600
m["knots"] = m.km / 1.852 / m.hrs.clip(lower=1 / 60)
clones = m[(m.knots > 50) & (m.km > 20)]
placeholder = s.mmsi.notna() & (s.mmsi % 1_000_000 == 0)
ident = pd.DataFrame({
    "Indicator": ["Malformed MMSI (MID outside 2xx-7xx)", "Placeholder MMSI (xxx000000)",
                  "Physically impossible re-sighting (>50 kn over >20 km)", "'noisy_vessel' AIS tracks"],
    "Global": [int(s.mmsi_malformed.sum()), int(placeholder.sum()), len(clones),
               int((s.matched_category == "noisy_vessel").sum())],
    "Gulf war zone": [int(s[s.zone == "Gulf war zone"].mmsi_malformed.sum()), int(placeholder[s.zone == "Gulf war zone"].sum()),
                      int(clones.region.isin(GULF_CONFLICT).sum()),
                      int(((s.matched_category == "noisy_vessel") & (s.zone == "Gulf war zone")).sum())],
})
table(ident, "t7_7_identity")
noisy = s.groupby("zone").apply(lambda d: (d.matched_category == "noisy_vessel").mean() * 100, include_groups=False)

# ---------------------------------------------------------------- 7.10 India's seas close-up
ind = s[s.lat.between(0, 26) & s.lon.between(60, 100)]
fig, ax = plt.subplots(figsize=(9, 5))
basemap_ax(ax, 0, 26, 60, 100, res="l", grid=5)
for lab, sel, col, sz_ in [("AIS-matched", ~ind.dark, C["blue"], 2), ("Dark < 60 m (mostly fishing)", ind.dark & (ind.length_m < 60), C["yellow"], 2),
                           ("Dark >= 60 m", ind.dark & (ind.length_m >= 60), C["red"], 7)]:
    d_ = ind[sel]
    ax.scatter(d_.lon, d_.lat, s=sz_, color=col, lw=0, alpha=0.7, label=f"{lab} (n={len(d_):,})", rasterized=True)
ax.legend(loc="lower left", markerscale=3)
ax.set_title("Figure 7.10  India's maritime neighbourhood - who is visible and who is not (1-14 Mar 2026)")
save(fig, "f7_10_india_seas")
ind_seas = s[s.region.isin(INDIA_SEAS)]

put_metrics(
    large_conflict_dark=round(float(p_conf), 3), large_rest_dark=round(float(p_rest), 3),
    large_rr=round(float(rr), 2), large_or=round(float(odds), 2), chi2=round(float(chi2), 1), chi2_p=float(pchi),
    gulf_large_dark=round(float(gulf_large), 3), rest_large_dark=round(float(rest_large), 3),
    hormuz_large_dark=round(float(large.loc["Strait of Hormuz", "share"]), 3),
    pg_large_dark=round(float(large.loc["Persian Gulf", "share"]), 3),
    goo_large_dark=round(float(large.loc["Gulf of Oman", "share"]), 3),
    black_large_dark=round(float(large.loc["Black Sea", "share"]), 3),
    redsea_large_dark=round(float(large.loc["Red Sea", "share"]), 3),
    arab_all_dark=round(float(allv.loc["Arabian Sea", "share"]), 3), bob_all_dark=round(float(allv.loc["Bay of Bengal", "share"]), 3),
    arab_large_dark=round(float(large.loc["Arabian Sea", "share"]), 3), bob_large_dark=round(float(large.loc["Bay of Bengal", "share"]), 3),
    nweu_all_dark=round(float(allv.loc["NW Europe & North Sea", "share"]), 3),
    india_seas_n=len(ind_seas), india_seas_dark=int(ind_seas.dark.sum()),
    india_seas_small_dark_share=round(float(ind_seas[ind_seas.length_m < 40].dark.mean()), 3),
    india_seas_fishing_share_dark=round(float(ind_seas[ind_seas.dark].likely_fishing.mean()), 3),
    gulf_hot_cells=len(hot), gulf_cells=len(gg), global_hot_cells=int((gl.gi > 1.96).sum()), global_cells=len(gl),
    n_clusters=len(cl), top_cluster=cl.iloc[0].nearest_ref, top_cluster_n=int(cl.iloc[0].n),
    top_cluster_share=round(float(cl.iloc[0].dark_share_local), 3),
    gulf_daily_trend_rho=round(float(tr.correlation), 2), gulf_daily_trend_p=round(float(tr.pvalue), 3),
    gulf_dark_first3=round(float(day.dark.iloc[:3].mean()), 3), gulf_dark_last3=round(float(day.dark.iloc[-3:].mean()), 3),
    flag_gulf_foc=round(float(fc.loc["Gulf war zone", "Flag of convenience"]), 1),
    flag_world_foc=round(float(fc.loc["Rest of world", "Flag of convenience"]), 1),
    flag_gulf_shadow=round(float(fc.loc["Gulf war zone", "Shadow-fleet-associated"]), 1),
    flag_world_shadow=round(float(fc.loc["Rest of world", "Shadow-fleet-associated"]), 1),
    flag_black_shadow=round(float(fc.loc["Black Sea war zone", "Shadow-fleet-associated"]), 1),
    clones=len(clones), placeholders=int(placeholder.sum()),
    noisy_gulf=round(float(noisy.get("Gulf war zone", 0)), 2), noisy_world=round(float(noisy.get("Rest of world", 0)), 2),
)
print(rt.head(10))
print(cl.head(12)[["nearest_ref", "region", "n", "dark_share_local", "med_len"]])
print(fc.round(1))
print(tf)
print(ident)
print(hot_by_region.head(10))
print("rr", rr, "odds", odds, "chi2", chi2, pchi, "trend", tr)
