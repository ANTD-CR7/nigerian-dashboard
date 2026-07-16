# NPEDATA - AI "ask the data" assistant.
#
# Copyright 2026 Taoheed Abdulmanan Olaosebikan (Matric 22/10267,
# Computer Science, Caleb University, Lagos). Apache-2.0; see LICENSE/NOTICE.
# Provenance fingerprint 3b191f211c44c1286fd5ec5cf9ddb867988c33da3ea228040c9a7b53226c6966
#
# The assistant is deliberately grounded: it retrieves real figures from the
# platform, hands them to the model, and instructs it to answer ONLY from those
# figures and to cite them. It never invents numbers. If no API key is set it
# degrades gracefully (the route returns 503), so the rest of the API is
# unaffected. No third-party SDK: the Anthropic call is a plain HTTPS POST.

from __future__ import annotations

import json
import os
import urllib.request

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = os.environ.get("NPE_AI_MODEL", "claude-sonnet-5")

SYSTEM_PROMPT = (
    "You are the data assistant for NPEDATA, a platform of Nigerian public "
    "economic data (CBN, NBS, World Bank). You will be given a user question and "
    "a JSON block of REAL figures retrieved from the platform. Rules:\n"
    "1. Answer ONLY using the figures provided. Never invent or estimate numbers.\n"
    "2. Always cite the indicator name and the observation date for any figure.\n"
    "3. If the provided data does not answer the question, say so plainly and "
    "name what IS available.\n"
    "4. Correlation is not causation; if asked 'why', explain you can describe "
    "what the data shows, not prove causes.\n"
    "5. Be concise and plain-spoken. Two or three short paragraphs at most.\n"
    "6. Do not give financial advice."
)


def key_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def match_indicators(question: str, indicators: dict, limit: int = 6) -> list[str]:
    """Pick indicators whose id or name tokens appear in the question."""
    q = question.lower()
    hits = []
    for iid, meta in indicators.items():
        name = str(meta.get("name", "")).lower()
        toks = [iid.replace("_", " "), iid] + [t for t in name.split() if len(t) > 3]
        if any(t and t in q for t in toks):
            hits.append(iid)
    # a few sensible fallbacks by keyword
    aliases = {
        "inflation": "inflation", "naira": "exchange_rate", "exchange": "exchange_rate",
        "dollar": "exchange_rate", "gdp": "gdp", "growth": "gdp", "reserves": "fx_reserves",
        "interest": "interest_rate", "mpr": "interest_rate", "rate": "interest_rate",
    }
    for kw, iid in aliases.items():
        if kw in q and iid in indicators and iid not in hits:
            hits.append(iid)
    return hits[:limit]


def call_anthropic(user_content: str, api_key: str, model: str = None,
                   max_tokens: int = 700, timeout: float = 40.0) -> dict:
    """POST to the Anthropic Messages API and return {text, model, usage}."""
    payload = {
        "model": model or DEFAULT_MODEL,
        "max_tokens": max_tokens,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_content}],
    }
    req = urllib.request.Request(
        ANTHROPIC_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    text = "".join(block.get("text", "") for block in data.get("content", []))
    return {"text": text.strip(), "model": data.get("model"), "usage": data.get("usage")}


def build_user_message(question: str, data_context: dict) -> str:
    return (
        f"User question:\n{question}\n\n"
        f"Real figures retrieved from NPEDATA (JSON):\n"
        f"{json.dumps(data_context, ensure_ascii=False, indent=2)}\n\n"
        f"Answer the question using only these figures, citing indicator and date."
    )
