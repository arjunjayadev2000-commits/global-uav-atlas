"""Commander's Edition - a ~20-page version of the report for a commander or senior leader.

Same evidence, same numbers (data/metrics.json), same charts; told as one story in ten short chapters, each opening with
'The story so far' and closing with 'So what'. The full report remains the technical annex.
"""
import base64
import re

import pandas as pd

import build_report as BR
from build_report import AUTHOR, FIG, IG, M, OUT, RANK, SERVICE_NO, ST, T, UNIT, fitz, pct, roman, sync_playwright

KICK = {1: "Prologue - the question", 2: "Part I - the storm gathers", 3: "Part II - the storm reaches the sea lanes",
        4: "Part III - the ships go blind", 5: "Part IV - the bill arrives", 6: "Part V - what we know, and how sure we are",
        7: "Part VI - what it means for the world and for India", 8: "Part VII - what it means for the Armed Forces",
        9: "Part VIII - what we should do", 10: "Epilogue"}

OPEN = {
    1: "On 28 February 2026 war reached the shores of the Strait of Hormuz, the passage for about a fifth of the world's oil and a large part of "
       "India's. This edition answers five questions a commander would ask: what happened, what did it do to the ships, what did it cost, "
       "how sure are we, and what should we do?",
    2: "The story begins on land. Before the war reached the sea, it changed in size, in weapons and in geography.",
    3: "The war had moved to the Gulf's energy coast and was being fought with missiles and drones. The next question: did it reach the sea "
       "lanes, and how long do such crises last?",
    4: "Violence reached the waters around Hormuz and the Red Sea, and such crises can outlast our reserves. What did the ships do? "
       "Satellite radar sees every ship, whether or not it wants to be seen.",
    5: "Ships near the fighting switched off their identities or stayed away. A supply chain is ultimately about goods and money, so "
       "we follow the shock to the oil price, the rupee and India's import bill.",
    6: "The evidence is complete. Before acting on it, a good staff officer asks: are we sure, and could something else explain it?",
    7: "Having established what we know and how sure we are, we turn to what it means: first for the world, then for India.",
    8: "The same shocks that hit India's economy reach its Armed Forces through fuel, spares, threats to bases and the need to protect citizens abroad.",
    9: "The story has shown what happens, how long it lasts, what it costs and whom it hurts. Now: what to do, what to watch, and in what order.",
    10: "We end where we began, with the commander's questions, now answered with evidence.",
}
CLOSE = {
    1: ("Two datasets from CDM (11 years of conflict events; 106,533 ships seen by satellite radar) plus four open-source datasets (oil price, rupee, "
        "India's oil balance, world ports), tested with standard analytics and intelligence tradecraft.", "How did the conflict itself change?"),
    2: (f"The war nearly tripled violence ({M['pv_war_ratio']:.1f}x). 84% of it was delivered by missiles and drones, and it hit the Gulf states that export "
        f"the world's energy ({M['gcc_multiplier']:.0f}x).", "Did it reach the sea lanes?"),
    3: (f"Yes. Violence around Hormuz reached {M['hormuz_war_mult']:.0f}x its normal level, and in the Red Sea it moved from shore to sea. Most crises end in "
        f"weeks, but {pct(M['km_p_gt_spr'])} outlast India's emergency oil reserve.", "What did the ships do?"),
    4: (f"Big ships went dark: {pct(M['hormuz_large_dark'])} at Hormuz against about 10% in peaceful seas. They did not simply leave; many were held "
        "at anchor with identities off. The same war produced four behaviours at sea, and a model can forecast where darkness will appear.", "What did it cost?"),
    5: (f"Oil went from ${M['brent_prewar']:.0f} to ${M['brent_war_peak']:.0f}, the rupee weakened, and India's oil bill rose by about "
        f"US${M['extra_bill_usd_bn']:.0f} billion. Our warning signals stayed Red when the market relaxed, and oil then rose {M['brent_oos_change']:.0f}%.",
        "How sure are we?"),
    6: ("Very sure of the main finding. It holds however it is measured, grows stronger closer to the fighting, repeats in another war, "
        "and no other explanation fits.", "What does it mean for the world and for India?"),
    7: ("For the world, chokepoint war is a recurring cost and a hazard at sea. For India the exposure is concentrated in oil, westbound "
        "trade, connectivity projects and nine million citizens in the Gulf.", "And for the Armed Forces?"),
    8: ("Fuel and spares stocks sized on evidence, rear areas defended against drones and missiles, navigation that does not depend on GPS, "
        "and a joint watch on the chokepoints.", "What should we do, and in what order?"),
    9: ("Eleven staffed actions, the DARKWATCH watch-list and a three-phase plan that starts at no new cost and stops if it does not help a decision.", None),
}
PL = ST.PLAIN


def build():
    d = BR.Doc()
    d.kickers, d.opens, d.closes = KICK, OPEN, CLOSE

    # 1 ---------------------------------------------------------------- the question
    d.chapter("The Question and How We Answered It")
    d.html_fig(IG.theatre_map(M, base64.b64encode((FIG / "base_theatre.png").read_bytes()).decode()),
               "The theatre: India's western sea lanes, the chokepoints and the headline findings")
    d.html_fig(IG.methodology(), "How the question was answered")
    d.p("The two CDM datasets are the <b>ACLED</b> conflict record (every reported attack, battle and protest in the Middle East, week by week, "
        "2015 to June 2026) and <b>Sentinel-1 satellite radar</b> detections of 106,533 ships in the first fortnight of the war, each checked "
        "against the ship's identity beacon (AIS). Open-source oil-price, exchange-rate and energy data (to September 2026) measure the cost. "
        "The glossary at the end explains every technique in plain words.")

    # 2 ---------------------------------------------------------------- the storm gathers
    d.chapter("The Storm Gathers")
    d.fig("f5_4_changepoints", "Weekly political violence, 2015-2026, with the dates the 'battle rhythm' changed", width=96)
    d.p(f"Without being told any dates, the computer found the weeks when the conflict changed: <b>7 October 2023</b> (the Gaza war) and "
        f"<b>28 February 2026</b> (the regional war). In the war weeks violence ran at <b>{M['pv_war_ratio']:.1f} times</b> the previous year's level. "
        "<b>84%</b> of it was delivered from a distance, by missiles, drones and artillery.")
    d.fig("f5_7_war_map", "Where the violence fell, 28 February - 10 April 2026", width=78)
    d.p(f"The fighting reached the <b>shore of the Strait of Hormuz</b> (Hormozgan province: 229 attacks, 215 deaths in six weeks). The Gulf states, "
        f"which had seen almost no violence, were struck every week: <b>{M['gcc_multiplier']:.0f} times</b> their pre-war rate.")

    # 3 ---------------------------------------------------------------- reaches the sea lanes
    d.chapter("The Storm Reaches the Sea Lanes")
    d.fig("f6_5_offshore", "Red Sea: attacks on land fell while attacks at sea rose", width=82)
    d.p(f"A 'thermometer' of violence was built for each sea route. Around Hormuz it reached <b>{M['hormuz_war_mult']:.0f} times</b> its normal level. "
        f"In the Red Sea the threat <b>moved offshore</b>: attacks at sea rose from {M['sea_2022']} (2022) to {M['sea_2024']} (2024) while the land war faded. "
        "A land-only measure would have shown the Red Sea getting safer just as it became the most dangerous waterway for merchant ships.")
    d.fig("f12_4_duration", "Two clocks: fighting near a sea lane (orange) against the shipping disruption it causes (blue), 2019-2026", width=80)
    d.p(f"<b>There are two clocks.</b> Flare-ups of fighting near a sea lane usually end within weeks (median {M['ep_median_wk']:.1f} weeks), although "
        f"{pct(M['km_p_gt_spr'])} still outlast India's strategic petroleum reserve (about 9.5 days). The <b>shipping disruption they cause lasts months</b>: "
        f"the IMF's daily transit counts for 28 world chokepoints show a median of {M['ship_ep_median']:.0f} days, and "
        f"<b>{pct(M['ship_p_gt_74'])} outlasted India's total national cover</b> of about 74 days. The Red Sea disruption ran {M['ship_ep_max'] / 30.4:.0f} months; "
        f"Hormuz had been shut {M['closure_days']} days when the record ended. The danger is not the spike but its duration.")

    # 4 ---------------------------------------------------------------- the ships go blind
    d.chapter("The Ships Go Blind")
    d.fig("f7_2_dark_by_region", "Share of ships with their identity beacon off, by sea (right panel: big ships only)", width=86)
    d.p(f"Small boats run without beacons everywhere, so the test that matters is <b>big ships (100 m and over)</b>, which must carry one by law. "
        f"In peaceful seas about 1 in 10 is dark. At <b>Hormuz it was {pct(M['hormuz_large_dark'])}</b>, in the Persian Gulf {pct(M['pg_large_dark'])}, "
        f"and in the Black Sea, the other war zone, {pct(M['black_large_dark'])}. Big ships in war zones were <b>{M['large_rr']:.1f} times</b> as likely "
        "to be dark.")
    d.fig("f11_1_presence_identity", "Did the ships leave or go silent? Same sea area at Hormuz, imaged on 4 and 12 March", width=80)
    d.p(f"<b>The ships did not simply leave.</b> On the same patch of sea, AIS-transmitting big hulls fell {abs(M['pi_lit_chg'])}% while radar saw the "
        f"physical fleet fall only {abs(M['pi_radar_chg'])}%, and the dark fleet did not shrink at all. Many dark hulls were <b>held at anchor</b>: seen in "
        f"the same 100 m square on different days far more than chance allows (z = {M['stasis_dark_z']}). An AIS-based traffic count therefore "
        "overstated the collapse of shipping and hid the collapse of the maritime picture.")
    d.fig("f12_1_hormuz_transits", "Third witness: ships crossing the Strait of Hormuz each day (IMF PortWatch), 2025-2026", width=80)
    d.p(f"<b>A third, independent source settles it.</b> The IMF's daily count of ships crossing Hormuz fell from about {M['pw_base']:.0f} a day to "
        f"{M['pw_post']:.0f} ({M['pw_drop']:.0f}% down); on <b>4 March it was {M['pw_zero_4mar']}</b>, the very day radar counted {M['pi_radar_1']} big hulls "
        f"inside the Gulf. Ships were there (radar), a growing share hid who they were (AIS), and almost none crossed (transits). "
        f"<b>The fleet was held, silent, inside the Gulf.</b> Other chokepoints barely moved ({M['pw_ctrl_change']:+.0f}%), so this was Hormuz, not the world.")
    d.html_fig(IG.signatures(M, T("t11_6_signatures")), "Four behaviours at sea: the same war produced concealment, evacuation, a frozen sea and compliance")
    d.fig("f7_6_dbscan", "Where dark ships gather: tanker queues off Dubai and Fujairah, and in the Black Sea", width=76)
    d.fig("f8_3_risk_surface", "Forecast: where a 180 m merchant ship is likely to go dark", width=76)
    d.p(f"A machine-learning model, trained on 62,000 ships and tested only on seas it had never seen, forecasts where ships will go dark "
        f"(score {M['auc_gbt']:.2f}, where 0.5 is a coin toss). After a ship's size, <b>distance from the fighting</b> is the strongest clue. "
        "It is good enough to point satellites at the right waters.")

    # 5 ---------------------------------------------------------------- the bill arrives
    d.chapter("The Bill Arrives")
    d.fig("f9o_2_event_study", "Oil price after four Middle-East shocks (day 0 = the day before each began)", width=80)
    d.p(f"Only the war that reached Hormuz produced a lasting shock: <b>Brent +{M['ev_war_peak']:.0f}%</b> within 40 days, from "
        f"${M['brent_prewar']:.0f} to a peak of ${M['brent_war_peak']:.0f}. The Red Sea campaign, where ships could detour, left oil <i>lower</i> "
        "a month later. The market confirms the signatures of Chapter 4: concealment where there is no detour produces a price shock; evacuation where "
        "there is a detour produces a freight shock instead.")
    wp = T("t9o_3_war_premium")
    d.table(wp, "What the war cost India (open-source data)", small=True)
    d.p(f"India imports <b>{M['india_dep']:.0f}%</b> of its oil, and the share is rising. The war added about <b>US${M['extra_bill_usd_bn']:.0f} billion "
        f"(Rs {M['extra_bill_inr_lakh_cr']:.1f} lakh crore)</b> to the oil bill in {M['war_days']} days. Every US$10 a barrel for a year costs about "
        f"US${M['per10_usd_bn']:.1f} billion.")
    d.p(f"<b>In defence terms:</b> in March 2026 the extra oil bill equalled <b>{M['def_ratio_mar_lo'] * 100:.0f}-{M['def_ratio_mar_hi'] * 100:.0f}% of the whole "
        f"monthly defence budget</b>; in April it reached {M['def_ratio_apr_hi'] * 100:.0f}%.")
    d.callout(f"<b>Could we have seen it coming?</b> On 26 June 2026, when the conflict data end, the oil market looked calm: Brent was back at "
              f"${M['brent_at_cut']:.0f}. The six warning signals built in this study all read Red or Amber and said <i>hold the buffers</i>. "
              f"Oil then rose <b>{M['brent_oos_change']:.0f}%</b> to ${M['brent_last']:.0f} by {M['brent_last_date']}. The dip had a cause the transit data show: in late June a few ships crossed and Hormuz traffic briefly climbed to about a third of normal, "
              f"then fell back to {M['pw_last30_pct']:.0f}% of normal. The data saw what the market missed.")

    # 6 ---------------------------------------------------------------- inference
    d.chapter("Inference: What We Know and How Sure We Are")
    d.fig("f9_3_dose_response", "The closer to the fighting, the more big ships went dark (Gulf war zone)", width=78)
    d.p(f"Four tests make the main finding solid. (1) It holds under <b>eight different ways</b> of measuring it (war zones {M['rob_min_rr']:.1f} to "
        f"{M['rob_max_rr']:.1f} times darker). (2) It gets <b>stronger nearer the fighting</b>, from {pct(M['dose_0_50'])} within 50 km to 43% at 150-200 km. "
        "(3) It <b>repeats in a separate war</b> (Black Sea). (4) Of four possible explanations (deliberate switch-off, GPS jamming, radio "
        "reception gaps, computer error), only <b>deliberate switch-off</b> fits all the evidence. (5) It survives removing the "
        f"{M['alldark_n']} passes that were entirely dark (a possible feed outage) and holds by day and by night. (6) The Gulf darkened "
        f"{M['did_excess']:.1f} points a day faster than 11 control seas (p = {M['did_p']:.3f}). A failed identity match proves the picture failed; "
        "it cannot prove intent, so that judgement is held at 'likely'.")
    KJ = pd.DataFrame([
        ("Almost certain", "The war caused big ships to go dark.", "High"),
        ("Likely", "Most of the darkness is deliberate switch-off; GPS jamming probably adds to it.", "Moderate"),
        ("Highly likely", "The Hormuz coast stays in crisis, at least on and off, through September 2026.", "Moderate"),
        ("Likely", f"A sea-lane crisis outlasts India's emergency oil reserve ({pct(M['km_p_gt_spr'])} of cases).", "Moderate"),
        ("Almost certain", "Drones and missiles will remain the main threat to rear-area logistics and energy sites.", "High"),
        ("Highly likely", "Conflict and satellite signals warn earlier than market prices.", "Moderate"),
    ], columns=["How likely", "Judgement", "Confidence"])
    d.table(KJ, "Key judgements (intelligence estimative language)", small=True)

    # 7 ---------------------------------------------------------------- world and India
    d.chapter("What It Means for the World and for India")
    d.add("<h3>For the world</h3>")
    d.bullets([
        "<b>Energy:</b> about a fifth of the world's oil passes Hormuz. Chokepoint risk is now a recurring cost, not a rare event.",
        "<b>Trade:</b> where a detour exists, conflict adds 10-14 days per Asia-Europe voyage and raises freight and insurance costs.",
        "<b>Safety at sea:</b> when most big ships are dark, collision avoidance, rescue and identification fail, and neutral ships risk being mistaken for targets.",
        "<b>Shadow fleets:</b> flags often linked to sanctions evasion are about three times over-represented among visible ships in war zones, but the dark fleet is mainly mainstream shipping: the problem is the whole fleet's behaviour, not a rogue fleet.",
    ])
    d.add("<h3>For India</h3>")
    d.html_fig(IG.impact_cascade(M), "How the shock travels from the strait to India's import bill and the Armed Forces")
    d.html_fig(IG.cog(M), "India's centre of gravity at sea, with the vulnerabilities this study measured")
    d.bullets([
        f"<b>Energy:</b> {M['india_dep']:.0f}% of oil is imported, much of it through Hormuz, which has no detour. Only buffers and other suppliers help.",
        "<b>Trade:</b> the Red Sea diversion lengthens and raises the cost of India's westbound exports.",
        "<b>Connectivity:</b> the Chabahar corridor and IMEC run through the theatres studied.",
        f"<b>People:</b> about nine million Indians live in the Gulf states, where violence rose {M['gcc_multiplier']:.0f}-fold. At least "
        f"{M['ind_gulf_ships']} Indian-flag ships were inside the Gulf war zone.",
        "<b>Home waters:</b> India's own seas hold thousands of small boats without beacons, so coastal security cannot rely on AIS.",
    ])

    # 8 ---------------------------------------------------------------- Armed Forces
    d.chapter("What It Means for the Indian Armed Forces")
    d.html_fig(IG.triservice(M), "Impact on the Indian Navy, Air Force and Army")
    d.fig("f9_1_stock_cover", "How much stock is enough? Risk of running dry and average days short, by days of stock held", width=82)
    sc = T("t9_7_scenarios")
    d.table(sc[["Scenario", "Duration", "P(disruption lasts at least this long)", "Days beyond national cover (74 d)",
                "Days beyond 30 d / 45 d Service holdings"]], "Planning scenarios for a Hormuz or Red Sea disruption", small=True)
    d.p(f"<b>For Service stocks, a six-week crisis is the planning case</b>: roughly 1 in 5 flare-ups last that long. It leaves a 30-day holding 12 days short, while "
        f"45 days covers it fully. Beyond about {M['stock_knee_days']} days each extra day of stock buys little. Hence 35-45 days for fuel, "
        "aviation fuel and critical spares.")
    d.fig("f12_5_effective_cover", "Effective cover = days of stock / share of supply behind the closed chokepoint", width=76)
    d.p(f"<b>For supply, the planning case is months, and stocks cannot carry it.</b> A stock only has to replace the share of supply that is cut off. "
        f"At India's pre-war exposure of about 45% to Hormuz, 74 days of national cover lasts about {M['cover_74_at45']} days; cut the exposure to 30% "
        f"and it lasts {M['cover_74_at30']} days, longer than the {M['closure_days']}-day closure so far. <b>Stocks bridge; diversification carries.</b> "
        "For the Services this means 35-45 days of holdings plus a second source for every critical fuel and spare.")

    # 9 ---------------------------------------------------------------- way forward
    d.chapter("Way Forward")
    R = pd.DataFrame([
        ("Maritime Picture Assurance as a named joint warning function; SDR and DARKWATCH as weekly products.", "HQ IDS with IFC-IOR", "4 months", "A principal acts on a DARKWATCH warning"),
        ("Standing rule: no AIS-derived traffic count for a contested corridor without a radar cross-check.", "HQ IDS", "Immediate", "Rule issued; cited in assessments"),
        ("Fuse national satellite radar (NISAR, EOS-04) with AIS to flag every dark big ship automatically.", "Navy (IFC-IOR), DSA", "6-18 months", "Dark hulls cued within 24 h of a pass"),
        ("Treat AIS identity as untrusted: automatic checks for cloned or fake identities.", "Navy (IFC-IOR)", "6 months", "Checks shared with ports and insurers"),
        ("Know the small-boat population in India's seas: transponders, coastal radar, satellite radar.", "Navy, Coast Guard, MoFAH", "18 months", "Share of small craft identifiable"),
        ("Size strategic oil and LPG reserves on crisis-duration evidence; diversify away from Hormuz.", "MoPNG with MEA", "12 months", "Cover set on the survival curve"),
        ("Re-set fuel, aviation-fuel and critical-spares War Wastage Reserves for all three Services at 35-45 days.", "HQ IDS (Log)", "6 months", "Days of cover within the band"),
        ("Air defence and counter-drone cover for depots, railheads, air bases and fuel points; GPS-denied fallback.", "Army, IAF", "3 years, rolling", "Critical nodes covered; drills done"),
        ("Keep the Gulf evacuation plan (Navy sealift, IAF airlift, Army reception) ready while signals are Amber or Red.", "HQ IDS with MEA", "3 months", "Time to first lift from alert"),
        ("Indigenise first the items that come through Hormuz or the Red Sea with long lead-times.", "DDP, Services", "Rolling", "Exposure-weighted list adopted"),
        ("Archive corridor satellite imagery and write up what shipping did after every chokepoint crisis.", "HQ IDS, CDM", "After each crisis", "Report within 90 days"),
    ], columns=["Action", "Lead", "Timeline", "Measure of effectiveness"])
    d.table(R, "Eleven staffed actions, each traced to the evidence", small=True)
    iwt = T("t9_6_iw_matrix")
    d.html_fig(IG.iw_dashboard(M, iwt), "DARKWATCH: the six-signal watch-list at 27 June 2026, and what happened next")
    d.html_fig(IG.roadmap(), "Three-phase plan")

    # 10 --------------------------------------------------------------- conclusion
    d.chapter("Conclusion")
    d.html_fig(IG.takeaways(M), "Five takeaways")
    d.p("<b>The first casualty of war at a chokepoint is visibility.</b> Physical disruption follows, lasts longer than intuition suggests, "
        "and reaches India's energy, trade, citizens and military sustainment. The same data that measured it can warn of it. Turned into a "
        "standing weekly watch, the tools built here let India and its Armed Forces decide on evidence rather than precedent. That is the aim "
        "of this Datathon.")
    d.add(f'<div class="story"><span class="lab">Where to find the detail</span>The full technical report (method, all charts and tables, '
          f'robustness tests, references) and the Power BI dashboard accompany this edition. Every number here is reproduced there, and can be '
          f'regenerated from the raw data with one command.</div>')

    # glossary (short)
    d.chapter("Annex A - Data Analytics in Plain Words", letter="A")
    d.add(ST.glossary_html())

    # technical summary for assessors
    d.chapter("Annex B - Technical Summary for Assessors", letter="B")
    d.p("For assessors: every technique used, the plain question it answers, the key result, and where the full method, tests and "
        "tables appear in the accompanying technical report. All results are regenerated from raw data by one command, and the pipeline "
        "is deterministic (two consecutive runs give identical outputs).")
    TS = pd.DataFrame([
        ("Validation, cleaning, feature engineering; BallTree haversine spatial join", "Is the evidence sound?",
         f"{M['acled_rows']:,} conflict rows; {M['sar_rows']:,} ships; {M['sar_low_conf_dropped']} low-confidence detections dropped", "Ch 4"),
        ("Change-point detection (PELT, L2 cost); Mann-Whitney U", "When did the battle rhythm change?",
         f"7 Oct 2023, 28 Feb 2026, 11 Apr 2026; war regime {M['pv_war_ratio']:.1f}x (p = {M['mw_p']:.0e})", "5.1"),
        ("Chokepoint Conflict Intensity Index; ARIMA with 12-week back-test and 4,000 simulations", "Is the sea lane under stress, and will it stay so?",
         f"Hormuz littoral {M['hormuz_war_mult']:.0f}x baseline; {pct(M['fc_prob_above_thr'])} of simulated paths breach by Sep 2026", "6.1-6.2"),
        ("Survival analysis: Kaplan-Meier, Cox proportional hazards, log-rank", "How long do crises last?",
         f"Median {M['ep_median_wk']:.1f} wk; {pct(M['km_p_gt_spr'])} exceed SPR; {pct(M['km_p_gt_74d'])} exceed 74 days", "6.3"),
        ("Wilson intervals, chi-square, relative risk, odds ratio", "Are war-zone ships really darker?",
         f"RR {M['large_rr']:.1f}, OR {M['large_or']:.1f}, p &lt; 10<sup>-300</sup>", "7.1"),
        ("Getis-Ord Gi* local hot-spot statistic", "Where do dark ships cluster?", f"{M['gulf_hot_cells']} significant cells, Qatar-Hormuz belt", "7.2"),
        ("DBSCAN density clustering (haversine)", "Where do they wait?", f"{M['n_clusters']} clusters; Dubai {pct(M['top_cluster_share'])} dark", "7.3"),
        ("Logistic regression; gradient-boosted trees with monotonic constraints; leave-one-region-out CV", "Can we forecast darkness?",
         f"ROC-AUC {M['auc_gbt']:.2f} on unseen seas (random CV {M['auc_gbt_random']:.2f}, reported as leakage)", "Ch 8"),
        ("Event study; Granger causality; pass-through regression; import-bill model", "What did it cost, and do prices warn?",
         f"Brent +{M['ev_war_peak']:.0f}% peak; no price lead (p &gt; 0.4); ~US${M['extra_bill_usd_bn']:.0f} bn to India", "9.2-9.7"),
        ("Scene-cluster bootstrap (8 specifications); dose-response logit; Analysis of Competing Hypotheses", "How sure are we?",
         f"RR {M['rob_min_rr']:.1f}-{M['rob_max_rr']:.1f}; {pct(M['dose_0_50'])} to 43% with distance; switch-off 0 inconsistencies", "10.4-10.6"),
        ("Expected shortfall from the survival curve; scenario matrix", "How much stock is enough?",
         f"Returns flatten at ~{M['stock_knee_days']} days; 45 days covers the 6-week case", "13.5-13.6"),
        ("Presence vs identity on a common footprint; stasis index against a crowding null", "Did ships leave or go silent?",
         f"AIS {M['pi_lit_chg']}% vs radar {M['pi_radar_chg']}%; dark hulls held in place (z = {M['stasis_dark_z']})", "7.8"),
        ("Scene-level difference-in-differences with 5,000 permutations; all-dark and day/night checks", "Did the Gulf change more than elsewhere?",
         f"+{M['did_excess']:.1f} pts/day vs controls (p = {M['did_p']:.3f}); RR {M['rr_excl_alldark']:.1f} without all-dark passes", "10.4"),
        ("Flag-retention shift (chi-square); rule-based signature assignment", "Who kept transmitting; what kind of event is it?",
         f"Gulf flags {M['flag_littoral_1']:.0f}% to {M['flag_littoral_2']:.0f}% of lit fleet; four signatures", "7.9-7.10"),
        ("Chokepoint transit series (IMF PortWatch, 28 chokepoints); frozen-baseline disruption episodes; survival", "Did ships stop crossing, and for how long?",
         f"Hormuz {M['pw_drop']:.0f}% down, 0 transits on 4 Mar; median disruption {M['ship_ep_median']:.0f} d, {pct(M['ship_p_gt_74'])} &gt; 74 d", "9.9-9.12"),
        ("Effective-cover model (stock days / share exposed)", "Can stocks carry a months-long closure?",
         f"74 d lasts {M['cover_74_at45']} d at 45% exposure, {M['cover_74_at30']} d at 30%", "13.5"),
        ("Indicators & warnings matrix; out-of-sample test", "Would we have been warned?",
         f"{M['iw_red']} Red / {M['iw_amber']} Amber at ${M['brent_at_cut']:.0f} Brent; oil then {M['brent_oos_change']:+.0f}%", "9.8, 14.2"),
    ], columns=["Technique", "Commander's question", "Key result", "Full report"])
    d.table(TS, "Techniques, questions and results", small=True)

    # software and screenshots
    d.chapter("Annex C - Software Used and Screenshots", letter="C")
    d.p("<b>Stack:</b> Python 3.11 (pandas, NumPy, SciPy, statsmodels, scikit-learn, ruptures, Matplotlib/Basemap) for analysis; "
        "headless Chromium for the report; Microsoft Power BI Desktop for the dashboard (.pbix) built on the exported star schema "
        "(FactConflictWeekly, FactVesselDetections, DimAdmin1, DimDate and the analysis tables).")
    d.fig("screen_pipeline", "Screenshot: the complete pipeline run, raw data to every chart, table and dashboard table", width=100)
    d.fig("screen_code", "Screenshot: code excerpt, scene-cluster bootstrap behind the robustness test", width=100)
    slot = ('<div style="border:1.5pt dashed #9aa5ae;border-radius:4pt;height:150pt;display:flex;align-items:center;justify-content:center;'
            'color:#6b6a66;font-family:Liberation Sans,sans-serif;font-size:10pt;text-align:center">{t}</div>')
    # Power BI screenshots: drop figures/pbi_page1.png ... pbi_page4.png in place and rebuild; a dashed slot shows until then
    pbi = [("Conflict Pulse", "weekly violence, event mix and map of where it fell"),
           ("Chokepoint Watch", "conflict index by sea lane, Hormuz transits and shipping disruptions"),
           ("Dark Ships", "SAR detections coloured by AIS status, dark share by sea and dark-ship clusters"),
           ("Decision", "stock-days what-if, effective cover and the forecast risk of darkness")]
    for k, (name, what) in enumerate(pbi, 1):
        cap = f"Screenshot: Power BI dashboard, page {k} - {name} ({what})"
        if (FIG / f"pbi_page{k}.png").exists():
            d.fig(f"pbi_page{k}", cap, width=100)
        else:
            d.html_fig(slot.format(t=f"[ Insert screenshot: Power BI page {k} - {name} ]"), cap)

    # references
    d.chapter("Annex D - Key References and Data Sources", letter="D")
    refs = [
        "College of Defence Management (2026). Datathon-2026 General Instructions and theme datasets (ACLED Middle-East weekly aggregates; Sentinel-1 SAR vessel detections).",
        "Raleigh, C. et al. (2010). Introducing ACLED. <i>Journal of Peace Research</i> 47(5), 651-660.",
        "Paolo, F.S. et al. (2024). Satellite mapping reveals extensive industrial activity at sea. <i>Nature</i> 625, 85-91.",
        "UNCTAD (2024). <i>Review of Maritime Transport 2024</i>. U.S. EIA (2024). <i>World Oil Transit Chokepoints</i>.",
        "Killick, R., Fearnhead, P., Eckley, I.A. (2012). Optimal detection of changepoints with a linear computational cost. <i>JASA</i> 107, 1590-1598.",
        "Getis, A., Ord, J.K. (1992); Ord, J.K., Getis, A. (1995). Local spatial statistics. <i>Geographical Analysis</i> 24(3); 27(4).",
        "Ester, M. et al. (1996). DBSCAN. <i>Proc. KDD-96</i>, 226-231. Kaplan, E.L., Meier, P. (1958). <i>JASA</i> 53, 457-481. Cox, D.R. (1972). <i>JRSS-B</i> 34, 187-220.",
        "Roberts, D.R. et al. (2017). Cross-validation strategies for structured data. <i>Ecography</i> 40, 913-929.",
        "Open data: EIA Brent/WTI spot prices (github.com/datasets/oil-prices); Federal Reserve H.10 INR/US$ (github.com/datasets/exchange-rates); "
        "Energy Institute Statistical Review via Our World in Data (github.com/owid/energy-data); Natural Earth ports. Icons: Font Awesome Free (CC BY 4.0).",
        "IMF PortWatch (2026). Daily chokepoint transit calls, 28 chokepoints, 2019-2026 (portwatch.imf.org; mirror github.com/ebiisharifi/hormuz-chokepoint-analytics).",
        "Open-source reporting: Press Information Bureau (defence budget 2026-27); All India Radio News; Operation Urja Suraksha (from 23 Mar 2026); "
        "The National and Al Jazeera (Hormuz and Red Sea shipping); CNBC and straits.live (Hormuz reopening, late June 2026).",
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
    html_body = f"<!doctype html><html><head><meta charset='utf-8'><style>{BR.CSS}{IG.CSS}{css_extra}</style></head><body>{''.join(body.parts)}</body></html>"
    with sync_playwright() as p:
        br = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")

        def render(h, path):
            pg = br.new_page()
            pg.set_content(h, wait_until="load")
            pg.pdf(path=str(path), format="A4", print_background=True,
                   margin={"top": "20mm", "bottom": "18mm", "left": "20mm", "right": "18mm"})
            pg.close()

        render(html_body, OUT / "_cbody.pdf")
        bd = fitz.open(OUT / "_cbody.pdf")
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
<div class="t3" style="margin-bottom:20pt">Theme: Global Conflicts &ndash; Impact on Supply Chains</div>
<div class="t1">{BR.TITLE}</div><div class="t2" style="margin-bottom:6pt">{BR.SUBTITLE}</div>
<div class="t2" style="margin-bottom:14pt;font-style:normal;font-weight:bold">Commander's Edition</div>
<div class="t3" style="font-size:10.5pt;max-width:80%;margin:0 auto 18pt auto">What the 2026 war did to the ships that carry India's oil and trade,
what it cost, how long such crises last, and what India and its Armed Forces should do. Told as one story, in plain words.</div>
<div class="t3">Submitted by</div><div class="t3"><b>{RANK} {AUTHOR.upper()}</b></div><div class="t3">{SERVICE_NO} &middot; {UNIT}</div>
<div class="t3" style="margin-top:18pt">September 2026</div>
<div class="t3" style="margin-top:40pt;font-size:9.5pt;color:#444">Companion documents: full technical report, Power BI dashboard (.pbix), analysis code and data</div></div>
<div class="front pb"><h1>THE STUDY AT A GLANCE</h1>{IG.at_a_glance(M)}</div>
<div class="front pb es"><h1>EXECUTIVE SUMMARY</h1>{ST.exec_summary_story(M)}</div>
<div class="front pb"><h1>CONTENTS</h1><table class="toc">{toc}</table>
<p style="font-size:10pt;margin-top:14pt">Each chapter opens with <b>The story so far</b> and closes with <b>So what</b>; every chart carries
<b>What this shows</b>. A commander can read the Executive Summary and the coloured boxes alone in about ten minutes.</p></div>"""
        render(f"<!doctype html><html><head><meta charset='utf-8'><style>{BR.CSS}{IG.CSS}{css_extra}</style></head><body>{front}</body></html>",
               OUT / "_cfront.pdf")
        br.close()
    fr = fitz.open(OUT / "_cfront.pdf")
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
        pg_.insert_text((57, 36), "CDM Datathon-2026  |  Commander's Edition  |  Global Conflicts - Impact on Supply Chains", fontsize=7.2,
                        fontname="helv", color=(0.45, 0.45, 0.45))
        pg_.draw_line((57, 41), (w - 51, 41), color=(0.75, 0.75, 0.75), width=0.4)
    doc.set_metadata({"title": f"{BR.TITLE.title()} - Commander's Edition", "author": AUTHOR})
    out = OUT / "Datathon2026_Commanders_Edition.pdf"
    doc.save(out, garbage=4, deflate=True)
    for f in ("_cbody.pdf", "_cfront.pdf"):
        (OUT / f).unlink()
    print("pages:", len(doc), "front:", nf, "->", out)


if __name__ == "__main__":
    main()
