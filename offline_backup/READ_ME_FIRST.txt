======================================================================
  NPEDATA  —  OFFLINE BACKUP COPY   (works with NO internet at all)
======================================================================

This is a fully self-contained copy of the NPEDATA dashboard for your
defence, in case there is no network at the venue. All 122 indicators
and ~12,100 observations are stored locally (offline/snapshot.js), and
the chart libraries are bundled (vendor/), so every data page and chart
works with the internet completely disconnected.

Snapshot taken: July 2026.


HOW TO USE
----------
EASIEST:   double-click  index.html   ->  it opens in your browser and
           works, no setup, no internet.

If a browser ever blocks the double-click method (rare), use the server:
           double-click  serve.bat
           then open      http://localhost:8850   in your browser.


WHAT WORKS OFFLINE
------------------
- Homepage: live KPI cards, coverage strip, the pipeline section.
- Every indicator page and chart (inflation, exchange rate, GDP,
  reserves, multi-currency, CBN balance sheet, NFEM, etc.) with event
  markers, range presets and the Reader/Analyst dial.
- Analytics: correlation, the 12-indicator correlation matrix, Compare.
- Reform Impact: the before/after tables, purchasing-power and sector
  sections.
- Data Sources: the 122 x years coverage heatmap.
- Briefing Studio and the Pipeline Playground (CSV validation runs
  locally and still refuses to write).
- Command-palette search (Ctrl/Cmd-K).


WHAT NEEDS THE LIVE SERVER (won't be identical offline)
-------------------------------------------------------
- The API Docs "Try it" buttons and HATEOAS Explorer return snapshot
  data offline, but are best shown live. The Swagger /docs page needs
  the Render server (internet).
- Fonts fall back to system fonts offline; the layout is unchanged.


RECOMMENDED PLAN FOR THE DEFENCE
--------------------------------
1. FIRST CHOICE: the LIVE site over your phone's hotspot
   -> antd-cr7.github.io/nigerian-dashboard  (real, live, updates).
2. NO SIGNAL AT ALL: this folder -> double-click index.html.
3. ULTIMATE FALLBACK: the slide deck
   -> docs/NPEDATA_Defense_Slides.pptx  (screenshots, cannot fail).

You are covered three ways. Good luck.
======================================================================
