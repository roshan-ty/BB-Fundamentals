#!/usr/bin/env python3
"""
Bulls & Bears Fundamentals - Quantitative Institutional Analysis Engine
Implements a mathematical scoring framework that mimics a veteran macro
institutional strategist. Calculates four structural pillars across 200+
tickers to produce a composite bias score from 1.0 to 10.0.

Scoring Equation:
    Final Score = (P1 x 0.35) + (P2 x 0.25) + (P3 x 0.20) + (P4 x 0.20)

P1 = Monetary Policy Spread (35%)
P2 = Growth & Inflation Vector (25%)
P3 = Liquidity & Curve Structure (20%)
P4 = Positioning Extremes (20%)
"""

import os
import sys
import json
import logging
import math
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple

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
BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

MARKET_BIAS_FILE = os.path.join(DATA_DIR, "market_bias.json")
MACRO_DATA_FILE = os.path.join(DATA_DIR, "macro_data.json")
CFTC_COT_FILE = os.path.join(DATA_DIR, "cftc_cot.json")
ANALYSIS_RESULTS_FILE = os.path.join(DATA_DIR, "analysis_results.json")

# Bias classification thresholds
BIAS_THRESHOLDS = [
    (2.0, "Very Bearish"),
    (5.0, "Bearish"),
    (5.0, "Neutral"),
    (8.0, "Bullish"),
    (float('inf'), "Very Bullish"),
]

# Asset class base rates for P1 (Monetary Policy) calculation
# These are approximate central bank rates used as reference
ASSET_CLASS_BASE_RATES: Dict[str, float] = {
    "forex_majors": 0.05,      # USD-based
    "forex_crosses": 0.04,     # Cross-currency average
    "global_indices": 0.05,    # US equity risk premium reference
    "commodities": 0.03,       # Commodity carry reference
    "crypto": 0.02,            # Crypto risk-free proxy
}


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def load_json_file(filepath: str) -> Any:
    """Load a JSON file and return its contents. Returns None on failure."""
    try:
        if not os.path.exists(filepath):
            logger.warning(f"File not found: {filepath}")
            return None
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except (json.JSONDecodeError, IOError, OSError) as e:
        logger.warning(f"Error loading {filepath}: {e}")
        return None


def classify_bias(score: float) -> str:
    """
    Map a numerical score to a bias classification label.
    """
    if score <= 2.0:
        return "Very Bearish"
    elif score < 5.0:
        return "Bearish"
    elif score == 5.0:
        return "Neutral"
    elif score < 8.0:
        return "Bullish"
    else:
        return "Very Bullish"


def normalize_score(raw_score: float, min_val: float = 1.0, max_val: float = 10.0) -> float:
    """
    Clamp and normalize a raw score to the [1.0, 10.0] range.
    """
    return max(min_val, min(max_val, raw_score))


def safe_get(data: Any, key: str, default: Any = None) -> Any:
    """Safely get a value from a dict or list."""
    if isinstance(data, dict):
        return data.get(key, default)
    return default


# ---------------------------------------------------------------------------
# Pillar 1: Monetary Policy Spread (Weight: 35%)
# ---------------------------------------------------------------------------

def calculate_p1_monetary_policy(
    instrument: Dict[str, Any],
    macro_data: Optional[Dict[str, Any]],
    fed_funds_rate: Optional[float],
) -> Tuple[float, str]:
    """
    Evaluate monetary policy spread between base and quote currencies.
    For indices/commodities/crypto, evaluate equity risk premium vs 10Y real yield.

    Returns (score_component, reasoning).
    """
    asset_class = instrument.get("asset_class", "")
    symbol = instrument.get("symbol", "")

    if fed_funds_rate is None:
        fed_funds_rate = 5.0  # Default fallback

    # Base rate for the asset class
    base_rate = ASSET_CLASS_BASE_RATES.get(asset_class, 0.04)

    # For forex, calculate rate differential based on symbol
    if asset_class in ("forex_majors", "forex_crosses"):
        # Determine if USD is base or quote
        if "JPY" in symbol:
            # For JPY pairs, use BOJ rate (~0.1%) vs USD
            quote_rate = 0.001 if symbol.startswith("USD") else fed_funds_rate
            base_rate_adj = fed_funds_rate if symbol.startswith("USD") else 0.001
        elif "EUR" in symbol:
            # For EUR pairs, use ECB rate (~4.0%) vs USD
            eur_rate = 0.04
            base_rate_adj = fed_funds_rate if "EUR" in symbol else eur_rate
            quote_rate = eur_rate if "EUR" in symbol else fed_funds_rate
        elif "GBP" in symbol:
            # For GBP pairs, use BOE rate (~5.25%)
            gbp_rate = 0.0525
            base_rate_adj = fed_funds_rate if "GBP" in symbol else gbp_rate
            quote_rate = gbp_rate if "GBP" in symbol else fed_funds_rate
        elif "AUD" in symbol or "NZD" in symbol:
            # AUD/NZD typically higher yielders
            high_rate = 0.045
            base_rate_adj = fed_funds_rate if symbol[:3] in ("AUD", "NZD") else high_rate
            quote_rate = high_rate if symbol[:3] in ("AUD", "NZD") else fed_funds_rate
        elif "CAD" in symbol or "CHF" in symbol:
            cad_chf_rate = 0.035
            base_rate_adj = fed_funds_rate if symbol[:3] in ("USD",) else cad_chf_rate
            quote_rate = cad_chf_rate if symbol[:3] in ("USD",) else fed_funds_rate
        else:
            base_rate_adj = fed_funds_rate
            quote_rate = fed_funds_rate

        rate_differential = base_rate_adj - quote_rate

        # Normalize: higher rate differential = higher score (bullish for base currency)
        if abs(rate_differential) < 0.001:
            p1_score = 5.0  # Neutral
        else:
            # Scale: each 1% rate differential = ~1.5 score points
            p1_score = 5.0 + (rate_differential * 150)

        reasoning = f"Rate differential: {base_rate_adj:.2%} - {quote_rate:.2%} = {rate_differential:.2%}"

    elif asset_class == "global_indices":
        # Equity Risk Premium approach
        # ERP = Earnings Yield - 10Y Real Yield
        # Use T10Y2Y spread as proxy for real yield environment
        try:
            if macro_data and "series" in macro_data:
                t10y2y_series = None
                for series in macro_data["series"]:
                    if series.get("series_id") == "T10Y2Y":
                        t10y2y_series = series
                        break

                if t10y2y_series and t10y2y_series.get("data_points"):
                    current_spread = t10y2y_series["data_points"][-1].get("value", 0)
                else:
                    current_spread = 0
            else:
                current_spread = 0

            # Inverted yield curve (negative spread) = bearish for equities
            if current_spread < -0.5:
                p1_score = 2.0  # Very Bearish
                reasoning = f"Deep yield curve inversion: {current_spread:.2f}%"
            elif current_spread < 0:
                p1_score = 3.5  # Bearish
                reasoning = f"Yield curve inverted: {current_spread:.2f}%"
            elif current_spread < 1.0:
                p1_score = 5.5  # Slightly Bullish
                reasoning = f"Yield curve normalizing: {current_spread:.2f}%"
            else:
                p1_score = 7.5  # Bullish
                reasoning = f"Healthy yield curve: {current_spread:.2f}%"
        except Exception:
            p1_score = 5.0
            reasoning = "Could not calculate yield curve context. Neutral."

    elif asset_class == "commodities":
        # Commodities: higher rates = higher carrying cost = slightly bearish
        if fed_funds_rate > 5.0:
            p1_score = 3.5
            reasoning = f"High rates ({fed_funds_rate:.2f}%) increase commodity carrying costs"
        elif fed_funds_rate > 3.0:
            p1_score = 5.0
            reasoning = f"Moderate rates ({fed_funds_rate:.2f}%) - neutral for commodities"
        elif fed_funds_rate > 1.0:
            p1_score = 6.5
            reasoning = f"Low rates ({fed_funds_rate:.2f}%) supportive for commodities"
        else:
            p1_score = 7.5
            reasoning = f"Near-zero rates ({fed_funds_rate:.2f}%) very supportive for commodities"

    elif asset_class == "crypto":
        # Crypto: low rates = more liquidity = bullish for risk assets
        if fed_funds_rate > 5.0:
            p1_score = 2.5
            reasoning = f"High rates ({fed_funds_rate:.2f}%) reduce liquidity for risk assets"
        elif fed_funds_rate > 3.0:
            p1_score = 4.0
            reasoning = f"Restrictive rates ({fed_funds_rate:.2f}%) - bearish for crypto"
        elif fed_funds_rate > 1.0:
            p1_score = 6.5
            reasoning = f"Accommodative rates ({fed_funds_rate:.2f}%) supportive for crypto"
        else:
            p1_score = 8.0
            reasoning = f"Ultra-loose monetary policy very bullish for crypto"
    else:
        p1_score = 5.0
        reasoning = "Unknown asset class - neutral monetary policy score"

    return normalize_score(p1_score), reasoning


# ---------------------------------------------------------------------------
# Pillar 2: Growth & Inflation Vector (Weight: 25%)
# ---------------------------------------------------------------------------

def calculate_p2_growth_inflation(
    instrument: Dict[str, Any],
    macro_data: Optional[Dict[str, Any]],
) -> Tuple[float, str]:
    """
    Calculate directional rate of change of latest CPI and GDP prints.
    Positive growth momentum boosts equities/commodities.
    Hot inflation momentum drives hawkish monetary scoring.

    Returns (score_component, reasoning).
    """
    asset_class = instrument.get("asset_class", "")

    # Extract CPI and GDP data from macro_data if available
    cpi_values = []
    gdp_values = []

    if macro_data and "series" in macro_data:
        for series in macro_data["series"]:
            series_id = series.get("series_id", "")
            data_points = series.get("data_points", [])

            if series_id == "CPIAUCSL":
                cpi_values = [p.get("value", 0) for p in data_points[-6:]]  # Last 6 months
            elif series_id == "GDPC1":
                gdp_values = [p.get("value", 0) for p in data_points[-3:]]  # Last 3 quarters

    # Calculate CPI momentum
    cpi_score = 5.0
    cpi_reasoning = ""
    if len(cpi_values) >= 3:
        cpi_2mo_ago = cpi_values[-3]
        cpi_1mo_ago = cpi_values[-2]
        cpi_latest = cpi_values[-1]

        cpi_momentum_1 = ((cpi_latest - cpi_1mo_ago) / cpi_1mo_ago) * 100
        cpi_momentum_2 = ((cpi_1mo_ago - cpi_2mo_ago) / cpi_2mo_ago) * 100

        if cpi_momentum_1 > cpi_momentum_2 and cpi_momentum_1 > 0:
            # Inflation is accelerating
            if asset_class in ("global_indices", "commodities", "crypto"):
                cpi_score = 3.5  # Accelerating inflation bearish for risk assets
                cpi_reasoning = f"Inflation accelerating ({cpi_momentum_1:+.2f}%) - bearish for risk assets"
            elif asset_class in ("forex_majors", "forex_crosses"):
                cpi_score = 6.5  # Hot inflation = hawkish central bank = bullish fiat
                cpi_reasoning = f"Inflation accelerating ({cpi_momentum_1:+.2f}%) - hawkish monetary outlook"
            else:
                cpi_score = 5.0
                cpi_reasoning = f"Inflation at {cpi_latest:.1f} - neutral"
        elif cpi_momentum_1 < cpi_momentum_2 and cpi_momentum_1 > 0:
            # Inflation decelerating but still positive
            cpi_score = 5.5
            cpi_reasoning = f"Inflation decelerating ({cpi_momentum_1:+.2f}%) - modestly supportive"
        elif cpi_momentum_1 < 0:
            # Deflationary trend
            if asset_class in ("global_indices", "commodities", "crypto"):
                cpi_score = 7.0  # Deflation = rates will be cut = bullish risk
                cpi_reasoning = f"Disinflationary trend ({cpi_momentum_1:+.2f}%) - bullish for risk assets"
            else:
                cpi_score = 4.0
                cpi_reasoning = f"Disinflationary - bearish for fiat currencies"
        else:
            cpi_score = 5.0
            cpi_reasoning = "CPI stable"
    else:
        cpi_reasoning = "Insufficient CPI data"

    # Calculate GDP momentum
    gdp_score = 5.0
    gdp_reasoning = ""
    if len(gdp_values) >= 2:
        gdp_prev = gdp_values[-2]
        gdp_latest = gdp_values[-1]

        gdp_growth = ((gdp_latest - gdp_prev) / gdp_prev) * 100

        if gdp_growth > 0.5:
            gdp_score = 7.5  # Strong growth
            gdp_reasoning = f"Strong GDP growth ({gdp_growth:+.2f}%)"
        elif gdp_growth > 0:
            gdp_score = 6.0  # Moderate growth
            gdp_reasoning = f"Moderate GDP growth ({gdp_growth:+.2f}%)"
        elif gdp_growth > -0.5:
            gdp_score = 4.0  # Mild contraction
            gdp_reasoning = f"Mild GDP contraction ({gdp_growth:+.2f}%)"
        else:
            gdp_score = 2.0  # Severe contraction
            gdp_reasoning = f"Severe GDP contraction ({gdp_growth:+.2f}%)"
    else:
        gdp_reasoning = "Insufficient GDP data"

    # Combine CPI and GDP scores with weighting
    # For risk assets (indices, crypto, commodities): GDP momentum matters more
    if asset_class in ("global_indices", "crypto"):
        combined_score = (cpi_score * 0.35) + (gdp_score * 0.65)
    elif asset_class in ("forex_majors", "forex_crosses"):
        combined_score = (cpi_score * 0.60) + (gdp_score * 0.40)  # CPI matters more for FX
    elif asset_class == "commodities":
        combined_score = (cpi_score * 0.50) + (gdp_score * 0.50)
    else:
        combined_score = (cpi_score * 0.50) + (gdp_score * 0.50)

    reasoning = f"CPI: {cpi_reasoning} | GDP: {gdp_reasoning}"
    return normalize_score(combined_score), reasoning


# ---------------------------------------------------------------------------
# Pillar 3: Liquidity & Curve Structure (Weight: 20%)
# ---------------------------------------------------------------------------

def calculate_p3_liquidity_curve(
    instrument: Dict[str, Any],
    macro_data: Optional[Dict[str, Any]],
) -> Tuple[float, str]:
    """
    Utilize FRED T10Y2Y spread and sovereign bond yield configurations.
    Yield curve inversions subtract points from equities; widening spreads
    add positive directional scores to higher-yielding currencies.

    Returns (score_component, reasoning).
    """
    asset_class = instrument.get("asset_class", "")

    # Extract T10Y2Y spread
    current_spread = None
    if macro_data and "series" in macro_data:
        for series in macro_data["series"]:
            if series.get("series_id") == "T10Y2Y":
                if series.get("data_points"):
                    current_spread = series["data_points"][-1].get("value")
                break

    if current_spread is None:
        return 5.0, "No yield curve data available - neutral score"

    if asset_class in ("forex_majors", "forex_crosses"):
        # For currencies: steep curve = bullish USD, flat/inverted = bearish USD
        if current_spread > 1.0:
            p3_score = 7.0
            reasoning = f"Steep yield curve ({current_spread:.2f}%) supports higher-yielding currencies"
        elif current_spread > 0.5:
            p3_score = 6.0
            reasoning = f"Moderately steep curve ({current_spread:.2f}%) - modestly supportive"
        elif current_spread > 0:
            p3_score = 5.0
            reasoning = f"Flat yield curve ({current_spread:.2f}%) - neutral for currencies"
        elif current_spread > -0.5:
            p3_score = 4.0
            reasoning = f"Mild inversion ({current_spread:.2f}%) - slightly negative"
        else:
            p3_score = 3.0
            reasoning = f"Deep inversion ({current_spread:.2f}%) - bearish for high-yield currencies"

    elif asset_class == "global_indices":
        # For equities: inverted curve = recession signal = bearish
        if current_spread > 1.0:
            p3_score = 7.5
            reasoning = f"Healthy steep curve ({current_spread:.2f}%) - bullish for equities"
        elif current_spread > 0.3:
            p3_score = 6.5
            reasoning = f"Normal positive curve ({current_spread:.2f}%) - supportive"
        elif current_spread > 0:
            p3_score = 5.0
            reasoning = f"Flattening curve ({current_spread:.2f}%) - neutral/cautious"
        elif current_spread > -0.5:
            p3_score = 3.5
            reasoning = f"Inversion ({current_spread:.2f}%) - recession signal, bearish equities"
        else:
            p3_score = 2.0
            reasoning = f"Deep inversion ({current_spread:.2f}%) - strong recession signal"

    elif asset_class in ("commodities", "crypto"):
        # For commodities/crypto: tightening = bearish (liquidity drain)
        if current_spread > 0.5:
            p3_score = 6.5
            reasoning = f"Positive yield curve ({current_spread:.2f}%) - ample liquidity"
        elif current_spread > 0:
            p3_score = 5.0
            reasoning = f"Flat curve ({current_spread:.2f}%) - neutral liquidity"
        elif current_spread > -0.5:
            p3_score = 3.5
            reasoning = f"Inversion ({current_spread:.2f}%) - tightening liquidity"
        else:
            p3_score = 2.5
            reasoning = f"Deep inversion ({current_spread:.2f}%) - severe liquidity drain"
    else:
        p3_score = 5.0
        reasoning = "Unknown asset class - neutral curve score"

    return normalize_score(p3_score), reasoning


# ---------------------------------------------------------------------------
# Pillar 4: Positioning Extremes (Weight: 20%)
# ---------------------------------------------------------------------------

def calculate_p4_positioning_extremes(
    instrument: Dict[str, Any],
    cftc_data: Optional[Dict[str, Any]],
) -> Tuple[float, str]:
    """
    Determine the 52-week rolling percentile of CFTC Non-Commercial speculative
    net positioning. If positioning exceeds 90th percentile, trigger contrarian
    correction factor.

    Returns (score_component, reasoning).
    """
    asset_class = instrument.get("asset_class", "")
    symbol = instrument.get("symbol", "")

    if not cftc_data or "asset_classes" not in cftc_data:
        return 5.0, "No CFTC positioning data available - neutral"

    # Map instrument asset class to CFTC asset class
    cftc_class_mapping = {
        "forex_majors": "currencies",
        "forex_crosses": "currencies",
        "global_indices": "indices",
        "commodities": "commodities",
        "crypto": "other",
    }
    cftc_class = cftc_class_mapping.get(asset_class, "other")

    asset_class_data = cftc_data["asset_classes"].get(cftc_class)
    if not asset_class_data:
        return 5.0, f"No CFTC data for asset class '{cftc_class}'"

    contracts = asset_class_data.get("contracts", [])
    if not contracts:
        return 5.0, "No contracts in CFTC data"

    # Extract net positions across contracts
    net_positions = []
    for contract in contracts:
        net_pos = contract.get("net_speculative_market_positioning", 0)
        if net_pos is not None:
            net_positions.append(net_pos)

    if not net_positions:
        return 5.0, "No net positioning data available"

    # Calculate aggregate net positioning percentile
    net_positions_array = np.array(net_positions)
    aggregate_net = np.sum(net_positions_array)

    # Estimate percentile based on absolute magnitude relative to open interest
    total_oi = sum(
        contract.get("open_interest", 0) or 0 for contract in contracts
    )

    if total_oi > 0:
        net_oi_ratio = aggregate_net / total_oi
    else:
        net_oi_ratio = 0

    # Map net OI ratio to a score
    if abs(net_oi_ratio) > 0.15:
        # Extreme positioning - apply contrarian correction
        if net_oi_ratio > 0.15:
            p4_base = 8.0  # Very bullish positioning
            contrarian_factor = min(1.0, (net_oi_ratio - 0.15) / 0.10)
            p4_score = p4_base * (1.0 - contrarian_factor * 0.5)  # Reduce weight
            reasoning = (
                f"Extreme net long positioning ({net_oi_ratio:.1%} of OI) - "
                f"contrarian correction applied"
            )
        else:
            p4_base = 2.0  # Very bearish positioning
            contrarian_factor = min(1.0, (abs(net_oi_ratio) - 0.15) / 0.10)
            p4_score = p4_base * (1.0 - contrarian_factor * 0.5)  # Reduce bearishness
            reasoning = (
                f"Extreme net short positioning ({net_oi_ratio:.1%} of OI) - "
                f"contrarian correction applied"
            )
    elif abs(net_oi_ratio) > 0.05:
        # Significant but not extreme
        if net_oi_ratio > 0.05:
            p4_score = 6.5  # Bullish but not extreme
            reasoning = f"Moderate net long positioning ({net_oi_ratio:.1%} of OI)"
        else:
            p4_score = 3.5  # Bearish but not extreme
            reasoning = f"Moderate net short positioning ({net_oi_ratio:.1%} of OI)"
    else:
        # Neutral positioning
        p4_score = 5.0
        reasoning = f"Neutral net positioning ({net_oi_ratio:.1%} of OI)"

    return normalize_score(p4_score), reasoning


# ---------------------------------------------------------------------------
# Combined Scoring Engine
# ---------------------------------------------------------------------------

def calculate_composite_score(
    instrument: Dict[str, Any],
    macro_data: Optional[Dict[str, Any]],
    cftc_data: Optional[Dict[str, Any]],
    fed_funds_rate: Optional[float],
) -> Dict[str, Any]:
    """
    Calculate the final composite score for a single instrument.
    Applies the weighting equation:
        Final Score = (P1 x 0.35) + (P2 x 0.25) + (P3 x 0.20) + (P4 x 0.20)
    """
    # Calculate each pillar
    p1_score, p1_reasoning = calculate_p1_monetary_policy(instrument, macro_data, fed_funds_rate)
    p2_score, p2_reasoning = calculate_p2_growth_inflation(instrument, macro_data)
    p3_score, p3_reasoning = calculate_p3_liquidity_curve(instrument, macro_data)
    p4_score, p4_reasoning = calculate_p4_positioning_extremes(instrument, cftc_data)

    # Apply weights
    final_score = (
        (p1_score * 0.35) +
        (p2_score * 0.25) +
        (p3_score * 0.20) +
        (p4_score * 0.20)
    )

    final_score = normalize_score(final_score)
    bias = classify_bias(final_score)

    result = {
        "symbol": instrument.get("symbol", ""),
        "display_name": instrument.get("display_name", ""),
        "asset_class": instrument.get("asset_class", ""),
        "current_spot_pricing": instrument.get("current_spot_pricing"),
        "twenty_four_hour_percentage_price_variance": instrument.get(
            "twenty_four_hour_percentage_price_variance"
        ),
        "calculated_comprehensive_fundamental_bias": bias,
        "final_composite_score": round(final_score, 4),
        "pillar_scores": {
            "monetary_policy_spread_pillar_1_weight_35": {
                "score": round(p1_score, 4),
                "reasoning": p1_reasoning,
            },
            "growth_inflation_vector_pillar_2_weight_25": {
                "score": round(p2_score, 4),
                "reasoning": p2_reasoning,
            },
            "liquidity_curve_structure_pillar_3_weight_20": {
                "score": round(p3_score, 4),
                "reasoning": p3_reasoning,
            },
            "positioning_extremes_pillar_4_weight_20": {
                "score": round(p4_score, 4),
                "reasoning": p4_reasoning,
            },
        },
    }

    return result


# ---------------------------------------------------------------------------
# Main Analysis Orchestrator
# ---------------------------------------------------------------------------

def main() -> None:
    """Main entry point for the Quantitative Analysis Engine."""
    logger.info("=" * 60)
    logger.info("Bulls & Bears Fundamentals - Quantitative Institutional Analysis Engine")
    logger.info("=" * 60)

    # Load all input data
    logger.info("Loading input data files...")
    market_bias_data = load_json_file(MARKET_BIAS_FILE)
    macro_data = load_json_file(MACRO_DATA_FILE)
    cftc_data = load_json_file(CFTC_COT_FILE)

    if not market_bias_data:
        logger.error("No market bias data available. Run fetch_yfinance.py first.")
        sys.exit(1)

    instruments = market_bias_data.get("instruments", [])
    if not instruments:
        logger.error("No instruments found in market_bias.json.")
        sys.exit(1)

    logger.info(f"Loaded {len(instruments)} instruments for analysis")

    # Extract current Fed Funds Rate from macro data
    fed_funds_rate = None
    if macro_data and "series" in macro_data:
        for series in macro_data["series"]:
            if series.get("series_id") == "FEDFUNDS":
                data_points = series.get("data_points", [])
                if data_points:
                    fed_funds_rate = data_points[-1].get("value")
                break

    if fed_funds_rate is None:
        logger.warning("Could not determine Fed Funds Rate. Using default 5.0%")
        fed_funds_rate = 5.0
    else:
        logger.info(f"Current Effective Federal Reserve Funds Rate: {fed_funds_rate:.2f}%")

    # Run analysis on all instruments
    analysis_results: List[Dict[str, Any]] = []
    bias_distribution: Dict[str, int] = {
        "Very Bearish": 0,
        "Bearish": 0,
        "Neutral": 0,
        "Bullish": 0,
        "Very Bullish": 0,
    }

    for instrument in instruments:
        result = calculate_composite_score(instrument, macro_data, cftc_data, fed_funds_rate)
        analysis_results.append(result)

        # Update distribution
        bias = result.get("calculated_comprehensive_fundamental_bias", "Neutral")
        if bias in bias_distribution:
            bias_distribution[bias] += 1
        else:
            bias_distribution[bias] = 1

    # Aggregate statistics
    scores = [r.get("final_composite_score", 5.0) for r in analysis_results]
    avg_score = np.mean(scores) if scores else 5.0
    median_score = np.median(scores) if scores else 5.0
    std_score = np.std(scores) if scores else 0.0

    # Build output structure
    output: Dict[str, Any] = {
        "meta": {
            "application": "Bulls & Bears Fundamentals",
            "engine": "Quantitative Institutional Analysis Engine",
            "version": "1.0.0",
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "total_instruments_analyzed": len(analysis_results),
            "reference_fed_funds_rate": fed_funds_rate,
        },
        "market_summary": {
            "average_composite_score": round(float(avg_score), 4),
            "median_composite_score": round(float(median_score), 4),
            "standard_deviation_of_scores": round(float(std_score), 4),
            "bias_distribution_across_all_instruments": bias_distribution,
        },
        "instruments": analysis_results,
    }

    # Write analysis results
    try:
        os.makedirs(os.path.dirname(ANALYSIS_RESULTS_FILE), exist_ok=True)
        with open(ANALYSIS_RESULTS_FILE, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        logger.info(f"Analysis results written to {ANALYSIS_RESULTS_FILE}")

        # Also update market_bias.json with bias info embedded
        enriched_instruments = []
        for orig_instr in instruments:
            symbol = orig_instr.get("symbol", "")
            # Find matching analysis result
            for result in analysis_results:
                if result.get("symbol") == symbol:
                    enriched = dict(orig_instr)
                    enriched["calculated_comprehensive_fundamental_bias"] = result.get(
                        "calculated_comprehensive_fundamental_bias", "Neutral"
                    )
                    enriched["final_composite_score"] = result.get("final_composite_score", 5.0)
                    enriched_instruments.append(enriched)
                    break

        if enriched_instruments:
            enriched_market_bias = {
                "meta": market_bias_data.get("meta", {}),
                "instruments": enriched_instruments,
            }
            with open(MARKET_BIAS_FILE, "w", encoding="utf-8") as f:
                json.dump(enriched_market_bias, f, indent=2, ensure_ascii=False)
            logger.info(f"Enriched market_bias.json with bias scores for {len(enriched_instruments)} instruments")

    except (OSError, IOError) as e:
        logger.error(f"Failed to write output files: {e}")
        sys.exit(1)

    # Print summary
    logger.info("=" * 60)
    logger.info("ANALYSIS SUMMARY")
    logger.info(f"  Total Instruments Analyzed: {len(analysis_results)}")
    logger.info(f"  Average Composite Score: {avg_score:.4f}")
    logger.info(f"  Median Composite Score: {median_score:.4f}")
    logger.info(f"  Bias Distribution: {json.dumps(bias_distribution)}")
    logger.info("=" * 60)
    logger.info("Quantitative Institutional Analysis Engine completed successfully.")


if __name__ == "__main__":
    main()