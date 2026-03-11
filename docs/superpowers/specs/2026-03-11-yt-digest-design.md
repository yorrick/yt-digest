# yt-digest: Daily YouTube Channel Monitor

## Overview

A Python CLI app run daily via cron on an Ubuntu desktop. Monitors YouTube channels for new videos, generates summaries using NotebookLM (with Claude as fallback), clusters summaries by topic, and posts a grouped daily digest to Slack.

## Pipeline

```
[Fetch] → [Summarize] → [Cluster] → [Post]
```

1. **Fetch** — Pull RSS feeds from monitored YouTube channels, compare against SQLite DB of processed videos, yield new video URLs
2. **Summarize** — Pass each new video URL to NotebookLM via `notebooklm-py` (primary). On failure, fall back to Claude via Anthropic SDK (fetches transcript with `youtube-transcript-api`, then summarizes). ~10 sentences per video.
3. **Cluster** — Group summaries into 2-4 dynamic topic clusters using a single Claude API call
4. **Post** — Format clustered summaries into a single Slack digest message via Incoming Webhook with video titles linking to sources

## Channels (initial set)

| Handle | Name |
|--------|------|
| @SimonHoiberg | Simon Hoiberg |
| @StripeDev | Stripe Developers |
| @indydevdan | IndyDevDan |
| @ycombinator | Y Combinator |
| @ColeMedin | Cole Medin |
| @hamelhusain7140 | Hamel Husain |
| @GregIsenberg | Greg Isenberg |
| @Fireship | Fireship |
| @matthew_berman | Matthew Berman |
| @AICodeKing | AI Code King |
| @claude | Claude |
| @eoglobal | EO Global |
| @NateBJones | Nate B Jones |

## Data Model (SQLite)

### channels

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| name | TEXT | Display name |
| youtube_handle | TEXT UNIQUE | e.g., "@Fireship" |
| rss_url | TEXT | RSS feed URL |
| active | BOOLEAN | Toggle monitoring on/off |
| created_at | TIMESTAMP | When added |

### videos

| Column | Type | Description |
|--------|------|-------------|
| video_id | TEXT PK | YouTube video ID |
| channel_id | INTEGER FK | References channels.id |
| title | TEXT | Video title |
| url | TEXT | Full YouTube URL |
| published_at | TIMESTAMP | When published |
| summary | TEXT | Generated summary |
| cluster | TEXT | Topic cluster assigned |
| summarizer | TEXT | Backend used (notebooklm / claude) |
| processed_at | TIMESTAMP | When processed |

## Summarizer Interface

```python
class Summarizer(ABC):
    async def summarize(self, video_url: str) -> str:
        """Return ~10 sentence summary of the video."""

class NotebookLMSummarizer(Summarizer):
    # Uses notebooklm-py: create notebook, add YouTube URL as source,
    # chat to get summary, clean up notebook

class ClaudeSummarizer(Summarizer):
    # Fallback: fetch transcript via youtube-transcript-api,
    # send to Claude API with summarization prompt
```

- Primary: NotebookLMSummarizer
- Fallback: ClaudeSummarizer (auto-triggered on NotebookLM failure)
- Summarizer selection via config, with automatic fallback

## Clustering

Single Claude API call after all summaries are generated. Prompt sends list of (title, summary) pairs, asks Claude to group into 2-4 dynamic topic clusters with cluster names based on actual content (not hardcoded categories).

## Slack Output Format

Single message via Incoming Webhook:

```
📬 YouTube Digest — March 11, 2026

🤖 AI Coding & Agents
• *Video Title Here* — Summary in ~10 sentences...
  🔗 https://youtube.com/watch?v=xxx

📈 Marketing & Entrepreneurship
• *Another Video* — Summary...
  🔗 https://youtube.com/watch?v=yyy
```

Edge cases:
- No new videos → post "No new content today"
- Single video fails to summarize → include with "Summary unavailable" + link, don't block the rest

## Configuration

`config.yaml`:
```yaml
summarizer:
  primary: notebooklm
  fallback: claude

slack:
  webhook_url: ${SLACK_WEBHOOK_URL}

notebooklm:
  # notebooklm-py auth config

claude:
  api_key: ${ANTHROPIC_API_KEY}
  model: claude-sonnet-4-20250514

db_path: ~/.yt-digest/data.db
```

Secrets loaded from `.env` file via `python-dotenv`. `.env` is gitignored.

## Project Structure

```
yt-digest/
├── yt_digest/
│   ├── __init__.py
│   ├── __main__.py          # Entry point
│   ├── config.py             # Load config.yaml + env vars
│   ├── fetcher.py            # RSS fetch + dedup against DB
│   ├── summarizer/
│   │   ├── __init__.py
│   │   ├── base.py           # ABC
│   │   ├── notebooklm.py     # notebooklm-py implementation
│   │   └── claude.py         # Anthropic SDK fallback
│   ├── clusterer.py          # Claude-based topic clustering
│   ├── slack.py              # Webhook posting
│   └── db.py                 # SQLite operations
├── config.yaml
├── pyproject.toml
├── .env.example
├── .gitignore
├── README.md
└── tests/
    ├── conftest.py           # Shared fixtures (in-memory DB, mock summarizers)
    ├── test_fetcher.py       # RSS parsing, dedup logic
    ├── test_db.py            # DB operations, schema
    ├── test_clusterer.py     # Clustering output format
    ├── test_slack.py         # Message formatting
    └── test_summarizer.py    # Summarizer fallback logic
```

## Testing Strategy

- **Unit tests** for each module with mocked external dependencies (no real API calls in tests)
- **Fixtures**: in-memory SQLite DB, mock RSS responses, mock summarizer responses
- **Key test cases**:
  - Fetcher correctly identifies new vs already-processed videos
  - Summarizer falls back to Claude when NotebookLM fails
  - Clusterer groups videos and returns valid structure
  - Slack formatter produces correct Block Kit / mrkdwn output
  - DB operations (insert channel, insert video, dedup query)
  - Config loads from yaml + .env correctly

## Dependencies

- `notebooklm-py` — NotebookLM unofficial API
- `anthropic` — Claude API (fallback summarizer + clustering)
- `feedparser` — RSS feed parsing
- `pyyaml` — Config file parsing
- `aiohttp` — Async HTTP for Slack webhook
- `youtube-transcript-api` — Transcript extraction for Claude fallback
- `python-dotenv` — Load secrets from `.env` file
- `pytest` + `pytest-asyncio` — Testing

## Deployment

- Cron job: `0 8 * * * cd /path/to/yt-digest && /path/to/python -m yt_digest`
- First run: `python -m yt_digest --init` seeds 13 channels into SQLite
- Target: Ubuntu desktop
- Public GitHub repo

## Future Extensions (out of scope)

- Blog/newsletter monitoring
- NotebookLM as interactive knowledge base
- Relevance filtering
