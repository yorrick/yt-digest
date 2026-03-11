# yt_digest/init_channels.py
import logging
import re

import httpx

from yt_digest.db import Database
from yt_digest.models import ChannelInfo

logger = logging.getLogger(__name__)

INITIAL_CHANNELS = [
    ("Simon Hoiberg", "@SimonHoiberg"),
    ("Stripe Developers", "@StripeDev"),
    ("IndyDevDan", "@indydevdan"),
    ("Y Combinator", "@ycombinator"),
    ("Cole Medin", "@ColeMedin"),
    ("Hamel Husain", "@hamelhusain7140"),
    ("Greg Isenberg", "@GregIsenberg"),
    ("Fireship", "@Fireship"),
    ("Matthew Berman", "@matthew_berman"),
    ("AI Code King", "@AICodeKing"),
    ("Claude", "@claude"),
    ("EO Global", "@eoglobal"),
    ("Nate B Jones", "@NateBJones"),
]


def resolve_channel_id(handle: str) -> str:
    """Resolve a YouTube handle (e.g., @Fireship) to a channel ID (UCxxx)."""
    url = f"https://www.youtube.com/{handle}"
    resp = httpx.get(url, follow_redirects=True, timeout=30)
    resp.raise_for_status()

    # Look for channel ID in page source
    match = re.search(r'"externalId":"(UC[a-zA-Z0-9_-]+)"', resp.text)
    if match:
        return match.group(1)

    # Fallback: look in meta tags
    match = re.search(
        r'<meta itemprop="channelId" content="(UC[a-zA-Z0-9_-]+)"', resp.text
    )
    if match:
        return match.group(1)

    raise ValueError(f"Could not resolve channel ID for {handle}")


def init_channels(db: Database) -> None:
    for name, handle in INITIAL_CHANNELS:
        try:
            # Check if already exists
            channels = db.get_active_channels()
            existing_handles = {ch["youtube_handle"] for ch in channels}
            if handle in existing_handles:
                logger.info("Channel %s already exists, skipping", handle)
                continue

            logger.info("Resolving channel ID for %s...", handle)
            channel_id = resolve_channel_id(handle)
            channel = ChannelInfo(
                name=name, youtube_handle=handle, channel_id=channel_id
            )
            db.insert_channel(channel)
            logger.info("Added channel %s (ID: %s)", name, channel_id)
        except Exception:
            logger.exception("Failed to add channel %s", handle)
