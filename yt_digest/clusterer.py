# yt_digest/clusterer.py
import json

from claude_code_sdk import ClaudeCodeOptions, query, AssistantMessage, TextBlock
from loguru import logger

from yt_digest.models import VideoSummary, ClusterResult, ClusterGroup

CLUSTER_PROMPT_TEMPLATE = """You are given a list of YouTube video summaries. Group them into 2-4 topic clusters based on their content.

Return ONLY a JSON array, no other text. Each element must have:
- "name": a short descriptive cluster name (e.g., "AI Coding & Agents", "Marketing & Entrepreneurship")
- "video_indices": array of 0-based indices from the list below

Videos:
{videos_text}

Respond with ONLY the JSON array."""


def _parse_cluster_response(response: str, num_videos: int) -> ClusterResult:
    fallback = ClusterResult(
        clusters=[
            ClusterGroup(name="Today's Videos", video_indices=list(range(num_videos)))
        ]
    )
    try:
        # Strip markdown code fences if present
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.rsplit("```", 1)[0]
        data = json.loads(cleaned)
        if not isinstance(data, list) or not data:
            return fallback
        clusters = []
        for item in data:
            if "name" not in item or "video_indices" not in item:
                return fallback
            indices = item["video_indices"]
            if any(i < 0 or i >= num_videos for i in indices):
                return fallback
            clusters.append(ClusterGroup(name=item["name"], video_indices=indices))
        return ClusterResult(clusters=clusters)
    except (json.JSONDecodeError, KeyError, TypeError):
        return fallback


async def cluster_summaries(
    summaries: list[VideoSummary], model: str = "claude-sonnet-4-20250514"
) -> ClusterResult:
    if not summaries:
        return ClusterResult(clusters=[])

    if len(summaries) <= 2:
        return ClusterResult(
            clusters=[
                ClusterGroup(
                    name="Today's Videos", video_indices=list(range(len(summaries)))
                )
            ]
        )

    videos_text = "\n".join(
        f"[{i}] {s.title} ({s.channel_name}): {s.summary[:200]}"
        for i, s in enumerate(summaries)
    )
    prompt = CLUSTER_PROMPT_TEMPLATE.format(videos_text=videos_text)

    options = ClaudeCodeOptions(max_turns=1, model=model)
    result_text = ""
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    result_text += block.text

    return _parse_cluster_response(result_text, len(summaries))
