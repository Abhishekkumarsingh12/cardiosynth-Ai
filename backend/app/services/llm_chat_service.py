"""
OpenAI-compatible Chat Completions client + prompt assembly.

Falls back cleanly when disabled, misconfigured, or HTTP errors.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

import httpx

from app.config import get_settings
from app.services.chat_safety_service import build_safety_system_instructions

log = logging.getLogger(__name__)


def is_llm_available() -> bool:
    s = get_settings()
    return bool(s.llm_enabled and (s.openai_api_key or "").strip())


def _strip_json_fence(s: str) -> str:
    t = s.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def _parse_structured_response(content: str) -> Dict[str, Any]:
    raw = _strip_json_fence(content)
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and data.get("reply"):
            return data
    except json.JSONDecodeError:
        pass
    return {
        "reply": content.strip(),
        "summary": None,
        "condition_explanation": None,
        "risk_explanation": None,
        "recommendation": None,
        "tone": None,
        "follow_up_suggestion": None,
    }


def build_system_prompt(*, mode: str) -> str:
    mode_line = "Dashboard chat" if mode == "dashboard" else "Report guidance chat"
    return (
        f"You are CardioSynth AI, a clear and empathetic assistant helping users understand ECG-related outputs from the {mode_line}.\n"
        + build_safety_system_instructions()
        + "\nResponse format: reply with VALID JSON ONLY (no markdown outside JSON) with keys:\n"
        "reply (string, main answer, can use short markdown-like **bold** sparingly),\n"
        "summary (string, one short paragraph),\n"
        "condition_explanation (string, educational),\n"
        "risk_explanation (string, ties to risk/confidence),\n"
        "recommendation (string, safe next steps, non-prescriptive),\n"
        "tone (one of: reassuring, cautious, serious_calm, neutral_helpful),\n"
        "follow_up_suggestion (string, one inviting follow-up question or topic).\n"
    )


def call_chat_completions(
    *,
    system_prompt: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.4,
) -> Optional[str]:
    s = get_settings()
    if not is_llm_available():
        return None
    url = (s.openai_base_url or "").rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {s.openai_api_key.strip()}",
        "Content-Type": "application/json",
    }
    payload: Dict[str, Any] = {
        "model": s.llm_model,
        "temperature": temperature,
        "messages": [{"role": "system", "content": system_prompt}, *messages],
    }
    try:
        with httpx.Client(timeout=s.llm_timeout_seconds) as client:
            r = client.post(url, headers=headers, json={**payload, "response_format": {"type": "json_object"}})
            if r.status_code >= 400:
                r = client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
        choices = data.get("choices") or []
        if not choices:
            return None
        msg = (choices[0].get("message") or {}).get("content")
        return str(msg) if msg else None
    except Exception as e:
        log.warning("LLM chat completion failed: %s", e)
        return None


def run_llm_turn(
    *,
    user_message: str,
    grounding_json: Dict[str, Any],
    history: List[dict],
    mode: str,
) -> Optional[Dict[str, Any]]:
    """
    Returns structured dict with at least 'reply', or None on failure.
    """
    sys_p = build_system_prompt(mode=mode)
    ctx_blob = json.dumps(grounding_json, ensure_ascii=False, indent=2)[:24000]
    user_block = (
        f"ECG_CONTEXT_JSON:\n{ctx_blob}\n\n"
        f"USER_MESSAGE:\n{user_message.strip()[:8000]}\n\n"
        "Answer using the context. If a field is unknown, say so. "
        "Respect data_source / report_type differences (CSV vs OCR vs image waveform)."
    )
    msgs: List[Dict[str, str]] = []
    for h in history[-20:]:
        role = h.get("role")
        content = h.get("content")
        if role in ("user", "assistant") and content:
            msgs.append({"role": str(role), "content": str(content)[:12000]})
    msgs.append({"role": "user", "content": user_block})

    raw = call_chat_completions(system_prompt=sys_p, messages=msgs)
    if not raw:
        return None
    parsed = _parse_structured_response(raw)
    return parsed
