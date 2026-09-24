"""Technical Annex to Project HIGH GROUND (Theme 6.1): methods, formulas, parameters, validation and limitations.

Usage:  cd report && python build_annex.py        (after analysis/run_all.py). Also saves HTML for build_word.py.
"""

# =====================================================================================================
# ANNOTATED SOURCE - build_annex.py
# The annex is written for assessors and analysts: every method with its formula, parameters and test result, so the
# booklet's claims can be checked and the pipeline re-run. Numbers come from data/metrics.json and tables/*.csv.
# =====================================================================================================
import re

import pandas as pd

import infographics_space as IG
import story as ST
from booklet_lib import CHROME, CSS, M, OUT, WORD, Doc, T, fitz, pct, roman, sync_playwright

TITLE = "PROJECT HIGH GROUND"


def eqn(d, body, num):
    d.eq(body, num)


def build():
    d = Doc()
    d.kickers, d.opens, d.closes = {}, {}, {}

    d.chapter("Scope, Data and Preparation")
    d.p("This annex documents every method behind the Commander's Edition: definitions, formulas, parameters, validation and "
        "limitations. All numbers are regenerated from raw data by <i>analysis/run_all.py</i> (12 stages); two consecutive runs give "
        "identical outputs.")
    src = pd.DataFrame([
        ("CDM satellite census", "1,167 active satellites", "launched 1974 - Jan 2014", "orbit, mass, power, users, purpose, life", "CDM"),
        ("CDM Dst index", f"{M['dst_n']:,} hourly values", "3 anonymised periods", "geomagnetic disturbance (nT)", "CDM"),
        ("CDM smoothed sunspot number", "192 values", "same periods", "solar activity", "CDM"),
        ("CDM MODIS fire detections", f"{M['fires_n']:,}", f"{M['fires_first']} - {M['fires_last']}", "position, time, satellite, type", "CDM"),
        ("CelesTrak SATCAT", f"{M['satcat_n']:,} Earth-orbiting objects", f"1957 - {M['satcat_last']}", "type, owner, launch, decay, orbit", "Open"),
        ("UCS Satellite Database", f"{M['ucs20_n']:,} active satellites", "1 Apr 2020", "as CDM census (second census)", "Open"),
        ("UNOOSA registry (OWID)", "objects per country-year", "1957 - 2023", "cross-check of launch counts", "Open"),
        ("CelesTrak GP elements (OMM)", f"{M['cj_A_n']:,} + {M['cj_B_n']:,} LEO objects", "epochs 30 Aug - 23 Sep 2026", "SGP4 orbital elements", "Open"),
    ], columns=["Dataset", "Size", "Period", "Fields used", "Source"])
    d.table(src, "Data sources", small=True)
    d.table(T("t1_cleaning_log"), "Cleaning log (every step and the rows it touched)", small=True)
    d.p("Validation rules: launch dates converted from Excel serial days (origin 1899-12-30); orbital periods below 80 minutes and "
        "inclinations above 180 degrees are physically impossible and set to missing; the misspelt user class 'Commerical' is corrected; "
        "catalogue owner and launch-site codes are decoded with explicit look-up tables (analysis/common.py); only Earth-orbiting "
        "objects are kept.")

    d.chapter("Growth, Concentration and Congestion")
    d.section("2.1", "Population reconstruction")
    d.p("An object is in orbit at date <i>t</i> if launched on or before <i>t</i> and not re-entered by <i>t</i>:")
    eqn(d, "N(t) = #{ i : launch<sub>i</sub> &le; t &lt; decay<sub>i</sub> }&nbsp;&nbsp;(decay<sub>i</sub> = &infin; if still in orbit)", 1)
    d.p(f"Active-satellite counts come from three independent censuses (CDM 2014: {M['active_2014']:,}; UCS 2020: {M['active_2020']:,}; catalogue "
        f"operational flag 2026: {M['active_now']:,}). UNOOSA registrations and catalogue payload launches correlate at r = {M['unoosa_corr']}.")
    d.section("2.2", "Change-points and growth rates")
    d.p("PELT (Killick et al., 2012) minimises the total within-segment squared error plus a penalty per change-point:")
    eqn(d, "min<sub>&tau;</sub> &Sigma;<sub>k</sub> &Sigma;<sub>t&isin;segment k</sub> (y<sub>t</sub> &minus; &#563;<sub>k</sub>)<sup>2</sup> + &beta;&middot;K", 2)
    d.p(f"applied to payloads launched per year 1990-2025, scaled by its standard deviation, with &beta; = 3, minimum segment 3 years. "
        f"Result: break in {M['growth_cps'][0]}. Compound annual growth rate CAGR = (x<sub>b</sub>/x<sub>a</sub>)<sup>1/(b&minus;a)</sup> &minus; 1: "
        f"{M['cagr_2000_2013']}% (2000-2013), {M['cagr_2019_2025']}% (2019-2025).")
    d.section("2.3", "Concentration")
    eqn(d, "HHI = &Sigma;<sub>c</sub> (100 &middot; s<sub>c</sub>)<sup>2</sup>, &nbsp; s<sub>c</sub> = share of active satellites of country c", 3)
    d.p(f"Thresholds per the US merger guidelines: &gt; 1,800 moderately and &gt; 2,500 highly concentrated (older convention). Results: "
        f"{M['hhi_country_2014']:,.0f} (2014), {M['hhi_country_2020']:,.0f} (2020), {M['hhi_country_now']:,.0f} (2026).")
    d.section("2.4", "Collision-risk index")
    d.p("Low orbit (apogee &lt; 2,000 km) is cut into 25 km shells at each object's mean altitude (perigee + apogee)/2. Under the "
        "kinetic-gas model (Kessler and Cour-Palais, 1978) the collision rate in a shell is proportional to n<sub>i</sub><sup>2</sup> "
        "&middot; &sigma; &middot; v<sub>rel</sub> / V<sub>i</sub>; with cross-section &sigma; and relative speed v<sub>rel</sub> held equal "
        "across shells:")
    eqn(d, "I = &Sigma;<sub>i</sub> n<sub>i</sub><sup>2</sup> / V<sub>i</sub>, &nbsp; V<sub>i</sub> = 4/3 &pi; [(R+h<sub>i</sub>+&Delta;)<sup>3</sup> &minus; (R+h<sub>i</sub>)<sup>3</sup>], &nbsp; R = 6,371 km, &Delta; = 25 km", 4)
    d.p(f"normalised to January 2014 = 1. Result: {M['risk_ratio']} (Sep 2026); scenarios for 2030: {M['risk_2030_low']} / {M['risk_2030_base']} / "
        f"{M['risk_2030_high']}. It is a relative index, not a probability; it ignores size differences and manoeuvres (which reduce "
        "real risk for active satellites) and eccentric orbits crossing several shells.")
    d.section("2.5", "Debris survival")
    d.p("For each weapon test or collision, the share of catalogued pieces still in orbit <i>t</i> years after the event, with pieces "
        "still in orbit treated as censored at the catalogue date:")
    eqn(d, "S(t) = #{ pieces with (decay &minus; event) &gt; t or still in orbit } / #{ pieces }", 5)
    d.table(T("t4_asat_debris"), "Debris created and remaining by event", small=True)

    d.chapter("Contest, Space Weather and Earth-Observation Value")
    d.section("3.1", "Programme families (name rules)")
    d.table(T("t5_isr_families"), "Military and state-ISR families from official names (lower bound: covert or commercially flagged "
            "military satellites are not counted)", small=True)
    d.section("3.2", "Geomagnetic storms")
    d.p("Storm = a run of consecutive hours with Dst &le; &minus;50 nT; intense if its minimum &le; &minus;100 nT, severe if &le; "
        "&minus;200 nT (Gonzalez et al., 1994). Each hour is matched to the smoothed sunspot number by linear interpolation; data are cut "
        "into 30-day blocks (blocks with &lt; 25 days dropped). Poisson regression of intense-storm counts:")
    eqn(d, "log E[storms<sub>b</sub>] = &beta;<sub>0</sub> + &beta;<sub>1</sub> &middot; SSN<sub>b</sub>/50", 6)
    d.p(f"gives a rate ratio e<sup>&beta;1</sup> = {M['storm_irr50']} per 50 sunspots (p = {M['storm_irr_p']:.1e}); Spearman &rho; between "
        f"block sunspot number and block minimum Dst = {M['storm_rho']} (p = {M['storm_rho_p']:.1e}). Share of 30-day blocks with at least one "
        f"intense storm: {pct(M['p_intense_hi'])} at SSN &ge; 100 vs {pct(M['p_intense_lo'])} at SSN &lt; 30.")
    d.table(T("t6_storm_classes"), "Storm events by class", small=True)
    d.section("3.3", "Solar cycle in re-entries")
    d.p("Re-entry rate r<sub>y</sub> = debris and rocket bodies (perigee &lt; 2,000 km at the start of year y) re-entering in year y / "
        "that population, 1965-2025. log r<sub>y</sub> is de-trended with a quadratic and a periodogram taken; the dominant period is "
        f"{M['reentry_period']} years (solar cycle ~11 years). Mean rate near solar maxima {M['reentry_max']}% vs minima {M['reentry_min']}%.")
    d.section("3.4", "Constellation premium and surge detection (MODIS)")
    d.p("Each archive detection is assigned to a cell-day (0.1&deg; latitude x 0.1&deg; longitude x calendar day). The share of cell-days "
        f"seen by only one satellite is {pct(M['prem_single'])} (Aqua only {pct(M['prem_aqua_only'])}, Terra only {pct(M['prem_terra_only'])}). "
        "Monthly surge score z<sub>m</sub> = (x<sub>m</sub> &minus; median of the same month in earlier years) / their standard deviation; "
        f"z &gt; 2 flags a surge ({M['surges_n']} months).")

    d.chapter("Machine Learning: Military-Use Classifier")
    feats = pd.DataFrame([
        ("Orbit", "log perigee, log apogee, eccentricity, inclination, log period; orbit class (LEO/MEO/GEO/elliptical)"),
        ("Engineered", "sun-synchronous-like (95-100.5 deg, apogee < 1,500 km); Molniya-like (eccentricity > 0.5, 60-66 deg)"),
        ("Build", "log launch mass, log power, design life (gaps allowed: imputed with medians plus missing-value indicators)"),
        ("Excluded", "name, purpose, users, operator, contractor (would leak the label); launch year (cannot extrapolate)"),
        ("Variant", "physics + operator country bloc (USA / China / Russia / India / other)"),
    ], columns=["Group", "Features"])
    d.table(feats, "Features", small=True)
    d.p(f"Label: military = the Users field mentions Military (incl. dual-use), {M['ml_pos_train']} of {M['ml_n_train']:,} in 2014. Models: "
        "L2-regularised logistic regression (C = 0.5) and histogram gradient-boosted trees (250 iterations, learning rate 0.05, 15 leaves). "
        "Protocol: (a) 5-fold stratified cross-validation repeated 5 times on the 2014 census; (b) out-of-time test: fit on all of 2014, "
        f"predict the {M['ml_n_test']:,} UCS 2020 satellites launched after the census ({M['ml_pos_test']} military). The model is "
        "chosen on (b).")
    d.table(T("t11_ml_results"), "Model skill", small=True)
    d.table(T("t11_ml_importance").head(8), "Permutation importance on the out-of-time set (chosen model)", small=True)
    d.p(f"Cross-validation would have chosen the trees ({M['ml_cv_auc_gbt']}), which collapse out of time ({M['ml_ext_auc_gbt']}): the post-2014 "
        "population (mass-produced commercial constellations in low orbit) differs from the 2014 one, and the trees memorise the old one. "
        f"The logistic model degrades gracefully ({M['ml_cv_auc']} to {M['ml_ext_auc']}). Dual-use signal: {M['ml_dual_n']} of {M['ml_civil_n']:,} "
        "non-military satellites score p &ge; 0.5.")

    d.chapter("Close-Approach Screening")
    par = pd.DataFrame([
        ("Elements", "CelesTrak GP data (CCSDS OMM) via public mirror; LEO only: mean motion >= 11.25 rev/day, eccentricity <= 0.25"),
        ("Screening A", f"{M['cj_A_n']:,} active satellites vs each other, 24 h from 31 Aug 2026 12:00 UTC (elements of 30-31 Aug)"),
        ("Screening B", f"{M['cj_B_n']:,} objects: freshly tracked satellites + 4 debris clouds, 24 h from 23 Sep 2026 12:00 UTC (elements of 21-24 Sep)"),
        ("Propagator", "SGP4 (Vallado et al., 2006), WGS-72, vectorised"),
        ("Coarse filter", "positions every 10 s; k-d tree pairs within 80 km (>= half the 150 km two objects can close in 10 s at 15 km/s)"),
        ("Refinement", "1-s positions over +-10 s around the closest sample; linearised closest approach (eq. 7)"),
        ("Thresholds", "report < 5 km; high interest < 1 km; co-orbiting / docked if relative speed < 0.5 km/s"),
    ], columns=["Item", "Setting"])
    d.table(par, "Screening parameters", small=True)
    eqn(d, "&tau;* = &minus;(&Delta;r &middot; &Delta;v) / |&Delta;v|<sup>2</sup>, &nbsp; miss = |&Delta;r + &Delta;v &tau;*| &nbsp;(&tau;* clipped to &plusmn;1 s)", 7)
    d.table(T("t12_conjunction_summary"), "Encounters under 5 km in the two 24-hour screenings", small=True)
    ce = T("t12_closest_encounters").head(10)
    d.table(ce[["name_a", "name_b", "kind", "miss_km", "rel_speed_kms", "alt_km"]].rename(columns={"name_a": "Object A", "name_b": "Object B",
            "kind": "Kind", "miss_km": "Miss (km)", "rel_speed_kms": "Speed (km/s)", "alt_km": "Altitude (km)"}), "Closest crossing encounters", small=True)
    d.p("Limits: public GP elements carry about 1 km error, growing with time from epoch, so miss distances are screening values; no "
        "covariance or collision probability is computed; objects manoeuvre; the full debris catalogue (about 12,500 pieces) is not "
        "publicly mirrored, so screening B covers the four largest clouds only; the catalogue excludes objects smaller than about 10 cm.")

    d.chapter("Forecast, Limitations and Reproducibility")
    d.section("6.1", "Forecast")
    d.p("Holt's damped additive trend on log payloads in orbit, 2000-2026 (Hyndman and Athanasopoulos, 2021):")
    eqn(d, "&ell;<sub>t</sub> = &alpha;y<sub>t</sub> + (1&minus;&alpha;)(&ell;<sub>t&minus;1</sub> + &phi;b<sub>t&minus;1</sub>), &nbsp; b<sub>t</sub> = &beta;(&ell;<sub>t</sub> &minus; &ell;<sub>t&minus;1</sub>) + (1&minus;&beta;)&phi;b<sub>t&minus;1</sub>", 8)
    d.p(f"80% interval from 2,000 simulated paths (seeded). Back-test: fit to 2000-2021, forecast 2022-2026, mean absolute percentage error "
        f"{M['fc_bt_mape']}%. 2030: {M['fc_2030_mid']:,} ({M['fc_2030_lo']:,}-{M['fc_2030_hi']:,}).")
    d.table(T("t8_scenarios_2030"), "Bottom-up scenarios for working satellites in 2030 (others grow 3 / 7 / 12% a year)", small=True)
    d.section("6.2", "Limitations and threats to validity")
    d.bullets([
        "The CDM census is a 2014 snapshot; growth after 2014 rests on the open catalogue and the UCS 2020 census (cross-checked).",
        "'Operational' in the catalogue is the maintainer's flag; some dead satellites may be flagged operational and vice versa.",
        "Military counts use names: a lower bound. The classifier's label is the registered user, itself imperfect for dual-use satellites.",
        "The collision-risk index is relative and ignores object size, manoeuvres and eccentric orbits spanning shells.",
        "The CDM space-weather periods are anonymised; the storm-sunspot relation uses their internal timing only.",
        "Scenario totals depend on announced plans; they are assumptions, stated in the table, not predictions of company behaviour.",
    ])
    d.section("6.3", "Reproducibility")
    d.p("Python 3.11.15; pandas 3.0.6; NumPy 2.3.5; SciPy 1.17.1; statsmodels 0.15.0; scikit-learn 1.9.1; ruptures 1.1.10; sgp4 2.27; "
        "Matplotlib 3.10.9. Commands: <i>cd analysis &amp;&amp; python run_all.py</i> (about 8 minutes, of which 7 are the close-approach "
        "screening), then <i>cd ../report &amp;&amp; python build_booklet.py &amp;&amp; python build_annex.py &amp;&amp; python build_word.py</i>. "
        "Random elements are seeded; two consecutive runs give identical metrics.")
    return d


def main():
    body = build()
    css_extra = """
body { font-size: 10.5pt; line-height: 1.38; }
h1.chapter { font-size: 13.5pt; margin: 16pt 0 8pt 0; page-break-before: auto; break-before: auto; border-top: 1.5pt solid #1f3b5c; padding-top: 7pt; page-break-after: avoid; }
table.tbl.small td, table.tbl.small th { padding: 2pt 4pt; }
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

        render(html_body, OUT / "_abody.pdf")
        bd = fitz.open(OUT / "_abody.pdf")
        pages = {}
        for i, pg_ in enumerate(bd):
            for mk in re.findall(r"@@([A-Z0-9_]+)@@", pg_.get_text()):
                pages.setdefault(mk, i + 1)
            hits = [w for w in pg_.get_text("words") if "@@" in w[4]]
            for w in hits:
                pg_.add_redact_annot(fitz.Rect(w[:4]), fill=False)
            if hits:
                pg_.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=fitz.PDF_REDACT_LINE_ART_NONE)
        toc = "".join(f'<tr class="l{lvl}"><td class="t">{lab}&nbsp;&nbsp;{title}</td><td class="pg">{pages.get(mid, "")}</td></tr>'
                      for mid, lvl, lab, title in body.sec)
        front = f"""<div class="titlepage" style="padding-top:14mm">
<div class="t3">COLLEGE OF DEFENCE MANAGEMENT &middot; DATATHON - 2026 &middot; THEME 6.1</div>
<div class="t1" style="margin-top:18pt">{TITLE}</div><div class="t2" style="margin-bottom:10pt">Technical Annex</div>
<div class="t3" style="font-size:10.5pt;max-width:82%;margin:0 auto 22pt auto">Methods, formulas, parameters, validation and limitations behind the
Commander's Edition. For assessors and analysts.</div></div>
<h1 style="text-align:center;font-size:13pt;margin-top:10pt">CONTENTS</h1><table class="toc">{toc}</table>"""
        front_doc = f"<!doctype html><html><head><meta charset='utf-8'>{style}</head><body>{front}</body></html>"
        render(front_doc, OUT / "_afront.pdf")
        WORD.mkdir(exist_ok=True)
        (WORD / "annex_front.html").write_text(front_doc.replace('<h1 style="text-align:center;font-size:13pt;margin-top:10pt">CONTENTS</h1>',
                                                                   '<div class="front pb"><h1>CONTENTS</h1>').replace("</table>", "</table></div>", 1))
        (WORD / "annex_body.html").write_text(html_body)
        br.close()
    fr = fitz.open(OUT / "_afront.pdf")
    doc = fitz.open()
    doc.insert_pdf(fr)
    doc.insert_pdf(bd)
    nf = len(fr)
    for i, pg_ in enumerate(doc):
        w, h = pg_.rect.width, pg_.rect.height
        label = roman(i + 1) if i < nf else str(i - nf + 1)
        pg_.insert_text((w / 2 - 6, h - 24), label, fontsize=9.5, fontname="times-roman")
        pg_.insert_text((57, 36), "CDM Datathon-2026  |  Theme 6.1  |  Project High Ground  |  Technical Annex", fontsize=7.2, fontname="helv",
                        color=(0.45, 0.45, 0.45))
        pg_.draw_line((57, 41), (w - 51, 41), color=(0.75, 0.75, 0.75), width=0.4)
    doc.set_metadata({"title": "Project High Ground - Technical Annex", "author": "Arjun Jayadev"})
    out = OUT / "Datathon2026_Theme6.1_Technical_Annex.pdf"
    doc.save(out, garbage=4, deflate=True)
    for f in ("_abody.pdf", "_afront.pdf"):
        (OUT / f).unlink()
    print("pages:", len(doc), "->", out)


if __name__ == "__main__":
    main()
