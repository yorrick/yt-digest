# yt-digest Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a daily YouTube channel monitor that summarizes new videos and posts a clustered digest to Slack.

**Architecture:** Python CLI app with four pipeline stages (Fetch → Summarize → Cluster → Post). SQLite for state, NotebookLM for primary summarization, Claude Code SDK for fallback + clustering. Deployed via cron.

**Tech Stack:** Python 3.10+, notebooklm-py, claude-code-sdk, feedparser, pydantic, httpx, python-dotenv, pytest

**Spec:** `docs/superpowers/specs/2026-03-11-yt-digest-design.md`

---

## File Structure

```
yt-digest/
├── yt_digest/
│   ├── __init__.py              # Package marker
│   ├── __main__.py              # CLI entry point (argparse, pipeline orchestration)
│   ├── config.py                # Load config.yaml + .env, Pydantic settings model
│   ├── models.py                # Shared Pydantic models (ChannelInfo, VideoInfo, ClusterResult)
│   ├── db.py                    # SQLite operations (channels + videos tables)
│   ├── fetcher.py               # RSS fetch + dedup against DB
│   ├── summarizer/
│   │   ├── __init__.py          # Factory function: get_summarizer(config)
│   │   ├── base.py              # Summarizer ABC
│   │   ├── notebooklm.py        # NotebookLM implementation via notebooklm-py
│   │   └── claude.py            # Claude Code SDK fallback
│   ├── clusterer.py             # Claude Code SDK topic clustering
│   └── slack.py                 # Slack webhook posting with mrkdwn formatting
├── config.yaml                  # Default configuration
├── pyproject.toml               # Project metadata + dependencies
├── .env.example                 # Template for secrets
├── .gitignore
├── README.md
└── tests/
    ├── conftest.py              # Shared fixtures
    ├── test_db.py
    ├── test_models.py
    ├── test_fetcher.py
    ├── test_summarizer.py
    ├── test_clusterer.py
    └── test_slack.py
```

---

## Chunk 1: Project Scaffolding + Models + DB

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `config.yaml`
- Create: `yt_digest/__init__.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "yt-digest"
version = "0.1.0"
description = "Daily YouTube channel monitor with AI-powered summaries"
requires-python = ">=3.10"
dependencies = [
    "notebooklm-py>=0.5.0",
    "claude-code-sdk>=0.1.0",
    "feedparser>=6.0.0",
    "pydantic>=2.0.0",
    "httpx>=0.27.0",
    "youtube-transcript-api>=0.6.0",
    "python-dotenv>=1.0.0",
    "pyyaml>=6.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
]

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"
```

- [ ] **Step 2: Create `.gitignore`**

```
__pycache__/
*.pyc
.env
*.db
.pytest_cache/
dist/
*.egg-info/
.venv/
```

- [ ] **Step 3: Create `.env.example`**

```
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
# NotebookLM auth cookies (see notebooklm-py docs)
# ANTHROPIC_API_KEY must be UNSET to use Claude Max subscription
```

- [ ] **Step 4: Create `config.yaml`**

```yaml
summarizer:
  primary: notebooklm
  fallback: claude

slack:
  webhook_url: ${SLACK_WEBHOOK_URL}

notebooklm:
  # notebooklm-py uses cookie-based auth stored in its own config
  # See: https://github.com/teng-lin/notebooklm-py#authentication
  enabled: true

claude:
  model: claude-sonnet-4-20250514

db_path: ~/.yt-digest/data.db
```

- [ ] **Step 5: Create `yt_digest/__init__.py`**

```python
"""yt-digest: Daily YouTube channel monitor with AI-powered summaries."""
```

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore .env.example config.yaml yt_digest/__init__.py
git commit -m "chore: scaffold project with pyproject.toml and config"
```

---

### Task 2: Pydantic models

**Files:**
- Create: `yt_digest/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write tests for models**

```python
# tests/test_models.py
from datetime import datetime, timezone
from yt_digest.models import ChannelInfo, VideoInfo, VideoSummary, ClusterResult, ClusterGroup


def test_channel_info_rss_url():
    ch = ChannelInfo(
        name="Fireship",
        youtube_handle="@Fireship",
        channel_id="UCsBjURrPoezykLs9EqgamOA",
    )
    assert ch.rss_url == "https://www.youtube.com/feeds/videos.xml?channel_id=UCsBjURrPoezykLs9EqgamOA"


def test_video_info_url():
    v = VideoInfo(
        video_id="abc123",
        channel_pk=1,
        title="Test Video",
        published_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
    )
    assert v.url == "https://www.youtube.com/watch?v=abc123"


def test_video_summary():
    vs = VideoSummary(
        video_id="abc123",
        title="Test Video",
        url="https://www.youtube.com/watch?v=abc123",
        summary="This is a summary.",
        summarizer="notebooklm",
        channel_name="Fireship",
    )
    assert vs.summarizer == "notebooklm"


def test_cluster_result():
    cr = ClusterResult(clusters=[
        ClusterGroup(name="AI Coding", video_indices=[0, 1]),
        ClusterGroup(name="Marketing", video_indices=[2]),
    ])
    assert len(cr.clusters) == 2
    assert cr.clusters[0].video_indices == [0, 1]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/yorrickjansen/work/yt-digest && python -m pytest tests/test_models.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: Implement models**

```python
# yt_digest/models.py
from datetime import datetime
from pydantic import BaseModel, computed_field


class ChannelInfo(BaseModel):
    name: str
    youtube_handle: str
    channel_id: str
    active: bool = True

    @computed_field
    @property
    def rss_url(self) -> str:
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={self.channel_id}"


class VideoInfo(BaseModel):
    video_id: str
    channel_pk: int
    title: str
    published_at: datetime

    @computed_field
    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"


class VideoSummary(BaseModel):
    video_id: str
    title: str
    url: str
    summary: str
    summarizer: str
    channel_name: str


class ClusterGroup(BaseModel):
    name: str
    video_indices: list[int]


class ClusterResult(BaseModel):
    clusters: list[ClusterGroup]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/yorrickjansen/work/yt-digest && python -m pytest tests/test_models.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add yt_digest/models.py tests/test_models.py
git commit -m "feat: add Pydantic models for channels, videos, summaries, clusters"
```

---

### Task 3: Database layer

**Files:**
- Create: `yt_digest/db.py`
- Create: `tests/conftest.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: Write shared test fixtures**

```python
# tests/conftest.py
import pytest
from yt_digest.db import Database


@pytest.fixture
def db(tmp_path):
    """In-memory-like DB using a temp file for tests."""
    db_path = tmp_path / "test.db"
    database = Database(str(db_path))
    database.init()
    return database
```

- [ ] **Step 2: Write DB tests**

```python
# tests/test_db.py
from datetime import datetime, timezone
from yt_digest.models import ChannelInfo, VideoInfo


def test_insert_and_get_channels(db):
    channel = ChannelInfo(
        name="Fireship",
        youtube_handle="@Fireship",
        channel_id="UCsBjURrPoezykLs9EqgamOA",
    )
    db.insert_channel(channel)
    channels = db.get_active_channels()
    assert len(channels) == 1
    assert channels[0]["youtube_handle"] == "@Fireship"
    assert channels[0]["channel_id"] == "UCsBjURrPoezykLs9EqgamOA"


def test_insert_duplicate_channel_raises(db):
    channel = ChannelInfo(
        name="Fireship",
        youtube_handle="@Fireship",
        channel_id="UCsBjURrPoezykLs9EqgamOA",
    )
    db.insert_channel(channel)
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        db.insert_channel(channel)


import pytest


def test_insert_video_and_check_exists(db):
    channel = ChannelInfo(
        name="Fireship", youtube_handle="@Fireship", channel_id="UCsBjURrPoezykLs9EqgamOA"
    )
    db.insert_channel(channel)
    channels = db.get_active_channels()
    channel_pk = channels[0]["id"]

    video = VideoInfo(
        video_id="abc123",
        channel_pk=channel_pk,
        title="Test Video",
        published_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
    )
    assert not db.video_exists("abc123")
    db.insert_video(video)
    assert db.video_exists("abc123")


def test_get_unprocessed_videos(db):
    channel = ChannelInfo(
        name="Fireship", youtube_handle="@Fireship", channel_id="UCsBjURrPoezykLs9EqgamOA"
    )
    db.insert_channel(channel)
    channels = db.get_active_channels()
    channel_pk = channels[0]["id"]

    video = VideoInfo(
        video_id="abc123",
        channel_pk=channel_pk,
        title="Test Video",
        published_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
    )
    db.insert_video(video)

    unprocessed = db.get_unprocessed_videos()
    assert len(unprocessed) == 1
    assert unprocessed[0]["video_id"] == "abc123"


def test_store_summary_and_mark_processed(db):
    channel = ChannelInfo(
        name="Fireship", youtube_handle="@Fireship", channel_id="UCsBjURrPoezykLs9EqgamOA"
    )
    db.insert_channel(channel)
    channels = db.get_active_channels()
    channel_pk = channels[0]["id"]

    video = VideoInfo(
        video_id="abc123",
        channel_pk=channel_pk,
        title="Test Video",
        published_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
    )
    db.insert_video(video)

    db.store_summary("abc123", "This is a summary.", "notebooklm")
    row = db.get_video("abc123")
    assert row["summary"] == "This is a summary."
    assert row["processed_at"] is None  # not yet marked processed

    db.mark_processed(["abc123"], "AI Coding")
    row = db.get_video("abc123")
    assert row["processed_at"] is not None
    assert row["cluster"] == "AI Coding"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd /Users/yorrickjansen/work/yt-digest && python -m pytest tests/test_db.py -v`
Expected: FAIL

- [ ] **Step 4: Implement database layer**

```python
# yt_digest/db.py
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from yt_digest.models import ChannelInfo, VideoInfo


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init(self) -> None:
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    youtube_handle TEXT UNIQUE NOT NULL,
                    channel_id TEXT NOT NULL,
                    rss_url TEXT NOT NULL,
                    active BOOLEAN NOT NULL DEFAULT 1,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS videos (
                    video_id TEXT PRIMARY KEY,
                    channel_pk INTEGER NOT NULL REFERENCES channels(id),
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    published_at TIMESTAMP NOT NULL,
                    summary TEXT,
                    cluster TEXT,
                    summarizer TEXT,
                    processed_at TIMESTAMP
                );
            """)

    def insert_channel(self, channel: ChannelInfo) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO channels (name, youtube_handle, channel_id, rss_url, active) VALUES (?, ?, ?, ?, ?)",
                (channel.name, channel.youtube_handle, channel.channel_id, channel.rss_url, channel.active),
            )

    def get_active_channels(self) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM channels WHERE active = 1").fetchall()

    def video_exists(self, video_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM videos WHERE video_id = ?", (video_id,)).fetchone()
            return row is not None

    def insert_video(self, video: VideoInfo) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO videos (video_id, channel_pk, title, url, published_at) VALUES (?, ?, ?, ?, ?)",
                (video.video_id, video.channel_pk, video.title, video.url, video.published_at.isoformat()),
            )

    def get_video(self, video_id: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM videos WHERE video_id = ?", (video_id,)).fetchone()

    def get_unprocessed_videos(self) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                """SELECT v.*, c.name as channel_name
                   FROM videos v JOIN channels c ON v.channel_pk = c.id
                   WHERE v.processed_at IS NULL"""
            ).fetchall()

    def store_summary(self, video_id: str, summary: str, summarizer: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE videos SET summary = ?, summarizer = ? WHERE video_id = ?",
                (summary, summarizer, video_id),
            )

    def mark_processed(self, video_ids: list[str], cluster: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            for vid in video_ids:
                conn.execute(
                    "UPDATE videos SET processed_at = ?, cluster = ? WHERE video_id = ?",
                    (now, cluster, vid),
                )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/yorrickjansen/work/yt-digest && python -m pytest tests/test_db.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add yt_digest/db.py tests/conftest.py tests/test_db.py
git commit -m "feat: add SQLite database layer for channels and videos"
```

---

## Chunk 2: Config + Fetcher

### Task 4: Configuration loading

**Files:**
- Create: `yt_digest/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write config tests**

```python
# tests/test_config.py
import os
from pathlib import Path
from yt_digest.config import load_config


def test_load_config_from_yaml(tmp_path, monkeypatch):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
summarizer:
  primary: notebooklm
  fallback: claude

slack:
  webhook_url: ${SLACK_WEBHOOK_URL}

claude:
  model: claude-sonnet-4-20250514

db_path: ~/.yt-digest/data.db
""")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/test")
    config = load_config(str(config_file))
    assert config.summarizer.primary == "notebooklm"
    assert config.summarizer.fallback == "claude"
    assert config.slack.webhook_url == "https://hooks.slack.com/test"
    assert config.claude.model == "claude-sonnet-4-20250514"


def test_config_env_var_substitution(tmp_path, monkeypatch):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
summarizer:
  primary: notebooklm
  fallback: claude

slack:
  webhook_url: ${SLACK_WEBHOOK_URL}

claude:
  model: claude-sonnet-4-20250514

db_path: /tmp/test.db
""")
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/replaced")
    config = load_config(str(config_file))
    assert config.slack.webhook_url == "https://hooks.slack.com/replaced"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/yorrickjansen/work/yt-digest && python -m pytest tests/test_config.py -v`
Expected: FAIL

- [ ] **Step 3: Implement config loading**

```python
# yt_digest/config.py
import os
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel


class SummarizerConfig(BaseModel):
    primary: str = "notebooklm"
    fallback: str = "claude"


class SlackConfig(BaseModel):
    webhook_url: str


class ClaudeConfig(BaseModel):
    model: str = "claude-sonnet-4-20250514"


class AppConfig(BaseModel):
    summarizer: SummarizerConfig = SummarizerConfig()
    slack: SlackConfig
    claude: ClaudeConfig = ClaudeConfig()
    db_path: str = "~/.yt-digest/data.db"


def _substitute_env_vars(text: str) -> str:
    """Replace ${VAR_NAME} with environment variable values."""
    def replacer(match: re.Match) -> str:
        var_name = match.group(1)
        value = os.environ.get(var_name)
        if value is None:
            raise ValueError(f"Environment variable {var_name} is not set")
        return value
    return re.sub(r"\$\{(\w+)\}", replacer, text)


def load_config(config_path: str = "config.yaml") -> AppConfig:
    load_dotenv()
    raw = Path(config_path).read_text()
    substituted = _substitute_env_vars(raw)
    data = yaml.safe_load(substituted)
    config = AppConfig(**data)
    config.db_path = str(Path(config.db_path).expanduser())
    return config
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/yorrickjansen/work/yt-digest && python -m pytest tests/test_config.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add yt_digest/config.py tests/test_config.py
git commit -m "feat: add config loading from YAML with env var substitution"
```

---

### Task 5: RSS fetcher

**Files:**
- Create: `yt_digest/fetcher.py`
- Create: `tests/test_fetcher.py`

- [ ] **Step 1: Write fetcher tests**

```python
# tests/test_fetcher.py
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock
from yt_digest.fetcher import fetch_new_videos, parse_feed_entries

# Sample RSS XML from a YouTube channel feed
SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns="http://www.w3.org/2005/Atom">
  <title>Fireship</title>
  <entry>
    <yt:videoId>abc123</yt:videoId>
    <title>New AI Video</title>
    <published>2026-03-11T10:00:00+00:00</published>
  </entry>
  <entry>
    <yt:videoId>def456</yt:videoId>
    <title>Old Video</title>
    <published>2026-03-01T10:00:00+00:00</published>
  </entry>
</feed>"""


def test_parse_feed_entries():
    entries = parse_feed_entries(SAMPLE_RSS, channel_pk=1)
    assert len(entries) == 2
    assert entries[0].video_id == "abc123"
    assert entries[0].title == "New AI Video"
    assert entries[0].channel_pk == 1


def test_parse_feed_filters_by_date():
    cutoff = datetime(2026, 3, 10, tzinfo=timezone.utc)
    entries = parse_feed_entries(SAMPLE_RSS, channel_pk=1, since=cutoff)
    assert len(entries) == 1
    assert entries[0].video_id == "abc123"


def test_fetch_new_videos_skips_existing(db):
    from yt_digest.models import ChannelInfo, VideoInfo

    channel = ChannelInfo(name="Fireship", youtube_handle="@Fireship", channel_id="UCsBjURrPoezykLs9EqgamOA")
    db.insert_channel(channel)
    channels = db.get_active_channels()
    channel_pk = channels[0]["id"]

    # Pre-insert a video so it's "already seen"
    existing = VideoInfo(
        video_id="abc123", channel_pk=channel_pk, title="Existing",
        published_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
    )
    db.insert_video(existing)

    with patch("yt_digest.fetcher._fetch_feed_xml", return_value=SAMPLE_RSS):
        new_videos = fetch_new_videos(db)

    # abc123 already exists, def456 is too old (>48h if cutoff is ~now)
    # Only truly new videos within 48h window should appear
    existing_ids = {v.video_id for v in new_videos}
    assert "abc123" not in existing_ids
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/yorrickjansen/work/yt-digest && python -m pytest tests/test_fetcher.py -v`
Expected: FAIL

- [ ] **Step 3: Implement fetcher**

```python
# yt_digest/fetcher.py
import logging
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree as ET

import httpx

from yt_digest.db import Database
from yt_digest.models import VideoInfo

logger = logging.getLogger(__name__)

ATOM_NS = "http://www.w3.org/2005/Atom"
YT_NS = "http://www.youtube.com/xml/schemas/2015"


def _fetch_feed_xml(rss_url: str) -> str:
    resp = httpx.get(rss_url, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    return resp.text


def parse_feed_entries(
    xml_text: str, channel_pk: int, since: datetime | None = None
) -> list[VideoInfo]:
    root = ET.fromstring(xml_text)
    entries = []
    for entry in root.findall(f"{{{ATOM_NS}}}entry"):
        video_id = entry.find(f"{{{YT_NS}}}videoId")
        title = entry.find(f"{{{ATOM_NS}}}title")
        published = entry.find(f"{{{ATOM_NS}}}published")
        if video_id is None or title is None or published is None:
            continue
        pub_dt = datetime.fromisoformat(published.text)
        if since and pub_dt < since:
            continue
        entries.append(VideoInfo(
            video_id=video_id.text,
            channel_pk=channel_pk,
            title=title.text,
            published_at=pub_dt,
        ))
    return entries


def fetch_new_videos(db: Database) -> list[VideoInfo]:
    channels = db.get_active_channels()
    since = datetime.now(timezone.utc) - timedelta(hours=48)
    new_videos = []

    for ch in channels:
        try:
            xml = _fetch_feed_xml(ch["rss_url"])
            entries = parse_feed_entries(xml, channel_pk=ch["id"], since=since)
            for video in entries:
                if not db.video_exists(video.video_id):
                    db.insert_video(video)
                    new_videos.append(video)
        except Exception:
            logger.exception("Failed to fetch RSS for channel %s", ch["youtube_handle"])
            continue

    logger.info("Found %d new videos across %d channels", len(new_videos), len(channels))
    return new_videos
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/yorrickjansen/work/yt-digest && python -m pytest tests/test_fetcher.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add yt_digest/fetcher.py tests/test_fetcher.py
git commit -m "feat: add RSS fetcher with 48h window and dedup"
```

---

## Chunk 3: Summarizers

### Task 6: Summarizer base + factory

**Files:**
- Create: `yt_digest/summarizer/__init__.py`
- Create: `yt_digest/summarizer/base.py`

- [ ] **Step 1: Create summarizer ABC**

```python
# yt_digest/summarizer/base.py
from abc import ABC, abstractmethod


class Summarizer(ABC):
    @abstractmethod
    async def summarize(self, video_url: str) -> str:
        """Return ~10 sentence summary of the video."""
```

- [ ] **Step 2: Create factory with fallback logic**

```python
# yt_digest/summarizer/__init__.py
import logging
from yt_digest.summarizer.base import Summarizer

logger = logging.getLogger(__name__)


class FallbackSummarizer:
    """Wraps a primary + fallback summarizer. Falls back on any exception.

    Not a Summarizer subclass because it returns (summary, backend_name) tuples.
    """

    def __init__(self, primary: Summarizer, fallback: Summarizer):
        self.primary = primary
        self.fallback = fallback
        self._primary_failed = False

    async def summarize(self, video_url: str) -> tuple[str, str]:
        """Returns (summary, summarizer_name)."""
        if not self._primary_failed:
            try:
                result = await self.primary.summarize(video_url)
                return result, "notebooklm"
            except Exception:
                logger.warning("Primary summarizer failed, falling back to Claude for this run", exc_info=True)
                self._primary_failed = True

        result = await self.fallback.summarize(video_url)
        return result, "claude"
```

- [ ] **Step 3: Commit**

```bash
git add yt_digest/summarizer/__init__.py yt_digest/summarizer/base.py
git commit -m "feat: add summarizer ABC and fallback wrapper"
```

---

### Task 7: NotebookLM summarizer

**Files:**
- Create: `yt_digest/summarizer/notebooklm.py`

- [ ] **Step 1: Implement NotebookLM summarizer**

```python
# yt_digest/summarizer/notebooklm.py
import logging

from notebooklm import NotebookLMClient
from yt_digest.summarizer.base import Summarizer

logger = logging.getLogger(__name__)

SUMMARY_PROMPT = (
    "Summarize this video in approximately 10 sentences. "
    "Cover the key points, insights, and takeaways. "
    "Be specific and cite what the speaker actually said."
)


class NotebookLMSummarizer(Summarizer):
    async def summarize(self, video_url: str) -> str:
        async with await NotebookLMClient.from_storage() as client:
            nb = await client.notebooks.create("yt-digest-temp")
            try:
                await client.sources.add_url(nb.id, video_url, wait=True)
                result = await client.chat.ask(nb.id, SUMMARY_PROMPT)
                return result.answer
            finally:
                try:
                    await client.notebooks.delete(nb.id)
                except Exception:
                    logger.warning("Failed to clean up notebook %s", nb.id)
```

- [ ] **Step 2: Commit**

```bash
git add yt_digest/summarizer/notebooklm.py
git commit -m "feat: add NotebookLM summarizer via notebooklm-py"
```

---

### Task 8: Claude Code SDK summarizer

**Files:**
- Create: `yt_digest/summarizer/claude.py`
- Create: `tests/test_summarizer.py`

- [ ] **Step 1: Implement Claude Code SDK summarizer**

```python
# yt_digest/summarizer/claude.py
import logging

from claude_code_sdk import ClaudeCodeOptions, query, AssistantMessage, TextBlock
from youtube_transcript_api import YouTubeTranscriptApi

from yt_digest.summarizer.base import Summarizer

logger = logging.getLogger(__name__)

SUMMARY_PROMPT_TEMPLATE = """Summarize the following YouTube video transcript in approximately 10 sentences.
Cover the key points, insights, and takeaways. Be specific about what was said.
Do NOT add any information that is not in the transcript.

TRANSCRIPT:
{transcript}

Respond with ONLY the summary, no preamble or formatting."""


class ClaudeCodeSummarizer(Summarizer):
    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self.model = model

    async def summarize(self, video_url: str) -> str:
        video_id = video_url.split("v=")[-1]
        transcript_parts = YouTubeTranscriptApi.get_transcript(video_id)
        transcript_text = " ".join(part["text"] for part in transcript_parts)

        prompt = SUMMARY_PROMPT_TEMPLATE.format(transcript=transcript_text[:50000])

        options = ClaudeCodeOptions(
            max_turns=1,
            model=self.model,
        )

        result_text = ""
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        result_text += block.text

        if not result_text.strip():
            raise RuntimeError("Claude Code SDK returned empty response")

        return result_text.strip()
```

- [ ] **Step 2: Write summarizer fallback tests (mocked)**

```python
# tests/test_summarizer.py
import pytest
from unittest.mock import AsyncMock, patch
from yt_digest.summarizer import FallbackSummarizer
from yt_digest.summarizer.base import Summarizer


class MockPrimary(Summarizer):
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.call_count = 0

    async def summarize(self, video_url: str) -> str:
        self.call_count += 1
        if self.fail:
            raise RuntimeError("Primary failed")
        return f"Primary summary of {video_url}"


class MockFallback(Summarizer):
    def __init__(self):
        self.call_count = 0

    async def summarize(self, video_url: str) -> str:
        self.call_count += 1
        return f"Fallback summary of {video_url}"


@pytest.mark.asyncio
async def test_fallback_uses_primary_when_healthy():
    primary = MockPrimary(fail=False)
    fallback = MockFallback()
    summarizer = FallbackSummarizer(primary, fallback)

    summary, backend = await summarizer.summarize("https://youtube.com/watch?v=test")
    assert backend == "notebooklm"
    assert "Primary summary" in summary
    assert primary.call_count == 1
    assert fallback.call_count == 0


@pytest.mark.asyncio
async def test_fallback_switches_on_primary_failure():
    primary = MockPrimary(fail=True)
    fallback = MockFallback()
    summarizer = FallbackSummarizer(primary, fallback)

    summary, backend = await summarizer.summarize("https://youtube.com/watch?v=test1")
    assert backend == "claude"
    assert "Fallback summary" in summary

    # Second call should skip primary entirely
    summary2, backend2 = await summarizer.summarize("https://youtube.com/watch?v=test2")
    assert backend2 == "claude"
    assert primary.call_count == 1  # only tried once
    assert fallback.call_count == 2
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `cd /Users/yorrickjansen/work/yt-digest && python -m pytest tests/test_summarizer.py -v`
Expected: PASS (2 tests)

- [ ] **Step 4: Commit**

```bash
git add yt_digest/summarizer/claude.py tests/test_summarizer.py
git commit -m "feat: add Claude Code SDK summarizer and fallback tests"
```

---

## Chunk 4: Clusterer + Slack

### Task 9: Topic clusterer

**Files:**
- Create: `yt_digest/clusterer.py`
- Create: `tests/test_clusterer.py`

- [ ] **Step 1: Write clusterer tests**

```python
# tests/test_clusterer.py
import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from yt_digest.clusterer import cluster_summaries, _parse_cluster_response
from yt_digest.models import VideoSummary, ClusterResult


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/yorrickjansen/work/yt-digest && python -m pytest tests/test_clusterer.py -v`
Expected: FAIL

- [ ] **Step 3: Implement clusterer**

```python
# yt_digest/clusterer.py
import json
import logging

from claude_code_sdk import ClaudeCodeOptions, query, AssistantMessage, TextBlock

from yt_digest.models import VideoSummary, ClusterResult, ClusterGroup

logger = logging.getLogger(__name__)

CLUSTER_PROMPT_TEMPLATE = """You are given a list of YouTube video summaries. Group them into 2-4 topic clusters based on their content.

Return ONLY a JSON array, no other text. Each element must have:
- "name": a short descriptive cluster name (e.g., "AI Coding & Agents", "Marketing & Entrepreneurship")
- "video_indices": array of 0-based indices from the list below

Videos:
{videos_text}

Respond with ONLY the JSON array."""


def _parse_cluster_response(response: str, num_videos: int) -> ClusterResult:
    fallback = ClusterResult(clusters=[
        ClusterGroup(name="Today's Videos", video_indices=list(range(num_videos)))
    ])
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
        return ClusterResult(clusters=[
            ClusterGroup(name="Today's Videos", video_indices=list(range(len(summaries))))
        ])

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/yorrickjansen/work/yt-digest && python -m pytest tests/test_clusterer.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add yt_digest/clusterer.py tests/test_clusterer.py
git commit -m "feat: add topic clusterer with Claude Code SDK"
```

---

### Task 10: Slack posting

**Files:**
- Create: `yt_digest/slack.py`
- Create: `tests/test_slack.py`

- [ ] **Step 1: Write Slack tests**

```python
# tests/test_slack.py
from datetime import date
from yt_digest.models import VideoSummary, ClusterResult, ClusterGroup
from yt_digest.slack import format_digest, format_no_content_message, split_messages


def _make_summary(idx: int, title: str = "Video", channel: str = "Channel") -> VideoSummary:
    return VideoSummary(
        video_id=f"vid{idx}",
        title=f"{title} {idx}",
        url=f"https://www.youtube.com/watch?v=vid{idx}",
        summary=f"Summary of video {idx}. " * 5,
        summarizer="notebooklm",
        channel_name=channel,
    )


def test_format_digest_with_clusters():
    summaries = [_make_summary(0, "AI Video", "Fireship"), _make_summary(1, "Marketing Video", "Greg")]
    clusters = ClusterResult(clusters=[
        ClusterGroup(name="AI Coding", video_indices=[0]),
        ClusterGroup(name="Marketing", video_indices=[1]),
    ])
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
    summaries = [VideoSummary(
        video_id="vid0", title="Broken Video",
        url="https://www.youtube.com/watch?v=vid0",
        summary="Summary unavailable",
        summarizer="none", channel_name="Test",
    )]
    clusters = ClusterResult(clusters=[
        ClusterGroup(name="Today's Videos", video_indices=[0]),
    ])
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/yorrickjansen/work/yt-digest && python -m pytest tests/test_slack.py -v`
Expected: FAIL

- [ ] **Step 3: Implement Slack module**

```python
# yt_digest/slack.py
import logging
from datetime import date

import httpx

from yt_digest.models import VideoSummary, ClusterResult

logger = logging.getLogger(__name__)

EMOJI_MAP = {
    0: "\U0001f916",  # 🤖
    1: "\U0001f4c8",  # 📈
    2: "\U0001f680",  # 🚀
    3: "\U0001f4a1",  # 💡
}


def format_digest(
    summaries: list[VideoSummary],
    clusters: ClusterResult,
    today: date,
) -> str:
    date_str = today.strftime("%B %d, %Y")
    lines = [f"\U0001f4ec *YouTube Digest — {date_str}*\n"]

    for i, cluster in enumerate(clusters.clusters):
        emoji = EMOJI_MAP.get(i, "\U0001f4cc")
        lines.append(f"{emoji} *{cluster.name}*")
        for idx in cluster.video_indices:
            s = summaries[idx]
            lines.append(f"\u2022 *{s.title}* ({s.channel_name}) — {s.summary}")
            lines.append(f"  \U0001f517 {s.url}")
        lines.append("")

    return "\n".join(lines).strip()


def format_no_content_message(today: date) -> str:
    date_str = today.strftime("%B %d, %Y")
    return f"\U0001f4ec *YouTube Digest — {date_str}*\n\nNo new content today."


def split_messages(text: str, max_chars: int = 3000) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    sections = text.split("\n\n")
    messages = []
    current = ""

    for section in sections:
        if current and len(current) + len(section) + 2 > max_chars:
            messages.append(current.strip())
            current = section
        else:
            current = current + "\n\n" + section if current else section

    if current.strip():
        messages.append(current.strip())

    return messages


async def post_to_slack(webhook_url: str, text: str) -> None:
    messages = split_messages(text)
    async with httpx.AsyncClient() as client:
        for msg in messages:
            resp = await client.post(webhook_url, json={"text": msg}, timeout=30)
            resp.raise_for_status()
    logger.info("Posted %d Slack message(s)", len(messages))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/yorrickjansen/work/yt-digest && python -m pytest tests/test_slack.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add yt_digest/slack.py tests/test_slack.py
git commit -m "feat: add Slack posting with mrkdwn formatting and message splitting"
```

---

## Chunk 5: Main Entry Point + Channel Init

### Task 11: CLI entry point and pipeline orchestration

**Files:**
- Create: `yt_digest/__main__.py`

- [ ] **Step 1: Implement main entry point**

```python
# yt_digest/__main__.py
import argparse
import asyncio
import logging
import sys
from datetime import date
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from yt_digest.config import load_config
from yt_digest.db import Database
from yt_digest.fetcher import fetch_new_videos
from yt_digest.clusterer import cluster_summaries
from yt_digest.models import VideoSummary
from yt_digest.slack import format_digest, format_no_content_message, post_to_slack
from yt_digest.summarizer import FallbackSummarizer
from yt_digest.summarizer.notebooklm import NotebookLMSummarizer
from yt_digest.summarizer.claude import ClaudeCodeSummarizer

logger = logging.getLogger("yt_digest")


def setup_logging() -> None:
    log_dir = Path("~/.yt-digest").expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "yt-digest.log"

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    file_handler = TimedRotatingFileHandler(log_file, when="D", backupCount=7)
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logger.setLevel(logging.INFO)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="yt-digest: Daily YouTube channel monitor")
    parser.add_argument("--init", action="store_true", help="Initialize DB and seed channels")
    parser.add_argument("--dry-run", action="store_true", help="Print digest to stdout instead of posting to Slack")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    return parser.parse_args()


async def run_pipeline(config, db: Database, dry_run: bool = False) -> None:
    # 1. Fetch new videos
    logger.info("Fetching new videos...")
    new_videos = fetch_new_videos(db)

    # Check for unprocessed videos with existing summaries (crash recovery)
    unprocessed = db.get_unprocessed_videos()
    videos_needing_summary = [v for v in unprocessed if v["summary"] is None]
    videos_with_summary = [v for v in unprocessed if v["summary"] is not None]

    logger.info(
        "%d new videos, %d need summaries, %d have summaries from previous run",
        len(new_videos), len(videos_needing_summary), len(videos_with_summary),
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
            logger.info("Summarized %s via %s", video_id, backend)
        except Exception:
            logger.exception("Failed to summarize %s", video_id)
            db.store_summary(video_id, "Summary unavailable", "none")

    # 3. Build summaries list from all unprocessed videos
    all_unprocessed = db.get_unprocessed_videos()
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
    if not dry_run and all_unprocessed:
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
```

- [ ] **Step 2: Commit**

```bash
git add yt_digest/__main__.py
git commit -m "feat: add CLI entry point with pipeline orchestration"
```

---

### Task 12: Channel initialization (--init)

**Files:**
- Create: `yt_digest/init_channels.py`

- [ ] **Step 1: Implement channel init with handle-to-ID resolution**

```python
# yt_digest/init_channels.py
import logging
import re

import httpx

from yt_digest.db import Database
from yt_digest.models import ChannelInfo

logger = logging.getLogger(__name__)

INITIAL_CHANNELS = [
    ("Simon Hoiberg", "@SimonHoiberg"),
    ("Stripe Developers", "@StripeDev"),
    ("IndyDevDan", "@indydevdan"),
    ("Y Combinator", "@ycombinator"),
    ("Cole Medin", "@ColeMedin"),
    ("Hamel Husain", "@hamelhusain7140"),
    ("Greg Isenberg", "@GregIsenberg"),
    ("Fireship", "@Fireship"),
    ("Matthew Berman", "@matthew_berman"),
    ("AI Code King", "@AICodeKing"),
    ("Claude", "@claude"),
    ("EO Global", "@eoglobal"),
    ("Nate B Jones", "@NateBJones"),
]


def resolve_channel_id(handle: str) -> str:
    """Resolve a YouTube handle (e.g., @Fireship) to a channel ID (UCxxx)."""
    url = f"https://www.youtube.com/{handle}"
    resp = httpx.get(url, follow_redirects=True, timeout=30)
    resp.raise_for_status()

    # Look for channel ID in page source
    match = re.search(r'"externalId":"(UC[a-zA-Z0-9_-]+)"', resp.text)
    if match:
        return match.group(1)

    # Fallback: look in meta tags
    match = re.search(r'<meta itemprop="channelId" content="(UC[a-zA-Z0-9_-]+)"', resp.text)
    if match:
        return match.group(1)

    raise ValueError(f"Could not resolve channel ID for {handle}")


def init_channels(db: Database) -> None:
    for name, handle in INITIAL_CHANNELS:
        try:
            # Check if already exists
            channels = db.get_active_channels()
            existing_handles = {ch["youtube_handle"] for ch in channels}
            if handle in existing_handles:
                logger.info("Channel %s already exists, skipping", handle)
                continue

            logger.info("Resolving channel ID for %s...", handle)
            channel_id = resolve_channel_id(handle)
            channel = ChannelInfo(name=name, youtube_handle=handle, channel_id=channel_id)
            db.insert_channel(channel)
            logger.info("Added channel %s (ID: %s)", name, channel_id)
        except Exception:
            logger.exception("Failed to add channel %s", handle)
```

- [ ] **Step 2: Commit**

```bash
git add yt_digest/init_channels.py
git commit -m "feat: add channel initialization with YouTube handle resolution"
```

---

### Task 13: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write README**

```markdown
# yt-digest

Daily YouTube channel monitor that summarizes new videos and posts a clustered digest to Slack.

## How it works

1. Fetches RSS feeds from monitored YouTube channels
2. Summarizes new videos using NotebookLM (falls back to Claude Code SDK)
3. Clusters summaries by topic using Claude
4. Posts a grouped digest to Slack

## Setup

```bash
# Clone
git clone https://github.com/YOUR_USERNAME/yt-digest.git
cd yt-digest

# Install
pip install -e ".[dev]"

# Configure
cp .env.example .env
# Edit .env with your Slack webhook URL

# Initialize database and seed channels
python -m yt_digest --init

# Test run (prints to stdout)
python -m yt_digest --dry-run

# Production run
python -m yt_digest
```

## Cron setup (Ubuntu)

```bash
crontab -e
# Add:
0 8 * * * cd /path/to/yt-digest && /path/to/python -m yt_digest
```

## Requirements

- Python 3.10+
- Claude Code CLI (for Max subscription auth)
- Slack Incoming Webhook
- NotebookLM account (optional, for primary summarizer)

## Configuration

Edit `config.yaml` to customize:
- Summarizer selection (primary/fallback)
- Claude model
- Database path

Secrets go in `.env` (gitignored).
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with setup and usage instructions"
```

---

### Task 14: Create GitHub repo and push

- [ ] **Step 1: Create public GitHub repo**

```bash
cd /Users/yorrickjansen/work/yt-digest
gh repo create yt-digest --public --source=. --push
```

- [ ] **Step 2: Verify repo is accessible**

```bash
gh repo view --web
```
