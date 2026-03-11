# tests/test_summarizer.py
import pytest
from yt_digest.summarizer import FallbackSummarizer
from yt_digest.summarizer.base import Summarizer


class MockPrimary(Summarizer):
    backend_name = "notebooklm"

    def __init__(self, fail: bool = False):
        self.fail = fail
        self.call_count = 0

    async def summarize(self, video_url: str) -> str:
        self.call_count += 1
        if self.fail:
            raise RuntimeError("Primary failed")
        return f"Primary summary of {video_url}"


class MockFallback(Summarizer):
    backend_name = "claude"

    def __init__(self):
        self.call_count = 0

    async def summarize(self, video_url: str) -> str:
        self.call_count += 1
        return f"Fallback summary of {video_url}"


@pytest.mark.asyncio
async def test_fallback_uses_primary_when_healthy():
    primary = MockPrimary(fail=False)
    fallback = MockFallback()
    summarizer = FallbackSummarizer(primary, fallback)

    summary, backend = await summarizer.summarize("https://youtube.com/watch?v=test")
    assert backend == "notebooklm"
    assert "Primary summary" in summary
    assert primary.call_count == 1
    assert fallback.call_count == 0


@pytest.mark.asyncio
async def test_fallback_switches_on_primary_failure():
    primary = MockPrimary(fail=True)
    fallback = MockFallback()
    summarizer = FallbackSummarizer(primary, fallback)

    summary, backend = await summarizer.summarize("https://youtube.com/watch?v=test1")
    assert backend == "claude"
    assert "Fallback summary" in summary

    # Second call should skip primary entirely
    summary2, backend2 = await summarizer.summarize("https://youtube.com/watch?v=test2")
    assert backend2 == "claude"
    assert primary.call_count == 1  # only tried once
    assert fallback.call_count == 2
