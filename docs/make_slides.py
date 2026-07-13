"""Build a 20-slide NPEDATA defence deck (16:9) in the platform's palette.
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
    set_run(np_.add_run(), f"{n:02d} / 20", 10, SLATE, BODY_F)


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
        bullets(s, items, top=Inches(2.4), left=Inches(1.0), width=Inches(6.0), size=16, gap=9)
        add_image(s, img, Inches(7.25), Inches(2.35), Inches(5.4), Inches(4.4))
    elif img:
        add_image(s, img, Inches(1.4), Inches(2.35), Inches(10.5), Inches(4.4))
    elif items:
        bullets(s, items, size=18)
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
content("Chapter One", "Introduction & Background", 2, items=[
    ("Economic data is a public good", "decisions by government, researchers, journalists, developers and the public depend on timely, reliable figures."),
    ("Nigeria's data is produced by credible institutions", "the CBN and NBS, supplemented by the World Bank."),
    ("But it is fragmented", "scattered across many sites and published for reading, not computation — PDF bulletins, spreadsheets, inconsistent web tables."),
    ("The result is a high “friction cost”", "combining even two indicators means locating, reconciling and aligning them by hand before any analysis can begin."),
    ("This project", "consolidates and standardises that data, then republishes it as a dashboard for people and an open API for programs."),
])

# ─────────────────────────── SLIDE 3 ───────────────────────────
content("Chapter One", "Statement of the Problem", 3, items=[
    ("Fragmentation", "no common point of access across institutional sites and documents."),
    ("Not machine-readable", "locked in PDFs and inconsistent spreadsheets; every reuse starts with manual extraction."),
    ("Inconsistent structure & units", "daily to annual frequencies; ₦'000, ₦ millions, %, USD — no unified schema."),
    ("No open API", "nothing free, documented and authentication-free to query programmatically."),
    ("Minimal presentation", "rarely beyond a static figure — little comparison or plain-language interpretation."),
    ("Duplicated effort", "every user repeats the same collection and cleaning work."),
])

# ─────────────────────────── SLIDE 4 ───────────────────────────
s = content("Chapter One", "Aim & Objectives", 4)
a = box(s, Inches(1.0), Inches(2.2), Inches(11.2), Inches(1.0))
ap = a.text_frame.paragraphs[0]
set_run(ap.add_run(), "Aim:  ", 17, GOLD, BODY_F, bold=True)
set_run(ap.add_run(), "To design and develop a web-based platform that aggregates Nigeria's public economic data into a single standardised store, accessible through an interactive dashboard and a free, open API.", 17, CREAM, BODY_F)
objs = [
    ("", "Collect indicators from the CBN, NBS and World Bank into one repository."),
    ("", "Design a unified relational model standardising indicators, sources and observations."),
    ("", "Implement server-side analytics — change, year-on-year, trend and correlation."),
    ("", "Build a free, documented REST API with HATEOAS and no authentication."),
    ("", "Build an interactive dashboard with clear, accurate visualisations."),
    ("", "Test and evaluate for correctness, usability and accessibility."),
]
tb = box(s, Inches(1.0), Inches(3.3), Inches(11.3), Inches(3.5)); tf = tb.text_frame
for i, (_, v) in enumerate(objs):
    p = tf.paragraphs[0] if i == 0 else tf.add_paragraph(); p.space_after = Pt(7)
    set_run(p.add_run(), f"{i+1}.  ", 15, GREEN, BODY_F, bold=True)
    set_run(p.add_run(), v, 15, CREAM, BODY_F)

# ─────────────────────────── SLIDE 5 ───────────────────────────
content("Chapter One", "Scope & Limitations", 5, items=[
    ("Scope", "collection, standardisation, storage, analysis, API exposure and visualisation."),
    ("Coverage", "122 indicators and ~12,100 observations — a controlled case study, extensible via CSV/API ingestion."),
    ("Manual collection", "source files are ingested manually; figures reflect the latest snapshot, not a live feed."),
    ("Bounded by sources", "coverage stops where the sources stop (e.g. the CBN annual statement ends in 2012)."),
    ("Classical analytics", "correlation, OLS trend and linear forecast — no machine learning, by design."),
    ("Not national infrastructure", "a student-built reference implementation, not an official system."),
])

# ─────────────────────────── SLIDE 6 ───────────────────────────
content("Chapter Two", "Literature Review — Key Concepts", 6, items=[
    ("Open data", "a public good; machine-processability and accessibility do the heavy lifting (Open Gov Working Group, 2007)."),
    ("Tidy data", "one observation per row, metadata separate — lets any-frequency series share one table (Wickham, 2014)."),
    ("REST & HATEOAS", "the Richardson Maturity Model; Level 3 makes an API self-describing (Fielding, 2000)."),
    ("Honest visualisation", "no dual axes, no truncation; plots must be trustworthy (Tufte, 1983; Anscombe, 1973)."),
    ("Classical statistics", "Pearson r with a Student-t p-value; spurious-trend caution (Granger & Newbold, 1974)."),
])

# ─────────────────────────── SLIDE 7 ───────────────────────────
content("Chapter Two", "Related Systems & the Gap", 7, items=[
    ("FRED / World Bank / IMF", "excellent access, but coarse or minimal Nigerian granularity."),
    ("Trading Economics / Statista", "largely paywalled; re-sell the same CBN/NBS figures."),
    ("CBN & NBS", "authoritative sources — but PDF/Excel, no public API."),
    ("data.gov.ng / BudgIT", "civic appetite exists, but focused on budgets, not usable economic time series."),
    ("The gap", "no system combines granular Nigerian coverage, open machine access AND built-in statistical honesty."),
])

# ─────────────────────────── SLIDE 8 ───────────────────────────
content("Chapter Two", "Why Hasn't This Been Built?", 8, items=[
    ("Not a technical problem", "Nigeria has had an e-Government Interoperability Framework since 2018."),
    ("Institutional cause", "agencies treat held data as a source of value and are reluctant to share it (Eleanya, 2026)."),
    ("A legislative gap too", "the FOI Act mandates publication since 2011, yet 153 of 250 MDAs failed a compliance benchmark in 2022 (Ogunyale & Osho, 2023)."),
    ("Precedent for a fix", "the 2023 Data Protection Act created the NDPC — a regulator with real enforcement power (Falore & Jidda, 2026)."),
    ("This project", "removes the technical excuse — one student, free tools, one academic year."),
])

# ─────────────────────────── SLIDE 9 ───────────────────────────
content("Chapter Three", "Methodology", 9, items=[
    ("Iterative & incremental prototyping", "data model → API → dashboard → analytics → refinement."),
    ("Why not Waterfall", "requirements were not fully known up front; source quirks emerged during ingestion."),
    ("Why not team Scrum", "the ceremony overhead is wasted on a single-developer project."),
    ("Verification every iteration", "displayed figures cross-checked against the database before new work began."),
    ("Consequence", "this is why the design and testing chapters are so closely connected."),
])

# ─────────────────────────── SLIDE 10 ───────────────────────────
content("Chapter Three", "System Architecture", 10, img=FIG / "fig3_1_architecture.png",
        caption="Figure 3.1 — Seven-stage pipeline: Collect → Validate → Standardise → Store → Analyse → API → Present.")

# ─────────────────────────── SLIDE 11 ───────────────────────────
content("Chapter Three", "Database Design", 11, img=FIG / "fig3_4_erd.png", items=[
    ("Tidy / long schema", "sources → indicators → observations."),
    ("One observations table", "holds daily-to-annual series in one shape: (indicator_id, obs_date, value)."),
    ("Integrity", "typed columns, foreign keys, and a uniqueness constraint that makes duplicate ingestion impossible."),
    ("Unit metadata", "carried per series — the key to avoiding silent ₦'000-vs-₦m errors."),
], caption="Figure 3.4 — Entity-relationship diagram.")

# ─────────────────────────── SLIDE 12 ───────────────────────────
content("Chapter Four", "The Open API — HATEOAS Level 3", 12, img=FIG / "fig4_11_hateoas_explorer.png", items=[
    ("FastAPI, versioned REST", "17 read endpoints, no key, open CORS."),
    ("HATEOAS", "every response carries a _links block — the whole API is navigable from the root."),
    ("Level 3 demonstrated live", "the HATEOAS Explorer follows _links in the browser."),
    ("Machine-ready", "MCP server + llms.txt for AI-agent access."),
], caption="Figure 4.11 — HATEOAS Explorer browsing the live API.")

# ─────────────────────────── SLIDE 13 ───────────────────────────
content("Chapter Four", "The Dashboard", 13, img=FIG / "fig4_4_analyst_dial.png", items=[
    ("Storytelling pattern", "headline stat, what happened / why it matters / how to read it, chart, table."),
    ("Reader / Analyst dial", "one page serves the public and researchers — no forked interface."),
    ("Honest encoding", "no dual axes; aligned panels or z-scores; units always stated."),
    ("Accessible", "WCAG 2.1 AA; 100/100 Lighthouse."),
], caption="Figure 4.4 — The Reader/Analyst dial revealing statistical detail.")

# ─────────────────────────── SLIDE 14 ───────────────────────────
content("Chapter Four", "Feature — Reform Impact", 14, img=FIG / "fig4_15_reform_impact.png", items=[
    ("The 2023 reforms", "fuel-subsidy removal and FX unification, split before/after June 2023."),
    ("Computed live", "every headline indicator averaged on each side of the reform."),
    ("Takes no side", "a critic and a supporter can both cite real numbers on one page."),
    ("Neutrality is the contribution", "the platform makes the data checkable, not the argument settled."),
], caption="Figure 4.15 — Reform Impact: before/after June 2023, neutral critic/supporter readings.")

# ─────────────────────────── SLIDE 15 ───────────────────────────
content("Chapter Four", "Honesty Guards & Validation", 15, img=FIG / "fig4_12_playground.png", items=[
    ("Spurious-correlation warning", "level r vs detrended r — flags shared-trend illusions."),
    ("Significance separated from strength", "a weak r can still be significant in a large sample."),
    ("Validation as a service", "the Pipeline Playground judges any CSV row-by-row — and never writes."),
    ("Demo-safe by default", "write paths are structurally disabled."),
], caption="Figure 4.12 — Pipeline Playground: per-row verdicts, nothing written.")

# ─────────────────────────── SLIDE 16 ───────────────────────────
content("Chapter Four", "Testing & Validation", 16, items=[
    ("24 automated unit tests (Pytest)", "read endpoints, demo-safe ingestion, TTL cache, and the HATEOAS _links — all pass."),
    ("Independent statistical validation", "p-values checked against known cases; the value formatter unit-tested across every unit type."),
    ("Data-truthfulness audit", "found and fixed real defects: a data-censoring routine, unit mislabels (×1000), a mis-titled “inverse” chart, a year-mismatched comparison."),
    ("Accessibility & robustness", "WCAG AA contrast; adversarial inputs (NaN/∞, 5,000-row floods) survive."),
])

# ─────────────────────────── SLIDE 17 ───────────────────────────
content("Chapter Four", "Results", 17, img=FIG / "fig4_10_heatmap.png", items=[
    ("122 indicators, ~12,100 observations", "aggregated into one queryable store."),
    ("17 live API endpoints", "documented, HATEOAS Level 3, all passing."),
    ("100/100 Lighthouse", "accessibility, on a zero-build static frontend."),
    ("Correct by audit", "displayed figures verified against stored data."),
], caption="Figure 4.10 — The aggregation at a glance: 122 indicators × 1960–2026, computed live.")

# ─────────────────────────── SLIDE 18 ───────────────────────────
content("Chapter Five", "Contribution to Knowledge", 18, items=[
    ("A working reference implementation", "of a unified Nigerian public-economic-data platform."),
    ("With a genuinely open, HATEOAS-level API", "an artefact that did not previously exist in freely accessible form."),
    ("Built entirely from free & open-source tools", "reproducible from the repository alone."),
    ("Evidence for a governance argument", "that unifying this data was always a choice, not an engineering barrier."),
])

# ─────────────────────────── SLIDE 19 ───────────────────────────
content("Chapter Five", "Limitations & Future Work", 19, items=[
    ("Automate collection", "scheduled connectors to source portals, ending manual re-ingestion."),
    ("Expand coverage", "more indicators, state-level data, longer historical series."),
    ("Richer analytics", "seasonal adjustment and proper forecasting — keeping transparency."),
    ("Authentication tiers & rate limiting", "for heavier API consumers."),
    ("Client SDKs", "Python / JavaScript packages to ease adoption."),
])

# ─────────────────────────── SLIDE 20: CLOSE ───────────────────────────
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
