# Global Conflicts — Impact on Supply Chains

**CDM Datathon 2026, Theme 6.2.** A reproducible analysis of what armed conflict
does to global shipping, built from the two supplied datasets and answering the
theme's four explicit asks: insights into conflict's impact on shipping,
identification of **AIS dead zones**, **prediction of AIS dark spots**, and their
correlation with the identification crisis produced by localised conflicts of the
Black Sea / Persian Gulf type.

```bash
pip install -r requirements.txt
python run.py --all          # ~2 minutes, no network required
```

Outputs land in `outputs/`: the report PDF, 20 figures, ~35 audit tables, and the
Power BI star-schema export.

---

## The finding in one paragraph

Conflict degrades shipping in **two opposite ways, and they need opposite
responses**. Where a belligerent can threaten hulls, ships *leave*: the
Bab-el-Mandeb corridor runs 81% below the large-vessel throughput of uncontested
corridors, and the Cape of Good Hope route now carries more large-vessel traffic
per imaged scene than the entire Suez/Red Sea route. Where a belligerent needs
its own traffic to keep moving unobserved, ships *stay and go dark*: 84% of
SOLAS-class vessels in the Strait of Hormuz carried no usable AIS identity
against a 10% open-ocean baseline, with the Black Sea at 48%. A watch-keeper
monitoring AIS traffic volume sees the first failure and is blind to the second.
A watch-keeper monitoring dark rates sees the second and reads the first as calm.

## What is distinctive here

| | |
|---|---|
| **Dark rates are size-standardised** | A raw dark rate ranks the Bay of Bengal above the Black Sea, because small craft are exempt from AIS carriage. Every corridor number is computed on SOLAS-class hulls and cross-checked by direct and indirect standardisation. |
| **Dead zones are separated from decisions** | A cell where *everything* is dark is a reception or feed failure; a cell where large hulls are dark while others match is a decision. The typology is computed, not asserted, and it reclassifies 9 apparent dark spots as feed gaps and 106 as ordinary non-carriage water. |
| **Absence is measured, not just darkness** | Traffic that has been driven away leaves no dark detections at all. A revisit-normalised throughput deficit catches what a dark-rate map cannot see. |
| **The coupling is tested three ways and reported honestly** | Detection-level logistic regression (n=39,876, cluster-robust SEs) finds a 2.39× odds ratio for darkness within 150 km of recent conflict. The corridor cross-section is *not* significant, and says so. The lead-lag test finds *no* usable warning time. |
| **Validation is spatially blocked** | The dark-spot classifier is scored on whole 5° blocks it never trained on (ROC-AUC 0.80). Random k-fold on gridded data would have reported a flattering and meaningless number. |
| **Judgements are in config, not code** | Risk weights and India-dependency scores live in `config/risk_weights.json` so an assessor can disagree by editing one file and re-running. |

## Layout

```
config/       chokepoints.json (28 corridor boxes), risk_weights.json (MSRI weights)
data/raw/     the two supplied files, unmodified
src/dcsc/
  ingest/     conflict.py, sar.py, external.py (declared open sources)
  features/   geo.py, conflict_features.py, maritime_features.py
  analysis/   eda, darkspots, displacement, coupling, predict, forecast, risk_index
  viz/        theme.py, charts.py, maps.py
  powerbi/    export.py  (star schema + DAX)
  report/     build_report.py
outputs/      figures/ tables/ powerbi/ report/ run_manifest.json
docs/         METHODOLOGY, DATA_DICTIONARY, FINDINGS, POWERBI_GUIDE, SOURCES
tests/        pytest suite over the statistics and the pipeline contracts
```

## Commands

```bash
python run.py --all                 # everything
python run.py --stage analysis      # tables only, no figures
python run.py --stage figures       # tables + figures
python run.py --stage report        # rebuild the PDF
python run.py --all --force-ingest  # ignore the cached parquet
python run.py --all --no-forecast   # skip the backtest (~60s faster)
python -m dcsc.ingest.external --list   # declared open-source extensions
pytest -q                           # test suite
```

## Deliverables against the submission format

| Asked for | Delivered |
|---|---|
| Analysis in PDF | `outputs/report/Datathon2026_Conflict_and_Supply_Chains.pdf` (22 pages, 20 figures) |
| Screenshots of the analytics software used | Every figure is the tool's own output at 160 dpi, in `outputs/figures/` |
| Power BI file (`.pbix`) | `.pbix` is a binary Power BI Desktop artefact. `outputs/powerbi/` holds what it is built from: 15 star-schema CSVs, `measures.dax`, `relationships.csv`, and a step-by-step build in `docs/POWERBI_GUIDE.md` (about 15 minutes in Power BI Desktop) |
| Use of other open-source data | `src/dcsc/ingest/external.py` declares 8 further sources with citation, licence, join key and what each would add; the core analysis needs none of them |

## Data

Both supplied files are committed under `data/raw/` so the analysis is
reproducible as submitted:

* `acled_middle_east_weekly_2026-06-27.xlsx` — 149,825 weekly conflict records,
  Dec 2014 – Jun 2026, 17 countries and sea areas.
* `sar_vessel_detections_2026-03.csv` — 107,257 Sentinel-1 radar vessel
  detections worldwide, 1–14 Mar 2026, each with its AIS correlation result.

See `docs/DATA_DICTIONARY.md` for every field and every derived column, and
`docs/SOURCES.md` for citation and licensing.
