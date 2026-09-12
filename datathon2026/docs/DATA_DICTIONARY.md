# Data dictionary

Every column the pipeline reads or creates. Supplied fields are marked **(raw)**;
everything else is derived, with the rule that derives it.

---

## 1. Conflict dataset

`data/raw/acled_middle_east_weekly_2026-06-27.xlsx` → `data/interim/conflict_weekly.parquet`

One row per **week × country × admin1 × event type × sub-event type**.
149,825 rows, 601 weeks (27 Dec 2014 – 27 Jun 2026), 17 countries and sea areas.

| Column | Type | Source | Meaning |
|---|---|---|---|
| `week` | datetime | **(raw)** `WEEK` | Week-ending date (Saturday) |
| `region` | string | **(raw)** `REGION` | Always "Middle East" in this extract |
| `country` | string | **(raw)** `COUNTRY` | Country, or a **sea area**: "Indian Ocean", "Mediterranean Sea" |
| `admin1` | string | **(raw)** `ADMIN1` | First-level admin unit, or a sea area name |
| `event_type` | string | **(raw)** `EVENT_TYPE` | Battles, Explosions/Remote violence, Protests, Riots, Strategic developments, Violence against civilians |
| `sub_event_type` | string | **(raw)** `SUB_EVENT_TYPE` | 37 values, including "Air/drone strike" and "Disrupted weapons use" (intercepted munitions) |
| `events` | int | **(raw)** `EVENTS` | Event count for the row |
| `fatalities` | int | **(raw)** `FATALITIES` | Reported fatalities |
| `population_exposure` | int | **(raw)** `POPULATION_EXPOSURE` | Population of the affected admin unit |
| `disorder_type` | string | **(raw)** `DISORDER_TYPE` | Political violence, Demonstrations, Strategic developments |
| `admin_id` | int | **(raw)** `ID` | Admin-unit identifier; the join key to the corridor bridge |
| `lat` / `lon` | float | **(raw)** centroids | **Admin-unit centroid, not event location.** Accurate to hundreds of km |
| `zero_event_row` | bool | derived | `events <= 0`; flagged, never deleted |
| `year`, `month`, `iso_week` | — | derived from `week` | Calendar keys |
| `fatalities_per_event` | float | derived | Lethality; guarded against divide-by-zero |

## 2. SAR detection dataset

`data/raw/sar_vessel_detections_2026-03.csv` → `data/interim/sar_detections.parquet`

One row per radar contact. 107,257 raw → **104,840** after quality gates.
2,830 Sentinel-1 scenes, worldwide, 1–14 Mar 2026.

| Column | Type | Source | Meaning |
|---|---|---|---|
| `scene_id` | string | **(raw)** | Sentinel-1 IW GRDH scene identifier; encodes platform and acquisition time |
| `timestamp` | datetime (UTC) | **(raw)** | Acquisition instant |
| `lat` / `lon` | float | **(raw)** | Detection position |
| `presence_score` | float | **(raw)** | Model confidence that the return is a vessel. Gated at ≥ 0.90 |
| `length_m` | float | **(raw)** | Radar-estimated vessel length. Gated at ≥ 10 m |
| `mmsi` | float | **(raw)** | *Candidate* AIS identity. Null = no candidate existed |
| `matching_score` | float | **(raw)** | Strength of the SAR↔AIS correlation. 0 where no candidate |
| `fishing_score` | float | **(raw)** | Model score for fishing-like behaviour |
| `matched_category` | string | **(raw)** | **The provider's adjudication.** `unmatched` = match rejected; otherwise cargo, fishing, bunker, carrier, passenger, seismic_vessel, gear, noisy_vessel, other |
| `has_mmsi` | bool | derived | `mmsi` is not null |
| **`is_dark`** | bool | derived | **`matched_category == "unmatched"`. The headline definition** |
| `weak_match` | bool | derived | Accepted match whose `matching_score` < 1.0 |
| `is_dark_strict` | bool | derived | `is_dark OR weak_match`. Sensitivity definition |
| `dark_class` | string | derived | `dark_no_candidate`, `dark_rejected_candidate`, `matched_weak`, `matched_strong` |
| `mid` | string | derived | First three MMSI digits (maritime identification digits = flag) where present |
| `length_class` | category | derived | Six bands; boundaries 25 / 50 / 100 / 160 / 250 m |
| `is_large` | bool | derived | `length_m >= 100`. The SOLAS-class proxy |
| `likely_fishing` | bool | derived | `fishing_score >= 0.5` |
| `date`, `hour_utc` | — | derived | Calendar keys |
| `pass_direction` | string | derived | ascending / descending, inferred from acquisition hour. Guards against reading an orbit artefact as behaviour |
| `detection_id` | int | derived | Stable surrogate key |
| `chokepoint_id`, `chokepoint`, `theatre` | string | derived | Corridor assignment from `config/chokepoints.json`, priority-ordered so narrow straits claim a point before the basin around them |

## 3. Principal derived tables

All in `outputs/tables/`. One CSV behind every figure and every number in the report.

| Table | Grain | Key columns |
|---|---|---|
| `headline_numbers` | one row per headline metric | metric, value, definition |
| `darkspot_grid_cells` | 0.5° cell | `detections`, `dark`, `expected`, **`sdr`**, `dark_rate_lo/hi` (Wilson), `p_value`, `q_value` (BH), `is_dark_spot`, **`area_type`**, `persistence` |
| `darkspot_clusters` | DBSCAN cluster | `dark_detections`, centre, `radius_p90_km`, `local_solas_dark_rate`, `no_candidate_share` |
| `darkspot_sensitivity` | corridor | dark rate under each of the four definitions |
| `corridor_throughput_deficit` | corridor | `solas_per_scene`, `throughput_ratio`, `deficit_pct` |
| `route_suez_vs_cape` | route | `solas_per_scene`, `commercial_per_scene` |
| `coupling_detection_logit` | model term | `coef`, `odds_ratio`, `or_lo/hi`, `p_value` |
| `coupling_lead_lag` | lag (−10…+10 weeks) | `correlation`, `p_value` |
| `darkspot_model_cv_scores` | spatial fold | `roc_auc`, `pr_auc`, `base_rate` |
| `darkspot_model_importance` | feature | `gain_importance`, `permutation_importance` ± sd |
| `forecast_backtest_scores` | corridor × model | `mae`, `rmse`, `mape`, `bias`, `skill_vs_naive_pct` |
| `forecast_corridor_12w` | corridor × week | `forecast`, `lower`, `upper`, `model` |
| `risk_index_msri` | corridor | five components, `msri`, `tier`, `india_dependency`, `india_exposure` |

## 4. Key definitions

| Term | Definition used here |
|---|---|
| **Dark** | A radar detection the provider could not attribute to an AIS track (`matched_category == "unmatched"`) |
| **SOLAS-class** | `length_m >= 100`, a working proxy for the SOLAS Ch. V carriage threshold (300 GT on international voyages). Length is what SAR measures |
| **SDR** | Standardised dark ratio: observed dark ÷ expected dark, where expected uses global length-class-specific rates. Free of the cell's size mix |
| **AIS dead zone** | A cell where reception or the feed has failed: everything is dark, including large hulls |
| **Behavioural dark spot** | A cell where the AIS picture demonstrably arrives (some ships match) and large hulls are selectively absent from it |
| **Corridor pressure** | Weekly conflict events in admin units within 250 km of a corridor box, also reported with an exp(−d/150 km) decay weighting |
| **MSRI** | Maritime Supply-Chain Risk Index: weighted, min-max scaled composite of five components, relative to the corridors in the run |
