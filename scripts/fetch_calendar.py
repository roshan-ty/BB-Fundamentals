#!/usr/bin/env python3
"""
Bulls & Bears Fundamentals - Economic Calendar Engine
Fetches real-time macroeconomic event data from Financial Modeling Prep
and Alpha Vantage APIs. Compiles events with actual, consensus, previous values
and impact levels. Outputs structured data to data/economic_calendar.json
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional

import requests
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
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "economic_calendar.json")

# API Endpoints
FMP_BASE_URL = "https://financialmodelingprep.com/api/v3"
ALPHAVANTAGE_BASE_URL = "https://www.alphavantage.co/query"

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5
REQUEST_TIMEOUT = 30

# Impact level keywords for classification
HIGH_IMPACT_KEYWORDS = [
    "FOMC", "INTEREST RATE", "FED", "NFP", "NON-FARM", "NONFARM",
    "PAYROLLS", "CPI", "CONSUMER PRICE", "PCE", "PERSONAL CONSUMPTION",
    "GDP", "GROSS DOMESTIC PRODUCT", "UNEMPLOYMENT", "JOBLESS",
    "INITIAL CLAIMS", "FED", "CENTRAL BANK", "EMPLOYMENT CHANGE",
    "MANUFACTURING PMI", "SERVICES PMI", "ISM MANUFACTURING", "ISM SERVICES",
    "RETAIL SALES", "INDUSTRIAL PRODUCTION", "EMPLOYMENT COST",
    "FOMC MEETING", "FEDERAL RESERVE", "ECB", "BANK OF ENGLAND",
    "BANK OF JAPAN", "BOJ", "BOE", "RBA", "RESERVE BANK",
]

MEDIUM_IMPACT_KEYWORDS = [
    "PPI", "PRODUCER PRICE", "EXPORT", "IMPORT", "TRADE BALANCE",
    "BUILDING PERMITS", "HOUSING STARTS", "EXISTING HOME", "NEW HOME",
    "CONSUMER CONFIDENCE", "MICHIGAN", "PHILLY FED", "EMPIRE STATE",
    "DURABLE GOODS", "FACTORY ORDERS", "WHOLESALE", "BUSINESS INVENTORIES",
    "CONSTRUCTION SPENDING", "TIC DATA", "TREASURY INTERNATIONAL",
    "JOB OPENINGS", "JOLTS", "QUITS", "LABOR FORCE",
    "AVERAGE HOURLY EARNINGS", "WEEKLY EARNINGS", "PRODUCTIVITY",
    "UNIT LABOR COSTS", "CAPACITY UTILIZATION", "BEIGE BOOK",
    "TREASURY AUCTION", "TREASURY REFUNDING",
]


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def load_environment_variables() -> Dict[str, Optional[str]]:
    """Load API keys from environment variables."""
    load_dotenv()
    return {
        "fmp_key": os.getenv("FMP_API_KEY"),
        "alphavantage_key": os.getenv("ALPHAVANTAGE_API_KEY"),
        "finnhub_key": os.getenv("FINNHUB_API_KEY"),
    }


def classify_impact_level(event_name: str) -> str:
    """
    Classify the impact level of an economic event based on its name.
    Returns 'High', 'Medium', or 'Low'.
    """
    event_upper = event_name.upper()

    for keyword in HIGH_IMPACT_KEYWORDS:
        if keyword in event_upper:
            return "High"

    for keyword in MEDIUM_IMPACT_KEYWORDS:
        if keyword in event_upper:
            return "Medium"

    return "Low"


def fetch_fmp_calendar(api_key: str, days_ahead: int = 14) -> List[Dict[str, Any]]:
    """
    Fetch economic calendar events from Financial Modeling Prep.
    """
    events: List[Dict[str, Any]] = []
    if not api_key:
        logger.warning("No FMP API key provided. Skipping FMP calendar fetch.")
        return events

    try:
        url = f"{FMP_BASE_URL}/economic_calendar"
        params = {"apikey": api_key}

        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info(f"Fetching economic calendar from FMP - Attempt {attempt}/{MAX_RETRIES}")
                response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
                response.raise_for_status()
                data = response.json()

                if not data or not isinstance(data, list):
                    logger.warning("No calendar data returned from FMP")
                    return events

                # Parse FMP calendar entries
                for entry in data:
                    try:
                        event_name = entry.get("event", "") or entry.get("name", "")
                        if not event_name:
                            continue

                        event_date = entry.get("date", "") or entry.get("time", "") or ""
                        actual_val = entry.get("actual", "")
                        consensus_val = entry.get("consensus", "") or entry.get("estimate", "") or ""
                        previous_val = entry.get("previous", "") or ""

                        # Convert numeric strings to float where possible
                        actual = safe_float(actual_val)
                        consensus = safe_float(consensus_val)
                        previous = safe_float(previous_val)

                        country = entry.get("country", "") or "Global"

                        events.append({
                            "event_name": event_name.strip(),
                            "country": country,
                            "timestamp": event_date,
                            "actual": actual,
                            "consensus": consensus,
                            "previous": previous,
                            "impact_level": classify_impact_level(event_name),
                            "source": "financialmodelingprep",
                        })
                    except (KeyError, ValueError, TypeError) as e:
                        logger.debug(f"Error parsing FMP entry: {e}")
                        continue

                logger.info(f"Fetched {len(events)} events from FMP")
                return events

            except requests.exceptions.RequestException as e:
                last_error = e
                logger.warning(f"FMP request failed: {e}")
                if attempt < MAX_RETRIES:
                    wait_time = RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
                    time.sleep(wait_time)

        logger.error(f"All FMP attempts failed: {last_error}")

    except Exception as e:
        logger.error(f"Unexpected error fetching FMP calendar: {e}")

    return events


def fetch_alphavantage_calendar(api_key: str) -> List[Dict[str, Any]]:
    """
    Fetch economic calendar events from Alpha Vantage.
    Alpha Vantage provides an INCOME_STATEMENT-like endpoint for economic indicators.
    """
    events: List[Dict[str, Any]] = []
    if not api_key:
        logger.warning("No Alpha Vantage API key provided. Skipping Alpha Vantage calendar fetch.")
        return events

    # Fetch key economic indicators directly via Alpha Vantage
    indicator_mapping = {
        "REAL_GDP": "Real Gross Domestic Product",
        "REAL_GDP_PER_CAPITA": "Real Gross Domestic Product Per Capita",
        "TREASURY_YIELD": "Treasury Yield (10-Year Note)",
        "INFLATION": "Inflation Rate (CPI Based)",
        "CPI": "Consumer Price Index",
        "RETAIL_SALES": "Retail Sales Monthly Change",
        "DURABLES": "Manufacturers New Orders Durable Goods",
        "UNEMPLOYMENT": "Civilian Unemployment Rate",
        "NONFARM_PAYROLL": "Total Nonfarm Payrolls Employment Change",
    }

    for indicator, display_name in indicator_mapping.items():
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                url = ALPHAVANTAGE_BASE_URL
                params = {
                    "function": indicator,
                    "apikey": api_key,
                }
                # Some indicators need additional parameters
                if indicator == "TREASURY_YIELD":
                    params["interval"] = "monthly"
                    params["maturity"] = "10year"

                logger.info(f"Fetching Alpha Vantage indicator '{indicator}' - Attempt {attempt}")
                response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
                response.raise_for_status()
                data = response.json()

                # Parse the response to extract data
                if "data" in data:
                    for entry in data["data"]:
                        date_str = entry.get("date", "")
                        value_str = entry.get("value", "")
                        try:
                            events.append({
                                "event_name": display_name,
                                "country": "United States",
                                "timestamp": date_str,
                                "actual": safe_float(value_str),
                                "consensus": None,
                                "previous": None,
                                "impact_level": classify_impact_level(display_name),
                                "source": "alphavantage",
                            })
                        except (ValueError, TypeError):
                            continue
                break

            except requests.exceptions.RequestException as e:
                logger.warning(f"Alpha Vantage request for '{indicator}' failed: {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY_SECONDS * (2 ** (attempt - 1)))
                else:
                    logger.error(f"All Alpha Vantage attempts failed for '{indicator}'.")

    logger.info(f"Fetched {len(events)} events from Alpha Vantage")
    return events


def safe_float(value: Any) -> Optional[float]:
    """Safely convert a value to float, returning None if impossible."""
    if value is None or value == "" or value == "None":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        # Remove common formatting characters
        cleaned = str(value).replace(",", "").replace("$", "").replace("%", "").replace("+", "").strip()
        return float(cleaned) if cleaned else None
    except (ValueError, TypeError):
        return None


def merge_and_deduplicate(events_list: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """
    Merge events from multiple sources and deduplicate by event name + timestamp.
    """
    seen: set = set()
    merged: List[Dict[str, Any]] = []

    for events in events_list:
        for event in events:
            # Create a dedup key based on event name and date
            event_name = event.get("event_name", "").strip().upper()
            timestamp = event.get("timestamp", "").strip()
            dedup_key = f"{event_name}|{timestamp}"

            if dedup_key not in seen:
                seen.add(dedup_key)
                merged.append(event)

    # Sort by timestamp (most recent first)
    merged.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    return merged


def build_calendar_output(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build the final structured output for the economic calendar.
    """
    # Count by impact level
    high_count = sum(1 for e in events if e.get("impact_level") == "High")
    medium_count = sum(1 for e in events if e.get("impact_level") == "Medium")
    low_count = sum(1 for e in events if e.get("impact_level") == "Low")

    output: Dict[str, Any] = {
        "meta": {
            "source": "Financial Modeling Prep, Alpha Vantage, Finnhub",
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "total_events": len(events),
            "breakdown_by_impact": {
                "high_impact_events": high_count,
                "medium_impact_events": medium_count,
                "low_impact_events": low_count,
            },
        },
        "events": events,
    }

    return output


def write_output(data: Dict[str, Any], filepath: str) -> None:
    """Write the output JSON to disk with explicit UTF-8 encoding."""
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Economic calendar data successfully written to {filepath}")
    except (OSError, IOError) as e:
        logger.error(f"Failed to write output file '{filepath}': {e}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Main Execution
# ---------------------------------------------------------------------------

def main() -> None:
    """Main entry point for the Economic Calendar Engine."""
    logger.info("=" * 60)
    logger.info("Bulls & Bears Fundamentals - Economic Calendar Engine")
    logger.info("=" * 60)

    api_keys = load_environment_variables()

    # Fetch from multiple sources in parallel (sequential due to simplicity)
    fmp_events = fetch_fmp_calendar(api_keys.get("fmp_key", ""))
    av_events = fetch_alphavantage_calendar(api_keys.get("alphavantage_key", ""))

    # Merge all event sources
    all_events = merge_and_deduplicate([fmp_events, av_events])

    if not all_events:
        logger.warning("No economic calendar events were fetched. Writing empty dataset.")
        # Write at least an empty structure so the frontend doesn't crash
        empty_output = {
            "meta": {
                "source": "Financial Modeling Prep, Alpha Vantage",
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "total_events": 0,
                "breakdown_by_impact": {
                    "high_impact_events": 0,
                    "medium_impact_events": 0,
                    "low_impact_events": 0,
                },
            },
            "events": [],
        }
        write_output(empty_output, OUTPUT_FILE)
        logger.info("Empty economic calendar file written.")
        return

    # Build output
    output = build_calendar_output(all_events)

    # Write to file
    write_output(output, OUTPUT_FILE)

    logger.info(f"Economic Calendar Engine completed. Total events: {len(all_events)}")


if __name__ == "__main__":
    main()