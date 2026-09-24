"""Plain-language story layer for a commander or senior leader with no analytics background.

Each chapter opens with 'The story so far' (linking back) and closes with 'So what' plus the question that leads into the
next chapter. Every chart carries a one-line 'What this shows'. Numbers come from data/metrics.json.
"""

# =====================================================================================================
# ANNOTATED SOURCE - story.py: the plain-language layer
# -----------------------------------------------------------------------------------------------------
# KICKER      the 'Part I - ...' line under each chapter title.
# openings    'The story so far' box at the start of each chapter (links back to the previous one).
# closings    'So what' box at the end of each chapter, with the question that leads into the next.
# PLAIN       one-line 'What this shows' under each chart, keyed by the chart's file name.
# GLOSSARY    each analytics technique explained in plain words with a military analogy.
# exec_summary_story / storyline   the executive summary and the seven-step storyboard on the at-a-glance page.
# To change wording, edit the text here and rebuild; numbers stay live because they come from M (metrics.json).
# =====================================================================================================



def pct(x):
    return f"{x * 100:.0f}%"


KICKER = {
    1: "Prologue - the question", 2: "Background - what others have learned", 3: "Background - the tools, in plain words",
    4: "Background - checking the evidence", 5: "Part I of the story - the storm gathers",
    6: "Part II - the storm reaches the sea lanes", 7: "Part III - the ships go blind", 8: "Part IV - can we see it coming?",
    9: "Part V - the bill arrives", 10: "Part VI - what we know, and how sure we are", 11: "Part VII - what it means for the world",
    12: "Part VIII - what it means for India", 13: "Part IX - what it means for the Armed Forces",
    14: "Part X - what we should do", 15: "Epilogue - the end of the story, and the start of the watch",
}


def openings(M):
    return {
        1: "In February 2026 a war broke out on the shores of the world's most important oil strait. This report asks a commander's "
           "questions about it. What did the war do to the ships that carry India's oil and trade? How long does such a disruption last? "
           "What did it cost? Could we have seen it coming, and what should India and its Armed Forces do next time?",
        2: "Before looking at the evidence, we check what others have already learned about conflict data, satellite tracking of ships "
           "and supply chains, and where the gap is that this study fills.",
        3: "The investigation uses a set of analytical tools. This chapter explains what each tool does. A commander who only wants the "
           "answers can read the plain-language summaries and the glossary, and skip the equations.",
        4: "Good decisions need clean evidence. Before any analysis, the two datasets were checked, cleaned and prepared, much as "
           "intelligence reports are collated and verified before they reach a commander.",
        5: "With the evidence prepared, the story begins on land. Before we look at the sea, we need to know how the conflict itself "
           "grew, changed its character, and moved towards the energy coast of the Gulf.",
        6: "Chapter 5 showed the war moving to the Gulf's energy coast and being fought mainly with missiles and drones. The next question is "
           "whether that violence reached the sea lanes, and for how long.",
        7: f"Chapter 6 showed the violence reached the waters around Hormuz and the Red Sea, and that such crises can last for months. "
           "So what did the ships do? Here we look at the sea itself, through satellite radar that sees every ship whether it "
           "wants to be seen or not.",
        8: f"Chapter 7 found that ships near the fighting switch off their identity beacons: {pct(M['hormuz_large_dark'])} of big ships at Hormuz "
           "went dark. A commander's next question is whether we could have predicted where this would happen.",
        9: "So far the story has been about violence and ships. But a supply chain is ultimately about goods and money. This chapter follows the "
           "shock from the strait to the oil price, the rupee and India's import bill, using public data that runs to September 2026.",
        10: "The evidence is now complete. Before drawing conclusions, a good staff officer asks: are we sure, and could something else "
            "explain what we see? This chapter tests the story and states each conclusion with its level of confidence.",
        11: "Having established what we know and how sure we are, we turn to what it means, starting with the wider world "
            "before narrowing to India and then to our own forces.",
        12: "The world pays for a chokepoint war in higher prices and slower trade. India pays more than most, because it imports "
            "almost nine-tenths of its oil and sits at the end of both the Hormuz and Red Sea routes.",
        13: "The same shocks that hit India's economy also reach the Armed Forces: through fuel, spares, the threat to bases, and "
            "the need to protect citizens abroad.",
        14: "The story has shown what happens, how long it lasts, what it costs and whom it affects. This chapter turns that into "
            "action: what to do, what to watch, and in what order.",
        15: "We end where we began, with the commander's questions, now answered with evidence.",
    }


def closings(M):
    return {
        1: ("A clear question and seven testable hypotheses.", "What do we already know from others' work?"),
        2: ("Nobody has yet joined conflict data, satellite ship data and India's supply needs in one study. That is the gap filled here.",
            "What tools will we use?"),
        3: ("Each tool answers one simple question: when did things change, where do dark ships gather, how long do crises last, "
            "and can we predict it?", "Is the evidence clean enough to trust?"),
        4: (f"Two clean datasets: {M['acled_events']:,} conflict events over 11 years and {M['sar_rows']:,} ships seen from space in the "
            "first fortnight of the war.", "What does the conflict itself tell us?"),
        5: (f"The war nearly tripled regional violence ({M['pv_war_ratio']:.1f}x). Most of it was delivered by missiles and drones (84%), and "
            f"it struck the Gulf states that export the world's energy ({M['gcc_multiplier']:.0f}x rise).",
            "Did this violence reach the sea lanes that carry India's oil?"),
        6: (f"Yes. Violence around Hormuz reached {M['hormuz_war_mult']:.0f} times its normal level, and in the Red Sea it moved from land to sea. "
            f"Such crises usually last a few weeks, but {pct(M['km_p_gt_spr'])} of them outlast India's emergency oil reserve.",
            "What did the ships do while this was happening?"),
        7: (f"Big ships went dark: {pct(M['hormuz_large_dark'])} at Hormuz against about 10% in peaceful seas. AIS counts said traffic fell "
            f"{abs(M['pi_lit_chg'])}%, but radar saw most hulls still there, many held at anchor. Four behaviours emerged: concealment in the Gulf, "
            "evacuation from the Red Sea, a frozen Black Sea, and compliance where an authority enforces reporting.",
            "Could we have predicted where ships would go dark?"),
        8: (f"Partly, and usefully. After a ship's size, its distance from the fighting is the strongest clue. The model beats chance on seas it "
            f"has never seen (score {M['auc_gbt']:.2f}, where 0.5 is a coin toss and 1.0 is perfect). It is good enough to point satellites "
            "at the right waters, though not to name individual ships.", "What did all this cost India?"),
        9: (f"Oil rose from ${M['brent_prewar']:.0f} to ${M['brent_war_peak']:.0f}, the rupee weakened, and India's oil bill rose by about "
            f"US${M['extra_bill_usd_bn']:.0f} billion. The warning signals built here stayed Red in June while the market relaxed, and oil then "
            f"rose {M['brent_oos_change']:.0f}%.", "How sure can we be of all this?"),
        10: ("The central finding survives every test we could devise. It holds under eight different definitions, it gets stronger the "
             "closer ships are to the fighting, and no rival explanation fits the evidence as well as deliberate switch-off.",
             "What does this mean for the world?"),
        11: ("For the world, chokepoint war is now a recurring cost of trade and a hazard at sea.", "What does it mean for India?"),
        12: ("For India the exposure is concentrated in oil, westbound trade, connectivity projects and nine million citizens in the Gulf.",
             "And for the Armed Forces?"),
        13: ("For the Armed Forces it means fuel and spares stocks sized on evidence, rear areas defended against drones and missiles, "
             "navigation that does not rely on GPS alone, and a joint watch on the chokepoints.", "What should we do, and in what order?"),
        14: ("Fifteen staffed actions, the DARKWATCH watch-list and a three-phase plan that starts at no new cost, each traced to a finding.", None),
    }


PLAIN = {
    "f5_1_annual": "Violence in the Middle East peaked in 2024. In only six months, 2026 has already been one of the deadliest years of the decade.",
    "f5_2_eventmix": "Each bar is one year. The blue part (missiles, drones, shelling) grows sharply whenever states go to war with each other.",
    "f5_3_heatmap": "Darker cells mean more violence. Watch the conflict move from Syria and Iraq (left) to Israel, Lebanon and, in 2026, Iran and the Gulf states (right).",
    "f5_4_changepoints": "The orange steps are the 'battle rhythm'. The computer found, without being told, the exact weeks it changed: 7 Oct 2023 and 28 Feb 2026.",
    "f5_5_drone_share": "The share of violence delivered from a distance jumps at the start of each war. A rising share is an early warning sign.",
    "f5_6_gcc": "Before the war the Gulf states saw almost no violence. From 28 February they were hit every week.",
    "f5_7_war_map": "Each bubble is a province: bigger means more attacks, redder means more deaths. The fighting reached the shore of the Strait of Hormuz.",
    "f5_8_maritime": "Attacks at sea were rare until late 2023, then surged with the Red Sea campaign.",
    "f6_1_ccii": "A 'thermometer' of violence for each sea route. When the line crosses the dashed threshold, the route is under stress.",
    "f6_5_offshore": "In Yemen, attacks on land fell (left) while attacks at sea rose (right). The threat moved from the shore to the shipping lanes.",
    "f6_2_ccii_z": "Above the dashed line means a route is under stress. Hormuz went off the scale in March 2026 and stayed above the line.",
    "f6_3_forecast": "Blue is what happened; orange is the forecast for July-September 2026. The band shows the range of likely outcomes.",
    "f6_4_km": "Read it like a survival curve: the line shows the share of crises still going after a given number of weeks. The red lines are India's oil reserves.",
    "f7_1_global_map": "Every dot is a ship seen by satellite radar. Orange ships were not transmitting their identity. They cluster in the Gulf and the Black Sea.",
    "f7_2_dark_by_region": "Look at the right-hand panel (big ships only). War zones (orange) are four to seven times darker than peaceful seas (blue).",
    "f7_3_size_zone": "In peaceful seas, bigger ships are almost always visible. In the Gulf war zone even the biggest tankers are dark 60% of the time.",
    "f7_4_gulf_hotspots": "Red squares on the right are places where dark ships bunch together more than chance would allow: a belt from Qatar to Hormuz.",
    "f7_5_global_hotspots": "The same test worldwide. Red squares are statistically significant clusters of dark ships.",
    "f7_6_dbscan": "Each circle is a group of dark ships found automatically. The biggest are tanker queues off Dubai and Fujairah, waiting with identities off.",
    "f7_7_gulf_daily": "Each day of the war's first fortnight, a larger share of ships in the Gulf went dark.",
    "f7_8_flags": "The green segment shows ships registered in countries often linked to sanctions evasion. Their share is about three times higher in war zones.",
    "f7_10_india_seas": "Near India most dark craft are small fishing boats (yellow). Big ships near India are visible.",
    "f8_1_model": "Left: the further the curve bows above the diagonal, the better the prediction. Right: distance from the fighting and ship size matter most.",
    "f8_2_pdp": "The model's rule of thumb: the closer a big ship is to the fighting, the more likely it is to go dark.",
    "f8_3_risk_surface": "A forecast map of where a merchant ship is likely to go dark. Darkest near Hormuz and the UAE coast, lighter near India.",
    "f9o_1_brent_timeline": "Top: the oil price. Bottom: the violence thermometers. Oil exploded when war reached Hormuz and rose again after June.",
    "f9o_2_event_study": "Each line is one crisis, starting at zero on the day it began. Only the 2026 war (red) produced a lasting jump.",
    "f9o_3_rupee": "Left: the rupee weakened steadily during the war (a higher number means a weaker rupee).",
    "f9o_4_india_dependence": "The gap between the orange (use) and blue (own production) areas is what India must import: now 87% of its oil.",
    "f9_2_robustness": "Every dot is the same question asked a different way. All are far to the right of 1, so the war effect is real however it is measured.",
    "f9_3_dose_response": "The closer ships were to the fighting, the more of them went dark: a clear sign that the war caused it.",
    "f9_1_stock_cover": "Left: the chance that a crisis outlasts a given stock. Right: the average days short. Beyond about 35-45 days, extra stock buys little.",
}

GLOSSARY = [
    ("AIS (Automatic Identification System)", "A ship's identity beacon. It broadcasts name, position and course. It works like IFF for merchant ships, and a ship can switch it off."),
    ("AIS-dark ship", "A ship that satellite radar can see but that is not transmitting its identity: a vehicle driving at night with its lights off."),
    ("SAR (satellite radar)", "A radar satellite that sees ships day and night, through cloud, whether or not they transmit."),
    ("Chokepoint", "A narrow sea passage that ships cannot easily avoid, such as Hormuz or Bab-el-Mandeb: a defile on the sea lanes."),
    ("Relative risk / 'x times more likely'", "How much more often something happens in one group than another. A relative risk of 4.7 means 4.7 times as often."),
    ("p-value", "The chance that a result is a fluke. Below 0.05 means less than 1 in 20. Most results here are far smaller, i.e. almost certainly real."),
    ("Confidence interval", "The range in which the true value probably lies, like the beaten zone of a weapon rather than a single point."),
    ("Change-point detection", "A method that finds the dates when the 'battle rhythm' changed, without being told what to look for."),
    ("Conflict intensity index (CCII)", "A weekly thermometer of violence around each sea route, built from open conflict data."),
    ("Forecast (ARIMA)", "Projects the thermometer forward a few months, with a band showing the likely range."),
    ("Survival analysis (Kaplan-Meier, Cox)", "Measures how long crises last and what makes them last longer. It is the same tool used for time between equipment failures."),
    ("Hot-spot analysis (Getis-Ord Gi*)", "Finds places where dark ships bunch together more than chance would allow, like an incident-density overlay."),
    ("Cluster finding (DBSCAN)", "Automatically finds groups of ships close together, such as tanker queues at an anchorage."),
    ("Machine-learning model", "A program that learns a rule from 62,000 examples. It was tested only on seas it had never seen, like testing a soldier on unfamiliar ground."),
    ("Model score (ROC-AUC)", "How well a model separates dark ships from visible ones: 0.5 is a coin toss, 1.0 is perfect."),
    ("Bootstrap", "Re-running the analysis 2,000 times on re-shuffled satellite pictures to check that the answer does not change."),
    ("Dose-response", "The stronger the exposure, the stronger the effect. Here: the closer to the fighting, the more ships go dark."),
    ("Competing hypotheses", "Standard intelligence tradecraft: list every possible explanation and keep the one the evidence does not contradict."),
    ("Event study", "Tracking a price day by day after a shock, to see how big and how lasting the effect was."),
    ("Granger test", "Checks whether A reliably happens before B, i.e. whether A could serve as a warning of B."),
    ("Expected shortfall", "The average number of days a stock would run short in a crisis. It is used here to size fuel and spares reserves."),
    ("I&W (indicators and warnings)", "A short watch-list of measurable signals with thresholds that trigger pre-agreed actions."),
    ("Strategic Dark Ratio (SDR)", "Of the big ships (100 m and over) the radar sees in one satellite image, the share not transmitting their identity. Peaceful seas: about 10%."),
    ("Maritime Picture Assurance", "Checking, as a standing duty, that the maritime picture used for decisions still represents the ships actually on the water."),
    ("DARKWATCH", "The six-signal watch-list built in this study, with Amber and Red thresholds and a pre-agreed action for each."),
    ("Stasis index", "The share of ships seen in the same 100 m square on two different days: a ship under way cannot do that, a ship at anchor can."),
    ("Difference-in-differences", "Did the Gulf change more than everywhere else over the same fortnight? Compares the change, not just the level."),
    ("Estimative language", "'Almost certain' (over 95%), 'highly likely' (80-95%), 'likely' (55-80%): the standard way intelligence expresses probability."),
]


def glossary_html():
    rows = "".join(f"<tr><td style='width:34%;vertical-align:top'><b>{a}</b></td><td>{b}</td></tr>" for a, b in GLOSSARY)
    return ("<p style='font-size:10.5pt'>This report uses a number of data-analytics tools. None of them needs to be understood in detail to "
            "follow the story: every chapter opens with <b>The story so far</b>, closes with <b>So what</b>, and every chart carries a "
            "one-line <b>What this shows</b>. The terms below are explained in plain words for readers who want them.</p>"
            f"<table class='tbl small'><thead><tr><th>Term</th><th>What it means, in plain words</th></tr></thead><tbody>{rows}</tbody></table>")


def exec_summary_story(M):
    return f"""
<div class="bluf"><b>BOTTOM LINE UP FRONT.</b> When war reaches a sea chokepoint, the first thing to fail is the <b>maritime picture</b>: big ships stop
identifying themselves, so AIS-based counts overstate how much shipping has gone and hide what is still there. The disruption then <b>outlasts our reserves</b>
and cost India about <b>US${M['extra_bill_usd_bn']:.0f} billion</b> in six months. Our warning signals saw it coming when the market did not.</div>
<h2>Situation</h2><p style="font-size:10.3pt">War reached the Strait of Hormuz on 28 February 2026. This study joins 11 years of conflict data, satellite radar of
106,533 ships in the first fortnight, IMF daily transit counts at 28 world chokepoints, and open oil, rupee, energy and news sources to September 2026.</p>
<h2>Assessment</h2><ol style="font-size:10.3pt;line-height:1.36;padding-left:16pt;margin-bottom:4pt">
<li><b>The storm.</b> Violence nearly tripled ({M['pv_war_ratio']:.1f}x); 84% by missiles and drones; the Gulf states were hit {M['gcc_multiplier']:.0f} times more than before.</li>
<li><b>The picture failed.</b> {pct(M['hormuz_large_dark'])} of big ships at Hormuz were dark against {M['sdr_baseline']:.0f}% in peaceful seas. AIS counts fell
{abs(M['pi_lit_chg'])}%, but radar saw most hulls still there, many of them held at anchor. The Gulf darkened {M['did_excess']:.1f} points a day faster than 11 control seas.</li>
<li><b>Four behaviours, not one.</b> Concealment in the Gulf, evacuation from the Red Sea, a frozen Black Sea, and compliance in the East Med (8% dark beside heavy fighting).</li>
<li><b>It lasts.</b> Fighting flares for weeks, but shipping disruption lasts months: Hormuz transits fell {M['pw_drop']:.0f}% (zero on 4 March) and at world
chokepoints the median disruption ran {M['ship_ep_median']:.0f} days, {pct(M['ship_p_gt_74'])} outlasting India's 74-day national cover.</li>
<li><b>The bill.</b> Brent ${M['brent_prewar']:.0f} to ${M['brent_war_peak']:.0f}; in March the extra oil bill equalled {M['def_ratio_mar_lo'] * 100:.0f}-{M['def_ratio_mar_hi'] * 100:.0f}%
of the monthly defence budget.</li>
<li><b>We saw it coming.</b> On 26 June the market relaxed (${M['brent_at_cut']:.0f}); our DARKWATCH signals stayed Red. Oil then rose {M['brent_oos_change']:.0f}%.</li></ol>
<h2>Deduction</h2><p style="font-size:10.3pt">The decision variable is the <b>state of the corridor</b>, not AIS silence alone. Classify first (concealment,
evacuation, frozen, compliance), then act. Each needs a different response: escort and surveillance, rerouting, provenance checks, or sustained presence.</p>
<h2>Recommendation</h2><ul style="font-size:10.3pt;margin-bottom:4pt">
<li>Make <b>Maritime Picture Assurance</b> a named joint warning function under HQ IDS, run through IFC-IOR, with the SDR and DARKWATCH as standing products.</li>
<li>Size fuel, aviation-fuel and critical-spares reserves for all three Services at <b>35-45 days</b> as a bridge, and cut exposure to any one chokepoint, because <b>stocks bridge; diversification carries</b>; harden rear areas against drones and missiles; GPS-resilient navigation.</li>
<li>Standing rule: <b>no AIS-derived traffic count</b> for a contested corridor without a radar cross-check.</li></ul>
<h2>Decision sought</h2><p style="font-size:10.3pt">Approve a <b>four-month Phase 1 proof of concept</b> using existing establishment, free Copernicus
Sentinel-1 imagery and the analysis pipeline already built. Continue only if a principal acts on a DARKWATCH warning in that period.</p>"""


def storyline(M):
    """Seven-step storyboard for the 'at a glance' page."""
    return [("burst", "1. The storm", f"War nearly triples violence ({M['pv_war_ratio']:.1f}x); 84% by missile and drone"),
            ("water", "2. Reaches the sea", f"Hormuz violence {M['hormuz_war_mult']:.0f}x normal; Red Sea attacks move offshore"),
            ("eye-slash", "3. Ships go blind", f"{pct(M['hormuz_large_dark'])} of big ships at Hormuz switch identity off"),
            ("hourglass-half", "4. It lasts", f"Shipping disruption lasts months (median {M['ship_ep_median']:.0f} days)"),
            ("sack-dollar", "5. The bill", f"Oil +{M['ev_war_peak']:.0f}%, rupee weaker, ~${M['extra_bill_usd_bn']:.0f} bn extra for India"),
            ("traffic-light", "6. We saw it coming", "Signals stayed Red when markets relaxed"),
            ("shield-halved", "7. What to do", "35-45 days of stock, defend rear areas, watch weekly")]
