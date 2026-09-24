# Power BI dashboard - step-by-step build guide (.pbix)

The Datathon wants the dashboard as a Power BI `.pbix` file (Gen Instr Para 8.2). A `.pbix` can only be saved by
**Power BI Desktop** (free, Windows only). Everything else is ready in this folder, so the build takes 60-90 minutes.

**You need:** a Windows PC; Power BI Desktop (Microsoft Store, "Power BI Desktop", free, no login needed);
`powerbi_tables.zip` and `DarkwaterTheme.json` from this folder.

---

## Step 0 - Prepare (5 min)
1. Make a folder, e.g. `D:\Darkwater\`, and unzip `powerbi_tables.zip` into it (24 CSV files). Copy `DarkwaterTheme.json` there too.
2. Open Power BI Desktop. If it offers to sign in, close that box.
3. **File > Options and settings > Options > Security > Map and Filled Map visuals:** tick *Use Map and Filled Map visuals*, then click OK.
4. **File > Options > Regional settings > Import:** choose *English (United States)* so that dates such as 2026-03-04 load correctly.
5. **View > Themes > Browse for themes** and pick `DarkwaterTheme.json`. The colours will then match the report.
6. **File > Save as** `Datathon2026_Global_Conflicts_Supply_Chains.pbix`. Press Ctrl+S often after this.

## Step 1 - Load the data (10 min)
**Home > Get data > Text/CSV**, pick a file, then click **Load**. Do this for each file below. Power BI loads one file at a time,
so repeat the steps for each.

| Load this file | Used on page |
|---|---|
| `FactConflictWeekly.csv`, `DimAdmin1.csv`, `DimDate.csv` | 1 Conflict Pulse |
| `t6_ccii_weekly.csv`, `FactChokepointTransits.csv`, `t12_1_chokepoint_change.csv`, `t12_2_shipping_disruptions.csv` | 2 Chokepoint Watch |
| `FactVesselDetections.csv`, `t7_1_dark_by_region.csv`, `t7_4_dark_clusters.csv` | 3 Dark Ships |
| `t9_1_stock_decision.csv`, `t12_3_effective_cover.csv`, `t8_3_poi_risk.csv`, `t9_6_iw_matrix.csv` | 4 Decision |

Then check the data types. Click **Table view** (the grid icon on the left), select the column, and set **Column tools > Data type**:
- `WEEK` (FactConflictWeekly), `DATE` (DimDate, FactVesselDetections, FactChokepointTransits) → **Date**
- `LAT`, `LON` (DimAdmin1) and `lat`, `lon` (FactVesselDetections) → **Column tools > Data category** → *Latitude* / *Longitude*
- `AIS_DARK`, `LARGE_100M`, `POLITICAL_VIOLENCE`, `DRONE_MISSILE`, `GCC` → **True/False**. They usually load as True/False already.
- Select **DimDate**, then **Table tools > Mark as date table** and choose `DATE`.

## Step 2 - Link the tables (5 min)
Click **Model view** (the third icon on the left). Drag one column onto the other to create each link:
- `FactConflictWeekly[ADMIN1_ID]` → `DimAdmin1[ADMIN1_ID]`
- `FactConflictWeekly[WEEK]` → `DimDate[DATE]`
- `FactVesselDetections[DATE]` → `DimDate[DATE]`
- `FactChokepointTransits[DATE]` → `DimDate[DATE]`

Each line should read *many-to-one (\*:1)*. The `t...` tables stay unlinked, and that is correct.

## Step 3 - Measures (10 min)
Select the table named in brackets, click **Home > New measure**, paste one line and press Enter. Repeat for each line.
```DAX
Events            = SUM(FactConflictWeekly[EVENTS])                                   -- FactConflictWeekly
PV Events         = CALCULATE([Events], FactConflictWeekly[POLITICAL_VIOLENCE] = TRUE())
Stand-off share   = DIVIDE(CALCULATE([Events], FactConflictWeekly[DRONE_MISSILE] = TRUE(),
                           FactConflictWeekly[POLITICAL_VIOLENCE] = TRUE()), [PV Events])
Detections        = COUNTROWS(FactVesselDetections)                                   -- FactVesselDetections
Dark detections   = CALCULATE([Detections], FactVesselDetections[AIS_DARK] = TRUE())
Dark share        = DIVIDE([Dark detections], [Detections])
Dark share large  = CALCULATE([Dark share], FactVesselDetections[LARGE_100M] = TRUE())
World large dark  = CALCULATE([Dark share large], FactVesselDetections[ZONE] = "Rest of world")
Dark RR vs world  = DIVIDE([Dark share large], [World large dark])
Transits          = SUM(FactChokepointTransits[TRANSITS])                             -- FactChokepointTransits
Transits 7d avg   = AVERAGEX(DATESINPERIOD(DimDate[DATE], MAX(DimDate[DATE]), -7, DAY), [Transits])
Uncovered days    = SELECTEDVALUE(t9_1_stock_decision[Expected uncovered days])        -- t9_1_stock_decision
P outlasts stock  = SELECTEDVALUE(t9_1_stock_decision[P(disruption outlasts stock) %]) / 100
```
Format the measures. Select a measure, then in **Measure tools** set `Stand-off share`, `Dark share`, `Dark share large` and
`P outlasts stock` to **Percentage** with 0 decimals. Set `Dark RR vs world` to 1 decimal.

## Step 4 - Build the four pages (40-60 min)
Add a page with the **+** tab at the bottom, and double-click the tab to rename it. To add a visual, click the page, click the visual
icon in the **Visualizations** pane, then drag fields from the **Data** pane into its wells. For each page, add a **Text box**
(Insert > Text box) at the top with the page title and the one-line message shown in italics below.

### Page 1 - Conflict Pulse · *"War nearly tripled violence; 84% was missiles and drones."*
| Visual | Settings |
|---|---|
| Line chart | X-axis `DimDate[WEEK_START]`; Y-axis `PV Events` |
| Stacked column chart | X-axis `DimDate[YEAR]`; Y-axis `Events`; Legend `FactConflictWeekly[EVENT_TYPE]` |
| Map | Latitude `DimAdmin1[LAT]`; Longitude `DimAdmin1[LON]`; Bubble size `Events` |
| Card | `Stand-off share` |
| Slicers (×3) | `DimAdmin1[COUNTRY]`; `DimAdmin1[GCC]`; `DimDate[DATE]` (it becomes a date-range slider) |

Test it: drag the date slider to 28 Feb - 10 Apr 2026. The map should light up around the Gulf.

### Page 2 - Chokepoint Watch · *"Zero ships crossed Hormuz on 4 March; shipping disruptions last months."*
| Visual | Settings |
|---|---|
| Line chart | X-axis `t6_ccii_weekly[WEEK]`; Y-axis the four columns `Hormuz (littoral)`, `Red Sea / Arabian Sea (at sea)`, `East Med (at sea)`, `Black Sea (at sea)` (set each to *Sum*) |
| Line chart | X-axis `DimDate[DATE]`; Y-axis `Transits 7d avg`; filter pane: `FactChokepointTransits[CHOKEPOINT]` = *Strait of Hormuz* (you can also add Bab el-Mandeb Strait and Cape of Good Hope to the legend) |
| Clustered bar chart | Y-axis `t12_1_chokepoint_change[Chokepoint]`; X-axis `Change %` (Sum); sort ascending |
| Table | all columns of `t12_2_shipping_disruptions` |
| Slicer | `FactChokepointTransits[CHOKEPOINT]` |

### Page 3 - Dark Ships · *"74% of big ships at Hormuz were dark against about 10% in peaceful seas."*
| Visual | Settings |
|---|---|
| Map | Latitude `FactVesselDetections[lat]`; Longitude `[lon]`; Legend `[AIS_DARK]`. Power BI draws a sample of points, which is expected. |
| Clustered bar chart | Y-axis `FactVesselDetections[REGION]`; X-axis `Dark share large`; sort descending |
| Clustered column chart | X-axis `[size_class]`; Y-axis `Dark share`; Legend `[ZONE]` |
| Table | `t7_4_dark_clusters`: Cluster, region, Dark large vessels, Dark share of large ships within 30 km |
| Cards (×2) | `Dark share large`; `Dark RR vs world` |
| Slicers | `FactVesselDetections[ZONE]`; `DimDate[DATE]` |

Test it: pick *Gulf war zone* in the ZONE slicer. `Dark share large` should read about 60%.

### Page 4 - Decision · *"Stocks bridge; diversification carries."*
| Visual | Settings |
|---|---|
| Slicer (single select) | `t9_1_stock_decision[Stock (days)]`. In Format > Slicer settings, set Style to *Tile* and turn on *Single select*. |
| Cards (×2) | `Uncovered days`; `P outlasts stock` |
| Line chart | X-axis `t9_1_stock_decision[Stock (days)]`; Y-axis `Expected uncovered days` (Sum) |
| Line chart | X-axis `t12_3_effective_cover[Exposure]`; Y-axis the three columns (SPR only / National cover / Parliamentary target) |
| Clustered bar chart | Y-axis `t8_3_poi_risk[Location]`; X-axis `Predicted P(dark), 180 m ship` |
| Table | `t9_6_iw_matrix` (the DARKWATCH warning signals). You can use *Conditional formatting > Background colour* on the status column. |

Test it: click 30 on the stock slicer, then 45. The uncovered days should drop, which is the 35-45-day argument in the report.

**Polish (optional, 10 min):** keep the same title text box on every page (copy and paste it). Align visuals with **Format > Align**.
Under **View**, choose Page view > *Fit to page*.

## Step 5 - Save and take the screenshots (5 min)
1. **Ctrl+S.** The `.pbix` should be about 5-15 MB. Test it by closing Power BI and reopening the file.
2. For each page, click the page tab, click on empty canvas and press **Win+Shift+S**. Drag a box around the whole report canvas,
   leaving out the side panes. Then open the snip, choose **Save as** and give it the name below:
   `pbi_page1.png` (Conflict Pulse), `pbi_page2.png` (Chokepoint Watch), `pbi_page3.png` (Dark Ships), `pbi_page4.png` (Decision).
   Before taking each snip, set a meaningful filter so the picture tells the story. For example, use the war window on page 1 and
   *Gulf war zone* on page 3.

## Step 6 - Put the screenshots in Annex C
Annex C fills in automatically. Either:
- **Send the four PNGs in this chat**, and the Commander's Edition will be rebuilt with them; or
- copy them into `datathon2026/figures/` and run `python report/build_commander.py`. Each dashed slot in Annex C is replaced by the
  screenshot of the same name. Any file you have not supplied yet keeps its slot.

## Step 7 - Submit (Gen Instr Para 8)
Email to datathon.ids@gov.in by 30 Sep: the Commander's Edition PDF, the `.pbix` and, as an annex, the full technical report.
Keep the `.pbix` name the same as in Step 0.
