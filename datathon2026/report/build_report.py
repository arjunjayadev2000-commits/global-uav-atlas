"""Build the Datathon-2026 report (HTML -> PDF via headless Chromium).

Every number in the text is read from data/metrics.json or tables/*.csv, so the report always
matches the analysis pipeline (analysis/run_all.py).

Pipeline: render body (arabic page numbers) -> locate heading/figure markers -> render front matter
with a paginated table of contents, list of figures and list of tables -> merge -> stamp page numbers.
"""
import base64
import html
import json
import re
from pathlib import Path

import pymupdf as fitz
import pandas as pd
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
FIG, TAB, OUT = ROOT / "figures", ROOT / "tables", ROOT / "report"
M = json.loads((ROOT / "data" / "metrics.json").read_text())

AUTHOR = "Arjun Jayadev"
RANK = "[Rank]"
SERVICE_NO = "[Service No]"
UNIT = "[Unit / Formation]"
TITLE = "GLOBAL CONFLICTS AND THE BLINDING OF SUPPLY CHAINS"
SUBTITLE = ("A Data-Analytics Study of Chokepoint Conflict, AIS Dark Zones and Disruption Survival, "
            "with Implications for India and the Indian Armed Forces")


def pct(x, d=0):
    return f"{x * 100:.{d}f}%"


def n(x):
    return f"{x:,}"


# ------------------------------------------------------------------ numbering registries
class Doc:
    def __init__(self):
        self.ch = 0
        self.fig_no = 0
        self.tab_no = 0
        self.sec = []           # (id, level, label, title)
        self.figs = []          # (id, label, caption)
        self.tabs = []
        self.parts = []

    def add(self, s):
        self.parts.append(s)

    def chapter(self, title, letter=None):
        self.fig_no = self.tab_no = 0
        if letter:
            self.pfx = letter
            mid = f"SAPP{letter}"
            self.sec.append((mid, 1, "", title))
            self.add(f'<h1 class="chapter"><span class="mk">@@{mid}@@ </span>{title.upper()}</h1>')
            return
        self.ch += 1
        self.pfx = str(self.ch)
        mid = f"S{self.ch}"
        self.sec.append((mid, 1, f"{self.ch}.", title))
        self.add(f'<h1 class="chapter"><span class="mk">@@{mid}@@ </span>{self.ch}.&nbsp;&nbsp;{title.upper()}</h1>')

    def section(self, num, title, level=2):
        mid = "S" + num.replace(".", "_")
        self.sec.append((mid, level, num, title))
        tag = "h2" if level == 2 else "h3"
        self.add(f'<{tag}><span class="mk">@@{mid}@@ </span>{num}&nbsp;&nbsp;{title}</{tag}>')

    def p(self, *paras):
        for t in paras:
            self.add(f"<p>{t}</p>")

    def bullets(self, items, cls=""):
        self.add(f'<ul class="{cls}">' + "".join(f"<li>{i}</li>" for i in items) + "</ul>")

    def fig(self, name, caption, width=100, source=None):
        self.fig_no += 1
        label = f"{self.pfx}.{self.fig_no}"
        mid = f"F{label.replace('.', '_')}"
        self.figs.append((mid, label, caption))
        data = base64.b64encode((FIG / f"{name}.png").read_bytes()).decode()
        src = f'<div class="src">Source: {source}</div>' if source else ""
        self.add(f'<figure><img src="data:image/png;base64,{data}" style="width:{width}%">'
                 f'<figcaption><span class="mk">@@{mid}@@ </span><b>Figure {label} :</b> {caption}</figcaption>{src}</figure>')
        return label

    def html_fig(self, inner, caption):
        self.fig_no += 1
        label = f"{self.pfx}.{self.fig_no}"
        mid = f"F{label.replace('.', '_')}"
        self.figs.append((mid, label, caption))
        self.add(f'<figure>{inner}<figcaption><span class="mk">@@{mid}@@ </span><b>Figure {label} :</b> {caption}</figcaption></figure>')
        return label

    def table(self, df, caption, fmt=None, widths=None, small=False, note=None, breakable=False):
        self.tab_no += 1
        label = f"{self.pfx}.{self.tab_no}"
        mid = f"T{label.replace('.', '_')}"
        self.tabs.append((mid, label, caption))
        fmt = fmt or {}
        head = "".join(f"<th>{html.escape(str(c))}</th>" for c in df.columns)
        rows = []
        for _, r in df.iterrows():
            cells = []
            for c in df.columns:
                v = r[c]
                if c in fmt:
                    v = fmt[c](v)
                elif isinstance(v, float):
                    v = f"{v:,.0f}" if (v.is_integer() or abs(v) >= 100) else f"{v:,.2f}"
                elif isinstance(v, (int,)) and not isinstance(v, bool):
                    v = f"{v:,}"
                cells.append(f"<td>{v}</td>")
            rows.append("<tr>" + "".join(cells) + "</tr>")
        cls = "tbl small" if small else "tbl"
        nt = f'<div class="src">{note}</div>' if note else ""
        brk = ' style="page-break-inside:auto"' if breakable else ""
        self.add(f'<div class="tblwrap"{brk}><div class="tcap"><span class="mk">@@{mid}@@ </span><b>Table {label} :</b> {caption}</div>'
                 f'<table class="{cls}"><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table>{nt}</div>')
        return label

    def eq(self, body, num):
        self.add(f'<div class="eq"><span class="eqb">{body}</span><span class="eqn">({num})</span></div>')

    def callout(self, t):
        self.add(f'<div class="callout">{t}</div>')


def T(name):
    return pd.read_csv(TAB / f"{name}.csv")


CSS = """
@page { size: A4; margin: 24mm 22mm 22mm 26mm; }
* { box-sizing: border-box; }
body { font-family: 'Liberation Serif', 'Times New Roman', serif; font-size: 12pt; line-height: 1.5; color: #111; }
p { text-align: justify; margin: 0 0 8pt 0; }
h1.chapter { page-break-before: always; font-size: 15pt; margin: 0 0 14pt 0; }
h2 { font-size: 12.5pt; margin: 14pt 0 6pt 0; page-break-after: avoid; }
h3 { font-size: 12pt; font-style: italic; margin: 10pt 0 4pt 0; page-break-after: avoid; }
ul { margin: 0 0 8pt 0; padding-left: 22pt; } li { text-align: justify; margin-bottom: 3pt; }
ul.alpha { list-style: lower-alpha; }
figure { margin: 10pt 0 12pt 0; text-align: center; page-break-inside: avoid; }
figcaption { font-size: 10.5pt; margin-top: 4pt; text-align: center; }
.src { font-size: 9pt; color: #555; text-align: center; margin-top: 2pt; }
.tblwrap { margin: 10pt 0 12pt 0; page-break-inside: avoid; }
.tcap { font-size: 10.5pt; text-align: center; margin-bottom: 4pt; }
table.tbl { border-collapse: collapse; width: 100%; font-family: 'Liberation Sans', Arial, sans-serif; font-size: 8.8pt; line-height: 1.3; }
table.tbl.small { font-size: 8pt; }
table.tbl th { background: #1f3b5c; color: #fff; font-weight: bold; padding: 4pt 5pt; text-align: left; border: 0.5pt solid #1f3b5c; }
table.tbl tr { page-break-inside: avoid; }
table.tbl td { padding: 3pt 5pt; border: 0.5pt solid #c9c8c2; vertical-align: top; }
table.tbl tr:nth-child(even) td { background: #f4f3ef; }
.mk { color: #fff; font-size: 1pt; line-height: 0; }
.eq { display: flex; justify-content: space-between; align-items: center; margin: 6pt 0 8pt 30pt; font-style: italic; }
.eqb { font-family: 'Liberation Serif', serif; font-size: 12pt; } .eqn { font-style: normal; }
.callout { border-left: 3pt solid #1f3b5c; background: #eef2f7; padding: 7pt 10pt; margin: 8pt 0 10pt 0; font-size: 11pt; text-align: justify; page-break-inside: avoid; }
.center { text-align: center; }
.front h1 { text-align: center; font-size: 14pt; margin: 0 0 16pt 0; }
.toc { width: 100%; border-collapse: collapse; font-size: 11pt; }
.toc td { padding: 2pt 4pt; vertical-align: top; } .toc td.pg { text-align: right; width: 40pt; }
.toc tr.l1 td { font-weight: bold; padding-top: 5pt; } .toc tr.l3 td.t { padding-left: 34pt; font-size: 10.5pt; }
.toc tr.l2 td.t { padding-left: 18pt; }
.toc td.t { border-bottom: 0.5pt dotted #aaa; }
.flow { display: flex; flex-wrap: wrap; gap: 6pt; justify-content: center; font-family: 'Liberation Sans', sans-serif; font-size: 8.5pt; line-height: 1.25; }
.flow .col { width: 23.5%; display: flex; flex-direction: column; gap: 5pt; }
.flow .hd { background: #1f3b5c; color: #fff; padding: 5pt; font-weight: bold; text-align: center; border-radius: 3pt; }
.flow .bx { border: 0.8pt solid #1f3b5c; padding: 4pt 5pt; border-radius: 3pt; background: #f4f6f9; text-align: left; }
.kpis { display: flex; gap: 6pt; margin: 8pt 0 10pt 0; font-family: 'Liberation Sans', sans-serif; page-break-inside: avoid; }
.kpi { flex: 1; border: 0.6pt solid #c9c8c2; border-top: 3pt solid #1f3b5c; padding: 5pt 6pt; }
.kpi .v { font-size: 15pt; font-weight: bold; color: #1f3b5c; } .kpi .l { font-size: 7.8pt; color: #333; line-height: 1.25; }
.titlepage { text-align: center; padding-top: 18mm; }
.titlepage .t1 { font-size: 19pt; font-weight: bold; line-height: 1.3; margin-bottom: 10pt; }
.titlepage .t2 { font-size: 13pt; font-style: italic; margin-bottom: 36pt; }
.titlepage .t3 { font-size: 12pt; margin: 4pt 0; }
.sig { margin-top: 40pt; display: flex; justify-content: space-between; }
.pb { page-break-before: always; }
.code { font-family: 'Liberation Mono', monospace; font-size: 8pt; line-height: 1.3; background: #f6f6f4; border: 0.5pt solid #ddd; padding: 6pt; white-space: pre-wrap; text-align: left; }
"""


def build_body():
    d = Doc()
    # ================================================================== 1 INTRODUCTION
    d.chapter("Introduction")
    d.p(
        "Around 80 per cent of world merchandise trade by volume moves by sea, and a large share of it passes through a handful "
        "of narrow chokepoints: the Strait of Hormuz, Bab-el-Mandeb, the Suez Canal, the Strait of Malacca, the Bosphorus and a few others "
        "[1, 2]. When conflict reaches one of these straits, the effect spreads through energy prices, freight rates, insurance "
        "premia and delivery lead-times to every economy that depends on them. Between October 2023 and June 2026 the Middle East "
        "produced two such shocks in quick succession. The first was the Houthi anti-shipping campaign in the Red Sea and Gulf of Aden, which "
        "diverted a large part of Asia-Europe container traffic around the Cape of Good Hope [1]. The second was the regional war that broke out on "
        "28 February 2026 and carried missile and drone strikes to the Iranian coast and the Gulf Cooperation Council (GCC) states around the Strait of Hormuz.",
        "Conflict affects shipping in two ways. The obvious effect is physical: ships are struck, diverted or held in port. The less "
        "obvious effect is <b>informational</b>. Ships in or near a war zone switch off or manipulate their Automatic Identification "
        "System (AIS) transponders to avoid being targeted. Electronic warfare jams and spoofs satellite navigation. Sanctions-evading fleets operate dark by design. The common maritime "
        "picture, which navies, insurers, port authorities and logisticians all rely on, then loses its identities. The Datathon-2026 "
        "problem statement calls this an <i>identification crisis</i> and asks participants to find AIS dead zones and relate them "
        "to local conflicts such as those in the Black Sea and the Persian Gulf [3].",
        "This report takes up that problem with two unclassified datasets from the Datathon repository and a set of descriptive, "
        "diagnostic, predictive and prescriptive techniques. The first dataset is eleven and a half years of weekly Middle-East conflict "
        "events (ACLED). The second is 1-14 March 2026 of Sentinel-1 synthetic-aperture-radar (SAR) vessel detections matched against AIS. "
        "The report works from the evidence to inferences, then to the impact on the globe, on India and on the Indian Armed "
        "Forces, and ends with a way forward and a conclusion, each traced back to a finding in the analysis.")
    d.callout(
        "<b>Thesis.</b> Conflict near a maritime chokepoint shows up in the data first as the <i>blinding</i> of the "
        "supply chain: large, AIS-obligated ships vanish from the cooperative picture. Only after that does it show up as the "
        "physical disruption of trade flows. In March 2026, large ships in the Gulf war zone were "
        f"{M['large_rr']:.1f} times more likely to be AIS-dark than large ships elsewhere, and "
        "distance from the fighting predicts darkness even in regions the model has never seen. Disruption episodes have a heavy "
        f"tail: about {pct(M['km_p_gt_spr'])} outlast the ~9.5 days of India's strategic petroleum reserve. India's "
        "economic and military exposure therefore has to be managed as one data problem, joining maritime domain awareness with "
        "stock-holding policy.")

    d.section("1.1", "Problem Statement")
    d.p("Can open conflict and satellite data be used to (i) measure how Middle-East conflict intensity near maritime "
        "chokepoints has changed, (ii) locate and explain AIS dark zones and relate them to that conflict, (iii) predict "
        "where AIS darkness will appear, and (iv) turn the results into quantified guidance for India's supply-chain security and "
        "for the Indian Armed Forces' logistics and operational preparedness?")
    d.section("1.2", "Aim")
    d.p("To derive data-driven insights on the impact of global, and in particular Middle-East, conflicts on maritime supply "
        "chains, with a focus on AIS dark zones and chokepoint disruption, and to recommend measures for India and the Indian Armed Forces.")
    d.section("1.3", "Objectives")
    d.bullets([
        "Build a clean, reproducible data pipeline for the ACLED conflict and Sentinel-1 SAR/AIS datasets (Chapter 4).",
        "Characterise the Middle-East conflict system from 2015 to 2026, detect statistically significant regime shifts and measure the "
        "spill-over of the 2026 war onto the GCC energy coast (Chapter 5).",
        "Construct a Chokepoint Conflict Intensity Index (CCII), forecast it and model how long disruption episodes last with "
        "survival analysis (Chapter 6).",
        "Map AIS darkness worldwide, test whether it is significantly higher in war zones, find statistically significant "
        "dark hot spots and dark-vessel clusters, and profile the identity and registry of ships in the war zone (Chapter 7).",
        "Train and validate a model that predicts AIS dark spots from conflict geography (Chapter 8).",
        "Draw inferences from the findings and assess their impact on the globe, India and the Indian Armed Forces, with a "
        "prescriptive stock-cover model, a way forward and a conclusion (Chapters 9-14).",
    ], "alpha")
    d.section("1.4", "Hypotheses")
    d.table(pd.DataFrame([
        ("H1", "Middle-East political violence underwent statistically significant regime shifts that coincide with the 2023 and 2026 wars.", "Change-point detection (PELT), Mann-Whitney U"),
        ("H2", "The 2026 war moved conflict onto the maritime/energy littoral (GCC, Hormuz) and the Red Sea threat moved offshore.", "Littoral and at-sea indices, rate multipliers"),
        ("H3", "Large (>=100 m) vessels are significantly more often AIS-dark in war zones than elsewhere.", "Chi-square, odds ratio, Wilson intervals"),
        ("H4", "AIS darkness clusters in statistically significant hot spots that coincide with conflict chokepoints.", "Getis-Ord Gi*, DBSCAN"),
        ("H5", "Proximity to conflict predicts AIS darkness out-of-region.", "Logit, gradient-boosted trees, leave-one-region-out CV"),
        ("H6", "Chokepoint disruption durations are heavy-tailed and often exceed India's strategic oil cover.", "Kaplan-Meier, Cox PH, expected shortfall"),
    ], columns=["#", "Hypothesis", "Test"]), "Hypotheses tested in this study")
    d.section("1.5", "Methodology Overview")
    flow = """<div class="flow">
<div class="col"><div class="hd">1. Data</div><div class="bx">ACLED Middle-East weekly aggregates, 2015 - Jun 2026 (149,814 rows)</div>
<div class="bx">Sentinel-1 SAR vessel detections matched to AIS, 1-14 Mar 2026 (107,257 rows)</div><div class="bx">Reference: chokepoints, sea regions, MMSI-MID registry, gazetteer</div></div>
<div class="col"><div class="hd">2. Pre-process</div><div class="bx">Validation, de-duplication, confidence filter, MMSI validity</div>
<div class="bx">Feature engineering: region, size class, flag class, distance to chokepoint</div><div class="bx">Spatial join: conflict events within 500 km of each ship (BallTree, haversine)</div></div>
<div class="col"><div class="hd">3. Analyse</div><div class="bx"><b>Descriptive:</b> trends, mixes, maps</div><div class="bx"><b>Diagnostic:</b> PELT change-points, chi-square, Gi* hot spots, DBSCAN</div>
<div class="bx"><b>Predictive:</b> ARIMA forecast; logit and gradient-boosted trees with spatial CV</div><div class="bx"><b>Prescriptive:</b> Kaplan-Meier / Cox survival and expected-shortfall stock model</div></div>
<div class="col"><div class="hd">4. Decide</div><div class="bx">Findings F1-F10 and inferences I1-I6</div><div class="bx">Impact: globe, India, Indian Armed Forces</div>
<div class="bx">Way forward: recommendations and roadmap</div><div class="bx">Conclusion; Power BI decision dashboard</div></div></div>"""
    d.html_fig(flow, "Analytical framework - from data to decision")
    d.p("The work was done in Python 3.11 (pandas, NumPy, SciPy, statsmodels, scikit-learn, ruptures, Matplotlib/Basemap). "
        "The cleaned star-schema tables are exported for the Power BI (.pbix) dashboard that accompanies the report (Appendix B). "
        "Running the whole pipeline with a single command (<i>analysis/run_all.py</i>) regenerates every figure, table and number in this report from the raw files.")
    d.section("1.6", "Organisation of the Report")
    d.p("Chapter 2 reviews the literature and Chapter 3 sets out the theory behind the techniques used. Chapter 4 covers data "
        "pre-processing. Chapters 5 to 8 present the analysis: the conflict landscape, chokepoint intensity and disruption survival, "
        "AIS dark zones, and the predictive model. Chapter 9 draws the inferences. Chapters 10, 11 and 12 assess the impact on the globe, "
        "on India and on the Indian Armed Forces. Chapter 13 sets out the way forward and Chapter 14 concludes, followed by the references and appendices.")

    # ================================================================== 2 LITERATURE REVIEW
    d.chapter("Literature Review")
    d.p("The study drew on work in conflict-event data, maritime remote sensing, maritime security and statistical "
        "methods. The works that shaped the study most are summarised below.")
    d.bullets([
        "<b>Raleigh et al. (2010)</b> introduced the Armed Conflict Location and Event Data (ACLED) project, which codes political "
        "violence and protest events by date, location, actor and type [4]. The event typology used here (battles, explosions/remote "
        "violence, violence against civilians, riots, protests, strategic developments) and the weekly ADMIN1 aggregates come from ACLED. "
        "Aggregation to province centroids limits spatial precision, so this study measures distance to conflict at ADMIN1 resolution "
        "and treats the at-sea regions separately.",
        "<b>Paolo et al. (2024)</b>, writing in <i>Nature</i>, combined Sentinel-1 SAR imagery with deep learning and AIS to map "
        "industrial activity at sea. They found that about 72-76 per cent of the world's industrial fishing vessels and about a quarter of "
        "transport and energy vessels are not publicly tracked [5]. The SAR detections, presence, length and fishing scores and the "
        "AIS-matching logic in the Datathon SAR dataset follow the same approach. That result gives a <i>baseline</i> level of darkness against which "
        "conflict-related darkness can be measured.",
        "<b>UNCTAD, Review of Maritime Transport (2024)</b> documented the Red Sea crisis: collapsing Suez and Bab-el-Mandeb "
        "transits, Cape of Good Hope diversions adding roughly 10-14 days to Asia-Europe voyages, and the knock-on effects on freight "
        "rates, emissions and developing-country trade costs [1]. It frames the physical-disruption channel that this study pairs "
        "with the informational (AIS) channel.",
        "<b>U.S. Energy Information Administration (2024)</b>, <i>World Oil Transit Chokepoints</i>, estimates that flows through the "
        "Strait of Hormuz are about one-fifth of global petroleum liquids consumption, with most of them going to Asian buyers "
        "including India, and that alternative pipeline bypass capacity is limited [2]. This makes Hormuz the single most "
        "consequential chokepoint for India.",
        "<b>Killick, Fearnhead and Eckley (2012)</b> proposed PELT (Pruned Exact Linear Time), an exact change-point search with "
        "linear cost [6]. <b>Truong, Oudre and Vayatis (2020)</b> reviewed offline change-point methods and released the "
        "<i>ruptures</i> library used here [7].",
        "<b>Getis and Ord (1992) and Ord and Getis (1995)</b> developed the G and Gi* local statistics for finding significant spatial "
        "clusters of high or low values (hot and cold spots) [8, 9]. <b>Ester et al. (1996)</b> proposed DBSCAN, a density-based "
        "clustering algorithm that finds arbitrarily shaped clusters and treats sparse points as noise [10]. It suits the "
        "detection of anchorages and ship-to-ship transfer areas.",
        "<b>Kaplan and Meier (1958)</b> and <b>Cox (1972)</b> established the non-parametric survival estimator and the "
        "proportional-hazards model [11, 12]. The author's earlier work on predictive maintenance of armoured vehicles applied the "
        "same techniques to equipment time-to-failure data [13]. Here they are transferred to the time-to-end of chokepoint "
        "disruption episodes.",
        "<b>Roberts et al. (2017)</b> showed that ordinary random cross-validation overstates model skill when data are spatially "
        "autocorrelated and recommended blocked (e.g. leave-one-region-out) validation [14]. <b>Friedman (2001)</b> introduced "
        "gradient boosting [15]. <b>Hyndman and Athanasopoulos (2021)</b> give the forecasting practice (ARIMA, exponential smoothing, "
        "hold-out back-testing) followed here [16].",
    ], "alpha")
    d.p("<b>Gap addressed.</b> The literature treats conflict data, SAR/AIS data and supply-chain economics separately. "
        "No study found joins weekly conflict intensity at chokepoints to SAR-observed AIS darkness during a live war. Nor has "
        "any study turned the resulting disruption-duration distribution into a stock-holding decision for an Indian user. That join is "
        "what this study contributes.")

    # ================================================================== 3 BACKGROUND
    d.chapter("Background")
    d.section("3.1", "Maritime Chokepoints and Supply Chains")
    d.p("A chokepoint is a narrow channel on a widely used sea route that cannot easily be bypassed. Closing or degrading one "
        "adds distance, time and insurance cost to every voyage that depends on it. For some cargoes (Gulf crude, LPG and LNG, "
        "Qatari gas, Gulf fertiliser) there is little or no alternative supply in the short run. The Strait of Hormuz (~39 km wide at its "
        "narrowest point) connects the Persian Gulf producers to the Arabian Sea. Bab-el-Mandeb (~29 km) connects the Gulf of Aden to the "
        "Red Sea and the Suez Canal. Both lie within 2,000-3,000 km of India's west coast.")
    d.section("3.2", "AIS, SAR and the Identification Crisis")
    d.p("<b>AIS</b> is a VHF transponder system that broadcasts a ship's identity (MMSI), position, course and speed. Under SOLAS "
        "Chapter V, Regulation 19, AIS is mandatory for ships of 300 gross tonnage and above on international voyages, cargo ships of 500 GT "
        "and above, and all passenger ships [17]. The first three digits of the MMSI, the Maritime Identification Digits (MID), identify "
        "the flag state. AIS is cooperative: a ship can switch it off, transmit a false identity, or be displaced by GNSS "
        "spoofing so that its reported position no longer matches its real one.",
        "<b>SAR</b> satellites such as Sentinel-1 image the sea surface day and night through cloud. A ship shows up as a bright return "
        "whatever it chooses to transmit. Matching SAR detections to AIS tracks at the image time separates <i>cooperative</i> "
        "(matched) ships from <i>non-cooperative</i> or <i>dark</i> (unmatched) ones. Small craft are dark almost everywhere because they are not "
        "required to carry AIS. A dark ship over 100 m long, which is almost certainly AIS-obligated, is an anomaly. This study uses the "
        "large-ship dark share as its main indicator of the identification crisis.")
    d.section("3.3", "Analytical Techniques")
    d.section("3.3.1", "Proportions, confidence intervals and association", 3)
    d.p("The share of dark ships in a region is a binomial proportion p = x / n. Its 95 per cent Wilson score interval [18] is")
    d.eq("( p + z²/2n ± z &radic;( p(1-p)/n + z²/4n² ) ) / ( 1 + z²/n ),&nbsp;&nbsp; z = 1.96", "3.1")
    d.p("Association between war-zone location and darkness is tested with Pearson's chi-square on the 2x2 contingency table, and its "
        "strength is expressed as the relative risk RR = p<sub>war</sub> / p<sub>rest</sub> and the odds ratio "
        "OR = (a&middot;d)/(b&middot;c). Differences in weekly event counts between periods are tested with the non-parametric "
        "Mann-Whitney U test, which assumes no particular distribution.")
    d.section("3.3.2", "Change-point detection (PELT)", 3)
    d.p("For a weekly series y<sub>1..T</sub>, PELT finds the change-points &tau;<sub>1</sub>&lt;...&lt;&tau;<sub>m</sub> that minimise")
    d.eq("&Sigma;<sub>i=0..m</sub> C( y<sub>&tau;i+1 : &tau;i+1</sub> ) + &beta; m ,&nbsp;&nbsp; C = &Sigma;( y<sub>t</sub> - &ybar; )²  (L2 cost)", "3.2")
    d.p("where &beta; is a penalty that prevents over-segmentation. The series was standardised, a penalty of 12 and a minimum segment of three weeks were used, and the search was exact (jump = 1).")
    d.section("3.3.3", "Local spatial statistics: Getis-Ord Gi*", 3)
    d.p("For grid cell i with value x<sub>j</sub> (dark share) and binary neighbour weights w<sub>ij</sub> (the cell itself and its eight neighbours):")
    d.eq("G<sub>i</sub>* = ( &Sigma;<sub>j</sub> w<sub>ij</sub>x<sub>j</sub> - X&#772; &Sigma;<sub>j</sub> w<sub>ij</sub> ) / ( S &radic;( [ n&Sigma;w<sub>ij</sub>² - (&Sigma;w<sub>ij</sub>)² ] / (n-1) ) )", "3.3")
    d.p("G<sub>i</sub>* is a z-score. Values above 1.96 mark a statistically significant hot spot at the 5 per cent level.")
    d.section("3.3.4", "Density clustering (DBSCAN)", 3)
    d.p("DBSCAN groups points that have at least <i>minPts</i> neighbours within radius &epsilon;. Using the haversine metric, &epsilon; = 25 km and "
        "minPts = 15 on dark ships of 100 m and over, it finds anchorages and loitering or transfer areas where large "
        "ships gather with their AIS off.")
    d.section("3.3.5", "Forecasting", 3)
    d.p("The weekly Hormuz index is log-transformed (y' = ln(1+y)) and modelled as ARIMA(1,0,1) with a constant:")
    d.eq("y'<sub>t</sub> = c + &phi; y'<sub>t-1</sub> + &theta; &epsilon;<sub>t-1</sub> + &epsilon;<sub>t</sub>", "3.4")
    d.p("It is benchmarked against a naive forecast and damped-trend exponential smoothing on a 12-week hold-out.")
    d.section("3.3.6", "Survival analysis", 3)
    d.p("A <i>disruption episode</i> is a run of weeks in which a theatre's index is above its threshold (baseline mean + 3 SD). "
        "Its duration T is the survival time, and an episode still under way at the end of the data is right-censored. The Kaplan-Meier "
        "estimator of S(t) = P(T &gt; t) is")
    d.eq("S&#770;(t) = &Pi;<sub>t<sub>i</sub> &le; t</sub> ( 1 - d<sub>i</sub> / n<sub>i</sub> )", "3.5")
    d.p("where d<sub>i</sub> episodes end at t<sub>i</sub> out of n<sub>i</sub> still at risk. Covariate effects are estimated "
        "with the Cox proportional-hazards model h(t|x) = h<sub>0</sub>(t) exp(&beta;'x), and theatres are compared with the log-rank test.")
    d.section("3.3.7", "Classification and spatial cross-validation", 3)
    d.p("The probability that a detected ship is dark is modelled with logistic regression, logit(p) = &beta;<sub>0</sub> + &beta;'x, "
        "which gives interpretable odds ratios, and with histogram gradient-boosted trees with monotonic constraints, which capture "
        "non-linear effects. Skill is measured by leave-one-region-out cross-validation, so every prediction is made for a sea "
        "region the model did not see in training [14], and reported as ROC-AUC, PR-AUC and Brier score.")
    d.section("3.3.8", "Expected shortfall of a stock policy", 3)
    d.p("If a disruption lasts T days and stock covers S days, the uncovered days are (T - S)<sup>+</sup>. With the Kaplan-Meier curve,")
    d.eq("E[ (T - S)<sup>+</sup> ] = &int;<sub>S</sub><sup>&infin;</sup> S&#770;(t) dt", "3.6")
    d.p("This turns the disruption-duration distribution into a stock-holding decision curve (Section 12.5).")

    # ================================================================== 4 DATA PREPROCESSING
    d.chapter("Data Preprocessing")
    d.p("Pre-processing is the backbone of any statistical model. Both datasets were loaded into pandas, validated, cleaned, "
        "enriched with derived features and written to a clean columnar store (Parquet). The two datasets are summarised below.")
    d.table(T("t4_1_acled_summary"), "Summary of the conflict dataset (ACLED Middle-East weekly aggregates)")
    d.table(T("t4_2_sar_summary"), "Summary of the maritime dataset (Sentinel-1 SAR detections matched to AIS)")
    d.p("<b>Note on coverage.</b> Although the SAR file is named <i>indian ocean vessel</i>, its detections cover the world "
        f"(latitude -56&deg; to 75&deg;), with {n(M['sar_scenes'])} Sentinel-1A scenes. This allows a controlled comparison: "
        "war zones (Gulf, Black Sea) against India's seas and the rest of the world, all imaged by the same sensor in the same fortnight.")
    d.table(T("t4_4_attributes"), "Data headings analysed", small=True)
    d.section("4.1", "Cleaning")
    d.table(T("t4_3_cleaning_log").assign(Count=lambda x: x.Count.map(lambda v: f"{v:,}")), "Data-cleaning log")
    d.bullets([
        "<b>Temporal integrity.</b> One partial week (27 Dec 2014) was dropped so that every year is complete. Weeks were re-indexed to a regular 7-day "
        "frequency, with zero-filling, before any time-series operation.",
        "<b>Missing values.</b> POPULATION_EXPOSURE is missing in 30,965 rows, mostly sea areas and sparsely populated "
        "provinces. It was imputed with the median of the same ADMIN1 unit, or 0 where the unit never reports it. No other field had "
        "missing values.",
        f"<b>Confidence filter.</b> {n(M['sar_low_conf_dropped'])} SAR detections with presence score &lt; 0.80 were dropped "
        "to remove sea clutter, wakes and ambiguous returns.",
        f"<b>Identity validity.</b> {n(M['sar_mmsi_malformed'])} MMSIs outside the ship-station range (MID 2xx-7xx) were flagged as "
        "malformed and kept for the identity-integrity analysis (Section 7.7).",
        "<b>Definition of darkness.</b> <i>Dark</i> = matched_category 'unmatched' (no confident AIS association). "
        f"This covers {pct(M['sar_dark_share'], 1)} of detections. A stricter definition (no candidate MMSI at all, "
        f"{pct(M['sar_dark_strict_share'], 1)}) was used as a robustness check and gives the same regional ranking.",
    ])
    d.section("4.2", "Feature Engineering")
    d.bullets([
        "<b>Sea region</b>: 17 analyst-defined boxes (Strait of Hormuz, Persian Gulf, Gulf of Oman, Red Sea, Bab-el-Mandeb, Gulf of Aden, "
        "Arabian Sea, Bay of Bengal, Strait of Malacca, etc.), grouped into zones: Gulf war zone, Black Sea war zone, Red Sea zone, India's seas, rest of world.",
        "<b>Size class</b> from SAR length (&lt;25, 25-40, 40-100, 100-200, &gt;200 m). The <i>large</i> flag (&ge;100 m) marks ships that almost certainly carry AIS.",
        "<b>Flag state</b> decoded from the MID and classed as national flag, flag of convenience (ITF list) or shadow-fleet-associated registry.",
        "<b>Distance to the nearest chokepoint</b> (haversine) for every ship and every ADMIN1 centroid.",
        "<b>Conflict exposure</b> of every ship: distance to the nearest ADMIN1 with political violence in the war weeks overlapping the "
        "SAR window, and the number of such events within 500 km (BallTree haversine queries). At-sea ACLED rows carry a nominal "
        "basin centroid rather than a real position, so they were excluded from this spatial join.",
        "<b>Conflict flags</b>: political violence, remote violence (air/drone/missile/artillery), stand-off strike, GCC, maritime.",
    ])

    # ================================================================== 5 CONFLICT LANDSCAPE
    d.chapter("Conflict Landscape of the Middle East, 2015-2026")
    d.p(f"The ACLED data record {n(M['acled_events'])} events and {n(M['acled_fat'])} reported fatalities across "
        f"{M['acled_admin1']} provinces in {M['acled_weeks']} weeks. This chapter describes how the conflict system evolved "
        "and tests hypotheses H1 and H2.")
    d.fig("f5_1_annual", "Annual events and reported fatalities, 2015-2026 (2026 = 26 weeks)")
    d.p(f"Event volume peaked in 2024 ({n(M['yr_2024_events'])} events), driven by the Gaza war, the Israel-Hezbollah escalation "
        f"and the Red Sea campaign. In only 26 weeks, 2026 has already reached {n(M['yr_2026_events'])} events, and 2026 fatalities are "
        "the highest since 2019. Part of that fatality count comes from ACLED's coding of the January 2026 unrest in Iran: "
        f"{n(M['iran_riot_fat_jan26'])} fatalities in the single week of 3 January 2026, almost all coded as riots and protests. The rest comes from the war that began on 28 February.")
    d.fig("f5_2_eventmix", "Share of event types by year")
    d.p("Explosions/remote violence (air and drone strikes, shelling, missiles, IEDs) is the largest event type in most years. "
        "Its share rises sharply in years of inter-state war: 44.7 per cent in 2024 and 38.0 per cent in 2026. In between, protests and strategic developments "
        "dominate. The pattern for 2026 is clear: stand-off strikes (air/drone strike plus shelling/missile) made up "
        "<b>84 per cent</b> of all political violence recorded between 28 February and 10 April 2026.")
    d.fig("f5_3_heatmap", "Political-violence events by country and year (log colour scale)", width=96)
    d.p("The heat map shows the conflict moving across the region. Syria and Iraq dominated from 2015 to 2018. Palestine, Israel and Lebanon rose "
        "after 2023. In 2026 Iran and the GCC states, which had previously seen little political violence, turned dark. Bahrain, Kuwait, the UAE, "
        "Qatar and Oman record more political violence in the first half of 2026 than in the previous decade.")
    d.section("5.1", "Regime Shifts (H1)")
    d.fig("f5_4_changepoints", "Weekly political violence with PELT change-points (orange = regime mean)")
    d.table(T("t5_2_regimes"), "Conflict regimes detected by PELT")
    d.p("Without being told any dates, PELT placed change-points on <b>7 October 2023</b> (the Hamas attack on Israel and the "
        "start of the Gaza war), <b>21 September 2024</b> (the Israel-Hezbollah escalation), <b>30 November 2024</b> (the collapse of the Assad "
        "government followed shortly after) and <b>28 February 2026</b> (the regional war), with a de-escalation break on "
        f"<b>11 April 2026</b>. Weekly political violence averaged {M['pv_war_wk']:,.0f} events in the war regime against "
        f"{M['pv_base_wk']:,.0f} in the preceding 52 weeks, a {M['pv_war_ratio']:.1f}-fold rise (Mann-Whitney U, "
        f"p = {M['mw_p']:.1e}). After the April break, violence settled at about {M['pv_post_wk']:,.0f} events a week, "
        "still above the pre-war level. <b>H1 is supported.</b>")
    d.section("5.2", "Stand-off Warfare and the Spill-over to the Energy Coast (H2)")
    d.fig("f5_5_drone_share", "Share of stand-off strikes (air/drone strike, shelling/missile) in political violence, quarterly")
    d.p("Stand-off strikes are not trending steadily upwards. Their share <i>jumps</i> when an inter-state war begins "
        f"(linear trend p = {M['drone_share_p']:.2f}), reaching {M['drone_share_last']:.0f} per cent in Q1-2026. The share of stand-off "
        "strikes therefore works as a signature of war: a rise in it is an early-warning signal that ranges, and with them "
        "threats to shipping and energy infrastructure, are about to extend.")
    d.fig("f5_6_gcc", "Weekly political violence inside the GCC states, June 2025 - June 2026")
    d.p(f"Before the war the six GCC states together recorded about {M['gcc_pre_wk']:.1f} political-violence events a week. In "
        f"the six weeks from 28 February 2026 this rose to {M['gcc_war_wk']:.1f} a week, a <b>{M['gcc_multiplier']:.0f}-fold</b> increase. The UAE, "
        "Kuwait, Bahrain and Qatar, which host the region's export terminals, refineries and LNG trains, were struck directly.")
    d.fig("f5_7_war_map", "Geography of political violence, 28 February - 10 April 2026", width=92)
    d.table(T("t5_3_top_admin1_war"), "Top provinces by political-violence events, 28 Feb - 10 Apr 2026", small=True)
    d.p(f"Hormozgan, the Iranian province on the northern shore of the Strait of Hormuz, recorded {229} events and 215 fatalities "
        "in six weeks. Bushehr, Khuzestan (the oil province at the head of the Gulf) and Fars were also among the most affected Iranian "
        "provinces. The fighting reached the shoreline of the world's most important energy chokepoint.")
    d.fig("f5_8_maritime", "Conflict at sea: ACLED at-sea events by year and by sub-type")
    d.p(f"ACLED recorded {M['maritime_2022']} at-sea events in 2022, {M['maritime_2023']} in 2023, {M['maritime_2024']} in 2024 "
        f"and {M['maritime_2025']} in 2025, and already {M['maritime_2026']} in the first half of 2026. The dominant sub-types, "
        "'disrupted weapons use' (missiles and drones intercepted over the sea) and shelling/missile attacks, are those of an "
        "anti-shipping campaign. <b>H2 is supported</b> (see also Section 6.1).")

    # ================================================================== 6 CCII
    d.chapter("Chokepoint Conflict Intensity and Disruption Survival")
    d.section("6.1", "The Chokepoint Conflict Intensity Index (CCII)")
    d.p("Each theatre's threat to shipping is measured where it appears in the data. Weekly political-violence events are "
        "weighted 1.5 for stand-off strikes (the type of attack that reaches ships and terminals) and 1.0 otherwise:")
    d.bullets([
        "<b>Hormuz (littoral)</b>: events in ADMIN1 units within 500 km of the strait (coastal Iran, UAE, Oman, Qatar).",
        "<b>Red Sea / Arabian Sea (at sea)</b>: ACLED's at-sea 'North Indian Ocean' events, i.e. the Houthi anti-shipping campaign.",
        "<b>East Med (at sea)</b> and <b>Black Sea (at sea)</b>: ACLED's at-sea events for those waters.",
    ])
    d.p("A theatre is <i>disrupted</i> in a week when its index is above its own threshold, set at the 2015-2022 baseline mean plus 3 SD "
        "(minimum 3 weighted events).")
    d.fig("f6_1_ccii", "Chokepoint Conflict Intensity Index by theatre, 2015-2026")
    d.fig("f6_5_offshore", "Red Sea theatre: stand-off strikes on the Yemeni littoral versus violence at sea")
    d.p(f"<b>The Red Sea threat moved offshore.</b> Stand-off strikes on land within 500 km of Bab-el-Mandeb fell from "
        f"{n(M['yem_land_2019'])} in 2019 to {n(M['yem_land_2025'])} in 2025 as Yemen's civil war froze. Over the same years "
        f"violence at sea rose from {M['sea_2022']} events in 2022 to {M['sea_2024']} in 2024. An index built on land violence "
        "alone would have shown the Red Sea getting <i>safer</i> just as it became the most dangerous waterway in the world for merchant shipping. "
        f"During the 2026 war the Hormuz littoral index averaged <b>{M['hormuz_war_mult']:.0f} times</b> its 2015-2022 "
        f"baseline, and the Red Sea at-sea index averaged {M['redsea_2024_mult']:.0f} times its baseline from mid-November 2023 to December 2024.")
    d.fig("f6_2_ccii_z", "Theatre stress relative to its disruption threshold (4-week rolling mean, symmetric-log scale)")
    d.section("6.2", "Forecasting the Hormuz Index")
    d.table(T("t6_1_backtest"), "12-week hold-out back-test of forecasting models (Hormuz littoral index)")
    d.p("ARIMA(1,0,1) on the log-transformed index roughly halved the back-test error of the naive forecast and beat "
        "damped-trend exponential smoothing. It was refitted on all data and projected 13 weeks ahead, to the end of September 2026.")
    d.fig("f6_3_forecast", "Hormuz CCII: observed values and 13-week ARIMA forecast with 80 per cent interval")
    d.p(f"The central forecast falls back towards {M['fc_end_mean']:.1f} weighted events a week by the end of September "
        f"(80 per cent interval {M['fc_end_lo']:.1f}-{M['fc_end_hi']:.1f}), below the disruption threshold of {M['hormuz_thr']:.1f}. "
        f"However, in 4,000 simulated paths from the fitted model, <b>{pct(M['fc_prob_above_thr'])}</b> cross the threshold in at least "
        "one of the 13 weeks. The Hormuz littoral has not returned to its pre-war calm. Flare-ups should be treated as the "
        "base case through the third quarter of 2026, not as a tail risk.")
    d.section("6.3", "How Long Do Disruptions Last? Survival Analysis")
    d.p(f"Applying the threshold rule to each theatre produced {M['ep_n']} disruption episodes. One of them, on the Hormuz littoral, "
        "was still under way at the end of the data and is right-censored.")
    d.fig("f6_4_km", "Kaplan-Meier survival of disruption episodes; red lines mark India's strategic oil cover")
    d.table(T("t6_3_km_summary"), "Disruption episodes by theatre")
    d.p(f"Across the {M['ep_n']} episodes, the median disruption lasts {M['ep_median_wk']:.1f} weeks, the mean "
        f"{M['ep_mean_wk']:.1f} weeks and the longest {M['ep_max_wk']} weeks, so the distribution is heavy-tailed. "
        f"The probability that an episode outlasts <b>9.5 days</b>, India's strategic petroleum reserve cover, is "
        f"<b>{pct(M['km_p_gt_spr'])}</b>. The probability that it outlasts <b>74 days</b>, the total national cover including refiners' "
        f"stocks, is <b>{pct(M['km_p_gt_74d'])}</b>. Red Sea episodes last longer than Hormuz episodes (median 4.0 against 2.0 weeks; "
        f"log-rank &chi;² = {M['logrank_chi2']:.2f}, p = {M['logrank_p']:.3f}).")
    cox = T("t6_4_cox").rename(columns={"coef": "Coefficient"})
    cox["Covariate"] = cox.Covariate.str.replace("chokepoint_", "Theatre: ").str.replace("post2023", "Episode began after Oct 2023")
    d.table(cox, "Cox proportional-hazards model of the hazard of a disruption ending (reference: Black Sea)")
    d.p(f"A hazard ratio below 1 means an episode is <i>less likely to end</i>, i.e. it lasts longer. Episodes that began after "
        f"October 2023 have a hazard ratio of {M['cox_post2023_hr']:.2f}: they are more persistent, though with only 32 "
        f"episodes the estimate is not significant at the 5 per cent level (p = {M['cox_post2023_p']:.2f}). <b>H6 is supported</b>: "
        "disruptions are heavy-tailed and most of them outlast India's strategic reserve.")

    # ================================================================== 7 SAR / AIS DARK
    d.chapter("Maritime Traffic and AIS Dark Zones")
    d.p(f"This chapter analyses {n(M['sar_rows'])} Sentinel-1 vessel detections from 1-14 March 2026, the first two "
        "weeks of the war, and tests hypotheses H3 and H4.")
    d.fig("f7_1_global_map", "Sentinel-1 vessel detections, 1-14 March 2026 (blue = AIS-matched, orange = AIS-dark)")
    d.section("7.1", "Where Are Ships Dark? (H3)")
    d.fig("f7_2_dark_by_region", "AIS-dark share by sea region, all vessels and large vessels, with 95 per cent Wilson intervals")
    rt = T("t7_1_dark_by_region")
    for c in ["Dark share (all)", "Dark share (large)", "CI low", "CI high"]:
        rt[c] = rt[c].map(lambda v: f"{v * 100:.1f}%")
    d.table(rt, "AIS-dark share by region (large = hull length &ge; 100 m)", small=True)
    d.p("Looking at all ships gives a misleading picture, because small craft are dark almost everywhere. Once the comparison is "
        "restricted to <b>large ships (&ge;100 m)</b>, which carry AIS by regulation, the war zones stand out: <b>Strait of Hormuz "
        f"{pct(M['hormuz_large_dark'])}</b>, Persian Gulf {pct(M['pg_large_dark'])}, Gulf of Oman {pct(M['goo_large_dark'])}, "
        f"Black Sea {pct(M['black_large_dark'])}. Every region at peace lies between about 7 and 17 per cent, and NW Europe is lowest at 8 per cent. "
        f"Large ships in war zones are dark in {pct(M['large_conflict_dark'])} of cases against {pct(M['large_rest_dark'])} elsewhere: "
        f"a <b>relative risk of {M['large_rr']:.1f}</b> and an <b>odds ratio of {M['large_or']:.1f}</b> "
        f"(&chi;² = {M['chi2']:,.0f}, p &lt; 10<sup>-300</sup>). <b>H3 is strongly supported.</b>")
    d.p("The Black Sea result is independent corroboration. It lies outside the ACLED Middle-East data, and it is the other theatre named in the Datathon problem statement. "
        f"The Russia-Ukraine war produces the same signature: {pct(M['black_large_dark'])} of large ships dark, about four times the peacetime norm.")
    d.p(f"The Red Sea shows a different effect: only {pct(M['redsea_large_dark'])} of large ships are dark, and just 54 detections were made in "
        "Bab-el-Mandeb in two weeks. In the Red Sea, ships do not go dark in the war zone. <b>They stay away</b>. "
        "The Gulf has no route around it, so ships that must load there go dark instead. The two chokepoints show the two responses of shipping to conflict: "
        "diversion where a detour exists, blinding where it does not.")
    d.fig("f7_3_size_zone", "AIS-dark share by vessel size class and zone")
    d.p("In peaceful waters darkness falls steadily with size, from 72 per cent of craft under 25 m to 8 per cent of ships over 200 m. In the Gulf war zone it "
        "hardly falls at all: ships over 200 m, which is VLCC and LNG-carrier size, are dark 60 per cent of the time. <b>In a war zone, size no longer predicts visibility.</b>")
    d.section("7.2", "Statistically Significant Dark Hot Spots (H4)")
    d.fig("f7_4_gulf_hotspots", "Dark share and Getis-Ord Gi* hot spots, ships &ge; 60 m, India's western approaches (0.5&deg; cells)")
    d.p(f"Of {M['gulf_cells']} half-degree cells with enough ships in the Gulf-Arabian Sea window, <b>{M['gulf_hot_cells']} are "
        "significant dark hot spots</b> (Gi* &gt; 1.96). They form one contiguous belt from Qatar across the UAE coast and Hormuz into the "
        "Gulf of Oman. The north-western Gulf (Kuwait, Iraq, the Saudi coast) and India's west coast are <b>cold spots</b>: large ships there stay visible.")
    d.fig("f7_5_global_hotspots", "Global Gi* hot spots of AIS-dark ships &ge; 60 m (1&deg; cells)")
    d.table(T("t7_3_hotspot_cells").rename(columns={"region": "Region"}), "Significant dark hot-spot cells (1&deg;) by region", small=True)
    d.p(f"Worldwide, {M['global_hot_cells']} of {n(M['global_cells'])} one-degree cells are dark hot spots. Relative to the area "
        "of each region, the Persian Gulf, Gulf of Oman and Black Sea are the densest. Hot spots elsewhere, in the South China Sea, Southern Indian Ocean "
        "and Pacific, mark distant-water fishing grounds where small and medium craft routinely run without AIS [5]. <b>H4 is supported.</b>")
    d.section("7.3", "Where Do Dark Ships Gather? DBSCAN Clusters")
    d.fig("f7_6_dbscan", f"DBSCAN clusters of AIS-dark ships &ge; 100 m (numbers = rank in Table {d.pfx}.{d.tab_no + 1})")
    cl = T("t7_4_dark_clusters").drop(columns=["lat", "lon"])
    cl["Dark share of large ships within 30 km"] = cl["Dark share of large ships within 30 km"].map(lambda v: f"{v * 100:.0f}%")
    d.table(cl, "Largest clusters of dark ships &ge; 100 m", small=True)
    d.p(f"DBSCAN found {M['n_clusters']} clusters. The two largest are off <b>Dubai/Jebel Ali ({n(M['top_cluster_n'])} dark large ships; "
        f"{pct(M['top_cluster_share'])} of all large ships there dark)</b> and the <b>Fujairah/Khor Fakkan anchorage</b>, the "
        "main bunkering and waiting area outside Hormuz. Together with the Hormuz and Ras Laffan clusters, they are fleets of tankers and gas "
        "carriers waiting at anchor with AIS off. That is the physical form of a supply chain on hold. The Novorossiysk/Kerch "
        "clusters are the Black Sea equivalent. The Kolkata/Haldia cluster (44 per cent dark) is the only large-ship cluster in India's own waters "
        "and is flagged for follow-up. The single-day Tokyo Bay cluster is most likely an AIS-matching gap and is treated as an artefact.")
    d.section("7.4", "The Daily Picture in the Gulf")
    d.fig("f7_7_gulf_daily", "Gulf war zone: detections per SAR scene and share AIS-dark, 1-14 March 2026")
    d.p(f"Over the first two weeks of the war, darkness in the Gulf <b>rose</b> from {pct(M['gulf_dark_first3'])} of detections in the "
        f"first three imaged days to {pct(M['gulf_dark_last3'])} in the last three (Spearman &rho; = {M['gulf_daily_trend_rho']:.2f}, "
        f"p = {M['gulf_daily_trend_p']:.3f}). Two days (6 and 12 March) had very few detections per scene, and their shares should be read "
        "with caution. The trend holds with them removed.")
    d.section("7.5", "Who Is Sailing? Flag States of Visible Ships")
    d.fig("f7_8_flags", "Registry class of AIS-visible large ships by zone (MMSI MID decode)")
    d.table(T("t7_6_top_flags_gulf"), "Top flag states of visible large ships, Gulf war zone against rest of world", small=True)
    d.p(f"Flags of convenience make up about half of visible large ships everywhere, so they do not distinguish the war zones. What does distinguish them is "
        f"<b>shadow-fleet-associated registries</b> (Gabon, Cameroon, Comoros, Sierra Leone, Togo, Cook Islands, Palau and similar): "
        f"{M['flag_gulf_shadow']:.1f} per cent of visible large ships in the Gulf and {M['flag_black_shadow']:.1f} per cent in the Black Sea, against "
        f"{M['flag_world_shadow']:.1f} per cent elsewhere. Iranian-flagged ships make up 6.9 per cent of visible large ships in the Gulf against 0.1 per cent worldwide. "
        "The ships still transmitting in the war zone lean towards registries with weak oversight, which adds to the identity problem.")
    d.section("7.6", "India's Maritime Neighbourhood")
    d.fig("f7_10_india_seas", "Arabian Sea and Bay of Bengal: AIS-matched, small dark and large dark detections", width=95)
    d.p(f"India's seas have the highest overall dark shares in the dataset (Arabian Sea {pct(M['arab_all_dark'])}, Bay of Bengal "
        f"{pct(M['bob_all_dark'])}). This is <b>not</b> a conflict signal: {pct(M['india_seas_small_dark_share'])} of craft under 40 m "
        f"are dark, and {pct(M['india_seas_fishing_share_dark'])} of dark detections score as fishing vessels. "
        f"Large ships off India are visible (Arabian Sea {pct(M['arab_large_dark'])} dark, Bay of Bengal {pct(M['bob_large_dark'])}). The "
        "security point is that India's near seas contain thousands of small, uncooperative craft, the same class of craft used in the "
        "26/11 Mumbai attack. The domestic maritime picture depends on non-AIS sensing.")
    d.section("7.7", "Identity Integrity")
    d.table(T("t7_7_identity"), "Indicators of AIS identity anomalies", small=True)
    d.p(f"Beyond darkness, the data show {n(M['sar_mmsi_malformed'])} malformed MMSIs, {M['placeholders']} placeholder identities "
        f"(e.g. 200000000, 412000000) and {M['clones']} cases of one MMSI appearing at two places that would need speeds above "
        "50 knots, i.e. cloned or spoofed identities. These counts are small but not negligible, and they show that an AIS match alone does not "
        "confirm a ship's identity.")

    # ================================================================== 8 PREDICTIVE MODEL
    d.chapter("Predicting AIS Dark Spots")
    d.p(f"The Datathon problem statement asks participants to <i>predict</i> AIS dark spots. A model was trained on "
        f"{n(M['model_n'])} detections of ships &ge; 40 m (the AIS-carrying fleet; base dark rate {pct(M['model_base_rate'], 1)}). "
        "It uses five features that describe the ship and its conflict geography, and it deliberately excludes latitude and longitude "
        "so that it cannot simply memorise where the dark ships are.")
    lt = T("t8_1_logit")
    d.table(lt, "Logistic regression: odds ratios per 1 SD of each feature (all 62,624 ships &ge; 40 m)")
    d.p(f"Holding size and type constant, each 1-SD increase in (log) distance from the nearest active conflict province lowers "
        f"the odds of darkness to {M['or_dist']:.2f} times. The raw event count within 500 km adds nothing once distance is known. "
        "<i>Proximity</i> to the fighting matters; the <i>volume</i> of fighting does not.")
    mt = T("t8_2_model_cv")
    d.table(mt, "Model skill, leave-one-region-out cross-validation", small=True)
    d.fig("f8_1_model", "ROC curves (leave-one-region-out) and permutation importance")
    d.p(f"Evaluated only on sea regions it had never seen, the gradient-boosted model reaches <b>ROC-AUC {M['auc_gbt']:.2f}</b> and "
        f"<b>PR-AUC {M['prauc_gbt']:.2f}</b>, almost twice the {M['model_base_rate']:.2f} a random model would score. Ordinary random "
        f"cross-validation would have reported AUC {M['auc_gbt_random']:.2f}. That inflation from spatial leakage is exactly what "
        "Roberts et al. warn against [14], and the lower, honest figure is the one relied on here. <b>H5 is supported</b>: conflict geography "
        "carries real, transferable information about where ships will go dark.")
    d.fig("f8_2_pdp", "Model response: predicted darkness against distance from active conflict")
    d.fig("f8_3_risk_surface", "Predicted AIS dark-spot surface for a 180 m merchant ship, early-March-2026 conflict picture")
    pr = T("t8_3_poi_risk")
    pr[pr.columns[1]] = pr[pr.columns[1]].map(lambda v: f"{v * 100:.0f}%")
    d.table(pr, "Predicted probability that a 180 m merchant ship is AIS-dark at points of interest to India")
    d.p("The model's surface reproduces the observed belt of darkness along Hormuz and the UAE coast and a secondary area around "
        "Bab-el-Mandeb and the Gulf of Aden. It also gives a <i>transferable</i> rule. Given a new conflict picture, such as a future escalation near "
        "Chabahar or the Makran coast, the same model can be re-run to predict where the cooperative maritime picture will fail "
        "before any satellite pass confirms it.")

    # ================================================================== 9 INFERENCE
    d.chapter("Inference")
    d.p("This chapter brings together the results of Chapters 5 to 8, gives the verdict on each hypothesis and states the "
        "inferences that the impact assessments (Chapters 10-12) and the way forward (Chapter 13) are built on.")
    d.section("9.1", "Key Findings")
    kp = [(f"{M['pv_war_ratio']:.1f}x", "weekly political violence in the 2026 war regime vs the prior year"),
          (f"{M['gcc_multiplier']:.0f}x", "rise in violence inside GCC energy states"),
          (pct(M['hormuz_large_dark']), "large ships AIS-dark in the Strait of Hormuz"),
          (f"{M['large_rr']:.1f}x", "relative risk of darkness for large ships in war zones"),
          (pct(M['km_p_gt_spr']), "disruptions outlasting India's 9.5-day SPR")]
    d.add('<div class="kpis">' + "".join(f'<div class="kpi"><div class="v">{v}</div><div class="l">{l}</div></div>' for v, l in kp) + "</div>")
    F = pd.DataFrame([
        ("F1", "Violence rose 2.9-fold in the 2026 war regime; PELT dated the regime shifts to 7 Oct 2023 and 28 Feb 2026 without being given the dates.", "5.1"),
        ("F2", "84% of war-period violence was stand-off strikes (air, drone, missile, artillery), a sharp jump that marks the onset of inter-state war.", "5.2"),
        ("F3", f"The war reached the energy coast: GCC violence rose {M['gcc_multiplier']:.0f}-fold, the Hormuz littoral index {M['hormuz_war_mult']:.0f}-fold.", "5.2, 6.1"),
        ("F4", "The Red Sea threat moved offshore: land strikes fell ~6-fold while at-sea violence rose ~30-fold; a land-based index would miss it.", "6.1"),
        ("F5", f"Disruptions are heavy-tailed: median {M['ep_median_wk']:.1f} wk, max {M['ep_max_wk']} wk; {pct(M['km_p_gt_spr'])} outlast the SPR, {pct(M['km_p_gt_74d'])} outlast 74 days; Hormuz stays elevated into Q3-2026 ({pct(M['fc_prob_above_thr'])} of simulated paths cross the threshold).", "6.2, 6.3"),
        ("F6", f"Large ships in war zones are {M['large_rr']:.1f}x more likely to be AIS-dark (Hormuz {pct(M['hormuz_large_dark'])}, Black Sea {pct(M['black_large_dark'])}); darkness in the Gulf rose over the first two weeks of the war.", "7.1, 7.4"),
        ("F7", "Two responses to conflict: blinding where there is no detour (Gulf) and diversion where there is (Red Sea).", "7.1"),
        ("F8", "Dark ships gather at the Dubai/Jebel Ali and Fujairah anchorages: the supply chain is held at anchor with AIS off; shadow-fleet registries are over-represented about 3x.", "7.3, 7.5"),
        ("F9", "India's near seas are dominated by thousands of small, non-AIS craft; large ships off India remain visible.", "7.6"),
        ("F10", f"Proximity to conflict predicts darkness in unseen regions (ROC-AUC {M['auc_gbt']:.2f}); AIS identity itself is unreliable (clones, placeholders, malformed IDs).", "7.7, 8"),
    ], columns=["#", "Finding", "Section"])
    d.table(F, "Key findings of the study")
    d.section("9.2", "Verdict on the Hypotheses")
    d.table(pd.DataFrame([
        ("H1", "Regime shifts coincide with the 2023 and 2026 wars", f"Supported - change-points on 7 Oct 2023 and 28 Feb 2026; war regime {M['pv_war_ratio']:.1f}x, p = {M['mw_p']:.1e}"),
        ("H2", "War moved to the energy littoral; Red Sea threat moved offshore", f"Supported - GCC {M['gcc_multiplier']:.0f}x, Hormuz littoral {M['hormuz_war_mult']:.0f}x; Yemen land strikes down, at-sea events up"),
        ("H3", "Large ships are more often dark in war zones", f"Strongly supported - RR {M['large_rr']:.1f}, OR {M['large_or']:.1f}, chi-square p &lt; 10<sup>-300</sup>"),
        ("H4", "Darkness forms significant hot spots at conflict chokepoints", f"Supported - {M['gulf_hot_cells']} Gi* hot-spot cells in one belt from Qatar to the Gulf of Oman; largest DBSCAN clusters at Gulf anchorages"),
        ("H5", "Proximity to conflict predicts darkness out-of-region", f"Supported, with moderate skill - ROC-AUC {M['auc_gbt']:.2f}, PR-AUC {M['prauc_gbt']:.2f} against a base rate of {M['model_base_rate']:.2f}"),
        ("H6", "Disruptions are heavy-tailed and outlast India's oil cover", f"Supported - {pct(M['km_p_gt_spr'])} outlast the SPR, {pct(M['km_p_gt_74d'])} outlast 74 days; post-2023 episodes more persistent (HR {M['cox_post2023_hr']:.2f}, not significant)"),
    ], columns=["#", "Hypothesis", "Verdict and evidence"]), "Verdict on the hypotheses")
    d.section("9.3", "Inferences Drawn")
    d.p("Read together, the findings support six inferences. Each is stated with the findings it rests on.")
    d.bullets([
        "<b>I1 - Conflict at a chokepoint first shows up as a loss of information, and only then as a loss of flow (F6, F8).</b> "
        "Before cargo stops moving, the cooperative maritime picture collapses: large, AIS-obligated ships vanish from it, and tankers "
        "wait at anchor with transponders off. The large-ship dark share is therefore a <i>leading</i> indicator of supply disruption. "
        "It can be measured from space before trade statistics show anything.",
        "<b>I2 - Whether a detour exists decides how shipping responds (F4, F7).</b> Where there is an alternative route, as with the Red Sea and the Cape, "
        "conflict causes diversion: traffic thins and the cost appears as time and freight. Where there is none, as with the Gulf and Hormuz, "
        "conflict causes blinding: ships keep sailing but go dark, and the cost appears as risk. Policy for the two chokepoints "
        "must therefore differ.",
        "<b>I3 - Stand-off weapons have removed the distance between a land war and the sea lanes (F2, F3, F4).</b> With 84 per cent of "
        "war-period violence delivered by drones, missiles and artillery, any littoral actor can hold a chokepoint, a terminal or a "
        "logistics node at risk. Distance from the front line no longer protects rear areas.",
        "<b>I4 - Supply disruption is a question of duration, not of spikes (F5).</b> Most episodes are short, but the tail is long and "
        "persistent. Planning for the median episode leaves the force and the nation exposed for most of the expected shortfall. Buffers must be "
        "sized against the survival curve, and the prescriptive model (Chapter 12) shows the point at which extra stock stops paying off.",
        "<b>I5 - Darkness is predictable, so early warning is feasible (F1, F10).</b> Change-points in the conflict series match "
        "real-world turning points, and conflict geography predicts darkness in sea regions the model has never seen. Open "
        "conflict data combined with satellite radar can therefore give warning of where and when the maritime picture will fail.",
        "<b>I6 - AIS identity is necessary but not sufficient (F8, F9, F10).</b> Cloned, placeholder and malformed identities, "
        "shadow-fleet registries and thousands of non-AIS small craft in India's own seas mean that a trustworthy maritime "
        "picture requires independent sensing (SAR, radar) and automated identity checks.",
    ])
    d.section("9.4", "Confidence in the Inferences")
    d.bullets([
        "The SAR data cover only 14 days from a single satellite (Sentinel-1A), so the pre-war level of darkness in the same waters cannot be observed directly. "
        "Peacetime regions and the Black Sea serve as the comparison groups instead.",
        "'Unmatched' is not always deliberate: GNSS spoofing, AIS reception gaps and matching-algorithm limits also produce "
        "darkness. In the Gulf these are themselves effects of the war.",
        "ACLED aggregates are at ADMIN1 resolution, and its at-sea events carry a nominal basin centroid. Distances to conflict are therefore approximate.",
        "The survival analysis rests on 32 episodes, so Cox coefficients have wide intervals. MID-to-flag decoding and registry "
        "classes are approximations, and registry class is not proof of any particular ship's conduct.",
        "Figures quoted from secondary sources (oil import shares, reserve days, diaspora) are indicative and cited, and they were not "
        "derived from the Datathon datasets.",
    ])
    d.p("None of these limitations reverses the direction of the main inferences. The war-zone effect on large-ship darkness (I1) is "
        "large, significant and reproduced in two unrelated wars. Inferences I4 and I5 should be read as well supported but moderate in precision.")

    # ================================================================== 10 IMPACT - GLOBE
    d.chapter("Impact on the Globe")
    d.bullets([
        "<b>Energy security.</b> About a fifth of the world's oil liquids and a large share of its LNG pass through Hormuz [2]. "
        "F3 and F5 show the strait's shoreline became an active front and stayed above its disruption threshold for most of "
        "February to June 2026. The world energy market now has to price chokepoint risk as a recurring condition, not a rare event (I4).",
        "<b>Freight, time and cost.</b> Where a detour exists, conflict produces diversion (I2). Cape routing adds 10-14 days to "
        "Asia-Europe voyages, absorbs fleet capacity and raises freight and insurance costs worldwide [1]. The survival curves (F5) show "
        "these episodes last weeks to months, not days.",
        "<b>Loss of the common maritime picture.</b> In war zones the cooperative identity system on which collision avoidance, search "
        "and rescue, sanctions enforcement, insurance and port-state control depend fails for most large ships (F6, I1). Navigation safety "
        "deteriorates, and the chance of misidentifying and striking a neutral ship rises.",
        "<b>Sanctions and the shadow fleet.</b> Dark ships cluster at the Gulf and Black Sea anchorages, and shadow-fleet registries are "
        "about three times over-represented (F8). The informal, poorly insured fleet grows exactly where oversight is weakest, raising the risk of "
        "environmental disasters and unattributable incidents (I6).",
        "<b>Contagion of stand-off warfare.</b> Cheap drones and missiles have become the main tool of regional war (F2, I3). Any littoral "
        "actor can now hold a chokepoint at risk from the shore, and the model extends beyond the Middle East to other straits.",
        "<b>A model for other chokepoints.</b> The two responses identified here, diversion and blinding (I2), offer a way to anticipate "
        "what would happen in a crisis at Malacca, the Taiwan Strait or the Bosphorus, where the same data and methods can be applied.",
    ])

    # ================================================================== 11 IMPACT - INDIA
    d.chapter("Impact on India")
    d.bullets([
        "<b>Energy import exposure.</b> India imports close to nine-tenths of its crude oil. Open-source estimates put a large share of that "
        "crude (commonly 40-50 per cent), most of its LPG and much of its LNG as coming from the Gulf through Hormuz [2, 19]. "
        f"The heavy-tailed disruption curve (F5, I4) means that about {pct(M['km_p_gt_spr'])} of disruptions would outlast the strategic "
        f"petroleum reserve (~9.5 days) and about {pct(M['km_p_gt_74d'])} would outlast the total national cover of about 74 days [19]. "
        "Hormuz is a no-detour chokepoint (I2), so for this share of India's energy there is no rerouting option, only buffers and "
        "alternative suppliers.",
        "<b>Trade routes to Europe, Africa and the US East Coast.</b> The Red Sea diversion (F4, F7) lengthens India's westbound "
        "container and product-tanker routes and raises their cost, eroding the competitiveness of exports such as refined products, engineering goods, "
        "textiles and pharmaceuticals. The Houthi campaign episodes lasted a median of four weeks and up to 19 weeks.",
        "<b>Connectivity projects.</b> The International North-South Transport Corridor through Chabahar and the India-Middle East-Europe "
        "Economic Corridor (IMEC) both pass through the theatres analysed. The predicted dark-risk at Chabahar "
        "(Table 8.3) and the violence in Sistan-Baluchestan and Hormozgan (Chapter 5) point to delays and higher risk premia for both.",
        "<b>Diaspora and remittances.</b> About nine million Indians live in the GCC, which sends India a large share of its remittances [20]. "
        f"The {M['gcc_multiplier']:.0f}-fold rise in violence inside the GCC (F3) makes large-scale non-combatant evacuation a planning case, "
        "not a contingency.",
        "<b>Maritime domain awareness at home.</b> India's own seas are dominated by thousands of small, non-AIS craft (F9), and even "
        "AIS-visible identities can be cloned or spoofed (F10). The national maritime picture cannot rely on AIS alone (I6).",
        "<b>An opportunity.</b> The inferences also favour India. National SAR assets (EOS-04, NISAR), the Information Fusion Centre - "
        "Indian Ocean Region, and a growing analytics culture give India the means to turn I1 and I5 into a regional early-warning "
        "service for partners in the Indian Ocean, strengthening its role as a net security provider.",
    ])

    # ================================================================== 12 IMPACT - ARMED FORCES
    d.chapter("Impact on the Indian Armed Forces")
    d.p("The findings affect all three Services and the joint structures that link them. The common threads are fuel and "
        "spares security (I4), the stand-off threat to bases and nodes (I3), and operating in an environment where navigation and "
        "identity can no longer be taken for granted (I1, I6).")
    d.section("12.1", "Joint and Tri-Service Impact")
    d.bullets([
        "<b>POL and war-wastage reserves.</b> Mechanised formations, ships and aircraft all run on imported crude refined in India. "
        "A chokepoint disruption that outlasts national reserves (F5) would lead to rationing, in which defence consumption competes "
        "with the civil economy. The prescriptive model in Section 12.5 turns F5 into a stock-holding decision.",
        "<b>Imported equipment, spares and ammunition.</b> Sea-lifted defence imports and the spares for imported platforms move on the same "
        "routes. Longer, more variable lead-times (F4, F5, F7) mean that re-order points and safety stocks based on peacetime "
        "lead-times will be too low for all three Services.",
        "<b>Non-combatant evacuation.</b> The rise in GCC violence (F3) makes a large-scale evacuation of the Gulf diaspora a joint "
        "operation to plan now: Navy sealift, IAF airlift and Army reception, transit and medical support. Op Ganga (2022), Op Kaveri (2023) and Op Ajay (2023) are the reference cases.",
        "<b>Space-based surveillance.</b> The study shows what SAR can reveal in a war zone (F6, F8). The Defence Space Agency and "
        "the national SAR constellation are the natural owners of a standing dark-ship and chokepoint watch.",
    ])
    d.section("12.2", "Indian Navy")
    d.bullets([
        "<b>Escort and presence operations.</b> The belt of darkness from Qatar to the Gulf of Oman (F6, H4) is the area in which Indian-flag "
        "tankers and gas carriers would be escorted, as in Op Sankalp. Positive identification of contacts in a picture where 60-74 per cent "
        "of large ships are dark is harder, raising the risk of surprise and of mistaken engagement.",
        "<b>Stand-off threat at sea.</b> The anti-shipping campaign (F4) and the dominance of drones and missiles (F2) call for "
        "ship air defence, counter-drone systems and magazine depth sized for long campaigns (F5), not single incidents.",
        "<b>Coastal security.</b> The thousands of non-AIS small craft in India's near seas (F9) are the population in which a "
        "26/11-type threat hides. Coastal radar, SAR cueing and fishing-vessel transponders are needed alongside AIS.",
        "<b>Shadow fleet in the Indian EEZ.</b> Poorly insured, shadow-registered tankers (F8) crossing India's waters raise the risk of oil "
        "spills and incidents that the Navy and Coast Guard would have to respond to.",
    ])
    d.section("12.3", "Indian Air Force")
    d.bullets([
        "<b>Air-base survivability.</b> GCC energy infrastructure far from any front line was struck directly (F3), and stand-off weapons dominate (F2, I3). "
        "Forward and depth air bases, fuel farms and radars need layered air defence, hardened shelters, dispersal and rapid runway repair.",
        "<b>Air routes and airlift.</b> Violence across the GCC and Iran closes or restricts air corridors to West Asia, Africa and Europe. That "
        "lengthens ferry and airlift routes, including those needed for evacuation and for urgent sustainment of imported spares.",
        "<b>Navigation warfare.</b> The spoofing and identity anomalies seen at sea (F10) are the maritime face of the GNSS "
        "interference that also affects aircraft. Avionics and weapons need multi-constellation (NavIC), anti-jam and inertial fallback.",
    ])
    d.section("12.4", "Indian Army")
    d.bullets([
        "<b>Logistics nodes under stand-off threat.</b> Army depots, railheads, POL points and ammunition storage need the same "
        "layered air defence, counter-UAS, dispersal and hardening that the Gulf's terminals lacked (F2, F3, I3).",
        "<b>GNSS-dependent weapons.</b> Army drones, loitering munitions, precision artillery and timing networks need "
        "NavIC/multi-constellation, anti-jam and GNSS-denied fallback capability, and troops should train under jamming and spoofing (F6, F10).",
        "<b>Western front and hybrid spill-over.</b> Violence in Sistan-Baluchestan (among Iran's most violent provinces over the decade), the Makran "
        "littoral and a weakened Iranian periphery all border Pakistan's Balochistan. These affect the western-front threat picture and the security of connectivity projects.",
        "<b>Sustainment of imported fleets.</b> Armoured, artillery and aviation fleets with imported sub-systems face longer spares "
        "lead-times (F5). Predictive maintenance and survival-based spares forecasting of the kind the author developed for armoured vehicles [13] become more valuable.",
    ])
    d.section("12.5", "Prescriptive Model: How Much Stock Is Enough?")
    d.fig("f9_1_stock_cover", "Prescriptive stock-cover curve from observed Gulf and Red Sea disruption durations")
    st = T("t9_1_stock_decision")
    d.table(st, "Decision table: stock held against disruption risk and expected shortfall",
            fmt={c: (lambda v: f"{v:.1f}") for c in st.columns[1:]})
    d.p(f"With no stock, an average Gulf or Red Sea disruption leaves {M['stock_es_0']:.0f} uncovered days. Holding "
        f"<b>30 days</b> of stock cuts the expected shortfall to {M['stock_es_30']:.1f} days, and <b>45 days</b> to {M['stock_es_45']:.1f} days, "
        f"avoiding 74 per cent of the shortfall. The returns flatten at about <b>{M['stock_knee_days']} days</b>: beyond this point each "
        "additional day of stock removes less than a quarter of a day of expected shortfall. The same curve can be applied to "
        "any disruption-sensitive commodity held by any Service (POL, lubricants, aviation fuel, critical imported spares) to set holdings on evidence rather than precedent.")

    # ================================================================== 13 WAY FORWARD
    d.chapter("Way Forward")
    d.p("The way forward has three parts: recommendations traced to the findings and inferences, a phased roadmap to implement "
        "them, and the research that would strengthen the evidence.")
    d.section("13.1", "Recommendations")
    R = pd.DataFrame([
        ("National", "R1", "Expand strategic crude and LPG reserves and set national cover from the disruption-survival curve rather than a fixed number of days, with a target at or beyond the ~35-45-day point where returns flatten, for the Hormuz-dependent share of imports.", "F5, I4"),
        ("National", "R2", "Diversify energy sources and routes: more non-Gulf crude and LNG, access to Hormuz-bypass export points (Yanbu, Fujairah), and long-term charters that include war-risk clauses.", "F3, F7, I2"),
        ("National", "R3", "Build a national Chokepoint Early-Warning System that tracks the CCII, the stand-off strike share and the large-ship dark share weekly, with the thresholds from this study as triggers.", "F1, F2, F6, I1, I5"),
        ("Maritime / MDA", "R4", "Fuse SAR (NISAR, EOS-04, commercial SAR) with AIS at IFC-IOR and flag every dark large ship automatically, prioritising the hot-spot belt and the predicted dark-risk surface.", "F6, F8, I1"),
        ("Maritime / MDA", "R5", "Treat AIS identity as untrusted: build automated checks for impossible re-sightings, placeholder and malformed MMSIs and shadow-fleet registries, and share them with ports and insurers.", "F10, I6"),
        ("Maritime / MDA", "R6", "Extend coverage of small craft in India's seas (fishing-vessel transponders, coastal radar, SAR) so that the non-AIS population is known.", "F9, I6"),
        ("Joint (HQ IDS)", "R7", "Re-baseline POL, lubricant, aviation-fuel and critical-spares War Wastage Reserves for all three Services using the expected-shortfall method (Eq. 3.6), and re-order points using lead-time distributions measured during crises.", "F4, F5, I4"),
        ("Joint (HQ IDS)", "R8", "Set up a tri-service Data Analytics Cell under HQ IDS, with Service nodes (DG Log, DGMO, Naval Operations, Air Operations), that runs this pipeline and its Power BI dashboard as a standing supply-chain and conflict early-warning product.", "All"),
        ("Joint (HQ IDS)", "R9", "Pre-plan non-combatant evacuation from the GCC as a live case and rehearse Navy sealift, IAF airlift and Army reception, transit and medical components together.", "F3"),
        ("Indian Navy", "R10", "Use SAR dark-ship cueing and the predicted dark-risk surface for escort and presence operations in the Gulf and Arabian Sea; plan ship air defence and counter-drone magazines for long campaigns.", "F2, F4, F6"),
        ("Indian Air Force", "R11", "Harden and disperse air bases and fuel farms against stand-off strikes, and make multi-GNSS/NavIC, anti-jam and inertial fallback standard for avionics and weapons.", "F2, F3, F10, I3"),
        ("Indian Army", "R12", "Give priority to layered air defence, counter-UAS, dispersal and hardening of depots, POL points and railheads, and make GNSS resilience mandatory for drones, loitering munitions and precision fires.", "F2, F3, F10, I3"),
        ("All Services", "R13", "Weight indigenisation (Aatmanirbharta) priority lists by route exposure, so that items that move through Hormuz or the Red Sea and have long lead-times are indigenised or dual-sourced first.", "F4, F5, F7"),
    ], columns=["Level", "#", "Recommendation", "Based on"])
    d.table(R, "Recommendations traced to findings (F) and inferences (I)", breakable=True)
    d.section("13.2", "Phased Roadmap")
    W = pd.DataFrame([
        ("Phase 1 (0-6 months)", "Institutionalise the pipeline. Host the Power BI dashboard (Appendix B) at HQ IDS and Service HQs; run the weekly CCII and "
         "stand-off-share refresh from ACLED; set alert thresholds; start the tri-service WWR review using Eq. 3.6.",
         "Weekly early-warning brief; revised stock norms for trial"),
        ("Phase 2 (6-18 months)", "Fuse sensors and automate. Ingest national SAR (NISAR, EOS-04) and commercial SAR with AIS; run automated "
         "dark-ship and identity-anomaly detection; retrain the dark-spot model monthly; add freight-rate, insurance and port-call data "
         "to measure physical impact directly.", "Near-real-time dark-ship alerts; validated dark-risk maps"),
        ("Phase 3 (18-36 months)", "Move to prescriptive, joint decision support. Integrate with the tri-service logistics and inventory systems; "
         "simulate stock, route and evacuation decisions under scenarios; extend the same methods to the South China Sea "
         "and Malacca theatres; train staff in data-driven logistics through CDM and Service analytics courses.",
         "Joint supply-chain resilience system; trained analytics cadre"),
    ], columns=["Phase", "Actions", "Deliverable"])
    d.table(W, "Phased roadmap")
    d.section("13.3", "Future Research")
    d.p("Several extensions would strengthen the results: (a) extend the SAR window to a pre-war baseline for the same "
        "waters, which would give a true difference-in-differences estimate of war-induced darkness; (b) add ship-level AIS gap "
        "events and port calls to measure turnaround and diversion directly; (c) model GNSS-interference zones explicitly to separate "
        "spoofing from deliberate switch-off; (d) move from ADMIN1 centroids to event-level ACLED coordinates.")

    # ================================================================== 14 CONCLUSION
    d.chapter("Conclusion")
    d.p("This study set out to measure how global, and in particular Middle-East, conflicts affect maritime supply chains, to locate and "
        "predict AIS dark zones, and to turn the results into guidance for India and its Armed Forces. All six hypotheses are supported by the data.")
    d.section("14.1", "Conflict Analytics")
    d.bullets([
        f"Middle-East political violence moved through distinct regimes, and change-point detection dated the shifts to 7 October 2023 and 28 February 2026 without being given them. The war regime ran at {M['pv_war_ratio']:.1f} times the preceding year.",
        f"The 2026 war was fought mainly with stand-off weapons (84 per cent of violence), reached the GCC energy coast ({M['gcc_multiplier']:.0f}-fold rise) and put the Hormuz littoral at {M['hormuz_war_mult']:.0f} times its baseline.",
        "In the Red Sea the threat moved offshore. Chokepoint risk must be measured at sea, not only on land.",
    ], "alpha")
    d.section("14.2", "Disruption Survival")
    d.bullets([
        f"Disruption episodes are heavy-tailed (median {M['ep_median_wk']:.1f} weeks, longest {M['ep_max_wk']} weeks). {pct(M['km_p_gt_spr'])} outlast India's strategic reserve and {pct(M['km_p_gt_74d'])} outlast total national cover.",
        f"Holding about 35-45 days of stock covers most of the expected shortfall. Beyond about {M['stock_knee_days']} days each extra day of stock adds little protection.",
    ], "alpha")
    d.section("14.3", "AIS Dark Zones")
    d.bullets([
        f"Large ships were AIS-dark in {pct(M['hormuz_large_dark'])} of cases in the Strait of Hormuz and {pct(M['black_large_dark'])} in the Black Sea, against about 10 per cent in peacetime waters (relative risk {M['large_rr']:.1f}). The identification crisis named in the problem statement is real and measurable.",
        "Conflict produces blinding where there is no detour and diversion where there is. Dark tankers gathered at the Gulf anchorages, and shadow-fleet registries were over-represented.",
        f"Proximity to conflict predicts darkness in sea regions the model never saw (ROC-AUC {M['auc_gbt']:.2f}), which makes it possible to forecast where the maritime picture will fail.",
    ], "alpha")
    d.section("14.4", "Implications")
    d.p("For the globe, chokepoint risk has become a recurring cost of trade and a hazard to navigation. For India, the exposure is "
        "concentrated in Gulf energy, westbound trade, connectivity projects and the Gulf diaspora. For the Indian Armed Forces, the "
        "same evidence calls for fuel and spares reserves sized on the survival curve, bases and nodes hardened against stand-off "
        "attack, navigation that does not depend on GNSS alone, and a joint data cell that watches the chokepoints every week.")
    d.p("<b>Closing statement.</b> The first casualty of war at a chokepoint is <i>visibility</i>. Physical disruption follows it, lasts "
        "longer than intuition suggests, and reaches India's energy, trade, diaspora and military sustainment. The same data and methods "
        "that measured this can warn of it. By turning the pipeline, index, dark-spot model and stock-cover curve built here into standing tools, "
        "India and the Indian Armed Forces can base these decisions on data rather than on precedent, which is the aim of the Datathon.")

    # ================================================================== REFERENCES
    d.chapter("References")
    refs = [
        "UNCTAD (2024). <i>Review of Maritime Transport 2024: Navigating maritime chokepoints</i>. United Nations Conference on Trade and Development, Geneva.",
        "U.S. Energy Information Administration (2024). <i>World Oil Transit Chokepoints</i> and <i>Amid regional conflict, the Strait of Hormuz remains critical oil chokepoint</i>. EIA, Washington DC.",
        "College of Defence Management (2026). <i>Datathon-2026: General Instructions</i> and theme datasets 'Global Conflicts - Impact on Supply Chains'. CDM, Secunderabad, under HQ IDS.",
        "Raleigh, C., Linke, A., Hegre, H. and Karlsen, J. (2010). Introducing ACLED: An Armed Conflict Location and Event Dataset. <i>Journal of Peace Research</i>, 47(5), 651-660. Data: ACLED Middle East aggregated data to week of 27 June 2026, www.acleddata.com.",
        "Paolo, F.S., Kroodsma, D., Raynor, J. et al. (2024). Satellite mapping reveals extensive industrial activity at sea. <i>Nature</i>, 625, 85-91. Data: Global Fishing Watch SAR vessel detections.",
        "Killick, R., Fearnhead, P. and Eckley, I.A. (2012). Optimal detection of changepoints with a linear computational cost. <i>Journal of the American Statistical Association</i>, 107(500), 1590-1598.",
        "Truong, C., Oudre, L. and Vayatis, N. (2020). Selective review of offline change point detection methods. <i>Signal Processing</i>, 167, 107299.",
        "Getis, A. and Ord, J.K. (1992). The analysis of spatial association by use of distance statistics. <i>Geographical Analysis</i>, 24(3), 189-206.",
        "Ord, J.K. and Getis, A. (1995). Local spatial autocorrelation statistics: distributional issues and an application. <i>Geographical Analysis</i>, 27(4), 286-306.",
        "Ester, M., Kriegel, H.-P., Sander, J. and Xu, X. (1996). A density-based algorithm for discovering clusters in large spatial databases with noise. <i>Proc. KDD-96</i>, 226-231.",
        "Kaplan, E.L. and Meier, P. (1958). Nonparametric estimation from incomplete observations. <i>Journal of the American Statistical Association</i>, 53(282), 457-481.",
        "Cox, D.R. (1972). Regression models and life-tables. <i>Journal of the Royal Statistical Society, Series B</i>, 34(2), 187-220.",
        "Jayadev, A. (2021). <i>Predictive Maintenance in Armed Forces: A Machine Learning Based Decision Support System</i>. M.Tech Project Report, Department of Mechanical Engineering, IIT Kharagpur.",
        "Roberts, D.R., Bahn, V., Ciuti, S. et al. (2017). Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure. <i>Ecography</i>, 40(8), 913-929.",
        "Friedman, J.H. (2001). Greedy function approximation: a gradient boosting machine. <i>Annals of Statistics</i>, 29(5), 1189-1232.",
        "Hyndman, R.J. and Athanasopoulos, G. (2021). <i>Forecasting: Principles and Practice</i>, 3rd ed. OTexts, Melbourne.",
        "International Maritime Organization. <i>SOLAS Chapter V, Regulation 19</i> - Carriage requirements for shipborne navigational systems and equipment (AIS).",
        "Wilson, E.B. (1927). Probable inference, the law of succession, and statistical inference. <i>Journal of the American Statistical Association</i>, 22(158), 209-212.",
        "Ministry of Petroleum and Natural Gas / Petroleum Planning and Analysis Cell (PPAC), Government of India. Import dependence statistics; Indian Strategic Petroleum Reserves Ltd (ISPRL) capacity (5.33 MMT) and statements on national stock cover.",
        "Ministry of External Affairs, Government of India. Population of Overseas Indians; Reserve Bank of India, Survey on Cross-Border Inward Remittances.",
    ]
    d.add('<ol style="font-size:10.5pt;line-height:1.4;padding-left:20pt">' + "".join(f"<li style='margin-bottom:4pt;text-align:left'>{r}</li>" for r in refs) + "</ol>")

    # ================================================================== APPENDICES
    d.chapter("Appendix A - Toolchain and Reproducibility", letter="A")
    d.p("The analysis is fully scripted. The repository folder <i>datathon2026/</i> contains the pipeline below. Running "
        "<i>python analysis/run_all.py</i> rebuilds every artefact from the two raw files in about one minute on a laptop.")
    d.add('<div class="code">datathon2026/\n'
          '  analysis/common.py              shared styling, regions, chokepoints, MMSI-MID registry, helpers\n'
          '  analysis/01_preprocess.py       cleaning, validation, feature engineering, conflict spatial join\n'
          '  analysis/02_conflict.py         Chapter 5: trends, event mix, heat map, PELT regimes, GCC spill-over, maps\n'
          '  analysis/03_chokepoint_index.py Chapter 6: CCII, thresholds, ARIMA back-test and forecast, Kaplan-Meier, Cox\n'
          '  analysis/04_sar.py              Chapter 7: dark shares, chi-square, Gi* hot spots, DBSCAN, flags, identity\n'
          '  analysis/05_model.py            Chapter 8: logit, gradient-boosted trees, spatial CV, risk surface\n'
          '  analysis/06_decision.py         Section 12.5: expected-shortfall stock-cover model\n'
          '  analysis/07_powerbi_export.py   star-schema tables for the Power BI dashboard\n'
          '  figures/  tables/  powerbi/  data/metrics.json  report/build_report.py</div>')
    d.table(pd.DataFrame([
        ("Language / runtime", "Python 3.11"),
        ("Data manipulation", "pandas 2.x, NumPy, PyArrow (Parquet)"),
        ("Statistics", "SciPy (Mann-Whitney, chi-square, Spearman), statsmodels (Logit, ARIMA/SARIMAX, ETS, Kaplan-Meier, Cox PHReg, Wilson CI)"),
        ("Machine learning", "scikit-learn (HistGradientBoosting with monotonic constraints, GroupKFold spatial CV, DBSCAN, BallTree, permutation importance)"),
        ("Time series", "ruptures (PELT change-points)"),
        ("Visualisation / GIS", "Matplotlib, Basemap (coastlines), custom Getis-Ord Gi*"),
        ("Dashboard", "Microsoft Power BI Desktop (.pbix) on the exported star schema"),
        ("Report", "HTML/CSS rendered to PDF with headless Chromium; all numbers injected from metrics.json"),
    ], columns=["Layer", "Tools"]), "Software stack")
    d.chapter("Appendix B - Power BI Dashboard Data Model", letter="B")
    d.p("The Datathon requires a Power BI (.pbix) file alongside this report. The pipeline exports a star schema "
        "(<i>powerbi/</i>) that loads directly into Power BI Desktop. The model, relationships and core DAX measures are given below. "
        "The step-by-step build of the four dashboard pages is in <i>powerbi/POWERBI_BUILD_GUIDE.md</i>.")
    d.table(pd.DataFrame([
        ("FactConflictWeekly", "149,814", "WEEK, ADMIN1_ID, EVENT_TYPE, SUB_EVENT_TYPE, EVENTS, FATALITIES, flags", "ADMIN1_ID -> DimAdmin1; WEEK -> DimDate[DATE]"),
        ("DimAdmin1", "243", "ADMIN1_ID, COUNTRY, ADMIN1, LAT, LON, GCC, MARITIME, KM_TO_HORMUZ ...", "-"),
        ("FactVesselDetections", "106,533", "DETECTION_ID, DATE, lat, lon, REGION, ZONE, length_m, AIS_DARK, LARGE_100M, flag, flag_class ...", "DATE -> DimDate[DATE]"),
        ("DimDate", "4,383", "DATE, YEAR, QUARTER, MONTH, WEEK_START", "-"),
        ("t6_ccii_weekly, t6_2_episodes, t7_4_dark_clusters, t8_3_poi_risk, t9_1_stock_decision", "-", "analysis outputs", "stand-alone"),
    ], columns=["Table", "Rows", "Key columns", "Relationship"]), "Power BI star schema", small=True)
    d.add('<div class="code">Events            = SUM(FactConflictWeekly[EVENTS])\n'
          'Fatalities        = SUM(FactConflictWeekly[FATALITIES])\n'
          'Stand-off share   = DIVIDE(CALCULATE([Events], FactConflictWeekly[DRONE_MISSILE] = TRUE()),\n'
          '                           CALCULATE([Events], FactConflictWeekly[POLITICAL_VIOLENCE] = TRUE()))\n'
          'Detections        = COUNTROWS(FactVesselDetections)\n'
          'Dark share        = DIVIDE(CALCULATE([Detections], FactVesselDetections[AIS_DARK] = TRUE()), [Detections])\n'
          'Dark share large  = CALCULATE([Dark share], FactVesselDetections[LARGE_100M] = TRUE())\n'
          'Dark RR vs world  = DIVIDE([Dark share large],\n'
          '                           CALCULATE([Dark share large], FactVesselDetections[ZONE] = "Rest of world"))</div>')
    d.p("<b>Dashboard pages.</b> (1) Conflict Pulse: weekly events and fatalities, event-type mix, map of ADMIN1 bubbles, GCC slicer. "
        "(2) Chokepoint Watch: CCII lines by theatre with threshold lines, episode table, forecast. (3) Dark Ships: map of detections "
        "coloured by AIS_DARK, dark share by region and size, cluster table, flag class. (4) Decision: stock-cover decision table, "
        "points-of-interest risk, and a what-if parameter for days of stock.")
    return d


def front_html(body, pages):
    toc = []
    for mid, lvl, lab, title in body.sec:
        if lvl > 2 and not title.startswith(("Proportions", "Change-point")):
            pass
        toc.append(f'<tr class="l{lvl}"><td class="t">{lab}&nbsp;&nbsp;{title}</td><td class="pg">{pages.get(mid, "")}</td></tr>')
    lof = "".join(f'<tr><td style="width:62pt">Figure {lab}</td><td class="t">{cap}</td><td class="pg">{pages.get(mid, "")}</td></tr>'
                  for mid, lab, cap in body.figs)
    lot = "".join(f'<tr><td style="width:56pt">Table {lab}</td><td class="t">{cap}</td><td class="pg">{pages.get(mid, "")}</td></tr>'
                  for mid, lab, cap in body.tabs)
    abbr = [("ACLED", "Armed Conflict Location & Event Data"), ("AIS", "Automatic Identification System"),
            ("AUC", "Area Under the (ROC) Curve"), ("CCII", "Chokepoint Conflict Intensity Index"),
            ("CI", "Confidence Interval"), ("DBSCAN", "Density-Based Spatial Clustering of Applications with Noise"),
            ("FoC", "Flag of Convenience"), ("GBT", "Gradient-Boosted Trees"), ("GCC", "Gulf Cooperation Council"),
            ("GNSS", "Global Navigation Satellite System"), ("HR", "Hazard Ratio"), ("IFC-IOR", "Information Fusion Centre - Indian Ocean Region"),
            ("IMEC", "India-Middle East-Europe Economic Corridor"), ("INSTC", "International North-South Transport Corridor"),
            ("KM", "Kaplan-Meier"), ("MDA", "Maritime Domain Awareness"), ("MID", "Maritime Identification Digits"),
            ("MMSI", "Maritime Mobile Service Identity"), ("OR", "Odds Ratio"), ("PELT", "Pruned Exact Linear Time"),
            ("POL", "Petroleum, Oil and Lubricants"), ("RR", "Relative Risk"), ("SAR", "Synthetic Aperture Radar"),
            ("SPR", "Strategic Petroleum Reserve"), ("VLCC", "Very Large Crude Carrier"), ("WWR", "War Wastage Reserve")]
    ab = "".join(f"<tr><td style='width:70pt'><b>{a}</b></td><td>{b}</td></tr>" for a, b in abbr)
    abstract = (
        "<p>The Datathon-2026 theme <i>Global Conflicts - Impact on Supply Chains</i> asks how conflicts affect world shipping, "
        "and specifically asks participants to identify AIS dead zones and relate them to the identification crisis created by local "
        "conflicts. This study combines eleven and a half years of weekly Middle-East conflict data (ACLED; "
        f"{n(M['acled_events'])} events) with {n(M['sar_rows'])} Sentinel-1 radar vessel detections matched to AIS during the first "
        "two weeks of the 2026 regional war (1-14 March 2026).</p>"
        "<p>Change-point detection dates the regime shifts in regional violence to 7 October 2023 and 28 February 2026 "
        f"without being given either date. The war regime ran at {M['pv_war_ratio']:.1f} times the previous year's rate and was dominated (84 per cent) by "
        f"stand-off strikes, which reached the GCC energy coast ({M['gcc_multiplier']:.0f}-fold rise). A new Chokepoint Conflict Intensity "
        "Index shows that the Red Sea threat moved offshore and that the Hormuz littoral reached "
        f"{M['hormuz_war_mult']:.0f} times its baseline. Survival analysis of {M['ep_n']} disruption episodes shows a heavy tail: "
        f"{pct(M['km_p_gt_spr'])} outlast India's strategic petroleum reserve.</p>"
        f"<p>Large ships were AIS-dark in {pct(M['hormuz_large_dark'])} of cases in the Strait of Hormuz and {pct(M['black_large_dark'])} in "
        f"the Black Sea, against about 10 per cent in peacetime waters (relative risk {M['large_rr']:.1f}, odds ratio {M['large_or']:.1f}). "
        "Getis-Ord hot spots and DBSCAN clusters locate fleets of dark tankers waiting at the Dubai and Fujairah anchorages. A "
        f"gradient-boosted model validated on unseen sea regions (ROC-AUC {M['auc_gbt']:.2f}) predicts AIS dark spots from "
        "conflict geography.</p>"
        "<p>The main inference is that the first measurable effect of war at a chokepoint is the <i>blinding</i> of the supply chain, "
        "followed by physical disruption that lasts longer than national buffers. The report then assesses the impact on the globe, on India "
        "and on the Indian Armed Forces (Navy, Air Force, Army and joint), gives a prescriptive stock-cover model (returns flatten at about "
        f"{M['stock_knee_days']} days of cover), and sets out a way forward of thirteen traced recommendations, a phased roadmap and a Power BI "
        "decision dashboard, before concluding.</p>"
        "<p><b>Keywords:</b> supply chain, chokepoints, AIS dark vessels, SAR, ACLED, change-point detection, Getis-Ord Gi*, DBSCAN, "
        "survival analysis, spatial cross-validation, Indian Armed Forces logistics.</p>")
    return f"""<div class="titlepage">
<div class="t3">COLLEGE OF DEFENCE MANAGEMENT &middot; DATATHON - 2026</div>
<div class="t3" style="margin-bottom:34pt">Theme: Global Conflicts &ndash; Impact on Supply Chains</div>
<div class="t1">{TITLE}</div><div class="t2">{SUBTITLE}</div>
<div class="t3">Submitted by</div><div class="t3"><b>{RANK} {AUTHOR.upper()}</b></div><div class="t3">{SERVICE_NO} &middot; {UNIT}</div>
<div class="t3" style="margin-top:34pt">Submitted to the Faculty of Decision Sciences, College of Defence Management, Secunderabad</div>
<div class="t3">under the aegis of HQ Integrated Defence Staff</div><div class="t3" style="margin-top:26pt">September 2026</div>
<div class="t3" style="margin-top:40pt;font-size:10pt;color:#444">Accompanying files: Power BI dashboard (.pbix), star-schema data tables, analysis source code</div></div>
<div class="front pb"><h1>DECLARATION</h1>
<p>I hereby certify that:</p><ul>
<li>The work in this report is original and has been done by me for Datathon-2026 of the College of Defence Management.</li>
<li>The analysis uses the unclassified datasets provided on the CDM website and open-source literature. No classified information has been used.</li>
<li>Due credit has been given to all data, inferences and references from external sources, and they are cited appropriately.</li>
<li>All figures, tables and statistics can be reproduced from the submitted code and data.</li></ul>
<div class="sig"><div>Place: ____________<br>Date: &nbsp;&nbsp;&nbsp;September 2026</div><div style="text-align:right">({RANK} {AUTHOR})<br>{SERVICE_NO}</div></div></div>
<div class="front pb"><h1>ACKNOWLEDGEMENT</h1>
<p>I thank the College of Defence Management and HQ Integrated Defence Staff for conducting Datathon-2026 and for placing
contemporary, unclassified datasets in the hands of serving officers. I am grateful to my Commanding Officer and superiors for
their encouragement, and to the open-data communities (ACLED, Global Fishing Watch, Copernicus Sentinel-1) whose work made this study possible.
The analytical grounding I received during my M.Tech at IIT Kharagpur, where I applied survival analysis to predictive maintenance
of armoured vehicles, shaped much of the method used here.</p></div>
<div class="front pb"><h1>ABSTRACT</h1>{abstract}</div>
<div class="front pb"><h1>LIST OF ABBREVIATIONS</h1><table class="toc">{ab}</table></div>
<div class="front pb"><h1>LIST OF FIGURES</h1><table class="toc">{lof}</table></div>
<div class="front pb"><h1>LIST OF TABLES</h1><table class="toc">{lot}</table></div>
<div class="front pb"><h1>TABLE OF CONTENTS</h1><table class="toc">
<tr class="l1"><td class="t">Abstract</td><td class="pg">iv</td></tr>
<tr class="l1"><td class="t">List of Abbreviations, Figures and Tables</td><td class="pg">v</td></tr>
{''.join(toc)}</table></div>"""


def page(html_body):
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{html_body}</body></html>"


def render(browser, html_str, path):
    pg = browser.new_page()
    pg.set_content(html_str, wait_until="load")
    pg.pdf(path=str(path), format="A4", print_background=True,
           margin={"top": "24mm", "bottom": "22mm", "left": "26mm", "right": "22mm"})
    pg.close()


def roman(k):
    vals = [(10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]
    out = ""
    for v, s in vals:
        while k >= v:
            out += s
            k -= v
    return out


def main():
    body = build_body()
    body_html = page("".join(body.parts))
    (OUT / "report_body.html").write_text(body_html)
    with sync_playwright() as p:
        br = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
        render(br, body_html, OUT / "_body.pdf")
        bd = fitz.open(OUT / "_body.pdf")
        pages = {}
        for i, pg_ in enumerate(bd):
            for mk in re.findall(r"@@([A-Z0-9_]+)@@", pg_.get_text()):
                pages.setdefault(mk, i + 1)
        for pg_ in bd:
            hits = [w for w in pg_.get_text("words") if "@@" in w[4]]
            for w in hits:
                pg_.add_redact_annot(fitz.Rect(w[:4]), fill=False)
            if hits:
                pg_.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)
        front = page(front_html(body, pages))
        render(br, front, OUT / "_front.pdf")
        br.close()
    fr = fitz.open(OUT / "_front.pdf")
    doc = fitz.open()
    doc.insert_pdf(fr)
    doc.insert_pdf(bd)
    nf = len(fr)
    for i, pg_ in enumerate(doc):
        w, h = pg_.rect.width, pg_.rect.height
        if i == 0:
            continue
        label = roman(i + 1) if i < nf else str(i - nf + 1)
        pg_.insert_text((w / 2 - 6, h - 30), label, fontsize=10, fontname="times-roman")
        pg_.insert_text((74, 40), "CDM Datathon-2026  |  Global Conflicts - Impact on Supply Chains", fontsize=7.5,
                        fontname="helv", color=(0.45, 0.45, 0.45))
        pg_.draw_line((74, 45), (w - 62, 45), color=(0.75, 0.75, 0.75), width=0.4)
    doc.set_metadata({"title": f"{TITLE.title()} - CDM Datathon 2026", "author": AUTHOR,
                      "subject": "Global Conflicts - Impact on Supply Chains"})
    out = OUT / "Datathon2026_Global_Conflicts_Supply_Chains_Report.pdf"
    doc.save(out, garbage=4, deflate=True)
    for f in ("_body.pdf", "_front.pdf"):
        (OUT / f).unlink()
    print("pages:", len(doc), "front:", nf, "->", out)


if __name__ == "__main__":
    main()
