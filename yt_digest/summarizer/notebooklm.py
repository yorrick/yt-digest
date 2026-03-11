# yt_digest/summarizer/notebooklm.py
from loguru import logger
from notebooklm import NotebookLMClient
from notebooklm.exceptions import AuthError as NotebookLMAuthError
from yt_digest.summarizer.base import AuthError, Summarizer

SUMMARY_PROMPT = (
    "Summarize this video in approximately 10 sentences. "
    "Cover the key points, insights, and takeaways. "
    "Be specific and cite what the speaker actually said."
)


class NotebookLMSummarizer(Summarizer):
    backend_name = "notebooklm"

    async def summarize(self, video_url: str) -> str:
        try:
            client_cm = await NotebookLMClient.from_storage()
        except (NotebookLMAuthError, FileNotFoundError) as e:
            raise AuthError(f"NotebookLM auth failed: {e}") from e
        except Exception as e:
            if "auth" in str(e).lower():
                raise AuthError(f"NotebookLM auth failed: {e}") from e
            raise

        async with client_cm as client:
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
