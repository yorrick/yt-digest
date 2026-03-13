# Fix Duplicate Video Processing & Per-Video Slack Messages — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix duplicate video processing across pipeline runs by tracking summarization failures, posting one Slack message per video, and marking each video processed immediately after its Slack post succeeds.

**Architecture:** Add `summarization_fail_count` column to DB, move video insertion before summarization, replace batch digest with per-video Slack messages posted and marked processed individually. Clustering kept for sort order only.

**Tech Stack:** Python, SQLite, pytest, loguru, httpx, pydantic

**Spec:** `docs/superpowers/specs/2026-03-12-fix-duplicate-processing-design.md`

---

## Chunk 1: DB Layer Changes

### Task 1: Add `summarization_fail_count` column and migration

**Files:**
- Modify: `yt_digest/db.py:1-10` (add constant), `yt_digest/db.py:20-43` (migration in init)
- Test: `tests/test_db.py`

- [ ] **Step 1: Write tests for migration and new constant**

Add to `tests/test_db.py`:

```python
from yt_digest.db import MAX_SUMMARIZATION_ATTEMPTS


def test_max_summarization_attempts_is_three():
    assert MAX_SUMMARIZATION_ATTEMPTS == 3


def test_init_adds_summarization_fail_count_column(db):
    """Column exists after init (already called by fixture)."""
    with db._connect() as conn:
        row = conn.execute(
            "SELECT summarization_fail_count FROM videos LIMIT 0"
        ).fetchone()
    # No error means column exists


def test_init_is_idempotent(db):
    """Calling init twice doesn't crash (migration is safe to re-run)."""
    db.init()  # second call — fixture already called init once
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/yorrickjansen/work/yt-digest && uv run pytest tests/test_db.py::test_max_summarization_attempts_is_three tests/test_db.py::test_init_adds_summarization_fail_count_column tests/test_db.py::test_init_is_idempotent -v`
Expected: FAIL — `MAX_SUMMARIZATION_ATTEMPTS` not found, column doesn't exist.

- [ ] **Step 3: Implement migration**

In `yt_digest/db.py`, add constant at top (after imports):

```python
MAX_SUMMARIZATION_ATTEMPTS = 3
```

In `db.init()`, after the `CREATE TABLE IF NOT EXISTS` block, add:

```python
            # Migration: add summarization_fail_count if missing
            try:
                conn.execute(
                    "ALTER TABLE videos ADD COLUMN summarization_fail_count INTEGER NOT NULL DEFAULT 0"
                )
            except sqlite3.OperationalError:
                pass  # column already exists
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/yorrickjansen/work/yt-digest && uv run pytest tests/test_db.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add yt_digest/db.py tests/test_db.py
git commit -m "feat(db): add summarization_fail_count column with migration"
```

---

### Task 2: Add `increment_fail_count` DB method

**Files:**
- Modify: `yt_digest/db.py` (new method after `store_summary`)
- Test: `tests/test_db.py`

- [ ] **Step 1: Write test**

Add to `tests/test_db.py`:

```python
def test_increment_fail_count(db):
    channel = ChannelInfo(
        name="Fireship",
        youtube_handle="@Fireship",
        channel_id="UCsBjURrPoezykLs9EqgamOA",
    )
    db.insert_channel(channel)
    channels = db.get_active_channels()
    channel_pk = channels[0]["id"]

    video = VideoInfo(
        video_id="fail1",
        channel_pk=channel_pk,
        title="Failing Video",
        published_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
    )
    db.insert_video(video)

    row = db.get_video("fail1")
    assert row["summarization_fail_count"] == 0

    db.increment_fail_count("fail1")
    row = db.get_video("fail1")
    assert row["summarization_fail_count"] == 1

    db.increment_fail_count("fail1")
    row = db.get_video("fail1")
    assert row["summarization_fail_count"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/yorrickjansen/work/yt-digest && uv run pytest tests/test_db.py::test_increment_fail_count -v`
Expected: FAIL — `AttributeError: 'Database' object has no attribute 'increment_fail_count'`

- [ ] **Step 3: Implement**

Add to `yt_digest/db.py` `Database` class:

```python
    def increment_fail_count(self, video_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE videos SET summarization_fail_count = summarization_fail_count + 1 WHERE video_id = ?",
                (video_id,),
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/yorrickjansen/work/yt-digest && uv run pytest tests/test_db.py::test_increment_fail_count -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add yt_digest/db.py tests/test_db.py
git commit -m "feat(db): add increment_fail_count method"
```

---

### Task 3: Filter `get_unprocessed_videos` by fail count

**Files:**
- Modify: `yt_digest/db.py:88-94` (modify query)
- Test: `tests/test_db.py`

- [ ] **Step 1: Write test**

Add to `tests/test_db.py`:

```python
def test_get_unprocessed_videos_excludes_exhausted(db):
    channel = ChannelInfo(
        name="Fireship",
        youtube_handle="@Fireship",
        channel_id="UCsBjURrPoezykLs9EqgamOA",
    )
    db.insert_channel(channel)
    channels = db.get_active_channels()
    channel_pk = channels[0]["id"]

    # Video with 0 failures — should appear
    v1 = VideoInfo(
        video_id="good1",
        channel_pk=channel_pk,
        title="Good Video",
        published_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
    )
    db.insert_video(v1)

    # Video with 3 failures — should NOT appear
    v2 = VideoInfo(
        video_id="bad1",
        channel_pk=channel_pk,
        title="Bad Video",
        published_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
    )
    db.insert_video(v2)
    for _ in range(3):
        db.increment_fail_count("bad1")

    unprocessed = db.get_unprocessed_videos()
    video_ids = [r["video_id"] for r in unprocessed]
    assert "good1" in video_ids
    assert "bad1" not in video_ids
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/yorrickjansen/work/yt-digest && uv run pytest tests/test_db.py::test_get_unprocessed_videos_excludes_exhausted -v`
Expected: FAIL — `"bad1"` still in results

- [ ] **Step 3: Modify query**

In `yt_digest/db.py`, change `get_unprocessed_videos`:

```python
    def get_unprocessed_videos(self) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                """SELECT v.*, c.name as channel_name
                   FROM videos v JOIN channels c ON v.channel_pk = c.id
                   WHERE v.processed_at IS NULL
                   AND v.summarization_fail_count < ?""",
                (MAX_SUMMARIZATION_ATTEMPTS,),
            ).fetchall()
```

- [ ] **Step 4: Run all DB tests**

Run: `cd /Users/yorrickjansen/work/yt-digest && uv run pytest tests/test_db.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add yt_digest/db.py tests/test_db.py
git commit -m "feat(db): exclude exhausted videos from get_unprocessed_videos"
```

---

### Task 4: Add `get_exhausted_videos` DB method

**Files:**
- Modify: `yt_digest/db.py` (new method)
- Test: `tests/test_db.py`

- [ ] **Step 1: Write test**

Add to `tests/test_db.py`:

```python
def test_get_exhausted_videos(db):
    channel = ChannelInfo(
        name="Fireship",
        youtube_handle="@Fireship",
        channel_id="UCsBjURrPoezykLs9EqgamOA",
    )
    db.insert_channel(channel)
    channels = db.get_active_channels()
    channel_pk = channels[0]["id"]

    # Exhausted video (3 failures, not processed)
    v1 = VideoInfo(
        video_id="exhausted1",
        channel_pk=channel_pk,
        title="Exhausted Video",
        published_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
    )
    db.insert_video(v1)
    for _ in range(3):
        db.increment_fail_count("exhausted1")

    # Normal video (0 failures) — should NOT appear
    v2 = VideoInfo(
        video_id="normal1",
        channel_pk=channel_pk,
        title="Normal Video",
        published_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
    )
    db.insert_video(v2)

    # Already processed exhausted video — should NOT appear
    v3 = VideoInfo(
        video_id="exhausted_done",
        channel_pk=channel_pk,
        title="Already Done",
        published_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
    )
    db.insert_video(v3)
    for _ in range(3):
        db.increment_fail_count("exhausted_done")
    db.mark_processed(["exhausted_done"], "uncategorized")

    exhausted = db.get_exhausted_videos()
    video_ids = [r["video_id"] for r in exhausted]
    assert video_ids == ["exhausted1"]
    assert exhausted[0]["channel_name"] == "Fireship"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/yorrickjansen/work/yt-digest && uv run pytest tests/test_db.py::test_get_exhausted_videos -v`
Expected: FAIL — method doesn't exist

- [ ] **Step 3: Implement**

Add to `yt_digest/db.py` `Database` class:

```python
    def get_exhausted_videos(self) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                """SELECT v.*, c.name as channel_name
                   FROM videos v JOIN channels c ON v.channel_pk = c.id
                   WHERE v.processed_at IS NULL
                   AND v.summarization_fail_count >= ?""",
                (MAX_SUMMARIZATION_ATTEMPTS,),
            ).fetchall()
```

- [ ] **Step 4: Run all DB tests**

Run: `cd /Users/yorrickjansen/work/yt-digest && uv run pytest tests/test_db.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add yt_digest/db.py tests/test_db.py
git commit -m "feat(db): add get_exhausted_videos method"
```

---

## Chunk 2: Slack Layer Changes

### Task 5: Add `strip_reference_markers` function

**Files:**
- Modify: `yt_digest/slack.py` (new function)
- Test: `tests/test_slack.py`

- [ ] **Step 1: Write tests**

Add to `tests/test_slack.py`:

```python
from yt_digest.slack import strip_reference_markers


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/yorrickjansen/work/yt-digest && uv run pytest tests/test_slack.py::test_strip_single_reference tests/test_slack.py::test_strip_multi_reference tests/test_slack.py::test_strip_many_references tests/test_slack.py::test_strip_preserves_four_digit_years tests/test_slack.py::test_strip_no_markers -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement**

Add to `yt_digest/slack.py` (add `import re` at top):

```python
def strip_reference_markers(text: str) -> str:
    """Remove NotebookLM-style reference markers like [1], [2, 3] but not 4-digit years like [2024]."""
    return re.sub(r"\[\d{1,2}(?:,\s*\d{1,2})*\]", "", text)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/yorrickjansen/work/yt-digest && uv run pytest tests/test_slack.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add yt_digest/slack.py tests/test_slack.py
git commit -m "feat(slack): add strip_reference_markers for NotebookLM cleanup"
```

---

### Task 6: Add `format_video_message`, rewrite `post_to_slack`, and remove old formatting

This task does three things atomically to avoid an intermediate broken state (removing `split_messages` while `post_to_slack` still uses it):

**Files:**
- Modify: `yt_digest/slack.py` (add `format_video_message`, rewrite `post_to_slack`, remove `format_digest`, `split_messages`, `EMOJI_MAP`)
- Test: `tests/test_slack.py`

- [ ] **Step 1: Write tests for `format_video_message` and new `post_to_slack`**

Add to `tests/test_slack.py`:

```python
import httpx
from yt_digest.slack import format_video_message


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
        return httpx.Response(200)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    from yt_digest.slack import post_to_slack

    await post_to_slack("https://hooks.example.com/test", ["msg1", "msg2", "msg3"])
    assert sent == ["msg1", "msg2", "msg3"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/yorrickjansen/work/yt-digest && uv run pytest tests/test_slack.py::test_format_video_message_with_summary tests/test_slack.py::test_format_video_message_unavailable tests/test_slack.py::test_post_to_slack_sends_each_message -v`
Expected: FAIL — `ImportError` for `format_video_message`, signature mismatch for `post_to_slack`

- [ ] **Step 3: Implement all changes in `slack.py`**

Add `format_video_message`:

```python
def format_video_message(video: VideoSummary) -> str:
    lines = [f"\U0001f4ec *{video.title}* ({video.channel_name})"]
    if video.summary == "Summary unavailable":
        lines.append("\u26a0\ufe0f Summary unavailable")
    else:
        lines.append(strip_reference_markers(video.summary))
    lines.append(f"\U0001f517 {video.url}")
    return "\n".join(lines)
```

Replace `post_to_slack`:

```python
async def post_to_slack(webhook_url: str, messages: list[str]) -> None:
    async with httpx.AsyncClient() as client:
        for msg in messages:
            resp = await client.post(webhook_url, json={"text": msg}, timeout=30)
            resp.raise_for_status()
    logger.info("Posted {} Slack message(s)", len(messages))
```

Remove `EMOJI_MAP`, `format_digest`, and `split_messages`.

- [ ] **Step 4: Update test imports and remove old tests**

Remove from `tests/test_slack.py`:
- `format_digest` and `split_messages` imports
- `test_format_digest_with_clusters`
- `test_format_digest_includes_summary_unavailable`
- `test_split_messages_under_limit`
- `test_split_messages_over_limit`
- The `_make_summary` helper (if no longer used)
- `ClusterResult` and `ClusterGroup` imports (if no longer used)

- [ ] **Step 5: Run all slack tests**

Run: `cd /Users/yorrickjansen/work/yt-digest && uv run pytest tests/test_slack.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add yt_digest/slack.py tests/test_slack.py
git commit -m "feat(slack): add format_video_message, rewrite post_to_slack, remove batch formatting"
```

---

## Chunk 3: Pipeline Rewrite

### Task 7: Rewrite `run_pipeline`

**Files:**
- Modify: `yt_digest/__main__.py:47-127` (full rewrite of `run_pipeline`)
- Modify: `yt_digest/__main__.py:15` (update imports — remove `format_digest`, `split_messages`; add `format_video_message`)
- Test: `tests/test_pipeline.py` (new file)

- [ ] **Step 1: Write pipeline integration tests**

Create `tests/test_pipeline.py`:

```python
# tests/test_pipeline.py
import pytest
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

from yt_digest.config import AppConfig, SlackConfig, ClaudeConfig
from yt_digest.db import Database
from yt_digest.models import ChannelInfo, VideoInfo, VideoSummary, ClusterResult, ClusterGroup


def _setup_channel(db: Database) -> int:
    channel = ChannelInfo(
        name="Fireship",
        youtube_handle="@Fireship",
        channel_id="UCsBjURrPoezykLs9EqgamOA",
    )
    db.insert_channel(channel)
    return db.get_active_channels()[0]["id"]


def _make_config(tmp_path) -> AppConfig:
    return AppConfig(
        db_path=str(tmp_path / "test.db"),
        slack=SlackConfig(webhook_url="https://hooks.example.com/test"),
        claude=ClaudeConfig(model="claude-sonnet-4-20250514"),
    )


@pytest.mark.asyncio
async def test_normal_flow_posts_and_marks_processed(db, tmp_path):
    """Videos get summarized, posted individually, and marked processed."""
    channel_pk = _setup_channel(db)
    config = _make_config(tmp_path)

    video = VideoInfo(
        video_id="vid1",
        channel_pk=channel_pk,
        title="Test Video",
        published_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
    )

    mock_summarizer = AsyncMock()
    mock_summarizer.summarize = AsyncMock(return_value=("A great summary", "notebooklm"))

    with patch("yt_digest.__main__.fetch_new_videos", return_value=[video]), \
         patch("yt_digest.__main__.NotebookLMSummarizer"), \
         patch("yt_digest.__main__.ClaudeCodeSummarizer"), \
         patch("yt_digest.__main__.FallbackSummarizer", return_value=mock_summarizer), \
         patch("yt_digest.__main__.cluster_summaries", new_callable=AsyncMock) as mock_cluster, \
         patch("yt_digest.__main__.post_to_slack", new_callable=AsyncMock) as mock_post:
        mock_cluster.return_value = ClusterResult(
            clusters=[ClusterGroup(name="AI", video_indices=[0])]
        )
        from yt_digest.__main__ import run_pipeline
        await run_pipeline(config, db)

    # Video should be marked processed
    row = db.get_video("vid1")
    assert row["processed_at"] is not None
    assert row["summary"] == "A great summary"
    mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_summarization_failure_increments_fail_count(db, tmp_path):
    """Failed summarization increments fail count, video stays unprocessed."""
    channel_pk = _setup_channel(db)
    config = _make_config(tmp_path)

    video = VideoInfo(
        video_id="fail1",
        channel_pk=channel_pk,
        title="Failing Video",
        published_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
    )

    mock_summarizer = AsyncMock()
    mock_summarizer.summarize = AsyncMock(side_effect=Exception("subtitles disabled"))

    with patch("yt_digest.__main__.fetch_new_videos", return_value=[video]), \
         patch("yt_digest.__main__.NotebookLMSummarizer"), \
         patch("yt_digest.__main__.ClaudeCodeSummarizer"), \
         patch("yt_digest.__main__.FallbackSummarizer", return_value=mock_summarizer), \
         patch("yt_digest.__main__.cluster_summaries", new_callable=AsyncMock) as mock_cluster, \
         patch("yt_digest.__main__.post_to_slack", new_callable=AsyncMock) as mock_post:
        mock_cluster.return_value = ClusterResult(clusters=[])
        from yt_digest.__main__ import run_pipeline
        await run_pipeline(config, db)

    row = db.get_video("fail1")
    assert row["summarization_fail_count"] == 1
    assert row["processed_at"] is None


@pytest.mark.asyncio
async def test_exhausted_video_posted_as_link_only(db, tmp_path):
    """Video with 3 failures gets posted as link-only and marked processed."""
    channel_pk = _setup_channel(db)
    config = _make_config(tmp_path)

    video = VideoInfo(
        video_id="exhaust1",
        channel_pk=channel_pk,
        title="Exhausted Video",
        published_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
    )
    db.insert_video(video)
    for _ in range(3):
        db.increment_fail_count("exhaust1")

    with patch("yt_digest.__main__.fetch_new_videos", return_value=[]), \
         patch("yt_digest.__main__.NotebookLMSummarizer"), \
         patch("yt_digest.__main__.ClaudeCodeSummarizer"), \
         patch("yt_digest.__main__.FallbackSummarizer") as mock_cls, \
         patch("yt_digest.__main__.cluster_summaries", new_callable=AsyncMock) as mock_cluster, \
         patch("yt_digest.__main__.post_to_slack", new_callable=AsyncMock) as mock_post:
        mock_cluster.return_value = ClusterResult(clusters=[])
        from yt_digest.__main__ import run_pipeline
        await run_pipeline(config, db)

    row = db.get_video("exhaust1")
    assert row["processed_at"] is not None
    # post_to_slack should have been called for the exhausted video
    mock_post.assert_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/yorrickjansen/work/yt-digest && uv run pytest tests/test_pipeline.py -v`
Expected: FAIL — pipeline still uses old flow

- [ ] **Step 3: Rewrite `run_pipeline`**

Replace `run_pipeline` in `yt_digest/__main__.py`. Update imports at top of file:

```python
from yt_digest.slack import format_video_message, format_no_content_message, post_to_slack
```

(Remove `format_digest` from imports.)

New `run_pipeline`:

```python
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
```

- [ ] **Step 4: Run pipeline tests**

Run: `cd /Users/yorrickjansen/work/yt-digest && uv run pytest tests/test_pipeline.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/yorrickjansen/work/yt-digest && uv run pytest -v`
Expected: ALL PASS

- [ ] **Step 6: Run ruff and pyright**

Run: `cd /Users/yorrickjansen/work/yt-digest && uv run ruff check . && uv run ruff format --check . && uv run pyright`
Expected: No errors

- [ ] **Step 7: Commit**

```bash
git add yt_digest/__main__.py tests/test_pipeline.py
git commit -m "feat: rewrite pipeline for per-video Slack posts and fail tracking"
```

---

### Task 8: Final lint, format, and verification

- [ ] **Step 1: Run ruff format**

Run: `cd /Users/yorrickjansen/work/yt-digest && uv run ruff format .`

- [ ] **Step 2: Run ruff check with fix**

Run: `cd /Users/yorrickjansen/work/yt-digest && uv run ruff check --fix .`

- [ ] **Step 3: Run pyright**

Run: `cd /Users/yorrickjansen/work/yt-digest && uv run pyright`

- [ ] **Step 4: Run full test suite**

Run: `cd /Users/yorrickjansen/work/yt-digest && uv run pytest -v`
Expected: ALL PASS

- [ ] **Step 5: Commit any formatting fixes**

```bash
git add -u
git commit -m "chore: lint and format"
```
