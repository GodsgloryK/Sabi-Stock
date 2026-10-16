"""Deterministic local responder for the Smart Stock assistant.

Used whenever the LLM API key is missing or the upstream call fails, so the
assistant always answers from the same computed shop snapshot.
"""

from __future__ import annotations

import re


def _fmt_naira(value) -> str:
    return f"₦{float(value):,.2f}"


def _urgent_lines(snapshot: dict) -> list[str]:
    lines = []
    for item in snapshot.get("urgent_reorders", []):
        reorder_by = item.get("reorder_by") or "as soon as possible"
        lines.append(
            f"{item['name']}: {item['stock']} in stock, ~{item['rate_per_day']:g}/day, "
            f"order by {reorder_by} ({item['suggested_qty']} units)"
        )
    return lines


def _low_lines(snapshot: dict) -> list[str]:
    return [
        f"{item['name']} ({item['stock']} left)"
        for item in snapshot.get("low_stock", [])
    ]


def _top_lines(snapshot: dict) -> list[str]:
    return [
        f"{item['name']} — {item['units']} units"
        for item in snapshot.get("top_sellers_30d", [])
    ]


def local_reply(message: str, snapshot: dict) -> str:
    text = message.lower().strip()

    if re.search(r"\b(hello|hi|hey|good (morning|afternoon|evening))\b", text):
        return (
            "Hi! I'm your Smart Stock assistant. Ask me what to restock, "
            "what sold best, or how today's sales are doing."
        )

    if re.search(r"\b(best|top|popular|selling|sold most|fastest)\b", text):
        tops = _top_lines(snapshot)
        if not tops:
            return "No sales recorded yet, so there are no best sellers to show."
        return "Top sellers over the last 30 days: " + "; ".join(tops) + "."

    if re.search(r"\b(restock|reorder|order more|buy more|supply|run out|running out)\b", text):
        urgent = _urgent_lines(snapshot)
        if not urgent:
            return (
                "Nothing needs reordering right now — no product is projected "
                "to run out in the next 10 days."
            )
        return "Reorder now: " + "; ".join(urgent) + "."

    if re.search(r"\b(low|low stock|almost out|stock level)\b", text):
        low = _low_lines(snapshot)
        threshold = snapshot.get("low_stock_threshold", 5)
        if not low:
            return f"Everything is above the low-stock threshold of {threshold} units."
        return f"Below the threshold of {threshold} units: " + "; ".join(low) + "."

    if re.search(r"\b(today|this morning|made|revenue|profit|sales amount|earn)\b", text):
        today = snapshot.get("today", {})
        return (
            f"Today's sales are {_fmt_naira(today.get('sales_amount', 0))} "
            f"with {_fmt_naira(today.get('profit', 0))} profit "
            f"as at {snapshot.get('date', '')} ({snapshot.get('timezone', '')})."
        )

    if re.search(r"\b(how many|total|how much stock|inventory)\b", text):
        totals = snapshot.get("totals", {})
        return (
            f"{totals.get('products', 0)} products and "
            f"{totals.get('stock_units', 0)} units in stock across the business."
        )

    if re.search(r"\b(where|dashboard|export|csv|report|how do i)\b", text):
        return (
            "Open the Dashboard for KPIs and charts, the Insights page for "
            "reorder forecasts, Products to edit your catalogue, and Sales to "
            "record or export transactions (CSV export lives at the top of "
            "Products and Sales)."
        )

    return (
        "I answer from today's shop snapshot. Try: 'What should I restock?', "
        "'What sold best?', 'Am I low on anything?', or 'How much did I make today?'"
    )
