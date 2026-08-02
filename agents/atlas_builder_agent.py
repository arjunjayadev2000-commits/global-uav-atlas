"""Atlas builder: the printable PDF and the interactive HTML edition.

Both editions show the same simple entry format required by the specification::

    | Photo | UAV Name | Country of Origin |

Sections are Military, Civilian & Commercial, Dual-use, Research & Experimental,
followed by an appendix of records that are still unverified, and the photo
attribution appendix.  Within a section entries sort by country, then
manufacturer, then platform name, then variant.

The PDF is produced with ReportLab: real text (searchable), embedded images,
page numbers, a table of contents, a country index, an alphabetical index and a
generation date.  Every entry row is its own flowable so nothing is ever clipped
and so exact page numbers can be captured for the indexes.
"""

from __future__ import annotations

import html
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.db import connect, query
from app.logging import AgentLogger, utc_now
from app.models import (
    DOMAIN_CIVIL,
    DOMAIN_DUAL,
    DOMAIN_MILITARY,
    DOMAIN_RESEARCH,
    DOMAIN_UNKNOWN,
    VERIFICATION_NEEDS,
)
from app.utils import clean_text, country_iso3, slugify

LOG = AgentLogger("atlas_builder_agent")
AGENT = "atlas_builder_agent"

TITLE = "Global UAV Visual Atlas 2026"
SUBTITLE = "Largest defensible consolidated registry generated from the configured sources"

SECTIONS: list[tuple[str, tuple[str, ...]]] = [
    ("Military UAVs", (DOMAIN_MILITARY,)),
    ("Civilian and Commercial UAVs", (DOMAIN_CIVIL,)),
    ("Dual-use UAVs", (DOMAIN_DUAL,)),
    ("Research and Experimental UAVs", (DOMAIN_RESEARCH, DOMAIN_UNKNOWN)),
]

PLACEHOLDER_NAME = "_no_verified_image.png"


@dataclass(slots=True)
class Entry:
    platform_id: int
    public_id: str
    name: str
    country: str
    manufacturer: str
    domain: str
    category: str
    variant: str
    verification_status: str
    image_path: str
    thumbnail_path: str
    attribution: str
    license_name: str
    license_url: str
    source_page_url: str
    identity_verdict: str
    identity_confidence: float

    @property
    def has_image(self) -> bool:
        return bool(self.image_path) and Path(self.image_path).is_file()


@dataclass(slots=True)
class AtlasData:
    entries: list[Entry] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def by_section(self) -> list[tuple[str, list[Entry]]]:
        out: list[tuple[str, list[Entry]]] = []
        for title, domains in SECTIONS:
            rows = [e for e in self.entries if e.domain in domains]
            if rows:
                out.append((title, sort_entries(rows)))
        return out

    def unverified(self) -> list[Entry]:
        return sort_entries(
            [e for e in self.entries if e.verification_status == VERIFICATION_NEEDS]
        )


def sort_entries(entries: list[Entry]) -> list[Entry]:
    return sorted(
        entries,
        key=lambda e: (
            e.country == "Unknown",
            e.country.lower(),
            e.manufacturer.lower(),
            e.name.lower(),
            e.variant.lower(),
        ),
    )


ENTRIES_SQL = """
SELECT p.id, p.public_id, p.canonical_name, p.domain, COALESCE(p.category,'') AS category,
       p.verification_status,
       COALESCE(c.name,'Unknown') AS country,
       COALESCE(m.name,'') AS manufacturer,
       COALESCE(v.variant_name,'') AS variant,
       COALESCE(i.atlas_path,'') AS atlas_path,
       COALESCE(i.thumbnail_path,'') AS thumbnail_path,
       COALESCE(i.attribution_text,'') AS attribution_text,
       COALESCE(i.license_name,'') AS license_name,
       COALESCE(i.license_url,'') AS license_url,
       COALESCE(i.source_page_url,'') AS source_page_url,
       COALESCE(i.identity_verdict,'no image') AS identity_verdict,
       COALESCE(i.identity_confidence,0) AS identity_confidence
FROM platforms p
LEFT JOIN countries c ON c.id = p.country_id
LEFT JOIN manufacturers m ON m.id = p.manufacturer_id
LEFT JOIN images i ON i.platform_id = p.id AND i.selected_for_atlas = 1
LEFT JOIN platform_variants v ON v.platform_id = p.id
WHERE p.is_merged_into IS NULL
GROUP BY p.id
"""


def load_atlas_data() -> AtlasData:
    from agents.export_agent import coverage_statistics

    conn = connect()
    entries = [
        Entry(
            platform_id=int(r["id"]),
            public_id=r["public_id"],
            name=clean_text(r["canonical_name"]),
            country=clean_text(r["country"]) or "Unknown",
            manufacturer=clean_text(r["manufacturer"]),
            domain=clean_text(r["domain"]) or DOMAIN_UNKNOWN,
            category=clean_text(r["category"]),
            variant=clean_text(r["variant"]),
            verification_status=r["verification_status"],
            image_path=r["atlas_path"],
            thumbnail_path=r["thumbnail_path"],
            attribution=r["attribution_text"],
            license_name=r["license_name"],
            license_url=r["license_url"],
            source_page_url=r["source_page_url"],
            identity_verdict=r["identity_verdict"],
            identity_confidence=float(r["identity_confidence"] or 0),
        )
        for r in query(ENTRIES_SQL, conn=conn)
    ]
    return AtlasData(entries=entries, stats=coverage_statistics())


# ---------------------------------------------------------------------------
# Placeholder artwork
# ---------------------------------------------------------------------------


def ensure_placeholder() -> Path:
    """A neutral 'no verified image' tile.

    Deliberately not a photograph and deliberately not AI-generated artwork: the
    atlas must never imply an image exists where none was verified.
    """
    settings = get_settings()
    path = settings.paths.images / PLACEHOLDER_NAME
    if path.is_file():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image, ImageDraw

        width, height = 640, 400
        image = Image.new("RGB", (width, height), (238, 240, 244))
        draw = ImageDraw.Draw(image)
        draw.rectangle([8, 8, width - 8, height - 8], outline=(176, 182, 194), width=3)
        for offset in range(-height, width, 46):
            draw.line([(offset, height), (offset + height, 0)], fill=(226, 229, 236), width=2)
        text = "NO VERIFIED IMAGE"
        try:
            bbox = draw.textbbox((0, 0), text)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        except AttributeError:  # very old Pillow
            tw, th = 150, 12
        draw.rectangle(
            [width / 2 - tw / 2 - 16, height / 2 - th / 2 - 12,
             width / 2 + tw / 2 + 16, height / 2 + th / 2 + 12],
            fill=(255, 255, 255),
            outline=(176, 182, 194),
        )
        draw.text((width / 2 - tw / 2, height / 2 - th / 2), text, fill=(88, 96, 112))
        image.save(path, "PNG", optimize=True)
    except Exception as exc:  # noqa: BLE001 - the atlas must still build
        LOG.warning("could not generate placeholder image: %s", exc)
    return path


# ---------------------------------------------------------------------------
# HTML edition
# ---------------------------------------------------------------------------


def _relative_to_output(path: str) -> str:
    if not path:
        return ""
    settings = get_settings()
    try:
        return str(Path(path).resolve().relative_to(settings.paths.root.resolve()))
    except ValueError:
        return path
    finally:
        pass


def build_html(data: AtlasData, destination: Path | None = None) -> Path:
    settings = get_settings()
    target = destination or (settings.paths.output / "Global_UAV_Visual_Atlas_2026.html")
    placeholder = ensure_placeholder()
    placeholder_rel = "../" + _relative_to_output(str(placeholder))

    payload = []
    for section_title, entries in data.by_section():
        for entry in entries:
            image = (
                "../" + _relative_to_output(entry.thumbnail_path or entry.image_path)
                if entry.has_image
                else placeholder_rel
            )
            payload.append(
                {
                    "section": section_title,
                    "name": entry.name,
                    "country": entry.country,
                    "iso3": country_iso3(entry.country) or "",
                    "manufacturer": entry.manufacturer,
                    "category": entry.category,
                    "domain": entry.domain,
                    "status": entry.verification_status,
                    "image": image,
                    "hasImage": entry.has_image,
                    "attribution": entry.attribution,
                    "license": entry.license_name,
                    "licenseUrl": entry.license_url,
                    "sourcePage": entry.source_page_url,
                    "identity": entry.identity_verdict,
                }
            )

    stats = data.stats
    generated = datetime.now(timezone.utc).strftime("%d %B %Y %H:%M UTC")
    document = _HTML_TEMPLATE.format(
        title=html.escape(TITLE),
        subtitle=html.escape(SUBTITLE),
        generated=generated,
        platforms=stats.get("canonical_platforms", len(payload)),
        countries=stats.get("countries_represented", 0),
        manufacturers=stats.get("manufacturers", 0),
        images=stats["images"]["selected_for_atlas"] if stats.get("images") else 0,
        coverage=stats["images"]["coverage_pct"] if stats.get("images") else 0,
        unresolved=stats.get("unresolved_open", 0),
        data_json=json.dumps(payload, ensure_ascii=False),
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(document, encoding="utf-8")
    LOG.info("HTML atlas written: %s (%d entries)", target, len(payload))
    LOG.event("html_atlas_built", path=str(target), entries=len(payload))
    return target


_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{
    --bg: #f6f7f9; --panel: #ffffff; --ink: #14181f; --muted: #5b6472;
    --line: #e0e4ea; --accent: #1f3864; --chip: #eef1f6;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#12151a; --panel:#1a1f27; --ink:#e8ecf2; --muted:#9aa5b5;
             --line:#2a313c; --accent:#7aa2e3; --chip:#232a34; }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
         font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }}
  header {{ background:var(--accent); color:#fff; padding:28px 20px; }}
  header h1 {{ margin:0 0 6px; font-size:26px; letter-spacing:.2px; }}
  header p {{ margin:0; opacity:.9; font-size:14px; }}
  .wrap {{ max-width:1180px; margin:0 auto; padding:0 16px 64px; }}
  .stats {{ display:grid; gap:10px; grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
            margin:18px 0; }}
  .stat {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:12px 14px; }}
  .stat b {{ display:block; font-size:22px; }}
  .stat span {{ color:var(--muted); font-size:12px; text-transform:uppercase; letter-spacing:.06em; }}
  .controls {{ position:sticky; top:0; z-index:5; background:var(--bg); padding:12px 0;
               border-bottom:1px solid var(--line); display:grid; gap:8px;
               grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); }}
  input, select {{ width:100%; padding:9px 11px; border:1px solid var(--line); border-radius:8px;
                   background:var(--panel); color:var(--ink); font-size:14px; }}
  .count {{ color:var(--muted); font-size:13px; margin:10px 2px; }}
  .tablewrap {{ overflow-x:auto; background:var(--panel); border:1px solid var(--line);
                border-radius:12px; }}
  table {{ border-collapse:collapse; width:100%; min-width:640px; }}
  th, td {{ padding:10px 12px; border-bottom:1px solid var(--line); text-align:left;
            vertical-align:middle; }}
  th {{ position:sticky; top:0; background:var(--panel); cursor:pointer; user-select:none;
        font-size:12px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); }}
  th[aria-sort="ascending"]::after {{ content:" \\2191"; }}
  th[aria-sort="descending"]::after {{ content:" \\2193"; }}
  td.photo {{ width:180px; }}
  img {{ width:160px; height:104px; object-fit:cover; border-radius:6px; background:var(--chip);
         border:1px solid var(--line); display:block; }}
  .name {{ font-weight:600; }}
  .meta {{ color:var(--muted); font-size:12.5px; margin-top:2px; }}
  .chip {{ display:inline-block; background:var(--chip); border-radius:999px; padding:1px 9px;
           font-size:11.5px; color:var(--muted); margin-right:4px; }}
  .sec {{ margin:28px 0 8px; font-size:18px; }}
  a {{ color:var(--accent); }}
  footer {{ color:var(--muted); font-size:13px; padding:24px 0; }}
  .noimg {{ opacity:.55; }}
</style>
</head>
<body>
<header>
  <h1>{title}</h1>
  <p>{subtitle} — generated {generated}</p>
</header>
<div class="wrap">
  <div class="stats">
    <div class="stat"><b>{platforms}</b><span>Canonical platforms</span></div>
    <div class="stat"><b>{countries}</b><span>Countries of origin</span></div>
    <div class="stat"><b>{manufacturers}</b><span>Manufacturers</span></div>
    <div class="stat"><b>{images}</b><span>Verified images</span></div>
    <div class="stat"><b>{coverage}%</b><span>Image coverage</span></div>
    <div class="stat"><b>{unresolved}</b><span>Open unresolved items</span></div>
  </div>

  <div class="controls">
    <input id="q" type="search" placeholder="Search name, manufacturer, country…" autocomplete="off">
    <select id="fCountry"><option value="">All countries</option></select>
    <select id="fManufacturer"><option value="">All manufacturers</option></select>
    <select id="fCategory"><option value="">All categories</option></select>
    <select id="fDomain"><option value="">All domains</option></select>
  </div>
  <div class="count" id="count"></div>
  <div id="out"></div>
  <footer>
    Photographs are reproduced under the licence recorded for each file; the full licence
    chain is in <code>output/photo_attribution.csv</code>. Entries marked
    “no verified image” had no image that passed licence, resolution and identity checks.
  </footer>
</div>
<script>
const DATA = {data_json};
const el = (id) => document.getElementById(id);
let sortKey = null, sortDir = 1;

function fill(select, key) {{
  const values = [...new Set(DATA.map(r => r[key]).filter(Boolean))].sort();
  for (const value of values) {{
    const option = document.createElement('option');
    option.value = value; option.textContent = value;
    select.appendChild(option);
  }}
}}
fill(el('fCountry'), 'country');
fill(el('fManufacturer'), 'manufacturer');
fill(el('fCategory'), 'category');
fill(el('fDomain'), 'domain');

function esc(value) {{
  return String(value == null ? '' : value).replace(/[&<>"']/g,
    ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}})[ch]);
}}

function filtered() {{
  const q = el('q').value.trim().toLowerCase();
  const country = el('fCountry').value, manufacturer = el('fManufacturer').value;
  const category = el('fCategory').value, domain = el('fDomain').value;
  let rows = DATA.filter(r =>
    (!country || r.country === country) &&
    (!manufacturer || r.manufacturer === manufacturer) &&
    (!category || r.category === category) &&
    (!domain || r.domain === domain) &&
    (!q || (r.name + ' ' + r.manufacturer + ' ' + r.country + ' ' + r.category).toLowerCase().includes(q))
  );
  if (sortKey) {{
    rows = rows.slice().sort((a, b) =>
      String(a[sortKey]).localeCompare(String(b[sortKey]), undefined, {{numeric:true}}) * sortDir);
  }}
  return rows;
}}

function render() {{
  const rows = filtered();
  el('count').textContent = rows.length + ' of ' + DATA.length + ' entries';
  const groups = new Map();
  for (const row of rows) {{
    if (!groups.has(row.section)) groups.set(row.section, []);
    groups.get(row.section).push(row);
  }}
  let html = '';
  for (const [section, items] of groups) {{
    html += '<h2 class="sec">' + esc(section) + ' <span class="chip">' + items.length + '</span></h2>';
    html += '<div class="tablewrap"><table><thead><tr>' +
      '<th data-k="">Photo</th><th data-k="name">UAV Name</th>' +
      '<th data-k="country">Country of Origin</th></tr></thead><tbody>';
    for (const row of items) {{
      const credit = row.attribution
        ? '<div class="meta">' + esc(row.license || 'licence recorded') +
          (row.sourcePage ? ' · <a href="' + esc(row.sourcePage) + '" rel="noopener noreferrer nofollow">source</a>' : '') +
          '</div>'
        : '<div class="meta noimg">no verified image</div>';
      html += '<tr><td class="photo"><img loading="lazy" decoding="async" src="' +
        esc(row.image) + '" alt="' + esc(row.name) + '">' + credit + '</td>' +
        '<td><div class="name">' + esc(row.name) + '</div><div class="meta">' +
        (row.manufacturer ? esc(row.manufacturer) + ' · ' : '') + esc(row.category || row.domain) +
        ' · <span class="chip">' + esc(row.status) + '</span></div></td>' +
        '<td>' + esc(row.country) + (row.iso3 ? ' <span class="chip">' + esc(row.iso3) + '</span>' : '') +
        '</td></tr>';
    }}
    html += '</tbody></table></div>';
  }}
  el('out').innerHTML = html || '<p>No entries match the current filters.</p>';
  document.querySelectorAll('th[data-k]').forEach(th => {{
    th.setAttribute('aria-sort', th.dataset.k && th.dataset.k === sortKey
      ? (sortDir === 1 ? 'ascending' : 'descending') : 'none');
    th.onclick = () => {{
      if (!th.dataset.k) return;
      if (sortKey === th.dataset.k) sortDir = -sortDir; else {{ sortKey = th.dataset.k; sortDir = 1; }}
      render();
    }};
  }});
}}

for (const id of ['q','fCountry','fManufacturer','fCategory','fDomain']) {{
  el(id).addEventListener('input', render);
}}
render();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# PDF edition
# ---------------------------------------------------------------------------


def build_pdf(data: AtlasData, destination: Path | None = None) -> Path | None:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            BaseDocTemplate,
            Frame,
            Image as RLImage,
            PageBreak,
            PageTemplate,
            Paragraph,
            Spacer,
            Table,
            TableStyle,
        )
        from reportlab.platypus.tableofcontents import TableOfContents
    except ImportError:
        LOG.error("reportlab is not installed - cannot build the PDF atlas")
        return None

    settings = get_settings()
    target = destination or (settings.paths.output / "Global_UAV_Visual_Atlas_2026.pdf")
    target.parent.mkdir(parents=True, exist_ok=True)
    placeholder = ensure_placeholder()

    styles = getSampleStyleSheet()
    style_title = ParagraphStyle(
        "AtlasTitle", parent=styles["Title"], fontSize=26, leading=30, spaceAfter=10
    )
    style_sub = ParagraphStyle(
        "AtlasSub", parent=styles["Normal"], fontSize=11.5, leading=15,
        alignment=TA_CENTER, textColor=colors.HexColor("#44506a"),
    )
    style_h1 = ParagraphStyle(
        "AtlasH1", parent=styles["Heading1"], fontSize=17, leading=21,
        spaceBefore=6, spaceAfter=8, textColor=colors.HexColor("#1f3864"),
    )
    style_h2 = ParagraphStyle(
        "AtlasH2", parent=styles["Heading2"], fontSize=12.5, leading=16,
        spaceBefore=8, spaceAfter=4, textColor=colors.HexColor("#24406e"),
    )
    style_name = ParagraphStyle("EntryName", parent=styles["Normal"], fontSize=10.5, leading=13.5)
    style_meta = ParagraphStyle(
        "EntryMeta", parent=styles["Normal"], fontSize=8, leading=10,
        textColor=colors.HexColor("#5b6472"),
    )
    style_cell = ParagraphStyle("Cell", parent=styles["Normal"], fontSize=10, leading=13)
    style_small = ParagraphStyle("Small", parent=styles["Normal"], fontSize=8, leading=10.5)
    style_toc1 = ParagraphStyle("TOC1", parent=styles["Normal"], fontSize=11, leading=16)
    style_toc2 = ParagraphStyle("TOC2", parent=styles["Normal"], fontSize=9.5, leading=13, leftIndent=14)

    page_width, page_height = A4
    margin = 16 * mm
    col_photo, col_name = 52 * mm, 78 * mm
    col_country = page_width - 2 * margin - col_photo - col_name
    col_widths = [col_photo, col_name, col_country]

    index_pages: dict[str, int] = {}
    country_pages: dict[str, set[int]] = defaultdict(set)

    class AtlasDoc(BaseDocTemplate):
        def afterFlowable(self, flowable: Any) -> None:  # noqa: N802 - ReportLab API
            entry = getattr(flowable, "_atlas_entry", None)
            if entry is not None:
                page = self.page
                index_pages.setdefault(entry[0], page)
                country_pages[entry[1]].add(page)
                return
            heading = getattr(flowable, "_toc_level", None)
            if heading is not None:
                text = getattr(flowable, "_toc_text", "")
                # 3-tuple form: a plain page reference. The 4-tuple form would
                # emit an internal hyperlink and require a matching bookmark
                # destination for every heading.
                self.notify("TOCEntry", (heading, text, self.page))

    def decorate(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#7c8698"))
        canvas.drawString(margin, 10 * mm, TITLE)
        canvas.drawRightString(page_width - margin, 10 * mm, f"Page {canvas.getPageNumber()}")
        canvas.setStrokeColor(colors.HexColor("#dfe4ec"))
        canvas.line(margin, 13 * mm, page_width - margin, 13 * mm)
        canvas.restoreState()

    frame = Frame(
        margin, 16 * mm, page_width - 2 * margin, page_height - margin - 20 * mm, id="body"
    )
    doc = AtlasDoc(
        str(target),
        pagesize=A4,
        title=TITLE,
        author="Global UAV Visual Atlas pipeline",
        subject=SUBTITLE,
        creator="global-uav-atlas",
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=16 * mm,
    )
    doc.addPageTemplates([PageTemplate(id="atlas", frames=[frame], onPage=decorate)])

    def heading(text: str, level: int = 0, key: str | None = None) -> Any:
        style = style_h1 if level == 0 else style_h2
        para = Paragraph(text, style)
        para._toc_level = level  # type: ignore[attr-defined]
        para._toc_text = text  # type: ignore[attr-defined]
        para._toc_key = key or slugify(text)  # type: ignore[attr-defined]
        return para

    def header_row() -> Any:
        table = Table(
            [[Paragraph("<b>Photo</b>", style_small),
              Paragraph("<b>UAV Name</b>", style_small),
              Paragraph("<b>Country of Origin</b>", style_small)]],
            colWidths=col_widths,
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef1f7")),
                    ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9d1de")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9d1de")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        return table

    def entry_row(entry: Entry) -> Any:
        path = Path(entry.image_path) if entry.has_image else placeholder
        image_flowable: Any
        try:
            image_flowable = RLImage(str(path))
            aspect = (image_flowable.imageHeight or 1) / (image_flowable.imageWidth or 1)
            width = col_photo - 10
            image_flowable.drawWidth = width
            image_flowable.drawHeight = min(width * aspect, 30 * mm)
            if image_flowable.drawHeight == 30 * mm:
                image_flowable.drawWidth = min(width, (30 * mm) / aspect)
        except Exception as exc:  # noqa: BLE001 - never emit a broken image
            LOG.warning("image unusable for %s (%s): %s", entry.name, path, exc)
            image_flowable = Paragraph("no verified image", style_meta)

        meta_bits = [b for b in (entry.manufacturer, entry.category) if b]
        name_cell = [Paragraph(html.escape(entry.name), style_name)]
        if meta_bits:
            name_cell.append(Paragraph(html.escape(" · ".join(meta_bits)), style_meta))
        if not entry.has_image:
            name_cell.append(Paragraph("no verified image", style_meta))

        iso = country_iso3(entry.country)
        country_cell = [
            Paragraph(html.escape(entry.country) + (f" ({iso})" if iso else ""), style_cell)
        ]

        table = Table([[image_flowable, name_cell, country_cell]], colWidths=col_widths)
        table.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#dfe4ec")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dfe4ec")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("ALIGN", (0, 0), (0, 0), "CENTER"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        table._atlas_entry = (entry.name, entry.country)  # type: ignore[attr-defined]
        return table

    story: list[Any] = []
    stats = data.stats

    # --- cover ---------------------------------------------------------
    story.append(Spacer(1, 42 * mm))
    story.append(Paragraph(TITLE, style_title))
    story.append(Paragraph(SUBTITLE, style_sub))
    story.append(Spacer(1, 10 * mm))
    story.append(
        Paragraph(
            f"Generated {datetime.now(timezone.utc).strftime('%d %B %Y %H:%M UTC')}", style_sub
        )
    )
    story.append(Spacer(1, 14 * mm))
    cover_stats = [
        ["Canonical platforms", str(stats.get("canonical_platforms", ""))],
        ["Countries of origin", str(stats.get("countries_represented", ""))],
        ["Manufacturers / design organisations", str(stats.get("manufacturers", ""))],
        ["Raw source records", str(stats.get("raw_source_records", ""))],
        ["Sources cited", str(stats.get("sources", ""))],
        ["Images verified and embedded", str(stats.get("images", {}).get("selected_for_atlas", 0))],
        ["Open unresolved items", str(stats.get("unresolved_open", ""))],
    ]
    cover_table = Table(cover_stats, colWidths=[95 * mm, 40 * mm], hAlign="CENTER")
    cover_table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#c9d1de")),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dfe4ec")),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(cover_table)
    story.append(Spacer(1, 12 * mm))
    story.append(
        Paragraph(
            "This atlas is the largest defensible consolidated registry generated from the "
            "configured sources. It is not a claim that every drone ever built is included.",
            style_small,
        )
    )
    story.append(PageBreak())

    # --- table of contents ---------------------------------------------
    story.append(Paragraph("Table of contents", style_h1))
    toc = TableOfContents()
    toc.levelStyles = [style_toc1, style_toc2]
    story.append(toc)
    story.append(PageBreak())

    # --- sections -------------------------------------------------------
    for section_title, entries in data.by_section():
        story.append(heading(f"{section_title} ({len(entries)})", 0))
        current_country = None
        for entry in entries:
            if entry.country != current_country:
                current_country = entry.country
                story.append(heading(f"{section_title} — {current_country}", 1))
                story.append(header_row())
            story.append(entry_row(entry))
        story.append(PageBreak())

    # --- unverified appendix -------------------------------------------
    unverified = data.unverified()
    if unverified:
        story.append(heading(f"Appendix A — Unresolved or unverified records ({len(unverified)})", 0))
        story.append(
            Paragraph(
                "These records are included for completeness but did not meet the evidence "
                "threshold for verification: they rest on a single source, an unresolved "
                "country of origin, or discovery-only material. They are marked "
                "“Needs Verification” throughout the database.",
                style_small,
            )
        )
        story.append(Spacer(1, 4 * mm))
        rows = [[Paragraph("<b>UAV Name</b>", style_small),
                 Paragraph("<b>Country</b>", style_small),
                 Paragraph("<b>Domain</b>", style_small)]]
        for entry in unverified:
            rows.append(
                [
                    Paragraph(html.escape(entry.name), style_small),
                    Paragraph(html.escape(entry.country), style_small),
                    Paragraph(html.escape(entry.domain), style_small),
                ]
            )
        table = Table(rows, colWidths=[85 * mm, 45 * mm, col_country + col_photo - 52 * mm + 6 * mm], repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#dfe4ec")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e7ebf2")),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef1f7")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(table)
        story.append(PageBreak())

    # --- country index ---------------------------------------------------
    story.append(heading("Appendix B — Country index", 0))
    country_rows = [[Paragraph("<b>Country</b>", style_small),
                     Paragraph("<b>ISO3</b>", style_small),
                     Paragraph("<b>Entries</b>", style_small),
                     Paragraph("<b>Pages</b>", style_small)]]
    counts: dict[str, int] = defaultdict(int)
    for entry in data.entries:
        counts[entry.country] += 1
    for country in sorted(counts):
        pages = sorted(country_pages.get(country, []))
        country_rows.append(
            [
                Paragraph(html.escape(country), style_small),
                Paragraph(country_iso3(country) or "—", style_small),
                Paragraph(str(counts[country]), style_small),
                Paragraph(_page_ranges(pages), style_small),
            ]
        )
    country_table = Table(
        country_rows, colWidths=[62 * mm, 16 * mm, 18 * mm, page_width - 2 * margin - 96 * mm],
        repeatRows=1,
    )
    country_table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#dfe4ec")),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e7ebf2")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef1f7")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(country_table)
    story.append(PageBreak())

    # --- alphabetical index ----------------------------------------------
    story.append(heading("Appendix C — Alphabetical index", 0))
    names = sorted({e.name for e in data.entries}, key=lambda s: s.lower())
    index_rows: list[list[Any]] = []
    per_column = 3
    row_buffer: list[Any] = []
    for name in names:
        page = index_pages.get(name)
        row_buffer.append(
            Paragraph(f"{html.escape(name)} <font color='#7c8698'>{page or '—'}</font>", style_small)
        )
        if len(row_buffer) == per_column:
            index_rows.append(row_buffer)
            row_buffer = []
    if row_buffer:
        while len(row_buffer) < per_column:
            row_buffer.append(Paragraph("", style_small))
        index_rows.append(row_buffer)
    if index_rows:
        column = (page_width - 2 * margin) / per_column
        index_table = Table(index_rows, colWidths=[column] * per_column)
        index_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                ]
            )
        )
        story.append(index_table)
    story.append(PageBreak())

    # --- attribution appendix --------------------------------------------
    story.append(heading("Appendix D — Photo attribution", 0))
    credited = [e for e in data.entries if e.has_image]
    if credited:
        story.append(
            Paragraph(
                "Every photograph below was retained only after its licence was verified as "
                "permitting redistribution, commercial use and modification. The complete "
                "machine-readable chain is in <font face='Courier'>output/photo_attribution.csv</font>.",
                style_small,
            )
        )
        story.append(Spacer(1, 3 * mm))
        rows = [[Paragraph("<b>UAV Name</b>", style_small),
                 Paragraph("<b>Attribution</b>", style_small),
                 Paragraph("<b>Licence</b>", style_small),
                 Paragraph("<b>Identity</b>", style_small)]]
        for entry in sorted(credited, key=lambda e: e.name.lower()):
            rows.append(
                [
                    Paragraph(html.escape(entry.name), style_small),
                    Paragraph(html.escape(entry.attribution or "—"), style_small),
                    Paragraph(html.escape(entry.license_name or "—"), style_small),
                    Paragraph(html.escape(entry.identity_verdict), style_small),
                ]
            )
        width = page_width - 2 * margin
        table = Table(
            rows, colWidths=[width * 0.24, width * 0.44, width * 0.18, width * 0.14], repeatRows=1
        )
        table.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#dfe4ec")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e7ebf2")),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef1f7")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(table)
    else:
        story.append(
            Paragraph(
                "No photographs are embedded in this edition: no image passed licence, "
                "resolution and identity verification. See docs/UNRESOLVED.md for the blocker "
                "and output/unresolved_records.csv for the per-platform detail.",
                style_small,
            )
        )
    story.append(PageBreak())

    # --- coverage statistics ---------------------------------------------
    story.append(heading("Appendix E — Coverage statistics", 0))
    coverage_rows = [
        ["Canonical platforms", stats.get("canonical_platforms", "")],
        ["Merged duplicates", stats.get("merged_duplicates", "")],
        ["Raw source records", stats.get("raw_source_records", "")],
        ["Manufacturers", stats.get("manufacturers", "")],
        ["Countries represented", stats.get("countries_represented", "")],
        ["Platform families", stats.get("platform_families", "")],
        ["Recorded variants", stats.get("platform_variants", "")],
        ["Aliases", stats.get("aliases", "")],
        ["Sources", stats.get("sources", "")],
        ["Images selected for atlas", stats.get("images", {}).get("selected_for_atlas", 0)],
        ["Image coverage %", stats.get("images", {}).get("coverage_pct", 0)],
        ["Open unresolved items", stats.get("unresolved_open", "")],
        ["Duplicate review rate %", stats.get("duplicate_review_rate_pct", "")],
    ]
    for domain, count in stats.get("by_domain", {}).items():
        coverage_rows.append([f"Domain — {domain}", count])
    for status, count in stats.get("by_verification_status", {}).items():
        coverage_rows.append([f"Verification — {status}", count])

    table = Table(
        [[Paragraph(html.escape(str(a)), style_small), Paragraph(html.escape(str(b)), style_small)]
         for a, b in coverage_rows],
        colWidths=[110 * mm, page_width - 2 * margin - 110 * mm],
    )
    table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#dfe4ec")),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e7ebf2")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(table)

    doc.multiBuild(story)
    LOG.info("PDF atlas written: %s (%d entries)", target, len(data.entries))
    LOG.event(
        "pdf_atlas_built",
        path=str(target),
        entries=len(data.entries),
        images=len(credited),
        size_bytes=target.stat().st_size if target.is_file() else 0,
    )
    return target


def _page_ranges(pages: list[int]) -> str:
    if not pages:
        return "—"
    ranges: list[str] = []
    start = previous = pages[0]
    for page in pages[1:]:
        if page == previous + 1:
            previous = page
            continue
        ranges.append(str(start) if start == previous else f"{start}–{previous}")
        start = previous = page
    ranges.append(str(start) if start == previous else f"{start}–{previous}")
    return ", ".join(ranges)


def run() -> dict[str, Any]:
    data = load_atlas_data()
    html_path = build_html(data)
    pdf_path = build_pdf(data)
    result = {
        "entries": len(data.entries),
        "html": str(html_path),
        "pdf": str(pdf_path) if pdf_path else None,
        "with_images": sum(1 for e in data.entries if e.has_image),
        "generated_at": utc_now(),
    }
    LOG.info("atlas build complete: %s", result)
    return result
