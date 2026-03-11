# tests/test_db.py
import sqlite3
from datetime import datetime, timezone

import pytest

from yt_digest.models import ChannelInfo, VideoInfo


def test_insert_and_get_channels(db):
    channel = ChannelInfo(
        name="Fireship",
        youtube_handle="@Fireship",
        channel_id="UCsBjURrPoezykLs9EqgamOA",
    )
    db.insert_channel(channel)
    channels = db.get_active_channels()
    assert len(channels) == 1
    assert channels[0]["youtube_handle"] == "@Fireship"
    assert channels[0]["channel_id"] == "UCsBjURrPoezykLs9EqgamOA"


def test_insert_duplicate_channel_raises(db):
    channel = ChannelInfo(
        name="Fireship",
        youtube_handle="@Fireship",
        channel_id="UCsBjURrPoezykLs9EqgamOA",
    )
    db.insert_channel(channel)
    with pytest.raises(sqlite3.IntegrityError):
        db.insert_channel(channel)


def test_insert_video_and_check_exists(db):
    channel = ChannelInfo(
        name="Fireship",
        youtube_handle="@Fireship",
        channel_id="UCsBjURrPoezykLs9EqgamOA",
    )
    db.insert_channel(channel)
    channels = db.get_active_channels()
    channel_pk = channels[0]["id"]

    video = VideoInfo(
        video_id="abc123",
        channel_pk=channel_pk,
        title="Test Video",
        published_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
    )
    assert not db.video_exists("abc123")
    db.insert_video(video)
    assert db.video_exists("abc123")


def test_get_unprocessed_videos(db):
    channel = ChannelInfo(
        name="Fireship",
        youtube_handle="@Fireship",
        channel_id="UCsBjURrPoezykLs9EqgamOA",
    )
    db.insert_channel(channel)
    channels = db.get_active_channels()
    channel_pk = channels[0]["id"]

    video = VideoInfo(
        video_id="abc123",
        channel_pk=channel_pk,
        title="Test Video",
        published_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
    )
    db.insert_video(video)

    unprocessed = db.get_unprocessed_videos()
    assert len(unprocessed) == 1
    assert unprocessed[0]["video_id"] == "abc123"


def test_store_summary_and_mark_processed(db):
    channel = ChannelInfo(
        name="Fireship",
        youtube_handle="@Fireship",
        channel_id="UCsBjURrPoezykLs9EqgamOA",
    )
    db.insert_channel(channel)
    channels = db.get_active_channels()
    channel_pk = channels[0]["id"]

    video = VideoInfo(
        video_id="abc123",
        channel_pk=channel_pk,
        title="Test Video",
        published_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
    )
    db.insert_video(video)

    db.store_summary("abc123", "This is a summary.", "notebooklm")
    row = db.get_video("abc123")
    assert row["summary"] == "This is a summary."
    assert row["processed_at"] is None  # not yet marked processed

    db.mark_processed(["abc123"], "AI Coding")
    row = db.get_video("abc123")
    assert row["processed_at"] is not None
    assert row["cluster"] == "AI Coding"
