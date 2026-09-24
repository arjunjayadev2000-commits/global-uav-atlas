# CDM Datathon-2026 · Theme 6.1 · Project HIGH GROUND

*Contested and Congested: the Crowding of Orbit, and What It Means for India and the Indian Armed Forces.*

## Deliverables

| File | What it is |
|---|---|
| `report/Datathon2026_Theme6.1_Satellites_Booklet.pdf` | Commander's Edition booklet: the submission, 26 pages |
| `report/Datathon2026_Theme6.1_Technical_Annex.pdf` (+ `.docx`) | Technical annex: methods, formulas, validation, limitations (8 pages) |
| `report/Datathon2026_Theme6.1_Satellites_Booklet.docx` | The same booklet as an editable Word file |
| `deck/Datathon2026_Theme6.1_Satellites_Presentation.pptx` | Phase II presentation: 19 slides, native charts, speaker notes |
| `powerbi/powerbi_tables.zip`, `powerbi/POWERBI_BUILD_GUIDE.md` | Power BI tables and step-by-step build guide |
| `submission/` | Email draft, Appendix A form and checklist per Gen Instr Para 8.2 |

## Data

**CDM datasets** (`data/raw`, not committed):
- `satellites.csv`: census of 1,167 active satellites, January 2014.
- `labels.csv` and `sunspots.csv`: Dst and sunspot space-weather records.
- `fire_*_M6.csv`: 1.25 million MODIS fire detections.

**Open sources** (`data/open`):
- CelesTrak SATCAT (70,793 objects, to 21 Sep 2026), via github.com/astrion-tech/celestrak-mirror.
- UCS Satellite Database, April 2020.
- UNOOSA objects launched per year (via Our World in Data).
- CelesTrak current orbital elements (OMM) for active satellites and debris clouds, via github.com/satvisorcom/satvisor-data.

## Rebuild everything

```bash
cd analysis && python run_all.py                  # 12 stages -> figures, tables, data/metrics.json, Power BI tables (deterministic)
cd ../report && python make_screens.py && python build_booklet.py && python build_annex.py && python build_word.py
cd ../deck && python prep_deck_data.py && node build_deck.js   # needs pptxgenjs, react-icons, sharp
```

## Analysis stages

| Stage | What it does |
|---|---|
| 01 | Cleaning, including Excel-date conversion and impossible-value checks |
| 02 | Growth: population rebuilt year by year, three censuses, PELT change-point, CAGR |
| 03 | Actors: country shares, HHI, users and purposes |
| 04 | Congestion: altitude shells, collision-risk index, GEO arc, ASAT debris survival |
| 05 | Contest: military and ISR programme families, India versus China and the USA |
| 06 | Space weather: storm events, Poisson regression, re-entry periodogram |
| 07 | Earth-observation value: constellation premium, surges, industrial heat sources |
| 08 | Forecast: damped trend with back-test, 2030 scenarios, risk index |
| 09 | India scorecard, robustness checks, ORBITWATCH warning matrix |
| 11 | Machine learning: military vs civil use from orbit, mass and power; out-of-time test on UCS 2020 launches |
| 12 | Close-approach screening: SGP4 on current orbital elements, 24 h, all active satellites + debris clouds |
| 10 | Power BI export (runs last) |
