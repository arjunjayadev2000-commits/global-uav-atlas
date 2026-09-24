# Code guide - how to read and run the analysis

Every Python file has an **annotated header** that says what the file does, what it reads and writes, and which
methods it uses and why. It also has **plain-language comments** at each step. The comments explain the code;
they do not change it. Each file's parsed code was checked against the original, and the metrics were
regenerated to confirm they are identical.

## Run everything
```bash
pip install pandas numpy scipy statsmodels scikit-learn ruptures matplotlib basemap pyarrow openpyxl \
            pymupdf playwright fontawesomefree python-docx beautifulsoup4
cd analysis && python run_all.py          # raw data -> figures, tables, metrics.json, Power BI tables (~2 min)
cd ../report
python build_report.py                    # full technical report (PDF)
python build_commander.py                 # Commander's Edition (PDF) - the submission
python build_scoresheet.py                # self-assessment sheet (PDF)
python build_word.py                      # editable Word (.docx) versions of all three
```

## Reading order (analysis/)
| File | Report chapter | What it answers |
|---|---|---|
| `common.py` | - | Shared paths, chart style, sea regions, distance formula, MMSI-to-flag decoder, metrics store |
| `01_preprocess.py` | 4 Data | Cleaning and validation, new columns, link each ship to the war |
| `02_conflict.py` | 5 | How violence changed; change-points; stand-off strikes; the GCC and the sea |
| `03_chokepoint_index.py` | 6 | Conflict index per sea lane; forecast; how long crises last (Kaplan-Meier, Cox) |
| `04_sar.py` | 7.1-7.7 | Where and which ships went dark; hot spots; clusters; flags; identity checks |
| `05_model.py` | 8 | Forecasting darkness, tested on unseen seas; the dark-risk map |
| `06_decision.py` | 13.5 | How much stock is enough (expected shortfall, the 35-45 day knee) |
| `08_intel.py` | 10, 14 | Robustness, dose-response, competing hypotheses, Indian ships, I&W matrix, scenarios |
| `09_opendata.py` | 9.1-9.8 | Oil, rupee, import bill, Granger test, out-of-sample check |
| `10_infographic_assets.py` | - | Base map for the theatre infographic |
| `11_darkwater.py` | 7.8-7.10, 10.4 | Presence vs identity, stasis, difference-in-differences, four signatures, defence budget |
| `12_portwatch.py` | 9.9-9.13, 13.5 | Ship transits at 28 chokepoints, shipping-disruption duration, effective cover |
| `07_powerbi_export.py` | - | Star-schema tables for the Power BI dashboard (runs last) |
| `run_all.py` | - | Runs all stages in order |

## report/
| File | Builds |
|---|---|
| `build_report.py` | Full technical report (thesis format). Put your rank, service number and unit in the lines marked EDIT HERE |
| `build_commander.py` | Commander's Edition (24 pages); Power BI screenshots go in `figures/pbi_page1-4.png` |
| `story.py`, `infographics.py` | Plain-language story text and SmartArt-style graphics |
| `build_scoresheet.py`, `make_screens.py` | Self-assessment sheet; software screenshots |
| `build_word.py` | Editable Word versions of the three PDFs |
