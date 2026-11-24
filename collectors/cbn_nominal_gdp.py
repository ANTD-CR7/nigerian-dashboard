# NPEDATA - Nominal GDP at current basic prices connector.
#
# Copyright 2026 Taoheed Abdulmanan Olaosebikan. Apache-2.0.
# Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
#
# Found via CBN's rates index (/rates/NominalGDP.html), backed by a live
# JSON API (GetAllNominalGDP, 104 rows, 1981-2024, zero messiness). This
# is a full GDP-by-sector breakdown at current (nominal) prices -- the
# platform's existing gdp_agriculture/gdp_industry/etc. series are at
# CONSTANT prices (a different basis) and are themselves stale leftovers
# from the original one-time ETL with no active connector. "cp" (current
# prices) prefixes every id here to avoid any collision with those.
#
# Three raw field names needed shortening to fit the indicator_id
# VARCHAR(50) column (confirmed in project/database/setup.sql): all 57
# generated ids are verified <=50 chars and unique.
#
# 1981-2009 has only period="Annual" rows (one per year). 2010-2024 has
# BOTH "Annual" and "Q1"-"Q4" rows for the same year -- an Annual row and
# a Q1 row for the same year would collide on obs_date if both were kept
# (both map to e.g. 2010-01-01). Uses quarterly granularity for 2010+
# (matches the existing gdp_growth indicator's quarterly convention) and
# only falls back to the Annual row for years before quarterly data
# exists -- the Annual row for 2010+ years is intentionally skipped, not
# double-counted.
#
# source is "NBS", not "CBN": CBN republishes this live, but NBS is the
# originating agency, same attribution as the existing (stale) gdp_*
# sector indicators for the same underlying concept.

from __future__ import annotations

import json
import urllib.request

from .base import Connector

URL = "https://www.cbn.gov.ng/api/GetAllNominalGDP"

FIELD_MAP = {
    "agriculture": "gdp_cp_agriculture",
    "cropProduction": "gdp_cp_crop_production",
    "livestock": "gdp_cp_livestock",
    "forestry": "gdp_cp_forestry",
    "fishing": "gdp_cp_fishing",
    "industry": "gdp_cp_industry",
    "miningAndQuarrying": "gdp_cp_mining_and_quarrying",
    "crudePetroleumAndNaturalGas": "gdp_cp_crude_petroleum_and_natural_gas",
    "coalMining": "gdp_cp_coal_mining",
    "metalOres": "gdp_cp_metal_ores",
    "quarryingAndOtherMinerals": "gdp_cp_quarrying_and_other_minerals",
    "manufacturing": "gdp_cp_manufacturing",
    "oilRefining": "gdp_cp_oil_refining",
    "cement": "gdp_cp_cement",
    "foodBeverageAndTobacco": "gdp_cp_food_beverage_and_tobacco",
    "textileApparelAndFootwear": "gdp_cp_textile_apparel_and_footwear",
    "woodAndWoodProducts": "gdp_cp_wood_and_wood_products",
    "pulpPaperAndPaperProducts": "gdp_cp_pulp_paper_and_paper_products",
    "chemicalAndPharmaceuticalProducts": "gdp_cp_chemical_and_pharmaceutical_products",
    "nonMetallicProducts": "gdp_cp_non_metallic_products",
    "plasticAndRubberProducts": "gdp_cp_plastic_and_rubber_products",
    "electricalAndElectronics": "gdp_cp_electrical_and_electronics",
    "basicMetalIronAndSteel": "gdp_cp_basic_metal_iron_and_steel",
    "motorVehiclesAndAssembly": "gdp_cp_motor_vehicles_and_assembly",
    "otherManufacturing": "gdp_cp_other_manufacturing",
    "electricityGasSteamAndAirCon": "gdp_cp_electricity_gas_steam_and_air_con",
    "waterSupplySewageWaste": "gdp_cp_water_supply_sewage_waste",
    "construction": "gdp_cp_construction",
    "services": "gdp_cp_services",
    "trade": "gdp_cp_trade",
    "accommodationAndFoodServices": "gdp_cp_accommodation_and_food_services",
    "transportationAndStorage": "gdp_cp_transportation_and_storage",
    "roadTransport": "gdp_cp_road_transport",
    "railTransportAndPipelines": "gdp_cp_rail_transport_and_pipelines",
    "waterTransport": "gdp_cp_water_transport",
    "airTransport": "gdp_cp_air_transport",
    "transportServices": "gdp_cp_transport_services",
    "postAndCourierServices": "gdp_cp_post_and_courier_services",
    "informationAndCommunication": "gdp_cp_information_and_communication",
    "telecommunicationsAndInformationServices": "gdp_cp_telecommunications_and_information_services",
    "publishing": "gdp_cp_publishing",
    "motionPicturesSoundRecordingAndMusicProduction": "gdp_cp_motion_pictures_recording_music",
    "broadcasting": "gdp_cp_broadcasting",
    "artsEntertainmentAndRecreation": "gdp_cp_arts_entertainment_and_recreation",
    "financeAndInsurance": "gdp_cp_finance_and_insurance",
    "financialInstitutions": "gdp_cp_financial_institutions",
    "insurance": "gdp_cp_insurance",
    "realEstate": "gdp_cp_real_estate",
    "professionalScientificAndTechnicalServices": "gdp_cp_professional_sci_and_tech_services",
    "administrativeAndSupportServicesBusinessServices": "gdp_cp_admin_and_support_services",
    "publicAdministration": "gdp_cp_public_administration",
    "education": "gdp_cp_education",
    "humanHealthAndSocialServices": "gdp_cp_human_health_and_social_services",
    "otherServices": "gdp_cp_other_services",
    "gdPatCurrentBasicPrices": "gdp_cp_basic_prices",
    "netTaxesOnProducts": "gdp_cp_net_taxes_on_products",
    "gdPatCurrentMarketPrices": "gdp_cp_market_prices",
}

QUARTER_START_MONTH = {"Q1": "01", "Q2": "04", "Q3": "07", "Q4": "10"}


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "npedata-collector/1.0"})
    with urllib.request.urlopen(req, timeout=60.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


class CBNNominalGDPConnector(Connector):
    name = "cbn_nominal_gdp"
    source_label = "NBS"

    def fetch(self, start_year: int = 2015):
        for row in _get(URL):
            year, period = row.get("tyear"), row.get("period")
            if period == "Annual":
                if int(year) >= 2010:
                    continue  # covered by this year's quarterly rows instead
                obs_date = f"{year}-01-01"
            else:
                month = QUARTER_START_MONTH.get(period)
                if month is None:
                    continue
                obs_date = f"{year}-{month}-01"
            for field, indicator_id in FIELD_MAP.items():
                raw = row.get(field)
                if raw is None or str(raw).strip() == "":
                    continue
                try:
                    value = float(str(raw).replace(",", "."))
                except ValueError:
                    continue
                yield {"indicator_id": indicator_id, "obs_date": obs_date, "value": value, "source": "NBS"}
