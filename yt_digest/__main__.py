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
from yt_digest.slack import format_digest, format_no_content_message, post_to_slack
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

    # Check for unprocessed videos with existing summaries (crash recovery)
    unprocessed = db.get_unprocessed_videos()
    videos_needing_summary = [v for v in unprocessed if v["summary"] is None]
    videos_with_summary = [v for v in unprocessed if v["summary"] is not None]

    logger.info(
        "{} new videos, {} need summaries, {} have summaries from previous run",
        len(new_videos),
        len(videos_needing_summary),
        len(videos_with_summary),
    )

    # 2. Summarize videos that need it
    primary = NotebookLMSummarizer()
    fallback = ClaudeCodeSummarizer(model=config.claude.model)
    summarizer = FallbackSummarizer(primary, fallback)

    for video_row in videos_needing_summary:
        url = video_row["url"]
        video_id = video_row["video_id"]
        try:
            summary, backend = await summarizer.summarize(url)
            db.store_summary(video_id, summary, backend)
            logger.info("Summarized {} via {}", video_id, backend)
        except Exception:
            logger.exception("Failed to summarize {}", video_id)
            db.store_summary(video_id, "Summary unavailable", "none")

    # 3. Build summaries list from all unprocessed videos
    all_unprocessed = db.get_unprocessed_videos()
    cluster_result = None
    if not all_unprocessed:
        digest_text = format_no_content_message(date.today())
    else:
        summaries = [
            VideoSummary(
                video_id=v["video_id"],
                title=v["title"],
                url=v["url"],
                summary=v["summary"],
                summarizer=v["summarizer"] or "none",
                channel_name=v["channel_name"],
            )
            for v in all_unprocessed
        ]

        # 4. Cluster
        cluster_result = await cluster_summaries(summaries, model=config.claude.model)
        digest_text = format_digest(summaries, cluster_result, date.today())

    # 5. Post or print
    if dry_run:
        print(digest_text)
    else:
        await post_to_slack(config.slack.webhook_url, digest_text)

    # 6. Mark all as processed
    if not dry_run and all_unprocessed and cluster_result:
        for cluster in cluster_result.clusters:
            video_ids = [all_unprocessed[i]["video_id"] for i in cluster.video_indices]
            db.mark_processed(video_ids, cluster.name)

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
