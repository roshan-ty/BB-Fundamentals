#!/usr/bin/env python3
"""
Bulls & Bears Fundamentals - FRED Macro Data Pipeline
Fetches 40 years of historical economic data from the St. Louis FRED API.
Calculates rolling 12-month moving averages and historical percentiles.
Outputs structured data to data/macro_data.json
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

import requests
import numpy as np
import pandas as pd
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
FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "macro_data.json")

# Series ID -> Display Name mapping (fully spelled out)
FRED_SERIES: Dict[str, str] = {
    "FEDFUNDS": "Effective Federal Reserve Funds Rate",
    "CPIAUCSL": "Consumer Price Index for All Urban Consumers",
    "PCEPI": "Core Personal Consumption Expenditures Price Index",
    "GDPC1": "Real Gross Domestic Product",
    "UNRATE": "Civilian Unemployment Rate",
    "PAYEMS": "Total Nonfarm Payrolls Employment Change",
    "T10Y2Y": "10-Year Treasury Constant Maturity Minus 2-Year Treasury Constant Maturity Yield Spread",
}

# Number of years of history to fetch
HISTORY_YEARS = 40

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5
REQUEST_TIMEOUT = 30


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def load_environment_variables() -> str:
    """Load and return the FRED API key from environment variables."""
    load_dotenv()
    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        logger.error("FRED_API_KEY environment variable is not set. Cannot fetch macro data.")
        sys.exit(1)
    return api_key


def fetch_fred_series(api_key: str, series_id: str, series_name: str) -> Optional[List[Dict[str, Any]]]:
    """
    Fetch historical observations for a given FRED series.
    Implements retry logic with exponential backoff.
    Returns a list of dicts with 'date' and 'value' keys, or None on failure.
    """
    # Calculate start date: 40 years ago from today
    start_date = (datetime.now() - timedelta(days=HISTORY_YEARS * 365)).strftime("%Y-%m-%d")
    
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start_date,
        "sort_order": "asc",
    }

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(f"Fetching FRED series '{series_name}' ({series_id}) - Attempt {attempt}/{MAX_RETRIES}")
            response = requests.get(
                FRED_BASE_URL,
                params=params,
                timeout=REQUEST_TIMEOUT
            )
            response.raise_for_status()
            data = response.json()

            if "observations" not in data:
                logger.warning(f"No observations found for series '{series_name}'")
                return None

            observations = data["observations"]
            parsed = []
            for obs in observations:
                date_str = obs.get("date", "")
                value_str = obs.get("value", "")
                if value_str == "." or value_str == "":
                    continue  # Skip missing values
                try:
                    value = float(value_str)
                except (ValueError, TypeError):
                    continue
                parsed.append({"date": date_str, "value": value})

            if not parsed:
                logger.warning(f"All observations for '{series_name}' were empty or invalid.")
                return None

            logger.info(f"Successfully fetched {len(parsed)} data points for '{series_name}'")
            return parsed

        except requests.exceptions.RequestException as e:
            last_error = e
            logger.warning(f"Request failed for '{series_name}': {e}")
            if attempt < MAX_RETRIES:
                wait_time = RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
                logger.info(f"Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                logger.error(f"All {MAX_RETRIES} attempts failed for '{series_name}'.")
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            last_error = e
            logger.error(f"JSON parsing error for '{series_name}': {e}")
            break

    logger.error(f"Failed to fetch FRED series '{series_name}': {last_error}")
    return None


def calculate_rolling_ma(data: List[Dict[str, Any]], window: int = 12) -> List[float]:
    """
    Calculate a rolling (moving) average on the values.
    Returns a list of values; the first (window-1) entries will be NaN.
    """
    values = [entry["value"] for entry in data]
    series = pd.Series(values)
    rolling = series.rolling(window=window, min_periods=1).mean()
    return rolling.tolist()


def calculate_percentiles(data: List[Dict[str, Any]]) -> List[float]:
    """
    Calculate the historical percentile rank for each data point.
    Each value's percentile is computed relative to all values up to and including it.
    Returns a list of floats in [0, 1].
    """
    values = [entry["value"] for entry in data]
    percentiles = []
    for i in range(len(values)):
        if i == 0:
            percentiles.append(0.5)  # Median for single point
        else:
            sub_array = values[:i + 1]
            rank = sum(1 for v in sub_array if v <= values[i]) / len(sub_array)
            percentiles.append(rank)
    return percentiles


def build_macro_output(all_series_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build the final structured output dictionary containing all macro data
    with computed statistics (rolling MA, percentiles).
    """
    output: Dict[str, Any] = {
        "meta": {
            "source": "Federal Reserve Economic Data (FRED) API",
            "last_updated": datetime.utcnow().isoformat() + "Z",
            "historical_years": HISTORY_YEARS,
            "total_series": len(all_series_data),
        },
        "series": [],
    }

    for series_id, series_info in all_series_data.items():
        raw_data = series_info.get("raw", [])
        if not raw_data:
            logger.warning(f"No raw data for series '{series_info.get('name', series_id)}'. Skipping.")
            continue

        rolling_ma = calculate_rolling_ma(raw_data, window=12)
        percentiles = calculate_percentiles(raw_data)

        # Build enriched data points
        enriched_points = []
        for i, point in enumerate(raw_data):
            enriched_points.append({
                "date": point["date"],
                "value": point["value"],
                "rolling_12_month_moving_average": rolling_ma[i] if not np.isnan(rolling_ma[i]) else None,
                "historical_percentile": round(percentiles[i], 4),
            })

        series_entry = {
            "series_id": series_id,
            "series_name": series_info["name"],
            "unit": series_info.get("unit", ""),
            "frequency": series_info.get("frequency", ""),
            "data_points": enriched_points,
            "summary_statistics": {
                "current_value": enriched_points[-1]["value"] if enriched_points else None,
                "minimum_value": min(p["value"] for p in enriched_points) if enriched_points else None,
                "maximum_value": max(p["value"] for p in enriched_points) if enriched_points else None,
                "mean_value": round(np.mean([p["value"] for p in enriched_points]), 4) if enriched_points else None,
                "standard_deviation": round(np.std([p["value"] for p in enriched_points]), 4) if enriched_points else None,
                "current_percentile": enriched_points[-1]["historical_percentile"] if enriched_points else None,
            },
        }
        output["series"].append(series_entry)
        logger.info(f"Processed {len(enriched_points)} data points for '{series_info['name']}'")

    return output


def write_output(data: Dict[str, Any], filepath: str) -> None:
    """Write the output JSON to disk with explicit UTF-8 encoding."""
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Macro data successfully written to {filepath}")
    except (OSError, IOError) as e:
        logger.error(f"Failed to write output file '{filepath}': {e}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Main Execution
# ---------------------------------------------------------------------------

def main() -> None:
    """Main entry point for the FRED macro data pipeline."""
    logger.info("=" * 60)
    logger.info("Bulls & Bears Fundamentals - FRED Macro Data Pipeline")
    logger.info("=" * 60)

    api_key = load_environment_variables()

    # Metadata about each series (units, frequency)
    series_metadata = {
        "FEDFUNDS": {"unit": "Percent", "frequency": "Monthly"},
        "CPIAUCSL": {"unit": "Index 1982-1984=100", "frequency": "Monthly"},
        "PCEPI": {"unit": "Index 2017=100", "frequency": "Monthly"},
        "GDPC1": {"unit": "Billions of Chained 2017 Dollars", "frequency": "Quarterly"},
        "UNRATE": {"unit": "Percent", "frequency": "Monthly"},
        "PAYEMS": {"unit": "Thousands of Persons", "frequency": "Monthly"},
        "T10Y2Y": {"unit": "Percent", "frequency": "Daily"},
    }

    all_series_data: Dict[str, Any] = {}

    for series_id, series_name in FRED_SERIES.items():
        raw_data = fetch_fred_series(api_key, series_id, series_name)
        if raw_data:
            all_series_data[series_id] = {
                "name": series_name,
                "unit": series_metadata.get(series_id, {}).get("unit", ""),
                "frequency": series_metadata.get(series_id, {}).get("frequency", ""),
                "raw": raw_data,
            }
        else:
            logger.warning(f"Skipping series '{series_name}' due to fetch failure.")

    if not all_series_data:
        logger.error("No macro data was successfully fetched. Exiting.")
        sys.exit(1)

    # Build the structured output
    macro_output = build_macro_output(all_series_data)

    # Write to file
    write_output(macro_output, OUTPUT_FILE)

    logger.info("FRED Macro Data Pipeline completed successfully.")


if __name__ == "__main__":
    main()