# NPEDATA MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io) server exposing the
[NPEDATA Open API](https://npedata-api.onrender.com) — Nigeria's public economic data from the CBN,
NBS, and World Bank — as 12 read-only tools for Claude Desktop, Cursor, and any other MCP-compatible
client. This is a separate component from the dashboard and the FastAPI backend: it's a thin client that
calls the already-public REST API at `https://npedata-api.onrender.com/api/v1`, holds no credentials,
and writes nothing.

## Requirements

- Node.js 18 or later (for built-in `fetch`).

## Setup

```bash
cd mcp-server
npm install
```

## Run standalone (for testing)

```bash
npm start
```

The server communicates over stdio per the MCP spec — running it directly just starts it listening for
a client connection; it won't print anything to the terminal on its own.

## Register with Claude Desktop

Add this to your Claude Desktop config (`claude_desktop_config.json` — on Windows, typically
`%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "npedata": {
      "command": "node",
      "args": ["C:/absolute/path/to/nigerian-dashboard/mcp-server/index.js"]
    }
  }
}
```

Replace the path with the absolute path to this directory's `index.js` on your machine, then restart
Claude Desktop. The same config shape works for Cursor's MCP settings.

## Tools

| Tool | Description |
|---|---|
| `get_summary` | Latest value for GDP, inflation, exchange rate, MPR, FX reserves |
| `get_gdp` | Quarterly real GDP growth (%) and annual nominal GDP (USD billions) |
| `get_inflation` | Monthly headline, food, and core inflation (% YoY) |
| `get_exchange_rate` | Monthly average official NGN/USD rate |
| `get_interest_rate` | CBN Monetary Policy Rate (MPR) per MPC decision |
| `get_fx_reserves` | Monthly gross, liquid, blocked FX reserves + block % |
| `get_currency_circulation` | Currency in circulation (NGN billions), 2002–2024 |
| `get_nfem` | NFEM daily closing/highest/lowest/weighted-average rates |
| `get_multicurrency` | Buying/central/selling rates for 11 currencies vs the Naira |
| `get_gdp_sectors` | Real GDP by sector (agriculture, industry, services, etc) |
| `get_cbn_balance_sheet` | CBN total assets, liabilities, gold, currency issued |
| `get_analytics` | Pearson correlation between inflation and exchange rate |

Most tools accept optional `start`/`end` ISO 8601 date parameters; `get_multicurrency` additionally
accepts an optional `currency` code to filter to a single currency.

## Verification note

This was written and reviewed against the official MCP TypeScript SDK's documented `registerTool` API
and the live `/api/v1/*` response shapes in `main.py`, but has not been executed end-to-end in the
authoring environment (no Node.js available there). Before relying on it, run `npm install && npm start`
and confirm at least one tool call succeeds from a real MCP client.
