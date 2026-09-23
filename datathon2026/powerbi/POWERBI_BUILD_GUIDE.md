# Power BI dashboard - build guide (.pbix)

The Datathon asks for the output as a Power BI `.pbix` file. A `.pbix` can only be saved by Power BI Desktop,
so this folder holds everything needed to build it in about 30 minutes. Unzip `powerbi_tables.zip` here first
(or regenerate the tables with `python analysis/run_all.py`).

## 1. Load data (Home > Get data > Text/CSV)
| File | Notes |
|---|---|
| `FactConflictWeekly.csv` | set `WEEK` = Date; `EVENTS`, `FATALITIES` = Whole number |
| `DimAdmin1.csv` | `LAT` / `LON` -> Data category Latitude / Longitude |
| `FactVesselDetections.csv` | `DATE` = Date; `lat` / `lon` -> Latitude / Longitude; `AIS_DARK`, `LARGE_100M` = True/False |
| `DimDate.csv` | Mark as date table on `DATE` |
| `t6_ccii_weekly.csv`, `t6_2_episodes.csv`, `t7_4_dark_clusters.csv`, `t8_3_poi_risk.csv`, `t9_1_stock_decision.csv`, `t7_1_dark_by_region.csv`, `t8_2_model_cv.csv` | analysis outputs, stand-alone |

## 2. Relationships (Model view)
- `FactConflictWeekly[ADMIN1_ID]` *:1 `DimAdmin1[ADMIN1_ID]`
- `FactConflictWeekly[WEEK]` *:1 `DimDate[DATE]`
- `FactVesselDetections[DATE]` *:1 `DimDate[DATE]`

## 3. Measures (New measure)
```DAX
Events            = SUM(FactConflictWeekly[EVENTS])
Fatalities        = SUM(FactConflictWeekly[FATALITIES])
PV Events         = CALCULATE([Events], FactConflictWeekly[POLITICAL_VIOLENCE] = TRUE())
Stand-off share   = DIVIDE(CALCULATE([Events], FactConflictWeekly[DRONE_MISSILE] = TRUE(),
                                     FactConflictWeekly[POLITICAL_VIOLENCE] = TRUE()), [PV Events])
Detections        = COUNTROWS(FactVesselDetections)
Dark detections   = CALCULATE([Detections], FactVesselDetections[AIS_DARK] = TRUE())
Dark share        = DIVIDE([Dark detections], [Detections])
Dark share large  = CALCULATE([Dark share], FactVesselDetections[LARGE_100M] = TRUE())
World large dark  = CALCULATE([Dark share large], FactVesselDetections[ZONE] = "Rest of world")
Dark RR vs world  = DIVIDE([Dark share large], [World large dark])
```
What-if parameter: *Modeling > New parameter* `Stock days` (0-120, step 5) and a card that looks up
`t9_1_stock_decision` (or bins it) to show the expected uncovered days.

## 4. Pages
1. **Conflict Pulse** - line: `PV Events` by `DimDate[WEEK_START]`; stacked column: `Events` by YEAR x EVENT_TYPE;
   map: bubbles at `DimAdmin1` LAT/LON sized by `Events`; slicers: COUNTRY, GCC, date range; card: `Stand-off share`.
2. **Chokepoint Watch** - line: the four CCII theatre columns from `t6_ccii_weekly` by WEEK; table: `t6_2_episodes`;
   cards: episodes, median weeks.
3. **Dark Ships** - map: `FactVesselDetections` lat/lon, legend `AIS_DARK`; bar: `Dark share large` by REGION;
   clustered column: `Dark share` by `size_class` x ZONE; table: `t7_4_dark_clusters`; card: `Dark RR vs world`.
4. **Decision** - table/line: `t9_1_stock_decision`; bar: `t8_3_poi_risk`; the `Stock days` what-if card.

Save as `Datathon2026_Global_Conflicts_Supply_Chains.pbix`, then take screenshots of each page for the submission.
