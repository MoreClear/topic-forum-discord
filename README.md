# topic-forum-discord

Posts a message to a Discord channel whenever a new topic appears in the
[Newspeak House 2026-27 forum](https://topic.forum/f/newspeak-house-2026-27).

## How it works

`notify.py` runs every 15 minutes on GitHub Actions. It fetches the forum's
Atom feed, posts any topic whose ID is not yet in `state.json`, and commits
the updated `state.json` back to the repository.

Topics are matched by ID, not by date, because editing a topic moves it to the
top of the feed.

## Setup

1. Create a webhook in the Discord channel (Edit Channel → Integrations → Webhooks).
2. Add the webhook URL as a repository secret named `DISCORD_WEBHOOK_URL`.
3. Push to GitHub. The workflow starts on its own schedule.

## Running locally

Preview what would be posted, without posting:

```powershell
$env:DRY_RUN = "1"; python notify.py
```

Post for real:

```powershell
$env:DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/..."; python notify.py
```

To make the bot treat a topic as new again, remove its ID from `state.json`.
