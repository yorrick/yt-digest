# yt-digest

## Adding a YouTube Channel

When the user asks to add a YouTube channel:

1. **Resolve channel info** from the URL or handle:
   - Fetch the YouTube channel page with `http --follow --print=b GET "<url>"`
   - Extract the handle: `grep -o '"vanityChannelUrl":"[^"]*"'`
   - Extract the name: `grep -o '"channelMetadataRenderer":{[^}]*}'` and parse the `"title"` field
   - Extract/verify the channel ID: `grep -o '"externalId":"[^"]*"'`
2. **Insert into the SQLite database on the Ubuntu desktop** (the app runs there):
   ```
   ssh ubuntu-desktop "python3 -c \"
   import sqlite3
   conn = sqlite3.connect('/home/yorrick/.yt-digest/data.db')
   conn.execute('INSERT INTO channels (name, youtube_handle, channel_id, rss_url, active) VALUES (?, ?, ?, ?, ?)',
       ('<name>', '<handle>', '<channel_id>', 'https://www.youtube.com/feeds/videos.xml?channel_id=<channel_id>', 1))
   conn.commit()
   conn.close()
   \""
   ```
   Note: `sqlite3` CLI is not installed on the Ubuntu desktop, so use `python3 -c` instead.
3. **Add the channel to `INITIAL_CHANNELS`** in `yt_digest/init_channels.py` so it persists across DB resets.

## Infrastructure

- The app runs on the Ubuntu desktop (`ssh ubuntu-desktop`)
- SQLite database lives at `~/.yt-digest/data.db` on the Ubuntu desktop
- Config at `config.yaml` (no channels config there — channels are in the DB)
