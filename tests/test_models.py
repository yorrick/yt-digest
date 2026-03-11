# tests/test_models.py
from datetime import datetime, timezone
from yt_digest.models import ChannelInfo, VideoInfo, VideoSummary, ClusterResult, ClusterGroup


def test_channel_info_rss_url():
    ch = ChannelInfo(
        name="Fireship",
        youtube_handle="@Fireship",
        channel_id="UCsBjURrPoezykLs9EqgamOA",
    )
    assert ch.rss_url == "https://www.youtube.com/feeds/videos.xml?channel_id=UCsBjURrPoezykLs9EqgamOA"


def test_video_info_url():
    v = VideoInfo(
        video_id="abc123",
        channel_pk=1,
        title="Test Video",
        published_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
    )
    assert v.url == "https://www.youtube.com/watch?v=abc123"


def test_video_summary():
    vs = VideoSummary(
        video_id="abc123",
        title="Test Video",
        url="https://www.youtube.com/watch?v=abc123",
        summary="This is a summary.",
        summarizer="notebooklm",
        channel_name="Fireship",
    )
    assert vs.summarizer == "notebooklm"


def test_cluster_result():
    cr = ClusterResult(clusters=[
        ClusterGroup(name="AI Coding", video_indices=[0, 1]),
        ClusterGroup(name="Marketing", video_indices=[2]),
    ])
    assert len(cr.clusters) == 2
    assert cr.clusters[0].video_indices == [0, 1]
