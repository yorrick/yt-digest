# yt_digest/summarizer/base.py
from abc import ABC, abstractmethod


class Summarizer(ABC):
    backend_name: str

    @abstractmethod
    async def summarize(self, video_url: str) -> str:
        """Return ~10 sentence summary of the video."""
