"""Stage 5 - predictive model of AIS darkness and a predicted dark-spot surface for the Indian Ocean."""

# =====================================================================================================
# ANNOTATED SOURCE - Stage 5: predicting where ships go dark (report Chapter 8)
# -----------------------------------------------------------------------------------------------------
# QUESTION  Given a ship's size and where it is relative to the fighting, how likely is it to be AIS-dark?
#           If this can be forecast, satellites can be pointed at the right waters.
# INPUT     data/clean/sar_clean.parquet (ships >= 40 m, about 62,000) and the war-time conflict centroids.
# OUTPUT    Figures 8.1-8.3; tables t8_1 (logit), t8_2 (model skill), t8_3 (risk at places that matter to
# India).
# METHODS   1. Logistic regression (statsmodels): an explainable model; each odds ratio says how the odds of
#              darkness change per one standard deviation of a feature.
#           2. Gradient-boosted trees (HistGradientBoosting): a stronger, non-linear model, constrained so that
#              darkness can never rise with distance from the fighting (domain knowledge built in).
#           3. Honest testing: LEAVE-ONE-REGION-OUT cross-validation (GroupKFold by sea region). The model is
#           always
#              scored on seas it never saw in training. An ordinary random split is also reported, labelled
#              'leaky',
#              because neighbouring ships share information and flatter the score.
#           4. Permutation importance (which feature matters most) and a partial-dependence curve.
#           5. A predicted 'dark-risk' map for a 180 m merchant ship across the Indian Ocean.
# SCORES    ROC-AUC: 0.5 = coin toss, 1.0 = perfect. PR-AUC and Brier score are also reported.
# =====================================================================================================

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, brier_score_loss, confusion_matrix, f1_score,
                             roc_auc_score, roc_curve)
from sklearn.model_selection import GroupKFold
from sklearn.neighbors import BallTree
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from common import C, CLEAN, SERIES, basemap_ax, haversine_km, CHOKEPOINTS, put_metrics, save, table

print("Stage 5: predictive model")
s = pd.read_parquet(CLEAN / "sar_clean.parquet")
# Ships of 40 m and more (commercial ships and large fishing boats that are expected to carry AIS).
s = s[s.length_m >= 40].copy()          # vessels expected to carry AIS (commercial & large fishing)
# Log transforms: a change from 50 to 100 km matters more than one from 2,050 to 2,100 km.
s["log_len"] = np.log(s.length_m)
s["log_dist_conflict"] = np.log1p(s.dist_conflict_km)
s["log_dist_choke"] = np.log1p(s.dist_chokepoint_km)
# The five inputs (features): hull length, fishing score, distance to the fighting, amount of fighting within
# 500 km, and distance to a chokepoint. Latitude/longitude are deliberately NOT used, so the model learns
# conflict geography rather than memorising places.
FEATS = ["log_len", "fishing_score", "log_dist_conflict", "log_conflict_500", "log_dist_choke"]
LABELS = {"log_len": "Hull length (log m)", "fishing_score": "Fishing-vessel score",
          "log_dist_conflict": "Distance to nearest conflict ADMIN1 (log km)",
          "log_conflict_500": "Conflict events within 500 km (log)", "log_dist_choke": "Distance to chokepoint (log km)"}
# X = inputs, y = 1 if dark, groups = sea region (used to hold out whole regions when testing).
X, y, groups = s[FEATS].values, s.dark.values.astype(int), s.region.values

# ---------------------------------------------------------------- interpretable model: logistic regression (statsmodels)
# LOGISTIC REGRESSION on standardised features (Table 8.1): odds ratio per 1 SD, 95% CI and p-value.
Z = (s[FEATS] - s[FEATS].mean()) / s[FEATS].std()
logit = sm.Logit(y, sm.add_constant(Z)).fit(disp=False)
ci = logit.conf_int()
lt = pd.DataFrame({"Feature": [LABELS[f] for f in FEATS], "Coef (per 1 SD)": logit.params[FEATS].round(3),
                   "Odds ratio": np.exp(logit.params[FEATS]).round(3),
                   "OR 95% CI": [f"{np.exp(ci.loc[f, 0]):.2f} - {np.exp(ci.loc[f, 1]):.2f}" for f in FEATS],
                   "p-value": logit.pvalues[FEATS].map(lambda p: "<0.001" if p < 0.001 else f"{p:.3f}")})
table(lt, "t8_1_logit")

# ---------------------------------------------------------------- leave-one-region-out validation
# The two candidate models. monotonic_cst: 0 = free, -1 = prediction may only fall as the feature rises,
# +1 = may only rise. Here: darkness may only fall with distance from conflict and from a chokepoint, and only
# rise with the amount of fighting nearby.
models = {
    "Logistic regression": make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)),
    "Gradient-boosted trees": HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06, max_leaf_nodes=31,
                                                             l2_regularization=1.0, random_state=0,
                                                             # domain knowledge: darkness cannot rise with distance
                                                             # from the fighting, nor fall as fighting intensifies
                                                             monotonic_cst=[0, 0, -1, 1, -1]),
}
base_rate = y.mean()
# LEAVE-ONE-REGION-OUT style validation: 6 folds, each holding out whole sea regions.
# 'oof' (out-of-fold) predictions are always made on regions the model has not seen.
cv = GroupKFold(n_splits=6)
oof = {k: np.zeros(len(y)) for k in models}
for tr, te in cv.split(X, y, groups):
    for k, m in models.items():
        m.fit(X[tr], y[tr])
        oof[k][te] = m.predict_proba(X[te])[:, 1]
# Model skill table (Table 8.2): ROC-AUC, PR-AUC, Brier score, F1 and accuracy, plus a baseline that always says
# 'not dark'.
rows = []
for k, p in oof.items():
    thr = 0.5
    rows.append((k, roc_auc_score(y, p), average_precision_score(y, p), brier_score_loss(y, p),
                 f1_score(y, p >= thr), ((p >= thr) == y).mean()))
rows.append(("Baseline (always 'not dark')", 0.5, base_rate, brier_score_loss(y, np.full(len(y), base_rate)), 0.0, 1 - base_rate))
# contrast: ordinary random 5-fold CV (spatially leaky - neighbouring ships share information)
# For contrast only: an ordinary random 5-fold split. It scores higher because neighbouring ships leak
# information between training and test sets. It is reported as leaky, not used for claims.
from sklearn.model_selection import StratifiedKFold, cross_val_predict
rnd = cross_val_predict(models["Gradient-boosted trees"], X, y, cv=StratifiedKFold(5, shuffle=True, random_state=0),
                        method="predict_proba")[:, 1]
rows.append(("GBT, random 5-fold CV (leaky, for contrast)", roc_auc_score(y, rnd), average_precision_score(y, rnd),
             brier_score_loss(y, rnd), f1_score(y, rnd >= 0.5), ((rnd >= 0.5) == y).mean()))
mt = pd.DataFrame(rows, columns=["Model", "ROC-AUC", "PR-AUC", "Brier", "F1 @0.5", "Accuracy"]).round(3)
table(mt, "t8_2_model_cv")
best = "Gradient-boosted trees" if mt.iloc[1]["ROC-AUC"] >= mt.iloc[0]["ROC-AUC"] else "Logistic regression"
pb = oof[best]
cm = confusion_matrix(y, pb >= 0.5)

# ---------------------------------------------------------------- figure 8.1 ROC + importance
# Figure 8.1: ROC curves and permutation importance.
# Permutation importance = how much the score drops when one feature's values are shuffled (15,000-ship sample,
# seeded).
gbm = models["Gradient-boosted trees"].fit(X, y)
idx = np.random.default_rng(0).choice(len(y), 15000, replace=False)
pi = permutation_importance(gbm, X[idx], y[idx], scoring="roc_auc", n_repeats=5, random_state=0)
imp = pd.Series(pi.importances_mean, index=[LABELS[f] for f in FEATS]).sort_values()
fig, ax = plt.subplots(1, 2, figsize=(9, 3.4), gridspec_kw={"width_ratios": [1, 1.3]})
for i, (k, p) in enumerate(oof.items()):
    fpr, tpr, _ = roc_curve(y, p)
    ax[0].plot(fpr, tpr, color=SERIES[i], label=f"{k} (AUC {roc_auc_score(y, p):.2f})")
ax[0].plot([0, 1], [0, 1], color=C["muted"], ls=":", lw=0.8)
ax[0].set_xlabel("False-positive rate")
ax[0].set_ylabel("True-positive rate")
ax[0].legend(loc="lower right", fontsize=7)
ax[0].set_title("ROC, leave-one-region-out", fontsize=9)
ax[1].barh(imp.index, imp.values, color=C["blue"], height=0.55)
ax[1].set_xlabel("Drop in ROC-AUC when feature is shuffled")
ax[1].set_title("Permutation importance (GBT)", fontsize=9)
ax[1].grid(axis="y", visible=False)
fig.suptitle("Figure 8.1  Predicting AIS darkness from conflict geography", x=0.01, ha="left", fontsize=11, fontweight="bold")
fig.tight_layout()
save(fig, "f8_1_model")

# ---------------------------------------------------------------- figure 8.2 partial dependence on conflict distance
# Figure 8.2: predicted darkness vs distance from the fighting for three hull sizes (60 m, 180 m, 300 m).
grid_d = np.linspace(0, 3000, 61)
fig, ax = plt.subplots(figsize=(9, 3))
for i, (L, lab) in enumerate([(60, "60 m"), (180, "180 m (Aframax/Handymax)"), (300, "300 m (VLCC)")]):
    row = pd.DataFrame({"log_len": np.log(L), "fishing_score": 0.03, "log_dist_conflict": np.log1p(grid_d),
                        "log_conflict_500": np.log1p(np.interp(grid_d, [0, 500, 3000], [s.conflict_events_500km.quantile(0.95), 0, 0])),
                        "log_dist_choke": np.log1p(np.clip(grid_d, 50, None))})
    ax.plot(grid_d, gbm.predict_proba(row[FEATS].values)[:, 1] * 100, color=SERIES[i], label=f"hull {lab}")
ax.set_xlabel("Distance from nearest active conflict ADMIN1 (km)")
ax.set_ylabel("Predicted P(AIS-dark) %")
ax.set_ylim(0, 100)
ax.legend()
ax.set_title("Figure 8.2  Model response: darkness decays with distance from the fighting (non-fishing ships)")
save(fig, "f8_2_pdp")

# ---------------------------------------------------------------- figure 8.3 predicted dark-risk surface
# Figure 8.3: PREDICTED DARK-RISK MAP.
# Build a 0.5-degree grid over the Indian Ocean, compute the same features for a 180 m merchant ship at each
# point
# (distance to the fighting, events within 500 km, distance to a chokepoint), and ask the model for the
# probability.
a = pd.read_parquet(CLEAN / "acled_clean.parquet")
war = a[(a.WEEK >= "2026-02-28") & (a.WEEK <= "2026-03-07") & a.POLITICAL_VIOLENCE & ~a.MARITIME]
cent = war.groupby(["ID", "CENTROID_LATITUDE", "CENTROID_LONGITUDE"]).EVENTS.sum().reset_index()
tree = BallTree(np.radians(cent[["CENTROID_LATITUDE", "CENTROID_LONGITUDE"]].values), metric="haversine")
glat, glon = np.meshgrid(np.arange(-5, 32, 0.5) + 0.25, np.arange(30, 100, 0.5) + 0.25, indexing="ij")
P = np.c_[glat.ravel(), glon.ravel()]
dist, _ = tree.query(np.radians(P), k=1)
ind = tree.query_radius(np.radians(P), r=500 / 6371)
ev = np.array([cent.EVENTS.values[i].sum() for i in ind])
dch = np.min([haversine_km(P[:, 0], P[:, 1], la, lo) for la, lo in CHOKEPOINTS.values()], axis=0)
G = pd.DataFrame({"log_len": np.log(180), "fishing_score": 0.03, "log_dist_conflict": np.log1p(dist[:, 0] * 6371),
                  "log_conflict_500": np.log1p(ev), "log_dist_choke": np.log1p(dch)})
risk = gbm.predict_proba(G[FEATS].values)[:, 1].reshape(glat.shape)
fig, ax = plt.subplots(figsize=(9, 4.8))
m = basemap_ax(ax, -5, 32, 30, 100, res="l", grid=10)
pc = ax.pcolormesh(glon - 0.25, glat - 0.25, np.ma.masked_invalid(risk), cmap="Oranges", vmin=0, vmax=1, shading="auto",
                   alpha=0.85, zorder=1)
m.fillcontinents(color=C["land"], lake_color=C["sea"], zorder=2)
m.drawcoastlines(linewidth=0.35, color="#a5a39c", zorder=3)
cb = fig.colorbar(pc, ax=ax, fraction=0.025)
cb.set_label("Predicted P(AIS-dark), 180 m merchant ship")
for cp in ["Strait of Hormuz", "Bab-el-Mandeb"]:
    la, lo = CHOKEPOINTS[cp]
    ax.plot(lo, la, marker="D", color=C["blue"], ms=6, mec="white", zorder=5)
ax.set_title("Figure 8.3  Predicted AIS dark-spot surface, conflict picture of early March 2026")
save(fig, "f8_3_risk_surface")
# risk at points of interest to India
# Table 8.3: the predicted risk at places that matter to India (Hormuz, Fujairah, Mumbai, Kandla, Kochi ...).
POI = {"Strait of Hormuz": (26.5, 56.3), "Fujairah anchorage": (25.2, 56.6), "Ras Tanura": (26.7, 50.3),
       "Gulf of Aden": (12.5, 47.0), "Mumbai approaches": (18.8, 72.2), "Kandla/Mundra approaches": (22.6, 69.5),
       "Chabahar": (25.2, 60.6), "Kochi approaches": (9.9, 75.9), "Colombo": (6.9, 79.6)}
pr = []
for k, (la, lo) in POI.items():
    i, j = np.argmin(np.abs(glat[:, 0] - la)), np.argmin(np.abs(glon[0] - lo))
    pr.append((k, round(float(risk[i, j]), 2)))
pr = pd.DataFrame(pr, columns=["Location", "Predicted P(dark), 180 m ship"]).sort_values(
    "Predicted P(dark), 180 m ship", ascending=False)
table(pr, "t8_3_poi_risk")

# Headline model numbers used in the report.
put_metrics(
    model_n=len(y), auc_gbt_random=round(float(roc_auc_score(y, rnd)), 3), model_base_rate=round(float(base_rate), 3), model_best=best,
    auc_lr=float(mt.iloc[0]["ROC-AUC"]), auc_gbt=float(mt.iloc[1]["ROC-AUC"]),
    prauc_gbt=float(mt.iloc[1]["PR-AUC"]), acc_gbt=float(mt.iloc[1]["Accuracy"]), f1_gbt=float(mt.iloc[1]["F1 @0.5"]),
    or_dist=float(lt.iloc[2]["Odds ratio"]), or_events=float(lt.iloc[3]["Odds ratio"]),
    or_len=float(lt.iloc[0]["Odds ratio"]), or_fish=float(lt.iloc[1]["Odds ratio"]),
    top_feature=imp.index[-1], cm=cm.tolist(), logit_pseudo_r2=round(float(logit.prsquared), 3),
)
print(lt, "\n", mt, "\n", imp, "\n", pr, "\n", cm)
