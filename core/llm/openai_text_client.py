from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI


@dataclass
class TextResponse:
    content: str


class OpenAITextClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        disable_thinking: bool = False,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url or None)
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._disable_thinking = disable_thinking

    async def ainvoke(self, prompt: str) -> TextResponse:
        extra_body: dict[str, Any] = {}
        if self._disable_thinking:
            extra_body["thinking"] = {"type": "disabled"}

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            extra_body=extra_body or None,
        )

        if not response.choices:
            return TextResponse(content="")

        content = response.choices[0].message.content
        if isinstance(content, str):
            return TextResponse(content=content)
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                text = getattr(item, "text", None)
                if isinstance(text, str):
                    chunks.append(text)
                elif isinstance(item, dict) and isinstance(item.get("text"), str):
                    chunks.append(item["text"])
            return TextResponse(content="\n".join(chunks))
        return TextResponse(content="")
