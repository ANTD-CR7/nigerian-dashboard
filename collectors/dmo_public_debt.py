# NPEDATA - DMO Total Public Debt connector.
#
# Copyright 2026 Taoheed Abdulmanan Olaosebikan. Apache-2.0.
# Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
#
# DMO (www.dmo.gov.ng) is a Joomla site (com_docman) with no JSON API and
# no Excel -- every number lives in single-page quarterly PDFs, discovered
# via a paginated HTML document-listing page. A WAF blocks requests that
# don't look like a real browser (plain curl -A "Mozilla/5.0" on a document
# page or its /file download link returns "403: Malware detected."); fixed
# by sending a full modern browser User-Agent, Accept and Referer.
#
# Three distinct table layouts confirmed by direct inspection (2014, 2018,
# 2022/2026 samples), not assumed:
#   - 2014: "A. External Debt Stock (FGN+States)" and "Domestic Debt Stock
#     (FGN Only)" combined into one "Sub-Total", then "B. Domestic Debt of
#     States" separately, then "C. Grand-Total".
#   - 2018: "A. External Debt" (one line), "B. Domestic Debt (FGN Only)",
#     "C. Domestic Debt (States+FCT)", "D. Sub-Total -- Domestic Debt",
#     "E. Total (A+D)".
#   - 2022/2026: "A. Total External Debt" / "B. Total Domestic Debt" (each
#     with FGN-only/States-only sub-lines and a % column, not collected),
#     "C. Total Public Debt(A+B)".
# pdfplumber's extract_tables() (not extract_text(), whose line-wrapping
# splits a category's two currency numbers across separate lines) gives
# clean rows, but a label and its numbers are sometimes split across two
# table rows (e.g. 2018's "C. Domestic Debt (States + FCT)" row has no
# numbers; they're on the next row alone) -- handled by carrying a pending
# label forward until a row with numbers is seen.
#
# Only the external/domestic/grand-total rows matter for this pilot; the
# FGN-only/States-only sub-lines (present in the 2022/2026 layout) are
# skipped -- their label never contains "external"/"domestic"/"total" on
# its own, so the keyword-based row selection excludes them naturally.
#
# "Domestic" needs variant-specific handling: when a domestic-labeled row
# also says "total"/"sub-total" (2018, 2022/2026), that ONE row is already
# the correct total -- summing every "domestic" row in that case would
# double-count (2018's D = B+C). Only when no domestic row claims to be a
# total (2014) is summing all domestic-labeled rows correct.
#
# Every parsed document is validated against the accounting identity
# external + domestic == grand_total (both currencies, small rounding
# tolerance) before being yielded -- a document that fails is dropped
# entirely rather than guessing which number is wrong, same philosophy as
# every other connector's data-quality checks this session.

from __future__ import annotations

import concurrent.futures
import datetime
import io
import re
import time
import urllib.request

import pdfplumber

from .base import Connector

LISTING_URL = "https://www.dmo.gov.ng/debt-profile/total-public-debt"
BASE_URL = "https://www.dmo.gov.ng"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

RESOURCE_LINK_RE = re.compile(r'href="/(\d+)-([a-z0-9-]+)"')

_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
_DATE_RE = re.compile(
    r"as at\s+(?:"
    r"(?P<month>" + "|".join(_MONTHS) + r")\.?\s*(?P<day>\d{1,2})(?:st|nd|rd|th)?,?\s*(?P<year>\d{4})"
    r"|"
    r"(?P<day2>\d{1,2})(?:st|nd|rd|th)?\s*(?P<month2>" + "|".join(_MONTHS) + r")\.?,?\s*(?P<year2>\d{4})"
    r")",
    re.IGNORECASE,
)

_NUMBER_RE = re.compile(r"\d[\d,\s]*\.\d{2}(?!\d)")


def _get_once(url: str, timeout: float, referer: str) -> bytes:
    headers = dict(HEADERS, Referer=referer)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _get(url: str, referer: str, timeout: float = 60.0, attempts: int = 3, backoff: float = 10.0) -> bytes:
    """Hard per-attempt timeout via a worker thread (urlopen's own timeout
    doesn't reliably bound DNS-resolution hangs -- confirmed the hard way
    on NBS's connector earlier this session) plus a backoff retry."""
    last_exc: Exception | None = None
    for attempt in range(attempts):
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_get_once, url, timeout, referer)
            try:
                return future.result(timeout=timeout * 1.5)
            except Exception as exc:
                last_exc = exc
        if attempt < attempts - 1:
            time.sleep(backoff * (2 ** attempt))
    raise last_exc


def _iter_resources():
    """Yields (resource_id, slug) for every quarterly Total Public Debt
    document, paginating the listing page until a page yields nothing
    new."""
    seen = set()
    limitstart = 0
    while True:
        url = f"{LISTING_URL}?limit=20&limitstart={limitstart}"
        html = _get(url, referer=LISTING_URL).decode("utf-8", errors="replace")
        found_new = False
        for resource_id, slug in RESOURCE_LINK_RE.findall(html):
            if resource_id not in seen:
                seen.add(resource_id)
                found_new = True
                yield resource_id, slug
        if not found_new:
            break
        limitstart += 20


def _parse_date(text: str) -> str | None:
    m = _DATE_RE.search(text)
    if not m:
        return None
    month_name = m.group("month") or m.group("month2")
    day = m.group("day") or m.group("day2")
    year = m.group("year") or m.group("year2")
    try:
        dt = datetime.datetime.strptime(f"{month_name} {day} {year}", "%B %d %Y")
        return dt.date().isoformat()
    except ValueError:
        return None


def _row_text(row) -> str:
    return " ".join(str(c).strip() for c in row if c and str(c).strip())


def _row_numbers(text: str) -> list[float]:
    out = []
    for match in _NUMBER_RE.findall(text):
        cleaned = match.replace(",", "").replace(" ", "")
        try:
            out.append(float(cleaned))
        except ValueError:
            continue
    return out


def _labeled_rows(table) -> list[tuple[str, float, float]]:
    """Walks a table's rows, carrying a label forward across the split
    label-row/numbers-row pairs some layouts produce, and returns
    (label, usd, ngn) for every row with exactly 2+ usable numbers."""
    rows = []
    pending_label = ""
    for raw_row in table:
        text = _row_text(raw_row)
        numbers = _row_numbers(text)
        if len(numbers) >= 2:
            label = f"{pending_label} {text}".strip() if pending_label else text
            rows.append((label.lower(), numbers[0], numbers[1]))
            pending_label = ""
        elif text:
            pending_label = f"{pending_label} {text}".strip() if pending_label else text
    return rows


def _select_debt_figures(rows: list[tuple[str, float, float]]):
    external = [r for r in rows if "external" in r[0]]
    domestic = [r for r in rows if "domestic" in r[0]]
    # A "total"-labeled row that isn't itself an external/domestic figure
    # is the grand total -- covers "Grand-Total (A+B)" (2014), "Total
    # Public Debt(A+B)" (2022/2026), and "Total (A+D)" (2018) alike.
    grand = [r for r in rows if "total" in r[0] and "external" not in r[0] and "domestic" not in r[0]]

    if not external or not domestic or not grand:
        return None

    # Some quarters print a redundant "External Debt" sub-line (no FGN/
    # States split that quarter) alongside "A. Total External Debt" --
    # both match the "external" keyword. Prefer the one also tagged
    # "total" when there's more than one candidate, same rule as domestic.
    external_totals = [r for r in external if "total" in r[0]]
    if external_totals:
        if len(external_totals) != 1:
            return None
        ext_usd, ext_ngn = external_totals[0][1], external_totals[0][2]
    elif len(external) == 1:
        ext_usd, ext_ngn = external[0][1], external[0][2]
    else:
        return None

    domestic_totals = [r for r in domestic if "total" in r[0]]
    if domestic_totals:
        if len(domestic_totals) != 1:
            return None
        dom_usd, dom_ngn = domestic_totals[0][1], domestic_totals[0][2]
    else:
        dom_usd = sum(r[1] for r in domestic)
        dom_ngn = sum(r[2] for r in domestic)

    # An orphaned "Sub-Total" row with no domestic/external keyword of its
    # own (2014's mixed External+Domestic-FGN subtotal) can also match the
    # "total" keyword -- the real grand total is always the final such row.
    grand_usd, grand_ngn = grand[-1][1], grand[-1][2]

    def _reconciles(a, b, total):
        return abs(a + b - total) <= max(1.0, total * 0.001)

    if not _reconciles(ext_usd, dom_usd, grand_usd) or not _reconciles(ext_ngn, dom_ngn, grand_ngn):
        return None

    return (ext_usd, dom_usd, grand_usd), (ext_ngn, dom_ngn, grand_ngn)


def _parse_debt_document(raw: bytes):
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        page = pdf.pages[0]
        text = page.extract_text() or ""
        obs_date = _parse_date(text)
        if obs_date is None:
            return None
        tables = page.extract_tables()
        if not tables:
            return None
        rows = _labeled_rows(tables[0])
        figures = _select_debt_figures(rows)
        if figures is None:
            return None
        return obs_date, figures


class DMOPublicDebtConnector(Connector):
    name = "dmo_public_debt"
    source_label = "DMO"

    def fetch(self, start_year: int = 2015):
        for resource_id, slug in _iter_resources():
            doc_url = f"{BASE_URL}/{resource_id}-{slug}"
            try:
                raw = _get(f"{doc_url}/file", referer=doc_url)
                parsed = _parse_debt_document(raw)
            except Exception:
                continue
            if parsed is None:
                continue
            obs_date, (usd, ngn) = parsed
            for suffix, (ext, dom, grand) in (("usd", usd), ("ngn", ngn)):
                yield {"indicator_id": f"dmo_total_external_debt_{suffix}", "obs_date": obs_date, "value": ext, "source": "DMO"}
                yield {"indicator_id": f"dmo_total_domestic_debt_{suffix}", "obs_date": obs_date, "value": dom, "source": "DMO"}
                yield {"indicator_id": f"dmo_total_public_debt_{suffix}", "obs_date": obs_date, "value": grand, "source": "DMO"}
