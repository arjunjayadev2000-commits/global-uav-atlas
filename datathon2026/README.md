# PROJECT DARKWATER - CDM Datathon-2026, Global Conflicts: Impact on Supply Chains

**Commander's Edition - THE SUBMISSION (24 pages):** `report/Datathon2026_Commanders_Edition.pdf`, built by `report/build_commander.py`:
the whole story in ten short chapters for a commander or senior leader, plus Annex A (plain-words glossary), Annex B
(technical summary for assessors), Annex C (software used and screenshots; two Power BI screenshot slots to fill) and
Annex D (references).

**Editable Word versions:** `report/*.docx` (built by `report/build_word.py`). **Annotated code:** `Datathon2026_Annotated_Code.zip` and `CODE_GUIDE.md`.

**Full technical report (90 pages):** `report/Datathon2026_Global_Conflicts_Supply_Chains_Report.pdf`, formatted in the
style of an M.Tech thesis: declaration, abstract, lists, TOC, numbered chapters, references, appendices).

**Thesis:** conflict at a maritime chokepoint first *blinds* the supply chain (large ships go AIS-dark), and the
physical disruption that follows lasts longer than national buffers. The report closes with: 9 Inference (findings,
hypothesis verdicts, inferences I1-I6) -> 10 Impact on the Globe -> 11 Impact on India -> 12 Impact on the Indian Armed
Forces (joint, Navy, Air Force, Army, stock-cover model) -> 13 Way Forward (13 traced recommendations, roadmap) -> 14 Conclusion.

## DARKWATER layer (analysis/11_darkwater.py)
Strategic Dark Ratio (SDR); presence vs identity on a common radar footprint (AIS -83% vs radar -33% at Hormuz, dark fleet
unchanged); stasis index against a crowding null (dark hulls held at anchor, z = 5.3); all-dark-pass and day/night checks;
scene-level difference-in-differences vs 11 control seas (+5.7 pts/day, p = 0.008); flag-retention shift; four signatures
(concealment, evacuation, attrition/frozen, deterrence/compliance); oil premium vs monthly defence budget; centre-of-gravity
analysis; staffed recommendations and DARKWATCH.

## Open-source data (data/open/, analysis/09_opendata.py)
- Brent/WTI daily (EIA, via datasets/oil-prices) to 15 Sep 2026; INR/US$ daily (Fed H.10, via datasets/exchange-rates) to 18 Sep 2026;
  India oil balance (Energy Institute via Our World in Data); Natural Earth ports.
- New Chapter 9 *Economic Transmission*: event study (Hormuz war Brent +94% peak vs Red Sea campaign -5%), Granger tests
  (conflict does not lead prices), rupee, India import dependence 87.4%, war premium ~US$27 bn, and an out-of-sample test:
  the June I&W call was Red with Brent at $70; Brent then rose 86% to $131.

## Movement layer and news (analysis/12_portwatch.py)
- IMF PortWatch daily transit calls at 28 world chokepoints, 2019 to 16 Aug 2026 (`data/open/imf_portwatch_chokepoints_daily.csv`,
  via the MIT-licensed mirror github.com/ebiisharifi/hormuz-chokepoint-analytics).
- Hormuz transits -92% (73.5 -> 5.8/day), **zero on 4 Mar** when radar saw 337 big hulls inside the Gulf: presence, identity and
  movement triangulated. Other chokepoints -4%. Red Sea evacuation confirmed (Bab-el-Mandeb -55%, Cape of Good Hope +82%).
- Shipping-disruption episodes (frozen prior-year baseline): median 104 days, 62% outlast India's 74-day national cover, vs a
  2.5-week median for conflict flare-ups. Effective cover = stock days / share exposed: stocks bridge; diversification carries.
- Dated open-source chronology (PIB, AIR, Operation Urja Suraksha, The National, Al Jazeera, CNBC, straits.live), full report 9.13.

## Story layer for non-specialist readers (report/story.py)
Written for a tactical commander or senior leader: every chapter carries a story kicker (Prologue, Part I ... Part X, Epilogue),
opens with *The story so far* (linking to the previous chapter) and closes with *So what* plus the question that leads into the
next chapter; every chart has a one-line *What this shows*; a *Data Analytics in Plain Words* glossary explains each technique
with military analogies; the executive summary is told as a six-step story.

## Infographics (report/infographics.py)
Study-at-a-glance page, theatre map with callouts, blinding-vs-diversion pictogram, impact cascade, tri-service impact
cards, I&W traffic-light dashboard, methodology and roadmap SmartArt, and a takeaways strip. HTML + inline SVG icons
(Font Awesome Free, CC BY 4.0), so they print vector-sharp.

## Intelligence-grade layer (analysis/08_intel.py)
- One-page **Executive Summary / BLUF** with key judgements in estimative-probability language and confidence levels.
- **Robustness**: war-zone darkness effect re-estimated under 8 specifications with a scene-cluster bootstrap (RR 3.9-6.4).
- **Dose-response** inside the Gulf: 76% dark within 50 km of fighting -> 43% at 150-200 km (p ~ 1e-27).
- **Analysis of Competing Hypotheses**: deliberate switch-off 0 inconsistencies vs reception gap 5, artefact 6.
- **Own-asset exposure**: 33 Indian-flagged ships visible inside the Gulf war zone in two weeks.
- **Indicators & Warnings matrix** (6 indicators, Amber/Red thresholds, action on Red): 4 Red, 2 Amber at 27 Jun 2026.
- **Scenario matrix** (2/6/12/26-week disruptions) against SPR, national and Service stock holdings.

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
powerbi/      powerbi_tables.zip (star schema, rebuilt by stage 07) + DarkwaterTheme.json + POWERBI_BUILD_GUIDE.md (step-by-step)
report/       build_report.py -> PDF
```

## Reproduce
```bash
pip install pandas numpy scipy statsmodels scikit-learn ruptures matplotlib basemap pyarrow openpyxl pymupdf playwright
# put the two CDM files in data/raw/
python analysis/run_all.py          # ~1 min: figures, tables, metrics, Power BI tables
python report/build_report.py       # full technical report (headless Chromium)
python report/make_screens.py       # software screenshots (pipeline run, code)
python report/build_commander.py    # 20-page Commander's Edition (submission)
```

Placeholders to fill before submission: `[Rank]`, `[Service No]`, `[Unit / Formation]` (top of `report/build_report.py`).
