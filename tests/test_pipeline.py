# tests/test_pipeline.py
import pytest
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch

from yt_digest.config import AppConfig, SlackConfig, ClaudeConfig
from yt_digest.db import Database
from yt_digest.models import ChannelInfo, VideoInfo, VideoSummary, ClusterResult, ClusterGroup


def _setup_channel(db: Database) -> int:
    channel = ChannelInfo(
        name="Fireship",
        youtube_handle="@Fireship",
        channel_id="UCsBjURrPoezykLs9EqgamOA",
    )
    db.insert_channel(channel)
    return db.get_active_channels()[0]["id"]


def _make_config(tmp_path) -> AppConfig:
    return AppConfig(
        db_path=str(tmp_path / "test.db"),
        slack=SlackConfig(webhook_url="https://hooks.example.com/test"),
        claude=ClaudeConfig(model="claude-sonnet-4-20250514"),
    )


@pytest.mark.asyncio
async def test_normal_flow_posts_and_marks_processed(db, tmp_path):
    """Videos get summarized, posted individually, and marked processed."""
    channel_pk = _setup_channel(db)
    config = _make_config(tmp_path)

    video = VideoInfo(
        video_id="vid1",
        channel_pk=channel_pk,
        title="Test Video",
        published_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
    )

    mock_summarizer = AsyncMock()
    mock_summarizer.summarize = AsyncMock(return_value=("A great summary", "notebooklm"))

    with patch("yt_digest.__main__.fetch_new_videos", return_value=[video]), \
         patch("yt_digest.__main__.NotebookLMSummarizer"), \
         patch("yt_digest.__main__.ClaudeCodeSummarizer"), \
         patch("yt_digest.__main__.FallbackSummarizer", return_value=mock_summarizer), \
         patch("yt_digest.__main__.cluster_summaries", new_callable=AsyncMock) as mock_cluster, \
         patch("yt_digest.__main__.post_to_slack", new_callable=AsyncMock) as mock_post:
        mock_cluster.return_value = ClusterResult(
            clusters=[ClusterGroup(name="AI", video_indices=[0])]
        )
        from yt_digest.__main__ import run_pipeline
        await run_pipeline(config, db)

    # Video should be marked processed
    row = db.get_video("vid1")
    assert row["processed_at"] is not None
    assert row["summary"] == "A great summary"
    mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_summarization_failure_increments_fail_count(db, tmp_path):
    """Failed summarization increments fail count, video stays unprocessed."""
    channel_pk = _setup_channel(db)
    config = _make_config(tmp_path)

    video = VideoInfo(
        video_id="fail1",
        channel_pk=channel_pk,
        title="Failing Video",
        published_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
    )

    mock_summarizer = AsyncMock()
    mock_summarizer.summarize = AsyncMock(side_effect=Exception("subtitles disabled"))

    with patch("yt_digest.__main__.fetch_new_videos", return_value=[video]), \
         patch("yt_digest.__main__.NotebookLMSummarizer"), \
         patch("yt_digest.__main__.ClaudeCodeSummarizer"), \
         patch("yt_digest.__main__.FallbackSummarizer", return_value=mock_summarizer), \
         patch("yt_digest.__main__.cluster_summaries", new_callable=AsyncMock) as mock_cluster, \
         patch("yt_digest.__main__.post_to_slack", new_callable=AsyncMock) as mock_post:
        mock_cluster.return_value = ClusterResult(clusters=[])
        from yt_digest.__main__ import run_pipeline
        await run_pipeline(config, db)

    row = db.get_video("fail1")
    assert row["summarization_fail_count"] == 1
    assert row["processed_at"] is None


@pytest.mark.asyncio
async def test_exhausted_video_posted_as_link_only(db, tmp_path):
    """Video with 3 failures gets posted as link-only and marked processed."""
    channel_pk = _setup_channel(db)
    config = _make_config(tmp_path)

    video = VideoInfo(
        video_id="exhaust1",
        channel_pk=channel_pk,
        title="Exhausted Video",
        published_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
    )
    db.insert_video(video)
    for _ in range(3):
        db.increment_fail_count("exhaust1")

    with patch("yt_digest.__main__.fetch_new_videos", return_value=[]), \
         patch("yt_digest.__main__.NotebookLMSummarizer"), \
         patch("yt_digest.__main__.ClaudeCodeSummarizer"), \
         patch("yt_digest.__main__.FallbackSummarizer") as mock_cls, \
         patch("yt_digest.__main__.cluster_summaries", new_callable=AsyncMock) as mock_cluster, \
         patch("yt_digest.__main__.post_to_slack", new_callable=AsyncMock) as mock_post:
        mock_cluster.return_value = ClusterResult(clusters=[])
        from yt_digest.__main__ import run_pipeline
        await run_pipeline(config, db)

    row = db.get_video("exhaust1")
    assert row["processed_at"] is not None
    # post_to_slack should have been called for the exhausted video
    mock_post.assert_called()


@pytest.mark.asyncio
async def test_crash_recovery_picks_up_unsummarized_video(db, tmp_path):
    """Video inserted but not summarized (simulating crash) gets summarized on next run."""
    channel_pk = _setup_channel(db)
    config = _make_config(tmp_path)

    # Simulate a previous crashed run: video in DB with no summary
    video = VideoInfo(
        video_id="orphan1",
        channel_pk=channel_pk,
        title="Orphaned Video",
        published_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
    )
    db.insert_video(video)
    # No summary stored — simulates crash after insert but before summarize

    mock_summarizer = AsyncMock()
    mock_summarizer.summarize = AsyncMock(return_value=("Recovered summary", "claude"))

    # fetch_new_videos returns [] because video already exists in DB
    with patch("yt_digest.__main__.fetch_new_videos", return_value=[]), \
         patch("yt_digest.__main__.NotebookLMSummarizer"), \
         patch("yt_digest.__main__.ClaudeCodeSummarizer"), \
         patch("yt_digest.__main__.FallbackSummarizer", return_value=mock_summarizer), \
         patch("yt_digest.__main__.cluster_summaries", new_callable=AsyncMock) as mock_cluster, \
         patch("yt_digest.__main__.post_to_slack", new_callable=AsyncMock) as mock_post:
        mock_cluster.return_value = ClusterResult(
            clusters=[ClusterGroup(name="Recovered", video_indices=[0])]
        )
        from yt_digest.__main__ import run_pipeline
        await run_pipeline(config, db)

    row = db.get_video("orphan1")
    assert row["summary"] == "Recovered summary"
    assert row["processed_at"] is not None
    mock_summarizer.summarize.assert_called_once()


@pytest.mark.asyncio
async def test_partial_slack_failure_leaves_failed_unprocessed(db, tmp_path):
    """When Slack fails for one video, only the successful ones get marked processed."""
    channel_pk = _setup_channel(db)
    config = _make_config(tmp_path)

    v1 = VideoInfo(
        video_id="ok1",
        channel_pk=channel_pk,
        title="OK Video",
        published_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
    )
    v2 = VideoInfo(
        video_id="slack_fail1",
        channel_pk=channel_pk,
        title="Slack Fail Video",
        published_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
    )

    mock_summarizer = AsyncMock()
    mock_summarizer.summarize = AsyncMock(return_value=("A summary", "notebooklm"))

    call_count = 0

    async def mock_post_side_effect(webhook_url, messages):
        nonlocal call_count
        call_count += 1
        # Fail on the second call
        if call_count == 2:
            raise Exception("Slack webhook timeout")

    with patch("yt_digest.__main__.fetch_new_videos", return_value=[v1, v2]), \
         patch("yt_digest.__main__.NotebookLMSummarizer"), \
         patch("yt_digest.__main__.ClaudeCodeSummarizer"), \
         patch("yt_digest.__main__.FallbackSummarizer", return_value=mock_summarizer), \
         patch("yt_digest.__main__.cluster_summaries", new_callable=AsyncMock) as mock_cluster, \
         patch("yt_digest.__main__.post_to_slack", new_callable=AsyncMock) as mock_post:
        mock_cluster.return_value = ClusterResult(
            clusters=[ClusterGroup(name="Test", video_indices=[0, 1])]
        )
        mock_post.side_effect = mock_post_side_effect
        from yt_digest.__main__ import run_pipeline
        await run_pipeline(config, db)

    # First video should be processed (Slack succeeded)
    row1 = db.get_video("ok1")
    assert row1["processed_at"] is not None

    # Second video should NOT be processed (Slack failed)
    row2 = db.get_video("slack_fail1")
    assert row2["processed_at"] is None
    assert row2["summary"] == "A summary"  # summary is stored, just not posted
