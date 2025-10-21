"""Optional DeepSeek integration for language-enhanced commentary."""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

import requests


class DeepSeekClient:
    """Minimal DeepSeek API client with opt-in behaviour."""

    def __init__(self, api_key: Optional[str] = None, *, base_url: str | None = None) -> None:
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.base_url = base_url or "https://api.deepseek.com/v1/chat/completions"
        self.logger = logging.getLogger(__name__)

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def analyze(self, prompt: str, *, model: str = "deepseek-chat") -> str:
        if not self.enabled:
            raise RuntimeError("DeepSeek integration is disabled")
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2}
        try:
            response = requests.post(self.base_url, headers=headers, data=json.dumps(payload), timeout=30)
            response.raise_for_status()
        except requests.RequestException as exc:  # pragma: no cover - network errors
            self.logger.error("DeepSeek request failed: %s", exc)
            raise RuntimeError(f"DeepSeek request failed: {exc}") from exc
        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError("DeepSeek returned no choices")
        return choices[0].get("message", {}).get("content", "")


__all__ = ["DeepSeekClient"]
