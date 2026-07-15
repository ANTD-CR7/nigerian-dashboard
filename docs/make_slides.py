"""Build a 21-slide NPEDATA defence deck (16:9) in the platform's palette.
Run:  python docs/make_slides.py   ->  docs/NPEDATA_Defense_Slides.pptx
"""
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

FIG = Path(__file__).parent / "figures"
OUT = Path(__file__).parent / "NPEDATA_Defense_Slides.pptx"

# ── NPEDATA palette ──
BLACK   = RGBColor(0x07, 0x08, 0x0D)
PANEL   = RGBColor(0x12, 0x14, 0x1F)
CREAM   = RGBColor(0xF5, 0xF0, 0xE8)
GREEN   = RGBColor(0x00, 0xA3, 0x62)
GOLD    = RGBColor(0xF4, 0xA0, 0x17)
SLATE   = RGBColor(0x9A, 0x96, 0x8F)
HEAD_F  = "Georgia"        # serif proxy for the site's Playfair headings
BODY_F  = "Segoe UI"

EMU_W, EMU_H = Inches(13.333), Inches(7.5)

prs = Presentation()
prs.slide_width = EMU_W
prs.slide_height = EMU_H
BLANK = prs.slide_layouts[6]


def bg(slide, color=BLACK):
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = color


def box(slide, l, t, w, h):
    tb = slide.shapes.add_textbox(l, t, w, h)
    tb.text_frame.word_wrap = True
    return tb


def set_run(r, text, size, color, font=BODY_F, bold=False, italic=False):
    r.text = text
    r.font.size = Pt(size)
    r.font.color.rgb = color
    r.font.name = font
    r.font.bold = bold
    r.font.italic = italic


def accent_bar(slide, l=Inches(0.9), t=Inches(0.62), w=Inches(0.55)):
    sh = slide.shapes.add_shape(1, l, t, w, Inches(0.06))  # rectangle
    sh.fill.solid(); sh.fill.fore_color.rgb = GOLD
    sh.line.fill.background()


def header(slide, eyebrow, title, n):
    accent_bar(slide)
    # eyebrow
    e = box(slide, Inches(0.9), Inches(0.72), Inches(9.5), Inches(0.4))
    p = e.text_frame.paragraphs[0]
    set_run(p.add_run(), eyebrow.upper(), 12, GREEN, BODY_F, bold=True)
    p.runs[0].font.spacing = Pt(2) if hasattr(p.runs[0].font, "spacing") else None
    # title
    tt = box(slide, Inches(0.88), Inches(1.05), Inches(11.4), Inches(1.2))
    tp = tt.text_frame.paragraphs[0]
    set_run(tp.add_run(), title, 32, CREAM, HEAD_F, italic=True)
    # slide number chip
    num = box(slide, Inches(12.35), Inches(6.95), Inches(0.8), Inches(0.4))
    np_ = num.text_frame.paragraphs[0]; np_.alignment = PP_ALIGN.RIGHT
    set_run(np_.add_run(), f"{n:02d} / 21", 10, SLATE, BODY_F)


def bullets(slide, items, top=Inches(2.35), left=Inches(1.0), width=Inches(11.2),
            size=18, gap=10):
    tb = box(slide, left, top, width, Inches(4.4))
    tf = tb.text_frame
    for i, (lead, rest) in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(gap)
        set_run(p.add_run(), "▸  ", size, GOLD, BODY_F, bold=True)
        if lead:
            set_run(p.add_run(), lead, size, CREAM, BODY_F, bold=True)
        if rest:
            set_run(p.add_run(), (" — " if lead else "") + rest, size, SLATE, BODY_F)
    return tb


def add_image(slide, path, l, t, max_w, max_h):
    from PIL import Image
    iw, ih = Image.open(path).size
    ratio = min(max_w / iw, max_h / ih)
    w, h = int(iw * ratio), int(ih * ratio)
    # center within the box
    pic = slide.shapes.add_picture(str(path), l + (max_w - w) // 2, t + (max_h - h) // 2, w, h)
    return pic


def content(eyebrow, title, n, items=None, img=None, img_side="right", caption=None):
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, eyebrow, title, n)
    if img and items:
        # split: bullets left, image right
        bullets(s, items, top=Inches(2.55), left=Inches(1.0), width=Inches(6.0), size=19, gap=16)
        add_image(s, img, Inches(7.25), Inches(2.5), Inches(5.4), Inches(4.2))
    elif img:
        add_image(s, img, Inches(1.4), Inches(2.35), Inches(10.5), Inches(4.4))
    elif items:
        bullets(s, items, top=Inches(2.7), size=24, gap=22)
    if caption:
        c = box(s, Inches(1.0), Inches(6.85), Inches(11.0), Inches(0.4))
        cp = c.text_frame.paragraphs[0]
        set_run(cp.add_run(), caption, 11, SLATE, BODY_F, italic=True)
    return s

# ─────────────────────────── SLIDE 1: TITLE ───────────────────────────
s = prs.slides.add_slide(BLANK); bg(s)
accent_bar(s, Inches(0.9), Inches(1.0), Inches(0.7))
eb = box(s, Inches(0.9), Inches(1.15), Inches(11), Inches(0.4))
set_run(eb.text_frame.paragraphs[0].add_run(),
        "CALEB UNIVERSITY, LAGOS  ·  B.Sc. COMPUTER SCIENCE  ·  FINAL YEAR PROJECT", 12, GREEN, BODY_F, bold=True)
tt = box(s, Inches(0.85), Inches(1.7), Inches(11.6), Inches(2.6))
para = tt.text_frame.paragraphs[0]
set_run(para.add_run(),
        "Design and Development of a Nigerian Public Economic Data Aggregation and Analytics Platform with Open API Access",
        34, CREAM, HEAD_F, italic=True)
sub = box(s, Inches(0.9), Inches(4.15), Inches(11), Inches(0.5))
set_run(sub.text_frame.paragraphs[0].add_run(), "A 2020–2026 Case Study  ·  “NPEDATA”", 18, GOLD, HEAD_F, italic=True)
meta = box(s, Inches(0.9), Inches(5.0), Inches(11.5), Inches(2.0))
lines = [
    ("By:  ", "Taoheed Abdulmanan Olaosebikan   (22/10267)"),
    ("Supervisor:  ", "Miss Ilori Deborah"),
    ("Head of Department:  ", "Dr. Ayorinde Oduroye"),
    ("Department:  ", "Computer Science, College of Science and Information Science (COSIS)"),
    ("Date:  ", "July 2026"),
]
tf = meta.text_frame
for i, (k, v) in enumerate(lines):
    p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
    p.space_after = Pt(5)
    set_run(p.add_run(), k, 14, GREEN, BODY_F, bold=True)
    set_run(p.add_run(), v, 14, CREAM, BODY_F)

# ─────────────────────────── SLIDE 2 ───────────────────────────
content("The Context", "The data exists. You just can't use it.", 2, items=[
    ("Credible sources", "CBN, NBS, World Bank."),
    ("But fragmented", "scattered PDFs and spreadsheets, published to read, not to compute."),
    ("High friction", "every question starts with manual cleaning."),
])

# ─────────────────────────── SLIDE 3 ───────────────────────────
content("The Problem", "Public data, practically closed", 3, items=[
    ("Not machine-readable", "locked in PDFs."),
    ("No common schema", "clashing units and frequencies."),
    ("No open API", "nothing free to query."),
    ("Duplicated effort", "everyone re-cleans the same data."),
])

# ─────────────────────────── SLIDE 4 ───────────────────────────
s = content("Aim & Objectives", "One store. Two front doors.", 4)
a = box(s, Inches(1.0), Inches(2.25), Inches(11.3), Inches(1.0))
ap = a.text_frame.paragraphs[0]
set_run(ap.add_run(), "Aim  ", 18, GOLD, BODY_F, bold=True)
set_run(ap.add_run(), "Aggregate Nigeria's public economic data into one standardised store, served through a dashboard and a free open API.", 18, CREAM, BODY_F)
objs = [
    "Collect  —  CBN, NBS, World Bank into one repository",
    "Standardise  —  one relational model",
    "Analyse  —  change, trend, correlation, server-side",
    "Open API  —  free, documented, HATEOAS, no auth",
    "Dashboard  —  clear, honest visualisations",
    "Evaluate  —  correctness, usability, accessibility",
]
tb = box(s, Inches(1.0), Inches(3.5), Inches(11.3), Inches(3.4)); tf = tb.text_frame
for i, v in enumerate(objs):
    p = tf.paragraphs[0] if i == 0 else tf.add_paragraph(); p.space_after = Pt(9)
    set_run(p.add_run(), f"{i+1}   ", 17, GREEN, BODY_F, bold=True)
    set_run(p.add_run(), v, 17, CREAM, BODY_F)

# ─────────────────────────── SLIDE 5 ───────────────────────────
content("Scope", "What it is — and isn't", 5, items=[
    ("Is", "a working prototype + open API, 122 indicators."),
    ("Isn't", "not national infrastructure, not a bank, not real-time."),
    ("No AI / ML", "transparent by design."),
    ("Classical analytics", "correlation, trend, forecast."),
])

# ─────────────────────────── SLIDE 6 ───────────────────────────
content("Foundations", "Built on established ideas", 6, items=[
    ("Open data", "machine-readable means actually usable."),
    ("Tidy data", "one row per observation (Wickham, 2014)."),
    ("REST & HATEOAS", "a self-describing API (Fielding, 2000)."),
    ("Honest charts", "no dual axes (Tufte; Anscombe)."),
])

# ─────────────────────────── SLIDE 7 ───────────────────────────
content("The Gap", "Nobody puts it all together", 7, items=[
    ("Global tools", "FRED, World Bank — thin Nigerian detail."),
    ("Local sources", "CBN, NBS — no API."),
    ("Paywalled aggregators", "resell the same figures."),
    ("The gap", "none combine coverage + open access + honesty."),
])

# ─────────────────────────── SLIDE 8 ───────────────────────────
content("Why Now", "Not a technical problem", 8, items=[
    ("Framework exists", "Ne-GIF since 2018."),
    ("Institutional", "agencies hoard data (Eleanya, 2026)."),
    ("Enforcement gap", "153 of 250 MDAs fail FOI (Ogunyale & Osho, 2023)."),
    ("This project", "removes the technical excuse."),
])

# ─────────────────────────── SLIDE 9 ───────────────────────────
content("Method", "Build in slices, verify each loop", 9, items=[
    ("Iterative prototyping", "model → API → dashboard → analytics."),
    ("Verify every loop", "figures checked against the database."),
    ("Not Waterfall or Scrum", "requirements emerged; solo developer."),
])

# ─────────────────────────── SLIDE 10 ───────────────────────────
content("Architecture", "One pipeline, seven stages", 10, img=FIG / "fig3_1_architecture.png",
        caption="Collect → Validate → Standardise → Store → Analyse → API → Present.")

# ─────────────────────────── SLIDE 11 ───────────────────────────
content("Data Model", "One table, every frequency", 11, img=FIG / "fig3_4_erd.png", items=[
    ("Tidy schema", "sources → indicators → observations."),
    ("One shape", "(indicator, date, value) — daily to annual."),
    ("Integrity", "keys + uniqueness kill duplicate ingestion."),
    ("Unit metadata", "no silent ₦'000-vs-₦m errors."),
], caption="Figure 3.4 — Entity-relationship diagram.")

# ─────────────────────────── SLIDE 12 ───────────────────────────
content("Open API", "HATEOAS, Level 3", 12, img=FIG / "fig4_11_hateoas_explorer.png", items=[
    ("FastAPI REST", "17 endpoints, no key."),
    ("Self-describing", "every response carries _links."),
    ("Proven live", "the HATEOAS Explorer follows them."),
    ("Machine-ready", "MCP + llms.txt for AI agents."),
], caption="Figure 4.11 — HATEOAS Explorer browsing the live API.")

# ─────────────────────────── SLIDE 13 ───────────────────────────
content("Dashboard", "One page, two audiences", 13, img=FIG / "fig4_4_analyst_dial.png", items=[
    ("Story pattern", "what happened / why / how to read it."),
    ("Reader ⇄ Analyst dial", "public and researcher, one page."),
    ("Honest encoding", "no dual axes; units stated."),
    ("100 / 100", "Lighthouse accessibility."),
], caption="Figure 4.4 — The Reader/Analyst dial revealing statistical detail.")

# ─────────────────────────── SLIDE 14 — ANALYTICS ───────────────────────────
content("Analytics", "The analytics engine", 14, img=FIG / "fig4_9_compare_significance.png", items=[
    ("Full profile", "latest, YoY, range, volatility, trend."),
    ("Correlation + significance", "Pearson r with R² and a p-value."),
    ("Correlation matrix", "12 indicators, cross-correlated at once."),
    ("Standardise & project", "z-scores + OLS trend."),
    ("No black box", "classical, checkable, reproducible."),
], caption="Figure 4.9 — Correlation reported with R² and a significance p-value.")

# ─────────────────────────── SLIDE 15 ───────────────────────────
content("In Action", "Reform Impact — takes no side", 15, img=FIG / "fig4_15_reform_impact.png", items=[
    ("June 2023", "subsidy removal + FX unification, split before/after."),
    ("Computed live", "every headline indicator, both sides."),
    ("Neutral", "critic and supporter cite the same real numbers."),
], caption="Figure 4.15 — Reform Impact: before/after June 2023, neutral readings.")

# ─────────────────────────── SLIDE 16 ───────────────────────────
content("Integrity", "It warns you when it might mislead", 16, img=FIG / "fig4_12_playground.png", items=[
    ("Spurious-correlation guard", "level r vs detrended r."),
    ("Significance ≠ strength", "kept visually separate."),
    ("Validation as a service", "the Playground — and it never writes."),
], caption="Figure 4.12 — Pipeline Playground: per-row verdicts, nothing written.")

# ─────────────────────────── SLIDE 17 ───────────────────────────
content("Testing", "Checked, not eyeballed", 17, items=[
    ("24 automated tests", "endpoints, HATEOAS, cache — all pass."),
    ("Stats validated", "p-values vs known cases."),
    ("Truth audit", "found and fixed real defects."),
    ("Robust", "survives NaN / ∞ and 5,000-row floods."),
])

# ─────────────────────────── SLIDE 18 ───────────────────────────
content("Results", "What it delivers", 18, img=FIG / "fig4_10_heatmap.png", items=[
    ("122 indicators / 12,100 obs", "one queryable store."),
    ("17 live endpoints", "HATEOAS Level 3."),
    ("100 / 100", "accessibility, zero build."),
    ("Audited correct", "figures verified against data."),
], caption="Figure 4.10 — The aggregation at a glance: 122 indicators × 1960–2026.")

# ─────────────────────────── SLIDE 19 ───────────────────────────
content("Contribution", "What's new", 19, items=[
    ("A reference implementation", "of unified Nigerian economic data."),
    ("A genuinely open API", "didn't exist in free form before."),
    ("All free tools", "reproducible from the repo alone."),
    ("A governance argument", "it was always a choice, not a barrier."),
])

# ─────────────────────────── SLIDE 20 ───────────────────────────
content("What's Next", "Where it goes", 20, items=[
    ("Automate collection", "scheduled connectors."),
    ("Expand coverage", "states, longer history."),
    ("Richer analytics", "seasonal adjustment, forecasting."),
    ("SDKs & auth tiers", "for heavier API users."),
])

# ─────────────────────────── SLIDE 21: CLOSE ───────────────────────────
s = prs.slides.add_slide(BLANK); bg(s)
accent_bar(s, Inches(0.9), Inches(2.0), Inches(0.7))
t = box(s, Inches(0.88), Inches(2.2), Inches(11.5), Inches(1.4))
set_run(t.text_frame.paragraphs[0].add_run(), "Conclusion", 40, CREAM, HEAD_F, italic=True)
c = box(s, Inches(0.95), Inches(3.35), Inches(11.4), Inches(1.6))
cp = c.text_frame.paragraphs[0]
set_run(cp.add_run(), "Nigeria's scattered, non-machine-readable public economic data need not stay that way: it can be consolidated into a correct, programmatically usable resource using only free and open-source tools.", 18, SLATE, BODY_F)
links = box(s, Inches(0.95), Inches(5.05), Inches(11.4), Inches(1.6)); lf = links.text_frame
rows = [
    ("Dashboard:  ", "antd-cr7.github.io/nigerian-dashboard"),
    ("Open API:  ", "npedata-api.onrender.com  (docs at /docs)"),
    ("Source:  ", "github.com/ANTD-CR7/nigerian-dashboard"),
]
for i, (k, v) in enumerate(rows):
    p = lf.paragraphs[0] if i == 0 else lf.add_paragraph(); p.space_after = Pt(4)
    set_run(p.add_run(), k, 14, GREEN, BODY_F, bold=True)
    set_run(p.add_run(), v, 14, GOLD, BODY_F)
ty = box(s, Inches(0.9), Inches(6.6), Inches(11), Inches(0.7))
set_run(ty.text_frame.paragraphs[0].add_run(), "Thank you.  Questions & live demonstration.", 22, CREAM, HEAD_F, italic=True)

prs.save(OUT)
print(f"Wrote {OUT}  ({OUT.stat().st_size:,} bytes, {len(prs.slides.__iter__.__self__._sldIdLst)} slides)")
