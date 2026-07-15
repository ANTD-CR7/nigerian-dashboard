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


def notes(slide, text):
    """Attach speaker notes — the presenter's context, never shown on screen."""
    if text:
        slide.notes_slide.notes_text_frame.text = text


def content(eyebrow, title, n, items=None, img=None, img_side="right", caption=None,
            sub=None, note=None):
    s = prs.slides.add_slide(BLANK); bg(s)
    header(s, eyebrow, title, n)
    b_text_top, b_img_top, img_top = Inches(2.7), Inches(2.55), Inches(2.35)
    if sub:
        sb = box(s, Inches(0.92), Inches(1.92), Inches(11.6), Inches(0.7))
        set_run(sb.text_frame.paragraphs[0].add_run(), sub, 15, GOLD, BODY_F, italic=True)
        b_text_top, b_img_top, img_top = Inches(3.15), Inches(3.05), Inches(2.85)
    if img and items:
        # split: bullets left, image right
        bullets(s, items, top=b_img_top, left=Inches(1.0), width=Inches(6.0), size=18, gap=13)
        add_image(s, img, Inches(7.25), img_top, Inches(5.4), Inches(4.0))
    elif img:
        add_image(s, img, Inches(1.4), img_top, Inches(10.5), Inches(4.2))
    elif items:
        bullets(s, items, top=b_text_top, size=22, gap=18)
    if caption:
        c = box(s, Inches(1.0), Inches(6.9), Inches(11.0), Inches(0.4))
        cp = c.text_frame.paragraphs[0]
        set_run(cp.add_run(), caption, 11, SLATE, BODY_F, italic=True)
    notes(s, note)
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
notes(s, "Greet the panel, give my name and the project title in one sentence: a platform that "
         "pulls Nigeria's scattered public economic data into one place and serves it to both "
         "people and programs. Keep this to about twenty seconds, then move on.")

# ─────────────────────────── SLIDE 2 ───────────────────────────
content("The Context", "The data exists. You just can't use it.", 2,
    sub="The raw material is reliable; its published form is the problem.",
    items=[
        ("Credible sources", "CBN, NBS, World Bank."),
        ("But fragmented", "scattered PDFs and spreadsheets, published to read, not to compute."),
        ("High friction", "every question starts with manual cleaning."),
    ],
    note="Open here. The raw material is not the problem: the CBN, NBS and World Bank produce "
         "reliable figures. The problem is form, PDFs and inconsistent spreadsheets, so anyone "
         "who wants to analyse the data first pays a friction cost, locating and cleaning it by "
         "hand before any real work begins. Removing that friction is what this project is about.")

# ─────────────────────────── SLIDE 3 ───────────────────────────
content("The Problem", "Public data, practically closed", 3,
    sub="Four concrete barriers turn technically-public data into practically-unusable data.",
    items=[
        ("Not machine-readable", "locked in PDFs."),
        ("No common schema", "clashing units and frequencies."),
        ("No open API", "nothing free to query."),
        ("Duplicated effort", "everyone re-cleans the same data."),
    ],
    note="These four are the specific problems I target, and each maps to a later design "
         "decision: not machine-readable maps to the pipeline; no common schema to the tidy "
         "observations model; no open API to the FastAPI HATEOAS API; duplicated effort to one "
         "shared, reusable store. Keep it to these four, do not read every word.")

# ─────────────────────────── SLIDE 4 ───────────────────────────
s = content("Aim & Objectives", "One store. Two front doors.", 4,
    note="State the aim in one breath, then note the six objectives map one-to-one onto the "
         "architecture I am about to show: collect, standardise, analyse, API, dashboard, "
         "evaluate. If asked, each objective was met, and the evaluation objective is the "
         "testing chapter.")
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
content("Scope", "What it is — and isn't", 5,
    sub="Being explicit about the boundary is deliberate — it pre-empts the hard questions.",
    items=[
        ("Is", "a working prototype + open API, 122 indicators."),
        ("Isn't", "not national infrastructure, not a bank, not real-time."),
        ("No AI / ML", "transparent by design."),
        ("Classical analytics", "correlation, trend, forecast."),
    ],
    note="This is my honesty slide, and I say it plainly: a working prototype and a controlled "
         "case study, not national infrastructure, not a bank, not real-time, and no AI, by "
         "choice, because the goal is transparency and trust rather than prediction. Saying this "
         "early defuses the is-this-a-national-system line of questioning before it starts.")

# ─────────────────────────── SLIDE 6 ───────────────────────────
content("Foundations", "Built on established ideas", 6,
    sub="Every design choice traces to a recognised principle, not personal preference.",
    items=[
        ("Open data", "machine-readable means actually usable."),
        ("Tidy data", "one row per observation (Wickham, 2014)."),
        ("REST & HATEOAS", "a self-describing API (Fielding, 2000)."),
        ("Honest charts", "no dual axes (Tufte; Anscombe)."),
    ],
    note="If challenged on any design decision, I can name its source: tidy data from Wickham, "
         "REST and HATEOAS from Fielding, honest visualisation from Tufte and Anscombe, the "
         "open-data principles. The project is applied engineering on an established base, not "
         "invented from scratch, which is a strength, not a weakness.")

# ─────────────────────────── SLIDE 7 ───────────────────────────
content("The Gap", "Nobody puts it all together", 7,
    sub="Strong systems exist on each side; none combine all three properties at once.",
    items=[
        ("Global tools", "FRED, World Bank — thin Nigerian detail."),
        ("Local sources", "CBN, NBS — no API."),
        ("Paywalled aggregators", "resell the same figures."),
        ("The gap", "none combine coverage + open access + honesty."),
    ],
    note="I am not claiming these systems are bad, FRED and the World Bank are excellent. I am "
         "claiming one specific empty niche: granular Nigerian data, free machine access, and "
         "statistical-integrity features, together. That combination is what is missing, and it "
         "is what I built. Frame it as a niche, not a criticism of anyone.")

# ─────────────────────────── SLIDE 8 ───────────────────────────
content("Why Now", "Not a technical problem", 8,
    sub="Every claim here is drawn from published sources, not personal opinion.",
    items=[
        ("Framework exists", "Ne-GIF since 2018."),
        ("Institutional", "data is treated as an asset (Eleanya, 2026)."),
        ("Enforcement gap", "153 of 250 MDAs fell below the FOI benchmark (Ogunyale & Osho, 2023)."),
        ("This project", "removes the technical excuse."),
    ],
    note="Keep this evidence-based and attributed, and do not editorialise about government. I am "
         "reporting published work: the interoperability framework exists since 2018, an audit "
         "found 153 of 250 agencies below the FOI benchmark, and the 2023 Data Protection Act "
         "set a precedent for enforcement. My point is narrow and technical: the barrier is not "
         "engineering, which a single-student build in one year demonstrates. If a panellist "
         "raises politics, return to that narrow point.")

# ─────────────────────────── SLIDE 9 ───────────────────────────
content("Method", "Build in slices, verify each loop", 9,
    sub="An iterative prototype fits a solo project whose requirements emerged during the build.",
    items=[
        ("Iterative prototyping", "model → API → dashboard → analytics."),
        ("Verify every loop", "figures checked against the database."),
        ("Not Waterfall or Scrum", "requirements emerged; solo developer."),
    ],
    note="Justify the methodology if asked: iterative and incremental, because I could not know "
         "every source quirk up front and I am one developer, so Waterfall and full team Scrum "
         "both fit poorly. The discipline that mattered was verifying every displayed figure "
         "against the database each iteration, which is why design and testing are so linked.")

# ─────────────────────────── SLIDE 10 ───────────────────────────
content("Architecture", "One pipeline, seven stages", 10, img=FIG / "fig3_1_architecture.png",
    sub="The core contribution: a pipeline that transforms the data, not a site that re-displays it.",
    caption="Collect → Validate → Standardise → Store → Analyse → API → Present.",
    note="This diagram is the heart of the project, walk it left to right: collect, validate, "
         "standardise, store, analyse, then expose two ways, API and dashboard. Dwell on validate "
         "and standardise, because that is where the value is added and what separates this from "
         "a re-display of the source sites.")

# ─────────────────────────── SLIDE 11 ───────────────────────────
content("Data Model", "One table, every frequency", 11, img=FIG / "fig3_4_erd.png",
    sub="Separating the value from its metadata lets one table hold every series.",
    items=[
        ("Tidy schema", "sources → indicators → observations."),
        ("One shape", "(indicator, date, value) — daily to annual."),
        ("Integrity", "keys + uniqueness kill duplicate ingestion."),
        ("Unit metadata", "no silent ₦'000-vs-₦m errors."),
    ], caption="Figure 3.4 — Entity-relationship diagram.",
    note="The design trick is separating the value from its metadata. One observations table, "
         "shape indicator-date-value, lets any frequency coexist and be queried by one engine. "
         "The uniqueness constraint makes duplicate ingestion structurally impossible, and "
         "per-series units prevent the thousands-versus-millions error I actually caught and "
         "fixed during the build.")

# ─────────────────────────── SLIDE 12 ───────────────────────────
content("Open API", "HATEOAS, Level 3", 12, img=FIG / "fig4_11_hateoas_explorer.png",
    sub="A free, self-describing REST API — the machine access the sources don't provide.",
    items=[
        ("FastAPI REST", "17 endpoints, no key."),
        ("Self-describing", "every response carries _links."),
        ("Proven live", "the HATEOAS Explorer follows them."),
        ("Machine-ready", "MCP + llms.txt for AI agents."),
    ], caption="Figure 4.11 — HATEOAS Explorer browsing the live API.",
    note="HATEOAS Level 3 means every response embeds a _links block, so the whole API is "
         "navigable from the root with no documentation, and I can prove it live with the "
         "Explorer. This is what makes it a platform others can build on, not just a website. "
         "Very few APIs reach Level 3, so this is a genuine strength to claim.")

# ─────────────────────────── SLIDE 13 ───────────────────────────
content("Dashboard", "One page, two audiences", 13, img=FIG / "fig4_4_analyst_dial.png",
    sub="One honest interface that serves both the public and researchers.",
    items=[
        ("Story pattern", "what happened / why / how to read it."),
        ("Reader ⇄ Analyst dial", "public and researcher, one page."),
        ("Honest encoding", "no dual axes; units stated."),
        ("100 / 100", "Lighthouse accessibility."),
    ], caption="Figure 4.4 — The Reader/Analyst dial revealing statistical detail.",
    note="The Reader/Analyst dial is the interface innovation: one page, one codebase, two "
         "depths, so I never maintain forked interfaces. Honest encoding throughout, no dual "
         "axes and units always stated, and a verified 100/100 Lighthouse accessibility score.")

# ─────────────────────────── SLIDE 14 — ANALYTICS ───────────────────────────
content("Analytics", "The analytics engine", 14, img=FIG / "fig4_9_compare_significance.png",
    sub="Inferential, not just descriptive — strength and reliability reported together.",
    items=[
        ("Full profile", "latest, YoY, range, volatility, trend."),
        ("Correlation + significance", "Pearson r with R² and a p-value."),
        ("Correlation matrix", "12 indicators, cross-correlated at once."),
        ("Standardise & project", "z-scores + OLS trend."),
        ("No black box", "classical, checkable, reproducible."),
    ], caption="Figure 4.9 — Correlation reported with R² and a significance p-value.",
    note="This answers the does-it-actually-do-analytics question directly. Any of 122 indicators "
         "gets a full live profile; correlations come with R-squared and a p-value; the matrix "
         "cross-correlates 12 headline series at once. Classical and reproducible with no black "
         "box is a deliberate transparency choice, not a shortcoming, and I should say so.")

# ─────────────────────────── SLIDE 15 ───────────────────────────
content("In Action", "Reform Impact — takes no side", 15, img=FIG / "fig4_15_reform_impact.png",
    sub="The aggregation applied to a live debate, without taking a political side.",
    items=[
        ("June 2023", "subsidy removal + FX unification, split before/after."),
        ("Computed live", "every headline indicator, both sides."),
        ("Neutral", "critic and supporter cite the same real numbers."),
    ], caption="Figure 4.15 — Reform Impact: before/after June 2023, neutral readings.",
    note="Handle this one calmly and stay neutral. The platform splits every headline indicator "
         "before and after June 2023 and lets a critic and a supporter both cite real numbers. If "
         "a panellist pushes a political view, I do not argue it; I show that the neutrality is "
         "the point, the tool makes the data checkable, it does not settle the argument.")

# ─────────────────────────── SLIDE 16 ───────────────────────────
content("Integrity", "It warns you when it might mislead", 16, img=FIG / "fig4_12_playground.png",
    sub="The differentiator: a tool that flags when a result may be misleading.",
    items=[
        ("Spurious-correlation guard", "level r vs detrended r."),
        ("Significance ≠ strength", "kept visually separate."),
        ("Validation as a service", "the Playground — and it never writes."),
    ], caption="Figure 4.12 — Pipeline Playground: per-row verdicts, nothing written.",
    note="Lead with the integrity story, it is my strongest point. The spurious-correlation guard "
         "compares level r to detrended r, for example CBN assets versus currency drops from 0.81 "
         "to 0.03 and is flagged. Significance is kept separate from strength, and the validation "
         "layer is itself a public service that never writes to the database.")

# ─────────────────────────── SLIDE 17 ───────────────────────────
content("Testing", "Checked, not eyeballed", 17,
    sub="Correctness is demonstrated, not asserted.",
    items=[
        ("24 automated tests", "endpoints, HATEOAS, cache — all pass."),
        ("Stats validated", "p-values vs known cases."),
        ("Truth audit", "found and fixed real defects."),
        ("Robust", "survives NaN / ∞ and 5,000-row floods."),
    ],
    note="24 automated Pytest tests, all passing, and that number matches the report exactly. "
         "Independent statistical validation against known cases, and a data-truthfulness audit "
         "that found and fixed real defects including a data-censoring routine and a "
         "times-thousand unit mislabel. If asked how I know it is right, this slide is the answer.")

# ─────────────────────────── SLIDE 18 ───────────────────────────
content("Results", "What it delivers", 18, img=FIG / "fig4_10_heatmap.png",
    sub="Concrete, verifiable outputs mapped to the objectives.",
    items=[
        ("122 indicators / 12,100 obs", "one queryable store."),
        ("17 live endpoints", "HATEOAS Level 3."),
        ("100 / 100", "accessibility, zero build."),
        ("Audited correct", "figures verified against data."),
    ], caption="Figure 4.10 — The aggregation at a glance: 122 indicators × 1960–2026.",
    note="Tie each result back to an objective from slide four: the store and coverage, the live "
         "endpoints, the accessibility score, and the audit confirming displayed figures match "
         "stored data. These are all verifiable on the live site if asked.")

# ─────────────────────────── SLIDE 19 ───────────────────────────
content("Contribution", "What's new", 19,
    sub="A reusable artefact and an argument, both reproducible from the repository.",
    items=[
        ("A reference implementation", "of unified Nigerian economic data."),
        ("A genuinely open API", "no freely accessible equivalent found."),
        ("All free tools", "reproducible from the repo alone."),
        ("A governance argument", "it was always a choice, not a barrier."),
    ],
    note="State the contribution modestly and precisely: a free, open, reproducible reference "
         "implementation with a HATEOAS API, for which I found no freely accessible equivalent. "
         "I deliberately say no equivalent found rather than first ever, because an absolute "
         "claim is the kind a panel can pick apart.")

# ─────────────────────────── SLIDE 20 ───────────────────────────
content("What's Next", "Where it goes", 20,
    sub="Known limitations, each paired with a concrete next step.",
    items=[
        ("Automate collection", "scheduled connectors."),
        ("Expand coverage", "states, longer history."),
        ("Richer analytics", "seasonal adjustment, forecasting."),
        ("SDKs & auth tiers", "for heavier API users."),
    ],
    note="Framing limitations as planned next steps shows I understand the boundaries rather than "
         "being caught by them: automate collection, expand coverage, richer analytics, and SDKs "
         "with auth tiers. Owning these openly stops them being used against me.")

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
notes(s, "Close on the integrity line, that a platform which tells you when it might be "
         "misleading you is the real contribution. Thank the panel and invite questions and the "
         "live demonstration. Have both the live site and the offline backup open and ready.")

prs.save(OUT)
print(f"Wrote {OUT}  ({OUT.stat().st_size:,} bytes, {len(prs.slides.__iter__.__self__._sldIdLst)} slides)")
