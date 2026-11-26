# NPEDATA - FMDQ NIBOR connector.
#
# Copyright 2026 Taoheed Abdulmanan Olaosebikan. Apache-2.0.
# Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
#
# fmdqgroup.com/exchange is a WordPress/Elementor marketing site, but its
# "Market Data" section renders a wpDataTables widget sourced from a daily-
# uploaded Excel file in the WP media library. That means the standard,
# public, unauthenticated WordPress REST API (/wp-json/wp/v2/media) can
# discover every historical upload directly -- no scraping, no WAF (unlike
# DMO), no PDF. Confirmed 1,333+ "Nibor Template"/"Template for NIBOR"
# attachments, daily, back to Feb 2022.
#
# Table structure confirmed stable across the full span (checked Feb 2022,
# Apr 2024, Nov 2026 samples): 4 rows, one per tenor (O/N, 1M, 3M, 6M),
# columns Tenor / Rate (%) / Change (%) / a date column (header text
# drifted from "Updated Time" in 2022 to "DATE" now -- found by name, not
# position). The date column is the authoritative as-of date for the rate;
# a WP attachment's own upload timestamp can be up to ~1 day later than
# that in-file date, so the date is always read from inside the file.
#
# Checked for duplication against CBN's existing interbank-rate ids
# (cbn_interbank_call_rate_daily, cbn_interbank_rate_{7,30,60,90,180,360}d)
# before building: NOT duplicates. CBN's daily call rate was a flat 20.00%
# for Nov 20/23/24 2026 while NIBOR O/N moved continuously (20.2083% on the
# 24th) -- different benchmarks (FMDQ is NIBOR's actual benchmark
# administrator), and the tenor sets don't even overlap (7D/30D/60D/90D/
# 180D/360D vs O/N/1M/3M/6M).
#
# Scale problem unlike NBS (31 files) or DMO (56 files): 1,333+ files and
# growing daily. Re-fetching full history on every daily cron run would
# mean ~1,300+ downloads every single day forever just to pick up one new
# day's rate. So the daily connector only paginates back a small bounded
# window (lookback_days, default 14 -- covers weekends/holidays plus the
# ~1-day upload-vs-infile-date lag); the one-time historical backfill
# passes lookback_days=None to fetch everything.

from __future__ import annotations

import concurrent.futures
import datetime
import io
import json
import time
import urllib.request

import openpyxl

from .base import Connector

MEDIA_API = "https://fmdqgroup.com/exchange/wp-json/wp/v2/media"

TENOR_MAP = {"O/N": "on", "1M": "1m", "3M": "3m", "6M": "6m"}


def _get_once(url: str, timeout: float) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "npedata-collector/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _get(url: str, timeout: float = 60.0, attempts: int = 3, backoff: float = 10.0) -> bytes:
    """Hard per-attempt timeout via a worker thread (urlopen's own timeout
    doesn't reliably bound DNS-resolution hangs -- confirmed the hard way
    on NBS's connector earlier this session) plus a backoff retry."""
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


def _iter_resources(lookback_days: int | None = 14):
    """Yields download URLs for every "Nibor Template" xlsx, newest
    first, stopping once a page is entirely older than the lookback
    window (or never stopping, for a full-history backfill)."""
    cutoff = None
    if lookback_days is not None:
        cutoff = datetime.date.today() - datetime.timedelta(days=lookback_days)

    page = 1
    while True:
        url = f"{MEDIA_API}?search=nibor+template&per_page=100&orderby=date&order=desc&page={page}"
        try:
            raw = _get(url)
        except Exception:
            break
        items = json.loads(raw)
        if not items:
            break

        any_within_window = False
        for item in items:
            filename = str(item.get("source_url", ""))
            if not filename.lower().endswith(".xlsx"):
                continue
            upload_date_str = str(item.get("date", ""))[:10]
            try:
                upload_date = datetime.date.fromisoformat(upload_date_str)
            except ValueError:
                upload_date = None
            if cutoff is not None and upload_date is not None and upload_date < cutoff:
                continue
            any_within_window = True
            yield item["source_url"]

        if cutoff is not None and not any_within_window:
            break
        page += 1


def _parse_nibor_file(raw: bytes):
    """Yields (tenor, obs_date, rate) for every tenor row in one daily
    NIBOR file."""
    wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True)
    ws = wb.active

    header = [str(c.value).strip().lower() if c.value else "" for c in next(ws.iter_rows(min_row=1, max_row=1))]
    try:
        tenor_col = header.index("tenor")
        rate_col = header.index("rate (%)")
    except ValueError:
        return
    date_col = None
    for name in ("date", "updated time"):
        if name in header:
            date_col = header.index(name)
            break
    if date_col is None:
        return

    for row in ws.iter_rows(min_row=2):
        tenor = row[tenor_col].value
        rate = row[rate_col].value
        date_val = row[date_col].value
        if tenor is None or rate is None or not isinstance(date_val, datetime.datetime):
            continue
        yield str(tenor).strip(), date_val.date().isoformat(), float(rate)


class FMDQNIBORConnector(Connector):
    name = "fmdq_nibor"
    source_label = "FMDQ"

    def __init__(self, lookback_days: int | None = 14):
        self.lookback_days = lookback_days

    def fetch(self, start_year: int = 2015):
        for url in _iter_resources(self.lookback_days):
            try:
                raw = _get(url)
                rows = list(_parse_nibor_file(raw))
            except Exception:
                continue
            for tenor, obs_date, rate in rows:
                suffix = TENOR_MAP.get(tenor)
                if suffix is None:
                    continue
                yield {
                    "indicator_id": f"fmdq_nibor_{suffix}",
                    "obs_date": obs_date,
                    "value": rate,
                    "source": "FMDQ",
                }
