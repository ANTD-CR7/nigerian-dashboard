# NPEDATA - Budget Office of the Federation connector (Revenue + Fiscal
# Deficit pilot).
#
# Copyright 2026 Taoheed Abdulmanan Olaosebikan. Apache-2.0.
# Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
#
# budgetoffice.gov.ng is a Joomla site. Its "Quarterly Budget Implementation
# Report" category lists a per-year sub-category back to 2009, each with
# ~4 quarterly report PDFs (.../download action URLs, same Joomla-document
# shape as DMO -- no WAF encountered here, unlike DMO).
#
# Every report has a "Table 3.9: FGN Budget Expenditure and Fiscal Account"
# page -- confirmed present and identically titled in samples spanning 2018,
# 2021 and 2026, though its page number shifts between reports, so it's
# found by searching page text for the title, never a fixed page index.
#
# Column structure is positionally stable even though header wording isn't:
# every sample's table rows are [S/No, Item, PriorYearAnnualBudget,
# CurrentYearAnnualBudget, CurrentYearQuarterlyBudget, PriorYearQuarterActual,
# CurrentYearQuarterActual, Variance, Variance%]. Column index 6 is always
# the current-quarter actual value in both the 2018 and 2026 samples despite
# their header text differing.
#
# Row LABELS drift more than DMO's did -- real risk, confirmed, not
# hypothetical: Revenue is "TOTAL RETAINED REVENUE" in 2018 vs "AGGREGATE
# FEDERAL GOVERNMENT REVENUE" in 2026; "Capital Expenditure" has the year
# baked into its label ("Sub-Total (Capital 2018)"); and 2018 has two
# plausible "Total Expenditure" lines with no equivalent in 2026. Only two
# metrics are robustly identifiable across years (confirmed with the user
# before building anything else):
#   - Revenue: always the first lettered row, S/No == "A".
#   - Fiscal Deficit: always has "deficit" in its label.
# Recurrent/Capital/Total Expenditure are explicitly out of scope.
#
# The server itself is unusually slow and occasionally silently truncates:
# throughput fluctuated ~11-60KB/s across repeated requests, and one plain
# download reported HTTP 200 success while delivering only 1,055,583 of
# 2,654,060 declared bytes (per the response's own Content-Disposition
# size= parameter) -- no error anywhere in that request. _get() below
# explicitly checks the downloaded byte count against that declared size
# and raises (triggering a retry) on a mismatch, since neither a timeout
# nor an exception would otherwise catch this.

from __future__ import annotations

import calendar
import concurrent.futures
import datetime
import io
import re
import time
import urllib.request

import pdfplumber

from .base import Connector

CATEGORY_URL = "https://budgetoffice.gov.ng/index.php/resources/internal-resources/reports/quarterly-budget-implementation"

_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
_DATE_RE = re.compile(r"as at\s+(" + "|".join(_MONTHS) + r")\s+(\d{4})", re.IGNORECASE)
_SIZE_RE = re.compile(r"size=(\d+)")
_NUMBER_RE = re.compile(r"\(?-?\d[\d,]*\.\d+\)?")
_YEAR_CATEGORY_RE = re.compile(
    r'href="(/index\.php/resources/internal-resources/reports/quarterly-budget-implementation/[a-z0-9-]+)"',
    re.IGNORECASE,
)
_DOWNLOAD_LINK_RE = re.compile(r'href="(/index\.php/[a-z0-9/_-]+/download)"', re.IGNORECASE)


def _get_once(url: str, timeout: float):
    req = urllib.request.Request(url, headers={"User-Agent": "npedata-collector/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        disposition = resp.headers.get("Content-Disposition", "")
    size_match = _SIZE_RE.search(disposition)
    if size_match and len(raw) != int(size_match.group(1)):
        raise ValueError(f"truncated download: got {len(raw)} bytes, server declared {size_match.group(1)}")
    return raw


def _get(url: str, timeout: float = 300.0, attempts: int = 3, backoff: float = 15.0) -> bytes:
    """Hard per-attempt timeout via a worker thread (this server's
    confirmed throughput can drop to ~11KB/s, hence the much larger default
    timeout than the other connectors tonight) plus a backoff retry, and a
    byte-count-vs-declared-size check inside _get_once for the silent-
    truncation failure mode confirmed on this specific server."""
    last_exc: Exception | None = None
    for attempt in range(attempts):
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_get_once, url, timeout)
            try:
                return future.result(timeout=timeout * 1.5)
            except Exception as exc:
                last_exc = exc
        if attempt < attempts - 1:
            time.sleep(backoff * (2 ** attempt))
    raise last_exc


def _iter_resources():
    """Yields every quarterly Budget Implementation Report download URL,
    discovered by first finding every year sub-category (back to 2009),
    then every /download link on each year's page."""
    html = _get(CATEGORY_URL).decode("utf-8", errors="replace")
    year_paths = sorted(set(_YEAR_CATEGORY_RE.findall(html)))
    for year_path in year_paths:
        if year_path.rstrip("/").endswith("quarterly-budget-implementation"):
            continue  # the category page links back to itself
        try:
            year_html = _get(f"https://budgetoffice.gov.ng{year_path}").decode("utf-8", errors="replace")
        except Exception:
            continue
        for download_path in sorted(set(_DOWNLOAD_LINK_RE.findall(year_html))):
            yield f"https://budgetoffice.gov.ng{download_path}"


def _find_table_page(pdf):
    """The "LIST OF TABLES" table-of-contents page also mentions "Table
    3.9" and "expenditure and fiscal" in its entry title, so a text match
    alone isn't enough -- the real table page is the one that actually
    has an extractable table."""
    for page in pdf.pages:
        text = page.extract_text() or ""
        lower = text.lower()
        if "table 3.9" in lower and "expenditure and fiscal" in lower and page.extract_tables():
            return page, text
    return None, None


def _parse_number(raw: str) -> float | None:
    raw = raw.strip()
    if not raw or raw == "-":
        return None
    negative = raw.startswith("(") and raw.endswith(")")
    cleaned = raw.strip("()").replace(",", "").replace(" ", "")
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return -value if negative else value


def _parse_bir_document(raw: bytes):
    """Returns (obs_date, revenue_actual, deficit_actual), any of which may
    be None if that piece couldn't be found -- never guessed."""
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        page, text = _find_table_page(pdf)
        if page is None:
            return None, None, None

        date_match = _DATE_RE.search(text)
        if not date_match:
            return None, None, None
        month_name, year = date_match.group(1), int(date_match.group(2))
        month = next((i for i, m in enumerate(_MONTHS, start=1) if m.lower() == month_name.lower()), None)
        if month is None:
            return None, None, None
        last_day = calendar.monthrange(year, month)[1]
        obs_date = datetime.date(year, month, last_day).isoformat()

        tables = page.extract_tables()
        if not tables:
            return obs_date, None, None
        revenue, deficit = _select_revenue_and_deficit(tables[0])
        return obs_date, revenue, deficit


def _select_revenue_and_deficit(rows):
    """Revenue is always the first lettered row (S/No == "A"); Fiscal
    Deficit always has "deficit" in its label -- the only two headline
    metrics confirmed robust against this table's row-label drift across
    years. Column 6 (0-indexed) is always the current-quarter actual
    value regardless of header-text differences between years."""
    revenue = None
    deficit = None
    for row in rows:
        cells = [str(c).strip() if c is not None else "" for c in row]
        if len(cells) < 7:
            continue
        if cells[0] == "A" and revenue is None:
            revenue = _parse_number(cells[6])
        elif "deficit" in cells[1].lower() and deficit is None:
            deficit = _parse_number(cells[6])
    return revenue, deficit


class BudgetOfficeConnector(Connector):
    name = "budget_office"
    source_label = "Budget Office of the Federation"

    def fetch(self, start_year: int = 2015):
        for url in _iter_resources():
            try:
                raw = _get(url)
                obs_date, revenue, deficit = _parse_bir_document(raw)
            except Exception:
                continue
            if obs_date is None:
                continue
            if revenue is not None:
                yield {
                    "indicator_id": "budgetoffice_revenue_actual",
                    "obs_date": obs_date,
                    "value": revenue,
                    "source": "Budget Office",
                }
            if deficit is not None:
                yield {
                    "indicator_id": "budgetoffice_fiscal_deficit_actual",
                    "obs_date": obs_date,
                    "value": deficit,
                    "source": "Budget Office",
                }
