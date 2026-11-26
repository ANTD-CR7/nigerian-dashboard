# NPEDATA - NBS state-level CPI connector (pilot).
#
# Copyright 2026 Taoheed Abdulmanan Olaosebikan. Apache-2.0.
# Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
#
# NBS (microdata.nigerianstat.gov.ng) runs NADA, a document/survey metadata
# catalog, not a time-series API like CBN's. There is no numeric endpoint --
# getting real numbers means downloading NBS's monthly CPI Excel reports and
# parsing them. This connector targets only Table-5 ("Combined Urban And
# Rural State Consumer Price Index") from the CPI dataset (catalog idno
# NGA-NBS-CPI) -- the one genuinely new thing NBS has that CBN's republished
# inflation feed (cbn_inflation.py) doesn't: a 36-state breakdown of Food and
# All-Items CPI. Table1-4 (national/sectoral) are excluded -- they duplicate
# cbn_inflation's existing ids. The %-change columns in Table-5 are also
# excluded -- only the three index-level columns are collected.
#
# Resource discovery: GET .../api/catalog/resources/NGA-NBS-CPI returns a
# stable JSON list of every monthly resource, each with a "title" in the
# reliable form "<Month> <Year> CPI Tables"/"CPI Report" (dcdate is often
# blank, so the date comes from the title, not dcdate). filename tells us
# what's inside: .pdf-only resources are the narrative report (skip,
# no data); .xlsx-only resources (Nov 2024-Jun 2025) have the data sheet
# directly; .zip resources (Jul 2025-present) bundle a .pdf and a
# cpi_1New*.xlsx together.
#
# Downloading needs a generous timeout and a retry: a 30s timeout once
# looked like a missing-cookie/session problem but was just a slow server
# (no cookies or Referer are actually required). Separately, in production
# two consecutive real-data runs each fetched only the first of 31
# resources before every later request failed -- diagnosed down to DNS
# resolution (getaddrinfo) itself hanging for 4-9x the stated urlopen
# timeout (one request logged 266.8s against a 30s timeout), a known
# urllib/OS gap where the timeout argument doesn't bound that phase. _get()
# below enforces its own hard deadline via a worker thread rather than
# trusting urlopen's timeout, plus a backoff retry for the transient local
# network blip this turned out to be.
#
# Two sheet layouts exist across the file history, confirmed by direct
# inspection of both a new-era and an old-era file, not assumed:
#   - New era ("Base Period: 2024 = 100", essentially every file): title at
#     row 1, 3 date columns at row 3, single header row 4, data from row 5.
#   - Old era ("Base Period: November 2009 = 100", confirmed present in the
#     Nov 2024 "CPI Tables" resource despite being published the same month
#     CPI was rebased): everything shifted down 6 blank rows, header split
#     across two rows instead of one, data from row 12.
# Column *positions* are identical in both eras (state name, then three
# Food/All-Items pairs: 12-months-ago, prior-month, current-month) -- only
# the row offset and base period differ, so this parses by anchoring on the
# "Table 5" title text and the 3-date row rather than hardcoding row numbers.
#
# One stray glitch found in the old-era file: the "12-months-ago" date cell
# showed day 03 instead of 01 -- obs_date is built from (year, month) only,
# never the exact day.
#
# Index values are not retroactively rebased -- old-era and new-era values
# for the same state jump discontinuously at the boundary. Stored as-is,
# same as CBN's own inflation indices already are on this platform.
#
# Every run fetches and parses all resources (not just the newest) --
# simplicity and idempotency (via normalize()'s last-write-wins dedup) over
# efficiency. This also means each month's value is corroborated by up to 3
# separate files (as the current month, then as "prior month" next file,
# then as "12-months-ago" the file after) -- free redundancy if NBS ever
# pulls a file.

from __future__ import annotations

import concurrent.futures
import datetime
import io
import json
import re
import time
import urllib.request
import zipfile

import openpyxl

from .base import Connector

RESOURCES_URL = "https://microdata.nigerianstat.gov.ng/index.php/api/catalog/resources/NGA-NBS-CPI"

_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)
TITLE_RE = re.compile(r"^(" + "|".join(_MONTHS) + r")\s+(\d{4})\s+CPI\s+(Tables|Report)\b")

# Exact state names as they appear in Table-5's own "State" column: 36
# states plus the FCT ("Abuja"), 37 entries in all. "Nassarawa" (double-s)
# is an alternate spelling confirmed present in at least the Nov 2024
# old-era file -- same state as "Nasarawa", mapped to the same slug.
STATE_SLUGS = {
    "Abia": "abia", "Abuja": "fct_abuja", "Adamawa": "adamawa", "Akwa Ibom": "akwa_ibom",
    "Anambra": "anambra", "Bauchi": "bauchi", "Bayelsa": "bayelsa", "Benue": "benue",
    "Borno": "borno", "Cross River": "cross_river", "Delta": "delta", "Ebonyi": "ebonyi",
    "Edo": "edo", "Ekiti": "ekiti", "Enugu": "enugu", "Gombe": "gombe", "Imo": "imo",
    "Jigawa": "jigawa", "Kaduna": "kaduna", "Kano": "kano", "Katsina": "katsina",
    "Kebbi": "kebbi", "Kogi": "kogi", "Kwara": "kwara", "Lagos": "lagos",
    "Nasarawa": "nasarawa", "Nassarawa": "nasarawa", "Niger": "niger", "Ogun": "ogun",
    "Ondo": "ondo", "Osun": "osun", "Oyo": "oyo", "Plateau": "plateau", "Rivers": "rivers",
    "Sokoto": "sokoto", "Taraba": "taraba", "Yobe": "yobe", "Zamfara": "zamfara",
}


def _get_once(url: str, timeout: float) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "npedata-collector/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _get(url: str, timeout: float = 90.0, attempts: int = 3, backoff: float = 10.0) -> bytes:
    """GET with a real hard timeout and a retry.

    urlopen's own timeout only bounds the socket connect/read -- on this
    machine, DNS resolution (getaddrinfo) itself was observed hanging for
    4-9x the stated timeout (one request logged 266.8s against a 30s
    timeout), so urlopen's timeout alone does not reliably bound wall-clock
    time. Each attempt instead runs in a worker thread with a hard
    .result(timeout=...) deadline; a thread that's still stuck past the
    deadline is abandoned (not killed -- Python threads can't be) and the
    next attempt proceeds independently. Exponential backoff between
    attempts, since the one real failure seen in production so far was a
    transient local network/DNS blip, not a persistent server block.
    """
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


def _extract_xlsx_bytes(raw: bytes, filename: str) -> bytes | None:
    if filename.lower().endswith(".xlsx"):
        return raw
    if filename.lower().endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for name in z.namelist():
                if name.lower().endswith(".xlsx"):
                    return z.read(name)
    return None


def _find_title_row(ws, max_scan: int = 20) -> int | None:
    for r in range(1, max_scan + 1):
        val = ws.cell(r, 1).value
        if isinstance(val, str) and "table 5" in val.lower() and "consumer price index" in val.lower():
            return r
    return None


def _find_date_row(ws, start: int, max_scan: int = 6) -> tuple[int, list[int]] | None:
    for r in range(start, start + max_scan):
        date_cols = [c for c in range(1, 15) if isinstance(ws.cell(r, c).value, datetime.datetime)]
        if len(date_cols) >= 3:
            return r, date_cols[:3]
    return None


def _find_header_row(ws, start: int, max_scan: int = 4) -> int | None:
    for r in range(start, start + max_scan):
        val = ws.cell(r, 2).value
        if isinstance(val, str) and val.strip() == "State":
            return r
    return None


def _find_data_start(ws, header_row: int) -> int:
    # Old-era files wrap "All Items" onto a second header row ("All" /
    # "Items" split across header_row and header_row+1); skip it if present.
    next_row = header_row + 1
    row_vals = [ws.cell(next_row, c).value for c in range(1, 15)]
    if ws.cell(next_row, 2).value is None and any(
        isinstance(v, str) and "items" in v.lower() for v in row_vals
    ):
        return next_row + 1
    return next_row


def _iter_table5_rows(ws):
    title_row = _find_title_row(ws)
    if title_row is None:
        return
    found = _find_date_row(ws, title_row + 1)
    if found is None:
        return
    date_row, date_cols = found
    header_row = _find_header_row(ws, date_row + 1)
    if header_row is None:
        return
    data_start = _find_data_start(ws, header_row)

    r = data_start
    while True:
        state = ws.cell(r, 2).value
        if not isinstance(state, str) or not state.strip() or state.strip().lower().startswith("note"):
            break
        yield state.strip(), r, date_row, date_cols
        r += 1


class NBSCPIStateConnector(Connector):
    name = "nbs_cpi_state"
    source_label = "NBS"

    def fetch(self, start_year: int = 2015):
        payload = json.loads(_get(RESOURCES_URL))
        for resource in payload.get("resources", []):
            title = str(resource.get("title", "")).strip()
            filename = str(resource.get("filename", ""))
            url = resource.get("url")
            if not TITLE_RE.match(title) or not url or filename.lower().endswith(".pdf"):
                continue

            try:
                raw = _get(url)
            except Exception:
                continue
            xlsx_bytes = _extract_xlsx_bytes(raw, filename)
            if not xlsx_bytes:
                continue

            try:
                wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=True)
            except Exception:
                continue
            if "Table-5" not in wb.sheetnames:
                continue
            ws = wb["Table-5"]

            for state, data_row, date_row, date_cols in _iter_table5_rows(ws):
                slug = STATE_SLUGS.get(state)
                if not slug:
                    continue
                for date_col in date_cols:
                    dt = ws.cell(date_row, date_col).value
                    if not isinstance(dt, datetime.datetime):
                        continue
                    obs_date = f"{dt.year}-{dt.month:02d}-01"
                    for col, suffix in ((date_col, "food"), (date_col + 1, "all")):
                        val = ws.cell(data_row, col).value
                        if val is None:
                            continue
                        try:
                            value = float(val)
                        except (TypeError, ValueError):
                            continue
                        yield {
                            "indicator_id": f"nbs_cpi_{slug}_{suffix}",
                            "obs_date": obs_date,
                            "value": value,
                            "source": "NBS",
                        }
