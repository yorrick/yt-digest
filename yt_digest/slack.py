# yt_digest/slack.py
import re
from datetime import date

import httpx
from loguru import logger

from yt_digest.models import VideoSummary


def strip_reference_markers(text: str) -> str:
    """Remove NotebookLM-style reference markers like [1], [2, 3] but not 4-digit years like [2024]."""
    return re.sub(r"\[\d{1,2}(?:,\s*\d{1,2})*\]", "", text)


def format_video_message(video: VideoSummary) -> str:
    lines = [f"\U0001f4ec *{video.title}* ({video.channel_name})"]
    if video.summary == "Summary unavailable":
        lines.append("\u26a0\ufe0f Summary unavailable")
    else:
        lines.append(strip_reference_markers(video.summary))
    lines.append(f"\U0001f517 {video.url}")
    return "\n".join(lines)


def format_no_content_message(today: date) -> str:
    date_str = today.strftime("%B %d, %Y")
    return f"\U0001f4ec *YouTube Digest \u2014 {date_str}*\n\nNo new content today."


async def post_to_slack(webhook_url: str, messages: list[str]) -> None:
    async with httpx.AsyncClient() as client:
        for msg in messages:
            resp = await client.post(webhook_url, json={"text": msg}, timeout=30)
            resp.raise_for_status()
    logger.info("Posted {} Slack message(s)", len(messages))
