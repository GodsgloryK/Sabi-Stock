"""LLM narration layer for Smart Stock.

The LLM never computes business numbers — it only rewrites facts that were
computed by `app.services.forecast` / SQL. Every call has a deterministic
fallback so the demo never fails when the API key is missing or the free
tier rate-limits a request.
"""

from __future__ import annotations

import json

import httpx

from app.core.config import settings

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models"
    "/{model}:generateContent"
)
LLM_TIMEOUT_SECONDS = 8.0
MAX_OUTPUT_TOKENS = 800


def _generate(prompt: str, system_instruction: str) -> str | None:
    api_key = settings.gemini_api_key
    if not api_key:
        return None
    payload = {
        "system_instruction": {"parts": [{"text": system_instruction}]},
        "contents": [
            {"role": "user", "parts": [{"text": prompt}]}
        ],
        "generationConfig": {
            "maxOutputTokens": MAX_OUTPUT_TOKENS,
            "temperature": 0.2,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    try:
        response = httpx.post(
            GEMINI_URL.format(model=settings.ai_model),
            headers={"x-goog-api-key": api_key},
            json=payload,
            timeout=LLM_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        body = response.json()
        candidates = body.get("candidates") or []
        if not candidates:
            return None
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(part.get("text", "") for part in parts).strip()
        return text or None
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return None


FORECAST_SYSTEM = (
    "You are the Smart Stock inventory assistant for a small retail business. "
    "You are given facts that were computed by the application's forecasting "
    "engine. Rewrite them as a short, practical 2-3 sentence briefing for the "
    "shop owner. Use every number exactly as provided — never invent, round, "
    "or recalculate figures. Mention Naira amounts with the ₦ symbol when "
    "relevant. Plain, confident tone; no markdown, no bullet points."
)


def narrate_forecast(facts: dict) -> str | None:
    prompt = (
        "Computed restock briefing facts:\n"
        f"{json.dumps(facts, default=str, indent=2)}"
    )
    return _generate(prompt, FORECAST_SYSTEM)


ASSISTANT_SYSTEM = (
    "You are the Smart Stock assistant inside an inventory management app for "
    "a small Nigerian retail business. Answer the owner's question using ONLY "
    "the shop snapshot provided — a JSON object of real, computed figures. "
    "If the answer is not in the snapshot, say you only have today's numbers "
    "and suggest which dashboard section to open. Keep replies under 80 "
    "words, friendly and direct, plain text only. Never invent sales "
    "figures, dates, or product names."
)


def assistant_reply(message: str, history: list[dict], snapshot: dict) -> str | None:
    transcript = "\n".join(
        f"{entry['role']}: {entry['text']}" for entry in history[-6:]
    )
    prompt = (
        f"Shop snapshot (JSON):\n{json.dumps(snapshot, default=str)}\n\n"
        f"Recent conversation:\n{transcript or '(none)'}\n\n"
        f"Owner's question: {message}"
    )
    return _generate(prompt, ASSISTANT_SYSTEM)
