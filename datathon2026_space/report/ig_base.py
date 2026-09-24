"""Icon helper and infographic CSS shared with the Theme 6.2 study (Font Awesome Free icons, CC BY 4.0)."""
import base64
import os
import re
from pathlib import Path

import fontawesomefree

ICON_DIR = Path(os.path.dirname(fontawesomefree.__file__)) / "static/fontawesomefree/svgs/solid"
NAVY, ORANGE, RED, AMBER, GREEN, BLUE, GREY = "#1f3b5c", "#eb6834", "#c62828", "#e08a00", "#2e7d32", "#2a78d6", "#6b6a66"


# Load a Font Awesome SVG icon by name and colour it.
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
