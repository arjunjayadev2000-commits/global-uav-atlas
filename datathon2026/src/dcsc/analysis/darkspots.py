"""Detection of AIS dark spots - where the radar picture and the AIS picture disagree.

Method
------
The question is not "where are there many dark ships" (that is mostly a map of
where there are many ships, and of where Sentinel-1 happens to look), but "where
are ships *darker than they should be*, given what kind of ships they are".

That is a classic indirect-standardisation problem, so it is solved the way
epidemiology solves it:

1. Compute a global dark rate for every vessel length class - the reference rates.
2. For each 0.5-degree cell, compute the **expected** number of dark detections
   as ``sum_over_classes(n_cell_class * global_rate_class)``.
3. The **standardised dark ratio** ``SDR = observed / expected`` is then free of
   the cell's size mix. SDR = 1 means "exactly as dark as this traffic mix is
   worldwide"; SDR = 4 means four times darker than its own traffic mix explains.
4. Significance comes from a one-sided binomial test against the cell's expected
   rate, with Benjamini-Hochberg control of the false discovery rate, because
   several thousand cells are tested at once and uncorrected p-values would
   produce dozens of spurious 'dark spots'.

A second, independent view clusters the dark detections themselves with DBSCAN
on the haversine metric. The grid answers "which cells are anomalous"; the
clusters answer "what contiguous operating areas do the dark ships form".
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.cluster import DBSCAN

from ..config import SETTINGS
from ..features.geo import EARTH_RADIUS_KM, add_grid, haversine_km, wilson_interval
from ..io_utils import get_logger, save_table

LOG = get_logger("dcsc.analysis.darkspots")


def reference_rates(det: pd.DataFrame, strata_col: str = "length_class") -> pd.Series:
    """Global dark rate per length class - the reference population."""
    rates = det.groupby(strata_col, observed=True)["is_dark"].mean()
    LOG.info(
        "reference dark rates: %s",
        ", ".join(f"{k}={v:.3f}" for k, v in rates.items()),
    )
    return rates


def dark_rate_surface(
    det: pd.DataFrame,
    deg: float | None = None,
    min_detections: int | None = None,
) -> pd.DataFrame:
    """Per-cell dark statistics with indirect standardisation and FDR control."""
    deg = deg or SETTINGS.grid_deg
    min_detections = min_detections or SETTINGS.min_cell_detections

    gridded = add_grid(det, deg=deg)
    rates = reference_rates(gridded)
    gridded = gridded.assign(
        expected_dark=gridded["length_class"].map(rates).astype(float),
        solas_dark_flag=gridded["is_large"] & gridded["is_dark"],
    )

    cells = (
        gridded.groupby(["cell_id", "cell_lat", "cell_lon"], observed=True)
        .agg(
            detections=("detection_id", "size"),
            dark=("is_dark", "sum"),
            expected=("expected_dark", "sum"),
            solas=("is_large", "sum"),
            solas_dark=("solas_dark_flag", "sum"),
            mean_length_m=("length_m", "mean"),
            fishing_share=("likely_fishing", "mean"),
            cell_area_km2=("cell_area_km2", "first"),
            scenes=("scene_id", "nunique"),
            corridor=("chokepoint", lambda s: s.mode().iat[0] if len(s.mode()) else "Open ocean"),
        )
        .reset_index()
    )
    cells = cells[cells["detections"] >= min_detections].copy()

    cells["dark_rate"] = cells["dark"] / cells["detections"]
    cells["expected_rate"] = cells["expected"] / cells["detections"]
    cells["sdr"] = cells["dark"] / cells["expected"].replace(0, np.nan)
    cells["excess_dark"] = cells["dark"] - cells["expected"]
    cells["density_per_1k_km2"] = cells["detections"] / cells["cell_area_km2"] * 1e3
    cells["solas_dark_rate"] = cells["solas_dark"] / cells["solas"].replace(0, np.nan)

    lo, hi = wilson_interval(cells["dark"].to_numpy(), cells["detections"].to_numpy())
    cells["dark_rate_lo"] = lo
    cells["dark_rate_hi"] = hi

    # One-sided exact binomial test: is this cell darker than its own traffic mix
    # predicts? sf(k-1) gives P(X >= k).
    cells["p_value"] = stats.binom.sf(
        cells["dark"].to_numpy() - 1,
        cells["detections"].to_numpy(),
        np.clip(cells["expected_rate"].to_numpy(), 1e-9, 1 - 1e-9),
    )
    cells["q_value"] = _benjamini_hochberg(cells["p_value"].to_numpy())
    cells["is_dark_spot"] = (cells["q_value"] < 0.05) & (cells["sdr"] >= 1.5)

    LOG.info(
        "grid cells tested=%d  dark spots (q<0.05 and SDR>=1.5)=%d",
        len(cells),
        int(cells["is_dark_spot"].sum()),
    )
    return cells.sort_values("sdr", ascending=False).reset_index(drop=True)


def _benjamini_hochberg(p: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg adjusted p-values (q-values)."""
    n = len(p)
    order = np.argsort(p)
    ranked = p[order] * n / (np.arange(n) + 1)
    # Enforce monotonicity from the largest p downwards.
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    q = np.empty(n, dtype=float)
    q[order] = np.clip(ranked, 0, 1)
    return q


def cluster_dark_detections(
    det: pd.DataFrame,
    eps_km: float | None = None,
    min_samples: int | None = None,
    solas_only: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cluster dark detections into contiguous dark operating areas.

    Restricted to SOLAS-class hulls by default: clustering every small craft
    would simply rediscover the world's fishing grounds, which is a different
    (and already well-known) phenomenon.
    """
    eps_km = eps_km or SETTINGS.dbscan_eps_km
    min_samples = min_samples or SETTINGS.dbscan_min_samples

    dark = det[det["is_dark"]]
    if solas_only:
        dark = dark[dark["length_m"] >= 100.0]
    dark = dark.copy()
    LOG.info("clustering %d dark detections (eps=%.0f km, min_samples=%d)", len(dark), eps_km, min_samples)

    coords = np.radians(dark[["lat", "lon"]].to_numpy())
    model = DBSCAN(
        eps=eps_km / EARTH_RADIUS_KM,
        min_samples=min_samples,
        metric="haversine",
        algorithm="ball_tree",
    )
    dark["cluster"] = model.fit_predict(coords)

    clustered = dark[dark["cluster"] >= 0]
    summary = (
        clustered.groupby("cluster")
        .agg(
            dark_detections=("detection_id", "size"),
            centre_lat=("lat", "mean"),
            centre_lon=("lon", "mean"),
            mean_length_m=("length_m", "mean"),
            max_length_m=("length_m", "max"),
            first_seen=("timestamp", "min"),
            last_seen=("timestamp", "max"),
            corridor=("chokepoint", lambda s: s.mode().iat[0] if len(s.mode()) else "Open ocean"),
            theatre=("theatre", lambda s: s.mode().iat[0] if len(s.mode()) else "Other"),
            no_candidate_share=("dark_class", lambda s: float((s == "dark_no_candidate").mean())),
        )
        .reset_index()
    )
    # Spatial extent: radius containing every member, a proxy for whether the
    # cluster is a holding area (tight) or a transit lane (elongated).
    radii = []
    for cid, grp in clustered.groupby("cluster"):
        d = haversine_km(
            grp["lat"].to_numpy(),
            grp["lon"].to_numpy(),
            grp["lat"].mean(),
            grp["lon"].mean(),
        )
        radii.append({"cluster": cid, "radius_p90_km": float(np.percentile(d, 90))})
    summary = summary.merge(pd.DataFrame(radii), on="cluster")

    # Local dark share: of ALL detections near the cluster centre, how many were dark?
    shares = []
    for row in summary.itertuples():
        d = haversine_km(det["lat"].to_numpy(), det["lon"].to_numpy(), row.centre_lat, row.centre_lon)
        near = det[d <= max(row.radius_p90_km, 25.0)]
        solas_near = near[near["length_m"] >= 100.0]
        shares.append(
            {
                "cluster": row.cluster,
                "local_detections": len(near),
                "local_solas_dark_rate": float(solas_near["is_dark"].mean())
                if len(solas_near)
                else np.nan,
            }
        )
    summary = summary.merge(pd.DataFrame(shares), on="cluster")

    LOG.info(
        "dark clusters=%d covering %d detections (%.0f%% of dark SOLAS traffic)",
        len(summary),
        int(summary["dark_detections"].sum()),
        100 * summary["dark_detections"].sum() / max(len(dark), 1),
    )
    return summary.sort_values("dark_detections", ascending=False).reset_index(drop=True), dark


def classify_areas(cells: pd.DataFrame, min_detections: int = 25) -> pd.DataFrame:
    """Separate AIS *dead zones* from AIS *dark behaviour*.

    The theme asks for AIS dead zones and for dark spots, and they are not the
    same thing. Both look identical in a dark-rate map, but they have opposite
    operational meanings, and the detection data itself can tell them apart:

    * A **dead zone** is a hole in the AIS picture - no terrestrial receiver in
      range, no satellite pass correlated, or a feed outage. Reception failure is
      indiscriminate: *nothing* in the cell matches, across every size class. A
      cell where 100% of detections are dark is far more likely to be a receiver
      or feed gap than a fleet that switched off in perfect unison.
    * A **behavioural dark spot** is deliberate. Some ships in the cell match
      perfectly well - which proves the AIS picture reaches that water - while
      others, typically the large ones, do not. Selective darkness is the
      signature.

    The discriminator is therefore the presence of matched traffic in the same
    cell, combined with whether darkness is concentrated in the SOLAS classes.
    """
    out = cells.copy()
    out["matched"] = out["detections"] - out["dark"]
    out["matched_share"] = out["matched"] / out["detections"]

    enough = out["detections"] >= min_detections
    blackout = out["dark_rate"] >= 0.97

    # A blackout that also swallows the large hulls cannot be explained by
    # carriage rules, so it is a reception or feed failure.
    dead_zone = enough & blackout & (out["sdr"] >= 2.0)

    # A blackout of an entirely small-craft population is the expected state:
    # those hulls are below the SOLAS carriage threshold and were never obliged
    # to transmit. Calling this a 'dark spot' would be a false positive.
    non_carriage = (
        enough
        & (out["dark_rate"] >= 0.85)
        & (out["sdr"] < 1.5)
        & (out["mean_length_m"] < 45.0)
    )

    # Selective darkness: the AIS picture demonstrably reaches this water (some
    # ships match) and the large hulls are the ones missing from it.
    selective = (
        enough
        & (out["sdr"] >= 1.5)
        & (out["q_value"] < 0.05)
        & (out["matched_share"] >= 0.05)
        & (out["solas_dark_rate"].fillna(0) >= 0.35)
    )

    out["area_type"] = np.select(
        [dead_zone, non_carriage, selective, enough & blackout, out["q_value"] < 0.05],
        [
            "AIS dead zone (reception / feed gap)",
            "Non-carriage area (small craft, AIS not required)",
            "Behavioural dark spot (selective switch-off)",
            "Blackout, cause unresolved",
            "Elevated dark, unclassified",
        ],
        default="Normal",
    )
    LOG.info("area typology: %s", out["area_type"].value_counts().to_dict())
    return out


def persistence(det: pd.DataFrame, cells: pd.DataFrame, deg: float | None = None) -> pd.DataFrame:
    """How many distinct days each flagged cell was observed dark.

    A cell that is dark on one satellite pass may be one convoy; a cell dark on
    nine days out of fourteen is a standing condition, and only the second kind
    is worth planning against.
    """
    deg = deg or SETTINGS.grid_deg
    gridded = add_grid(det, deg=deg)
    daily = (
        gridded.groupby(["cell_id", "date"], observed=True)
        .agg(detections=("detection_id", "size"), dark=("is_dark", "sum"))
        .reset_index()
    )
    daily["dark_rate_day"] = daily["dark"] / daily["detections"]
    agg = (
        daily.groupby("cell_id")
        .agg(
            days_observed=("date", "nunique"),
            days_dark_majority=("dark_rate_day", lambda s: int((s >= 0.5).sum())),
        )
        .reset_index()
    )
    agg["persistence"] = agg["days_dark_majority"] / agg["days_observed"]
    return cells.merge(agg, on="cell_id", how="left")


def sensitivity(det: pd.DataFrame) -> pd.DataFrame:
    """Re-run the corridor dark rate under alternative dark definitions.

    A result that survives all three definitions is a finding; one that only
    appears under the loosest definition is an artefact of the threshold.
    """
    rows = []
    for label, col, subset in (
        ("provider label (headline)", "is_dark", det),
        ("provider label, SOLAS class only", "is_dark", det[det["length_m"] >= 100.0]),
        ("provider label + weak matches", "is_dark_strict", det),
        (
            "no AIS candidate at all",
            "dark_no_candidate_flag",
            det.assign(dark_no_candidate_flag=det["dark_class"].eq("dark_no_candidate")),
        ),
    ):
        grp = (
            subset.groupby("chokepoint", observed=True)
            .agg(detections=(col, "size"), dark=(col, "sum"))
            .reset_index()
        )
        grp["definition"] = label
        grp["dark_rate"] = grp["dark"] / grp["detections"]
        rows.append(grp)
    out = pd.concat(rows, ignore_index=True)
    return out.pivot_table(
        index="chokepoint", columns="definition", values="dark_rate"
    ).reset_index()


def run(det: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Full dark-spot analysis; writes every table it produces."""
    surface = dark_rate_surface(det)
    surface = classify_areas(surface)
    surface = persistence(det, surface)
    clusters, labelled = cluster_dark_detections(det)
    sens = sensitivity(det)

    save_table(surface, "darkspot_grid_cells")
    save_table(surface[surface["is_dark_spot"]].head(200), "darkspot_top_cells")
    save_table(clusters, "darkspot_clusters")
    save_table(sens, "darkspot_sensitivity")
    return {"surface": surface, "clusters": clusters, "sensitivity": sens, "labelled": labelled}
