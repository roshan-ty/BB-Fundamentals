#!/usr/bin/env python3
"""
Bulls & Bears Fundamentals - CFTC Commitment of Traders Data Pipeline
Downloads and parses CFTC.gov compressed archives for Traders in Financial Futures
and Legacy reports. Extracts net positioning, open interest percentages for major
global asset classes. Outputs structured data to data/cftc_cot.json
"""

import os
import sys
import json
import io
import zipfile
import time
import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple

import requests
import pandas as pd
import numpy as np
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CFTC_BASE_URL = "https://www.cftc.gov/files/dea/history/"
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "cftc_cot.json")

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5
REQUEST_TIMEOUT = 60

# Asset class mapping for filtering CFTC data
ASSET_CLASS_FILTERS: Dict[str, Dict[str, Any]] = {
    "currencies": {
        "display_name": "Currency Futures",
        "keywords": [
            "EURO FX", "BRITISH POUND", "JAPANESE YEN", "SWISS FRANC",
            "CANADIAN DOLLAR", "AUSTRALIAN DOLLAR", "NEW ZEALAND DOLLAR",
            "MEXICAN PESO", "BRAZILIAN REAL", "SOUTH AFRICAN RAND",
            "RUSSIAN RUBLE", "INDIAN RUPEE", "CHINESE RENMINBI",
            "US DOLLAR INDEX", "EURO FX/BRITISH POUND", "EURO FX/JAPANESE YEN",
            "EURO FX/SWISS FRANC", "EURO FX/CANADIAN DOLLAR"
        ]
    },
    "commodities": {
        "display_name": "Commodity Futures",
        "keywords": [
            "GOLD", "SILVER", "PLATINUM", "PALLADIUM",
            "COPPER", "CRUDE OIL", "GASOLINE", "HEATING OIL",
            "NATURAL GAS", "WHEAT", "CORN", "SOYBEANS",
            "COTTON", "SUGAR", "COFFEE", "COCOA", "LIVE CATTLE",
            "LEAN HOGS"
        ]
    },
    "indices": {
        "display_name": "Equity Index Futures",
        "keywords": [
            "S&P 500", "NASDAQ 100", "DOW JONES", "RUSSELL 2000",
            "NIKKEI 225", "FTSE 100", "DAX 30", "CAC 40",
            "S&P/TSX 60", "S&P/ASX 200", "MSCI EAFE", "MSCI EMERGING MARKETS",
            "VIX", "S&P 500 MINI", "NASDAQ 100 MINI", "DOW JONES MINI"
        ]
    },
    "fixed_income": {
        "display_name": "Fixed Income Futures",
        "keywords": [
            "US TREASURY BOND", "US TREASURY NOTE 10-YEAR",
            "US TREASURY NOTE 5-YEAR", "US TREASURY NOTE 2-YEAR",
            "US TREASURY BILL", "EURODOLLAR", "FEDERAL FUNDS",
            "SOFR", "SONIA", "EURIBOR"
        ]
    }
}


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def load_environment_variables() -> None:
    """Load environment variables (for API keys if needed)."""
    load_dotenv()


def download_cftc_archive(year: int) -> Optional[bytes]:
    """
    Download the CFTC annual ZIP archive for a given year.
    Returns the raw bytes of the ZIP file, or None on failure.
    """
    filename = f"fut_fin_txt_{year}.zip"
    url = CFTC_BASE_URL + filename

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(f"Downloading CFTC archive '{filename}' - Attempt {attempt}/{MAX_RETRIES}")
            response = requests.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            logger.info(f"Downloaded {len(response.content)} bytes from {url}")
            return response.content
        except requests.exceptions.RequestException as e:
            last_error = e
            logger.warning(f"Download failed: {e}")
            if attempt < MAX_RETRIES:
                wait_time = RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
                logger.info(f"Retrying in {wait_time}s...")
                time.sleep(wait_time)

    logger.error(f"Failed to download CFTC archive for {year}: {last_error}")
    return None


def parse_cftc_txt_file(content: str) -> List[Dict[str, Any]]:
    """
    Parse a CFTC legacy/financial futures text file and extract structured records.
    Handles the pipe-delimited format used by CFTC.
    """
    records: List[Dict[str, Any]] = []
    lines = content.strip().split('\n')

    if not lines:
        return records

    # Try to detect delimiter: typically pipe '|' or comma
    delimiter = '|' if '|' in content else ','

    # Parse header line to find column indices
    header_line = lines[0].strip()
    headers = [h.strip().upper() for h in header_line.split(delimiter)]

    # Map expected columns to indices
    column_map: Dict[str, int] = {}
    expected_columns = [
        "MARKET AND EXCHANGE NAMES", "CONTRACT MARKET", "COMMODITY", "COMMODITY NAME",
        "REPORT DATE", "AS OF DATE", "CFTC MARKET CODE",
        "PCT OF OI", "OPEN INTEREST",
        "NONCOMMERCIAL LONG", "NONCOMMERCIAL SHORT", "NONCOMMERCIAL SPREAD",
        "COMMERCIAL LONG", "COMMERCIAL SHORT",
        "TOTAL LONG", "TOTAL SHORT",
        "DEALER LONG", "DEALER SHORT",
        "ASSET MGR LONG", "ASSET MGR SHORT",
        "LEV MONEY LONG", "LEV MONEY SHORT",
    ]

    for col_name in expected_columns:
        # Try exact match, then partial match
        for i, h in enumerate(headers):
            if col_name in h or h in col_name:
                if col_name not in column_map or i < column_map[col_name]:
                    column_map[col_name] = i

    # Parse data rows
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue

        fields = [f.strip() for f in line.split(delimiter)]
        if len(fields) < 10:
            continue

        try:
            record: Dict[str, Any] = {}
            # Extract commodity/contract name (try multiple possible columns)
            commodity_col = column_map.get("COMMODITY NAME")
            if commodity_col is None:
                commodity_col = column_map.get("COMMODITY")
            if commodity_col is None:
                commodity_col = column_map.get("MARKET AND EXCHANGE NAMES")
            if commodity_col is not None and commodity_col < len(fields):
                record["contract_name"] = fields[commodity_col].strip().upper()
            else:
                record["contract_name"] = "UNKNOWN"

            # Extract report date
            date_col = column_map.get("REPORT DATE")
            if date_col is None:
                date_col = column_map.get("AS OF DATE")
            if date_col is not None and date_col < len(fields):
                record["report_date"] = fields[date_col].strip()
            else:
                record["report_date"] = ""

            # Extract numeric fields with safe conversion
            numeric_mappings = {
                "open_interest": "OPEN INTEREST",
                "noncommercial_long": "NONCOMMERCIAL LONG",
                "noncommercial_short": "NONCOMMERCIAL SHORT",
                "noncommercial_spread": "NONCOMMERCIAL SPREAD",
                "commercial_long": "COMMERCIAL LONG",
                "commercial_short": "COMMERCIAL SHORT",
                "dealer_long": "DEALER LONG",
                "dealer_short": "DEALER SHORT",
                "asset_manager_long": "ASSET MGR LONG",
                "asset_manager_short": "ASSET MGR SHORT",
                "leveraged_funds_long": "LEV MONEY LONG",
                "leveraged_funds_short": "LEV MONEY SHORT",
                "pct_of_open_interest": "PCT OF OI",
            }

            for target_key, source_col in numeric_mappings.items():
                idx = column_map.get(source_col)
                if idx is not None and idx < len(fields):
                    val_str = fields[idx].strip().replace(',', '').replace('$', '').replace(' ', '')
                    try:
                        record[target_key] = float(val_str) if val_str else 0.0
                    except (ValueError, TypeError):
                        record[target_key] = 0.0
                else:
                    record[target_key] = 0.0

            # Calculate derived fields
            record["net_speculative_positioning"] = (
                record.get("noncommercial_long", 0.0) - record.get("noncommercial_short", 0.0)
            )
            record["net_dealer_positioning"] = (
                record.get("dealer_long", 0.0) - record.get("dealer_short", 0.0)
            )
            record["net_asset_manager_positioning"] = (
                record.get("asset_manager_long", 0.0) - record.get("asset_manager_short", 0.0)
            )
            record["net_leveraged_funds_positioning"] = (
                record.get("leveraged_funds_long", 0.0) - record.get("leveraged_funds_short", 0.0)
            )

            # Calculate open interest percentage if total OI > 0
            total_oi = record.get("open_interest", 0.0)
            if total_oi > 0:
                record["noncommercial_long_oi_pct"] = round(
                    (record["noncommercial_long"] / total_oi) * 100, 2
                )
                record["noncommercial_short_oi_pct"] = round(
                    (record["noncommercial_short"] / total_oi) * 100, 2
                )
            else:
                record["noncommercial_long_oi_pct"] = 0.0
                record["noncommercial_short_oi_pct"] = 0.0

            records.append(record)

        except (ValueError, IndexError, TypeError) as e:
            logger.debug(f"Skipping malformed line: {e}")
            continue

    return records


def classify_asset(contract_name: str) -> Tuple[str, str]:
    """
    Classify a contract into an asset class based on its name.
    Returns (asset_class, display_name).
    """
    contract_upper = contract_name.upper()

    for asset_class, info in ASSET_CLASS_FILTERS.items():
        for keyword in info["keywords"]:
            if keyword.upper() in contract_upper:
                return asset_class, info["display_name"]

    return "other", "Other Futures"


def build_cftc_output(all_records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build the final structured CFTC output with asset class grouping.
    """
    # Classify each record
    classified: Dict[str, List[Dict[str, Any]]] = {
        "currencies": [],
        "commodities": [],
        "indices": [],
        "fixed_income": [],
        "other": [],
    }

    for record in all_records:
        asset_class, display_name = classify_asset(record.get("contract_name", ""))
        record["asset_class"] = asset_class
        record["asset_class_display_name"] = display_name
        if asset_class in classified:
            classified[asset_class].append(record)
        else:
            classified["other"].append(record)

    # Build output structure
    output: Dict[str, Any] = {
        "meta": {
            "source": "U.S. Commodity Futures Trading Commission (CFTC)",
            "report_type": "Traders in Financial Futures - Legacy & Disaggregated",
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "total_records": len(all_records),
        },
        "asset_classes": {},
    }

    for asset_class, records in classified.items():
        if not records:
            continue

        # Calculate aggregate statistics
        non_commercial_longs = [r.get("noncommercial_long", 0.0) for r in records]
        non_commercial_shorts = [r.get("noncommercial_short", 0.0) for r in records]
        net_positions = [r.get("net_speculative_positioning", 0.0) for r in records]

        asset_entry = {
            "display_name": ASSET_CLASS_FILTERS.get(asset_class, {}).get(
                "display_name", "Other Futures"
            ),
            "record_count": len(records),
            "aggregate_metrics": {
                "total_noncommercial_longs": round(sum(non_commercial_longs), 2),
                "total_noncommercial_shorts": round(sum(non_commercial_shorts), 2),
                "aggregate_net_positioning": round(sum(net_positions), 2),
                "average_net_positioning": round(np.mean(net_positions), 2) if net_positions else 0.0,
            },
            "contracts": [],
        }

        for record in records[:100]:  # Limit to top 100 per class to keep file size manageable
            contract_entry = {
                "contract_name": record.get("contract_name", "UNKNOWN"),
                "report_date": record.get("report_date", ""),
                "non_commercial_speculative_long_contracts": record.get("noncommercial_long", 0.0),
                "non_commercial_speculative_short_contracts": record.get("noncommercial_short", 0.0),
                "net_speculative_market_positioning": record.get("net_speculative_positioning", 0.0),
                "dealer_long_contracts": record.get("dealer_long", 0.0),
                "dealer_short_contracts": record.get("dealer_short", 0.0),
                "asset_manager_long_contracts": record.get("asset_manager_long", 0.0),
                "asset_manager_short_contracts": record.get("asset_manager_short", 0.0),
                "leveraged_funds_long_contracts": record.get("leveraged_funds_long", 0.0),
                "leveraged_funds_short_contracts": record.get("leveraged_funds_short", 0.0),
                "open_interest_distribution_percentage": {
                    "non_commercial_long": record.get("noncommercial_long_oi_pct", 0.0),
                    "non_commercial_short": record.get("noncommercial_short_oi_pct", 0.0),
                },
            }
            contract_entry["open_interest"] = record.get("open_interest", 0.0)
            asset_entry["contracts"].append(contract_entry)

        output["asset_classes"][asset_class] = asset_entry

    return output


def write_output(data: Dict[str, Any], filepath: str) -> None:
    """Write the output JSON to disk with explicit UTF-8 encoding."""
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"CFTC data successfully written to {filepath}")
    except (OSError, IOError) as e:
        logger.error(f"Failed to write output file '{filepath}': {e}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Main Execution
# ---------------------------------------------------------------------------

def main() -> None:
    """Main entry point for the CFTC COT data pipeline."""
    logger.info("=" * 60)
    logger.info("Bulls & Bears Fundamentals - CFTC Commitment of Traders Pipeline")
    logger.info("=" * 60)

    load_environment_variables()

    current_year = datetime.now().year
    # Try current year and previous year
    years_to_try = [current_year, current_year - 1]

    all_records: List[Dict[str, Any]] = []

    for year in years_to_try:
        logger.info(f"Processing CFTC data for year {year}...")
        archive_bytes = download_cftc_archive(year)
        if archive_bytes is None:
            logger.warning(f"Could not download CFTC archive for {year}")
            continue

        try:
            with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
                txt_files = [f for f in zf.namelist() if f.endswith('.txt')]
                if not txt_files:
                    logger.warning(f"No text files found in CFTC archive for {year}")
                    continue

                logger.info(f"Found {len(txt_files)} text files in archive for {year}")

                for txt_file in txt_files:
                    try:
                        with zf.open(txt_file) as f:
                            content = f.read().decode('utf-8', errors='replace')
                        records = parse_cftc_txt_file(content)
                        logger.info(f"Parsed {len(records)} records from {txt_file}")
                        all_records.extend(records)
                    except Exception as e:
                        logger.warning(f"Error parsing file {txt_file}: {e}")
                        continue

        except zipfile.BadZipFile as e:
            logger.warning(f"Bad ZIP file for year {year}: {e}")
            continue
        except Exception as e:
            logger.warning(f"Unexpected error processing archive for {year}: {e}")
            continue

    if not all_records:
        logger.error("No CFTC records were parsed. Exiting.")
        sys.exit(1)

    # Build structured output
    cftc_output = build_cftc_output(all_records)

    # Write to file
    write_output(cftc_output, OUTPUT_FILE)

    logger.info(f"CFTC Pipeline completed. Total records: {len(all_records)}")


if __name__ == "__main__":
    main()