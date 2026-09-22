import json

import httpx
import pytest

from yt_digest.openrouter import OpenRouterClient


@pytest.mark.asyncio
async def test_completion_uses_deepseek_and_keeps_instructions_separate():
    def handler(request):
        assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-key"
        body = json.loads(request.content)
        assert body["model"] == "deepseek/deepseek-v4.1-flash"
        assert body["messages"] == [
            {"role": "system", "content": "Summarize only the supplied text."},
            {"role": "user", "content": "Full transcript"},
        ]
        assert body["provider"]["allow_fallbacks"] is False
        assert body["provider"]["only"] == ["deepinfra"]
        assert body["max_tokens"] == 2048
        return httpx.Response(200, json={"choices": [
            {"finish_reason": "stop", "message": {"content": " A real summary. "}}
        ]})

    client = OpenRouterClient(api_key="test-key", transport=httpx.MockTransport(handler))
    assert await client.complete("Summarize only the supplied text.", "Full transcript") == "A real summary."


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {"choices": []},
    {"choices": [{"finish_reason": "stop", "message": {"content": " "}}]},
    {"choices": [{"finish_reason": "length", "message": {"content": "Cut off"}}]},
    {"error": {"message": "provider failed"}},
    {"choices": [{"finish_reason": "stop", "message": {"content": None}}]},
])
async def test_invalid_completion_fails_visibly(payload):
    client = OpenRouterClient(api_key="test-key", transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=payload)))
    with pytest.raises(RuntimeError):
        await client.complete("Summarize", "Transcript")


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 402, 429, 503])
async def test_http_errors_are_not_summaries(status):
    client = OpenRouterClient(api_key="test-key", transport=httpx.MockTransport(
        lambda request: httpx.Response(status)))
    with pytest.raises(httpx.HTTPStatusError):
        await client.complete("Summarize", "Transcript")


def test_missing_key_fails_before_network(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        OpenRouterClient()
