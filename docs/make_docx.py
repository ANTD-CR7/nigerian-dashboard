"""Convert docs/FYP_REPORT.md to docs/FYP_REPORT.docx with python-docx.

Pragmatic converter for this report's Markdown subset: headings, bold runs,
pipe tables, fenced code blocks (mermaid blocks are kept as monospace source
with a note to render them at mermaid.live), bullet/numbered lists and
blockquotes. Re-run after editing the Markdown:  python docs/make_docx.py
"""
import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor

from PIL import Image

SRC = Path(__file__).parent / "FYP_REPORT.md"
DST = Path(__file__).parent / "FYP_REPORT.docx"


def add_runs(par, text):
    """Split **bold** segments into runs; strip stray backticks/italics markers."""
    text = text.replace("`", "")
    for i, chunk in enumerate(re.split(r"\*\*", text)):
        if not chunk:
            continue
        run = par.add_run(chunk)
        run.bold = (i % 2 == 1)


def add_code(doc, lines, mermaid=False):
    if mermaid:
        note = doc.add_paragraph()
        r = note.add_run("[Diagram source below — render it at mermaid.live or draw.io and replace with the image]")
        r.italic = True
        r.font.size = Pt(9)
    for line in lines:
        p = doc.add_paragraph()
        r = p.add_run(line if line else " ")
        r.font.name = "Consolas"
        r.font.size = Pt(9)
        p.paragraph_format.space_after = Pt(0)


def add_image(doc, alt, rel_path):
    """![caption](figures/x.png) → centered picture sized to the page, + caption."""
    img = Path(__file__).parent / rel_path
    if not img.exists():
        p = doc.add_paragraph()
        r = p.add_run(f"[missing image: {rel_path}]")
        r.italic = True
        return
    w_px, h_px = Image.open(img).size
    # fit within 6.2" wide and 7.5" tall (portrait A4 with margins)
    width = min(6.2, 6.2 * (w_px / max(w_px, 1)))
    height_at_width = h_px / w_px * width
    if height_at_width > 7.5:
        width = width * 7.5 / height_at_width
    # small diagrams shouldn't be blown up past ~2x native (96dpi assumption)
    native_in = w_px / 96
    width = min(width, max(native_in * 1.6, 3.0))
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run().add_picture(str(img), width=Inches(width))
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = cap.add_run(alt)
    r.italic = True
    r.font.size = Pt(9)
    cap.paragraph_format.space_after = Pt(14)


def add_table(doc, rows):
    cells = [[c.strip() for c in row.strip().strip("|").split("|")] for row in rows]
    cells = [r for r in cells if not all(re.fullmatch(r":?-{2,}:?", c or "---") for c in r)]
    if not cells:
        return
    ncols = max(len(r) for r in cells)
    t = doc.add_table(rows=len(cells), cols=ncols)
    t.style = "Table Grid"
    for ri, row in enumerate(cells):
        for ci in range(ncols):
            text = row[ci] if ci < len(row) else ""
            par = t.cell(ri, ci).paragraphs[0]
            add_runs(par, text)
            for run in par.runs:
                run.font.size = Pt(9)
                if ri == 0:
                    run.bold = True


def main():
    md = SRC.read_text(encoding="utf-8").splitlines()
    doc = Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(11)

    i = 0
    while i < len(md):
        line = md[i]

        if line.startswith("```"):
            mermaid = "mermaid" in line
            block = []
            i += 1
            while i < len(md) and not md[i].startswith("```"):
                block.append(md[i]); i += 1
            add_code(doc, block, mermaid)
            i += 1
            continue

        if line.strip().startswith("|"):
            rows = []
            while i < len(md) and md[i].strip().startswith("|"):
                rows.append(md[i]); i += 1
            add_table(doc, rows)
            doc.add_paragraph()
            continue

        m_img = re.match(r"^!\[(.*?)\]\((.*?)\)\s*$", line.strip())
        if m_img:
            add_image(doc, m_img.group(1), m_img.group(2))
            i += 1
            continue

        if line.startswith("# "):
            p = doc.add_heading(re.sub(r"\*\*", "", line[2:]).strip(), level=0)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif line.startswith("## "):
            doc.add_page_break()
            doc.add_heading(re.sub(r"\*\*", "", line[3:]).strip(), level=1)
        elif line.startswith("### "):
            doc.add_heading(re.sub(r"\*\*", "", line[4:]).strip(), level=2)
        elif line.startswith("#### "):
            doc.add_heading(re.sub(r"\*\*", "", line[5:]).strip(), level=3)
        elif line.startswith("> "):
            p = doc.add_paragraph()
            add_runs(p, line[2:])
            for run in p.runs:
                run.italic = True
                run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
        elif re.match(r"^\s*[-*] ", line):
            p = doc.add_paragraph(style="List Bullet")
            add_runs(p, re.sub(r"^\s*[-*] ", "", line))
        elif re.match(r"^\s*\d+\. ", line):
            p = doc.add_paragraph(style="List Number")
            add_runs(p, re.sub(r"^\s*\d+\. ", "", line))
        elif line.strip() in ("---", "***"):
            pass
        elif line.strip():
            p = doc.add_paragraph()
            add_runs(p, line)
        i += 1

    doc.save(DST)
    print(f"Wrote {DST} ({DST.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
