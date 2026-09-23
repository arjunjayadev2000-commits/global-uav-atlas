# CDM Datathon-2026 - Global Conflicts: Impact on Supply Chains

**Report:** `report/Datathon2026_Global_Conflicts_Supply_Chains_Report.pdf` (60 pages, formatted in the
style of an M.Tech thesis: declaration, abstract, lists, TOC, numbered chapters, references, appendices).

**Thesis:** conflict at a maritime chokepoint first *blinds* the supply chain (large ships go AIS-dark), and the
physical disruption that follows lasts longer than national buffers. The report closes with: 9 Inference (findings,
hypothesis verdicts, inferences I1-I6) -> 10 Impact on the Globe -> 11 Impact on India -> 12 Impact on the Indian Armed
Forces (joint, Navy, Air Force, Army, stock-cover model) -> 13 Way Forward (13 traced recommendations, roadmap) -> 14 Conclusion.

## Headline results
| | |
|---|---|
| Weekly political violence, 2026 war regime vs prior year | 2.9x (Mann-Whitney p = 3.6e-5) |
| Change-points found without being given the dates | 7 Oct 2023, 28 Feb 2026, 11 Apr 2026 |
| Stand-off strikes (air/drone/missile) share of war violence | 84% |
| Violence inside GCC states | 124x pre-war rate |
| Large ships (>=100 m) AIS-dark: Hormuz / Persian Gulf / Black Sea / peacetime waters | 74% / 60% / 38% / ~10% |
| Relative risk / odds ratio of darkness in war zones | 4.7 / 8.0 |
| Dark-spot model, leave-one-region-out ROC-AUC | 0.69 (0.74 with leaky random CV) |
| Disruptions outlasting India's SPR (~9.5 d) / total cover (~74 d) | 62% / 11% |

## Layout
```
analysis/     01..07 pipeline stages, common.py, run_all.py
figures/      26 charts and maps (PNG, 200 dpi)
tables/       23 result tables (CSV)
data/         metrics.json (every number quoted in the report); raw/ and clean/ are git-ignored
powerbi/      powerbi_tables.zip (star schema) + POWERBI_BUILD_GUIDE.md
report/       build_report.py -> PDF
```

## Reproduce
```bash
pip install pandas numpy scipy statsmodels scikit-learn ruptures matplotlib basemap pyarrow openpyxl pymupdf playwright
# put the two CDM files in data/raw/
python analysis/run_all.py          # ~1 min: figures, tables, metrics, Power BI tables
python report/build_report.py       # PDF report (headless Chromium)
```

Placeholders to fill before submission: `[Rank]`, `[Service No]`, `[Unit / Formation]` (top of `report/build_report.py`).
