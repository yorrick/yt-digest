# yt_digest/summarizer/__init__.py
import logging
from yt_digest.summarizer.base import Summarizer

logger = logging.getLogger(__name__)


class FallbackSummarizer:
    """Wraps a primary + fallback summarizer. Falls back on any exception.

    Not a Summarizer subclass because it returns (summary, backend_name) tuples.
    """

    def __init__(self, primary: Summarizer, fallback: Summarizer):
        self.primary = primary
        self.fallback = fallback
        self._primary_failed = False

    async def summarize(self, video_url: str) -> tuple[str, str]:
        """Returns (summary, summarizer_name)."""
        if not self._primary_failed:
            try:
                result = await self.primary.summarize(video_url)
                return result, "notebooklm"
            except Exception:
                logger.warning("Primary summarizer failed, falling back to Claude for this run", exc_info=True)
                self._primary_failed = True

        result = await self.fallback.summarize(video_url)
        return result, "claude"
