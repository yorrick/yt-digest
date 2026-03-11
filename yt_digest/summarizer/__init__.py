# yt_digest/summarizer/__init__.py
from loguru import logger
from yt_digest.summarizer.base import AuthError, Summarizer


class FallbackSummarizer:
    """Wraps a primary + fallback summarizer.

    Falls back per-video on content errors (e.g., video has no captions).
    Falls back permanently on auth errors (e.g., expired cookies).
    """

    def __init__(self, primary: Summarizer, fallback: Summarizer):
        self.primary = primary
        self.fallback = fallback
        self._primary_auth_failed = False

    async def summarize(self, video_url: str) -> tuple[str, str]:
        """Returns (summary, summarizer_name)."""
        if not self._primary_auth_failed:
            try:
                result = await self.primary.summarize(video_url)
                return result, self.primary.backend_name
            except AuthError:
                logger.opt(exception=True).warning(
                    "Primary summarizer auth failed, falling back to Claude for entire run"
                )
                self._primary_auth_failed = True
            except Exception:
                logger.opt(exception=True).warning(
                    "Primary summarizer failed for {}, trying fallback",
                    video_url,
                )

        result = await self.fallback.summarize(video_url)
        return result, self.fallback.backend_name
