# tests/test_slack.py
import pytest
import httpx
from datetime import date
from yt_digest.models import VideoSummary
from yt_digest.slack import format_no_content_message, strip_reference_markers, format_video_message


def test_format_no_content_message():
    msg = format_no_content_message(date(2026, 3, 11))
    assert "No new content today" in msg
    assert "March 11, 2026" in msg


def test_strip_single_reference():
    assert strip_reference_markers("some text [1] more") == "some text  more"


def test_strip_multi_reference():
    assert strip_reference_markers("text [2, 3] end") == "text  end"


def test_strip_many_references():
    assert strip_reference_markers("a [1] b [7, 8, 9] c [12] d") == "a  b  c  d"


def test_strip_preserves_four_digit_years():
    assert strip_reference_markers("in [2024] the year") == "in [2024] the year"


def test_strip_no_markers():
    assert strip_reference_markers("plain text") == "plain text"


def test_format_video_message_with_summary():
    video = VideoSummary(
        video_id="vid1",
        title="Cool AI Video",
        url="https://www.youtube.com/watch?v=vid1",
        summary="This video covers AI agents [1] and tools [2, 3].",
        summarizer="notebooklm",
        channel_name="Fireship",
    )
    result = format_video_message(video)
    assert "*Cool AI Video*" in result
    assert "(Fireship)" in result
    assert "This video covers AI agents  and tools ." in result
    assert "[1]" not in result
    assert "https://www.youtube.com/watch?v=vid1" in result


def test_format_video_message_unavailable():
    video = VideoSummary(
        video_id="vid2",
        title="Broken Video",
        url="https://www.youtube.com/watch?v=vid2",
        summary="Summary unavailable",
        summarizer="none",
        channel_name="Test",
    )
    result = format_video_message(video)
    assert "*Broken Video*" in result
    assert "\u26a0\ufe0f Summary unavailable" in result
    assert "https://www.youtube.com/watch?v=vid2" in result


@pytest.mark.asyncio
async def test_post_to_slack_sends_each_message(monkeypatch):
    sent = []

    async def mock_post(self, url, *, json, timeout):
        sent.append(json["text"])
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    from yt_digest.slack import post_to_slack

    await post_to_slack("https://hooks.example.com/test", ["msg1", "msg2", "msg3"])
    assert sent == ["msg1", "msg2", "msg3"]
