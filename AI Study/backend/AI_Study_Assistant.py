"""Gemini-powered study assistant service."""

import json
import os
from urllib import error as urlerror
from urllib import request as urlrequest


def ask_gemini(question):
    """Return an AI study answer or an explicit error message."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None, "AI is not configured. Set the GEMINI_API_KEY environment variable."

    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        f"?key={api_key}"
    )
    payload = {
        "system_instruction": {
            "parts": [
                {
                    "text": (
                        "You are AI Study Assistant. Help students learn clearly and safely. "
                        "Explain concepts step by step, use short examples, and do not do "
                        "graded work dishonestly. If a question is ambiguous, ask for context."
                    )
                }
            ]
        },
        "contents": [{"role": "user", "parts": [{"text": question}]}],
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 800},
    }
    request = urlrequest.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlrequest.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urlerror.HTTPError:
        return None, "The AI service rejected the request. Check your API key and model."
    except (urlerror.URLError, TimeoutError):
        return None, "The AI service is temporarily unavailable. Please try again."
    except (json.JSONDecodeError, KeyError, TypeError):
        return None, "The AI service returned an unexpected response."

    try:
        answer = result["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError, AttributeError):
        return None, "The AI service returned an empty answer."
    return answer, None
