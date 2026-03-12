# yt_digest/db.py
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from yt_digest.models import ChannelInfo, VideoInfo

MAX_SUMMARIZATION_ATTEMPTS = 3


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
            # Migration: add summarization_fail_count if missing
            try:
                conn.execute(
                    "ALTER TABLE videos ADD COLUMN summarization_fail_count INTEGER NOT NULL DEFAULT 0"
                )
            except sqlite3.OperationalError:
                pass  # column already exists

    def insert_channel(self, channel: ChannelInfo) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO channels (name, youtube_handle, channel_id, rss_url, active) VALUES (?, ?, ?, ?, ?)",
                (
                    channel.name,
                    channel.youtube_handle,
                    channel.channel_id,
                    channel.rss_url,
                    channel.active,
                ),
            )

    def get_active_channels(self) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM channels WHERE active = 1").fetchall()

    def video_exists(self, video_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM videos WHERE video_id = ?", (video_id,)
            ).fetchone()
            return row is not None

    def insert_video(self, video: VideoInfo) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO videos (video_id, channel_pk, title, url, published_at) VALUES (?, ?, ?, ?, ?)",
                (
                    video.video_id,
                    video.channel_pk,
                    video.title,
                    video.url,
                    video.published_at.isoformat(),
                ),
            )

    def get_video(self, video_id: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM videos WHERE video_id = ?", (video_id,)
            ).fetchone()

    def increment_fail_count(self, video_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE videos SET summarization_fail_count = summarization_fail_count + 1 WHERE video_id = ?",
                (video_id,),
            )

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
            conn.executemany(
                "UPDATE videos SET processed_at = ?, cluster = ? WHERE video_id = ?",
                [(now, cluster, vid) for vid in video_ids],
            )
