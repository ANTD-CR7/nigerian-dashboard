"""
FILE: etl/load_gdp.py

PURPOSE:
    Reads the real GDP growth rate data extracted from NBS quarterly
    reports and loads it into Supabase.

WHAT THIS SCRIPT DOES (step by step):
    1. Connects to your Supabase database
    2. Prepares all 20 quarters of real GDP growth rate data (2020-2024)
       that we extracted manually from the NBS Excel files
    3. For each quarter, inserts one row into the observations table
    4. Also loads the World Bank nominal GDP in USD data (5 annual values)

HOW TO RUN:
    python etl/load_gdp.py

REQUIRES:
    pip install supabase
"""

from supabase import create_client, Client

# ============================================================
# STEP 1: Connect to Supabase
# Replace these two values with your actual Supabase credentials.
# Find them in: Supabase Dashboard > Settings > API
# ============================================================
SUPABASE_URL = "https://YOUR_PROJECT_ID.supabase.co"
SUPABASE_KEY = "YOUR_ANON_KEY_HERE"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ============================================================
# STEP 2: Real GDP Growth Rate Data
# Source: NBS Quarterly GDP Reports
# These values were extracted from the "real gdp growth rate %" 
# sheet in each quarterly NBS Excel file.
# The row used is: "GDP at 2010 constant price"
# Date format: YYYY-MM-DD (first day of each quarter)
# ============================================================
GDP_GROWTH_DATA = [
    # 2020 - COVID-19 year
    {"obs_date": "2020-01-01", "value": 1.87,  "source": "NBS"},   # Q1 2020
    {"obs_date": "2020-04-01", "value": -6.10, "source": "NBS"},   # Q2 2020 - COVID shock
    {"obs_date": "2020-07-01", "value": -3.62, "source": "NBS"},   # Q3 2020
    {"obs_date": "2020-10-01", "value": 0.11,  "source": "NBS"},   # Q4 2020

    # 2021 - Recovery year
    {"obs_date": "2021-01-01", "value": 0.51,  "source": "NBS"},   # Q1 2021
    {"obs_date": "2021-04-01", "value": 5.01,  "source": "NBS"},   # Q2 2021
    {"obs_date": "2021-07-01", "value": 4.03,  "source": "NBS"},   # Q3 2021
    {"obs_date": "2021-10-01", "value": 3.98,  "source": "NBS"},   # Q4 2021

    # 2022
    {"obs_date": "2022-01-01", "value": 3.11,  "source": "NBS"},   # Q1 2022
    {"obs_date": "2022-04-01", "value": 3.54,  "source": "NBS"},   # Q2 2022
    {"obs_date": "2022-07-01", "value": 2.25,  "source": "NBS"},   # Q3 2022
    {"obs_date": "2022-10-01", "value": 3.52,  "source": "NBS"},   # Q4 2022

    # 2023
    {"obs_date": "2023-01-01", "value": 2.31,  "source": "NBS"},   # Q1 2023
    {"obs_date": "2023-04-01", "value": 2.51,  "source": "NBS"},   # Q2 2023
    {"obs_date": "2023-07-01", "value": 2.54,  "source": "NBS"},   # Q3 2023
    {"obs_date": "2023-10-01", "value": 3.46,  "source": "NBS"},   # Q4 2023

    # 2024
    {"obs_date": "2024-01-01", "value": 2.98,  "source": "NBS"},   # Q1 2024
    {"obs_date": "2024-04-01", "value": 3.19,  "source": "NBS"},   # Q2 2024
    {"obs_date": "2024-07-01", "value": 3.46,  "source": "NBS"},   # Q3 2024
    {"obs_date": "2024-10-01", "value": 3.97,  "source": "NBS"},   # Q4 2024
]


# ============================================================
# STEP 3: World Bank Nominal GDP Data
# Source: World Bank Open Data (data.worldbank.org)
# Indicator: NY.GDP.MKTP.CD (GDP, current US$)
# Values in USD Billions (original values divided by 1,000,000,000)
# Date: January 1st of each year (annual data)
# ============================================================
GDP_USD_DATA = [
    {"obs_date": "2020-01-01", "value": 432.29, "source": "WB"},
    {"obs_date": "2021-01-01", "value": 440.78, "source": "WB"},
    {"obs_date": "2022-01-01", "value": 477.39, "source": "WB"},
    {"obs_date": "2023-01-01", "value": 362.81, "source": "WB"},
    {"obs_date": "2024-01-01", "value": 390.00, "source": "WB"},
]


# ============================================================
# STEP 4: Load data into Supabase
# ============================================================
def load_indicator(indicator_id: str, data: list):
    """
    Insert a list of observations into the database.
    Each observation is a dict with: obs_date, value, source
    """
    print(f"\nLoading {indicator_id}...")
    success = 0
    errors = 0

    for row in data:
        try:
            record = {
                "indicator_id": indicator_id,
                "obs_date":     row["obs_date"],
                "value":        row["value"],
                "source":       row["source"],
            }
            supabase.table("observations").insert(record).execute()
            print(f"  Inserted: {row['obs_date']} = {row['value']}")
            success += 1
        except Exception as e:
            print(f"  ERROR on {row['obs_date']}: {e}")
            errors += 1

    print(f"  Done: {success} inserted, {errors} errors")


if __name__ == "__main__":
    print("=" * 50)
    print("GDP DATA LOADER")
    print("=" * 50)

    load_indicator("gdp_growth", GDP_GROWTH_DATA)
    load_indicator("gdp_usd",    GDP_USD_DATA)

    print("\nAll GDP data loaded successfully.")
