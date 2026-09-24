"""Editable Word (.docx) version of the Theme 6.1 booklet.

build_booklet.py saves its final HTML in report/_html/.
This script walks that HTML and writes native Word content: real Heading styles (so the Navigation pane and the
Table of Contents work), editable text, editable tables, shaded boxes for 'The story so far' / 'So what' / call-outs,
and Word caption styles that feed the List of Figures and List of Tables. Charts are placed as pictures; the HTML
infographics (at-a-glance, theatre map, signatures, centre of gravity ...) are rendered to pictures with the same CSS.

Run after the PDF builders:  python report/build_word.py
Word asks to update fields on first opening: answer Yes so the contents, figure and table lists fill in with page numbers.
"""
import base64
import io
import re
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent
HTML = OUT / "_html"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
NAVY, RUST, GREY = RGBColor(0x1F, 0x3B, 0x5C), RGBColor(0x9A, 0x4A, 0x3A), RGBColor(0x55, 0x55, 0x55)
# box style per HTML class: (fill, border colour, border sides)
BOX = {"story": ("FBF6EC", "D9C7A3", "all"), "sowhat": ("EEF2F7", "1F3B5C", "all"), "callout": ("EEF2F7", "1F3B5C", "left"),
       "bluf": ("EEF2F7", "1F3B5C", "all"), "code": ("F6F6F4", "DDDDDD", "all"), "plain": ("F7F7F4", "9A4A3A", "left")}
# HTML blocks that are pictures by nature (flex layouts, icons, maps) and are rendered, not rebuilt
PICTURE_CLASSES = {"ig", "kpis"}


# ------------------------------------------------------------------ low-level Word helpers
TCPR = ("cnfStyle", "tcW", "gridSpan", "hMerge", "vMerge", "tcBorders", "shd", "noWrap", "tcMar", "textDirection", "tcFitText", "vAlign", "hideMark")
TBLPR = ("tblStyle", "tblpPr", "tblOverlap", "bidiVisual", "tblStyleRowBandSize", "tblStyleColBandSize", "tblW", "jc", "tblCellSpacing",
         "tblInd", "tblBorders", "shd", "tblLayout", "tblCellMar", "tblLook", "tblCaption", "tblDescription")
SECTPR = ("headerReference", "footerReference", "footnotePr", "endnotePr", "type", "pgSz", "pgMar", "paperSrc", "pgBorders", "lnNumType",
          "pgNumType", "cols", "formProt", "vAlign", "noEndnote", "titlePg", "textDirection", "bidi", "rtlGutter", "docGrid")


def put(parent, el, order):
    """Insert `el` where the OOXML schema expects it (Word rejects out-of-order children)."""
    rank = order.index(el.tag.split("}")[1])
    for old in parent.findall(el.tag):
        parent.remove(old)
    for ch in parent:
        t = ch.tag.split("}")[1]
        if t in order and order.index(t) > rank:
            ch.addprevious(el)
            return
    parent.append(el)


def shade(cell_or_par, fill):
    """Background fill for a table cell (w:tcPr) or paragraph (w:pPr)."""
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear"), shd.set(qn("w:color"), "auto"), shd.set(qn("w:fill"), fill)
    put(cell_or_par._tc.get_or_add_tcPr(), shd, TCPR)


def cell_borders(cell, colour, sides="all", size=6):
    tcPr = cell._tc.get_or_add_tcPr()
    b = OxmlElement("w:tcBorders")
    for side in ("top", "left", "bottom", "right"):
        e = OxmlElement(f"w:{side}")
        on = sides == "all" or side == sides
        e.set(qn("w:val"), "single" if on else "nil")
        if on:
            e.set(qn("w:sz"), str(size if sides == "all" else 24)), e.set(qn("w:color"), colour)
        b.append(e)
    put(tcPr, b, TCPR)


def table_width(table, widths_dxa):
    """Fixed DXA widths on the grid and on every cell (Word, LibreOffice and Google Docs all honour this)."""
    tbl = table._tbl
    tblPr = tbl.tblPr
    w = OxmlElement("w:tblW")
    w.set(qn("w:w"), str(sum(widths_dxa))), w.set(qn("w:type"), "dxa")
    put(tblPr, w, TBLPR)
    lay = OxmlElement("w:tblLayout")
    lay.set(qn("w:type"), "fixed")
    put(tblPr, lay, TBLPR)
    grid = tbl.tblGrid
    for gc, wd in zip(grid.findall(qn("w:gridCol")), widths_dxa):
        gc.set(qn("w:w"), str(wd))
    for row in table.rows:
        for c, wd in zip(row.cells, widths_dxa):
            tcW = c._tc.get_or_add_tcPr().get_or_add_tcW()
            tcW.set(qn("w:w"), str(wd)), tcW.set(qn("w:type"), "dxa")


def repeat_header(row):
    trPr = row._tr.get_or_add_trPr()
    h = OxmlElement("w:tblHeader")
    h.set(qn("w:val"), "true")
    trPr.append(h)


def field(par, instr, cached=""):
    """A Word field (PAGE, TOC ...) with an optional cached result."""
    def fc(t):
        r = OxmlElement("w:r")
        e = OxmlElement("w:fldChar")
        e.set(qn("w:fldCharType"), t)
        r.append(e)
        return r
    par._p.append(fc("begin"))
    r = OxmlElement("w:r")
    it = OxmlElement("w:instrText")
    it.set(qn("xml:space"), "preserve")
    it.text = f" {instr} "
    r.append(it)
    par._p.append(r)
    par._p.append(fc("separate"))
    par.add_run(cached)
    par._p.append(fc("end"))


def keep_with_next(par):
    par.paragraph_format.keep_with_next = True


# ------------------------------------------------------------------ inline content
def clean(t):
    return re.sub(r"[ \t\r\n]+", " ", t.replace(" ", " "))


def inline(par, node, bold=False, italic=False, sup=False, sub=False, size=None, colour=None, mono=False):
    """Append the inline HTML under `node` to paragraph `par` as formatted runs."""
    for ch in node.children:
        if isinstance(ch, NavigableString):
            t = clean(str(ch))
            if not t:
                continue
            r = par.add_run(t)
            r.bold, r.italic = bold or None, italic or None
            r.font.superscript, r.font.subscript = sup or None, sub or None
            if size:
                r.font.size = Pt(size)
            if colour:
                r.font.color.rgb = colour
            if mono:
                r.font.name = "Consolas"
        elif isinstance(ch, Tag):
            cls = ch.get("class", [])
            if ch.name in ("svg", "style", "script") or "mk" in cls:
                continue
            if ch.name == "br":
                par.add_run().add_break()
                continue
            inline(par, ch, bold=bold or ch.name in ("b", "strong", "th") or "lab" in cls,
                   italic=italic or ch.name in ("i", "em"), sup=sup or ch.name == "sup", sub=sub or ch.name == "sub",
                   size=size, colour=colour, mono=mono)
    return par


def strip_lead(par):
    """Remove leading spaces left by the HTML (e.g. after the removed page-marker spans)."""
    for r in par.runs:
        if r.text.strip():
            r.text = r.text.lstrip()
            break
        r.text = ""


# ------------------------------------------------------------------ the converter
class Converter:
    def __init__(self, css, header, chapter_breaks=True, margins=(20, 18, 22, 18)):
        self.css, self.header, self.chapter_breaks = css, header, chapter_breaks
        self.doc = Document()
        self.pics = []                      # (placeholder paragraph, html) rendered in one browser session
        self.sec = self.doc.sections[0]
        self.sec.page_width, self.sec.page_height = Mm(210), Mm(297)
        t, b, l, r = margins
        self.sec.top_margin, self.sec.bottom_margin, self.sec.left_margin, self.sec.right_margin = Mm(t), Mm(b), Mm(l), Mm(r)
        self.text_w = 210 - l - r           # mm
        self._styles()

    # styles ---------------------------------------------------------
    def _styles(self):
        st = self.doc.styles
        n = st["Normal"]
        n.font.name, n.font.size = "Times New Roman", Pt(11)
        n.element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
        n.paragraph_format.space_after, n.paragraph_format.line_spacing = Pt(6), 1.2
        for name, size, before in (("Heading 1", 15, 0), ("Heading 2", 12.5, 12), ("Heading 3", 11.5, 10)):
            h = st[name]
            h.font.name, h.font.size, h.font.bold, h.font.color.rgb = "Times New Roman", Pt(size), True, NAVY
            rf = h.element.get_or_add_rPr().get_or_add_rFonts()
            for a in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
                rf.attrib.pop(qn(a), None)
            rf.set(qn("w:ascii"), "Times New Roman"), rf.set(qn("w:hAnsi"), "Times New Roman")
            h.paragraph_format.space_before, h.paragraph_format.space_after = Pt(before), Pt(6)
            h.paragraph_format.keep_with_next = True
        for name, it in (("Figure Caption", False), ("Table Caption", False)):
            s = st.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
            s.base_style = st["Normal"]
            s.font.size = Pt(10.5)
            s.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
            s.paragraph_format.space_before, s.paragraph_format.space_after = Pt(3), Pt(8)
        st["Table Caption"].paragraph_format.keep_with_next = True
        fh = st.add_style("Front Heading", WD_STYLE_TYPE.PARAGRAPH)   # front-matter titles: not in the contents
        fh.base_style = st["Normal"]
        fh.font.size, fh.font.bold, fh.font.color.rgb = Pt(14), True, NAVY
        fh.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
        fh.paragraph_format.space_after = Pt(12)
        fh.paragraph_format.keep_with_next = True
        k = st.add_style("Kicker", WD_STYLE_TYPE.PARAGRAPH)
        k.base_style = st["Normal"]
        k.font.name, k.font.size, k.font.bold, k.font.color.rgb = "Arial", Pt(9), True, RUST
        k.paragraph_format.keep_with_next = True
        tt = st.add_style("Table Text", WD_STYLE_TYPE.PARAGRAPH)
        tt.base_style = st["Normal"]
        tt.font.name, tt.font.size = "Arial", Pt(8.5)
        tt.paragraph_format.space_after, tt.paragraph_format.line_spacing = Pt(0), 1.0
        tt.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
        # Word refreshes every field (contents, lists, page numbers) when the file is opened
        # (w:updateFields must sit before these elements in settings.xml, per the schema order)
        se = self.doc.settings.element
        upd = OxmlElement("w:updateFields")
        upd.set(qn("w:val"), "true")
        after = ("hdrShapeDefaults", "footnotePr", "endnotePr", "compat", "docVars", "rsids", "mathPr", "attachedSchema",
                 "themeFontLang", "clrSchemeMapping", "doNotIncludeSubdocsInStats", "doNotAutoCompressPictures", "forceUpgrade",
                 "captions", "readModeInkLockDown", "smartTagType", "schemaLibrary", "shapeDefaults", "doNotEmbedSmartTags",
                 "decimalSymbol", "listSeparator")
        nxt = next((e for e in se if e.tag.split("}")[1] in after), None)
        nxt.addprevious(upd) if nxt is not None else se.append(upd)
        zoom = se.find(qn("w:zoom"))
        if zoom is not None and zoom.get(qn("w:percent")) is None:
            zoom.set(qn("w:percent"), "100")

    # page furniture -------------------------------------------------
    def furniture(self, section, fmt, start=None, first_blank=False):
        pgNumType = OxmlElement("w:pgNumType")
        pgNumType.set(qn("w:fmt"), fmt)
        if start:
            pgNumType.set(qn("w:start"), str(start))
        put(section._sectPr, pgNumType, SECTPR)
        section.different_first_page_header_footer = first_blank
        section.header.is_linked_to_previous = section.footer.is_linked_to_previous = False
        hp = section.header.paragraphs[0]
        hp.text = ""
        r = hp.add_run(self.header)
        r.font.size, r.font.name, r.font.color.rgb = Pt(7.5), "Arial", GREY
        fp = section.footer.paragraphs[0]
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        field(fp, "PAGE", "1")

    # blocks ---------------------------------------------------------
    def para(self, node=None, style=None, align=None, text=None, size=None, bold=False, italic=False, colour=None):
        p = self.doc.add_paragraph(style=style)
        if align is not None:
            p.alignment = align
        elif style is None:
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        if text is not None:
            r = p.add_run(text)
            r.bold, r.italic = bold or None, italic or None
            if size:
                r.font.size = Pt(size)
            if colour:
                r.font.color.rgb = colour
        if node is not None:
            inline(p, node, bold=bold, italic=italic, size=size, colour=colour)
            strip_lead(p)
        return p

    def picture_bytes(self, data, width_pct=100, max_h_mm=210):
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        w_mm = self.text_w * min(width_pct, 100) / 100
        h_mm = w_mm * im.height / im.width
        if h_mm > max_h_mm:
            w_mm *= max_h_mm / h_mm
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.keep_with_next = True
        p.add_run().add_picture(io.BytesIO(data), width=Mm(w_mm))
        return p

    def picture_html(self, html):
        """Placeholder now; the HTML is rendered to PNG in render_pictures()."""
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.keep_with_next = True
        self.pics.append((p, html))
        return p

    def box(self, node, kind):
        fill, border, sides = BOX[kind]
        t = self.doc.add_table(rows=1, cols=1)
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        c = t.cell(0, 0)
        shade(c, fill), cell_borders(c, border, sides)
        cs = OxmlElement("w:cantSplit")          # keep each box on one page
        t.rows[0]._tr.get_or_add_trPr().append(cs)
        table_width(t, [int(self.text_w / 25.4 * 1440)])
        c.paragraphs[0]._p.getparent().remove(c.paragraphs[0]._p)
        size = 9 if kind == "plain" else (8 if kind == "code" else None)
        if kind == "code":
            for line in node.get_text().split("\n"):
                p = c.add_paragraph(style="Table Text")
                r = p.add_run(line)
                r.font.name, r.font.size = "Consolas", Pt(8)
            return self.spacer()
        lab = node.find("span", class_="lab")
        if lab:
            p = c.add_paragraph(style="Table Text")
            r = p.add_run(lab.get_text().strip().upper())
            r.bold, r.font.color.rgb = True, NAVY if kind == "sowhat" else RUST
            lab.decompose()
        nxt = node.find("span", class_="next")
        if nxt:
            nxt.extract()
        blocks = [ch for ch in node.children if isinstance(ch, Tag) and ch.name in ("p", "ul", "ol")]
        if not blocks:
            p = c.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p.paragraph_format.space_after = Pt(2)
            inline(p, node, size=size)
            strip_lead(p)
        for b in blocks:
            if b.name == "p":
                p = c.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                inline(p, b, size=size)
                strip_lead(p)
            else:
                for i, li in enumerate(b.find_all("li", recursive=False), 1):
                    p = c.add_paragraph()
                    p.paragraph_format.left_indent, p.paragraph_format.first_line_indent = Mm(6), Mm(-5)
                    p.add_run(f"{i}.\t" if b.name == "ol" else "•\t")
                    inline(p, li, size=size)
        if nxt:
            p = c.add_paragraph()
            r = p.add_run(nxt.get_text().strip())
            r.italic, r.font.color.rgb = True, NAVY
        self.spacer()

    def spacer(self):
        p = self.doc.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.line_spacing = 0.6

    def lst(self, node, kind):
        for i, li in enumerate(node.find_all("li", recursive=False), 1):
            p = self.doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p.paragraph_format.left_indent, p.paragraph_format.first_line_indent = Mm(8), Mm(-6)
            p.paragraph_format.space_after = Pt(3)
            mark = {"ol": f"{i}.", "alpha": f"({chr(96 + i)})"}.get(kind, "•")
            p.add_run(mark + "\t")
            inline(p, li)

    def table(self, tbl, caption=None, note=None, small=True):
        if caption is not None:
            p = self.doc.add_paragraph(style="Table Caption")
            inline(p, caption)
            strip_lead(p)
        rows = [tr for tr in tbl.find_all("tr")]
        grid = [[c for c in tr.find_all(["td", "th"], recursive=False)] for tr in rows]
        ncol = max(sum(int(c.get("colspan", 1)) for c in r) for r in grid)
        t = self.doc.add_table(rows=len(rows), cols=ncol)
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.style = self.doc.styles["Table Grid"]
        # column widths: every column gets room for its longest word, the rest is shared in proportion to text length
        weight, minw = [1.0] * ncol, [8.0] * ncol          # minw in mm
        for r in grid:
            j = 0
            for c in r:
                span = int(c.get("colspan", 1))
                if span == 1:
                    txt = c.get_text(" ").strip()
                    longest = max((len(w) for w in txt.split()), default=0)
                    minw[j] = max(minw[j], min(longest * 2.0 + 4.5, 45))
                    weight[j] = max(weight[j], min(len(txt), 90) ** 0.9)
                j += span
        free = self.text_w - sum(minw)
        mm = [m + max(free, 0) * w / sum(weight) for m, w in zip(minw, weight)] if free > 0 else [m * self.text_w / sum(minw) for m in minw]
        widths = [int(x / 25.4 * 1440) for x in mm]
        for i, (tr, r) in enumerate(zip(rows, grid)):
            j = 0
            head = all(c.name == "th" for c in r)
            sec = "sec" in tr.get("class", [])
            for c in r:
                span = int(c.get("colspan", 1))
                cell = t.cell(i, j)
                if span > 1:
                    cell = cell.merge(t.cell(i, j + span - 1))
                p = cell.paragraphs[0]
                p.style = self.doc.styles["Table Text"]
                inline(p, c, bold=head or sec, colour=RGBColor(255, 255, 255) if head else None)
                strip_lead(p)
                if head:
                    shade(cell, "1F3B5C")
                elif sec:
                    shade(cell, "DCE3EC")
                elif i % 2 == 0 and small:
                    shade(cell, "F4F3EF")
                cls = c.get("class", [])
                for k, fill in (("ok", "D5ECD4"), ("pa", "FCEBC7"), ("no", "F6D2CC"), ("red", "F6D2CC"), ("amber", "FCEBC7")):
                    if k in cls or c.find(class_=k):
                        shade(cell, fill)
                j += span
            if head:
                repeat_header(t.rows[i])
        table_width(t, widths)
        if note is not None:
            p = self.para(node=note, size=9, italic=True)
        self.spacer()

    def figure(self, fig):
        img = fig.find("img", recursive=False)
        cap = fig.find("figcaption")
        if img is not None:
            m = re.search(r"width:\s*([\d.]+)%", img.get("style", ""))
            data = base64.b64decode(img["src"].split(",", 1)[1])
            self.picture_bytes(data, float(m.group(1)) if m else 100)
        else:
            inner = "".join(str(ch) for ch in fig.children if not (isinstance(ch, Tag) and ch.name in ("figcaption",)) and
                            not (isinstance(ch, Tag) and ("plain" in ch.get("class", []) or "src" in ch.get("class", []))))
            self.picture_html(inner)
        if cap is not None:
            p = self.doc.add_paragraph(style="Figure Caption")
            inline(p, cap)
            strip_lead(p)
        for d in fig.find_all("div", class_=["plain", "src"], recursive=False):
            if "plain" in d.get("class", []):
                self.box(d, "plain")
            else:
                self.para(node=d, size=9, italic=True)

    def block(self, el):
        """Convert one top-level HTML element."""
        if isinstance(el, NavigableString):
            if clean(str(el)).strip():
                self.para(text=clean(str(el)).strip())
            return
        cls = el.get("class", [])
        name = el.name
        if name == "h1" and "chapter" in cls:
            h = self.doc.add_heading(level=1)
            inline(h, el)
            strip_lead(h)
            if self.chapter_breaks:
                h.paragraph_format.page_break_before = True
            elif len(self.doc.paragraphs) > 3:
                h.paragraph_format.space_before = Pt(18)
        elif name == "h1":
            self.para(node=el, style="Front Heading")
        elif name in ("h2", "h3"):
            h = self.doc.add_heading(level=int(name[1]))
            inline(h, el)
            strip_lead(h)
        elif name == "h4":
            keep_with_next(self.para(node=el, bold=True))
        elif name == "p":
            self.para(node=el)
        elif name in ("ul", "ol"):
            self.lst(el, "alpha" if "alpha" in cls else name)
        elif name == "figure":
            self.figure(el)
        elif name == "table":
            self.table(el, small="small" in cls or "tbl" in cls)
        elif "tblwrap" in cls:
            self.table(el.find("table"), caption=el.find(class_="tcap"), note=el.find("div", class_="src"))
        elif "kicker" in cls:
            self.para(text=el.get_text().strip().upper(), style="Kicker")
        elif any(k in cls for k in BOX):
            self.box(el, next(k for k in BOX if k in cls))
        elif "eq" in cls:
            p = self.doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            inline(p, el.find(class_="eqb"), italic=True)
            p.add_run("\t\t(" + el.find(class_="eqn").get_text().strip("() ") + ")")
        elif PICTURE_CLASSES & set(cls):
            self.picture_html(str(el))
        elif name == "div":
            if el.find(["p", "h1", "h2", "h3", "table", "ul", "ol", "figure", "div"], recursive=False):
                for ch in el.children:
                    self.block(ch)
            elif el.get_text().strip():
                self.para(node=el)

    # rendering of HTML infographics --------------------------------
    def render_pictures(self):
        if not self.pics:
            return
        with sync_playwright() as pw:
            br = pw.chromium.launch(executable_path=CHROME)
            pg = br.new_page(device_scale_factor=2.2)
            for p, html in self.pics:
                pg.set_content(f"<!doctype html><html><head><meta charset='utf-8'><style>{self.css}"
                               f"body{{margin:0;background:#fff}}</style></head><body>"
                               f"<div id='cap' style='width:{self.text_w}mm;padding:2mm'>{html}</div></body></html>", wait_until="load")
                png = pg.locator("#cap").screenshot(type="png")
                from PIL import Image
                im = Image.open(io.BytesIO(png))
                w_mm = self.text_w
                h_mm = w_mm * im.height / im.width
                if h_mm > 225:
                    w_mm *= 225 / h_mm
                p.add_run().add_picture(io.BytesIO(png), width=Mm(w_mm))
            br.close()

    def save(self, path):
        self.render_pictures()
        cp = self.doc.core_properties
        cp.author, cp.last_modified_by, cp.comments = "Arjun Jayadev", "Arjun Jayadev", ""
        cp.title = self.header.split("|")[-1].strip()
        self.doc.save(path)
        print("->", path)


# ------------------------------------------------------------------ front matter
def front(cv, soup, lists):
    """Title page, declarations, summary and the Word-generated contents / lists of figures and tables."""
    tp = soup.find("div", class_="titlepage")
    for i, d in enumerate(tp.find_all("div", recursive=False)):
        c = d.get("class", [])
        p = cv.para(node=d, align=WD_ALIGN_PARAGRAPH.CENTER,
                    size=20 if "t1" in c else (13 if "t2" in c else 12), bold="t1" in c, italic="t2" in c and "font-style:normal" not in d.get("style", ""))
        m = re.search(r"margin-top:(\d+)pt", d.get("style", ""))
        p.paragraph_format.space_before = Pt(int(m.group(1)) if m else (70 if i == 0 else 4))
        if "t2" in c or "t1" in c:
            p.paragraph_format.space_after = Pt(18)
    for d in soup.body.find_all("div", class_="front", recursive=False):
        title = d.find("h1").get_text().strip()
        cv.doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        cv.doc.paragraphs[-1].paragraph_format.space_after = Pt(0)
        if title in lists:
            cv.para(text=title, style="Front Heading")
            instr, entries = lists[title]
            p = cv.doc.add_paragraph()
            field(p, instr, "")
            p.runs[-1].text = ""
            # cached entries (shown until Word updates the field on opening)
            for e in entries:
                q = cv.doc.add_paragraph(e)
                q.paragraph_format.space_after = Pt(2)
            for ch in d.find_all("p", recursive=False):
                cv.para(node=ch)
            continue
        for ch in d.children:
            if isinstance(ch, Tag) and "sig" in ch.get("class", []):
                for s in ch.find_all("div"):
                    cv.para(node=s, align=WD_ALIGN_PARAGRAPH.RIGHT)
            else:
                cv.block(ch)


def toc_entries(soup, heading):
    h = [x for x in soup.find_all("h1") if x.get_text().strip() == heading]
    if not h:
        return []
    return [clean(" ".join(td.get_text(" ") for td in tr.find_all("td") if "pg" not in td.get("class", []))).strip()
            for tr in h[0].find_next("table").find_all("tr")]


def css_of(soup):
    return "".join(s.get_text() for s in soup.find_all("style"))


def build(name, header, chapter_breaks, contents_levels, margins, out):
    fs = BeautifulSoup((HTML / f"{name}_front.html").read_text(), "html.parser")
    bs = BeautifulSoup((HTML / f"{name}_body.html").read_text(), "html.parser")
    cv = Converter(css_of(bs), header, chapter_breaks, margins)
    lists = {"TABLE OF CONTENTS": (f'TOC \\o "1-{contents_levels}" \\h \\z \\u', toc_entries(fs, "TABLE OF CONTENTS")),
             "CONTENTS": (f'TOC \\o "1-{contents_levels}" \\h \\z \\u', toc_entries(fs, "CONTENTS")),
             "LIST OF FIGURES": ('TOC \\h \\z \\t "Figure Caption,1"', toc_entries(fs, "LIST OF FIGURES")),
             "LIST OF TABLES": ('TOC \\h \\z \\t "Table Caption,1"', toc_entries(fs, "LIST OF TABLES"))}
    front(cv, fs, lists)
    # the body starts a new section: arabic page numbers from 1; the front keeps roman numerals and a bare title page
    body = cv.doc.add_section(WD_SECTION.NEW_PAGE)
    cv.furniture(cv.doc.sections[0], "lowerRoman", first_blank=True)
    cv.furniture(body, "decimal", start=1)
    first = True
    for el in bs.body.children:
        if first and isinstance(el, Tag) and el.name == "h1":
            el["class"] = el.get("class", []) + ["first"]
            cv.chapter_breaks, keep = False, cv.chapter_breaks
            cv.block(el)
            cv.chapter_breaks, first = keep, False
            continue
        cv.block(el)
    cv.save(OUT / out)


if __name__ == "__main__":
    build("booklet", "CDM Datathon-2026  |  Theme 6.1  |  Contested and Congested: Growth of Satellites in Outer Space",
          chapter_breaks=False, contents_levels=1, margins=(20, 18, 20, 18), out="Datathon2026_Theme6.1_Satellites_Booklet.docx")
