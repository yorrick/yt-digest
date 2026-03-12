# tests/test_db.py
import sqlite3
from datetime import datetime, timezone

import pytest

from yt_digest.db import MAX_SUMMARIZATION_ATTEMPTS
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



def test_max_summarization_attempts_is_three():
    assert MAX_SUMMARIZATION_ATTEMPTS == 3


def test_init_adds_summarization_fail_count_column(db):
    """Column exists after init (already called by fixture)."""
    with db._connect() as conn:
        row = conn.execute(
            "SELECT summarization_fail_count FROM videos LIMIT 0"
        ).fetchone()
    # No error means column exists


def test_init_is_idempotent(db):
    """Calling init twice doesn't crash (migration is safe to re-run)."""
    db.init()  # second call — fixture already called init once


def test_increment_fail_count(db):
    channel = ChannelInfo(
        name="Fireship",
        youtube_handle="@Fireship",
        channel_id="UCsBjURrPoezykLs9EqgamOA",
    )
    db.insert_channel(channel)
    channels = db.get_active_channels()
    channel_pk = channels[0]["id"]

    video = VideoInfo(
        video_id="fail1",
        channel_pk=channel_pk,
        title="Failing Video",
        published_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
    )
    db.insert_video(video)

    row = db.get_video("fail1")
    assert row["summarization_fail_count"] == 0

    db.increment_fail_count("fail1")
    row = db.get_video("fail1")
    assert row["summarization_fail_count"] == 1

    db.increment_fail_count("fail1")
    row = db.get_video("fail1")
    assert row["summarization_fail_count"] == 2


def test_get_unprocessed_videos_excludes_exhausted(db):
    channel = ChannelInfo(
        name="Fireship",
        youtube_handle="@Fireship",
        channel_id="UCsBjURrPoezykLs9EqgamOA",
    )
    db.insert_channel(channel)
    channels = db.get_active_channels()
    channel_pk = channels[0]["id"]

    v1 = VideoInfo(
        video_id="good1",
        channel_pk=channel_pk,
        title="Good Video",
        published_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
    )
    db.insert_video(v1)

    v2 = VideoInfo(
        video_id="bad1",
        channel_pk=channel_pk,
        title="Bad Video",
        published_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
    )
    db.insert_video(v2)
    for _ in range(3):
        db.increment_fail_count("bad1")

    unprocessed = db.get_unprocessed_videos()
    video_ids = [r["video_id"] for r in unprocessed]
    assert "good1" in video_ids
    assert "bad1" not in video_ids


def test_get_exhausted_videos(db):
    channel = ChannelInfo(
        name="Fireship",
        youtube_handle="@Fireship",
        channel_id="UCsBjURrPoezykLs9EqgamOA",
    )
    db.insert_channel(channel)
    channels = db.get_active_channels()
    channel_pk = channels[0]["id"]

    v1 = VideoInfo(
        video_id="exhausted1",
        channel_pk=channel_pk,
        title="Exhausted Video",
        published_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
    )
    db.insert_video(v1)
    for _ in range(3):
        db.increment_fail_count("exhausted1")

    v2 = VideoInfo(
        video_id="normal1",
        channel_pk=channel_pk,
        title="Normal Video",
        published_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
    )
    db.insert_video(v2)

    v3 = VideoInfo(
        video_id="exhausted_done",
        channel_pk=channel_pk,
        title="Already Done",
        published_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
    )
    db.insert_video(v3)
    for _ in range(3):
        db.increment_fail_count("exhausted_done")
    db.mark_processed(["exhausted_done"], "uncategorized")

    exhausted = db.get_exhausted_videos()
    video_ids = [r["video_id"] for r in exhausted]
    assert video_ids == ["exhausted1"]
    assert exhausted[0]["channel_name"] == "Fireship"


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
