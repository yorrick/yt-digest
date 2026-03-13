# Fix Duplicate Video Processing & Per-Video Slack Messages

## Problem

Three related issues discovered from production logs (2026-03-11 / 2026-03-12):

1. **Crashed runs re-include all videos in next digest.** `mark_processed` is all-or-nothing at the end of the pipeline. If the run crashes after summarization but before marking, every video gets re-posted next run.
2. **Failed videos retry forever.** Videos where summarization fails (e.g. subtitles disabled) are never inserted into DB, so `video_exists()` returns False and they're retried every run indefinitely.
3. **NotebookLM reference markers** like `[1]`, `[2, 3]` appear in Slack — they're meaningless outside the notebook.
4. **Minor:** `logger.info("Posted %d Slack message(s)", ...)` uses printf-style `%d` but loguru expects `{}`.

## Design

### DB Schema Change

Add column to `videos` table:

```sql
ALTER TABLE videos ADD COLUMN summarization_fail_count INTEGER NOT NULL DEFAULT 0;
```

**Migration strategy:** The `db.init()` method already runs on every startup. Add an `ALTER TABLE ... ADD COLUMN` wrapped in a try/except that ignores "duplicate column" errors. This is safe because SQLite's `ALTER TABLE ADD COLUMN` is a no-op-style check — we just catch the `OperationalError` if the column already exists.

New DB methods:
- `increment_fail_count(video_id: str) -> None` — increments `summarization_fail_count` by 1.
- `get_exhausted_videos() -> list[Row]` — returns unprocessed videos with `summarization_fail_count >= 3` and `processed_at IS NULL`. Joins channels table for `channel_name`.

Modified DB methods:
- `get_unprocessed_videos()` — add `AND summarization_fail_count < 3` filter (so exhausted videos don't enter the summarization loop).

### Pipeline Flow (run_pipeline)

New step order:

1. **Fetch new videos** — unchanged. Returns only videos where `video_exists()` is False.
2. **Insert immediately** — call `db.insert_video(video)` for each new video *before* summarization. Since `fetch_new_videos` already filters via `video_exists()`, these are guaranteed to be new — no duplicate key risk. Concurrent runs are not supported (single cron job, systemd timer with no overlap).
3. **Summarize** — re-query DB via `get_unprocessed_videos()` filtered to `summary IS NULL`. This single query covers both newly-inserted videos from step 2 AND previously-crashed videos from earlier runs. For each:
   - On success: `db.store_summary(video_id, summary, backend)`.
   - On failure: `db.increment_fail_count(video_id)`, log warning, continue.
4. **Handle exhausted videos** — query `get_exhausted_videos()`. Log count if > 0. For each, if not dry_run: post a link-only Slack message, then `db.mark_processed([video_id], "uncategorized")`. If dry_run: print to stdout.
5. **Gather postable videos** — `get_unprocessed_videos()` filtered to `summary IS NOT NULL`.
6. **Cluster** — call `cluster_summaries()` on postable videos (for ordering only). If any video index is missing from the cluster result, append it to a default "Other" cluster.
7. **Post to Slack** — iterate videos ordered by (cluster index, video_id). For each:
   - If dry_run: print formatted message to stdout.
   - Else: post one Slack message.
     - On success: `db.mark_processed([video_id], cluster_name)`.
     - On failure: log warning, continue. Video stays unprocessed for next run.
8. If no videos were posted (steps 4+7 both empty) and not dry_run: post a "no new content today" message.
9. Log "Pipeline complete".

**Removed:** The crash-recovery retry loop (old lines 80-90). No longer needed — step 3 re-queries the DB, which naturally includes previously-inserted-but-unsummarized videos.

### Slack Message Format

Each video is a separate Slack message.

**Successfully summarized:**
```
📬 *Video Title* (Channel Name)
Summary text here (with [N] references stripped)
🔗 https://www.youtube.com/watch?v=xyz
```

**Exhausted (3 failed summarizations):**
```
📬 *Video Title* (Channel Name)
⚠️ Summary unavailable
🔗 https://www.youtube.com/watch?v=xyz
```

**Changes to slack.py:**
- New `format_video_message(video: VideoSummary) -> str` — formats a single video.
- New `strip_reference_markers(text: str) -> str` — removes NotebookLM `[1]`, `[2, 3]` style markers using regex `\[\d+(?:,\s*\d+)*\]`. Avoids false positives on 4-digit years like `[2024]` by only matching 1-2 digit numbers.
- `post_to_slack` signature changes to accept a list of messages (strings), posting each individually.
- `format_digest` and `split_messages` are removed (no longer needed).
- `format_no_content_message` is kept for the "no new content" case.
- Fix `logger.info("Posted %d ...")` → `logger.info("Posted {} ...", ...)`.

### Clustering

Kept for sort ordering only. `cluster_summaries()` is unchanged. The cluster name is stored in DB via `mark_processed` but not displayed in Slack messages.

Sort order: videos are ordered by their cluster index (position of their cluster in `ClusterResult.clusters`), then by `video_id` within each cluster. Any video not assigned to a cluster is appended at the end in a default "Other" cluster.

### mark_processed Change

`mark_processed` currently accepts a list of video_ids. It will now be called per-video (with a single-element list) right after each successful Slack post. No signature change needed.

### Constants

`MAX_SUMMARIZATION_ATTEMPTS = 3` defined in `db.py` and used in queries. Single source of truth.

## Files Modified

- `yt_digest/db.py` — schema migration, new methods, modified query, constant
- `yt_digest/__main__.py` — new pipeline flow
- `yt_digest/slack.py` — per-video formatting, strip references, fix logger
- `yt_digest/models.py` — no changes needed
- `tests/test_db.py` — tests for new DB methods and fail count behavior
- `tests/test_slack.py` — tests for new format functions, reference stripping
- `tests/test_pipeline.py` — new file, key scenarios:
  - Video inserted then summarization fails → fail count incremented, retried next run
  - Video fails 3 times → posted as link-only, marked processed
  - Crash after insert but before summarize → picked up on next run
  - Partial Slack failure → only successful posts marked processed
  - Normal flow → all videos posted individually and marked processed
