from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    """Raised when a model call fails."""


@dataclass(slots=True)
class LLMClient:
    base_url: str
    model_name: str
    api_key: str
    timeout_seconds: int = 90
    max_retries: int = 2

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _parse_content(self, content: str) -> str:
        stripped = content.strip()
        if stripped.startswith("```"):
            match = re.search(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL)
            if match:
                return match.group(1)
        return stripped

    def chat_text(self, *, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
        }

        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers=self._headers(),
                json=payload,
            )

        if response.status_code >= 400:
            raise LLMError(f"model call failed: {response.status_code} {response.text}")

        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            raise LLMError("model response missing choices")

        content = choices[0].get("message", {}).get("content", "")
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                text = item.get("text") if isinstance(item, dict) else ""
                if text:
                    parts.append(text)
            return "\n".join(parts)
        if not isinstance(content, str):
            raise LLMError("model content is not a string")
        return content

    def chat_json(self, *, system_prompt: str, user_prompt: str, schema: type[T]) -> T:
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 2):
            payload = {
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            }

            try:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(
                        f"{self.base_url.rstrip('/')}/chat/completions",
                        headers=self._headers(),
                        json=payload,
                    )
                response.raise_for_status()
                data: dict[str, Any] = response.json()
                raw_content = data["choices"][0]["message"]["content"]
                if not isinstance(raw_content, str):
                    raise LLMError("model content is not a string")

                normalized = self._parse_content(raw_content)
                try:
                    return schema.model_validate_json(normalized)
                except ValidationError:
                    parsed = json.loads(normalized)
                    return schema.model_validate(parsed)
            except (
                httpx.HTTPError,
                KeyError,
                IndexError,
                ValidationError,
                json.JSONDecodeError,
                LLMError,
            ) as exc:
                last_error = exc
                logger.warning("LLM JSON attempt %s failed: %s", attempt, exc)
                if attempt >= self.max_retries + 1:
                    break

        raise LLMError(f"unable to parse structured model response: {last_error}")
