# tests/test_clusterer.py
import json
from yt_digest.clusterer import _parse_cluster_response


def test_parse_valid_cluster_response():
    response = json.dumps([
        {"name": "AI Coding", "video_indices": [0, 1]},
        {"name": "Marketing", "video_indices": [2]},
    ])
    result = _parse_cluster_response(response, num_videos=3)
    assert len(result.clusters) == 2
    assert result.clusters[0].name == "AI Coding"


def test_parse_malformed_response_falls_back():
    result = _parse_cluster_response("not valid json", num_videos=3)
    assert len(result.clusters) == 1
    assert result.clusters[0].name == "Today's Videos"
    assert result.clusters[0].video_indices == [0, 1, 2]


def test_parse_response_with_invalid_indices_falls_back():
    response = json.dumps([
        {"name": "AI", "video_indices": [0, 99]},  # 99 is out of range
    ])
    result = _parse_cluster_response(response, num_videos=3)
    assert len(result.clusters) == 1
    assert result.clusters[0].name == "Today's Videos"


def test_single_video_gets_single_cluster():
    result = _parse_cluster_response(
        json.dumps([{"name": "AI", "video_indices": [0]}]),
        num_videos=1,
    )
    assert len(result.clusters) == 1
