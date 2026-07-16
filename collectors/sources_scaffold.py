# NPEDATA - CBN / NBS connector scaffolds.
#
# Copyright 2026 Taoheed Abdulmanan Olaosebikan. Apache-2.0.
# Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
#
# Unlike the World Bank, the CBN and NBS publish no machine-readable API - the
# very gap this project exists to expose. Automating them means scraping PDFs
# and Excel files, which is brittle and source-specific. These scaffolds
# implement the Connector interface so a scraper can be dropped in later without
# touching the runner; today they yield nothing and say why.

from __future__ import annotations

from .base import Connector


class CBNConnector(Connector):
    name = "cbn"
    source_label = "CBN"
    #: hooks for a future scraper, e.g. the CBN statistics bulletin / rates pages
    ENDPOINTS = {
        "exchange_rate": "https://www.cbn.gov.ng/rates/ExchRateByCurrency.asp",
        "mpr": "https://www.cbn.gov.ng/MonetaryPolicy/decisions.asp",
    }

    def fetch(self, start_year: int = 2015):
        # No public API. A production scraper (PDF/Excel/HTML) would live here and
        # yield the same tidy rows as the other connectors.
        return iter(())


class NBSConnector(Connector):
    name = "nbs"
    source_label = "NBS"
    ENDPOINTS = {
        "cpi": "https://nigerianstat.gov.ng/elibrary",  # CPI reports (PDF)
        "gdp": "https://nigerianstat.gov.ng/elibrary",  # GDP reports (PDF)
    }

    def fetch(self, start_year: int = 2015):
        return iter(())
