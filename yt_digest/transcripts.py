import os
import re
from urllib.parse import parse_qs, urlsplit

import httpx


class ApifyTranscripts:
    """Download captions through an explicitly selected hosted scraper."""

    def __init__(
        self,
        api_key: str | None = None,
        timeout: int = 120,
        max_charge_usd: float = 0.05,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.api_key = api_key if api_key is not None else os.environ.get("APIFY_API_KEY")
        if not self.api_key or not self.api_key.strip():
            raise ValueError("APIFY_API_KEY is not set")
        self.timeout = timeout
        self.max_charge_usd = max_charge_usd
        self.transport = transport

    async def fetch(self, video_url: str) -> str:
        # VideoInfo constructs canonical watch URLs from RSS video IDs.
        url = urlsplit(video_url)
        video_id = parse_qs(url.query).get("v", [""])[0]
        if url.hostname not in {"youtube.com", "www.youtube.com"} or not re.fullmatch(r"[\w-]{11}", video_id):
            raise ValueError("Expected a YouTube watch URL with an 11-character video ID")
        async with httpx.AsyncClient(timeout=self.timeout + 30, transport=self.transport) as client:
            response = await client.post(
                "https://api.apify.com/v2/acts/pintostudio~youtube-transcript-scraper/run-sync-get-dataset-items",
                headers={"Authorization": f"Bearer {self.api_key}"},
                params={"timeout": self.timeout, "maxTotalChargeUsd": self.max_charge_usd},
                json={
                    "videoUrl": video_url,
                    "targetLanguage": "en",
                },
            )
            response.raise_for_status()
        try:
            items = response.json()
            if not isinstance(items, list) or len(items) != 1:
                raise ValueError("Expected exactly one video transcript")
            # This actor returns one segment list for the single requested URL,
            # without a video-id field. The synchronous run binds that response
            # to our request; no shared/latest dataset is used.
            segments = items[0]["data"]
            if not isinstance(segments, list):
                raise ValueError("Expected transcript segments")
            if any(not isinstance(s, dict) or not isinstance(s.get("text"), str) for s in segments):
                raise ValueError("Invalid transcript segment")
            text = " ".join(s["text"].strip() for s in segments).strip()
            if text:
                return text
        except (ValueError, KeyError, TypeError) as exc:
            raise RuntimeError("Apify returned invalid caption data") from exc
        # Empty captions can also mean an upstream block. Never consume a
        # video's retry allowance or substitute its description for captions.
        raise RuntimeError("Apify returned no usable English captions")
