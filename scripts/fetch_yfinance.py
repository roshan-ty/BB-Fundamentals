#!/usr/bin/env python3
"""
Bulls & Bears Fundamentals - Financial Prices & Symbols Engine
Fetches real-time pricing data for 200+ global financial instruments across
Forex, Indices, Commodities, and Crypto using the yfinance library.
Outputs structured data to data/market_bias.json (raw price data for analysis engine)
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple

import yfinance as yf
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
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "market_bias.json")

# Symbol definitions with full display names (fully spelled out)
SYMBOLS: Dict[str, List[Dict[str, str]]] = {
    "forex_majors": [
        {"symbol": "EURUSD=X", "name": "Euro / United States Dollar (EUR/USD)"},
        {"symbol": "GBPUSD=X", "name": "British Pound Sterling / United States Dollar (GBP/USD)"},
        {"symbol": "USDJPY=X", "name": "United States Dollar / Japanese Yen (USD/JPY)"},
        {"symbol": "AUDUSD=X", "name": "Australian Dollar / United States Dollar (AUD/USD)"},
        {"symbol": "USDCAD=X", "name": "United States Dollar / Canadian Dollar (USD/CAD)"},
        {"symbol": "USDCHF=X", "name": "United States Dollar / Swiss Franc (USD/CHF)"},
        {"symbol": "NZDUSD=X", "name": "New Zealand Dollar / United States Dollar (NZD/USD)"},
    ],
    "forex_crosses": [
        {"symbol": "EURGBP=X", "name": "Euro / British Pound Sterling (EUR/GBP)"},
        {"symbol": "EURJPY=X", "name": "Euro / Japanese Yen (EUR/JPY)"},
        {"symbol": "EURCHF=X", "name": "Euro / Swiss Franc (EUR/CHF)"},
        {"symbol": "EURNZD=X", "name": "Euro / New Zealand Dollar (EUR/NZD)"},
        {"symbol": "EURAUD=X", "name": "Euro / Australian Dollar (EUR/AUD)"},
        {"symbol": "GBPJPY=X", "name": "British Pound Sterling / Japanese Yen (GBP/JPY)"},
        {"symbol": "GBPCHF=X", "name": "British Pound Sterling / Swiss Franc (GBP/CHF)"},
        {"symbol": "GBPAUD=X", "name": "British Pound Sterling / Australian Dollar (GBP/AUD)"},
        {"symbol": "GBPNZD=X", "name": "British Pound Sterling / New Zealand Dollar (GBP/NZD)"},
        {"symbol": "AUDJPY=X", "name": "Australian Dollar / Japanese Yen (AUD/JPY)"},
        {"symbol": "AUDCHF=X", "name": "Australian Dollar / Swiss Franc (AUD/CHF)"},
        {"symbol": "AUDNZD=X", "name": "Australian Dollar / New Zealand Dollar (AUD/NZD)"},
        {"symbol": "CADJPY=X", "name": "Canadian Dollar / Japanese Yen (CAD/JPY)"},
        {"symbol": "CHFJPY=X", "name": "Swiss Franc / Japanese Yen (CHF/JPY)"},
        {"symbol": "NZDJPY=X", "name": "New Zealand Dollar / Japanese Yen (NZD/JPY)"},
        {"symbol": "EURNOK=X", "name": "Euro / Norwegian Krone (EUR/NOK)"},
        {"symbol": "EURSEK=X", "name": "Euro / Swedish Krona (EUR/SEK)"},
        {"symbol": "USDNOK=X", "name": "United States Dollar / Norwegian Krone (USD/NOK)"},
        {"symbol": "USDSEK=X", "name": "United States Dollar / Swedish Krona (USD/SEK)"},
        {"symbol": "USDSGD=X", "name": "United States Dollar / Singapore Dollar (USD/SGD)"},
        {"symbol": "USDHKD=X", "name": "United States Dollar / Hong Kong Dollar (USD/HKD)"},
        {"symbol": "USDKRW=X", "name": "United States Dollar / South Korean Won (USD/KRW)"},
        {"symbol": "USDTWD=X", "name": "United States Dollar / Taiwan Dollar (USD/TWD)"},
        {"symbol": "USDINR=X", "name": "United States Dollar / Indian Rupee (USD/INR)"},
        {"symbol": "USDBRL=X", "name": "United States Dollar / Brazilian Real (USD/BRL)"},
        {"symbol": "USDMXN=X", "name": "United States Dollar / Mexican Peso (USD/MXN)"},
        {"symbol": "USDZAR=X", "name": "United States Dollar / South African Rand (USD/ZAR)"},
        {"symbol": "USDTRY=X", "name": "United States Dollar / Turkish Lira (USD/TRY)"},
        {"symbol": "USDPLN=X", "name": "United States Dollar / Polish Zloty (USD/PLN)"},
    ],
    "global_indices": [
        {"symbol": "^DJI", "name": "Industrial Average Dow Jones 30 Index (^DJI)"},
        {"symbol": "^GSPC", "name": "Standard & Poor's 500 Index (^GSPC)"},
        {"symbol": "^IXIC", "name": "NASDAQ Composite 100 Index (^IXIC)"},
        {"symbol": "^RUT", "name": "Russell 2000 Small-Cap Index (^RUT)"},
        {"symbol": "^VIX", "name": "CBOE Volatility Index (^VIX)"},
        {"symbol": "^FTSE", "name": "Financial Times Stock Exchange 100 Index (^FTSE)"},
        {"symbol": "^N225", "name": "Nikkei 225 Stock Average Index (^N225)"},
        {"symbol": "^AXJO", "name": "S&P/ASX 200 Australian Index (^AXJO)"},
        {"symbol": "^HSI", "name": "Hang Seng Hong Kong Index (^HSI)"},
        {"symbol": "^STOXX50E", "name": "EURO STOXX 50 Index (^STOXX50E)"},
        {"symbol": "^FCHI", "name": "CAC 40 French Index (^FCHI)"},
        {"symbol": "^GDAXI", "name": "DAX 30 German Index (^GDAXI)"},
        {"symbol": "^BSESN", "name": "BSE SENSEX Indian Index (^BSESN)"},
        {"symbol": "^NSEI", "name": "NIFTY 50 Indian Index (^NSEI)"},
        {"symbol": "^SSEC", "name": "Shanghai Composite Chinese Index (^SSEC)"},
        {"symbol": "^KS11", "name": "KOSPI South Korean Index (^KS11)"},
        {"symbol": "^TWII", "name": "TSEC Weighted Taiwan Index (^TWII)"},
        {"symbol": "^BVSP", "name": "IBOVESPA Brazilian Index (^BVSP)"},
        {"symbol": "^MXX", "name": "IPC Mexican Index (^MXX)"},
        {"symbol": "^IPSA", "name": "IPSA Chilean Index (^IPSA)"},
        {"symbol": "^TA125", "name": "TA-125 Israeli Index (^TA125)"},
    ],
    "commodities": [
        {"symbol": "GC=F", "name": "Gold Futures (GC=F)"},
        {"symbol": "SI=F", "name": "Silver Futures (SI=F)"},
        {"symbol": "CL=F", "name": "Crude Oil West Texas Intermediate Futures (CL=F)"},
        {"symbol": "BZ=F", "name": "Brent Crude Oil Futures (BZ=F)"},
        {"symbol": "NG=F", "name": "Natural Gas Futures (NG=F)"},
        {"symbol": "HG=F", "name": "Copper Futures (HG=F)"},
        {"symbol": "PL=F", "name": "Platinum Futures (PL=F)"},
        {"symbol": "PA=F", "name": "Palladium Futures (PA=F)"},
        {"symbol": "ZC=F", "name": "Corn Futures (ZC=F)"},
        {"symbol": "ZW=F", "name": "Wheat Futures (ZW=F)"},
        {"symbol": "ZS=F", "name": "Soybean Futures (ZS=F)"},
        {"symbol": "KC=F", "name": "Coffee C Futures (KC=F)"},
        {"symbol": "CT=F", "name": "Cotton Futures (CT=F)"},
        {"symbol": "SB=F", "name": "Sugar Futures (SB=F)"},
        {"symbol": "CC=F", "name": "Cocoa Futures (CC=F)"},
    ],
    "crypto": [
        {"symbol": "BTC-USD", "name": "Bitcoin / United States Dollar (BTC-USD)"},
        {"symbol": "ETH-USD", "name": "Ethereum / United States Dollar (ETH-USD)"},
        {"symbol": "SOL-USD", "name": "Solana / United States Dollar (SOL-USD)"},
        {"symbol": "BNB-USD", "name": "BNB / United States Dollar (BNB-USD)"},
        {"symbol": "XRP-USD", "name": "XRP / United States Dollar (XRP-USD)"},
        {"symbol": "ADA-USD", "name": "Cardano / United States Dollar (ADA-USD)"},
        {"symbol": "DOGE-USD", "name": "Dogecoin / United States Dollar (DOGE-USD)"},
        {"symbol": "DOT-USD", "name": "Polkadot / United States Dollar (DOT-USD)"},
        {"symbol": "AVAX-USD", "name": "Avalanche / United States Dollar (AVAX-USD)"},
        {"symbol": "MATIC-USD", "name": "Polygon / United States Dollar (MATIC-USD)"},
        {"symbol": "LINK-USD", "name": "Chainlink / United States Dollar (LINK-USD)"},
        {"symbol": "UNI-USD", "name": "Uniswap / United States Dollar (UNI-USD)"},
        {"symbol": "ATOM-USD", "name": "Cosmos / United States Dollar (ATOM-USD)"},
        {"symbol": "LTC-USD", "name": "Litecoin / United States Dollar (LTC-USD)"},
        {"symbol": "BCH-USD", "name": "Bitcoin Cash / United States Dollar (BCH-USD)"},
    ],
}

# Rate limiting: yfinance can be aggressive, so we batch and delay
BATCH_SIZE = 10
INTER_BATCH_DELAY_SECONDS = 2


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def load_environment_variables() -> None:
    """Load environment variables."""
    load_dotenv()


def fetch_symbol_data(symbol: str, display_name: str, asset_class: str) -> Optional[Dict[str, Any]]:
    """
    Fetch real-time pricing data for a single symbol using yfinance.
    Returns a structured dict with price data, or None on failure.
    """
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info if ticker.info else {}

        # Get real-time price data
        hist = ticker.history(period="2d", interval="1d")
        if hist.empty:
            logger.warning(f"No historical data for {symbol}")
            return None

        latest = hist.iloc[-1]
        prev_close = hist.iloc[-2]["Close"] if len(hist) > 1 else latest["Close"]

        current_price = latest["Close"]
        previous_close = prev_close

        # Calculate 24h change
        abs_change = current_price - previous_close
        pct_change = (abs_change / previous_close) * 100 if previous_close != 0 else 0.0

        # Extract bid/ask if available
        bid = info.get("bid", None)
        ask = info.get("ask", None)

        # If bid/ask not in info, try regular market price
        if bid is None:
            bid = info.get("regularMarketPreviousClose", current_price)
        if ask is None:
            ask = info.get("regularMarketOpen", current_price)

        # Open, High, Low from latest candle
        open_price = latest["Open"]
        high_price = latest["High"]
        low_price = latest["Low"]

        record = {
            "symbol": symbol,
            "display_name": display_name,
            "asset_class": asset_class,
            "current_spot_pricing": round(float(current_price), 6),
            "twenty_four_hour_absolute_price_variance": round(float(abs_change), 6),
            "twenty_four_hour_percentage_price_variance": round(float(pct_change), 4),
            "current_institutional_bid_price": round(float(bid), 6) if bid is not None else None,
            "current_institutional_ask_price": round(float(ask), 6) if ask is not None else None,
            "daily_opening_price": round(float(open_price), 6),
            "daily_high_price": round(float(high_price), 6),
            "daily_low_price": round(float(low_price), 6),
            "previous_session_close": round(float(previous_close), 6),
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(f"Fetched data for {symbol}: ${current_price:.4f} ({pct_change:+.2f}%)")
        return record

    except Exception as e:
        logger.warning(f"Error fetching data for {symbol}: {e}")
        return None


def fetch_all_symbols() -> Dict[str, List[Dict[str, Any]]]:
    """
    Fetch data for all symbols across all asset classes.
    Returns a dict keyed by asset class name, each containing a list of records.
    """
    results: Dict[str, List[Dict[str, Any]]] = {}
    total_symbols = sum(len(symbols) for symbols in SYMBOLS.values())
    fetched_count = 0
    batch_count = 0

    logger.info(f"Starting data fetch for {total_symbols} symbols across {len(SYMBOLS)} asset classes")

    for asset_class, symbols in SYMBOLS.items():
        class_results: List[Dict[str, Any]] = []
        for i, sym_info in enumerate(symbols):
            record = fetch_symbol_data(
                sym_info["symbol"], sym_info["name"], asset_class
            )
            if record:
                class_results.append(record)
                fetched_count += 1

            # Batch delay to avoid rate limiting
            if (i + 1) % BATCH_SIZE == 0 and i < len(symbols) - 1:
                batch_count += 1
                logger.debug(f"Batch {batch_count} complete. Waiting {INTER_BATCH_DELAY_SECONDS}s...")
                time.sleep(INTER_BATCH_DELAY_SECONDS)

        results[asset_class] = class_results
        logger.info(
            f"Asset class '{asset_class}': {len(class_results)}/{len(symbols)} symbols fetched"
        )

    logger.info(f"Data fetch complete: {fetched_count}/{total_symbols} symbols successful")
    return results


def build_market_bias_output(all_data: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """
    Build the final structured output for market bias data.
    This is the raw price data that the analysis engine will use to calculate scores.
    """
    meta = {
        "application": "Bulls & Bears Fundamentals",
        "source": "Yahoo Finance (yfinance)",
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "total_instruments": sum(len(records) for records in all_data.values()),
    }

    # Combine all records into a flat array for easy frontend consumption
    all_instruments: List[Dict[str, Any]] = []
    for asset_class, records in all_data.items():
        for record in records:
            all_instruments.append(record)

    output: Dict[str, Any] = {
        "meta": meta,
        "instruments": all_instruments,
    }

    return output


def write_output(data: Dict[str, Any], filepath: str) -> None:
    """Write the output JSON to disk with explicit UTF-8 encoding."""
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Market bias data successfully written to {filepath}")
    except (OSError, IOError) as e:
        logger.error(f"Failed to write output file '{filepath}': {e}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Main Execution
# ---------------------------------------------------------------------------

def main() -> None:
    """Main entry point for the yfinance data pipeline."""
    logger.info("=" * 60)
    logger.info("Bulls & Bears Fundamentals - Financial Prices & Symbols Engine")
    logger.info("=" * 60)

    load_environment_variables()

    # Fetch all symbol data
    all_data = fetch_all_symbols()

    if not all_data:
        logger.error("No financial data was successfully fetched. Exiting.")
        sys.exit(1)

    # Build output
    output = build_market_bias_output(all_data)

    # Write to file
    write_output(output, OUTPUT_FILE)

    logger.info("Financial Prices & Symbols Engine completed successfully.")


if __name__ == "__main__":
    main()