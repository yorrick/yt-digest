# yt_digest/summarizer/notebooklm.py
from loguru import logger
from notebooklm import NotebookLMClient
from yt_digest.summarizer.base import Summarizer

SUMMARY_PROMPT = (
    "Summarize this video in approximately 10 sentences. "
    "Cover the key points, insights, and takeaways. "
    "Be specific and cite what the speaker actually said."
)


class NotebookLMSummarizer(Summarizer):
    backend_name = "notebooklm"

    async def summarize(self, video_url: str) -> str:
        async with await NotebookLMClient.from_storage() as client:
            nb = await client.notebooks.create("yt-digest-temp")
            try:
                await client.sources.add_url(nb.id, video_url, wait=True)
                result = await client.chat.ask(nb.id, SUMMARY_PROMPT)
                return result.answer
            finally:
                try:
                    await client.notebooks.delete(nb.id)
                except Exception:
                    logger.warning("Failed to clean up notebook {}", nb.id)
