# tests/test_slack.py
from datetime import date
from yt_digest.models import VideoSummary, ClusterResult, ClusterGroup
from yt_digest.slack import format_digest, format_no_content_message, split_messages


def _make_summary(
    idx: int, title: str = "Video", channel: str = "Channel"
) -> VideoSummary:
    return VideoSummary(
        video_id=f"vid{idx}",
        title=f"{title} {idx}",
        url=f"https://www.youtube.com/watch?v=vid{idx}",
        summary=f"Summary of video {idx}. " * 5,
        summarizer="notebooklm",
        channel_name=channel,
    )


def test_format_digest_with_clusters():
    summaries = [
        _make_summary(0, "AI Video", "Fireship"),
        _make_summary(1, "Marketing Video", "Greg"),
    ]
    clusters = ClusterResult(
        clusters=[
            ClusterGroup(name="AI Coding", video_indices=[0]),
            ClusterGroup(name="Marketing", video_indices=[1]),
        ]
    )
    result = format_digest(summaries, clusters, date(2026, 3, 11))
    assert "YouTube Digest" in result
    assert "AI Coding" in result
    assert "Marketing" in result
    assert "https://www.youtube.com/watch?v=vid0" in result


def test_format_no_content_message():
    msg = format_no_content_message(date(2026, 3, 11))
    assert "No new content today" in msg
    assert "March 11, 2026" in msg


def test_format_digest_includes_summary_unavailable():
    summaries = [
        VideoSummary(
            video_id="vid0",
            title="Broken Video",
            url="https://www.youtube.com/watch?v=vid0",
            summary="Summary unavailable",
            summarizer="none",
            channel_name="Test",
        )
    ]
    clusters = ClusterResult(
        clusters=[
            ClusterGroup(name="Today's Videos", video_indices=[0]),
        ]
    )
    result = format_digest(summaries, clusters, date(2026, 3, 11))
    assert "Summary unavailable" in result


def test_split_messages_under_limit():
    short_msg = "Short message"
    assert split_messages(short_msg) == [short_msg]


def test_split_messages_over_limit():
    # Create a message with multiple cluster sections
    sections = "\n\n".join(f"*Section {i}*\n" + "x" * 500 for i in range(10))
    header = "Header\n\n"
    full = header + sections
    parts = split_messages(full, max_chars=3000)
    assert len(parts) > 1
    for part in parts:
        assert len(part) <= 3000
