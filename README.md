# yt-digest

Monitors YouTube channel RSS feeds, downloads captions through Apify, and uses DeepSeek V4.1 Flash through OpenRouter to summarize and group videos before the daily Slack digest.

Each video gets a viewing preview: three short sentences, up to 65 words, covering the topic, a concrete detail, and what the viewer can learn. The goal is to quickly decide which videos to watch.

## Setup

```fish
uv sync --all-extras --frozen
cp .env.example .env
```

Set `SLACK_WEBHOOK_URL` in `.env`. The daily service sources `~/.ssh/apify.sh` and `~/.ssh/openrouter-aura.sh`, which must export `APIFY_API_KEY` and `OPENROUTER_API_KEY`, respectively. Restrict those scripts to the account owner with `chmod 600`. Never commit credentials.

```fish
uv run python -m yt_digest --init
./scripts/run-digest.sh --dry-run
```

`--dry-run` prints messages instead of posting to Slack. It still fetches videos and stores summaries in the configured database, and uses paid APIs. For isolated QA, pass `--config` pointing at a config with a copied database.

## Configuration

`config.yaml` selects the OpenRouter model and request timeout, the Apify server timeout and per-video charge cap, the database path, and the Slack webhook environment variable. Channels live in SQLite, with initial channels defined in `yt_digest/init_channels.py`.

The transcript source is explicitly `pintostudio/youtube-transcript-scraper` on Apify, using English captions only. It does not request paid speech transcription or AI summaries. The summary model is explicitly `deepseek/deepseek-v4.1-flash`, served by DeepInfra with OpenRouter provider failover disabled. The same model groups summaries by topic. NotebookLM cookies and Claude Code login are no longer required.

A live caption download of the reported video on September 22, 2026 cost $0.01. The configured $0.05 cap bounds each per-video Apify run, not the total daily batch; model usage is billed separately by OpenRouter. Caption behavior and pricing are documented by [Apify](https://apify.com/pintostudio/youtube-transcript-scraper); model pricing is published by [OpenRouter](https://openrouter.ai/deepseek/deepseek-v4.1-flash).

## Failure handling

A video is marked processed only after a successful Slack post. Failed caption downloads, empty responses, model errors, and oversized transcripts remain pending for the next daily run. The service exits unsuccessfully if any summaries failed, while still delivering summaries that succeeded. Videos without usable English captions also remain pending, since an empty scraper response cannot reliably distinguish missing captions from upstream blocking.

The pipeline no longer posts `Summary unavailable` or permanently exhausts videos after three service failures. Historical failure counts are retained but no longer exclude pending videos. Previously posted history is untouched. Full transcripts are sent without silent truncation; transcripts above 500,000 characters remain pending with an explicit log message.

## Ubuntu deployment

The app runs on `ssh ubuntu-desktop` in `~/work/yt-digest`; its database is `~/.yt-digest/data.db`. Install the service after placing the credential scripts and Slack webhook on that host:

```fish
chmod +x scripts/run-digest.sh
mkdir -p ~/.config/systemd/user
cp deploy/yt-digest.service ~/.config/systemd/user/yt-digest.service
systemctl --user daemon-reload
systemctl --user enable --now yt-digest.timer
systemctl --user list-timers yt-digest.timer
```

Keep the existing daily timer. The service pulls its checked-out branch using `git pull --ff-only` before each run. If deploying a reviewed PR branch before merge, keep it tracking that remote branch; after the PR is merged, explicitly return the checkout to `main`:

```fish
cd ~/work/yt-digest
git switch main
git pull --ff-only
```

Logs are in `journalctl --user -u yt-digest.service` and `~/.yt-digest/yt-digest.log`. The one-hour service timeout accommodates sequential hosted caption downloads. Check that a run is inactive before changing its checkout.

## Testing

```fish
uv run pytest -q
```
