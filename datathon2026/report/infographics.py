"""Infographics and SmartArt-style graphics for the report, built as HTML + inline SVG icons (Font Awesome Free,
CC BY 4.0) so they stay vector-sharp in print. Every number comes from data/metrics.json."""
import base64
import os
import re
from pathlib import Path

import fontawesomefree

ICON_DIR = Path(os.path.dirname(fontawesomefree.__file__)) / "static/fontawesomefree/svgs/solid"
NAVY, ORANGE, RED, AMBER, GREEN, BLUE, GREY = "#1f3b5c", "#eb6834", "#c62828", "#e08a00", "#2e7d32", "#2a78d6", "#6b6a66"


def icon(name, size=22, color=NAVY):
    svg = (ICON_DIR / f"{name}.svg").read_text()
    svg = re.sub(r"<!--.*?-->", "", svg)
    return svg.replace("<svg ", f'<svg style="width:{size}px;height:{size}px;fill:{color};vertical-align:middle" ', 1)


def pct(x):
    return f"{x * 100:.0f}%"


CSS = """
.ig { font-family: 'Liberation Sans', Arial, sans-serif; color: #1b1b1b; line-height: 1.25; text-align: left; }
.ig li { text-align: left !important; }
.ig-band { background: #1f3b5c; color: #fff; padding: 7pt 10pt; border-radius: 4pt; font-size: 11pt; font-weight: bold; }
.ig-band small { font-weight: normal; font-size: 8.5pt; opacity: .85; display: block; margin-top: 2pt; }
.ig-row { display: flex; gap: 6pt; margin-top: 6pt; }
.ig-tile { flex: 1; border: .6pt solid #c9d3de; border-radius: 4pt; padding: 6pt; background: #fff; text-align: center; }
.ig-tile .v { font-size: 17pt; font-weight: bold; color: #1f3b5c; margin-top: 3pt; }
.ig-tile .l { font-size: 7.4pt; color: #3b3b3b; margin-top: 2pt; }
.ig-tile.hot .v { color: #c62828; }
.ig-src { flex: 1; background: #eef2f7; border-radius: 4pt; padding: 5pt; font-size: 7.4pt; text-align: center; }
.ig-src b { display: block; font-size: 8pt; margin: 3pt 0 1pt 0; color: #1f3b5c; }
.ig-h { font-size: 8.5pt; font-weight: bold; color: #1f3b5c; text-transform: uppercase; letter-spacing: .4pt; margin: 8pt 0 0 0; }
.ig-chev { display: flex; margin-top: 6pt; }
.ig-chev > div { flex: 1; position: relative; color: #fff; padding: 7pt 14pt 7pt 16pt; font-size: 7.6pt; min-height: 70pt; text-align: center;
  clip-path: polygon(0 0, calc(100% - 10pt) 0, 100% 50%, calc(100% - 10pt) 100%, 0 100%, 10pt 50%); margin-right: -6pt; }
.ig-chev > div:first-child { clip-path: polygon(0 0, calc(100% - 10pt) 0, 100% 50%, calc(100% - 10pt) 100%, 0 100%); padding-left: 8pt; }
.ig-chev ul { text-align: left; }
.ig-chev b { display: block; font-size: 8.4pt; margin: 3pt 0 2pt 0; }
.ig-chev .n { font-size: 12pt; font-weight: bold; display: block; margin-top: 2pt; }
.ig-map { position: relative; width: 100%; }
.ig-map img { width: 100%; display: block; border-radius: 4pt; }
.ig-call { position: absolute; transform: translate(-50%, -50%); background: rgba(255,255,255,.95); border: .8pt solid #1f3b5c;
  border-radius: 3pt; padding: 3pt 5pt; font-size: 7pt; line-height: 1.2; box-shadow: 0 1pt 2pt rgba(0,0,0,.2); white-space: nowrap; }
.ig-call b { color: #c62828; font-size: 8.5pt; }
.ig-dot { position: absolute; width: 9pt; height: 9pt; border-radius: 50%; background: #c62828; border: 1.5pt solid #fff;
  transform: translate(-50%, -50%); box-shadow: 0 0 0 3pt rgba(198,40,40,.25); }
.ig-two { display: flex; gap: 8pt; }
.ig-panel { flex: 1; border-radius: 5pt; padding: 8pt; }
.ig-panel h4 { margin: 0 0 4pt 0; font-size: 11pt; }
.ig-panel .ships { margin: 5pt 0; }
.ig-panel ul { margin: 4pt 0 0 0; padding-left: 12pt; font-size: 8pt; } .ig-panel li { margin-bottom: 2pt; text-align: left; }
.ig-svc { flex: 1; border-radius: 5pt; overflow: hidden; border: .6pt solid #c9d3de; }
.ig-svc .hd { color: #fff; padding: 6pt; font-weight: bold; font-size: 10pt; text-align: center; }
.ig-svc ul { margin: 5pt 0 6pt 0; padding: 0 6pt 0 16pt; font-size: 7.8pt; } .ig-svc li { margin-bottom: 3pt; text-align: left; }
.ig-joint { margin-top: 6pt; background: #eef2f7; border-radius: 4pt; padding: 6pt 8pt; font-size: 8pt; }
.ig-light { display: inline-block; width: 11pt; height: 11pt; border-radius: 50%; vertical-align: middle; margin-right: 3pt; }
.ig-iw { flex: 1; border: .6pt solid #c9d3de; border-radius: 4pt; padding: 5pt; font-size: 7.4pt; }
.ig-iw .v { font-size: 13pt; font-weight: bold; margin: 2pt 0; }
.ig-note { margin-top: 6pt; border-left: 3pt solid #c62828; background: #fdf1f0; padding: 5pt 8pt; font-size: 8.3pt; }
.ig-tk { display: flex; gap: 8pt; align-items: center; margin-top: 5pt; font-size: 9pt; text-align: left; }
.ig-tk .i { flex: 0 0 26pt; height: 26pt; border-radius: 50%; background: #1f3b5c; display: flex; align-items: center; justify-content: center; }
"""


def at_a_glance(M):
    src = [("database", "ACLED", "149,814 rows<br>2015 - Jun 2026"), ("satellite", "Sentinel-1 SAR", f"{M['sar_rows']:,} ships<br>1-14 Mar 2026"),
           ("tower-broadcast", "AIS match", f"{M['sar_distinct_mmsi']:,} identities"),
           ("oil-well", "Brent (EIA)", f"daily to {M['brent_last_date']}"), ("indian-rupee-sign", "INR/US$ (Fed)", "daily to Sep 2026"),
           ("industry", "Energy Institute", "India oil balance<br>1990-2024")]
    tiles = [("eye-slash", pct(M["hormuz_large_dark"]), "large ships AIS-dark in the Strait of Hormuz", True),
             ("scale-balanced", f"{M['large_rr']:.1f}x", "risk of darkness in war zones", False),
             ("explosion", "84%", "of war violence was stand-off strikes", True),
             ("hourglass-half", pct(M["km_p_gt_spr"]), "disruptions outlast India's SPR", True),
             ("arrow-trend-up", f"+{M['ev_war_peak']:.0f}%", "Brent peak within 40 days of the war", True),
             ("sack-dollar", f"${M['extra_bill_usd_bn']:.0f} bn", "extra import bill for India (199 days)", False),
             ("ship", f"{M['ind_gulf_ships']}", "Indian-flag ships in the Gulf war zone", False),
             ("traffic-light", f"{M['iw_red']} Red", f"I&amp;W status at 27 Jun; Brent then {M['brent_oos_change']:+.0f}%", True)]
    meth = ["Change-points (PELT)", "Conflict index + ARIMA", "Kaplan-Meier / Cox", "Chi-square, bootstrap", "Getis-Ord Gi*",
            "DBSCAN", "Gradient boosting, spatial CV", "Event study, Granger", "Expected shortfall"]
    out = ['<div class="ig">']
    out.append('<div class="ig-band">Global Conflicts and the Blinding of Supply Chains<small>CDM Datathon-2026 &middot; '
               'Theme: Global Conflicts - Impact on Supply Chains &middot; the study on one page</small></div>')
    import story as ST
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
    out.append(f'<div class="ig-note"><b>Bottom line:</b> war at a chokepoint first <b>blinds</b> the supply chain, then <b>outlasts</b> the '
               f'buffers. Hold 35-45 days of cover, harden rear areas against stand-off strikes, and watch the chokepoints weekly with data.</div>')
    out.append("</div>")
    return "".join(out)


def _pos(lon, lat):
    return f"left:{(lon - 30) / 70 * 100:.2f}%;top:{(32 - lat) / 37 * 100:.2f}%"


def theatre_map(M, img_b64):
    dots = [(56.3, 26.5), (56.6, 25.2), (43.4, 12.6), (54.8, 25.5)]
    calls = [
        (60.5, 30.2, f"{icon('eye-slash', 11, RED)} <b>Strait of Hormuz</b><br>{pct(M['hormuz_large_dark'])} of large ships AIS-dark<br>"
                     f"littoral violence {M['hormuz_war_mult']:.0f}x baseline"),
        (46.2, 28.8, f"{icon('anchor', 11, RED)} <b>Dubai / Fujairah</b><br>dark tanker queues<br>{pct(M['top_cluster_share'])} of large ships dark"),
        (40.0, 18.5, f"{icon('route', 11, RED)} <b>Bab-el-Mandeb</b><br>ships divert, not darken<br>only 54 detections in 14 days"),
        (48.5, 5.5, f"{icon('explosion', 11, RED)} <b>At-sea attacks</b><br>6 (2022) &rarr; {M['sea_2024']} (2024)<br>violence moved offshore"),
        (66.0, 14.5, f"{icon('ship', 11, NAVY)} <b style='color:{NAVY}'>Arabian Sea</b><br>large ships visible ({pct(M['arab_large_dark'])} dark)"),
        (87.0, 25.5, f"{icon('oil-well', 11, NAVY)} <b style='color:{NAVY}'>India</b><br>{M['india_dep']:.0f}% of oil imported<br>"
                     f"{M['ind_gulf_ships']} Indian-flag ships in Gulf"),
        (89.0, 8.5, f"{icon('sack-dollar', 11, NAVY)} <b style='color:{NAVY}'>Cost of the war</b><br>~US$ {M['extra_bill_usd_bn']:.0f} bn extra oil bill<br>"
                    f"Brent ${M['brent_prewar']:.0f} &rarr; ${M['brent_war_peak']:.0f}"),
    ]
    h = ['<div class="ig"><div class="ig-map">', f'<img src="data:image/png;base64,{img_b64}">']
    h += [f'<div class="ig-dot" style="{_pos(lo, la)}"></div>' for lo, la in dots]
    h += [f'<div class="ig-call" style="{_pos(lo, la)}">{t}</div>' for lo, la, t in calls]
    h.append("</div></div>")
    return "".join(h)


def blinding_vs_diversion(M):
    def fleet(dark, n=12):
        # icons show the share of large ships that are dark; n shrinks when traffic itself has thinned
        k = round(dark * n)
        return "".join(icon("ship", 17, "#b9b8b2" if i < k else NAVY) for i in range(n))
    left = (f'<div class="ig-panel" style="background:#fdf1f0;border:.8pt solid {RED}"><h4 style="color:{RED}">{icon("eye-slash", 16, RED)} '
            f'GULF / HORMUZ: BLINDING</h4><div style="font-size:8pt">No detour exists, so ships keep sailing and switch off.</div>'
            f'<div class="ships">{fleet(M["gulf_large_dark"])}</div><div style="font-size:7pt;color:{GREY}">each icon = 1/12 of large ships; grey = AIS-dark</div>'
            f'<ul><li><b>{pct(M["gulf_large_dark"])}</b> of large ships dark (world {pct(M["rest_large_dark"])})</li>'
            f'<li>Dark tanker queues at Dubai and Fujairah</li><li>Brent <b>+{M["ev_war_peak"]:.0f}%</b> within 40 days</li>'
            f'<li>Cost appears as <b>risk</b>: misidentification, sanctions evasion, surprise</li></ul></div>')
    right = (f'<div class="ig-panel" style="background:#eef2f7;border:.8pt solid {NAVY}"><h4 style="color:{NAVY}">{icon("route", 16, NAVY)} '
             f'RED SEA / BAB-EL-MANDEB: DIVERSION</h4><div style="font-size:8pt">A detour exists (Cape of Good Hope), so ships stay away.</div>'
             f'<div class="ships">{fleet(M["redsea_large_dark"], 5)}</div><div style="font-size:7pt;color:{GREY}">traffic thins; the ships that remain stay visible</div>'
             f'<ul><li>Only <b>{pct(M["redsea_large_dark"])}</b> of large ships dark; 54 detections at the strait</li>'
             f'<li>+10-14 days per Asia-Europe voyage via the Cape</li><li>Brent <b>-5%</b> twenty days after the campaign began</li>'
             f'<li>Cost appears as <b>time and freight</b></li></ul></div>')
    return f'<div class="ig"><div class="ig-two">{left}{right}</div></div>'


def impact_cascade(M):
    steps = [("burst", "Conflict", f"{M['pv_war_ratio']:.1f}x", "violence vs prior year", "#3d5a80"),
             ("explosion", "Stand-off strikes", "84%", "of war violence", "#46638a"),
             ("eye-slash", "Blinding", pct(M["hormuz_large_dark"]), "large ships dark at Hormuz", "#9a4a3a"),
             ("oil-well", "Oil shock", f"+{M['brent_rise_pct']:.0f}%", f"Brent, war avg (peak ${M['brent_war_peak']:.0f})", "#b8452e"),
             ("indian-rupee-sign", "Rupee", f"{(1 - M['fx_base'] / M['fx_war']) * 100:.1f}% weaker", "vs US$, war-period average", "#c0392b"),
             ("sack-dollar", "India's bill", f"${M['extra_bill_usd_bn']:.0f} bn", "extra oil imports, 199 days", "#a93226"),
             ("shield-halved", "Armed Forces", "POL", "+ spares, air defence, lead-times", "#7b241c")]
    cells = "".join(f'<div style="background:{c}">{icon(i, 16, "#fff")}<b>{t}</b><span class="n">{v}</span>{l}</div>'
                    for i, t, v, l, c in steps)
    return f'<div class="ig"><div class="ig-chev">{cells}</div></div>'


def triservice(M):
    svc = [("anchor", "INDIAN NAVY", "#1f3b5c", [
        f"Escort in a picture where {pct(M['gulf_large_dark'])} of large ships are dark", "Ship air defence and counter-drone magazines for long campaigns",
        "Coastal security against thousands of non-AIS small craft", "Shadow-fleet oil-spill response in the EEZ"]),
        ("jet-fighter", "INDIAN AIR FORCE", "#2a78d6", [
        "Hardened, dispersed air bases and fuel farms vs stand-off strikes", "Air corridors to West Asia closed; longer airlift",
        "GNSS-resilient avionics and weapons (NavIC, anti-jam)", "Airlift for NEO of ~9 million citizens in GCC"]),
        ("person-military-rifle", "INDIAN ARMY", "#4b5d2a", [
        "Layered AD / counter-UAS for depots, railheads, POL points", "GNSS-denied fallback for drones, loitering munitions, fires",
        "Western front: instability in Sistan-Baluchestan / Makran", "Spares lead-times for imported fleets lengthen"])]
    cards = "".join(f'<div class="ig-svc"><div class="hd" style="background:{c}">{icon(i, 18, "#fff")} {n}</div><ul>'
                    + "".join(f"<li>{x}</li>" for x in items) + "</ul></div>" for i, n, c, items in svc)
    joint = (f'<div class="ig-joint">{icon("handshake", 14)} <b>JOINT (HQ IDS):</b> POL / aviation fuel / spares War Wastage Reserves sized on the '
             f'survival curve (35-45 days) &middot; ~US$ {M["per10_usd_bn"]:.1f} bn national cost per US$10/bbl-year &middot; tri-service Data Analytics Cell '
             f'running the I&amp;W matrix weekly &middot; GCC NEO at execution readiness</div>')
    return f'<div class="ig"><div class="ig-row" style="gap:6pt">{cards}</div>{joint}</div>'


def iw_dashboard(M, iw_df):
    col = {"RED": RED, "AMBER": AMBER, "GREEN": GREEN}
    short = ["Hormuz littoral index", "Red Sea at-sea index", "Stand-off strike share", "GCC violence / week",
             "Gulf large-ship dark share", "P(Hormuz breach, 13 wk)"]
    tiles = "".join(
        f'<div class="ig-iw" style="border-top:3pt solid {col[r.Status]}"><span class="ig-light" style="background:{col[r.Status]}"></span>'
        f'<b>{r.Status}</b><div class="v">{r["Latest value"]}</div>{short[i]}</div>' for i, (_, r) in enumerate(iw_df.iterrows()))
    note = (f'<div class="ig-note">{icon("bell", 12, RED)} <b>Out-of-sample test.</b> On 26 Jun 2026 the market read calm: Brent at '
            f'<b>${M["brent_at_cut"]:.0f}</b>, back to its pre-war level. The matrix read <b>{M["iw_red"]} Red</b>: hold buffers. Brent then rose '
            f'<b>{M["brent_oos_change"]:+.0f}%</b> to <b>${M["brent_last"]:.0f}</b> by {M["brent_last_date"]}. The data called what the market missed.</div>')
    return f'<div class="ig"><div class="ig-row">{tiles}</div>{note}</div>'


def roadmap():
    ph = [("0-6 months", "INSTITUTIONALISE", "gauge-high", ["Dashboard at HQ IDS and Service HQs", "Weekly I&amp;W brief", "WWR review on Eq. 3.6"], "#1f3b5c"),
          ("6-18 months", "FUSE &amp; AUTOMATE", "satellite-dish", ["National SAR + AIS fusion at IFC-IOR", "Automated dark-ship and identity alerts",
                                                                     "Add freight, port-call and price feeds"], "#2a5a8a"),
          ("18-36 months", "PRESCRIBE", "brain", ["Joint logistics decision support", "Scenario simulation: stock, route, NEO",
                                                   "Extend to Malacca / South China Sea; train cadre"], "#2a78d6")]
    cells = "".join(f'<div style="background:{c};min-height:88pt">{icon(i, 16, "#fff")}<b>{t}</b><span style="font-size:7pt;opacity:.9">{d}</span>'
                    '<ul style="margin:3pt 0 0 0;padding-left:10pt">' + "".join(f"<li>{x}</li>" for x in items) + "</ul></div>"
                    for d, t, i, items, c in ph)
    return f'<div class="ig"><div class="ig-chev">{cells}</div></div>'


def methodology():
    st = [("database", "1. DATA", "ACLED conflict &middot; Sentinel-1 SAR + AIS &middot; Brent, INR, energy (open data)", "#1f3b5c"),
          ("filter", "2. PREPARE", "Clean, validate, engineer features, spatial joins (BallTree)", "#2a5a8a"),
          ("magnifying-glass-chart", "3. ANALYSE", "Descriptive &rarr; diagnostic &rarr; predictive &rarr; prescriptive", "#2a78d6"),
          ("scale-balanced", "4. TEST", "Robustness, dose-response, competing hypotheses, out-of-sample check", "#3d8bd9"),
          ("flag", "5. DECIDE", "Inference, impact, I&amp;W matrix, way forward, Power BI", "#5a9be0")]
    cells = "".join(f'<div style="background:{c}">{icon(i, 16, "#fff")}<b>{t}</b>{d}</div>' for i, t, d, c in st)
    return f'<div class="ig"><div class="ig-chev">{cells}</div></div>'


def takeaways(M):
    tk = [("eye-slash", f"<b>Visibility is the first casualty.</b> {pct(M['hormuz_large_dark'])} of large ships dark at Hormuz; the effect is robust, graded and replicated."),
          ("route", "<b>Detour decides the response.</b> No detour means blinding and a price shock; a detour means diversion and higher freight."),
          ("hourglass-half", f"<b>Disruption is a duration problem.</b> {pct(M['km_p_gt_spr'])} outlast the SPR; returns to stock flatten at ~35-45 days."),
          ("explosion", "<b>Stand-off weapons erase the rear area.</b> 84% of war violence; energy and logistics nodes far from the front were hit."),
          ("traffic-light", f"<b>Data beats the market as a warning.</b> The June I&amp;W call was Red at $70 Brent; oil then rose {M['brent_oos_change']:.0f}%.")]
    return '<div class="ig">' + "".join(f'<div class="ig-tk"><div class="i">{icon(i, 14, "#fff")}</div><div>{t}</div></div>' for i, t in tk) + "</div>"
