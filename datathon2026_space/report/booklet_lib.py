"""Shared engine for the Theme 6.1 booklet: numbering, figures, tables, styles and PDF rendering.

Same engine as the Theme 6.2 study (Doc class, print CSS, marker-based page numbering), so both submissions share
one look. Every number comes from data/metrics.json and every table from tables/*.csv.
"""
import base64
import html
import json
import re
from pathlib import Path

import pandas as pd
import pymupdf as fitz
from playwright.sync_api import sync_playwright

import story as ST

ROOT = Path(__file__).resolve().parents[1]
FIG, TAB, OUT = ROOT / "figures", ROOT / "tables", ROOT / "report"
WORD = OUT / "_html"
M = json.loads((ROOT / "data" / "metrics.json").read_text())
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

def pct(x, d=0):
    return f"{x * 100:.{d}f}%"


def n(x):
    return f"{x:,}"


# ------------------------------------------------------------------ numbering registries
# Doc collects the report as HTML pieces and numbers chapters, sections, figures and tables automatically.
# Each heading/figure/table gets a hidden marker so its page number can be found after printing.
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

    # New chapter: closes the previous one with its 'So what' box, restarts figure/table numbering,
    # and adds the story kicker and 'The story so far' box (from story.py).
    def chapter(self, title, letter=None):
        close = getattr(self, "closes", {}).get(self.ch) if self.ch else None
        if close and not letter and self.ch not in getattr(self, "_closed", set()) or (close and letter and self.ch not in getattr(self, "_closed", set())):
            self._closed = getattr(self, "_closed", set()) | {self.ch}
            what, nxt = close
            nx = f'<span class="next">Next: {nxt}</span>' if nxt else ""
            self.add(f'<div class="sowhat"><span class="lab">So what</span>{what}{nx}</div>')
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
        kick = getattr(self, "kickers", ST.KICKER)
        if self.ch in kick:
            self.add(f'<div class="kicker">{kick[self.ch]}</div>')
        op = getattr(self, "opens", {}).get(self.ch)
        if op:
            self.add(f'<div class="story"><span class="lab">The story so far</span>{op}</div>')

    # Numbered section heading (level 2 = x.y, level 3 = x.y.z).
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

    # Insert figures/<name>.png with a numbered caption and, if story.py has one, a 'What this shows' line.
    def fig(self, name, caption, width=86, source=None):
        self.fig_no += 1
        label = f"{self.pfx}.{self.fig_no}"
        mid = f"F{label.replace('.', '_')}"
        self.figs.append((mid, label, caption))
        data = base64.b64encode((FIG / f"{name}.png").read_bytes()).decode()
        src = f'<div class="src">Source: {source}</div>' if source else ""
        pl = f'<div class="plain"><b>What this shows:</b> {ST.PLAIN[name]}</div>' if name in ST.PLAIN else ""
        self.add(f'<figure><img src="data:image/png;base64,{data}" style="width:{width}%">'
                 f'<figcaption><span class="mk">@@{mid}@@ </span><b>Figure {label} :</b> {caption}</figcaption>{pl}{src}</figure>')
        return label

    # Insert an HTML infographic (from infographics.py) as a numbered figure.
    def html_fig(self, inner, caption):
        self.fig_no += 1
        label = f"{self.pfx}.{self.fig_no}"
        mid = f"F{label.replace('.', '_')}"
        self.figs.append((mid, label, caption))
        self.add(f'<figure>{inner}<figcaption><span class="mk">@@{mid}@@ </span><b>Figure {label} :</b> {caption}</figcaption></figure>')
        return label

    # Insert a pandas table as a numbered, styled HTML table (numbers formatted automatically).
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


# Read tables/<name>.csv (a result table written by the analysis stages).
def T(name):
    return pd.read_csv(TAB / f"{name}.csv")


# Print styling for the PDF: A4, Times-style body, navy headings, table and box styles.
CSS = """
@page { size: A4; margin: 24mm 22mm 22mm 26mm; }
* { box-sizing: border-box; }
body { font-family: 'Liberation Serif', 'Times New Roman', serif; font-size: 11pt; line-height: 1.38; color: #111; }
p { text-align: justify; margin: 0 0 8pt 0; }
h1.chapter { page-break-before: always; font-size: 15pt; margin: 0 0 14pt 0; }
h2 { font-size: 12.5pt; margin: 14pt 0 6pt 0; page-break-after: avoid; }
h3 { font-size: 12pt; font-style: italic; margin: 10pt 0 4pt 0; page-break-after: avoid; }
ul { margin: 0 0 8pt 0; padding-left: 22pt; } li { text-align: justify; margin-bottom: 3pt; }
ul.alpha { list-style: lower-alpha; }
figure { margin: 6pt 0 9pt 0; text-align: center; page-break-inside: avoid; }
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
.rag { font-weight: bold; padding: 1pt 5pt; border-radius: 2pt; color: #fff; }
.rag.red { background: #c62828; } .rag.amber { background: #e08a00; } .rag.green { background: #2e7d32; }
.bluf { border: 1.2pt solid #1f3b5c; padding: 8pt 10pt; margin-bottom: 8pt; background: #eef2f7; font-size: 11pt; text-align: justify; }
.es h2 { font-size: 11.5pt; margin: 8pt 0 3pt 0; } .es p, .es li { font-size: 10.5pt; line-height: 1.38; margin-bottom: 3pt; }
.kicker { font-family: 'Liberation Sans', sans-serif; font-size: 9pt; color: #9a4a3a; text-transform: uppercase; letter-spacing: .6pt; margin: -8pt 0 8pt 0; font-weight: bold; }
.story { border: .8pt solid #d9c7a3; background: #fbf6ec; border-radius: 4pt; padding: 7pt 10pt; margin: 4pt 0 12pt 0; font-size: 11pt; text-align: justify; page-break-inside: avoid; }
.story .lab, .sowhat .lab { font-family: 'Liberation Sans', sans-serif; font-size: 8pt; font-weight: bold; letter-spacing: .5pt; text-transform: uppercase; color: #9a4a3a; display: block; margin-bottom: 2pt; }
.sowhat { border: .8pt solid #1f3b5c; background: #eef2f7; border-radius: 4pt; padding: 7pt 10pt; margin: 14pt 0 4pt 0; font-size: 11pt; text-align: justify; page-break-inside: avoid; }
.sowhat .lab { color: #1f3b5c; } .sowhat .next { display: block; margin-top: 4pt; font-style: italic; color: #1f3b5c; }
.plain { font-family: 'Liberation Sans', sans-serif; font-size: 8.8pt; color: #333; background: #f7f7f4; border-left: 3pt solid #9a4a3a; padding: 3pt 7pt; margin: 4pt auto 0 auto; text-align: left; max-width: 94%; }
.code { font-family: 'Liberation Mono', monospace; font-size: 8pt; line-height: 1.3; background: #f6f6f4; border: 0.5pt solid #ddd; padding: 6pt; white-space: pre-wrap; text-align: left; }
"""

def roman(k):
    vals = [(10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]
    out = ""
    for v, s in vals:
        while k >= v:
            out += s
            k -= v
    return out
