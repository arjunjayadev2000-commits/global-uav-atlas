"""Predicting where AIS goes dark.

The theme asks not only for dark spots that have already happened but for the
ability to anticipate them. This module fits a classifier on the 0.5-degree cell
surface: given what kind of traffic a patch of sea carries, where it sits, and
how much conflict has occurred near it, how likely is that patch to be a
*behavioural* dark spot - selective AIS switch-off among ships that are legally
required to transmit?

Validation is **spatially blocked**. Ordinary k-fold cross-validation on gridded
geodata is self-deception: neighbouring cells are near-duplicates, so a random
split leaves half of every dark spot in the training set and the score measures
memorisation. Folds here are whole 5-degree blocks, so the model is always scored
on water it has never seen.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupKFold

from ..config import SETTINGS, load_chokepoints
from ..features.geo import haversine_km
from ..io_utils import get_logger, save_table

LOG = get_logger("dcsc.analysis.predict")

FEATURES = [
    "log_detections",
    "mean_length_m",
    "fishing_share",
    "solas_share",
    "density_per_1k_km2",
    "abs_lat",
    "dist_critical_km",
    "conflict_events_300km",
    "conflict_nearest_km",
    "scenes",
]


def build_cell_features(cells: pd.DataFrame, det_exposed: pd.DataFrame) -> pd.DataFrame:
    """Assemble the modelling frame at cell level."""
    conflict_cols = ["conflict_events_300km", "conflict_nearest_km"]
    from ..features.geo import add_grid

    gridded = add_grid(det_exposed, deg=SETTINGS.grid_deg)
    per_cell = (
        gridded.groupby("cell_id", observed=True)[conflict_cols].mean().reset_index()
    )

    df = cells.merge(per_cell, on="cell_id", how="left")
    df["log_detections"] = np.log(df["detections"])
    df["solas_share"] = df["solas"] / df["detections"]
    df["abs_lat"] = df["cell_lat"].abs()

    criticals = [cp for cp in load_chokepoints() if cp.critical]
    dists = np.vstack(
        [
            haversine_km(
                df["cell_lat"].to_numpy(),
                df["cell_lon"].to_numpy(),
                np.clip(df["cell_lat"].to_numpy(), cp.lat_min, cp.lat_max),
                np.clip(df["cell_lon"].to_numpy(), cp.lon_min, cp.lon_max),
            )
            for cp in criticals
        ]
    )
    df["dist_critical_km"] = dists.min(axis=0)

    df["target"] = df["area_type"].eq("Behavioural dark spot (selective switch-off)").astype(int)
    # Spatial blocks of 5 degrees are the cross-validation groups.
    df["block"] = (
        (np.floor(df["cell_lat"] / 5) * 5).astype(int).astype(str)
        + "_"
        + (np.floor(df["cell_lon"] / 5) * 5).astype(int).astype(str)
    )
    return df.dropna(subset=FEATURES).reset_index(drop=True)


def spatial_cv(df: pd.DataFrame, n_splits: int = 5) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Spatially blocked cross-validation; returns fold scores and out-of-fold predictions."""
    X = df[FEATURES].to_numpy()
    y = df["target"].to_numpy()
    groups = df["block"].to_numpy()

    oof = np.full(len(df), np.nan)
    rows = []
    splitter = GroupKFold(n_splits=n_splits)
    for fold, (train_idx, test_idx) in enumerate(splitter.split(X, y, groups), start=1):
        if y[train_idx].sum() == 0 or y[test_idx].sum() == 0:
            LOG.warning("fold %d has no positives on one side; skipped", fold)
            continue
        model = GradientBoostingClassifier(
            n_estimators=250,
            max_depth=3,
            learning_rate=0.05,
            subsample=0.9,
            random_state=SETTINGS.random_state,
        )
        model.fit(X[train_idx], y[train_idx])
        proba = model.predict_proba(X[test_idx])[:, 1]
        oof[test_idx] = proba
        rows.append(
            {
                "fold": fold,
                "n_train": len(train_idx),
                "n_test": len(test_idx),
                "positives_test": int(y[test_idx].sum()),
                "roc_auc": roc_auc_score(y[test_idx], proba),
                "pr_auc": average_precision_score(y[test_idx], proba),
                "base_rate": float(y[test_idx].mean()),
            }
        )
    scores = pd.DataFrame(rows)
    mask = ~np.isnan(oof)
    overall = {
        "fold": "overall (out-of-fold)",
        "n_train": np.nan,
        "n_test": int(mask.sum()),
        "positives_test": int(y[mask].sum()),
        "roc_auc": roc_auc_score(y[mask], oof[mask]),
        "pr_auc": average_precision_score(y[mask], oof[mask]),
        "base_rate": float(y[mask].mean()),
    }
    scores = pd.concat([scores, pd.DataFrame([overall])], ignore_index=True)
    LOG.info(
        "dark-spot classifier: out-of-fold ROC-AUC=%.3f PR-AUC=%.3f (base rate %.3f)",
        overall["roc_auc"],
        overall["pr_auc"],
        overall["base_rate"],
    )
    out = df.copy()
    out["oof_probability"] = oof
    return scores, out


def fit_full(df: pd.DataFrame) -> tuple[GradientBoostingClassifier, pd.DataFrame]:
    """Refit on everything and report both split-gain and permutation importance."""
    X = df[FEATURES]
    y = df["target"]
    model = GradientBoostingClassifier(
        n_estimators=250,
        max_depth=3,
        learning_rate=0.05,
        subsample=0.9,
        random_state=SETTINGS.random_state,
    ).fit(X, y)

    perm = permutation_importance(
        model, X, y, n_repeats=15, random_state=SETTINGS.random_state, scoring="roc_auc"
    )
    imp = pd.DataFrame(
        {
            "feature": FEATURES,
            "gain_importance": model.feature_importances_,
            "permutation_importance": perm.importances_mean,
            "permutation_std": perm.importances_std,
        }
    ).sort_values("permutation_importance", ascending=False)
    return model, imp.reset_index(drop=True)


def run(cells: pd.DataFrame, det_exposed: pd.DataFrame) -> dict:
    df = build_cell_features(cells, det_exposed)
    LOG.info("modelling frame: %d cells, %d positives", len(df), int(df["target"].sum()))
    scores, oof = spatial_cv(df)
    model, importance = fit_full(df)
    oof["risk_probability"] = model.predict_proba(df[FEATURES])[:, 1]

    save_table(scores, "darkspot_model_cv_scores")
    save_table(importance, "darkspot_model_importance")
    save_table(
        oof[
            [
                "cell_id",
                "cell_lat",
                "cell_lon",
                "corridor",
                "detections",
                "dark_rate",
                "sdr",
                "area_type",
                "target",
                "oof_probability",
                "risk_probability",
            ]
        ],
        "darkspot_model_predictions",
    )
    return {"frame": df, "scores": scores, "importance": importance, "predictions": oof, "model": model}
