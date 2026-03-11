# yt_digest/summarizer/base.py
from abc import ABC, abstractmethod


class AuthError(Exception):
    """Raised when the primary summarizer has an authentication failure."""


class Summarizer(ABC):
    backend_name: str

    @abstractmethod
    async def summarize(self, video_url: str) -> str:
        """Return ~10 sentence summary of the video."""
