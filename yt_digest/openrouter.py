import os

import httpx


class OpenRouterClient:
    def __init__(
        self,
        model: str = "deepseek/deepseek-v4.1-flash",
        api_key: str | None = None,
        timeout: float = 90,
        provider: str = "deepinfra",
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.model = model
        self.provider = provider
        self.api_key = api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY")
        if not self.api_key or not self.api_key.strip():
            raise ValueError("OPENROUTER_API_KEY is not set")
        self.timeout = timeout
        self.transport = transport

    async def complete(self, instructions: str, content: str) -> str:
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": instructions},
                        {"role": "user", "content": content},
                    ],
                    "max_tokens": 2048,
                    "reasoning": {"enabled": False},
                    "provider": {"only": [self.provider], "allow_fallbacks": False},
                },
            )
            response.raise_for_status()
        try:
            payload = response.json()
            choice = payload["choices"][0]
            text = choice["message"]["content"]
            if payload.get("error") or choice["finish_reason"] != "stop":
                raise ValueError("Incomplete completion")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("Empty completion")
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("OpenRouter returned an invalid or incomplete completion") from exc
        return text.strip()
