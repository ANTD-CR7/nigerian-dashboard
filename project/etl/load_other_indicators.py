"""
FILE: etl/load_other_indicators.py

PURPOSE:
    Reads the inflation, exchange rate, and MPR data from the
    Excel files you downloaded and loads them into Supabase.

WHAT THIS SCRIPT DOES (step by step):
    1. Reads Inflation_Data_in_Excel.xlsx — filters to 2020-2024,
       extracts the "allItemsYearOn" column (headline inflation %)
    2. Reads exchange_rate.xlsx — filters daily USD rates to 2020-2024,
       calculates monthly averages using the Central Rate column
    3. Reads mpr.xlsx — loads MPR values directly (already clean)
    4. Inserts all values into the observations table in Supabase

HOW TO RUN:
    python etl/load_other_indicators.py

REQUIRES:
    pip install supabase pandas openpyxl
"""

import pandas as pd
from supabase import create_client, Client

# ============================================================
# CONFIGURATION - Replace with your Supabase credentials
# ============================================================
SUPABASE_URL = "https://YOUR_PROJECT_ID.supabase.co"
SUPABASE_KEY = "YOUR_ANON_KEY_HERE"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# File paths - update these to wherever your files are saved
INFLATION_FILE    = "data/Inflation_Data_in_Excel.xlsx"
EXCHANGE_FILE     = "data/exchange_rate.xlsx"
MPR_FILE          = "data/mpr.xlsx"


# ============================================================
# PART A: INFLATION DATA
# Source: NBS Consumer Price Index Report
# Column used: allItemsYearOn (headline year-on-year inflation %)
# ============================================================
def load_inflation():
    print("\n--- Loading Inflation Data ---")

    # Read the file
    df = pd.read_excel(INFLATION_FILE)

    # Filter to 2020-2024 only
    df = df[(df['tyear'] >= 2020) & (df['tyear'] <= 2024)].copy()

    # Build the date: year + month -> first day of that month
    # Example: year=2020, month=1 -> "2020-01-01"
    df['obs_date'] = pd.to_datetime(
        df['tyear'].astype(str) + '-' + df['tmonth'].astype(str).str.zfill(2) + '-01'
    )

    # Sort oldest to newest
    df = df.sort_values('obs_date')

    # The inflation value column
    df['value'] = pd.to_numeric(df['allItemsYearOn'], errors='coerce')

    # Drop any rows where value is missing
    df = df.dropna(subset=['value'])

    print(f"  Found {len(df)} months of inflation data (2020-2024)")
    print(f"  Date range: {df['obs_date'].min().date()} to {df['obs_date'].max().date()}")

    # Insert into Supabase
    success = 0
    for _, row in df.iterrows():
        try:
            supabase.table("observations").insert({
                "indicator_id": "inflation",
                "obs_date":     row['obs_date'].strftime('%Y-%m-%d'),
                "value":        round(float(row['value']), 2),
                "source":       "NBS",
            }).execute()
            success += 1
        except Exception as e:
            print(f"  ERROR: {row['obs_date'].date()} — {e}")

    print(f"  Inserted {success} inflation records")


# ============================================================
# PART B: EXCHANGE RATE DATA
# Source: CBN Official Rate
# Column used: Central Rate (NGN per USD)
# Step 1: Filter to USD rows only
# Step 2: Filter to 2020-2024
# Step 3: Group by year+month, calculate average
# Result: 60 monthly average exchange rate values
# ============================================================
def load_exchange_rate():
    print("\n--- Loading Exchange Rate Data ---")

    # Read the file
    df = pd.read_excel(EXCHANGE_FILE)

    # Convert Date column to proper datetime
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')

    # Filter to USD only (the file may contain other currencies)
    df = df[df['Currency'].str.strip().str.upper() == 'US DOLLAR'].copy()

    # Filter to 2020-2024
    df = df[
        (df['Date'].dt.year >= 2020) &
        (df['Date'].dt.year <= 2024)
    ].copy()

    # Convert Central Rate to number (some values may be strings with commas)
    df['Central Rate'] = pd.to_numeric(
        df['Central Rate'].astype(str).str.replace(',', ''), errors='coerce'
    )

    # Drop rows with missing rates
    df = df.dropna(subset=['Central Rate'])

    # Create year-month column for grouping
    df['year_month'] = df['Date'].dt.to_period('M')

    # Calculate monthly average
    monthly = df.groupby('year_month')['Central Rate'].mean().reset_index()
    monthly['obs_date'] = monthly['year_month'].dt.to_timestamp()  # first day of month

    monthly = monthly.sort_values('obs_date')

    print(f"  Found {len(monthly)} months of exchange rate data")
    print(f"  Date range: {monthly['obs_date'].min().date()} to {monthly['obs_date'].max().date()}")
    print(f"  Rate range: {monthly['Central Rate'].min():.2f} to {monthly['Central Rate'].max():.2f} NGN/USD")

    # Insert into Supabase
    success = 0
    for _, row in monthly.iterrows():
        try:
            supabase.table("observations").insert({
                "indicator_id": "exchange_rate",
                "obs_date":     row['obs_date'].strftime('%Y-%m-%d'),
                "value":        round(float(row['Central Rate']), 4),
                "source":       "CBN",
            }).execute()
            success += 1
        except Exception as e:
            print(f"  ERROR: {row['obs_date'].date()} — {e}")

    print(f"  Inserted {success} exchange rate records")


# ============================================================
# PART C: MONETARY POLICY RATE (MPR)
# Source: CBN Monetary Policy Committee decisions
# The mpr.xlsx file has two columns: Date and MPR (%)
# These are the exact dates the CBN announced each rate change
# ============================================================
def load_mpr():
    print("\n--- Loading MPR Data ---")

    # Read the file
    df = pd.read_excel(MPR_FILE)

    # The columns are 'Date' and 'MPR (%)'
    # Rename for easier use
    df.columns = df.columns.str.strip()
    df = df.rename(columns={'MPR (%)': 'value'})

    # Convert date to datetime
    df['obs_date'] = pd.to_datetime(df['Date'], errors='coerce')

    # Filter to 2020-2024
    df = df[
        (df['obs_date'].dt.year >= 2020) &
        (df['obs_date'].dt.year <= 2024)
    ].copy()

    df = df.sort_values('obs_date')

    print(f"  Found {len(df)} MPR data points")
    print(f"  Rate range: {df['value'].min()}% to {df['value'].max()}%")

    # Insert into Supabase
    success = 0
    for _, row in df.iterrows():
        try:
            supabase.table("observations").insert({
                "indicator_id": "mpr",
                "obs_date":     row['obs_date'].strftime('%Y-%m-%d'),
                "value":        round(float(row['value']), 2),
                "source":       "CBN",
            }).execute()
            success += 1
        except Exception as e:
            print(f"  ERROR: {row['obs_date'].date()} — {e}")

    print(f"  Inserted {success} MPR records")


# ============================================================
# RUN ALL THREE LOADERS
# ============================================================
if __name__ == "__main__":
    print("=" * 50)
    print("INFLATION, EXCHANGE RATE & MPR LOADER")
    print("=" * 50)

    load_inflation()
    load_exchange_rate()
    load_mpr()

    print("\nAll data loaded successfully.")
