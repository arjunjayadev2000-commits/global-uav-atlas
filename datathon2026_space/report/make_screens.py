"""Capture 'software used' screenshots for the submission: the real pipeline run log and a real code excerpt,
rendered as terminal / editor windows with headless Chromium."""

# =====================================================================================================
# ANNOTATED SOURCE - make_screens.py: 'software used' screenshots for Annex C
# -----------------------------------------------------------------------------------------------------
# Renders the real pipeline log (data/pipeline_run.log) as a terminal window and a real code excerpt as an
# editor window,
# using headless Chromium, and saves them as figures/screen_pipeline.png and figures/screen_code.png.
# =====================================================================================================

import html
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "figures"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
WIN = """<html><head><style>
body {{ margin:0; background:#fff; font-family:'Liberation Mono',monospace; }}
.w {{ width:1040px; border-radius:8px; overflow:hidden; box-shadow:0 2px 10px rgba(0,0,0,.35); margin:10px; }}
.bar {{ background:#3a3f4b; color:#cfd3dc; font:12px 'Liberation Sans',sans-serif; padding:7px 12px; }}
.bar i {{ display:inline-block; width:11px; height:11px; border-radius:50%; margin-right:6px; vertical-align:middle; }}
pre {{ margin:0; padding:12px 14px; background:{bg}; color:{fg}; font-size:12.5px; line-height:1.42; white-space:pre-wrap; }}
.ln {{ color:#6b7280; }} .kw {{ color:#c792ea; }} .st {{ color:#c3e88d; }} .cm {{ color:#7f8c98; font-style:italic; }} .ok {{ color:#89ddff; }}
</style></head><body><div class="w"><div class="bar"><i style="background:#ff5f57"></i><i style="background:#febc2e"></i>
<i style="background:#28c840"></i>&nbsp; {title}</div><pre>{body}</pre></div></body></html>"""


# Render one HTML window and save a cropped PNG screenshot.
def shot(page, html_str, out):
    page.set_content(html_str)
    page.locator(".w").screenshot(path=str(out))
    print("  screen ->", out.name)


log = (ROOT / "data/pipeline_run.log").read_text().splitlines()
keep = [l for l in log if l.startswith("Stage") or "rows" in l or "fig ->" in l] + [f"  ... {sum('->' in l for l in log)} figures and tables written"]
term = ("<span class='ok'>$</span> python analysis/run_all.py\n" +
        "\n".join(html.escape(l) if not l.startswith("Stage") else f"<span class='ok'>{html.escape(l)}</span>" for l in keep) +
        "\n<span class='ok'>$</span>")

src = (ROOT / "analysis/04_congestion.py").read_text().splitlines()
start = next(i for i, l in enumerate(src) if l.startswith("W = 25"))
code = src[start - 1: start + 17]


# Very small Python syntax highlighter for the code screenshot (keywords, strings, comments).
def hl(line):
    s = html.escape(line)
    if s.strip().startswith("#") or s.strip().startswith('"""') or s.strip().startswith("because"):
        return f"<span class='cm'>{s}</span>"
    for k in ("def ", "return ", "for ", "if ", "in ", "and "):
        s = s.replace(k, f"<span class='kw'>{k}</span>")
    return s


body = "\n".join(f"<span class='ln'>{start + i:4d}</span>  {hl(l)}" for i, l in enumerate(code))
with sync_playwright() as p:
    br = p.chromium.launch(executable_path=CHROME)
    pg = br.new_page(device_scale_factor=2)
    shot(pg, WIN.format(bg="#1e1e1e", fg="#e5e5e5", title="Terminal - Theme 6.1 - full pipeline run (raw data to booklet)", body=term),
         FIG / "screen_pipeline.png")
    shot(pg, WIN.format(bg="#263238", fg="#eeffff", title="analysis/04_congestion.py - altitude shells and the collision-risk index", body=body),
         FIG / "screen_code.png")
    br.close()
