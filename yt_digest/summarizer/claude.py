# yt_digest/summarizer/claude.py
from claude_code_sdk import ClaudeCodeOptions, query, AssistantMessage, TextBlock
from youtube_transcript_api import YouTubeTranscriptApi

from yt_digest.summarizer.base import Summarizer

SUMMARY_PROMPT_TEMPLATE = """Summarize the following YouTube video transcript in approximately 10 sentences.
Cover the key points, insights, and takeaways. Be specific about what was said.
Do NOT add any information that is not in the transcript.

TRANSCRIPT:
{transcript}

Respond with ONLY the summary, no preamble or formatting."""


class ClaudeCodeSummarizer(Summarizer):
    backend_name = "claude"

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self.model = model

    async def summarize(self, video_url: str) -> str:
        video_id = video_url.split("v=")[-1]
        api = YouTubeTranscriptApi()
        transcript = api.fetch(video_id)
        transcript_text = " ".join(snippet.text for snippet in transcript)

        prompt = SUMMARY_PROMPT_TEMPLATE.format(transcript=transcript_text[:50000])

        options = ClaudeCodeOptions(
            max_turns=1,
            model=self.model,
        )

        result_text = ""
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        result_text += block.text

        if not result_text.strip():
            raise RuntimeError("Claude Code SDK returned empty response")

        return result_text.strip()
