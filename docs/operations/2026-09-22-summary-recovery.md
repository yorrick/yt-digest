# Summary recovery, September 22, 2026

Production revision 151bc30 tried NotebookLM, then Claude Code. The Google session had expired. A direct Ubuntu probe returned HTTP 200 for the YouTube watch/player requests and HTTP 429 for `/api/timedtext`, so Claude generation was never reached. Three failed runs caused link-only posts to be marked processed.

The replacement uses `pintostudio/youtube-transcript-scraper` for English captions and `deepseek/deepseek-v4.1-flash` through OpenRouter, pinned to DeepInfra. The broader `streamers/youtube-scraper` passed one test but failed repeated tests with internal transport errors; it is not used. Direct DeepSeek hosting was excluded by the existing OpenRouter privacy policy, which was left unchanged. A DeepInfra request succeeded. No automatic provider or model fallback was added.

An Ubuntu run on a copy of the production database generated real summaries for `71-8fJIGi34` (the reported video), `bA8WeHYmJko` (the caption-block reproduction), and `AgzVxj_ztiA` (a short). It produced 5,977 characters of formatted messages, clustered the three summaries, asserted zero Slack calls, and left their processed timestamps unset. The local suite passes 72 tests. Historical processed rows remain untouched.

After deployment, the actual service wrapper completed a production `--dry-run` successfully. It fetched one new RSS video and generated all 16 pending summaries with DeepSeek, then formatted 16 messages. They are cached in the production database for the next daily delivery. A comparison with the backup verified that every previously processed timestamp was unchanged, and all 16 pending rows still have unset processed timestamps.

## Cross-AI review

Reviewer: Claude Code, Claude Opus 5, high effort. These three commands completed successfully with exit status 0; they reviewed the supplied plan or source payloads, with external tools disabled. The files are local investigation artifacts in `/tmp/yt-digest-investigation`.

```fish
claude -p --model claude-opus-5 --effort high --tools '' < /tmp/yt-digest-investigation/fix-plan.txt > /tmp/yt-digest-investigation/fix-plan-review.txt
claude -p --model claude-opus-5 --effort high --tools '' < /tmp/yt-digest-investigation/implementation-review-input.txt > /tmp/yt-digest-investigation/implementation-review-output.txt
claude -p --model claude-opus-5 --effort high --tools '' < /tmp/yt-digest-investigation/final-review-input.txt > /tmp/yt-digest-investigation/final-review-output.txt
```

Verified and fixed: ambiguous empty captions must remain retryable; one failed or oversized video must not block successful summaries; delivery failures must cause a failed service result; database marking errors must not be swallowed as Slack errors; malformed cluster names and non-integer indices need validation. Regression tests reproduced the outage exhaustion, duplicate posts, swallowed delivery error, invalid index, and invalid name problems before their respective fixes.

Rejected after checking: the no-content branch already propagates delivery errors; canonical watch URLs are guaranteed by `VideoInfo.url`; the systemd service already declares `Type=oneshot` and is a user unit; adding a new automatic clustering fallback conflicts with the user's policy. Clustering API failures remain visible and recoverable, with summaries already stored for the next run. Deployment must use a tracking branch, never a detached checkout.

## Deployment state

The reviewed `fix/deepseek-digest-summaries` branch is deployed to the Ubuntu checkout and tracks its remote branch. PR #3 remains open and unmerged: https://github.com/yorrick/yt-digest/pull/3. The existing daily timer is enabled and uses the installed `deploy/yt-digest.service`; systemd unit verification and all 72 tests passed on Ubuntu. The pre-deployment database backup is `~/.yt-digest/data-before-deepseek-20260922.db`. The service sources owner-only API credential scripts and permits an hour for caption downloads. Return production to `main` only after the PR is merged with the user's authorization; commands are in the README. Do not restart the service to send test Slack messages; use `--dry-run` for verification.
