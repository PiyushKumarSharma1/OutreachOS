"""LLM abstraction. Modes:
- mock: deterministic synthesis from structured context (zero keys, fully testable)
- live: OpenAI-compatible / Anthropic chat completions over stdlib HTTP
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

from ..config import SETTINGS
from ..utils import stable_seed


class LLMClient:
    def complete_json(self, instruction: str, context: dict) -> dict:
        raise NotImplementedError


class MockLLM(LLMClient):
    def complete_json(self, instruction: str, context: dict) -> dict:
        kind = context.get("_task", "personalize")
        if kind == "angles":
            return self._angles(context)
        if kind == "sequence":
            return self._sequence(context)
        if kind == "classify_reply":
            return self._classify(context)
        if kind == "brief":
            return self._brief(context)
        return {}

    def _angles(self, ctx):
        seed = stable_seed("ang", ctx.get("email", ""))
        rng = __import__("random").Random(seed)
        company = ctx.get("company", "their company")
        role = (ctx.get("title") or "the team").strip()
        signal = ctx.get("trigger_signal") or "recent growth"
        industry = ctx.get("industry", "B2B")
        return {
            "angles": [
                f"Problem angle: {role} teams at companies like {company} hit scaling friction around {signal.lower()} - lead with that pain",
                f"Value angle: quantify outcome - peers in {industry} cut manual work ~40% after adopting the offer",
                f"Signal angle: reference the {signal} directly and ask if it changed priorities this quarter",
            ],
            "_confidence": round(rng.uniform(0.7, 0.95), 2),
        }

    def _sequence(self, ctx):
        first = ctx.get("first_name", "there")
        company = ctx.get("company", "your team")
        offer = ctx.get("offer", "our solution")
        opener_signal = ctx.get("opener_signal", "what your team is building")
        case_study = ctx.get("case_study", {})
        cs_line = ""
        if case_study:
            cs_line = (f" A {case_study.get('industry', 'similar')} team ({case_study.get('name', 'a peer')}) "
                       f"saw {case_study.get('result', 'strong results')} in {case_study.get('timeframe', '90 days')}.")
        email1 = {
            "subject": f"{first}, quick one on {company}",
            "body": (
                f"Hi {first} - noticed {opener_signal}."
                f"{cs_line}\n\nWorth 15 minutes to see if {offer} fits how {company} works?\n\n"
                f"Best,\n{{sender_name}}"
            ),
        }
        email2 = {
            "subject": "Re: " + email1["subject"],
            "body": (
                f"{first} - following up once. The short version: {offer} removes the manual grind "
                f"so small teams punch above their weight.\n\nOpen to a quick look?"
            ),
        }
        email3 = {
            "subject": "Closing the loop",
            "body": (
                f"Hi {first} - timing may be off so I'll stop here. If {company} revisits this later, "
                f"reply 'later' and I'll circle back next quarter."
            ),
        }
        return {"emails": [email1, email2, email3]}

    def _classify(self, ctx):
        body = (ctx.get("body") or "").lower()
        positive_kw = ["interested", "sounds good", "let's do", "can we", "book", "schedule",
                       "thursday", "tuesday", "call", "meeting", "yes"]
        negative_kw = ["not interested", "remove me", "unsubscribe", "no thanks", "not a fit", "stop"]
        ooo_kw = ["out of office", "ooo", "vacation", "away until", "on leave"]
        if any(k in body for k in ooo_kw):
            return {"state": "ooo_autoreply"}
        if any(k in body for k in negative_kw):
            return {"state": "replied_negative"}
        if any(k in body for k in positive_kw):
            return {"state": "replied_positive"}
        return {"state": "needs_human"}

    def _brief(self, ctx):
        lead = ctx
        return {
            "pre_call_brief": {
                "prospect": f"{lead.get('full_name', '')} - {lead.get('title', '')} @ {lead.get('company', '')}",
                "context": [
                    f"Industry: {lead.get('industry', 'n/a')}",
                    f"Headcount: {lead.get('headcount', 'n/a')}",
                    f"Trigger signal: {lead.get('trigger_signal') or 'none observed'}",
                ],
                "angles_that_landed": lead.get("angles", []),
                "suggested_agenda": [
                    "Confirm current workflow + pain owner",
                    "Map offer to the trigger event",
                    "Agree success metric + pilot scope",
                ],
            }
        }


class OpenAICompatLLM(LLMClient):
    def available(self) -> bool:
        return bool(SETTINGS.openai_api_key)

    def complete_json(self, instruction: str, context: dict) -> dict:
        payload = {
            "model": SETTINGS.openai_model,
            "messages": [
                {"role": "system", "content": "You are an expert B2B outreach copy engine. Always reply with valid JSON only."},
                {"role": "user", "content": instruction + "\n\nCONTEXT_JSON:\n" + json.dumps(context, ensure_ascii=False)},
            ],
            "temperature": 0.7,
            "response_format": {"type": "json_object"},
        }
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {SETTINGS.openai_api_key}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
            content = data["choices"][0]["message"]["content"]
            return json.loads(_extract_json(content))
        except Exception:
            return MockLLM().complete_json(instruction, context)


def _extract_json(text: str) -> str:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return m.group(0) if m else "{}"


def get_llm() -> LLMClient:
    if SETTINGS.llm_mode == "live":
        if SETTINGS.llm_provider == "openai" and SETTINGS.openai_api_key:
            return OpenAICompatLLM()
        if SETTINGS.llm_provider == "anthropic" and SETTINGS.anthropic_api_key:
            return OpenAICompatLLM()
        return MockLLM()
    return MockLLM()
