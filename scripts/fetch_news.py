#!/usr/bin/env python3
"""
Bulls & Bears Fundamentals - Live News Feed Pipeline
Fetches global financial market headlines from NewsData.io and Finnhub APIs.
Runs on an independent high-frequency schedule. Outputs structured data
to data/live_news.json
"""

import os
import sys
import json
import time
import logging
import html
from datetime import datetime, timezone
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
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "live_news.json")

# API Endpoints
NEWSDATA_BASE_URL = "https://newsdata.io/api/1"
FINNHUB_BASE_URL = "https://finnhub.io/api/v1"

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5
REQUEST_TIMEOUT = 30

# Maximum number of articles to keep
MAX_ARTICLES = 200

# Asset tag keywords for classification
ASSET_TAG_KEYWORDS: Dict[str, List[str]] = {
    "forex": [
        "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USDCAD", "USDCHF",
        "NZD/USD", "forex", "currency", "dollar", "euro", "pound", "yen",
        "swiss franc", "canadian dollar", "australian dollar", "kiwi",
        "central bank", "interest rate", "monetary policy",
    ],
    "equities": [
        "stock", "equity", "S&P 500", "NASDAQ", "DOW JONES", "NYSE",
        "share", "dividend", "buyback", "IPO", "earnings", "bull market",
        "bear market", "rally", "sell-off", "correction",
    ],
    "commodities": [
        "gold", "silver", "crude oil", "natural gas", "copper", "platinum",
        "palladium", "commodity", "wheat", "corn", "soybean", "OPEC",
        "energy", "precious metal", "base metal",
    ],
    "crypto": [
        "bitcoin", "ethereum", "crypto", "blockchain", "BTC", "ETH",
        "altcoin", "defi", "nft", "web3", "solana", "ripple", "XRP",
        "cardano", "polkadot", "dogecoin",
    ],
    "macro": [
        "GDP", "CPI", "inflation", "unemployment", "payrolls", "FOMC",
        "federal reserve", "treasury", "yield", "recession", "economic",
        "fiscal", "stimulus", "trade", "manufacturing", "services PMI",
    ],
}


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def load_environment_variables() -> Dict[str, Optional[str]]:
    """Load API keys from environment variables."""
    load_dotenv()
    return {
        "newsdata_key": os.getenv("NEWSDATA_API_KEY"),
        "finnhub_key": os.getenv("FINNHUB_API_KEY"),
    }


def classify_asset_tags(headline: str, description: str = "") -> List[str]:
    """
    Classify which asset classes a news article relates to based on keyword matching.
    Returns a list of asset tag strings.
    """
    combined_text = (headline + " " + description).lower()
    tags: List[str] = []

    for asset_class, keywords in ASSET_TAG_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in combined_text:
                tags.append(asset_class)
                break

    return tags if tags else ["general"]


def clean_text(text: str) -> str:
    """Clean HTML entities and special characters from text."""
    text = html.unescape(text)
    text = text.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
    text = ' '.join(text.split())  # Collapse multiple spaces
    return text.strip()


def fetch_newsdata_articles(api_key: str) -> List[Dict[str, Any]]:
    """
    Fetch financial news articles from NewsData.io API.
    """
    articles: List[Dict[str, Any]] = []
    if not api_key:
        logger.warning("No NewsData.io API key provided. Skipping.")
        return articles

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            url = f"{NEWSDATA_BASE_URL}/news"
            params = {
                "apikey": api_key,
                "category": "business",
                "language": "en",
                "size": 50,
            }

            logger.info(f"Fetching news from NewsData.io - Attempt {attempt}/{MAX_RETRIES}")
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            data = response.json()

            if data.get("status") != "success":
                logger.warning(f"NewsData.io API returned non-success status: {data.get('status')}")
                return articles

            results = data.get("results", [])
            for item in results:
                try:
                    headline = clean_text(item.get("title", ""))
                    if not headline:
                        continue

                    description = clean_text(item.get("description", "") or "")
                    source = item.get("source_id", "") or item.get("source", "") or "NewsData.io"
                    link = item.get("link", "") or ""
                    pub_date = item.get("pubDate", "") or item.get("published_at", "") or ""

                    # Classify asset tags
                    tags = classify_asset_tags(headline, description)

                    articles.append({
                        "headline": headline,
                        "description": description[:300] if description else "",
                        "source": source,
                        "publication_date": pub_date,
                        "article_url": link,
                        "asset_tags": tags,
                    })
                except (KeyError, ValueError, TypeError) as e:
                    logger.debug(f"Error parsing NewsData.io article: {e}")
                    continue

            logger.info(f"Fetched {len(articles)} articles from NewsData.io")
            return articles

        except requests.exceptions.RequestException as e:
            logger.warning(f"NewsData.io request failed: {e}")
            if attempt < MAX_RETRIES:
                wait_time = RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
                time.sleep(wait_time)
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            logger.error(f"JSON parsing error from NewsData.io: {e}")
            break

    logger.error("All NewsData.io fetch attempts failed.")
    return articles


def fetch_finnhub_news(api_key: str) -> List[Dict[str, Any]]:
    """
    Fetch financial news articles from Finnhub API.
    """
    articles: List[Dict[str, Any]] = []
    if not api_key:
        logger.warning("No Finnhub API key provided. Skipping.")
        return articles

    # Finnhub provides market news via the 'news' endpoint
    categories = ["general", "forex", "crypto", "merger", "earnings"]

    for category in categories:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                url = f"{FINNHUB_BASE_URL}/news"
                params = {
                    "category": category,
                    "token": api_key,
                    "minId": 0,
                }

                logger.info(
                    f"Fetching Finnhub news category '{category}' - Attempt {attempt}/{MAX_RETRIES}"
                )
                response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
                response.raise_for_status()
                data = response.json()

                if not data or not isinstance(data, list):
                    continue

                for item in data:
                    try:
                        headline = clean_text(item.get("headline", ""))
                        if not headline:
                            continue

                        summary = clean_text(item.get("summary", "") or "")
                        source = item.get("source", "") or "Finnhub"
                        link = item.get("url", "") or ""
                        pub_date = item.get("datetime", 0)

                        # Convert Unix timestamp to ISO format
                        if pub_date:
                            try:
                                pub_date_iso = datetime.fromtimestamp(
                                    int(pub_date), tz=timezone.utc
                                ).isoformat()
                            except (ValueError, TypeError, OSError):
                                pub_date_iso = ""
                        else:
                            pub_date_iso = ""

                        # Classify asset tags
                        tags = classify_asset_tags(headline, summary)

                        articles.append({
                            "headline": headline,
                            "description": summary[:300] if summary else "",
                            "source": source,
                            "publication_date": pub_date_iso,
                            "article_url": link,
                            "asset_tags": tags,
                        })
                    except (KeyError, ValueError, TypeError) as e:
                        logger.debug(f"Error parsing Finnhub article: {e}")
                        continue

                logger.info(f"Fetched Finnhub category '{category}'")
                break  # Success, move to next category

            except requests.exceptions.RequestException as e:
                logger.warning(f"Finnhub request for '{category}' failed: {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY_SECONDS * (2 ** (attempt - 1)))
                else:
                    logger.error(f"All Finnhub attempts failed for '{category}'.")

    logger.info(f"Total Finnhub articles fetched: {len(articles)}")
    return articles


def merge_and_deduplicate_articles(articles_list: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """
    Merge articles from multiple sources and deduplicate by headline.
    """
    seen_headlines: set = set()
    merged: List[Dict[str, Any]] = []

    for articles in articles_list:
        for article in articles:
            headline_key = article.get("headline", "").strip().upper()[:100]
            if headline_key and headline_key not in seen_headlines:
                seen_headlines.add(headline_key)
                merged.append(article)

    # Sort by publication date (most recent first)
    def sort_key(article: Dict[str, Any]) -> str:
        return article.get("publication_date", "") or ""

    merged.sort(key=sort_key, reverse=True)

    # Limit to MAX_ARTICLES
    return merged[:MAX_ARTICLES]


def build_news_output(articles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build the final structured output for the live news feed.
    """
    # Count by asset tag
    tag_counts: Dict[str, int] = {}
    for article in articles:
        for tag in article.get("asset_tags", []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    output: Dict[str, Any] = {
        "meta": {
            "source": "NewsData.io, Finnhub",
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "total_articles": len(articles),
            "breakdown_by_asset_tag": tag_counts,
        },
        "articles": articles,
    }

    return output


def write_output(data: Dict[str, Any], filepath: str) -> None:
    """Write the output JSON to disk with explicit UTF-8 encoding."""
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Live news data successfully written to {filepath}")
    except (OSError, IOError) as e:
        logger.error(f"Failed to write output file '{filepath}': {e}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Main Execution
# ---------------------------------------------------------------------------

def main() -> None:
    """Main entry point for the Live News Feed Pipeline."""
    logger.info("=" * 60)
    logger.info("Bulls & Bears Fundamentals - Live News Feed Pipeline")
    logger.info("=" * 60)

    api_keys = load_environment_variables()

    # Fetch from multiple sources
    newsdata_articles = fetch_newsdata_articles(api_keys.get("newsdata_key", ""))
    finnhub_articles = fetch_finnhub_news(api_keys.get("finnhub_key", ""))

    # Merge and deduplicate
    all_articles = merge_and_deduplicate_articles([newsdata_articles, finnhub_articles])

    if not all_articles:
        logger.warning("No news articles were fetched. Writing empty dataset.")
        empty_output = {
            "meta": {
                "source": "NewsData.io, Finnhub",
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "total_articles": 0,
                "breakdown_by_asset_tag": {},
            },
            "articles": [],
        }
        write_output(empty_output, OUTPUT_FILE)
        logger.info("Empty news file written.")
        return

    # Build output
    output = build_news_output(all_articles)

    # Write to file
    write_output(output, OUTPUT_FILE)

    logger.info(f"Live News Feed Pipeline completed. Total articles: {len(all_articles)}")


if __name__ == "__main__":
    main()