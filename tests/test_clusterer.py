# tests/test_clusterer.py
import json
from yt_digest.clusterer import _parse_cluster_response


def test_parse_valid_cluster_response():
    response = json.dumps(
        [
            {"name": "AI Coding", "video_indices": [0, 1]},
            {"name": "Marketing", "video_indices": [2]},
        ]
    )
    result = _parse_cluster_response(response, num_videos=3)
    assert len(result.clusters) == 2
    assert result.clusters[0].name == "AI Coding"


def test_parse_malformed_response_falls_back():
    result = _parse_cluster_response("not valid json", num_videos=3)
    assert len(result.clusters) == 1
    assert result.clusters[0].name == "Today's Videos"
    assert result.clusters[0].video_indices == [0, 1, 2]


def test_parse_response_with_invalid_indices_falls_back():
    response = json.dumps(
        [
            {"name": "AI", "video_indices": [0, 99]},  # 99 is out of range
        ]
    )
    result = _parse_cluster_response(response, num_videos=3)
    assert len(result.clusters) == 1
    assert result.clusters[0].name == "Today's Videos"


def test_single_video_gets_single_cluster():
    result = _parse_cluster_response(
        json.dumps([{"name": "AI", "video_indices": [0]}]),
        num_videos=1,
    )
    assert len(result.clusters) == 1


def test_clusterer_uses_openrouter_for_three_videos():
    import asyncio
    from unittest.mock import AsyncMock
    from yt_digest.clusterer import cluster_summaries
    from yt_digest.models import VideoSummary

    llm = AsyncMock()
    llm.complete.return_value = '[{"name":"AI","video_indices":[0,1,2]}]'
    summaries = [VideoSummary(video_id=str(i), title=f"Video {i}", url="https://youtube.com",
                              summary="Content", summarizer="openrouter", channel_name="Claude")
                 for i in range(3)]
    result = asyncio.run(cluster_summaries(summaries, llm=llm))
    llm.complete.assert_called_once()
    assert result.clusters[0].video_indices == [0, 1, 2]


def test_cluster_parser_rejects_boolean_and_fractional_indices():
    for indices in [[True], [1.5], 0, {"0": 1}]:
        result = _parse_cluster_response(json.dumps([{"name": "AI", "video_indices": indices}]), 3)
        assert result.clusters[0].video_indices == [0, 1, 2]


def test_cluster_parser_rejects_invalid_names():
    for name in [42, {}, None, ""]:
        result = _parse_cluster_response(json.dumps([{"name": name, "video_indices": [0]}]), 3)
        assert result.clusters[0].video_indices == [0, 1, 2]
