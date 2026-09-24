# Power BI dashboard - step-by-step build guide (Theme 6.1, .pbix)

Power BI Desktop (free, Windows) is the only tool that saves a `.pbix`. Everything else is ready here; the build takes 60-90 minutes.

## Step 0 - Prepare (5 min)
1. Unzip `powerbi_tables.zip` into one folder, e.g. `D:\HighGround\`.
2. Open Power BI Desktop. **File > Options > Security**: tick *Use Map and Filled Map visuals*. **Regional settings > Import**: *English (United States)*.
3. Optional: **View > Themes > Browse for themes** and load `DarkwaterTheme.json` from the Theme 6.2 folder for the same colours.
4. **File > Save as** `Datathon2026_Theme6.1_Satellites.pbix`.

## Step 1 - Load the data (10 min)
Use **Home > Get data > Text/CSV** once for each file:

| Load | Used on page |
|---|---|
| `t2_population_by_year.csv`, `t2_launches_by_country.csv`, `t2_active_censuses.csv`, `DimDate.csv` | 1 Orbit Growth |
| `t3_country_share.csv`, `t5_isr_families.csv`, `FactCatalogue.csv` | 2 Owners and Contest |
| `t4_leo_shells.csv`, `t4_asat_debris.csv`, `t4_geo_arc_india.csv`, `FactSatellites2014.csv` | 3 Congestion |
| `FactStormDaily.csv`, `t6_reentry_rate.csv`, `t9_orbitwatch.csv`, `t8_scenarios_2030.csv`, `t8_risk_index.csv` | 4 Space Weather and Warning |

In **Table view** set `LAUNCH_DATE`, `DECAY_DATE` (FactCatalogue) and `DATE` (DimDate) to **Date**. Mark `DimDate` as a date table.

## Step 2 - Link (2 min)
**Model view**: drag `FactCatalogue[LAUNCH_DATE]` onto `DimDate[DATE]` (many-to-one). The `t...` tables stay unlinked.

## Step 3 - Measures (5 min)
Select FactCatalogue, **Home > New measure**, one line at a time:
```DAX
Objects            = COUNTROWS(FactCatalogue)
Working satellites = CALCULATE([Objects], FactCatalogue[operational] = TRUE(), FactCatalogue[type] = "Payload")
In orbit           = CALCULATE([Objects], ISBLANK(FactCatalogue[DECAY_DATE]))
Debris in orbit    = CALCULATE([In orbit], FactCatalogue[type] = "Debris")
Share of working   = DIVIDE([Working satellites], CALCULATE([Working satellites], ALL(FactCatalogue[owner])))
```
Format `Share of working` as a percentage.

## Step 4 - Four pages (40-60 min)
Each page gets a title text box with its one-line message.

**1 Orbit Growth** · *"15 times more working satellites since 2014."*
- Stacked area: `t2_population_by_year[year]`; values Payload, Rocket body, Debris.
- Column: `t2_active_censuses` (Date, Active satellites).
- Stacked column: `t2_launches_by_country` year × USA/China/India/Russia/Europe.
- Cards: `Working satellites`, `In orbit`.

**2 Owners and Contest** · *"One country and one company own most of orbit."*
- Clustered column: `t3_country_share` Country × the two % columns.
- Bar: `Working satellites` by `FactCatalogue[owner]` (Top N filter = 10).
- Bar: `Working satellites` by `FactCatalogue[constellation]` (exclude "Other").
- Table: `t5_isr_families`.
- Slicer: `FactCatalogue[type]`.

**3 Congestion** · *"A live crowd, a dead crowd, and collision risk x10."*
- Stacked column: `t4_leo_shells[Shell (km)]` × Active 2026 / Debris 2026.
- Line: Objects 2014.
- Bar: `t4_asat_debris` Event × Still in orbit %.
- Column: `t4_geo_arc_india`.
- Scatter: `FactSatellites2014` Perigee_km vs Apogee_km, legend Class_of_Orbit.

**4 Space Weather and Warning** · *"Storm odds x7 at solar maximum; 6 of 7 indicators Red."*
- Line: `FactStormDaily[day]` × `min_dst`, slicer on `period`.
- Line: `t6_reentry_rate`.
- Table: `t9_orbitwatch`, with conditional formatting on Status.
- Column: `t8_risk_index`.
- Table: `t8_scenarios_2030`.

## Step 5 - Save and take screenshots
1. Press **Ctrl+S**.
2. On each page, press **Win+Shift+S** around the canvas and save the snip as `pbi_page1.png` to `pbi_page4.png`.
3. Send them in the chat, or copy them to `datathon2026_space/figures/` and run `python report/build_booklet.py` and `python report/build_word.py`. Annex C fills in automatically.
