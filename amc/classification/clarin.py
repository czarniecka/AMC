"""The same classification through a hosted model of CLARIN-PL (OpenAI-compatible API).

The instruction, labels and validation are those of the local Ollama classifier, so results
differ only by the model. Requires CLARIN_TOKEN; list available models with `models()`.
"""

import json
import random
import re
import time
from collections.abc import Callable

import requests

from amc.classification.classifier import INSTRUCTION, validate_labels

API = "https://services.clarin-pl.eu/api/v1/oapi"


class ClarinError(Exception):
    """A safe, human-readable failure suitable for console output."""


class ClarinClient:
    def __init__(
        self,
        token: str,
        *,
        user_agent: str,
        delay: tuple[float, float] = (0.0, 0.1),
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not token.strip():
            raise ClarinError("Set CLARIN_TOKEN in .env or the environment before classifying.")
        # No shared session: requests are sent from several threads.
        self._headers = {"User-Agent": user_agent, "Authorization": "Bearer " + token}
        self.delay = delay
        self._sleeper = sleeper

    def models(self) -> list[str]:
        response = requests.get(API + "/models", headers=self._headers, timeout=30)
        if response.status_code != 200:
            raise ClarinError(f"CLARIN-PL returned HTTP {response.status_code}.")
        return [model.get("id", "") for model in response.json().get("data", [])]

    def complete(self, model: str, text: str) -> str:
        """Raw answer text; retries network failures, 429 and 5xx with growing waits."""
        body = {
            "model": model,
            "temperature": 0,
            "max_tokens": 100,
            "messages": [
                {"role": "system", "content": INSTRUCTION},
                {"role": "user", "content": text},
            ],
        }
        for attempt in range(6):
            try:
                response = requests.post(
                    API + "/chat/completions", json=body, headers=self._headers, timeout=120
                )
            except requests.RequestException:
                self._sleeper(10 * 2**attempt)
                continue
            self._sleeper(random.uniform(*self.delay))
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"] or ""
            if response.status_code in (401, 403):
                raise ClarinError(f"CLARIN-PL HTTP {response.status_code}: token rejected.")
            if response.status_code != 429 and response.status_code < 500:
                raise ClarinError(f"CLARIN-PL HTTP {response.status_code}: {response.text[:200]}")
            self._sleeper(min(10 * 2**attempt, 600))
        raise ClarinError("CLARIN-PL failed repeatedly; try again later.")

    def classify(self, text: str, model: str) -> dict[str, str]:
        """Validated relevance and impact; ValueError when the answer is not valid labels."""
        match = re.search(r"\{.*?\}", self.complete(model, text), re.S)
        if not match:
            raise ValueError("The model returned no JSON object.")
        return validate_labels(json.loads(match.group(0)))
