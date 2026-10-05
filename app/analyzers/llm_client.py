"""
LLM Client for Requirement & Ambiguity Analysis (Day 7).

Calls Google Gemini API using pure HTTP (via httpx) to avoid heavy SDK dependencies.
Includes intelligent heuristic fallback so development and offline test suites work
reliably under all network conditions.
"""

import json
import os
import re
from typing import Dict, Any, List
import httpx
from dotenv import load_dotenv

from app.analyzers.prompt import ANALYZER_SYSTEM_PROMPT, build_analysis_prompt

load_dotenv()


class LLMClient:
    GEMINI_MODELS = ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"]
    DEFAULT_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    @classmethod
    def get_api_key(cls) -> str:
        return os.getenv("GEMINI_API_KEY", "").strip()

    @classmethod
    def analyze_chunks(cls, chunks: list) -> Dict[str, Any]:
        """
        Sends chunks to Google Gemini API to extract requirements & ambiguities.
        Falls back to rule-based analysis if API key is invalid or offline.
        """
        api_key = cls.get_api_key()

        if api_key and not api_key.startswith("mock_"):
            try:
                result = cls._call_gemini_api(chunks, api_key)
                if result and ("requirements" in result or "ambiguities" in result):
                    return result
            except Exception as e:
                print(f"[LLMClient] Gemini API call returned error: {e}. Falling back to heuristic extractor.")

        # Fallback heuristic extractor
        return cls._heuristic_extraction(chunks)

    @classmethod
    def _call_gemini_api(cls, chunks: list, api_key: str) -> Dict[str, Any]:
        """Calls Google Gemini REST API with JSON output mode."""
        user_prompt = build_analysis_prompt(chunks)

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f"{ANALYZER_SYSTEM_PROMPT}\n\n{user_prompt}"}]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json"
            }
        }

        # Try gemini models
        for model in cls.GEMINI_MODELS:
            url = cls.DEFAULT_API_URL.format(model=model, api_key=api_key)
            try:
                response = httpx.post(url, json=payload, timeout=25.0)
                if response.status_code == 200:
                    data = response.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        text_response = candidates[0]["content"]["parts"][0]["text"].strip()
                        # Clean any stray markdown ticks if present
                        clean_json = re.sub(r"^```json\s*", "", text_response)
                        clean_json = re.sub(r"\s*```$", "", clean_json)
                        return json.loads(clean_json)
                else:
                    print(f"[LLMClient] Model {model} responded with {response.status_code}: {response.text[:120]}")
            except Exception as e:
                print(f"[LLMClient] Attempt with {model} failed: {e}")

        raise RuntimeError("All Gemini API attempts failed or invalid key format.")

    @classmethod
    def _heuristic_extraction(cls, chunks: list) -> Dict[str, Any]:
        """
        Intelligent rule-based parser that identifies testable requirements and ambiguities
        directly from chunk sentences. Ensures 100% deterministic fallback.
        """
        requirements = []
        ambiguities = []

        req_keywords = ["must", "shall", "should", "will", "can", "requires", "allow", "valid", "score", "qualify"]
        ambiguity_triggers = ["fast", "secure", "user-friendly", "appropriate", "reasonable", "as needed", "etc"]

        for c in chunks:
            cid = getattr(c, "chunk_id", None) or c.get("chunk_id")
            text = getattr(c, "text", None) or c.get("text", "")

            # Split text by lines and sentences
            sentences = re.split(r"(?<=[.!?])\s+|\n+", text)

            for s in sentences:
                s = s.strip().strip("-*• ")
                if len(s) < 15 or s.startswith("| ---"):
                    continue

                lower_s = s.lower()

                # 1. Identify Requirements
                if any(kw in lower_s for kw in req_keywords) or s.startswith("|") or "def " in s:
                    clean_req = s
                    if clean_req.startswith("|"):
                        # Format table row into requirement
                        cells = [col.strip() for col in clean_req.split("|") if col.strip()]
                        if len(cells) >= 2:
                            clean_req = f"Specification row: {', '.join(cells)}"

                    requirements.append({
                        "text": clean_req,
                        "linked_chunk_ids": [cid],
                        "confidence": 0.95 if any(kw in lower_s for kw in ["must", "shall"]) else 0.85
                    })

                # 2. Identify Ambiguities
                for trigger in ambiguity_triggers:
                    if trigger in lower_s:
                        ambiguities.append({
                            "description": f"Vague or subjective term '{trigger}' used in statement: '{s[:80]}...'",
                            "suggested_clarification": f"Please specify precise numerical metrics or verifiable criteria for '{trigger}'."
                        })
                        break

        # Deduplicate requirements by text
        seen = set()
        unique_reqs = []
        for r in requirements:
            if r["text"] not in seen:
                seen.add(r["text"])
                unique_reqs.append(r)

        return {
            "requirements": unique_reqs,
            "ambiguities": ambiguities
        }
