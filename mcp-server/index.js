#!/usr/bin/env node
// NPEDATA MCP Server — read-only Model Context Protocol wrapper around the
// public Nigerian Public Economic Data Open API (https://npedata-api.onrender.com).
// Every tool here is a thin fetch() against the already-public REST API — this
// server holds no credentials and talks to no database directly.

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const API_BASE = "https://npedata-api.onrender.com/api/v1";

async function fetchJson(path, params = {}) {
  const url = new URL(API_BASE + path);
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
  }
  const res = await fetch(url.toString());
  if (!res.ok) {
    throw new Error(`NPEDATA API request to ${path} failed: HTTP ${res.status}`);
  }
  return res.json();
}

function toolResult(data) {
  return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
}

const dateRange = {
  start: z.string().optional().describe("Start date, ISO 8601 (e.g. 2020-01-01). Defaults to the dataset's earliest date for this indicator."),
  end: z.string().optional().describe("End date, ISO 8601 (e.g. 2026-12-31). Defaults to the latest available date.")
};

const server = new McpServer({
  name: "npedata",
  version: "1.0.0",
  description: "Read-only access to Nigeria's public economic data — CBN, NBS and World Bank — via the NPEDATA Open API."
});

server.registerTool(
  "get_summary",
  {
    title: "NPEDATA — Summary",
    description: "Latest single value for Nigeria's five headline indicators: GDP growth, inflation, exchange rate, MPR, and FX reserves.",
    inputSchema: {}
  },
  async () => toolResult(await fetchJson("/summary"))
);

server.registerTool(
  "get_gdp",
  {
    title: "NPEDATA — GDP",
    description: "Nigeria's quarterly real GDP growth rate (%) and annual nominal GDP in USD billions.",
    inputSchema: dateRange
  },
  async ({ start, end }) => toolResult(await fetchJson("/gdp", { start, end }))
);

server.registerTool(
  "get_inflation",
  {
    title: "NPEDATA — Inflation",
    description: "Nigeria's monthly headline, food, and core inflation rates (% year-on-year), source NBS.",
    inputSchema: dateRange
  },
  async ({ start, end }) => toolResult(await fetchJson("/inflation", { start, end }))
);

server.registerTool(
  "get_exchange_rate",
  {
    title: "NPEDATA — Exchange Rate",
    description: "Nigeria's monthly average official NGN/USD exchange rate, including the June 2023 FX unification reform.",
    inputSchema: dateRange
  },
  async ({ start, end }) => toolResult(await fetchJson("/exchange-rate", { start, end }))
);

server.registerTool(
  "get_interest_rate",
  {
    title: "NPEDATA — Interest Rate (MPR)",
    description: "CBN Monetary Policy Rate (MPR) at each MPC decision date.",
    inputSchema: dateRange
  },
  async ({ start, end }) => toolResult(await fetchJson("/interest-rate", { start, end }))
);

server.registerTool(
  "get_fx_reserves",
  {
    title: "NPEDATA — FX Reserves",
    description: "Nigeria's monthly gross, liquid, and blocked foreign exchange reserves (USD billions), plus block percentage.",
    inputSchema: dateRange
  },
  async ({ start, end }) => toolResult(await fetchJson("/fx-reserves", { start, end }))
);

server.registerTool(
  "get_currency_circulation",
  {
    title: "NPEDATA — Currency in Circulation",
    description: "Naira currency in circulation (NGN billions), 2002–2024, including the January 2023 Naira redesign policy period.",
    inputSchema: dateRange
  },
  async ({ start, end }) => toolResult(await fetchJson("/currency-circulation", { start, end }))
);

server.registerTool(
  "get_nfem",
  {
    title: "NPEDATA — NFEM Rates",
    description: "Nigerian Foreign Exchange Market (NFEM) daily closing, highest, lowest, and weighted-average rates.",
    inputSchema: dateRange
  },
  async ({ start, end }) => toolResult(await fetchJson("/nfem", { start, end }))
);

server.registerTool(
  "get_multicurrency",
  {
    title: "NPEDATA — Multi-Currency Rates",
    description: "CBN buying, central, and selling rates for 11 currencies against the Naira (USD, GBP, EUR, CNY, CHF, ZAR, AED, SAR, SDR, CFA, WAUA).",
    inputSchema: {
      currency: z.enum(["usd", "gbp", "eur", "cny", "chf", "zar", "aed", "sar", "sdr", "cfa", "waua"])
        .optional()
        .describe("Filter to a single currency code. Omit to get all 11."),
      ...dateRange
    }
  },
  async ({ currency, start, end }) => toolResult(await fetchJson("/multicurrency", { currency, start, end }))
);

server.registerTool(
  "get_gdp_sectors",
  {
    title: "NPEDATA — GDP by Sector",
    description: "Nigeria's real GDP broken down by sector (agriculture, industry, services, manufacturing, telecoms, construction, trade), source NBS.",
    inputSchema: dateRange
  },
  async ({ start, end }) => toolResult(await fetchJson("/gdp-sectors", { start, end }))
);

server.registerTool(
  "get_cbn_balance_sheet",
  {
    title: "NPEDATA — CBN Balance Sheet",
    description: "Central Bank of Nigeria balance sheet — total assets, total liabilities, gold, and currency issued, 2005–2023.",
    inputSchema: dateRange
  },
  async ({ start, end }) => toolResult(await fetchJson("/cbn-balance-sheet", { start, end }))
);

server.registerTool(
  "get_analytics",
  {
    title: "NPEDATA — Inflation/FX Correlation",
    description: "Pearson correlation coefficient between Nigeria's headline inflation and the NGN/USD exchange rate, with peak values and dates.",
    inputSchema: {}
  },
  async () => toolResult(await fetchJson("/analytics"))
);

const transport = new StdioServerTransport();
await server.connect(transport);
