"""Infographics for the Theme 6.1 booklet, built as HTML + inline SVG icons (Font Awesome Free, CC BY 4.0).
Every number comes from data/metrics.json (M)."""
import story as ST
from ig_base import AMBER, BLUE, CSS as BASE_CSS, GREEN, GREY, NAVY, ORANGE, RED, icon, pct

CSS = BASE_CSS + """
.lad { display: flex; flex-direction: column; gap: 3pt; font-family: 'Liberation Sans', Arial, sans-serif; }
.lad .r { display: flex; align-items: center; gap: 8pt; border-radius: 4pt; padding: 5pt 8pt; color: #1b1b1b; }
.lad .alt { flex: 0 0 78pt; font-weight: bold; font-size: 8.5pt; color: #1f3b5c; }
.lad .d { flex: 1; font-size: 8pt; line-height: 1.3; }
.lad .n { flex: 0 0 70pt; text-align: right; font-size: 13pt; font-weight: bold; }
.lad .n small { display: block; font-size: 6.8pt; font-weight: normal; color: #444; }
"""


def at_a_glance(M):
    src = [("database", "CDM satellites", f"{M['cdm_n']:,} active<br>census Jan 2014"),
           ("sun", "CDM space weather", f"{M['dst_n']:,} hours<br>Dst + sunspots"),
           ("fire", "CDM MODIS fires", f"{M['fires_n'] / 1e6:.2f} million<br>2010-2020"),
           ("satellite", "Satellite catalogue", f"{M['satcat_n']:,} objects<br>to {M['satcat_last']}"),
           ("layer-group", "UCS 2020 census", f"{M['ucs20_n']:,} active<br>Apr 2020"),
           ("globe", "UNOOSA registry", "launches by country<br>1957-2023"),
           ("book-open", "Official & news", "ISRO, PIB, ESA,<br>NOAA, 2024-26")]
    tiles = [("satellite", f"{M['active_mult']:.0f}x", "working satellites, 2014 to 2026", True),
             ("flag", f"{M['us_share_now']:.0f}%", "of working satellites are US-operated", False),
             ("burst", f"x{M['risk_ratio']:.0f}", "collision-risk index in low orbit vs 2014", True),
             ("explosion", f"{M['fy1c_alive_pct']:.0f}%", "of 2007 ASAT-test debris still in orbit", True),
             ("eye", f"{M['cn_isr_ops']} : {M['in_isr_ops']}", "state ISR satellites, China : India", True),
             ("sun", f"x{M['storm_mult']:.0f}", "intense-storm odds at solar maximum", False),
             ("satellite-dish", pct(M['prem_single']), "of fire-days only one of two satellites saw", False),
             ("chart-line", f"~{M['sc_base'] / 1000:.0f}k", "working satellites by 2030 (base case)", True)]
    meth = ["Change-points (PELT)", "Concentration index (HHI)", "Kinetic-gas collision index", "Survival of debris",
            "Poisson regression", "Periodogram", "Exponential smoothing + back-test", "Scenario model", "Warning matrix"]
    out = ['<div class="ig">']
    out.append('<div class="ig-band">PROJECT HIGH GROUND &middot; Contested and Congested: the Crowding of Orbit<small>CDM Datathon-2026 '
               '&middot; Theme 6.1: Growth of Satellites in Outer Space &middot; the study on one page</small></div>')
    cells = "".join(f'<div style="background:{c}">{icon(i, 15, "#fff")}<b>{h}</b>{x}</div>' for (i, h, x), c in
                    zip(ST.storyline(M), ["#3d5a80", "#46638a", "#9a4a3a", "#b8452e", "#a93226", "#7b241c", "#1f3b5c"]))
    out.append(f'<div class="ig-h">The story in seven steps</div><div class="ig-chev">{cells}</div>')
    out.append('<div class="ig-h">Data fused</div><div class="ig-row">' + "".join(
        f'<div class="ig-src">{icon(i, 20)}<b>{t}</b>{s}</div>' for i, t, s in src) + "</div>")
    out.append('<div class="ig-h">Methods</div><div style="margin-top:4pt">' + "".join(
        f'<span style="display:inline-block;background:#1f3b5c;color:#fff;border-radius:9pt;padding:2pt 7pt;margin:2pt;font-size:7.4pt">{x}</span>'
        for x in meth) + "</div>")
    out.append('<div class="ig-h">What the data says</div>')
    for k in (0, 4):
        out.append('<div class="ig-row">' + "".join(
            f'<div class="ig-tile{" hot" if h else ""}">{icon(i, 20, RED if h else NAVY)}<div class="v">{v}</div><div class="l">{l}</div></div>'
            for i, v, l, h in tiles[k:k + 4]) + "</div>")
    out.append('<div class="ig-note"><b>Bottom line:</b> orbit is crowded, concentrated and contested. India depends on it more each '
               'year while holding a shrinking share of it. Build capacity and resilience, and watch the orbit weekly.</div></div>')
    return "".join(out)


def orbits(M):
    rows = [("GEO 35,786 km", "Geostationary belt: communications, early warning, weather. The arc used by India (40-110 E) is among the "
             "most crowded on the belt.", f"{M['geo_arc20']}<small>satellites 40-110 E</small>", "#eef2f7"),
            ("MEO ~20,000 km", "Navigation constellations (GPS, GLONASS, Galileo, BeiDou). India's NavIC sits in GEO/inclined orbits.",
             "4<small>global GNSS systems</small>", "#f4f6f9"),
            ("LEO 1,050-1,200 km", "Coming: China's Guowang and Qianfan shells (about 27,000 planned). Debris here stays for centuries.",
             "~470<small>already launched</small>", "#fdf1f0"),
            ("LEO 750-900 km", f"THE DEAD CROWD: {pct(M['dead_debris_share'])} debris, much of it from the 2007 Chinese ASAT test and the "
             "2009 collision.", f"{M['dead_now']:,}<small>objects</small>", "#fbe3dd"),
            ("LEO 450-500 km", f"THE LIVE CROWD: {pct(M['band_active_share'])} working satellites, mostly Starlink. Up from "
             f"{M['band_2014']} objects in 2014.", f"{M['band_now']:,}<small>objects</small>", "#e3edf9"),
            ("LEO < 450 km", "Very low orbits: short-lived; where India's 2019 ASAT test was conducted, so its debris re-entered fast.",
             f"{M['shakti_alive']}<small>Shakti debris left</small>", "#f4f6f9")]
    body = "".join(f'<div class="r" style="background:{bg}"><div class="alt">{a}</div><div class="d">{d}</div><div class="n">{n}</div></div>'
                   for a, d, n, bg in rows)
    return f'<div class="ig lad">{body}</div>'


def methodology():
    st = [("database", "1. DATA", "CDM satellites, space weather, fires &middot; open catalogue, UCS, UNOOSA, official sources", "#1f3b5c"),
          ("filter", "2. PREPARE", "Validate, correct impossible values, decode codes, rebuild orbit year by year", "#2a5a8a"),
          ("magnifying-glass-chart", "3. ANALYSE", "Descriptive &rarr; diagnostic &rarr; predictive &rarr; prescriptive", "#2a78d6"),
          ("scale-balanced", "4. TEST", "Second source or second method for every headline; forecast back-test", "#3d8bd9"),
          ("flag", "5. DECIDE", "Impact on India and the Services, ORBITWATCH, way forward, Power BI", "#5a9be0")]
    cells = "".join(f'<div style="background:{c}">{icon(i, 16, "#fff")}<b>{t}</b>{d}</div>' for i, t, d, c in st)
    return f'<div class="ig"><div class="ig-chev">{cells}</div></div>'


def triservice(M):
    svc = [("anchor", "INDIAN NAVY", "#1f3b5c", ["Maritime domain awareness over the Indian Ocean rests on SAR and AIS satellites",
                                                  "GSAT-7 series: networked fleet communications at sea",
                                                  "Assume adversary satellites track carrier groups: emission control, deception"]),
           ("jet-fighter-up", "INDIAN AIR FORCE", "#2a78d6", ["Precision strike needs NavIC/GNSS and fresh imagery (Op Sindoor)",
                                                             "GSAT-7A: airborne and ground-station links",
                                                             "Space weather degrades GNSS and HF: storm drills for aircrew and ATC"]),
           ("person-military-rifle", "INDIAN ARMY", "#9a4a3a", [f"Northern border under persistent overhead ISR ({M['cn_isr_ops']} Chinese satellites)",
                                                               "Camouflage, concealment and deception against satellite revisit",
                                                               "Tactical satellite terminals and imagery down to formation level"])]
    cards = "".join(f'<div class="ig-svc"><div class="hd" style="background:{c}">{icon(i, 14, "#fff")} {h}</div><ul>'
                    + "".join(f"<li>{x}</li>" for x in pts) + "</ul></div>" for i, h, c, pts in svc)
    return (f'<div class="ig"><div class="ig-row">{cards}</div><div class="ig-joint">{icon("user-shield", 13)} <b>JOINT (HQ IDS / Defence Space '
            'Agency):</b> space situational awareness (ORBITWATCH) &middot; SBS-III at pace &middot; manoeuvrable, storm-hardened satellites '
            '&middot; commercial capacity on call &middot; a space doctrine that plans for denial of space</div></div>')


def orbitwatch(M, iw):
    col = {"RED": RED, "AMBER": AMBER, "GREEN": GREEN}
    cells = "".join(f'<div class="ig-iw" style="flex:0 0 23%"><span class="ig-light" style="background:{col[r.Status]}"></span><b>{r.Status}</b>'
                    f'<div class="v" style="color:{col[r.Status]}">{r["Latest value"]}</div>{r.Indicator[3:]}</div>'
                    for _, r in iw.iterrows())
    return (f'<div class="ig"><div class="ig-row" style="flex-wrap:wrap">{cells}</div><div class="ig-note"><b>Status, Sep 2026:</b> '
            f'{M["ow_red"]} Red, {M["ow_amber"]} Amber. The orbital environment, the ISR balance and India\'s share are all past their '
            'warning thresholds.</div></div>')


def roadmap():
    ph = [("PHASE 1 - INSTITUTIONALISE", "0-4 months", ["ORBITWATCH proof of concept at DSA", "Weekly space-situation brief to HQ IDS",
                                                       "Storm and conjunction drills written"]),
          ("PHASE 2 - FIELD", "4-24 months", ["SBS-III launches at pace; commercial imagery contracts", "Manoeuvre and fuel budgets for every "
                                              "satellite", "Indian ground radars and telescopes fused into ORBITWATCH"]),
          ("PHASE 3 - ASSURE", "2-5 years", ["Persistent coverage of northern borders and IOR", "Reserve and rapid-launch satellites",
                                             "Doctrine and exercises for operations with space denied"])]
    cells = "".join(f'<div style="background:{c}"><b>{t}</b><span class="n">{w}</span><ul>' + "".join(f"<li>{x}</li>" for x in pts) + "</ul></div>"
                    for (t, w, pts), c in zip(ph, ["#1f3b5c", "#2a78d6", "#3d8bd9"]))
    return f'<div class="ig"><div class="ig-chev">{cells}</div></div>'


def takeaways(M):
    tk = [("satellite", f"<b>Orbit is crowded.</b> {M['active_mult']:.0f} times more working satellites than in 2014; about "
                        f"{M['sc_base'] / 1000:.0f},000 by 2030."),
          ("flag", f"<b>Orbit is concentrated.</b> One country operates {M['us_share_now']:.0f}% of working satellites; India "
                   f"{M['in_share_now']:.1f}%."),
          ("burst", f"<b>Orbit is dangerous.</b> Collision risk about x{M['risk_ratio']:.0f}; high-altitude weapon debris lasts decades."),
          ("eye", f"<b>Orbit is contested.</b> China operates about {M['cn_isr_ops']} state ISR satellites; India about {M['in_isr_ops']}."),
          ("shield-halved", "<b>Numbers and resilience win.</b> More satellites buy coverage; manoeuvre, hardening and awareness keep them alive.")]
    return '<div class="ig">' + "".join(f'<div class="ig-tk"><div class="i">{icon(i, 14, "#fff")}</div><div>{t}</div></div>' for i, t in tk) + "</div>"
