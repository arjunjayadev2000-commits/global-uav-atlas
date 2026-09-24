"""Stage 10 - base artwork for the report infographics (margin-free theatre map with sea routes and ports)."""

# =====================================================================================================
# ANNOTATED SOURCE - Stage 10: base map for the theatre infographic
# -----------------------------------------------------------------------------------------------------
# Draws a margin-free map (30-100 E, 5 S-32 N) with schematic sea lines of communication into India and the
# Natural Earth ports. The report's HTML infographic (report/infographics.py) places labelled call-outs on it
# by latitude/longitude, which is why the map must have no margins.
# =====================================================================================================

import json

import matplotlib.pyplot as plt
from mpl_toolkits.basemap import Basemap

from common import FIG, ROOT

print("Stage 10: infographic assets")
# The map spans exactly lon 30-100 E, lat 5 S-32 N with no margins, so HTML callouts can be placed by coordinates.
fig = plt.figure(figsize=(9.6, 5.074))
ax = fig.add_axes([0, 0, 1, 1])
m = Basemap(projection="cyl", llcrnrlat=-5, urcrnrlat=32, llcrnrlon=30, urcrnrlon=100, resolution="l", ax=ax)
m.drawmapboundary(fill_color="#dfeaf3", linewidth=0)
m.fillcontinents(color="#f4f2ec", lake_color="#dfeaf3")
m.drawcoastlines(linewidth=0.4, color="#9aa5ae")
m.drawcountries(linewidth=0.3, color="#c3c2b7")
# schematic sea lines of communication into India
# Four schematic sea routes (lon, lat way-points): Hormuz to Mumbai and to Kandla, Bab-el-Mandeb to Kochi, and
# the Red Sea to Suez.
routes = [[(56.3, 26.4), (58.5, 23.5), (65, 21.5), (72.6, 19.0)], [(56.3, 26.4), (60, 24.0), (69.8, 22.6)],
          [(43.4, 12.6), (51, 12.8), (62, 11.5), (75.8, 9.9)], [(43.4, 12.6), (38.0, 20.5), (33.5, 27.5)]]
for r in routes:
    xs, ys = zip(*r)
    ax.plot(xs, ys, color="#1f3b5c", lw=1.1, ls=(0, (4, 3)), alpha=0.7)
# Port positions from Natural Earth (open data), drawn as small dots.
ports = json.load(open(ROOT / "data/open/ne_ports_indian_ocean.geojson"))      # Natural Earth ports
px = [f["geometry"]["coordinates"] for f in ports["features"]]
ax.scatter([p[0] for p in px], [p[1] for p in px], s=4, color="#52514e", zorder=3)
ax.set_axis_off()
fig.savefig(FIG / "base_theatre.png", dpi=200, facecolor="#dfeaf3")
plt.close(fig)
print("  fig -> base_theatre")
