# yt_digest/fetcher.py
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree as ET

import httpx
from loguru import logger

from yt_digest.db import Database
from yt_digest.models import VideoInfo

ATOM_NS = "http://www.w3.org/2005/Atom"
YT_NS = "http://www.youtube.com/xml/schemas/2015"


def _fetch_feed_xml(rss_url: str) -> str:
    resp = httpx.get(rss_url, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    return resp.text


def parse_feed_entries(
    xml_text: str, channel_pk: int, since: datetime | None = None
) -> list[VideoInfo]:
    root = ET.fromstring(xml_text)
    entries = []
    for entry in root.findall(f"{{{ATOM_NS}}}entry"):
        video_id = entry.find(f"{{{YT_NS}}}videoId")
        title = entry.find(f"{{{ATOM_NS}}}title")
        published = entry.find(f"{{{ATOM_NS}}}published")
        if video_id is None or title is None or published is None:
            continue
        pub_dt = datetime.fromisoformat(published.text)
        if since and pub_dt < since:
            continue
        entries.append(
            VideoInfo(
                video_id=video_id.text,
                channel_pk=channel_pk,
                title=title.text,
                published_at=pub_dt,
            )
        )
    return entries


def fetch_new_videos(db: Database) -> list[VideoInfo]:
    channels = db.get_active_channels()
    since = datetime.now(timezone.utc) - timedelta(hours=48)
    new_videos = []

    for ch in channels:
        try:
            xml = _fetch_feed_xml(ch["rss_url"])
            entries = parse_feed_entries(xml, channel_pk=ch["id"], since=since)
            for video in entries:
                if not db.video_exists(video.video_id):
                    new_videos.append(video)
        except Exception as e:
            logger.warning("Failed to fetch RSS for channel {}: {}", ch["youtube_handle"], e)
            continue

    logger.info(
        "Found {} new videos across {} channels", len(new_videos), len(channels)
    )
    return new_videos
