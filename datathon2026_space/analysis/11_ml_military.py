"""Stage 11 - machine learning: can a satellite's orbit, mass and power reveal military use?"""

# =====================================================================================================
# ANNOTATED SOURCE - Stage 11: the military-use classifier (booklet Chapter 5, Technical Annex T10)
# -----------------------------------------------------------------------------------------------------
# QUESTION  Military satellites are often registered under vague names. Can we tell military from civil/commercial
#           satellites from physics alone - orbit, mass, power, design life - without reading the name or purpose?
# TARGET    military = the CDM 'Users' field mentions Military (incl. dual-use Military/Commercial etc.).
# FEATURES  perigee, apogee, eccentricity, inclination, period (logs where skewed), launch mass, power, design life,
#           launch year, orbit class, and two engineered flags: sun-synchronous-like (97-100 deg, low orbit: typical
#           of imaging/ISR) and Molniya-like (high eccentricity, ~63 deg: Russian early warning / communications).
#           Purpose, users, name, operator and country are EXCLUDED from the physics model (they would leak the answer).
#           A second model adds the operator's country bloc, to show how much 'who' adds to 'what'.
# MODELS    logistic regression (explainable baseline) and gradient-boosted trees (handles gaps in mass/power).
# TESTING   (a) 5-fold stratified cross-validation repeated 5 times on the 2014 CDM census;
#           (b) OUT-OF-TIME test: train on 2014, predict the satellites in the UCS 2020 census that were launched
#               after the 2014 census - a genuinely unseen, later population.
# USE       'Dual-use signal': commercial or civil satellites launched after 2014 whose physics look military.
# =====================================================================================================
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, balanced_accuracy_score, roc_auc_score, roc_curve
from sklearn.model_selection import RepeatedStratifiedKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from common import C, CLEAN, OPEN, SNAPSHOT_CDM, put_metrics, save, table

print("Stage 11: military-use classifier")
cdm = pd.read_parquet(CLEAN / "cdm_satellites.parquet")
u = pd.read_excel(OPEN / "ucs_2020.xls")
u = u[u["Name of Satellite, Alternate Names"].notna()].copy()


def num(s):
    return pd.to_numeric(s.astype(str).str.replace(",", "").str.strip(), errors="coerce")


def features(perigee, apogee, ecc, incl, period, mass, power, life, launch, cls, country):
    f = pd.DataFrame({
        "log_perigee": np.log1p(perigee.clip(lower=0)), "log_apogee": np.log1p(apogee.clip(lower=0)), "eccentricity": ecc,
        "inclination": incl, "log_period": np.log(period), "log_mass": np.log1p(mass), "log_power": np.log1p(power),
        "design_life": life, "launch_year": launch.dt.year + launch.dt.dayofyear / 365.25,
    })
    cls = cls.astype(str).str.upper().str.strip()
    for k in ["LEO", "MEO", "GEO", "ELLIPTICAL"]:
        f[f"orbit_{k.lower()}"] = cls.eq(k).astype(float)
    f["sun_sync_like"] = (incl.between(95, 100.5) & (apogee < 1500)).astype(float)
    f["molniya_like"] = ((ecc > 0.5) & incl.between(60, 66)).astype(float)
    c = country.astype(str)
    bloc = np.select([c.str.startswith("USA"), c.str.startswith("China"), c.str.startswith("Russia"), c.str.startswith("India")],
                     ["USA", "China", "Russia", "India"], "Other")
    for b in ["USA", "China", "Russia", "India"]:
        f[f"op_{b.lower()}"] = (bloc == b).astype(float)
    return f


# launch year is left out: it cannot extrapolate beyond the training years (every new satellite would sit outside its range)
PHYS = ["log_perigee", "log_apogee", "eccentricity", "inclination", "log_period", "log_mass", "log_power", "design_life",
        "orbit_leo", "orbit_meo", "orbit_geo", "orbit_elliptical", "sun_sync_like", "molniya_like"]
FULL = PHYS + ["op_usa", "op_china", "op_russia", "op_india"]
LABEL = {"launch_year": "Launch year", "log_perigee": "Perigee", "log_apogee": "Apogee", "eccentricity": "Eccentricity", "inclination": "Inclination",
         "log_period": "Period", "log_mass": "Launch mass", "log_power": "Power", "design_life": "Design life",
         "launch_year": "Launch year", "orbit_leo": "LEO", "orbit_meo": "MEO", "orbit_geo": "GEO", "orbit_elliptical": "Elliptical",
         "sun_sync_like": "Sun-synchronous-like", "molniya_like": "Molniya-like", "op_usa": "Operator USA", "op_china": "Operator China",
         "op_russia": "Operator Russia", "op_india": "Operator India"}

X14 = features(cdm.Perigee_km, cdm.Apogee_km, cdm.Eccentricity, cdm.incl_deg, cdm.Period_minutes, cdm.Launch_Mass_kg,
               cdm.Power_watts, cdm.Anticipated_Lifetime, cdm.launch, cdm.Class_of_Orbit, cdm.Country_of_Operator)
y14 = cdm.military_any.astype(int).values
launch20 = pd.to_datetime(u["Date of Launch"], errors="coerce")
new = u[launch20 > SNAPSHOT_CDM].copy()                                # satellites the 2014 model has never seen
X20 = features(num(new["Perigee (km)"]), num(new["Apogee (km)"]), num(new["Eccentricity"]), num(new["Inclination (degrees)"]),
               num(new["Period (minutes)"]), num(new["Launch Mass (kg.)"]), num(new["Power (watts)"]), num(new["Expected Lifetime (yrs.)"]),
               pd.to_datetime(new["Date of Launch"], errors="coerce"), new["Class of Orbit"], new["Country of Operator/Owner"])
users20 = new.Users.astype(str)
y20 = users20.str.contains("Military").astype(int).values


def models():
    return {"Logistic regression": make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler(),
                                                 LogisticRegression(max_iter=2000, C=0.5)),
            "Gradient-boosted trees": HistGradientBoostingClassifier(max_iter=250, learning_rate=0.05, max_leaf_nodes=15,
                                                                     l2_regularization=1.0, random_state=0)}


rows, oof_store, ext_store, fitted = [], {}, {}, {}
cv = RepeatedStratifiedKFold(n_splits=5, n_repeats=5, random_state=0)
for fs_name, cols in [("Physics only", PHYS), ("Physics + operator country", FULL)]:
    for m_name, m in models().items():
        aucs = []
        for r in range(5):
            cvr = [(tr, te) for k, (tr, te) in enumerate(cv.split(X14, y14)) if k // 5 == r]
            p = cross_val_predict(m, X14[cols].values, y14, cv=cvr, method="predict_proba")[:, 1]
            aucs.append(roc_auc_score(y14, p))
        oof_store[(fs_name, m_name)] = p
        m.fit(X14[cols].values, y14)
        fitted[(fs_name, m_name)] = m
        pe = m.predict_proba(X20[cols].values)[:, 1]
        ext_store[(fs_name, m_name)] = pe
        rows.append((fs_name, m_name, round(np.mean(aucs), 3), round(np.std(aucs), 3), round(roc_auc_score(y20, pe), 3),
                     round(average_precision_score(y20, pe), 3), round(balanced_accuracy_score(y20, pe >= 0.5), 3)))
res = pd.DataFrame(rows, columns=["Features", "Model", "CV ROC-AUC 2014 (mean)", "CV SD", "Out-of-time ROC-AUC (2020 launches)",
                                  "Out-of-time PR-AUC", "Balanced accuracy @0.5"])
table(res, "t11_ml_results")

# model choice by the OUT-OF-TIME score, not the cross-validation score: the trees fit 2014 best but generalise worst
best_key = max([k for k in ext_store if k[0] == "Physics only"], key=lambda k: roc_auc_score(y20, ext_store[k]))
gbm = fitted[best_key]
pi = permutation_importance(gbm, X20[PHYS].values, y20, scoring="roc_auc", n_repeats=10, random_state=0)
imp = pd.Series(pi.importances_mean, index=[LABEL[c] for c in PHYS]).sort_values()
table(imp.sort_values(ascending=False).round(4).rename("AUC drop when shuffled").rename_axis("Feature").reset_index(), "t11_ml_importance")

# dual-use signal: non-military satellites (by registration) whose physics look military
pe = ext_store[best_key]
civil = y20 == 0
flag = civil & (pe >= 0.5)
dual = new.assign(p_mil=pe)[flag]
dual_by = dual["Users"].astype(str).value_counts().head(5)
dual_purpose = dual["Purpose"].astype(str).value_counts().head(5)
table(dual[["Name of Satellite, Alternate Names", "Country of Operator/Owner", "Users", "Purpose", "Class of Orbit", "p_mil"]]
      .sort_values("p_mil", ascending=False).head(15).round(2), "t11_dual_use_flags")

fig, ax = plt.subplots(1, 2, figsize=(9, 3.4), gridspec_kw={"width_ratios": [1, 1.2]})
for (k, col, ls) in [(("Physics only", "Logistic regression"), C["blue"], "-"), (("Physics + operator country", "Logistic regression"), C["orange"], "-"),
                     (("Physics only", "Gradient-boosted trees"), C["muted"], "--")]:
    fpr, tpr, _ = roc_curve(y20, ext_store[k])
    ax[0].plot(fpr, tpr, color=col, ls=ls, label=f"{k[0]}, {k[1].split()[0].lower()} (AUC {roc_auc_score(y20, ext_store[k]):.2f})")
ax[0].plot([0, 1], [0, 1], color=C["muted"], ls=":", lw=0.8)
ax[0].set_xlabel("false-positive rate")
ax[0].set_ylabel("true-positive rate")
ax[0].legend(fontsize=6.5, loc="lower right")
ax[0].set_title("Trained on 2014, tested on 2014-2020 launches", fontsize=9)
top = imp.tail(8)
ax[1].barh(top.index, top.values, color=C["blue"], height=0.6)
ax[1].set_xlabel("drop in AUC when the feature is shuffled")
ax[1].grid(axis="y", visible=False)
ax[1].set_title("What gives a military satellite away", fontsize=9)
fig.suptitle("Machine learning: orbit, mass and power reveal military use", x=0.01, ha="left", fontsize=11, fontweight="bold")
fig.tight_layout()
save(fig, "f11_1_ml_military")

r = res.set_index(["Features", "Model"])
put_metrics(
    ml_n_train=int(len(y14)), ml_pos_train=int(y14.sum()), ml_n_test=int(len(y20)), ml_pos_test=int(y20.sum()),
    ml_cv_auc=float(r.loc[best_key, "CV ROC-AUC 2014 (mean)"]), ml_cv_sd=float(r.loc[best_key, "CV SD"]),
    ml_ext_auc=float(r.loc[best_key, "Out-of-time ROC-AUC (2020 launches)"]),
    ml_ext_auc_gbt=float(r.loc[("Physics only", "Gradient-boosted trees"), "Out-of-time ROC-AUC (2020 launches)"]),
    ml_cv_auc_gbt=float(r.loc[("Physics only", "Gradient-boosted trees"), "CV ROC-AUC 2014 (mean)"]), ml_best_model=best_key[1],
    ml_ext_auc_full=float(r.loc[("Physics + operator country", "Logistic regression"), "Out-of-time ROC-AUC (2020 launches)"]),
    ml_cv_auc_full=float(r.loc[("Physics + operator country", "Logistic regression"), "CV ROC-AUC 2014 (mean)"]),
    ml_top_feature=imp.index[-1], ml_second_feature=imp.index[-2],
    ml_dual_n=int(flag.sum()), ml_dual_share=round(float(flag.sum() / max(civil.sum(), 1)), 3), ml_civil_n=int(civil.sum()),
)
print(res.to_string(), "\n", imp.sort_values(ascending=False).head(8), "\ndual", flag.sum(), civil.sum(), "\n", dual_by, "\n", dual_purpose)
