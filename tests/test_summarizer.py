from unittest.mock import AsyncMock

import pytest

from yt_digest.summarizer.openrouter import OpenRouterSummarizer


@pytest.mark.asyncio
async def test_summary_uses_full_transcript():
    text = "A complete transcript. " * 3000
    llm = AsyncMock(model="deepseek/deepseek-v4.1-flash")
    llm.complete.return_value = "Real summary"
    transcripts = AsyncMock()
    transcripts.fetch.return_value = text
    summarizer = OpenRouterSummarizer(llm, transcripts)
    assert await summarizer.summarize("https://youtube.com/watch?v=bA8WeHYmJko") == "Real summary"
    assert llm.complete.call_args.args[1] == text
    assert summarizer.backend_name == "openrouter/deepseek/deepseek-v4.1-flash"


@pytest.mark.asyncio
async def test_transcript_error_never_calls_llm():
    llm, transcripts = AsyncMock(), AsyncMock()
    transcripts.fetch.side_effect = RuntimeError("No captions returned")
    with pytest.raises(RuntimeError):
        await OpenRouterSummarizer(llm, transcripts).summarize("url")
    llm.complete.assert_not_called()


@pytest.mark.asyncio
async def test_oversized_transcript_is_not_silently_truncated():
    llm, transcripts = AsyncMock(), AsyncMock()
    transcripts.fetch.return_value = "x" * 500_001
    with pytest.raises(RuntimeError, match="input limit"):
        await OpenRouterSummarizer(llm, transcripts).summarize("url")
    llm.complete.assert_not_called()
