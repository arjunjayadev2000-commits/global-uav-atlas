# Sources and citation

## Supplied datasets (the primary evidence)

1. **Middle East weekly conflict aggregate** —
   `Middle-East_aggregated_data_up_to_week_of-2026-06-27.xlsx`, supplied with the
   competition pack. ACLED-style schema (WEEK / REGION / COUNTRY / ADMIN1 /
   EVENT_TYPE / SUB_EVENT_TYPE / EVENTS / FATALITIES / POPULATION_EXPOSURE /
   DISORDER_TYPE / ID / centroids). Underlying methodology: Armed Conflict
   Location & Event Data Project (ACLED), <https://acleddata.com>. Committed
   unmodified as `data/raw/acled_middle_east_weekly_2026-06-27.xlsx`.

2. **Indian Ocean / global SAR vessel detections, March 2026** —
   `indian ocean vessel - Mar 26.csv`, supplied with the competition pack.
   Sentinel-1 IW GRDH detections with AIS correlation results. The competition's
   own `Data Links.docx` cites the published source as
   <https://www.kaggle.com/datasets/shubh5106/indian-ocean-sar-vessel-detections>.
   Committed unmodified as `data/raw/sar_vessel_detections_2026-03.csv`.

3. **Data Links.docx**, supplied with the competition pack, listing three Kaggle
   AIS datasets. Retained at `data/raw/Data_Links.docx`; all three appear in the
   declared open-source register below.

Sentinel-1 imagery is a Copernicus Programme product of the European Space Agency
and the European Commission, available under the Copernicus open data policy.

## Reference geography (analyst-entered, in `config/`)

`config/chokepoints.json` defines 28 corridor boxes. The boxes are coarse
rectangles drawn around navigable water; they are **analyst-entered reference
geography, not measurements**, and each is listed with its coordinates so any
reviewer can check or change one. The set of corridors treated as strategically
critical follows the standard public chokepoint literature:

* U.S. Energy Information Administration, *World Oil Transit Chokepoints*.
* UNCTAD, *Review of Maritime Transport* (chokepoint and route definitions).
* IMF PortWatch chokepoint definitions, <https://portwatch.imf.org>.

`config/risk_weights.json` holds the MSRI weights and the India-dependency
scores. **Both are declared analyst judgements, not data.** Each dependency score
carries its rationale inline. They are kept in configuration precisely so that an
assessor can disagree with them by editing one file and re-running.

## Regulatory basis for the SOLAS-class threshold

IMO SOLAS Chapter V, Regulation 19, requires AIS carriage on ships of 300 gross
tonnage and upwards engaged on international voyages, all ships of 500 GT and
upwards, and all passenger ships. SAR measures length, not tonnage, so a 100 m
length cut is used as a conservative proxy: a 100 m hull of any normal form is
comfortably above 300 GT.

## Declared open-source extensions

`src/dcsc/ingest/external.py` registers eight further sources with citation,
licence, join key and a statement of what each would add. Run
`python -m dcsc.ingest.external --list`. The core analysis needs none of them and
runs with no network access; this register exists so that the route beyond the
supplied data is explicit and auditable rather than improvised.

| Key | Source | What it would add |
|---|---|---|
| `imf_portwatch_chokepoints` | IMF PortWatch daily chokepoint transits | Converts the 14-day traffic *level* into a *change* — the single biggest limitation here |
| `unctad_maritime` | UNCTADstat | Expresses a throughput deficit in tonnes and freight cost |
| `acled_full` | ACLED event-level export | Point coordinates, replacing the admin-centroid approximation |
| `gfw_sar_global` | Global Fishing Watch | Extends the detection window; enables out-of-time validation |
| `kaggle_harboriq` | Kaggle (from the competition's Data Links) | Vessel particulars by MMSI → flag and type breakdown of the dark fleet |
| `kaggle_mmsi_daily` | Kaggle (from the competition's Data Links) | Track history: was a dark vessel transmitting elsewhere days earlier? |
| `kaggle_indian_ocean_sar` | Kaggle (from the competition's Data Links) | Provenance of the supplied detection file |
| `natural_earth_coastline` | Natural Earth (public domain) | A conventional basemap and a true distance-to-coast feature |

## Software

Python 3.11 with pandas, numpy, scipy, statsmodels, scikit-learn, matplotlib,
openpyxl, pyarrow, reportlab and Pillow. Versions are pinned by lower bound in
`requirements.txt`; the exact run is recorded in `outputs/run_manifest.json`.

## How to cite this work

> "Global Conflicts — Impact on Supply Chains: AIS dark spots, chokepoint
> exposure and the maritime cost of conflict." Submission to CDM Datathon 2026,
> Theme 6.2. Analysis of the supplied ACLED-style Middle East conflict aggregate
> and Sentinel-1 SAR vessel detections, March 2026.
