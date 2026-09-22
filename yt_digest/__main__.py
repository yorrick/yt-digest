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
from yt_digest.openrouter import OpenRouterClient
from yt_digest.transcripts import ApifyTranscripts
from yt_digest.summarizer.openrouter import OpenRouterSummarizer


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
    # Validate credentials before fetching or modifying the database.
    llm = OpenRouterClient(
        model=config.openrouter.model, provider=config.openrouter.provider,
        timeout=config.openrouter.timeout,
    )
    transcripts = ApifyTranscripts(
        timeout=config.apify.timeout, max_charge_usd=config.apify.max_charge_usd
    )
    summarizer = OpenRouterSummarizer(llm, transcripts)
    failures: list[str] = []
    delivery_failures: list[str] = []
    # 1. Fetch new videos
    logger.info("Fetching new videos...")
    new_videos = fetch_new_videos(db)

    # 2. Insert all new videos immediately (before summarization)
    for video in new_videos:
        db.insert_video(video)
    logger.info("Inserted {} new videos", len(new_videos))

    # 3. Summarize all unprocessed videos that need summaries
    to_summarize = [v for v in db.get_unprocessed_videos() if v["summary"] is None]
    for video_row in to_summarize:
        video_id = video_row["video_id"]
        url = video_row["url"]
        try:
            summary = await summarizer.summarize(url)
            db.store_summary(video_id, summary, summarizer.backend_name)
            logger.info("Summarized {} via {}", video_id, summarizer.backend_name)
        except Exception as e:
            failures.append(video_id)
            logger.warning("Failed to summarize {}; leaving pending: {}", video_id, e)

    # 4. Gather postable videos (unprocessed with summaries)
    postable = [v for v in db.get_unprocessed_videos() if v["summary"] is not None]

    if not postable and failures:
        raise RuntimeError(f"Summarization failed; videos remain pending: {', '.join(failures)}")

    if not postable:
        if dry_run:
            print(format_no_content_message(date.today()))
        else:
            await post_to_slack(config.slack.webhook_url, [format_no_content_message(date.today())])
        logger.info("Pipeline complete")
        return

    # 5. Cluster for sort order
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
    cluster_result = await cluster_summaries(summaries, llm=llm)

    # Build ordered list: (cluster_index, cluster_name, video_index)
    clustered_indices: set[int] = set()
    ordered: list[tuple[int, str, int]] = []
    for ci, cluster in enumerate(cluster_result.clusters):
        for vi in sorted(cluster.video_indices, key=lambda i: postable[i]["video_id"]):
            if vi in clustered_indices:
                continue
            ordered.append((ci, cluster.name, vi))
            clustered_indices.add(vi)
    # Append any unclustered videos
    for i in range(len(postable)):
        if i not in clustered_indices:
            ordered.append((len(cluster_result.clusters), "Other", i))

    # 6. Post to Slack, one message per video
    for _, cluster_name, vi in ordered:
        video = summaries[vi]
        msg = format_video_message(video)
        if dry_run:
            print(msg)
            print()
        else:
            try:
                await post_to_slack(config.slack.webhook_url, [msg])
            except Exception as e:
                delivery_failures.append(video.video_id)
                logger.warning("Failed to post {} to Slack: {}", video.video_id, e)
            else:
                # A DB failure after delivery must surface as a DB failure,
                # not be swallowed and incorrectly logged as a Slack failure.
                db.mark_processed([video.video_id], cluster_name)

    if delivery_failures:
        raise RuntimeError(f"Slack delivery failed; videos remain pending: {', '.join(delivery_failures)}")
    if failures:
        raise RuntimeError(f"Summarization failed; videos remain pending: {', '.join(failures)}")
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
