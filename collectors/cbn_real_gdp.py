# NPEDATA - Real GDP (constant prices) connector.
#
# Copyright 2026 Taoheed Abdulmanan Olaosebikan. Apache-2.0.
# Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
#
# Found via CBN's rates index (/rates/RealGDP.html, GetAllRealGDP, 104
# rows, 1981-2024, zero messiness -- same identity check as
# cbn_nominal_gdp.py, which holds clean across all 104 rows here, unlike
# Nominal GDP's one corrupted row).
#
# Identical field structure to GetAllNominalGDP (same 57 field names,
# CBN just reuses the generic gdPatCurrentBasicPrices/etc names even
# though this is constant-price data), but 7 of these 57 fields exactly
# match the platform's existing stale gdp_agriculture/gdp_industry/
# gdp_services/gdp_manufacturing/gdp_telecommunicationsAndInformation
# Services/gdp_construction/gdp_trade ids -- confirmed same source
# (gdp_agriculture's existing 2024-03-31 value of 3851.89 matches this
# feed's 2024 Q1 value exactly). This connector REFRESHES those 7
# existing ids rather than duplicating them; the other 50 fields are
# genuinely new, using a gdp_real_ prefix (parallel to the Nominal GDP
# connector's gdp_cp_ prefix).
#
# Date convention: the existing 7 ids use quarter-END dates (2024-03-31,
# 2024-06-30, ...; annual years at YYYY-12-31), not quarter-start like
# gdp_growth/the Nominal GDP connector. To correctly refresh (overwrite)
# those rows rather than create parallel never-colliding duplicates,
# this connector uses quarter-end dates throughout.
#
# Same annual/quarterly collision avoidance as cbn_nominal_gdp.py:
# 1981-2009 has only Annual rows; 2010-2024 has both Annual and Q1-Q4
# rows for the same year (would collide on obs_date if both were kept).

from __future__ import annotations

import json
import urllib.request

from .base import Connector

URL = "https://www.cbn.gov.ng/api/GetAllRealGDP"

FIELD_MAP = {
    "agriculture": "gdp_agriculture",
    "cropProduction": "gdp_real_crop_production",
    "livestock": "gdp_real_livestock",
    "forestry": "gdp_real_forestry",
    "fishing": "gdp_real_fishing",
    "industry": "gdp_industry",
    "miningAndQuarrying": "gdp_real_mining_and_quarrying",
    "crudePetroleumAndNaturalGas": "gdp_real_crude_petroleum_and_natural_gas",
    "coalMining": "gdp_real_coal_mining",
    "metalOres": "gdp_real_metal_ores",
    "quarryingAndOtherMinerals": "gdp_real_quarrying_and_other_minerals",
    "manufacturing": "gdp_manufacturing",
    "oilRefining": "gdp_real_oil_refining",
    "cement": "gdp_real_cement",
    "foodBeverageAndTobacco": "gdp_real_food_beverage_and_tobacco",
    "textileApparelAndFootwear": "gdp_real_textile_apparel_and_footwear",
    "woodAndWoodProducts": "gdp_real_wood_and_wood_products",
    "pulpPaperAndPaperProducts": "gdp_real_pulp_paper_and_paper_products",
    "chemicalAndPharmaceuticalProducts": "gdp_real_chemical_and_pharmaceutical_products",
    "nonMetallicProducts": "gdp_real_non_metallic_products",
    "plasticAndRubberProducts": "gdp_real_plastic_and_rubber_products",
    "electricalAndElectronics": "gdp_real_electrical_and_electronics",
    "basicMetalIronAndSteel": "gdp_real_basic_metal_iron_and_steel",
    "motorVehiclesAndAssembly": "gdp_real_motor_vehicles_and_assembly",
    "otherManufacturing": "gdp_real_other_manufacturing",
    "electricityGasSteamAndAirCon": "gdp_real_electricity_gas_steam_and_air_con",
    "waterSupplySewageWaste": "gdp_real_water_supply_sewage_waste",
    "construction": "gdp_construction",
    "services": "gdp_services",
    "trade": "gdp_trade",
    "accommodationAndFoodServices": "gdp_real_accommodation_and_food_services",
    "transportationAndStorage": "gdp_real_transportation_and_storage",
    "roadTransport": "gdp_real_road_transport",
    "railTransportAndPipelines": "gdp_real_rail_transport_and_pipelines",
    "waterTransport": "gdp_real_water_transport",
    "airTransport": "gdp_real_air_transport",
    "transportServices": "gdp_real_transport_services",
    "postAndCourierServices": "gdp_real_post_and_courier_services",
    "informationAndCommunication": "gdp_real_information_and_communication",
    "telecommunicationsAndInformationServices": "gdp_telecommunicationsAndInformationServices",
    "publishing": "gdp_real_publishing",
    "motionPicturesSoundRecordingAndMusicProduction": "gdp_real_motion_pictures_recording_music",
    "broadcasting": "gdp_real_broadcasting",
    "artsEntertainmentAndRecreation": "gdp_real_arts_entertainment_and_recreation",
    "financeAndInsurance": "gdp_real_finance_and_insurance",
    "financialInstitutions": "gdp_real_financial_institutions",
    "insurance": "gdp_real_insurance",
    "realEstate": "gdp_real_real_estate",
    "professionalScientificAndTechnicalServices": "gdp_real_professional_sci_and_tech_services",
    "administrativeAndSupportServicesBusinessServices": "gdp_real_admin_and_support_services",
    "publicAdministration": "gdp_real_public_administration",
    "education": "gdp_real_education",
    "humanHealthAndSocialServices": "gdp_real_human_health_and_social_services",
    "otherServices": "gdp_real_other_services",
    "gdPatCurrentBasicPrices": "gdp_real_basic_prices",
    "netTaxesOnProducts": "gdp_real_net_taxes_on_products",
    "gdPatCurrentMarketPrices": "gdp_real_market_prices",
}

QUARTER_END_DATE = {"Q1": "-03-31", "Q2": "-06-30", "Q3": "-09-30", "Q4": "-12-31"}


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "npedata-collector/1.0"})
    with urllib.request.urlopen(req, timeout=60.0) as resp:
        return json.loads(resp.read().decode("utf-8"))


class CBNRealGDPConnector(Connector):
    name = "cbn_real_gdp"
    source_label = "NBS"

    def fetch(self, start_year: int = 2015):
        for row in _get(URL):
            year, period = row.get("tyear"), row.get("period")
            if period == "Annual":
                if int(year) >= 2010:
                    continue  # covered by this year's quarterly rows instead
                obs_date = f"{year}-12-31"
            else:
                suffix = QUARTER_END_DATE.get(period)
                if suffix is None:
                    continue
                obs_date = f"{year}{suffix}"

            # Same corroborating-identity check as cbn_nominal_gdp.py: only
            # the corrupted field would be dropped, not the whole row. This
            # dataset currently passes clean (verified across all 104 live
            # rows) but the check is kept as defensive insurance.
            skip_net_taxes = False
            try:
                basic = float(str(row.get("gdPatCurrentBasicPrices")).replace(",", "."))
                market = float(str(row.get("gdPatCurrentMarketPrices")).replace(",", "."))
                taxes = float(str(row.get("netTaxesOnProducts")).replace(",", "."))
                if abs((basic + taxes) - market) > max(1.0, market * 0.01):
                    skip_net_taxes = True
            except (TypeError, ValueError):
                pass

            for field, indicator_id in FIELD_MAP.items():
                if field == "netTaxesOnProducts" and skip_net_taxes:
                    continue
                raw = row.get(field)
                if raw is None or str(raw).strip() == "":
                    continue
                try:
                    value = float(str(raw).replace(",", "."))
                except ValueError:
                    continue
                yield {"indicator_id": indicator_id, "obs_date": obs_date, "value": value, "source": "NBS"}
