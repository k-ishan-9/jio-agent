"""
agent/adk_agent.py — the ADK agent definition, wrapping the two retrieval tools.
"""

import os
from typing import Optional

from config import GOOGLE_API_KEY, AGENT_MODEL

os.environ["GOOGLE_API_KEY"] = GOOGLE_API_KEY  # ADK reads this env var directly

from google.adk.agents import Agent

from retrieval.tools import query_jio_plans, search_jio_knowledge


async def find_jio_plans(
    max_price: float = 0.0, min_price: float = 0.0, min_data_gb: float = 0.0,
    min_speed_mbps: float = 0.0, section: str = "", category: str = "",
    validity: str = "", subscription: str = "",
) -> dict:
    """Search Jio's structured mobile and fiber plan database with filters.

    Use this tool for any question about specific plan prices, data amounts,
    validity periods, fiber speeds, or which plans include a given OTT
    subscription (e.g. Netflix, Amazon Prime). Do NOT use this for general
    questions like "how do I port my number" — use search_jio_faq_and_info instead.

    Args:
        max_price: Maximum price in rupees.
        min_price: Minimum price in rupees.
        min_data_gb: Minimum data allowance in GB.
        min_speed_mbps: Minimum fiber/airfiber speed in Mbps.
        section: Either "mobile_plans" or "fiber". Leave unset to search both.
        category: Partial match, e.g. "prepaid", "postpaid", "5G", "fiber_home".
        validity: Partial match on billing cycle, e.g. "Monthly".
        subscription: Partial match on included OTT subscriptions, e.g. "Netflix".

    Returns:
        A dict with "status" and "plans" (list of matching plan dicts).
    """
    results = await query_jio_plans(
        max_price=max_price if max_price > 0.0 else None,
        min_price=min_price if min_price > 0.0 else None,
        min_data=min_data_gb if min_data_gb > 0.0 else None,
        min_speed=min_speed_mbps if min_speed_mbps > 0.0 else None,
        section=section if section != "" else None,
        category=category if category != "" else None,
        validity=validity if validity != "" else None,
        subscription=subscription if subscription != "" else None,
    )
    if not results:
        return {
            "status": "no_results",
            "message": "No plans matched these filters. This is a real result, "
                       "not an error — tell the user no such plan exists.",
            "plans": [],
        }
    return {"status": "success", "plans": results}


async def search_jio_faq_and_info(query: str, section_filter: str = "") -> dict:
    """Semantic search over Jio's FAQ articles, business/enterprise pages, and app descriptions.

    Use this for general "how do I..." questions, policy questions,
    troubleshooting, porting, business/enterprise services, or app features.
    Do NOT use this for plan pricing — use find_jio_plans for those.

    Args:
        query: The user's natural-language question.
        section_filter: Optionally restrict to "faq", "business", or "apps".

    Returns:
        A dict with "status" and "results" (list of matching content chunks).
    """
    results = await search_jio_knowledge(
        query,
        top_k=5,
        section_filter=section_filter if section_filter != "" else None
    )
    if not results:
        return {"status": "no_results", "message": "No relevant content found.", "results": []}
    return {"status": "success", "results": results}


root_agent = Agent(
    model=AGENT_MODEL,
    name="jio_assistant",
    description="Answers questions about Jio's mobile plans, fiber plans, FAQs, business services, and apps.",
    instruction=(
        "You are a helpful assistant for Jio (an Indian telecom/digital services company). "
        "You have two tools:\n\n"
        "1. find_jio_plans — for structured questions about plan prices, data, validity, "
        "fiber speed, or OTT subscriptions included.\n"
        "2. search_jio_faq_and_info — for general questions, how-to guides, porting, "
        "troubleshooting, business services, and app features.\n\n"
        "Always call the appropriate tool before answering — do not answer from your own "
        "knowledge, since Jio's plans and policies change and you must be grounded in the "
        "actual current data. If a tool returns no_results, tell the user clearly that "
        "nothing matched rather than guessing an answer. When you do have results, cite "
        "specific plan names/prices or FAQ content, and mention the source URL if available."
    ),
    tools=[find_jio_plans, search_jio_faq_and_info],
)
