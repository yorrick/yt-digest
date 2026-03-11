# yt_digest/summarizer/base.py
from abc import ABC, abstractmethod


class Summarizer(ABC):
    @abstractmethod
    async def summarize(self, video_url: str) -> str:
        """Return ~10 sentence summary of the video."""
