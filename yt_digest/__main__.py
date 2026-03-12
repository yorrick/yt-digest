# yt_digest/__main__.py
import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path

from loguru import logger

from yt_digest.config import AppConfig, load_config
from yt_digest.db import Database
from yt_digest.fetcher import fetch_new_videos
from yt_digest.clusterer import cluster_summaries
from yt_digest.models import VideoSummary
from yt_digest.slack import format_video_message, format_no_content_message, post_to_slack
from yt_digest.summarizer import FallbackSummarizer
from yt_digest.summarizer.notebooklm import NotebookLMSummarizer
from yt_digest.summarizer.claude import ClaudeCodeSummarizer


def setup_logging() -> None:
    log_dir = Path("~/.yt-digest").expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "yt-digest.log"

    logger.remove()
    logger.add(sys.stderr, level="INFO")
    logger.add(log_file, level="INFO", rotation="1 day", retention=7)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="yt-digest: Daily YouTube channel monitor"
    )
    parser.add_argument(
        "--init", action="store_true", help="Initialize DB and seed channels"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print digest to stdout instead of posting to Slack",
    )
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    return parser.parse_args()


async def run_pipeline(config: AppConfig, db: Database, dry_run: bool = False) -> None:
    # 1. Fetch new videos
    logger.info("Fetching new videos...")
    new_videos = fetch_new_videos(db)

    # 2. Insert all new videos immediately (before summarization)
    for video in new_videos:
        db.insert_video(video)
    logger.info("Inserted {} new videos", len(new_videos))

    # 3. Summarize all unprocessed videos that need summaries
    primary = NotebookLMSummarizer()
    fallback = ClaudeCodeSummarizer(model=config.claude.model)
    summarizer = FallbackSummarizer(primary, fallback)

    to_summarize = [v for v in db.get_unprocessed_videos() if v["summary"] is None]
    for video_row in to_summarize:
        video_id = video_row["video_id"]
        url = video_row["url"]
        try:
            summary, backend = await summarizer.summarize(url)
            db.store_summary(video_id, summary, backend)
            logger.info("Summarized {} via {}", video_id, backend)
        except Exception as e:
            db.increment_fail_count(video_id)
            logger.warning("Failed to summarize {} (attempt {}): {}", video_id, video_row["summarization_fail_count"] + 1, e)

    # 4. Handle exhausted videos (failed 3+ times) — post as link-only
    exhausted = db.get_exhausted_videos()
    if exhausted:
        logger.info("Posting {} exhausted videos as link-only", len(exhausted))
    for row in exhausted:
        video = VideoSummary(
            video_id=row["video_id"],
            title=row["title"],
            url=row["url"],
            summary="Summary unavailable",
            summarizer="none",
            channel_name=row["channel_name"],
        )
        msg = format_video_message(video)
        if dry_run:
            print(msg)
            print()
        else:
            try:
                await post_to_slack(config.slack.webhook_url, [msg])
                db.mark_processed([row["video_id"]], "uncategorized")
            except Exception as e:
                logger.warning("Failed to post exhausted video {} to Slack: {}", row["video_id"], e)

    # 5. Gather postable videos (unprocessed with summaries)
    postable = [v for v in db.get_unprocessed_videos() if v["summary"] is not None]

    if not postable and not exhausted:
        if dry_run:
            print(format_no_content_message(date.today()))
        else:
            await post_to_slack(config.slack.webhook_url, [format_no_content_message(date.today())])
        logger.info("Pipeline complete")
        return

    if not postable:
        logger.info("Pipeline complete")
        return

    # 6. Cluster for sort order
    summaries = [
        VideoSummary(
            video_id=v["video_id"],
            title=v["title"],
            url=v["url"],
            summary=v["summary"],
            summarizer=v["summarizer"] or "none",
            channel_name=v["channel_name"],
        )
        for v in postable
    ]
    cluster_result = await cluster_summaries(summaries, model=config.claude.model)

    # Build ordered list: (cluster_index, cluster_name, video_index)
    clustered_indices: set[int] = set()
    ordered: list[tuple[int, str, int]] = []
    for ci, cluster in enumerate(cluster_result.clusters):
        for vi in sorted(cluster.video_indices, key=lambda i: postable[i]["video_id"]):
            ordered.append((ci, cluster.name, vi))
            clustered_indices.add(vi)
    # Append any unclustered videos
    for i in range(len(postable)):
        if i not in clustered_indices:
            ordered.append((len(cluster_result.clusters), "Other", i))

    # 7. Post to Slack — one message per video
    for _, cluster_name, vi in ordered:
        video = summaries[vi]
        msg = format_video_message(video)
        if dry_run:
            print(msg)
            print()
        else:
            try:
                await post_to_slack(config.slack.webhook_url, [msg])
                db.mark_processed([video.video_id], cluster_name)
            except Exception as e:
                logger.warning("Failed to post {} to Slack: {}", video.video_id, e)

    logger.info("Pipeline complete")


def main() -> None:
    setup_logging()
    args = parse_args()
    config = load_config(args.config)
    db = Database(config.db_path)

    if args.init:
        from yt_digest.init_channels import init_channels

        db.init()
        init_channels(db)
        logger.info("Database initialized and channels seeded")
        return

    db.init()
    asyncio.run(run_pipeline(config, db, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
