"""Plain-language story layer for a commander or senior leader with no analytics background.

Each chapter opens with 'The story so far' and closes with 'So what' plus the question that leads into the next chapter.
Every chart carries a one-line 'What this shows'. All numbers come from data/metrics.json (M).
"""


def pct(x, d=0):
    return f"{x * 100:.{d}f}%"


KICKER = {1: "Prologue - the question", 2: "Part I - the crowd", 3: "Part II - who owns orbit", 4: "Part III - where it is crowded",
          5: "Part IV - the contest", 6: "Part V - the natural adversary", 7: "Part VI - what eyes in orbit buy",
          8: "Part VII - the trajectory", 9: "Part VIII - how sure we are", 10: "Part IX - what it means",
          11: "Part X - what we should do", 12: "Epilogue"}


def openings(M):
    return {
        1: "In May 2025, during Operation Sindoor, ten Indian satellites worked round the clock to see, talk and navigate for the "
           "forces. Space is no longer a support service; it is where modern operations begin. This booklet asks what has happened "
           "to that space in the last twelve years, and what India and its Armed Forces should do about it.",
        2: "The story begins with numbers. In January 2014, the date of the CDM satellite census, about 1,200 satellites were working. "
           "What happened next?",
        3: f"The sky filled {M['active_mult']:.0f} times over. The next question is whose satellites these are, and what they are for.",
        4: "A few owners now hold most of the sky. But orbit is not one place: some altitudes are empty and some are packed. Where is "
           "the crowding, and how dangerous is it?",
        5: "A crowded orbit is a hazard. A crowded orbit full of military eyes is a contest. Who is building the watchers?",
        6: "Rivals are not the only threat. The Sun sets the weather in space, and it does not negotiate.",
        7: "So far the story has been about risk. Why do nations accept that risk? Because of what satellites see. The CDM fire data "
           "show it on the ground.",
        8: "The past is measured. What comes next?",
        9: "The findings are strong claims. Before a commander acts on them, a staff officer asks: are we sure?",
        10: "The evidence holds. What does it mean for the world, for India, and for the Army, Navy and Air Force?",
        11: "The implications are clear. The last question is the one a commander always asks: what do we do, who does it, and by when?",
        12: "We end where we began, with the commander's questions, now answered with evidence.",
    }


def closings(M):
    return {
        1: ("Five questions, three CDM datasets, four open sources and one repeatable pipeline.", "How crowded has orbit become?"),
        2: (f"Active satellites went from {M['active_2014']:,} to {M['active_now']:,} in twelve years ({M['active_mult']:.0f} times). "
            f"Growth changed gear around {M['growth_cps'][0]}: {M['cagr_2000_2013']:.0f}% a year before, {M['cagr_2019_2025']:.0f}% after.",
            "Whose satellites are they?"),
        3: (f"One country operates {M['us_share_now']:.0f}% of working satellites and one company about {pct(M['starlink_share'])}. "
            f"India's share fell from {M['in_share_2014']:.1f}% to {M['in_share_now']:.1f}%.", "Where is orbit crowded, and how risky is it?"),
        4: (f"Collision risk in low orbit is about {M['risk_ratio']:.0f} times the 2014 level, and a one-day screening found "
            f"{M['cj_cross_total']:,} close approaches under 5 km, {M['cj_B_india']} of them Indian satellites passing debris. High-altitude "
            "weapon debris lasts decades; India's low-altitude test cleaned itself up within a year.", "Who is building military eyes in orbit?"),
        5: (f"China operates about {M['cn_isr_ops']} state and military imaging and intelligence satellites; India about {M['in_isr_ops']}. "
            f"The gap is not closing on its own. Physics alone flags military satellites (ROC-AUC {M['ml_ext_auc']:.2f} on unseen launches).",
            "What threat does nature add?"),
        6: (f"At high solar activity the odds of an intense geomagnetic storm in any month rise about {M['storm_mult']:.0f}-fold. The "
            "solar cycle even shows in how fast debris falls.", "Why take these risks at all?"),
        7: (f"Two satellites together saw fires that either one alone would have missed {pct(M['prem_single'])} of the time. Numbers "
            "in orbit buy coverage, persistence and early warning.", "What will orbit look like by 2030?"),
        8: (f"About {M['sc_base'] / 1000:.0f},000 working satellites by 2030 in the base case, and a collision-risk index about "
            f"{M['risk_2030_base']:.0f} times the 2014 level.", "How sure are we?"),
        9: ("Every headline finding survives an independent check.", "What does it mean for India and its Armed Forces?"),
        10: ("India depends on space more every year while holding a shrinking share of it. That is the strategic problem.",
             "What should India do?"),
        11: ("Seven actions, each with a lead, a timeline and a test of success.", None),
    }


PLAIN = {
    "f2_1_population": "Everything we track in orbit, year by year. Blue is satellites (working or dead), orange is debris. The blue "
                       "wedge at the right is the mega-constellation era.",
    "f2_2_censuses": "Three independent counts of working satellites. Red is one company's constellation.",
    "f2_3_launch_rate": "Left: satellites launched each year (red = Starlink). Right: rocket launches each year by country.",
    "f3_1_actors": "Left: each country's share of working satellites in 2014, 2020 and 2026. Right: the largest constellations today.",
    "f3_2_users_purpose": "What satellites do, and what share of each country's fleet serves the military.",
    "f4_1_leo_shells": "How many objects sit at each height in low orbit. The black line is 2014; bars are today. Tall blue bars are "
                       "working satellites; orange is debris.",
    "f4_2_geo_arc": "Satellites parked above the equator, by longitude. The shaded band is the arc India uses; red markers are Indian "
                    "satellites.",
    "f4_3_asat_debris": "Share of debris pieces from each weapon test or collision still in orbit, year by year afterwards.",
    "f5_1_isr_race": "Left: military and state intelligence satellites launched since 2000. Right: how many are working today.",
    "f6_1_storms": "Left: an hourly record of magnetic storms (dips below the red lines are dangerous). Right: storms per month at "
                   "different levels of solar activity.",
    "f6_2_reentry_cycle": "The share of debris falling back to Earth each year. The peaks line up with the Sun's 11-year maximum.",
    "f7_1_eo_value": "Left: which satellite saw each fire-day. Centre: monthly fire detections, with abnormal surges flagged. Right: a "
                     "volcano watched through its eruption.",
    "f7_2_fire_map": "Every fire and heat source the two satellites detected over ten years.",
    "f8_1_forecast": "Left: satellites in orbit and three scenarios for 2030. Right: how collision risk grows under each.",
    "f9_1_launch_capacity": "Rocket launches per year from US, Chinese and Indian soil.",
    "f11_1_ml_military": "Left: how well the model separates military from civil satellites it has never seen (higher curve = better). Right: "
                         "which physical features give a military satellite away.",
    "f12_1_conjunctions": "Left: at what height satellites came within 5 km of each other or of debris in one day. Right: how fast they "
                          "passed each other.",
}

GLOSSARY = [
    ("Satellite catalogue (SATCAT)", "The public list of every tracked object in Earth orbit: satellites, rocket bodies and debris, "
     "with launch and re-entry dates and orbit heights."),
    ("LEO / MEO / GEO", "Low Earth orbit (below 2,000 km, most satellites), medium orbit (navigation satellites) and geostationary "
     "orbit (36,000 km above the equator, where a satellite appears fixed in the sky)."),
    ("Mega-constellation", "Thousands of small satellites flying together to give continuous global coverage, such as Starlink."),
    ("Debris", "Broken pieces of satellites and rockets: from explosions, collisions and weapon tests. At 7-8 km/s a 1 cm piece hits "
     "like a hand grenade."),
    ("ASAT test", "Anti-satellite weapon test: a missile destroys a satellite in orbit, creating a cloud of debris."),
    ("Collision-risk index", "A relative measure of how likely collisions are: it grows with the square of the number of objects "
     "at each height. 2014 = 1."),
    ("HHI (concentration index)", "Sum of squared market shares, 0-10,000. Above 2,500 means a few players dominate."),
    ("Change-point detection", "A method that finds the date when a trend shifted, without being told where to look."),
    ("Dst index", "A measure of how much a magnetic storm disturbs the Earth's field. Below -100 nT is an intense storm."),
    ("Sunspot number", "A count of dark spots on the Sun; high counts mean an active Sun and more storms."),
    ("Periodogram", "A tool that finds repeating cycles in a time series, like finding the beat in music."),
    ("Poisson regression", "A model for counts (e.g. storms per month) that measures how a factor raises the rate."),
    ("Constellation premium", "What extra satellites add: the share of events that one satellite alone would have missed."),
    ("Exponential smoothing (Holt)", "A forecasting method that follows the recent trend and lets it flatten over time."),
    ("Back-test", "Hiding the last few years, forecasting them, and checking the error: a test of the forecast method."),
    ("ISR", "Intelligence, surveillance and reconnaissance: satellites that image, listen and watch."),
    ("ORBITWATCH", "The seven-indicator warning matrix proposed in this study, updated from open data."),
    ("SGP4", "The standard mathematical model that turns published orbital elements into a satellite's position at any time."),
    ("Close approach (conjunction)", "Two objects passing close to each other; screening flags passes under 5 km for closer study."),
    ("Out-of-time test", "Training a model on older data and testing it on later data it has never seen: the honest test of a forecast."),
    ("ROC-AUC", "A model's skill at ranking positives above negatives: 0.5 is a coin toss, 1.0 is perfect."),
    ("SBS-III", "India's Space-Based Surveillance phase III: 52 military surveillance satellites approved in 2023, due by 2029."),
]


def exec_summary_story(M):
    return f"""
<div class="bluf"><b>BOTTOM LINE UP FRONT.</b> Orbit has become <b>crowded, concentrated and contested</b> faster than any plan
assumed. Working satellites rose from {M['active_2014']:,} to {M['active_now']:,} in twelve years; collision risk in low orbit is about
<b>{M['risk_ratio']:.0f} times</b> the 2014 level; and China now operates about <b>{M['cn_isr_ops']}</b> state and military imaging and
intelligence satellites to India's <b>{M['in_isr_ops']}</b>. India's share of working satellites has fallen to {M['in_share_now']:.1f}%.</div>
<h2>Situation</h2><p style="font-size:10.3pt">The CDM datasets give a census of 1,167 active satellites (Jan 2014), 140,000 hours of
space-weather records and 1.25 million satellite fire detections. Open sources extend the picture to September 2026: the full public
satellite catalogue ({M['satcat_n']:,} objects), the UCS 2020 census and UN launch registrations.</p>
<h2>Assessment</h2><ol style="font-size:10.3pt;line-height:1.36;padding-left:16pt;margin-bottom:4pt">
<li><b>Crowded.</b> Payloads launched a year rose from {M['pay_2013']} (2013) to {M['pay_2025']:,} (2025). Growth changed gear around {M['growth_cps'][0]}.</li>
<li><b>Concentrated.</b> The USA operates {M['us_share_now']:.0f}% of working satellites (43% in 2014); one company about {pct(M['starlink_share'])}.</li>
<li><b>Risky.</b> A live crowd of {M['band_now']:,} objects sits at 450-500 km; a dead crowd of debris at 750-900 km. Debris from China's
2007 weapon test is still {M['fy1c_alive_pct']:.0f}% in orbit; India's 2019 test debris has all re-entered.</li>
<li><b>Contested.</b> China has launched about {M['cn_isr_rate_2023_25']:.0f} state intelligence satellites a year since 2023; India under one.
SBS-III's 52 satellites close only about {pct(M['sbs3_close'])} of today's gap.</li>
<li><b>Exposed to nature.</b> At high solar activity the odds of an intense magnetic storm in a month rise from {pct(M['p_intense_lo'])} to {pct(M['p_intense_hi'])}.</li>
<li><b>Close calls daily.</b> A one-day screening of current orbits found {M['cj_cross_total']:,} passes under 5 km; {M['cj_B_india']} Indian
satellites, including EMISAT, passed within 5 km of weapon-test or collision debris.</li>
<li><b>Worth it.</b> Two satellites saw {pct(M['prem_single'])} of fire-days that one alone would have missed: numbers buy coverage.</li></ol>
<h2>Deduction</h2><p style="font-size:10.3pt">India's security now depends on space, while its share of space shrinks and the
environment grows more dangerous. Capacity, resilience and awareness of the space picture, not single prestige satellites, decide who
keeps the high ground.</p>
<h2>Recommendation</h2><ul style="font-size:10.3pt;margin-bottom:4pt">
<li>Stand up <b>ORBITWATCH</b> under the Defence Space Agency: a weekly space-situation picture and warning matrix from open and national data.</li>
<li>Accelerate SBS-III and buy commercial capacity to reach <b>persistent</b> coverage of the northern borders and the Indian Ocean.</li>
<li>Make every new military satellite <b>manoeuvrable and storm-hardened</b>, and budget fuel for collision avoidance.</li></ul>
<h2>Decision sought</h2><p style="font-size:10.3pt">Approve a <b>four-month ORBITWATCH proof of concept</b> at the Defence Space Agency using
the open catalogue and the pipeline already built. Continue only if it flags at least one actionable conjunction or threat event.</p>"""


def storyline(M):
    return [("earth-asia", "1. The crowd", f"{M['active_mult']:.0f}x working satellites since 2014"),
            ("flag", "2. The owners", f"USA {M['us_share_now']:.0f}% of the sky; India {M['in_share_now']:.1f}%"),
            ("burst", "3. The danger", f"Collision risk x{M['risk_ratio']:.0f}; debris that stays for decades"),
            ("eye", "4. The contest", f"China {M['cn_isr_ops']} ISR satellites; India {M['in_isr_ops']}"),
            ("sun", "5. The Sun", f"Storm odds x{M['storm_mult']:.0f} at solar maximum"),
            ("chart-line", "6. The trajectory", f"~{M['sc_base'] / 1000:.0f}k working satellites by 2030"),
            ("shield-halved", "7. What to do", "ORBITWATCH, SBS-III faster, resilient satellites")]
