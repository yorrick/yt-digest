# tests/test_fetcher.py
from datetime import datetime, timezone
from unittest.mock import patch
from yt_digest.fetcher import fetch_new_videos, parse_feed_entries
from yt_digest.models import ChannelInfo, VideoInfo

# Sample RSS XML from a YouTube channel feed
SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns="http://www.w3.org/2005/Atom">
  <title>Fireship</title>
  <entry>
    <yt:videoId>abc123</yt:videoId>
    <title>New AI Video</title>
    <published>2026-03-11T10:00:00+00:00</published>
  </entry>
  <entry>
    <yt:videoId>def456</yt:videoId>
    <title>Old Video</title>
    <published>2026-03-01T10:00:00+00:00</published>
  </entry>
</feed>"""


def test_parse_feed_entries():
    entries = parse_feed_entries(SAMPLE_RSS, channel_pk=1)
    assert len(entries) == 2
    assert entries[0].video_id == "abc123"
    assert entries[0].title == "New AI Video"
    assert entries[0].channel_pk == 1


def test_parse_feed_filters_by_date():
    cutoff = datetime(2026, 3, 10, tzinfo=timezone.utc)
    entries = parse_feed_entries(SAMPLE_RSS, channel_pk=1, since=cutoff)
    assert len(entries) == 1
    assert entries[0].video_id == "abc123"


def test_fetch_new_videos_skips_existing(db):
    channel = ChannelInfo(
        name="Fireship",
        youtube_handle="@Fireship",
        channel_id="UCsBjURrPoezykLs9EqgamOA",
    )
    db.insert_channel(channel)
    channels = db.get_active_channels()
    channel_pk = channels[0]["id"]

    # Pre-insert a video so it's "already seen"
    existing = VideoInfo(
        video_id="abc123",
        channel_pk=channel_pk,
        title="Existing",
        published_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
    )
    db.insert_video(existing)

    with patch("yt_digest.fetcher._fetch_feed_xml", return_value=SAMPLE_RSS):
        new_videos = fetch_new_videos(db)

    # abc123 already exists, def456 is too old (>48h if cutoff is ~now)
    # Only truly new videos within 48h window should appear
    existing_ids = {v.video_id for v in new_videos}
    assert "abc123" not in existing_ids
