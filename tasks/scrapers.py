"""
tasks/scrapers.py — Lightweight change checks and full scrapers for Jio plans and FAQs.

The pages at JIO_PLANS_URL / JIO_FAQ_URL are client-rendered Next.js shells
with no plan/FAQ data anywhere in the server-side HTML — parsing them with
requests + BeautifulSoup (the original approach) reliably returns nothing,
which is why this file previously always produced 0 results against the
live site. This version hits the same public JSON APIs the Jio frontend
itself calls (found via the browser network tab), which return real
structured data with no authentication required.
"""

import hashlib
import logging
import re

import requests
from bs4 import BeautifulSoup

from config import JIO_PLANS_URL, JIO_FAQ_URL, JIO_PLANS_API_URL, JIO_FAQ_API_URL

logger = logging.getLogger("jio_scrapers")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

# The public FAQ API has 3700+ entries; capped to keep re-ingestion (which
# embeds every FAQ via the Gemini API) fast and within reasonable API cost.
FAQ_PAGE_SIZE = 100
FAQ_MAX_PAGES = 5

# Matches a total data figure like "56GB" or "70 GB" while excluding a
# daily figure like "2GB/Day" — descriptions frequently state a per-day
# rate first ("2GB/Day") followed by the total ("56GB"), or vice versa.
_TOTAL_DATA_RE = re.compile(r"(\d+(?:\.\d+)?)\s*GB(?!\s*/\s*Day)", re.I)
_VALIDITY_RE = re.compile(r"Validity\s*[:\-]\s*(\d+)\s*Days?", re.I)


def fetch_plans_signature() -> str:
    """SHA256 hash of the real plans JSON API response."""
    try:
        resp = requests.get(JIO_PLANS_API_URL, timeout=15, headers=_HEADERS)
        if resp.status_code == 200:
            return hashlib.sha256(resp.content).hexdigest()
        return hashlib.sha256(f"status_{resp.status_code}".encode()).hexdigest()
    except Exception as e:
        logger.warning(f"Error fetching plan signature: {e}")
        return ""


def fetch_faq_signature() -> str:
    """SHA256 hash of the most-recently-updated FAQ page, so an edit to any
    existing FAQ (not just a new one) is caught. Falls back cleanly if the
    'sort' query param is ever rejected by the API."""
    try:
        resp = requests.get(
            JIO_FAQ_API_URL,
            params={"sort[updatedAt]": "desc", "pagination[pageSize]": 20},
            timeout=15,
            headers=_HEADERS,
        )
        if resp.status_code == 200:
            return hashlib.sha256(resp.content).hexdigest()
        return hashlib.sha256(f"status_{resp.status_code}".encode()).hexdigest()
    except Exception as e:
        logger.warning(f"Error fetching FAQ signature: {e}")
        return ""


def _extract_total_data_gb(description: str):
    match = _TOTAL_DATA_RE.search(description or "")
    return float(match.group(1)) if match else None


def _extract_validity(plan: dict) -> str:
    prime = plan.get("primeData") or {}
    amount, unit = prime.get("offerBenefits3"), prime.get("offerBenefits4")
    if amount and unit and str(amount).replace(".", "", 1).isdigit():
        return f"{amount} {unit}"
    match = _VALIDITY_RE.search(plan.get("description") or "")
    return f"{match.group(1)} Days" if match else None


def scrape_jio_plans() -> list[dict]:
    """Fetches the live prepaid mobile plans JSON and normalizes it into
    the same row shape reingest_plans() writes to SQLite."""
    logger.info(f"Fetching plan data from {JIO_PLANS_API_URL}")
    plans = []
    try:
        resp = requests.get(JIO_PLANS_API_URL, timeout=20, headers=_HEADERS)
        if resp.status_code != 200:
            logger.error(f"Plans API returned status {resp.status_code}")
            return []

        data = resp.json()
        for category in data.get("planCategories", []):
            for sub in category.get("subCategories", []):
                category_label = sub.get("type") or category.get("type") or "Plans"
                for plan in sub.get("plans", []):
                    amount = plan.get("amount")
                    if not amount:
                        continue
                    try:
                        price = float(amount)
                    except (TypeError, ValueError):
                        continue

                    subscriptions = ", ".join(
                        s.get("title", "") for s in (plan.get("misc") or {}).get("subscriptions", []) if s.get("title")
                    )
                    description = plan.get("description", "").strip()
                    title = f"Prepaid {category_label} - Rs.{amount}"

                    plans.append({
                        "title": title,
                        "section": "mobile_plans",
                        "category": f"prepaid_{category_label}",
                        "price": price,
                        "validity": _extract_validity(plan),
                        "data_gb": _extract_total_data_gb(description),
                        "speed_mbps": None,
                        "subscriptions": subscriptions or None,
                        "description": f"{title} | {description}" if description else title,
                        "url": JIO_PLANS_URL,
                    })
    except Exception as e:
        logger.error(f"Error scraping live Jio plans: {e}")
    return plans


def scrape_jio_faqs() -> list[dict]:
    """Fetches FAQ content from the public jio-faqs JSON API (paginated up
    to FAQ_MAX_PAGES) and strips the rich-text HTML down to plain text
    suitable for embedding."""
    logger.info(f"Fetching FAQ content from {JIO_FAQ_API_URL}")
    faqs = []
    try:
        for page in range(1, FAQ_MAX_PAGES + 1):
            resp = requests.get(
                JIO_FAQ_API_URL,
                params={"pagination[pageSize]": FAQ_PAGE_SIZE, "pagination[page]": page},
                timeout=20,
                headers=_HEADERS,
            )
            if resp.status_code != 200:
                logger.warning(f"FAQ API page {page} returned status {resp.status_code}, stopping.")
                break

            payload = resp.json()
            entries = payload.get("data", [])
            if not entries:
                break

            for entry in entries:
                attrs = entry.get("attributes", {})
                title = attrs.get("title", "").strip()
                raw_html = attrs.get("description") or attrs.get("myjioDescription") or ""
                content = BeautifulSoup(raw_html, "html.parser").get_text(separator=" ", strip=True)
                if not title or not content:
                    continue

                pathname = attrs.get("pathname", "")
                url = f"https://www.jio.com{pathname}" if pathname else JIO_FAQ_URL

                category = ((attrs.get("jioFaqsCategory") or {}).get("data") or {}).get("attributes", {})

                faqs.append({
                    "section": "faq",
                    "category": category.get("name", "General Help"),
                    "title": title,
                    "content": content,
                    "url": url,
                })

            pagination = payload.get("meta", {}).get("pagination", {})
            if page >= pagination.get("pageCount", page):
                break
    except Exception as e:
        logger.error(f"Error scraping live Jio FAQs: {e}")
    return faqs
