# Methodology

This document states every analytical decision and why it was made, in the order
the pipeline makes them. Where a choice could reasonably have gone the other way,
the alternative is named and the reason for rejecting it is given.

---

## 1. The measurement problem

Two sources, two kinds of truth:

* **SAR (Sentinel-1) detections** are physical. A radar return is a hull on the
  water whether or not anybody wanted it seen.
* **AIS** is declarative. It is what a ship says about itself, to whoever is
  listening, if it is transmitting and if a receiver is in range.

Everything interesting lives in the disagreement between them. But "disagreement"
has at least four causes with completely different meanings:

| Cause | Meaning | Is it a finding? |
|---|---|---|
| Vessel below the SOLAS carriage threshold | Nothing. It was never required to transmit | No |
| No receiver in range / feed outage / no correlated pass | A hole in our picture | Yes — but a **collection** finding |
| Equipment failure | Maintenance | Rarely |
| Deliberate switch-off, spoofing or jamming | An adversary decision | **Yes** |

The whole method is the business of separating these.

## 2. Cleaning

### 2.1 The `matched_category` discovery

The supplied file carries two partially contradictory accounts of identification:

* `matched_category` — the provider's adjudication. `"unmatched"` means the match
  was rejected; any other value means it was accepted.
* `mmsi` + `matching_score` — the *candidate* association.

They disagree in both directions. 13,057 detections carry a candidate MMSI and
are still labelled `unmatched`. Roughly a third of accepted matches sit below a
correlation score of 1.0.

Three defensible dark definitions therefore exist, and they give materially
different global dark rates:

| Definition | Global dark rate |
|---|---|
| No MMSI at all | 26.6% |
| Provider label (`matched_category == "unmatched"`) — **adopted** | 39.1% |
| Provider label plus weak-scoring accepted matches | 58.4% |

The provider's label is adopted as the headline because it is an adjudication
made with information this project does not have (track continuity, timing,
kinematics). The other two are carried through every corridor result as a
sensitivity analysis (`outputs/tables/darkspot_sensitivity.csv`). **The corridor
ranking is stable across all three**, which is the claim that matters — no
conclusion rests on the threshold choice.

### 2.2 Quality gates

| Gate | Value | Rows lost | Reason |
|---|---|---|---|
| `presence_score` | ≥ 0.90 | 2,412 | Below this a contact is as likely to be clutter, wind streaks or a wake as a hull |
| `length_m` | ≥ 10 | 8 | Below reliable Sentinel-1 IW detection size |

Conflict-side cleaning drops nothing: coordinates are range-checked, weeks are
parsed, and zero-event rows are flagged rather than deleted.

## 3. Making dark rates comparable

### 3.1 The confound

Dark rate falls monotonically with hull length: 74.9% for craft under 25 m, down
to 13.2% for 160–250 m hulls. Below roughly 300 GT on international voyages,
SOLAS Chapter V does not require AIS at all. A raw dark rate therefore maps
fishing fleets, and would rank the Bay of Bengal (72%) above the Black Sea (55%).

### 3.2 Three corrections, used together

1. **SOLAS-class subset** (≥ 100 m). Length is what SAR measures; 100 m is
   comfortably above the tonnage threshold for any normal hull form. This is the
   headline measure.
2. **Direct standardisation** to the global length-class mix — "what would this
   corridor's dark rate be with the world's average ship mix?" Strata with fewer
   than 15 observations are dropped and their weight redistributed, with the
   surviving share reported as `standardised_coverage` so a thin result can be
   discounted rather than believed.
3. **Indirect standardisation** at cell level — expected dark count from global
   class-specific rates, giving a **standardised dark ratio (SDR)** of observed
   over expected. SDR = 1 means "exactly as dark as this traffic mix is
   worldwide". This is the epidemiologist's SMR, applied to ships.

## 4. Finding dark spots

1. Bin detections into 0.5° cells (equal-angle, with true surface area computed
   per cell so densities remain comparable across latitudes).
2. Keep cells with ≥ 25 detections.
3. Compute SDR and a **Wilson score interval** on the dark proportion. Wilson
   rather than the normal approximation because cell denominators are small,
   where the normal interval is badly wrong and would manufacture dark spots out
   of three detections.
4. One-sided **exact binomial test** against the cell's own expected rate.
5. **Benjamini–Hochberg FDR control at q < 0.05.** 1,038 cells are tested at
   once; uncorrected p-values would return roughly 50 false positives by
   construction.
6. Flag a dark spot where q < 0.05 **and** SDR ≥ 1.5 — statistical significance
   and a materially large effect, not either alone.

## 5. Dead zone versus decision: the typology

The theme asks for dead zones *and* dark spots. They look identical on a dark-rate
map and mean opposite things. The discriminator is whether **anything else in the
same cell matched**:

| Type | Rule | Interpretation |
|---|---|---|
| AIS dead zone | dark rate ≥ 0.97 **and** SDR ≥ 2 | Even large hulls are dark: reception or feed failure, not behaviour |
| Non-carriage area | dark rate ≥ 0.85, SDR < 1.5, mean length < 45 m | Small-craft water. Expected, not a finding |
| Behavioural dark spot | SDR ≥ 1.5, q < 0.05, ≥ 5% of traffic matched, SOLAS dark rate ≥ 0.35 | The picture demonstrably reaches this water and the large hulls are missing from it |
| Blackout, cause unresolved | dark rate ≥ 0.97 but SDR < 2 | Insufficient large-hull traffic to decide |

Results: 93 behavioural, 106 non-carriage, 9 dead zones, 17 unresolved. Two of the
nine dead zones sit over Tokyo Bay — one of the most instrumented waters on earth
— where *every* detection is unmatched. That is a feed gap, and calling it an
adversary dark spot would have cost a sortie.

**Persistence** is computed alongside: days on which a cell was majority-dark over
days observed. A cell dark on one pass may be one convoy; a cell dark on nine days
of fourteen is a standing condition.

## 6. Clustering

DBSCAN on the haversine metric (60 km neighbourhood, 40-contact minimum),
restricted to dark SOLAS hulls. DBSCAN rather than k-means because the number of
dark areas is unknown and their shapes are not spherical — a transit lane is
elongated, a holding area is round, and the p90 radius reported per cluster tells
them apart. For each cluster, the **local dark rate** is recomputed over *all*
large-vessel detections within its own extent, so a high value proves matched
traffic was present and the cluster still stayed dark.

## 7. Measuring absence

Traffic driven away leaves no dark detections — it leaves nothing. Two traps had
to be avoided:

* **Never count throughput with the AIS category.** `matched_category` is only
  known for identified vessels, so in a corridor where most traffic is dark the
  commercial count collapses by construction, and concealment is misread as
  evacuation. Throughput is counted on radar length alone.
* **Scene counts are inferred** from scenes that yielded at least one detection
  in the box, because footprints are not in the extract. A genuinely empty
  corridor therefore under-counts its own observation opportunities and its
  per-scene rate is flattered. The bias runs *against* the finding, making every
  measured deficit a lower bound.

The benchmark is the median SOLAS detections per imaged scene across nine
uncontested corridors.

## 8. Testing the conflict link

Three independent tests, because any one of them alone would be weak, and they do
not all agree.

| Test | Unit | Result |
|---|---|---|
| Logistic regression, cluster-robust SEs on the 0.5° cell | 39,876 SOLAS detections | Within 150 km of recent conflict: **OR 2.39** (95% CI 1.24–4.60, p = 0.009). Per log-unit of conflict events within 300 km: OR 1.12. Per log-metre of hull: OR 0.65 |
| Spearman + OLS cross-section | 25 corridors | rho = 0.28, **p = 0.18 — not significant.** Underpowered, and reported as such |
| Cross-correlation, weekly | 2019–2026 | Peak at **lag 0** (r = 0.63), nearly flat from −10 to +10 weeks. **No usable warning time** |

Reporting the null result is deliberate. An analysis that produced three
confirmations from three tests of the same hypothesis on the same data would be
less believable, not more.

## 9. Prediction

**Dark-spot classifier.** Gradient boosting over cell-level features (traffic
composition, density, absolute latitude, distance to the nearest critical
chokepoint, conflict exposure), target = behavioural dark spot.

Validation is **spatially blocked**: folds are whole 5° blocks. Random k-fold on
gridded geodata is self-deception — neighbouring cells are near-duplicates, so a
random split leaves half of every dark spot in training and the score measures
memorisation. Out-of-fold ROC-AUC 0.80, PR-AUC 0.36 against a 0.09 base rate.

Absolute latitude ranks first by permutation importance, which is itself
diagnostic: satellite AIS reception geometry is latitude-dependent, so part of
what the model learns is where the *picture* is weak rather than where ships
hide. That is exactly why the typology in §5 exists.

**Conflict forecasting.** Four models — naive, 4-week mean, SARIMAX(2,1,1) and
gradient boosting on lag features — compete on one-step-ahead expanding-window
backtests over 26 weeks. The winner per corridor is refit and projected 12 weeks
with intervals from its *own* backtest error distribution, widened as √h.

At Bab-el-Mandeb the 4-week mean beats naive by 20%. At **Hormuz nothing beats
naive** — conflict there arrives in spikes a weekly model cannot anticipate, and
that is reported rather than hidden behind the best-looking fit.

## 10. The composite index

MSRI = weighted sum of five min-max scaled components: conflict intensity (0.25),
escalation trend (0.15), identification risk (0.25), throughput disruption (0.20),
strategic criticality (0.15).

Three properties make it usable rather than decorative:

* **Relative by construction.** Scaling is across the corridors in the run, so
  0.72 means "among the worst lanes observed", never "72% chance of closure".
* **Weights are external.** `config/risk_weights.json`. An assessor who disagrees
  edits one file and re-runs.
* **Decomposable.** Every chart shows each component's contribution, so the
  ranking can be argued with rather than accepted.

The India overlay multiplies MSRI by a declared dependency score, kept separate
from the index itself so that a judgement never contaminates a measurement.

## 11. Reproducibility

Fixed seed (`SETTINGS.random_state`), parquet caching of cleaned inputs, a run
manifest capturing settings, row counts, runtime and headline values, and one CSV
in `outputs/tables/` behind every figure and every number in the report. No
network access is required at any stage.
