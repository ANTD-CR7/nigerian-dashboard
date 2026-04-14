"""
FILE: load_data.py

PURPOSE:
    Loads ALL data into your Supabase database in one run.
    This covers all 5 indicators: GDP growth, nominal GDP, 
    inflation, exchange rate, and MPR.

HOW TO RUN:
    1. Make sure your data files are in the same folder as this script:
         - Inflation_Data_in_Excel.xlsx
         - exchange_rate.xlsx
         - mpr.xlsx
    2. Open your terminal and run:
         python load_data.py

REQUIRES:
    pip install supabase pandas openpyxl
"""

import pandas as pd
from supabase import create_client, Client

# ============================================================
# YOUR SUPABASE CREDENTIALS — already filled in
# ============================================================
SUPABASE_URL = "https://fjsytcmcxapfbrwvawmu.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZqc3l0Y21jeGFwZmJyd3Zhd211Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzU4OTcxOTgsImV4cCI6MjA5MTQ3MzE5OH0.0lGkBdBsY7bQGu4jlHQA0MKm54dd51QwJTdeill_ADw"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ============================================================
# HELPER — inserts one row into observations table
# ============================================================
def insert(indicator_id, obs_date, value, source):
    supabase.table("observations").insert({
        "indicator_id": indicator_id,
        "obs_date":     obs_date,
        "value":        value,
        "source":       source,
    }).execute()


# ============================================================
# PART 1: GDP GROWTH RATE (quarterly, from NBS Excel files)
# These 20 values were extracted directly from the "real gdp
# growth rate %" sheet in each NBS quarterly GDP report.
# Row used: "GDP at 2010 constant price"
# ============================================================
def load_gdp_growth():
    print("\n[1/5] Loading GDP Growth Rate...")

    data = [
        ("2020-01-01",  1.87),   # Q1 2020
        ("2020-04-01", -6.10),   # Q2 2020 — COVID-19 shock
        ("2020-07-01", -3.62),   # Q3 2020
        ("2020-10-01",  0.11),   # Q4 2020
        ("2021-01-01",  0.51),   # Q1 2021
        ("2021-04-01",  5.01),   # Q2 2021 — recovery
        ("2021-07-01",  4.03),   # Q3 2021
        ("2021-10-01",  3.98),   # Q4 2021
        ("2022-01-01",  3.11),   # Q1 2022
        ("2022-04-01",  3.54),   # Q2 2022
        ("2022-07-01",  2.25),   # Q3 2022
        ("2022-10-01",  3.52),   # Q4 2022
        ("2023-01-01",  2.31),   # Q1 2023
        ("2023-04-01",  2.51),   # Q2 2023
        ("2023-07-01",  2.54),   # Q3 2023
        ("2023-10-01",  3.46),   # Q4 2023
        ("2024-01-01",  2.98),   # Q1 2024
        ("2024-04-01",  3.19),   # Q2 2024
        ("2024-07-01",  3.46),   # Q3 2024
        ("2024-10-01",  3.97),   # Q4 2024
    ]

    for obs_date, value in data:
        insert("gdp_growth", obs_date, value, "NBS")
        print(f"  {obs_date}  {value:+.2f}%")

    print(f"  Done — {len(data)} quarters loaded")


# ============================================================
# PART 2: NOMINAL GDP IN USD (annual, from World Bank)
# Source: data.worldbank.org — NY.GDP.MKTP.CD
# Values in USD Billions
# ============================================================
def load_gdp_usd():
    print("\n[2/5] Loading Nominal GDP (USD Billions)...")

    data = [
        ("2020-01-01", 432.29),
        ("2021-01-01", 440.78),
        ("2022-01-01", 477.39),
        ("2023-01-01", 362.81),
        ("2024-01-01", 390.00),
    ]

    for obs_date, value in data:
        insert("gdp_usd", obs_date, value, "WB")
        print(f"  {obs_date}  ${value:.2f}B")

    print(f"  Done — {len(data)} years loaded")


# ============================================================
# PART 3: HEADLINE INFLATION RATE (monthly, from NBS CPI file)
# Source: Inflation_Data_in_Excel.xlsx
# Column: allItemsYearOn (year-on-year headline inflation %)
# ============================================================
def load_inflation():
    print("\n[3/5] Loading Inflation Rate...")

    df = pd.read_excel("Inflation_Data_in_Excel.xlsx")

    # Filter to 2020-2024
    df = df[(df['tyear'] >= 2020) & (df['tyear'] <= 2024)].copy()

    # Build date: first day of each month
    df['obs_date'] = (
        df['tyear'].astype(str) + '-' +
        df['tmonth'].astype(str).str.zfill(2) + '-01'
    )

    # Get the inflation value
    df['value'] = pd.to_numeric(df['allItemsYearOn'], errors='coerce')
    df = df.dropna(subset=['value'])
    df = df.sort_values('obs_date')

    count = 0
    for _, row in df.iterrows():
        insert("inflation", row['obs_date'], round(float(row['value']), 2), "NBS")
        print(f"  {row['obs_date']}  {row['value']:.2f}%")
        count += 1

    print(f"  Done — {count} months loaded")


# ============================================================
# PART 4: EXCHANGE RATE (daily -> monthly average, from CBN)
# Source: exchange_rate.xlsx
# Column: Central Rate (NGN per USD)
# Process: filter USD, group by month, average
# ============================================================
def load_exchange_rate():
    print("\n[4/5] Loading Exchange Rate (NGN/USD)...")

    df = pd.read_excel("exchange_rate.xlsx")

    # Convert date column
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')

    # Filter USD only
    df = df[df['Currency'].str.strip().str.upper() == 'US DOLLAR'].copy()

    # Filter 2020-2024
    df = df[
        (df['Date'].dt.year >= 2020) &
        (df['Date'].dt.year <= 2024)
    ].copy()

    # Clean the Central Rate column (remove commas if any)
    df['Central Rate'] = pd.to_numeric(
        df['Central Rate'].astype(str).str.replace(',', ''), errors='coerce'
    )
    df = df.dropna(subset=['Central Rate'])

    # Calculate monthly average
    df['year_month'] = df['Date'].dt.to_period('M')
    monthly = df.groupby('year_month')['Central Rate'].mean().reset_index()
    monthly['obs_date'] = monthly['year_month'].dt.to_timestamp().dt.strftime('%Y-%m-%d')
    monthly = monthly.sort_values('obs_date')

    count = 0
    for _, row in monthly.iterrows():
        insert("exchange_rate", row['obs_date'], round(float(row['Central Rate']), 4), "CBN")
        print(f"  {row['obs_date']}  {row['Central Rate']:.2f} NGN/USD")
        count += 1

    print(f"  Done — {count} months loaded")


# ============================================================
# PART 5: MONETARY POLICY RATE (from mpr.xlsx)
# Source: CBN MPC decisions
# Already clean — just load directly
# ============================================================
def load_mpr():
    print("\n[5/5] Loading Monetary Policy Rate (MPR)...")

    df = pd.read_excel("mpr.xlsx")
    df.columns = df.columns.str.strip()

    # Rename MPR column
    mpr_col = [c for c in df.columns if 'MPR' in c or 'mpr' in c.lower()][0]
    df = df.rename(columns={mpr_col: 'value'})

    # Convert date
    df['obs_date'] = pd.to_datetime(df['Date'], errors='coerce')
    df = df[
        (df['obs_date'].dt.year >= 2020) &
        (df['obs_date'].dt.year <= 2024)
    ].copy()
    df = df.sort_values('obs_date')

    count = 0
    for _, row in df.iterrows():
        obs_date = row['obs_date'].strftime('%Y-%m-%d')
        insert("mpr", obs_date, round(float(row['value']), 2), "CBN")
        print(f"  {obs_date}  {row['value']:.2f}%")
        count += 1

    print(f"  Done — {count} MPC decisions loaded")


# ============================================================
# RUN EVERYTHING
# ============================================================
if __name__ == "__main__":
    print("=" * 55)
    print("NIGERIAN FINANCIAL DATA AGGREGATION SYSTEM")
    print("Loading all data into Supabase...")
    print("=" * 55)

    try:
        load_gdp_growth()
        load_gdp_usd()
        load_inflation()
        load_exchange_rate()
        load_mpr()

        print("\n" + "=" * 55)
        print("ALL DATA LOADED SUCCESSFULLY")
        print("You can now start the FastAPI server:")
        print("  uvicorn main:app --reload")
        print("=" * 55)

    except Exception as e:
        print(f"\nERROR: {e}")
        print("Check that:")
        print("  1. Your Excel files are in the same folder as this script")
        print("  2. You ran setup.sql in Supabase SQL Editor first")
        print("  3. You have internet connection")
