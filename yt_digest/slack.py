# yt_digest/slack.py
from datetime import date

import httpx
from loguru import logger

from yt_digest.models import VideoSummary, ClusterResult

EMOJI_MAP = {
    0: "\U0001f916",  # robot
    1: "\U0001f4c8",  # chart_increasing
    2: "\U0001f680",  # rocket
    3: "\U0001f4a1",  # lightbulb
}


def format_digest(
    summaries: list[VideoSummary],
    clusters: ClusterResult,
    today: date,
) -> str:
    date_str = today.strftime("%B %d, %Y")
    lines = [f"\U0001f4ec *YouTube Digest \u2014 {date_str}*\n"]

    for i, cluster in enumerate(clusters.clusters):
        emoji = EMOJI_MAP.get(i, "\U0001f4cc")
        lines.append(f"{emoji} *{cluster.name}*")
        for idx in cluster.video_indices:
            s = summaries[idx]
            lines.append(f"\u2022 *{s.title}* ({s.channel_name}) \u2014 {s.summary}")
            lines.append(f"  \U0001f517 {s.url}")
        lines.append("")

    return "\n".join(lines).strip()


def format_no_content_message(today: date) -> str:
    date_str = today.strftime("%B %d, %Y")
    return f"\U0001f4ec *YouTube Digest \u2014 {date_str}*\n\nNo new content today."


def split_messages(text: str, max_chars: int = 3000) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    sections = text.split("\n\n")
    messages = []
    current = ""

    for section in sections:
        if current and len(current) + len(section) + 2 > max_chars:
            messages.append(current.strip())
            current = section
        else:
            current = current + "\n\n" + section if current else section

    if current.strip():
        messages.append(current.strip())

    return messages


async def post_to_slack(webhook_url: str, text: str) -> None:
    messages = split_messages(text)
    async with httpx.AsyncClient() as client:
        for msg in messages:
            resp = await client.post(webhook_url, json={"text": msg}, timeout=30)
            resp.raise_for_status()
    logger.info("Posted %d Slack message(s)", len(messages))
