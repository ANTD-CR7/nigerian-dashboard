// Type definitions for @npedata/client
// Copyright 2026 Taoheed Abdulmanan Olaosebikan. Apache-2.0.

export interface NPEDataOptions {
  baseUrl?: string;
  apiKey?: string;
  fetch?: typeof fetch;
}

export interface DateRange {
  start?: string;
  end?: string;
}

export type Json = Record<string, any>;

export class NPEDataError extends Error {}

export class NPEData {
  constructor(opts?: NPEDataOptions);
  baseUrl: string;

  // named data endpoints
  summary(o?: DateRange): Promise<Json>;
  gdp(o?: DateRange): Promise<Json>;
  inflation(o?: DateRange): Promise<Json>;
  exchange_rate(o?: DateRange): Promise<Json>;
  interest_rate(o?: DateRange): Promise<Json>;
  fx_reserves(o?: DateRange): Promise<Json>;
  currency_circulation(o?: DateRange): Promise<Json>;
  nfem(o?: DateRange): Promise<Json>;
  multicurrency(o?: DateRange): Promise<Json>;
  gdp_sectors(o?: DateRange): Promise<Json>;
  cbn_balance_sheet(o?: DateRange): Promise<Json>;
  series(name: string, o?: DateRange): Promise<Json>;

  // analytics
  analytics(id: string, o?: DateRange & { forecast_periods?: number }): Promise<Json>;
  forecast(id: string, o?: DateRange & { periods?: number; confidence?: number }): Promise<Json>;
  decompose(id: string, o?: DateRange): Promise<Json>;
  leadlag(x: string, y: string, o?: DateRange & { max_lag?: number }): Promise<Json>;
  correlation(): Promise<Json>;
  coverage(o?: DateRange): Promise<Json>;
  exportCsv(id: string, o?: DateRange): Promise<string>;

  // hypermedia
  root(): Promise<Json>;
  follow(response: Json, rel: string): Promise<Json>;
}

export default NPEData;
