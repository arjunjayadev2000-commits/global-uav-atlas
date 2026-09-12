"""Does conflict actually drive the maritime signal? Three independent tests.

1. **Detection-level logistic regression.** For every SOLAS-class radar contact,
   is the probability that it is dark related to how much conflict has happened
   near it in the preceding 30 days, once hull size and vessel type are held
   constant? This is the strongest of the three because it uses 40,000
   observations rather than 25 corridor averages, and because the controls it
   needs (size, fishing behaviour) are measured on the same row.

2. **Corridor cross-section.** Rank correlation and OLS between corridor conflict
   pressure and corridor dark rate. Few observations, but it is the level at
   which a commander actually makes decisions, and it is trivially auditable.

3. **Historical lead-lag.** Within the conflict data alone, does violence ashore
   lead attacks at sea? A cross-correlation over 2015-2026 of littoral conflict
   against ACLED's own maritime-domain events gives the warning time available
   between a land campaign intensifying and shipping being attacked.

Every test reports an effect size, not only a p-value: with 40,000 detections
almost anything is 'significant', and the operationally meaningful question is
how much the odds of a dark ship actually move.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

from ..features.geo import haversine_km
from ..io_utils import get_logger, save_table

LOG = get_logger("dcsc.analysis.coupling")


def conflict_exposure_for_detections(
    det: pd.DataFrame,
    conflict: pd.DataFrame,
    lookback_days: int = 30,
    radii_km: tuple[float, ...] = (150.0, 300.0, 600.0),
) -> pd.DataFrame:
    """Attach recent conflict intensity to every detection.

    Conflict is located at ACLED admin-unit centroids, so the exposure measure is
    deliberately coarse-grained (hundreds of km, not tens). That is a real
    limitation of the source and it is why the radii are wide.
    """
    window_start = pd.Timestamp(det["timestamp"].min()).tz_localize(None) - pd.Timedelta(
        days=lookback_days
    )
    window_end = pd.Timestamp(det["timestamp"].max()).tz_localize(None)
    recent = conflict[(conflict["week"] >= window_start) & (conflict["week"] <= window_end)]

    units = (
        recent.groupby(["admin_id", "lat", "lon"], observed=True)
        .agg(events=("events", "sum"), fatalities=("fatalities", "sum"))
        .reset_index()
    )
    LOG.info(
        "conflict exposure window %s..%s: %d admin units, %d events",
        window_start.date(),
        window_end.date(),
        len(units),
        int(units["events"].sum()),
    )

    out = det.copy()
    ulat = units["lat"].to_numpy()
    ulon = units["lon"].to_numpy()
    uev = units["events"].to_numpy(dtype=float)
    ufat = units["fatalities"].to_numpy(dtype=float)

    nearest = np.full(len(out), np.nan)
    counts = {r: np.zeros(len(out)) for r in radii_km}
    fatal = np.zeros(len(out))

    # Chunked so the 105k x 250 distance matrix never has to exist at once.
    lat = out["lat"].to_numpy()
    lon = out["lon"].to_numpy()
    chunk = 5000
    for start in range(0, len(out), chunk):
        stop = min(start + chunk, len(out))
        d = haversine_km(lat[start:stop, None], lon[start:stop, None], ulat[None, :], ulon[None, :])
        nearest[start:stop] = d.min(axis=1)
        for r in radii_km:
            counts[r][start:stop] = (d <= r) @ uev
        fatal[start:stop] = (d <= 300.0) @ ufat

    out["conflict_nearest_km"] = nearest
    for r in radii_km:
        out[f"conflict_events_{int(r)}km"] = counts[r]
    out["conflict_fatalities_300km"] = fatal
    out["conflict_log_300km"] = np.log1p(out["conflict_events_300km"])
    return out


def detection_logit(det_exposed: pd.DataFrame) -> tuple[pd.DataFrame, object]:
    """Logistic model of P(dark) on conflict exposure, controlling for the hull.

    Fitted on SOLAS-class detections only, where AIS carriage is mandatory, so
    the outcome means "a ship that should have been transmitting was not".
    Standard errors are clustered on the 0.5-degree cell, because detections in
    the same water on the same pass are anything but independent.
    """
    df = det_exposed[det_exposed["length_m"] >= 100.0].copy()
    df["log_length"] = np.log(df["length_m"])
    df["cell_key"] = (
        (np.floor(df["lat"] * 2) / 2).astype(str) + "_" + (np.floor(df["lon"] * 2) / 2).astype(str)
    )

    X = pd.DataFrame(
        {
            "log_length": df["log_length"],
            "fishing_score": df["fishing_score"],
            "conflict_log_300km": df["conflict_log_300km"],
            "near_conflict_150km": (df["conflict_nearest_km"] <= 150).astype(float),
            "ascending_pass": (df["pass_direction"] == "ascending").astype(float),
        }
    )
    X = sm.add_constant(X)
    y = df["is_dark"].astype(int)

    model = sm.Logit(y, X).fit(disp=False, cov_type="cluster", cov_kwds={"groups": df["cell_key"]})
    summary = pd.DataFrame(
        {
            "term": model.params.index,
            "coef": model.params.to_numpy(),
            "std_err": model.bse.to_numpy(),
            "z": model.tvalues.to_numpy(),
            "p_value": model.pvalues.to_numpy(),
            "odds_ratio": np.exp(model.params.to_numpy()),
            "or_lo": np.exp(model.conf_int()[0].to_numpy()),
            "or_hi": np.exp(model.conf_int()[1].to_numpy()),
        }
    )
    summary.attrs["n"] = len(df)
    summary.attrs["pseudo_r2"] = float(model.prsquared)
    LOG.info(
        "detection logit: n=%d pseudo-R2=%.3f  conflict OR=%.3f (p=%.3g)",
        len(df),
        model.prsquared,
        float(np.exp(model.params["conflict_log_300km"])),
        float(model.pvalues["conflict_log_300km"]),
    )
    return summary, model


def corridor_cross_section(
    profile: pd.DataFrame, pressure: pd.DataFrame, window: tuple[str, str]
) -> tuple[pd.DataFrame, dict]:
    """Corridor-level association between conflict pressure and dark rate."""
    start, end = window
    recent = pressure[(pressure["week"] >= start) & (pressure["week"] <= end)]
    agg = (
        recent.groupby("chokepoint_id", observed=True)
        .agg(
            conflict_events=("events_within", "sum"),
            threat_events=("threat_events", "sum"),
            conflict_weighted=("events_weighted", "sum"),
        )
        .reset_index()
    )
    merged = profile.merge(agg, on="chokepoint_id", how="left").fillna(
        {"conflict_events": 0, "threat_events": 0, "conflict_weighted": 0.0}
    )
    merged = merged[(merged["solas_detections"] >= 50) & (merged["chokepoint_id"] != "open_ocean")]
    merged["log_conflict"] = np.log1p(merged["conflict_events"])
    merged["log_traffic"] = np.log(merged["solas_detections"])

    rho, p_rho = stats.spearmanr(merged["conflict_events"], merged["solas_dark_rate"])
    X = sm.add_constant(merged[["log_conflict", "log_traffic"]])
    ols = sm.OLS(merged["solas_dark_rate"], X).fit(cov_type="HC3")

    stats_out = {
        "n_corridors": len(merged),
        "spearman_rho": float(rho),
        "spearman_p": float(p_rho),
        "ols_log_conflict_coef": float(ols.params["log_conflict"]),
        "ols_log_conflict_p": float(ols.pvalues["log_conflict"]),
        "ols_r2": float(ols.rsquared),
    }
    LOG.info("corridor cross-section: %s", stats_out)
    return merged, stats_out


def lead_lag(conflict: pd.DataFrame, max_lag: int = 10) -> pd.DataFrame:
    """Cross-correlation between littoral land violence and attacks at sea.

    Positive lag means land violence *leads* maritime attacks by that many weeks,
    which is the quantity a warning system needs.
    """
    from ..features.conflict_features import MARITIME_ADMIN1

    sea = (
        conflict[conflict["admin1"].isin(MARITIME_ADMIN1)]
        .groupby("week", observed=True)["events"]
        .sum()
        .rename("maritime_events")
    )
    littoral_countries = ("Yemen", "Israel", "Palestine", "Lebanon", "Iran", "Egypt", "Turkey")
    land = (
        conflict[conflict["country"].isin(littoral_countries) & ~conflict["admin1"].isin(MARITIME_ADMIN1)]
        .groupby("week", observed=True)["events"]
        .sum()
        .rename("littoral_events")
    )
    joined = pd.concat([sea, land], axis=1, sort=True).fillna(0.0).sort_index()
    joined = joined[joined.index >= "2019-01-01"]

    rows = []
    for lag in range(-max_lag, max_lag + 1):
        shifted = joined["littoral_events"].shift(lag)
        mask = shifted.notna()
        if mask.sum() < 30:
            continue
        r, p = stats.pearsonr(joined.loc[mask, "maritime_events"], shifted[mask])
        rows.append({"lag_weeks": lag, "correlation": r, "p_value": p})
    out = pd.DataFrame(rows)
    best = out.loc[out["correlation"].idxmax()]
    LOG.info(
        "lead-lag peak: land violence leads maritime attacks by %d weeks (r=%.3f)",
        int(best["lag_weeks"]),
        best["correlation"],
    )
    return out


def run(
    det: pd.DataFrame,
    conflict: pd.DataFrame,
    profile: pd.DataFrame,
    pressure: pd.DataFrame,
) -> dict:
    exposed = conflict_exposure_for_detections(det, conflict)
    logit_summary, _ = detection_logit(exposed)
    cross, cross_stats = corridor_cross_section(profile, pressure, ("2026-02-01", "2026-03-31"))
    ll = lead_lag(conflict)

    save_table(logit_summary, "coupling_detection_logit")
    save_table(cross, "coupling_corridor_cross_section")
    save_table(ll, "coupling_lead_lag")
    return {
        "exposed": exposed,
        "logit": logit_summary,
        "cross": cross,
        "cross_stats": cross_stats,
        "lead_lag": ll,
    }
