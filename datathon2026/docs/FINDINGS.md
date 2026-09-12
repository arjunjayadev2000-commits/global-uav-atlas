# Findings

Every number here is reproduced by `python run.py --all` and is backed by a named
CSV in `outputs/tables/`. Figure numbers refer to `outputs/figures/`.

---

## The thesis

**Conflict degrades shipping in two opposite ways, and a staff that watches for
one is blind to the other.**

| | Concealment | Avoidance |
|---|---|---|
| What happens | Ships stay, and stop declaring themselves | Ships go somewhere else |
| Signature | Dark rate rises; traffic count normal or high | Traffic count collapses; dark rate normal |
| Archetype | **Strait of Hormuz** — 84% dark, 3.6× the benchmark traffic density | **Bab-el-Mandeb** — 5% dark, 81% below benchmark throughput |
| What it needs | Independent tracking, collection, identification | Routing, insurance, schedule and stock resilience |

Watching AIS volume finds avoidance and misses concealment. Watching dark rates
finds concealment and reads avoidance as calm. Both must be measured.

---

## F1 — The conflict picture, and its move to sea

* 614,134 events and 552,727 fatalities across 601 weeks (Dec 2014 – Jun 2026),
  17 countries and sea areas.
* The mix has shifted towards **Explosions/Remote violence** (228,545 events) —
  the category containing air and drone strikes and anti-ship missile employment,
  the class of violence that reaches ships without any ground advance.
* **1,257 events are located at sea**, not on land: North Indian Ocean (845),
  Wider Black Sea Region (305), Eastern Mediterranean (107). The series is
  negligible before late 2023 and sustained thereafter, with 2026 Q2 (153 events)
  the heaviest quarter on record.
* The heaviest single week in the whole record is **3 Jan 2026** (27,696
  fatalities, overwhelmingly Iran, driven by riots and protests). Internal
  instability in a littoral state is precisely the condition under which that
  state's shipping stops declaring itself — and Hormuz is that state's strait.

*Figures 1–4. Tables: `conflict_weekly_totals`, `conflict_event_mix`,
`conflict_maritime_domain_events`.*

## F2 — A raw dark rate is a trap

Dark rate by hull length: **74.9%** under 25 m → 46.7% → 25.2% → 17.3% → 13.2% →
15.2% over 250 m. Below the SOLAS carriage threshold a vessel is not required to
transmit at all.

An uncontrolled dark rate therefore ranks the **Bay of Bengal (72%) above the
Black Sea (55%)** — it is measuring fishing fleets, not concealment. Every
corridor figure in this work is computed on SOLAS-class hulls (≥ 100 m, n =
39,876, 15.2% dark overall) and cross-checked by standardisation.

*Figure 5. Table: `sar_dark_by_length_class`.*

## F3 — Where large ships stop being identifiable

Against a **10% open-ocean baseline**:

| Corridor | SOLAS dark rate | n | 95% Wilson |
|---|---|---|---|
| **Strait of Hormuz** | **83.9%** | 1,304 | 81.8–85.8% |
| Black Sea | 48.1% | 1,465 | 45.6–50.7% |
| Gulf of Oman | 45.9% | 314 | 40.4–51.4% |
| Persian Gulf | 42.4% | 1,376 | 39.9–45.1% |
| Southern Red Sea | 23.3% | 180 | 17.8–30.0% |
| Turkish Straits | 2.1% | 610 | 1.2–3.6% |
| Suez Canal | 2.8% | 424 | 1.6–4.9% |

The two worst are exactly the two theatres the theme statement names — the
Persian Gulf and the Black Sea — which is a useful external check that the
instrument measures what it claims.

**The within-theatre contrast is the most telling result.** The Turkish Straits,
under continuous VTS control, sit at 2% while the Black Sea beyond them sits at
48%. The Suez Canal, transited under authority supervision, sits at 3% while the
Gulf of Oman approach sits at 46%. Darkness is not a property of a region; it is
a property of whether a ship expects to be held to account in that water.

The ranking survives all four dark definitions:

| Corridor | No candidate | Provider label | + weak matches | SOLAS only |
|---|---|---|---|---|
| Strait of Hormuz | 68% | 84% | 91% | **84%** |
| Black Sea | 35% | 55% | 69% | **48%** |
| Bay of Bengal | 62% | 72% | 80% | **17%** |
| Dover Strait | 8% | 17% | 47% | **4%** |

Note the Bay of Bengal column: it looks severe on every uncontrolled definition
and normal on the controlled one. That single row is the argument for the whole
method.

*Figure 6, 15. Tables: `traffic_by_corridor`, `darkspot_sensitivity`.*

## F4 — Dead zone, non-carriage, or decision?

Of 1,038 cells tested, **142 are significantly darker than their own traffic mix
predicts** (BH-FDR q < 0.05, SDR ≥ 1.5). Classified:

| Type | Cells | Example |
|---|---|---|
| Behavioural dark spot (selective switch-off) | **93** | Hormuz 25.0N 56.0E: 231 detections, 90% dark, SDR 4.1, dark on every observed day |
| Non-carriage area (small craft) | 106 | Bangladesh coast 21.0N 91.0E: mean length 22 m, SDR 1.4 |
| AIS dead zone (reception / feed gap) | **9** | **Tokyo Bay 35.5N 139.5E: 73 detections, 100% dark, SDR 4.6** |
| Blackout, cause unresolved | 17 | Gulf of Thailand 9.5N 104.5E |

Tokyo Bay is the instructive case. It is among the most densely instrumented
waters on earth and *every* detection there is unmatched — including large hulls.
No fleet switches off in perfect unison in a Japanese port approach; that is a
feed gap. Nine cells would have been reported as adversary dark spots by any
method that did not ask whether anything else in the cell matched. **The
discriminator costs nothing but the question.**

*Figure 16. Table: `darkspot_grid_cells` (`area_type`, `persistence`).*

## F5 — Dark operating areas

DBSCAN over dark SOLAS hulls recovers 14 contiguous areas holding 45% of all dark
large-vessel traffic:

| Rank | Where | Dark contacts | Centre | Local dark rate | Extent (p90) |
|---|---|---|---|---|---|
| 1 | **Strait of Hormuz** | **1,401** | 25.6N 55.6E | 82% | 176 km |
| 2 | **Black Sea (Novorossiysk–Kerch)** | 510 | 44.7N 37.3E | 76% | 136 km |
| 3 | Persian Gulf (Qatar approaches) | 134 | 25.8N 51.9E | 62% | 52 km |
| 4 | Central Mediterranean | 120 | 36.1N 14.7E | 69% | 95 km |
| 5 | Tokyo Bay *(feed gap, see F4)* | 98 | 35.4N 139.8E | 100% | 69 km |

"Local dark rate" is computed over **all** large-vessel detections inside each
cluster's own extent. At Hormuz, 82% means matched traffic was demonstrably
present in the same water on the same days and the cluster still stayed dark —
the reception explanation fails in the most direct way the data allows.

*Figures 17–18. Table: `darkspot_clusters`.*

## F6 — The traffic that left

Throughput measured as SOLAS-class detections per imaged scene, against a
benchmark of **33.2** (median across nine uncontested corridors):

| Corridor | Per scene | vs benchmark |
|---|---|---|
| Bab-el-Mandeb | 6.2 | **−81%** |
| Gulf of Aden | 6.3 | −81% |
| Southern Red Sea | 11.3 | −66% |
| Northern & Central Red Sea | 11.4 | −66% |
| Black Sea | 23.6 | −29% |
| **Strait of Hormuz** | **118.5** | **+257%** |

Hormuz is the control that proves the instrument: it sits far *above* the
benchmark. Its ships are present in force and concealed. The Red Sea corridors
sit far below: their ships are elsewhere.

Where they went: the **Cape of Good Hope route carries 21.5 SOLAS-class vessels
per imaged scene against 19.4 for the entire Suez/Red Sea route**. A detour of
roughly 3,500 nautical miles now moves as much large-vessel traffic as the canal
corridor it replaced.

*Figures 7, 8, 19. Tables: `corridor_throughput_deficit`, `route_suez_vs_cape`.*

## F7 — Is it conflict, or just geography?

Three independent tests. They do not all agree, and all three are reported.

1. **Detection level (n = 39,876 SOLAS hulls, SEs clustered on 0.5° cells).**
   Within 150 km of conflict in the preceding 30 days: **OR 2.39** (95% CI
   1.24–4.60, p = 0.009). Per log-unit of conflict events within 300 km: OR 1.12
   (1.03–1.23). Per log-metre of hull: OR 0.65 (0.52–0.81) — bigger ships are
   *less* likely to be dark, exactly as carriage rules predict, which is a
   sanity check on the model as much as a finding.
2. **Corridor level (n = 25).** Spearman ρ = 0.28, **p = 0.18 — not
   significant.** Correct in sign, underpowered, reported rather than buried.
3. **Over time (weekly, 2019–2026).** Cross-correlation of littoral land
   violence against maritime-domain events peaks at **lag 0 (r = 0.63)** and is
   nearly flat from −10 to +10 weeks. **There is no warning time.** Maritime
   posture cannot be sequenced behind a land-violence indicator; it has to move
   at the same time.

*Figures 9, 10, 20. Tables: `coupling_detection_logit`, `coupling_lead_lag`,
`coupling_corridor_cross_section`.*

## F8 — Dark spots can be anticipated

Gradient-boosted classifier over cell-level features, validated on **whole 5°
spatial blocks never seen in training**: out-of-fold **ROC-AUC 0.803**, PR-AUC
0.355 against a base rate of 0.090 — a roughly fourfold lift on unseen water.

Permutation importance: absolute latitude (0.025) > **distance to nearest recent
conflict (0.022)** > mean vessel length > fishing share > distance to critical
chokepoint > conflict events within 300 km.

Latitude ranking first is itself a finding: satellite AIS reception geometry is
latitude-dependent, so part of what the model learns is where the *picture* is
weak rather than where ships hide. That is precisely why the F4 typology exists,
and why the model is a triage aid rather than an accusation.

**Conflict forecasting**, 12 weeks ahead, four models in competition:

| Corridor | Winner | MAE | Skill vs naive |
|---|---|---|---|
| Bab-el-Mandeb | 4-week mean | 28.4 | **+20%** |
| Black Sea | SARIMAX | 15.4 | +10% |
| Suez Canal | SARIMAX | 119.2 | +3% |
| **Strait of Hormuz** | **naive** | 23.0 | **0% — nothing beat the benchmark** |

Hormuz conflict arrives in spikes no weekly model anticipates. Saying so is what
makes the corridors where a model *did* win worth acting on.

*Figures 11, 12. Tables: `darkspot_model_cv_scores`, `forecast_backtest_scores`.*

## F9 — Ranked exposure

Six corridors sit in the RED tier. The ranking and its dominant driver:

| Rank | Corridor | MSRI | Driver | India exposure |
|---|---|---|---|---|
| 1 | Gulf of Aden | 0.72 | Throughput disruption | 0.54 |
| 2 | Southern Red Sea | 0.70 | Conflict intensity | 0.56 |
| 3 | Bab-el-Mandeb | 0.68 | Throughput disruption | 0.54 |
| 4 | Black Sea | 0.67 | Conflict intensity | 0.30 |
| 5 | Eastern Mediterranean | 0.66 | Conflict intensity | 0.26 |
| 6 | **Strait of Hormuz** | 0.62 | **Identification risk** | **0.62 (highest)** |
| 7 | Gulf of Oman | 0.59 (AMBER) | Conflict intensity | 0.53 |

Weighted by Indian trade dependency, **Hormuz is first and the Gulf of Oman
third** — the corridor through which the bulk of India's crude and LPG imports
must pass, and the one where the recognised maritime picture has most thoroughly
collapsed.

*Figures 13, 14. Tables: `risk_index_msri`, `risk_index_watchlist`,
`risk_index_india_exposure`.*

---

## What follows

1. **Make the SOLAS-class dark rate a reportable weekly indicator.** Threshold
   35%: below it corridors sit in a tight 2–20% band; above it, every one is in a
   contested theatre. One radar product and one AIS feed are all it takes.
2. **Never report an uncontrolled dark rate.** Brief the Bay of Bengal as worse
   than the Black Sea once and the indicator is discredited for good.
3. **Classify before tasking.** Dead zone, non-carriage and behavioural darkness
   need a feed fix, no action, and collection respectively.
4. **Plan Hormuz for identification failure** — independent tracking, escorted
   transit windows, reporting that does not depend on the vessel's own
   transponder, and the working assumption that any AIS picture of the Gulf
   under-counts large hulls several-fold.
5. **Plan the Red Sea for absence** — the question is no longer whether diversion
   happens but what sustained Cape routing costs in hull-days, bunkers, schedule
   reliability and escort geography.
6. **Watch the Gulf of Oman as the early-warning water** — second-highest Indian
   exposure, already 46% dark, and outside the strait where sea room still exists.
7. **Watch the Sri Lanka corridor and the west-coast approaches for the same
   signature.** Both are normal today. A dark-rate rise there without conflict
   would signal dark-fleet practice migrating into Indian near waters — slower
   than an attack, and visible only to this measurement.
