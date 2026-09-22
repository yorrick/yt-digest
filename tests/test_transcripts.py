import json

import httpx
import pytest

from yt_digest.transcripts import ApifyTranscripts


VIDEO_URL = "https://www.youtube.com/watch?v=bA8WeHYmJko"


@pytest.mark.asyncio
async def test_apify_fetches_only_requested_video_captions():
    def handler(request):
        assert request.headers["Authorization"] == "Bearer test-key"
        assert request.url.params["maxTotalChargeUsd"] == "0.05"
        assert request.url.params["timeout"] == "120"
        body = json.loads(request.content)
        assert body["videoUrl"] == VIDEO_URL
        assert body["targetLanguage"] == "en"
        return httpx.Response(200, json=[{
            "data": [
                {"start": "0", "dur": "2", "text": "Complete"},
                {"start": "2", "dur": "2", "text": "spoken transcript"}
            ]
        }])
    client = ApifyTranscripts(api_key="test-key", transport=httpx.MockTransport(handler))
    assert await client.fetch(VIDEO_URL) == "Complete spoken transcript"


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    [], {"error": "actor failed"},
    [{"data": [{"text": "Valid"}, {"text": None}]}],
    [{"data": []}],
    [{"data": [{"text": " "}]}],
    [{"data": "Wrong type"}],
    [{"id": "bA8WeHYmJko", "subtitles": []}],
    [{"id": "bA8WeHYmJko", "subtitles": [{"language": "en", "plaintext": " "}]}],
    [{"id": "bA8WeHYmJko", "description": "Not a transcript"}],
])
async def test_unusable_actor_output_is_recoverable_service_error(payload):
    client = ApifyTranscripts(api_key="test-key", transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=payload)))
    with pytest.raises(RuntimeError):
        await client.fetch(VIDEO_URL)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 429, 503])
async def test_transcript_service_http_errors_propagate(status):
    client = ApifyTranscripts(api_key="test-key", transport=httpx.MockTransport(
        lambda request: httpx.Response(status)))
    with pytest.raises(httpx.HTTPStatusError):
        await client.fetch(VIDEO_URL)
