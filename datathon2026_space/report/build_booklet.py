"""Project HIGH GROUND - the Theme 6.1 booklet (PDF), told as one story for a commander.

Usage:  cd report && python build_booklet.py        (run analysis/run_all.py first)
Every number comes from data/metrics.json (M) and every table from tables/*.csv (T). The final HTML is also saved to
report/_html/ for build_word.py (the editable Word version).
"""

# =====================================================================================================
# ANNOTATED SOURCE - build_booklet.py
# -----------------------------------------------------------------------------------------------------
# 1. build() writes twelve chapters and four annexes as HTML with the Doc engine (booklet_lib.py): each chapter opens with
#    'The story so far' and closes with 'So what' (story.py); charts carry 'What this shows'.
# 2. Chromium prints the body; hidden markers give each heading's page number; the front (title page, at a glance,
#    executive summary, contents) is printed with those numbers, merged in front, and pages are stamped.
# TO EDIT  Your rank, service number and unit: the RANK / SERVICE_NO / UNIT lines below.
# POWER BI SCREENSHOTS  Save as figures/pbi_page1.png ... pbi_page4.png and re-run; Annex C picks them up.
# =====================================================================================================
import re

import pandas as pd

import infographics_space as IG
import story as ST
from booklet_lib import CHROME, CSS, FIG, M, OUT, WORD, Doc, T, fitz, pct, roman, sync_playwright

TITLE = "PROJECT HIGH GROUND"
SUBTITLE = "Contested and Congested: the Crowding of Orbit, and What It Means for India and the Indian Armed Forces"
AUTHOR = "Arjun Jayadev"
RANK, SERVICE_NO, UNIT = "[Rank]", "[Service No]", "[Unit / Formation]"      # EDIT HERE
CLOSE = ST.closings(M)
Q_STORM = 1 - (1 - M["p_intense_hi"]) ** 3          # chance of at least one intense storm in a quarter at high solar activity


def build():
    d = Doc()
    d.kickers, d.opens, d.closes = ST.KICKER, ST.openings(M), CLOSE

    # 1 ---------------------------------------------------------------- the question
    d.chapter("The Question and How We Answered It")
    d.p("Theme 6.1 asks participants to derive insights into the proliferation of satellites and to predict the future trajectory. "
        "This study turns that into five questions a commander would ask: <b>How crowded is orbit? Whose satellites are they? How "
        "dangerous has it become? Who is building military eyes in orbit? And what should India do?</b>")
    d.html_fig(IG.orbits(M), "Orbit at a glance: where the crowds are, from 300 km to 36,000 km (numbers from this study)")
    d.html_fig(IG.methodology(), "How the question was answered")
    d.p(f"The three CDM datasets give a census of <b>{M['cdm_n']:,} active satellites</b> (January 2014), <b>{M['dst_n']:,} hours</b> of "
        f"space-weather records, and <b>{M['fires_n'] / 1e6:.2f} million</b> fire detections by two NASA satellites. Open sources bring the "
        f"story to September 2026: the full public satellite catalogue ({M['satcat_n']:,} objects), the UCS 2020 census and UN launch "
        "registrations. The glossary at Annex A explains each technique in plain words.")

    # 2 ---------------------------------------------------------------- the crowd
    d.chapter("The Crowd")
    d.fig("f2_2_censuses", "Working satellites in three independent censuses: CDM (2014), UCS (2020), satellite catalogue (2026)", width=80)
    d.p(f"In January 2014 about <b>{M['active_2014']:,}</b> satellites were working. By April 2020 there were {M['active_2020']:,}; by "
        f"September 2026 <b>{M['active_now']:,}</b>, a <b>{M['active_mult']:.0f}-fold</b> rise in twelve years. About "
        f"{pct(M['starlink_share'])} of today's working satellites belong to a single constellation, Starlink.")
    d.fig("f2_1_population", "Everything tracked in Earth orbit, 1957-2026: payloads, rocket bodies and debris", width=86)
    d.fig("f2_3_launch_rate", "Satellites launched and rocket launches per year", width=90)
    d.p(f"The launch rate changed gear. In 2013, {M['pay_2013']} satellites were launched; in 2025, <b>{M['pay_2025']:,}</b>. A change-point "
        f"test places the break in <b>{M['growth_cps'][0]}</b>: growth of {M['cagr_2000_2013']:.0f}% a year before the mega-constellations, "
        f"<b>{M['cagr_2019_2025']:.0f}% a year</b> after. Rocket launches rose from {M['launches_2013']} (2013) to {M['launches_2025']} (2025). "
        f"UN registrations track the catalogue almost exactly (correlation {M['unoosa_corr']:.3f}), so the count is sound.")

    # 3 ---------------------------------------------------------------- the owners
    d.chapter("Who Owns Orbit")
    d.fig("f3_1_actors", "Share of working satellites by country, and the largest constellations today", width=92)
    d.p(f"In 2014 the USA operated {M['us_share_2014']:.0f}% of working satellites; today <b>{M['us_share_now']:.0f}%</b>. The concentration "
        f"index (HHI) rose from {M['hhi_country_2014']:,.0f} to <b>{M['hhi_country_now']:,.0f}</b>; anything above 2,500 counts as highly "
        f"concentrated. China grew {M['cn_now'] / M['cn_2014']:.0f}-fold in numbers ({M['cn_2014']} to {M['cn_now']:,}) but held its share "
        f"near 10%. <b>India grew from {M['in_2014']} to {M['in_now']} satellites, but its share fell from {M['in_share_2014']:.1f}% to "
        f"{M['in_share_now']:.1f}%.</b>")
    ct = T("t3_country_share")
    d.table(ct[["Country", "Jan 2014 (CDM)", "Apr 2020 (UCS)", "Sep 2026 (catalogue)", "Jan 2014 (CDM) %", "Sep 2026 (catalogue) %"]],
            "Working satellites by country: 2014, 2020, 2026", small=True)
    d.fig("f3_2_users_purpose", "What satellites are for, and how military each country's fleet is", width=90)
    d.p(f"Commercial users rose from {M['comm_share_2014']:.0f}% of satellites (2014) to {M['comm_share_2020']:.0f}% (2020), while the "
        f"military share fell from {M['mil_share_2014']:.0f}% to {M['mil_share_2020']:.0f}%. That is not demilitarisation: military "
        f"satellites grew in number, and commercial constellations are now used in war (Ukraine has shown this). In 2014, "
        f"{M['mil_ru_2014']:.0f}% of Russian and {M['mil_cn_2014']:.0f}% of Chinese satellites served the military, against "
        f"{M['mil_in_2014']:.0f}% of India's. And {pct(M['beyond_life'])} of the 2014 satellites were already past their design life: "
        "fleets must be renewed continuously just to stand still.")

    # 4 ---------------------------------------------------------------- congestion
    d.chapter("Where It Is Crowded")
    d.fig("f4_1_leo_shells", "Low Earth orbit by altitude, 2014 against 2026", width=90)
    d.p(f"Orbit is crowded in two places. <b>The live crowd</b>: {M['band_now']:,} objects at 450-500 km, {pct(M['band_active_share'])} of "
        f"them working satellites (there were {M['band_2014']} objects there in 2014). <b>The dead crowd</b>: {M['dead_now']:,} objects at "
        f"750-900 km, {pct(M['dead_debris_share'])} of them debris. A kinetic-gas model, in which collisions grow with the square of the "
        f"number of objects at each height, puts the <b>collision-risk index at about {M['risk_ratio']:.0f} times</b> the 2014 level.")
    d.fig("f4_2_geo_arc", "The geostationary belt by longitude; the shaded arc is the one India uses", width=88)
    d.p(f"Higher up, the geostationary arc used by India (40-110 E) held <b>{M['geo_arc20']}</b> satellites in 2020, "
        f"{pct(M['geo_arc_share20'])} of the whole belt, up from {M['geo_arc14']} in 2014. China ({M['geo_arc_cn20']}) and the USA "
        f"(33) each had more there than India ({M['geo_arc_in20']}). Slots and radio frequencies over India are a contested resource.")
    d.fig("f4_3_asat_debris", "Debris from weapon tests and the 2009 collision: share still in orbit, year by year", width=86)
    at = T("t4_asat_debris")
    d.table(at[["Event", "Date", "Pieces catalogued", "Still in orbit (Sep 2026)", "Still in orbit %"]],
            "Weapon tests and collisions: debris created and debris remaining", small=True)
    d.p(f"<b>Altitude decides the legacy.</b> China's 2007 test at about 865 km made {M['fy1c_pieces']:,} tracked pieces; "
        f"<b>{M['fy1c_alive_pct']:.0f}% are still in orbit</b> nearly twenty years later. India's 2019 test (Mission Shakti) was done at "
        f"about 280 km: all {M['shakti_pieces']} pieces have re-entered, most within half a year. Russia's 2021 test "
        f"({M['ru1408_pieces']:,} pieces) has almost cleared. A responsible test is a low one; a high one poisons an orbit for a generation.")
    d.section("4.1", "Close Calls: Screening Every Satellite for a Day")
    d.fig("f12_1_conjunctions", "Close approaches under 5 km found by screening current orbits with the SGP4 propagator", width=90)
    d.p(f"To see the congestion directly, every active satellite in low orbit ({M['cj_A_n']:,}) was propagated with SGP4, the standard "
        "model for published orbital elements, every 10 seconds for 24 hours, and every pair was checked. A second screening pitted "
        f"freshly tracked satellites against the four largest debris clouds. In <b>one day</b>: <b>{M['cj_A_cross_diff'] + M['cj_A_cross_same']:,} "
        f"crossing encounters closer than 5 km</b> between satellites ({M['cj_A_under1']} under 1 km), {pct(M['cj_cross_starlink_share'])} of them "
        f"involving Starlink, typically at {M['cj_median_speed']:.0f} km/s; and <b>{M['cj_B_total']} encounters between satellites and weapon-test "
        f"or collision debris</b> ({M['cj_B_under1']} under 1 km). The closest pass found was {M['cj_min_miss'] * 1000:.0f} m.")
    ib = T("t12_india_encounters")
    ib = ib[ib.screen.str.startswith("B")].head(8)
    d.table(ib[["name_a", "name_b", "miss_km", "rel_speed_kms", "alt_km"]].rename(columns={
        "name_a": "Indian satellite", "name_b": "Debris object", "miss_km": "Miss distance (km)", "rel_speed_kms": "Relative speed (km/s)",
        "alt_km": "Altitude (km)"}).round(2), "Indian satellites passing within 5 km of weapon-test and collision debris, 23-24 Sep 2026", small=True)
    d.p(f"<b>{M['cj_B_india']} Indian satellites had such a pass in a single day</b>, including EMISAT (electronic intelligence), HySIS, SARAL "
        "and Oceansat-3, mostly against debris from the 2009 Iridium-Cosmos collision and China's 2007 test. Public elements are accurate "
        "to about a kilometre, so this is screening, not collision probability, but it is exactly the daily watch ORBITWATCH would run.")

    # 5 ---------------------------------------------------------------- the contest
    d.chapter("The Contest")
    d.fig("f5_1_isr_race", "Military and state intelligence satellites: launched since 2000, and working today", width=92)
    d.p(f"Grouping satellites by their official programme names gives a transparent lower bound. China operates about "
        f"<b>{M['cn_isr_ops']}</b> state and military imaging, intelligence and technology satellites ({M['yaogan_ops']} of them Yaogan "
        f"military reconnaissance), and has launched about <b>{M['cn_isr_rate_2023_25']:.0f} a year</b> since 2023. The USA has added "
        f"{M['us_nnn_2024_26']} national-security payloads since 2024. India operates about <b>{M['in_isr_ops']}</b> and launches fewer than "
        f"one a year. The ratio is about <b>{M['cn_in_ratio']:.0f} to 1</b>.")
    it = T("t5_isr_families")
    d.table(it, "Military and state-ISR programme families (name-based lower bound)", small=True)
    d.p(f"India's answer is <b>SBS-III</b>: 52 surveillance satellites approved in 2023 (Rs 26,968 crore), 21 built by ISRO and 31 by "
        f"industry, due by 2029. Against today's gap, SBS-III closes only about <b>{pct(M['sbs3_close'])}</b>. During Operation Sindoor "
        "(May 2025) ten Indian satellites supported the forces round the clock: the need is proven, the capacity is thin.")
    d.section("5.1", "Can Physics Reveal a Military Satellite?")
    d.fig("f11_1_ml_military", "Machine learning on the CDM census: predicting military use from orbit, mass and power", width=90)
    d.p(f"Names and registrations can hide a satellite's role; physics cannot. A model trained on the {M['ml_n_train']:,} satellites of the "
        f"CDM census ({M['ml_pos_train']} military or dual-use) learns military use from orbit, mass, power and design life alone, never "
        f"the name, purpose or owner. Tested on {M['ml_n_test']:,} satellites launched <b>after</b> the census (UCS 2020), it scores "
        f"<b>ROC-AUC {M['ml_ext_auc']:.2f}</b> (0.5 = coin toss). Launch mass and apogee give a satellite away most.")
    d.table(T("t11_ml_results"), "Model skill: cross-validation on 2014 against the out-of-time test on later launches", small=True)
    d.p(f"<b>The honest test changed the answer.</b> Ordinary cross-validation favoured gradient-boosted trees (ROC-AUC "
        f"{M['ml_cv_auc_gbt']:.2f}), but on later satellites they fell to {M['ml_ext_auc_gbt']:.2f}; the simpler logistic model held at "
        f"{M['ml_ext_auc']:.2f} and was chosen. Adding the operator's country did not help ({M['ml_ext_auc_full']:.2f}): <i>what</i> a satellite "
        f"is says more than <i>whose</i> it is. The model flags <b>{M['ml_dual_n']} ({pct(M['ml_dual_share'])})</b> of the later 'civil' or "
        "'commercial' satellites as military-like, led by navigation satellites with encrypted government services: the dual-use blur "
        "in numbers, and a triage tool for any new object in the catalogue.")

    # 6 ---------------------------------------------------------------- space weather
    d.chapter("The Natural Adversary")
    d.fig("f6_1_storms", "Geomagnetic storms and solar activity (CDM space-weather data)", width=90)
    d.p(f"The CDM records hold {M['storm_events']} storms, {M['storm_intense']} of them intense and {M['storm_severe']} severe (lowest "
        f"Dst {M['dst_min']} nT). When the Sun is active (sunspot number 100 or more), the chance of an intense storm in any 30 days is "
        f"<b>{pct(M['p_intense_hi'])}</b>, against {pct(M['p_intense_lo'])} when it is quiet: about <b>{M['storm_mult']:.0f} times</b>. A "
        f"Poisson model gives {M['storm_irr50']:.2f} times the storm rate for every 50 more sunspots (p &lt; 0.001).")
    d.fig("f6_2_reentry_cycle", "The solar cycle in the debris record: share of low-orbit debris re-entering each year", width=86)
    d.p(f"A heated upper atmosphere drags satellites down. A periodogram of re-entry rates finds a <b>{M['reentry_period']:.0f}-year "
        f"cycle</b> without being told to look for one: the Sun's cycle. At solar maximum {M['reentry_max']:.1f}% of low-orbit debris "
        f"re-enters each year, against {M['reentry_min']:.1f}% at minimum. The same drag killed 38 new Starlink satellites in a moderate "
        "storm in February 2022, and the May 2024 'Gannon' superstorm (Dst -412 nT) forced mass orbit corrections. Solar cycle 25 peaked "
        "in October 2024 and storms remain frequent through 2026.")

    # 7 ---------------------------------------------------------------- EO value
    d.chapter("What Eyes in Orbit Buy")
    d.fig("f7_2_fire_map", "Fire and heat detections by NASA's Terra and Aqua satellites over the USA, 2010-2020 (CDM data)", width=84)
    d.fig("f7_1_eo_value", "Coverage, persistence and early warning from two satellites", width=94)
    d.p(f"Terra passes in the morning and Aqua in the afternoon. Put every detection on a 10-km grid, one cell per day: <b>{pct(M['prem_single'])} "
        f"of fire-days were seen by only one of the two</b> ({pct(M['prem_aqua_only'])} Aqua only, {pct(M['prem_terra_only'])} Terra only). "
        f"A single satellite would have missed nearly half of what the pair saw. Thermal sensors also see at night "
        f"({pct(M['night_share'])} of detections). They pick out {M['industrial_cells']} persistent industrial heat sources, such as steel "
        "mills and smelters, and they followed Kilauea's 2018 eruption to its end.")
    d.p(f"A seasonal baseline flags abnormal months, the logic of any warning system: {M['surges_n']} surges stand out, the largest "
        f"in {M['surge_top']} (z = {M['surge_top_z']:.1f}). <b>For the Services the lesson is direct: persistence comes from numbers.</b> "
        "Revisit, not resolution alone, decides whether a mobilisation, a launcher or a convoy is caught in time.")

    # 8 ---------------------------------------------------------------- forecast
    d.chapter("The Trajectory to 2030")
    d.fig("f8_1_forecast", "Satellites in orbit to 2030: statistical trend, scenarios and the collision-risk index", width=92)
    sc = T("t8_scenarios_2030")
    d.table(sc, "Working satellites in 2030 under three deployment scenarios (assumptions stated)", small=True)
    d.p(f"Two independent routes agree. A damped-trend forecast of satellites in orbit reaches about <b>{M['fc_2030_mid']:,}</b> in 2030 "
        f"(80% range {M['fc_2030_lo']:,}-{M['fc_2030_hi']:,}); it missed 2022-2026 by only {M['fc_bt_mape']:.1f}% when tested on held-back "
        f"years. A bottom-up build from the announced constellations gives <b>{M['sc_low']:,} / {M['sc_base']:,} / {M['sc_high']:,}</b> working "
        f"satellites (low / base / high). The collision-risk index rises to about <b>{M['risk_2030_base']:.0f} times</b> the 2014 level in the "
        f"base case and {M['risk_2030_high']:.0f} times in the high case. China's shells at 1,050-1,200 km are the concern: debris there "
        "stays for centuries.")

    # 9 ---------------------------------------------------------------- inference
    d.chapter("Inference: What We Know and How Sure We Are")
    d.table(T("t9_robustness"), "Every headline finding checked by an independent route", small=True)
    kj = pd.DataFrame([
        ("Almost certain", "More than 20,000 satellites will be working by 2030 (even the low scenario).", "High"),
        ("Highly likely", f"Collision risk in low orbit keeps rising: index {M['risk_2030_low']:.0f}-{M['risk_2030_high']:.0f} times 2014 by 2030.", "Moderate"),
        ("Highly likely", "China's lead in state ISR satellites over India persists through 2029, even with SBS-III.", "High"),
        ("Likely", f"At least one intense geomagnetic storm per quarter while sunspots stay above 100 ({pct(Q_STORM)}).", "Moderate"),
        ("Realistic possibility", "Another debris-creating event (collision, break-up or weapon test) in a crowded shell by 2030.", "Moderate"),
        ("Almost certain", "More satellites buy coverage: one satellite misses much of what a constellation sees.", "High"),
        ("Almost certain", f"Indian satellites pass within 5 km of weapon-test and collision debris every day ({M['cj_B_india']} in one day).", "Moderate"),
    ], columns=["How likely", "Judgement", "Confidence"])
    d.table(kj, "Key judgements (intelligence estimative language)", small=True)
    d.p("The judgements use the estimative language of intelligence assessments. Confidence reflects the data: counts from the "
        "catalogue are high-confidence; the 2030 scenarios depend on company and state deployment plans and are moderate.")

    # 10 --------------------------------------------------------------- impact
    d.chapter("What It Means for the World, India and the Armed Forces")
    d.p("<b>For the world:</b> orbit is becoming a commons run by a few operators. A single company's decisions now shape the "
        "collision risk for everyone, and commercial constellations have become military assets in war. Norms on debris and weapon "
        "tests lag far behind the traffic.")
    d.table(T("t9_india_scorecard").fillna("-"), "India against China and the USA", small=True)
    d.fig("f9_1_launch_capacity", "Access to space: rocket launches per year from US, Chinese and Indian soil", width=82)
    d.p(f"<b>For India:</b> national dependence on space grows (banking, navigation, communications, disaster warning), while India's share "
        f"of working satellites has fallen to {M['in_share_now']:.1f}% and it launched {M['launches_2025_in']} rockets in 2025 against "
        f"China's {M['launches_2025_cn']}. Over 2021-25 China averaged about {M['launch_ratio']:.0f} times India's launch rate. Access "
        "to space is the bottleneck.")
    d.html_fig(IG.triservice(M), "Impact on the Indian Navy, Air Force and Army, and the joint response")
    d.p("<b>For the Armed Forces:</b> the adversary can now watch continuously; our own satellites face collisions, storms and "
        "counterspace threats; and operations increasingly assume space support that may be denied. Plans must assume <b>being "
        "watched</b> and <b>losing some space services</b>.")

    # 11 --------------------------------------------------------------- way forward
    d.chapter("Way Forward")
    R = pd.DataFrame([
        ("Stand up ORBITWATCH: daily close-approach screening (demonstrated in 4.1) and the 7-indicator warning matrix from open, ISRO NETRA and commercial data",
         "DSA with ISRO (NETRA)", "4 months", "An actionable conjunction or threat warning acted upon"),
        ("Accelerate SBS-III and buy commercial imagery and radar capacity for persistent revisit of the northern borders and IOR",
         "DSA, NSIL, IN-SPACe, industry", "2026-2029", "Revisit time over priority areas"),
        ("Resilience by design: manoeuvre capability, collision-avoidance fuel and storm hardening for every new military satellite",
         "DSA, ISRO, DRDO", "Contracts from 2027", "Share of fleet able to manoeuvre"),
        ("Space-weather cell: storm warnings to all Services; drills for degraded GNSS and HF communications",
         "HQ IDS, IAF Met, ISRO", "6 months", "Drill conducted each quarter"),
        ("Rapid reconstitution: SSLV launch slots and spare satellites on standby",
         "ISRO, NSIL, DSA", "2-3 years", "Days to replace a lost satellite"),
        ("Protect GEO slots and ITU filings in the 40-110 E arc; interference monitoring",
         "DoT, ISRO, DSA", "Ongoing", "Filings secured; interference cases resolved"),
        ("Concealment and deception doctrine against persistent satellite ISR for field formations",
         "Army, HQ IDS", "12 months", "Exercised in field formations"),
    ], columns=["Action", "Lead", "Timeline", "Measure of effectiveness"])
    d.table(R, "Seven staffed actions, traced to the evidence", small=True)
    d.html_fig(IG.orbitwatch(M, T("t9_orbitwatch")), "ORBITWATCH: the seven-indicator warning matrix at September 2026")
    d.html_fig(IG.roadmap(), "Three-phase plan")

    # 12 --------------------------------------------------------------- conclusion
    d.chapter("Conclusion")
    d.html_fig(IG.takeaways(M), "Five takeaways")
    d.p("<b>The high ground has become a crowd.</b> In twelve years orbit went from about a thousand working satellites to seventeen "
        "thousand, owned mostly by one country and one company, circling in shells where collision risk has multiplied and where "
        "weapon debris can linger for decades. China is filling it with eyes; the Sun periodically lashes it. India, which "
        "depends on space more every year, holds a shrinking share of it. The remedy is not a single prestige satellite but "
        "numbers, resilience and awareness: SBS-III at pace, satellites that can manoeuvre and survive, and a standing ORBITWATCH so that "
        "India always knows what is overhead.")

    # annexes -----------------------------------------------------------------------------------
    d.chapter("Annex A - Data Analytics in Plain Words", letter="A")
    d.table(pd.DataFrame(ST.GLOSSARY, columns=["Term", "What it means, in plain words"]), "Glossary of techniques and terms", small=True)

    d.chapter("Annex B - Technical Summary for Assessors", letter="B")
    d.p("Every technique used, the question it answers and the key result. All results are regenerated from the raw data by one "
        "command (analysis/run_all.py), and two consecutive runs give identical outputs.")
    TS = pd.DataFrame([
        ("Validation and cleaning: Excel-date conversion, impossible periods/inclinations removed, code look-ups, duplicate removal",
         "Is the evidence sound?", f"{M['bad_period']} impossible periods and {M['bad_incl']} impossible inclination corrected; 1 duplicate fire removed", "Ch 1"),
        ("Year-end population rebuilt from launch and re-entry dates; three independent censuses", "How crowded is orbit?",
         f"{M['active_2014']:,} to {M['active_now']:,} working satellites", "Ch 2"),
        ("Change-point detection (PELT); compound growth rates; cross-check with UNOOSA", "When did growth change gear?",
         f"Break {M['growth_cps'][0]}; {M['cagr_2000_2013']}% to {M['cagr_2019_2025']}% a year; r = {M['unoosa_corr']}", "Ch 2"),
        ("Herfindahl-Hirschman concentration index", "Is control of orbit spreading or concentrating?",
         f"HHI {M['hhi_country_2014']:,.0f} to {M['hhi_country_now']:,.0f}", "Ch 3"),
        ("Altitude-shell spatial density; kinetic-gas collision-risk index (sum n^2 / V)", "How dangerous has orbit become?",
         f"Index x{M['risk_ratio']}", "Ch 4"),
        ("Survival curves of debris by event", "How long does weapon debris last?", f"FY-1C {M['fy1c_alive_pct']}% remaining; Shakti 0%", "Ch 4"),
        ("Name-based programme families (transparent lower bound)", "Who is building military eyes?", f"China {M['cn_isr_ops']} vs India {M['in_isr_ops']}", "Ch 5"),
        ("Storm event detection (Dst thresholds); Poisson regression; Spearman correlation", "Does solar activity raise storm risk?",
         f"Rate ratio {M['storm_irr50']} per +50 sunspots; odds x{M['storm_mult']}", "Ch 6"),
        ("Periodogram of de-trended re-entry rate", "Does the solar cycle show in debris decay?", f"{M['reentry_period']}-year cycle", "Ch 6"),
        ("Grid-day matching of detections (0.1 deg); seasonal baseline z-scores", "What does a constellation add?",
         f"{pct(M['prem_single'])} of fire-days seen by one satellite only", "Ch 7"),
        ("Holt damped-trend smoothing with 2,000 simulations and back-test; bottom-up scenarios", "What comes by 2030?",
         f"{M['fc_2030_mid']:,} (trend); {M['sc_base']:,} (base); back-test {M['fc_bt_mape']}%", "Ch 8"),
        ("Logistic regression and gradient-boosted trees; repeated stratified CV; out-of-time test on UCS 2020 launches; permutation importance",
         "Can physics reveal a military satellite?", f"Out-of-time ROC-AUC {M['ml_ext_auc']} (trees {M['ml_ext_auc_gbt']}); {M['ml_dual_n']} dual-use flags", "Ch 5.1"),
        ("SGP4 propagation every 10 s for 24 h; k-d tree pair screening (80 km); 1-s refinement and linearised closest approach",
         "How often do satellites nearly collide?", f"{M['cj_cross_total']:,} encounters < 5 km in two screenings; {M['cj_B_india']} Indian vs debris", "Ch 4.1"),
        ("Indicators and warnings matrix (ORBITWATCH)", "What should be watched?", f"{M['ow_red']} Red, {M['ow_amber']} Amber", "Ch 11"),
    ], columns=["Technique", "Commander's question", "Key result", "Chapter"])
    d.table(TS, "Techniques, questions and results", small=True)
    d.table(T("t1_cleaning_log"), "Data cleaning log", small=True)

    d.chapter("Annex C - Software Used and Screenshots", letter="C")
    d.p("<b>Stack:</b> Python 3.11 (pandas, NumPy, SciPy, statsmodels, scikit-learn, ruptures, sgp4, Matplotlib) for analysis; headless Chromium for the "
        "booklet; Microsoft Power BI Desktop for the dashboard (.pbix) built on the exported tables (FactCatalogue, FactSatellites2014, "
        "FactStormDaily, FactFiresMonthly, DimDate and the analysis tables).")
    d.fig("screen_pipeline", "Screenshot: the complete pipeline run, raw data to every chart and table", width=100)
    d.fig("screen_code", "Screenshot: code excerpt, altitude shells and the collision-risk index", width=100)
    slot = ('<div style="border:1.5pt dashed #9aa5ae;border-radius:4pt;height:150pt;display:flex;align-items:center;justify-content:center;'
            'color:#6b6a66;font-family:Liberation Sans,sans-serif;font-size:10pt;text-align:center">{t}</div>')
    pbi = [("Orbit Growth", "working satellites, launches and population by year"), ("Owners and Contest", "country shares and ISR families"),
           ("Congestion", "altitude shells, GEO arc and debris events"), ("Space Weather and Warning", "storms, re-entries and ORBITWATCH")]
    for k, (name, what) in enumerate(pbi, 1):
        cap = f"Screenshot: Power BI dashboard, page {k} - {name} ({what})"
        if (FIG / f"pbi_page{k}.png").exists():
            d.fig(f"pbi_page{k}", cap, width=100)
        else:
            d.html_fig(slot.format(t=f"[ Insert screenshot: Power BI page {k} - {name} ]"), cap)

    d.chapter("Annex D - References and Data Sources", letter="D")
    refs = [
        "College of Defence Management (2026). Datathon-2026 General Instructions and Theme 6.1 datasets (satellite census; Dst and sunspot records; MODIS fire detections).",
        "CelesTrak Satellite Catalogue (SATCAT), T.S. Kelso; public mirror github.com/astrion-tech/celestrak-mirror, accessed 24 Sep 2026.",
        "Union of Concerned Scientists (2020). UCS Satellite Database, 1 April 2020 edition (via github.com/nfrontero20/satellites).",
        "UNOOSA Online Index of Objects Launched into Outer Space, via Our World in Data (TidyTuesday, 23 Apr 2024).",
        "ESA Space Debris Office (2025). ESA's Annual Space Environment Report 2025.",
        "Kessler, D.J., Cour-Palais, B.G. (1978). Collision frequency of artificial satellites: the creation of a debris belt. <i>JGR</i> 83(A6), 2637-2646.",
        "Gonzalez, W.D. et al. (1994). What is a geomagnetic storm? <i>JGR</i> 99(A4), 5771-5792.",
        "SILSO, Royal Observatory of Belgium: international sunspot number; NASA/NOAA joint solar maximum announcement, 15 Oct 2024.",
        "Hapgood, M. et al. (2022). Unexpected space weather causing the reentry of 38 Starlink satellites in February 2022. <i>J. Space Weather Space Clim.</i>",
        "Giglio, L., Schroeder, W., Justice, C.O. (2016). The Collection 6 MODIS active fire detection algorithm and fire products. <i>Remote Sensing of Environment</i> 178, 31-41.",
        "Killick, R., Fearnhead, P., Eckley, I.A. (2012). Optimal detection of changepoints with a linear computational cost. <i>JASA</i> 107, 1590-1598.",
        "Hyndman, R.J., Athanasopoulos, G. (2021). <i>Forecasting: Principles and Practice</i>, 3rd ed. (damped trend methods).",
        "U.S. Department of Justice and FTC (2023). Merger Guidelines (HHI concentration thresholds).",
        "Vallado, D.A., Crawford, P., Hujsak, R., Kelso, T.S. (2006). Revisiting Spacetrack Report #3. AIAA 2006-6753 (SGP4); CelesTrak GP data in CCSDS OMM format via github.com/satvisorcom/satvisor-data.",
        "Hoots, F.R., Crawford, P.S., Roehrich, R.L. (1984). An analytical method to determine future close approaches between satellites. <i>Celestial Mechanics</i> 33, 143-158.",
        "Open-source reporting: All India Radio News (ISRO Chairman on Operation Sindoor, 9 Sep 2025); Outlook Business (SBS-III, 52 satellites, Rs 26,968 crore); "
        "KeepTrack (Starlink count, Sep 2026); OrbitalRadar (Guowang and Qianfan, 2026); NOAA SWPC (solar cycle 25).",
        "Jayadev, A. (2021). <i>Predictive Maintenance in Armed Forces: A Machine Learning Based Decision Support System</i>. M.Tech report, IIT Kharagpur.",
    ]
    d.add('<ol style="font-size:9.5pt;line-height:1.35;padding-left:18pt">' + "".join(f"<li style='margin-bottom:3pt;text-align:left'>{r}</li>" for r in refs) + "</ol>")
    return d


def main():
    body = build()
    css_extra = """
body { font-size: 11pt; line-height: 1.4; }
h1.chapter { font-size: 14pt; margin: 18pt 0 10pt 0; page-break-before: auto; break-before: auto; border-top: 1.5pt solid #1f3b5c; padding-top: 8pt; page-break-after: avoid; break-after: avoid; }
.kicker, .story { page-break-after: avoid; break-after: avoid; }
table.tbl.small td, table.tbl.small th { padding: 2pt 4pt; }
figure { margin: 6pt 0 8pt 0; } .story, .sowhat { font-size: 10.5pt; padding: 6pt 9pt; }
"""
    style = f"<style>{CSS}{IG.CSS}{css_extra}</style>"
    html_body = f"<!doctype html><html><head><meta charset='utf-8'>{style}</head><body>{''.join(body.parts)}</body></html>"
    with sync_playwright() as p:
        br = p.chromium.launch(executable_path=CHROME)

        def render(h, path):
            pg = br.new_page()
            pg.set_content(h, wait_until="load")
            pg.pdf(path=str(path), format="A4", print_background=True, margin={"top": "20mm", "bottom": "18mm", "left": "20mm", "right": "18mm"})
            pg.close()

        render(html_body, OUT / "_bbody.pdf")
        bd = fitz.open(OUT / "_bbody.pdf")
        pages = {}
        for i, pg_ in enumerate(bd):
            for mk in re.findall(r"@@([A-Z0-9_]+)@@", pg_.get_text()):
                pages.setdefault(mk, i + 1)
            hits = [w for w in pg_.get_text("words") if "@@" in w[4]]
            for w in hits:
                pg_.add_redact_annot(fitz.Rect(w[:4]), fill=False)
            if hits:
                pg_.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)
        toc = "".join(f'<tr class="l1"><td class="t">{lab}&nbsp;&nbsp;{title}</td><td class="pg">{pages.get(mid, "")}</td></tr>'
                      for mid, lvl, lab, title in body.sec if lvl == 1)
        front = f"""<div class="titlepage" style="padding-top:10mm">
<div class="t3">COLLEGE OF DEFENCE MANAGEMENT &middot; DATATHON - 2026</div>
<div class="t3" style="margin-bottom:20pt">Theme 6.1: Contested and Congested &ndash; Growth of Satellites in Outer Space</div>
<div class="t1">{TITLE}</div><div class="t2" style="margin-bottom:6pt">{SUBTITLE}</div>
<div class="t2" style="margin-bottom:14pt;font-style:normal;font-weight:bold">Commander's Edition</div>
<div class="t3" style="font-size:10.5pt;max-width:80%;margin:0 auto 18pt auto">How crowded orbit has become since 2014, who owns it, how
dangerous it is, who is building military eyes in it, what nature adds, where it is heading by 2030, and what India and its
Armed Forces should do. Told as one story, in plain words.</div>
<div class="t3">Submitted by</div><div class="t3"><b>{RANK} {AUTHOR.upper()}</b></div><div class="t3">{SERVICE_NO} &middot; {UNIT}</div>
<div class="t3" style="margin-top:18pt">September 2026</div>
<div class="t3" style="margin-top:40pt;font-size:9.5pt;color:#444">Companion files: Power BI dashboard (.pbix), analysis code and data</div></div>
<div class="front pb"><h1>THE STUDY AT A GLANCE</h1>{IG.at_a_glance(M)}</div>
<div class="front pb es"><h1>EXECUTIVE SUMMARY</h1>{ST.exec_summary_story(M)}</div>
<div class="front pb"><h1>CONTENTS</h1><table class="toc">{toc}</table>
<p style="font-size:10pt;margin-top:14pt">Each chapter opens with <b>The story so far</b> and closes with <b>So what</b>; every chart carries
<b>What this shows</b>. A commander can read the Executive Summary and the coloured boxes alone in about ten minutes.</p></div>"""
        front_doc = f"<!doctype html><html><head><meta charset='utf-8'>{style}</head><body>{front}</body></html>"
        render(front_doc, OUT / "_bfront.pdf")
        WORD.mkdir(exist_ok=True)       # final HTML kept for the editable Word version (build_word.py)
        (WORD / "booklet_front.html").write_text(front_doc)
        (WORD / "booklet_body.html").write_text(html_body)
        br.close()
    fr = fitz.open(OUT / "_bfront.pdf")
    doc = fitz.open()
    doc.insert_pdf(fr)
    doc.insert_pdf(bd)
    nf = len(fr)
    for i, pg_ in enumerate(doc):
        if i == 0:
            continue
        w, h = pg_.rect.width, pg_.rect.height
        label = roman(i + 1) if i < nf else str(i - nf + 1)
        pg_.insert_text((w / 2 - 6, h - 24), label, fontsize=9.5, fontname="times-roman")
        pg_.insert_text((57, 36), "CDM Datathon-2026  |  Theme 6.1  |  Contested and Congested: Growth of Satellites in Outer Space",
                        fontsize=7.2, fontname="helv", color=(0.45, 0.45, 0.45))
        pg_.draw_line((57, 41), (w - 51, 41), color=(0.75, 0.75, 0.75), width=0.4)
    doc.set_metadata({"title": f"{TITLE.title()} - Commander's Edition", "author": AUTHOR})
    out = OUT / "Datathon2026_Theme6.1_Satellites_Booklet.pdf"
    doc.save(out, garbage=4, deflate=True)
    for f in ("_bbody.pdf", "_bfront.pdf"):
        (OUT / f).unlink()
    print("pages:", len(doc), "front:", nf, "->", out)


if __name__ == "__main__":
    main()
