"""Self-assessment on the CDM Datathon-2026 Assessment Sheet (Appendix B, Para 8.5 of the General Instructions),
plus a compliance check against the General Instructions."""

# =====================================================================================================
# ANNOTATED SOURCE - build_scoresheet.py: self-assessment on the CDM Datathon-2026 Assessment Sheet
# -----------------------------------------------------------------------------------------------------
# S lists every criterion of Appendix B (Para 8.5, General Instructions): paragraph, criterion, maximum marks,
# marks
# awarded, evidence from the submission, and what would lift the mark. Section rows (awarded = None) are
# totalled
# automatically. IMPACT is the overall impact rating (1-10). Output: Datathon2026_Self_Assessment_Sheet.pdf.
# =====================================================================================================

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
M = json.loads((ROOT / "data/metrics.json").read_text())

S = [  # (para, item, max, awarded, evidence, what would lift it)
    ("4", "DATA ANALYTICS", 40, None, None, None),
    ("4.1", "Ability to understand and define the problem", 8, 8,
     "Core question ('do ships leave or stop identifying themselves?') answers the theme text on AIS dead zones and the identification "
     "crisis in the Black Sea / Persian Gulf; aim, objectives and seven testable hypotheses stated (Ch 1).", "-"),
    ("4.2", "Quality of data preprocessing and cleaning", 8, 7,
     f"Cleaning log for both files; confidence filter; MMSI validity; {M['alldark_n']} possible feed-outage passes isolated; maritime "
     "pseudo-countries separated; fully repeatable pipeline (two runs give identical outputs).",
     "Bring the forensic-screen table (unmatched-with-MMSI, all-dark passes) into the short edition."),
    ("4.3", "Selection of appropriate analytical techniques", 8, 8,
     "Each technique mapped to a commander's question (Annex B): change-points, survival analysis, hot-spots, clustering, "
     "difference-in-differences, event study, spatially honest machine-learning validation.", "-"),
    ("4.4", "Depth and accuracy of analysis", 8, 7,
     f"Findings replicated under 8 specifications, dose-response, DiD (+{M['did_excess']:.1f} pts/day, p = {M['did_p']:.3f}), stasis, "
     "out-of-sample oil-price check; failed or non-replicating claims dropped.",
     "SAR window is 14 days; presence-vs-identity rests on two passes; defence-budget figure to be verified."),
    ("4.5", "Use of relevant visualizations and insights", 8, 8,
     "40+ charts and 11 infographics; every chart carries a one-line 'What this shows'; theatre map, four-signature and "
     "centre-of-gravity graphics.", "-"),
    ("5", "TECHNICAL SKILLS", 25, None, None, None),
    ("5.1", "Proficiency in programme languages / platform / software", 5, 3,
     "Advanced Python pipeline (11 stages). Power BI star schema, DAX and build guide prepared, but the .pbix is not yet built.",
     "Build and submit the .pbix (mandatory, Para 8.2) and add its screenshots: +2."),
    ("5.2", "Utilization of libraries and frameworks", 7, 6,
     "pandas, NumPy, SciPy, statsmodels, scikit-learn, ruptures, Matplotlib/Basemap, headless-browser reporting.",
     "Power BI visuals and DAX in the dashboard would confirm this mark."),
    ("5.3", "Efficient data manipulation and transformation", 8, 7,
     "Haversine spatial joins, scene/pass aggregation, weekly panels, star-schema export (FactConflictWeekly, FactVesselDetections).",
     "Show Power Query steps in the .pbix: +1."),
    ("5.4", "Application of statistical methods", 5, 5,
     "Wilson intervals, chi-square, Mann-Whitney, bootstrap, permutation tests, Kaplan-Meier/Cox, ARIMA back-test, Granger.", "-"),
    ("6", "CREATIVITY AND INNOVATION", 20, None, None, None),
    ("6.1", "Uniqueness and originality of the approach", 6, 6,
     "Maritime Picture Assurance; Strategic Dark Ratio; presence vs identity; four signatures.", "-"),
    ("6.2", "Creative problem-solving techniques", 6, 6,
     "Satellite revisits used to detect held ships; survival curves turned into a 35-45 day stock rule; I&W tested out-of-sample.", "-"),
    ("6.3", "Innovative use of data and methods", 8, 7,
     "Fuses CDM conflict + SAR/AIS data with IMF PortWatch chokepoint transits, open oil-price, rupee, energy, port data and news.",
     "Future work: a longer SAR record with a pre-war baseline (not achievable before 30 Sep)."),
    ("7", "COMMUNICATION", 15, None, None, None),
    ("7.1", "Clarity and organization of the report / presentation", 5, 5,
     "Decision brief, story arc (Prologue, Parts I-VIII, Epilogue), 'So what' boxes, contents and annexes.", "-"),
    ("7.2", "Ability to convey complex ideas concisely", 5, 4,
     "22-page edition with plain-words glossary; executive summary is still number-dense.",
     "Trim the executive summary to five numbers: +1."),
    ("7.3", "Engaging and informative data storytelling", 5, 5,
     "Single narrative from the storm on land to the Armed Forces; each chapter links to the previous.", "-"),
]
# Overall impact rating on the 1-10 scale of Para 8.1.
IMPACT = 9
subtot = {"4": 0, "5": 0, "6": 0, "7": 0}
for p, *_r in S:
    if "." in p:
        subtot[p.split(".")[0]] += _r[2]
total = sum(subtot.values())
potential = total + 2 + 1 + 1   # achievable by 30 Sep: .pbix (5.1 +2, 5.3 +1) and a tighter executive summary (7.2 +1)

rows = ""
for p, item, mx, aw, ev, lift in S:
    if aw is None:
        rows += (f"<tr class='sec'><td>{p}.</td><td colspan='2'><b>{item}</b> ({mx} points)</td>"
                 f"<td class='c'><b>{subtot[p]} / {mx}</b></td><td colspan='2'></td></tr>")
    else:
        rows += (f"<tr><td>{p}</td><td>{item}</td><td class='c'>{mx}</td><td class='c'><b>{aw}</b></td>"
                 f"<td>{ev}</td><td>{lift}</td></tr>")

comp = [
    ("Theme chosen from Para 6", "Yes", "6.2 Global Conflicts - Impact on Supply Chains"),
    ("Theme datasets used (Para 5, 8.1)", "Yes", "ACLED Middle-East aggregates; Sentinel-1 SAR vessel detections"),
    ("Other open-source datasets used, with citation (Para 5, 7)", "Yes", "IMF PortWatch (28 chokepoints, daily), EIA Brent/WTI, Fed H.10 INR/US$, Energy Institute via OWID, Natural Earth, dated news chronology; cited in Annex D"),
    ("Theme text addressed: AIS dead zones, predict AIS dark spots, identification crisis (Para 6.2)", "Yes", "Ch 4 (dark zones, prediction), Annex B"),
    ("Insights and recommendations for India and the Armed Forces (Para 5, 6)", "Yes", "Ch 7-9; staffed actions"),
    ("Analysis submitted in PDF (Para 8.2)", "Yes", "Commander's Edition; full technical report as annex"),
    ("Screenshots of data analytics software used (Para 8.2)", "Partial", "Python pipeline and code in Annex C; Power BI screenshots pending"),
    ("Output files in Power BI (*.pbix) format only (Para 8.2)", "NO", "Tables, DAX and build guide ready; .pbix to be built"),
    ("Personal details (Appendix A format) (Para 8.1, 8.2)", "NO", "Rank, Service No, Unit and Appendix A form pending"),
    ("Submitted to datathon.ids@gov.in by 30 Sep 26 (Para 8.2)", "Pending", "-"),
]
crow = "".join(f"<tr><td>{a}</td><td class='c {('ok' if b == 'Yes' else 'no' if b == 'NO' else 'pa')}'>{b}</td><td>{c}</td></tr>" for a, b, c in comp)

html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 15mm 14mm; }}
body {{ font-family: 'Liberation Serif', serif; font-size: 10pt; color: #111; }}
h1 {{ text-align: center; font-size: 13pt; margin: 0; }} .sub {{ text-align: center; font-size: 9.5pt; margin: 2pt 0 8pt 0; }}
table {{ border-collapse: collapse; width: 100%; font-family: 'Liberation Sans', sans-serif; font-size: 7.9pt; }}
td, th {{ border: .5pt solid #999; padding: 3pt 4pt; vertical-align: top; }} th {{ background: #1f3b5c; color: #fff; text-align: left; }}
tr.sec td {{ background: #e8edf3; }} .c {{ text-align: center; }} .ok {{ color: #2e7d32; font-weight: bold; }}
.no {{ color: #c62828; font-weight: bold; }} .pa {{ color: #b26a00; font-weight: bold; }}
.info td {{ border: none; font-family: 'Liberation Serif', serif; font-size: 10pt; padding: 1pt 4pt; }}
.tot {{ margin-top: 6pt; border: 1pt solid #1f3b5c; padding: 6pt 8pt; font-size: 10.5pt; }} h2 {{ font-size: 11pt; margin: 10pt 0 4pt 0; }}
.note {{ font-size: 8.5pt; color: #444; margin-top: 4pt; }}
</style></head><body>
<h1>DATATHON: ASSESSMENT SHEET</h1>
<div class="sub">(Appendix B, refers Para 8.5 of General Instructions, Datathon-2026) &middot; <b>Self-assessment of the submission before dispatch</b></div>
<b>Participant Information</b>
<table class="info"><tr><td>1. Participant's Rank &amp; Name</td><td>: [Rank] Arjun Jayadev</td></tr>
<tr><td>2. Theme</td><td>: 6.2 Global Conflicts - Impact on Supply Chains (Project DARKWATER)</td></tr>
<tr><td>3. Date of Assessment</td><td>: 23 Sep 2026</td></tr>
<tr><td>Documents assessed</td><td>: Commander's Edition (24 pp, main submission) with Full Technical Report (90 pp) as annex</td></tr></table>
<h2>Scoring Criteria</h2>
<table><tr><th style="width:4%">Para</th><th style="width:21%">Criterion</th><th style="width:5%">Max</th><th style="width:6%">Marks</th>
<th style="width:38%">Evidence in the submission</th><th style="width:26%">What would lift the mark</th></tr>{rows}</table>
<div class="tot"><b>TOTAL: {total} / 100</b> as the submission stands today &nbsp;|&nbsp; <b>{potential} / 100</b> achievable by 30 Sep once actions 1-5 below are closed.
<br><b>8. Overall Impact</b> - 8.1 Rate the overall impact on a scale of 1-10 &nbsp;: <b>{IMPACT} / 10</b> (a decision brief with a costed,
no-new-money first phase, a validated early warning and quantified implications for all three Services).
<br>Sub-totals: Data Analytics {subtot['4']}/40 &middot; Technical Skills {subtot['5']}/25 &middot; Creativity &amp; Innovation {subtot['6']}/20 &middot; Communication {subtot['7']}/15</div>
<h2>Compliance with the General Instructions</h2>
<table><tr><th style="width:44%">Requirement (Gen Instr para)</th><th style="width:9%">Status</th><th>Remarks</th></tr>{crow}</table>
<h2>Actions to close before 30 Sep 26</h2>
<table><tr><th style="width:4%">#</th><th>Action</th><th style="width:22%">Effect on assessment</th></tr>
<tr><td>1</td><td>Build the .pbix in Power BI Desktop from powerbi/ (four pages) and attach it</td><td>Mandatory (Para 8.2); +3 to 5.1-5.3</td></tr>
<tr><td>2</td><td>Paste two Power BI screenshots into Annex C (Fig C.3, C.4)</td><td>Completes Para 8.2 screenshot requirement</td></tr>
<tr><td>3</td><td>Fill Rank, Service No, Unit; attach Appendix A details</td><td>Mandatory (Para 8.1)</td></tr>
<tr><td>4</td><td>Verify the 2026-27 defence budget figure used in the defence-cost comparison</td><td>Protects 4.4 (accuracy)</td></tr>
<tr><td>5</td><td>Trim the executive summary to five headline numbers</td><td>+1 to 7.2</td></tr></table>
<div class="note">Note: a self-assessment by the author tends to run a few points generous; independent assessors may mark 3-5 points lower.</div>
</body></html>"""
out = ROOT / "report" / "Datathon2026_Self_Assessment_Sheet.pdf"
(ROOT / "report" / "_html").mkdir(exist_ok=True)  # kept for the editable Word version (build_word.py)
(ROOT / "report" / "_html" / "scoresheet.html").write_text(html)
with sync_playwright() as p:
    br = p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    pg = br.new_page()
    pg.set_content(html)
    pg.pdf(path=str(out), format="A4", print_background=True)
    br.close()
print("total", total, "potential", potential, "->", out)
