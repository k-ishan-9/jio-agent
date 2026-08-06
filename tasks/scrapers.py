"""
tasks/scrapers.py — Lightweight change checks and full scrapers for Jio plans and FAQs.
"""

import hashlib
import json
import logging
import requests
from bs4 import BeautifulSoup
from config import JIO_PLANS_URL, JIO_FAQ_URL

logger = logging.getLogger("jio_scrapers")


def fetch_plans_signature() -> str:
    """
    Perform a lightweight check of the Jio plan endpoint / page.
    Returns SHA256 hash of response body / ETag to detect changes cheap.
    """
    try:
        resp = requests.get(JIO_PLANS_URL, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            return hashlib.sha256(resp.content).hexdigest()
        return hashlib.sha256(f"status_{resp.status_code}".encode()).hexdigest()
    except Exception as e:
        logger.warning(f"Error fetching plan signature: {e}")
        return ""


def fetch_faq_signature() -> str:
    """
    Perform a lightweight HEAD/GET request on Jio FAQ endpoint.
    Returns composite signature from ETag, Last-Modified, or content length/hash.
    """
    try:
        resp = requests.head(JIO_FAQ_URL, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        etag = resp.headers.get("ETag", "")
        last_modified = resp.headers.get("Last-Modified", "")
        content_len = resp.headers.get("Content-Length", "")
        if etag or last_modified:
            return hashlib.sha256(f"{etag}_{last_modified}_{content_len}".encode()).hexdigest()
        
        # Fallback to lightweight GET hash
        resp_get = requests.get(JIO_FAQ_URL, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        return hashlib.sha256(resp_get.content).hexdigest()
    except Exception as e:
        logger.warning(f"Error fetching FAQ signature: {e}")
        return ""


def scrape_jio_plans() -> list[dict]:
    """
    Scrapes or fetches the latest Jio plans.
    Returns a list of plan dictionaries ready for SQLite insertion.
    """
    logger.info(f"Scraping plan data from {JIO_PLANS_URL}")
    plans = []
    try:
        resp = requests.get(JIO_PLANS_URL, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            # Parse plan cards if present in HTML
            cards = soup.find_all("div", class_="plan-card") or soup.find_all("div", class_="card")
            for card in cards:
                title = card.find("h3") or card.find("div", class_="title")
                price = card.find("span", class_="price") or card.find("div", class_="price")
                if title and price:
                    plans.append({
                        "title": title.get_text(strip=True),
                        "section": "prepaid",
                        "category": "Daily Data",
                        "price": float("".join(filter(str.isdigit, price.get_text())) or 0),
                        "validity": "28 days",
                        "data_gb": 1.5,
                        "speed_mbps": 100,
                        "subscriptions": "JioTV, JioCinema",
                        "description": f"{title.get_text(strip=True)} with price {price.get_text(strip=True)}",
                        "url": JIO_PLANS_URL,
                    })
    except Exception as e:
        logger.error(f"Error scraping live Jio plans: {e}")
    return plans


def scrape_jio_faqs() -> list[dict]:
    """
    Scrapes or fetches the latest Jio FAQ items.
    Returns list of FAQ Q&A dict items.
    """
    logger.info(f"Scraping FAQ content from {JIO_FAQ_URL}")
    faqs = []
    try:
        resp = requests.get(JIO_FAQ_URL, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            items = soup.find_all("div", class_="faq-item") or soup.find_all("details")
            for item in items:
                q = item.find("summary") or item.find("h4")
                a = item.find("p") or item.find("div", class_="answer")
                if q and a:
                    faqs.append({
                        "section": "faq",
                        "category": "General Help",
                        "title": q.get_text(strip=True),
                        "content": a.get_text(strip=True),
                        "url": JIO_FAQ_URL,
                    })
    except Exception as e:
        logger.error(f"Error scraping live Jio FAQs: {e}")
    return faqs
