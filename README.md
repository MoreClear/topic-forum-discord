# topic-forum-discord

Posts a message to a Discord channel whenever a new topic appears in the
[Newspeak House 2026-27 forum](https://topic.forum/f/newspeak-house-2026-27).

## How it works

`notify.py` runs every 15 minutes on GitHub Actions. It fetches the forum's
Atom feed, posts any topic whose ID is not yet in `state.json`, and commits
the updated `state.json` back to the repository.

Each message has a footer such as `Topic #155 · Joshua Becker's 4th`: the
topic's number in the forum and among its author's topics, counted by publish
time. The numbers come from the forum's public JSON export. If the export
cannot be read, the topic is posted without the footer.

The footer also shows the topic's hearts on the forum, such as `❤️ 7`, once it
has at least one. `state.json` keeps the Discord message ID of each topic the
bot posts, and every run reads the export and edits the messages whose count
has changed. A count is therefore as old as the last run. A message that was
deleted, or that sits in a channel the webhook has since left, cannot be
edited and is dropped from tracking.

A second footer line gives the topic's dates in UK time, such as
`First published 25 Jul 2026 22:10 · Last edited 15 Oct 2026 01:21`. "Last
edited" appears only for edits made after publishing, and is updated on the
message along with the hearts. The forum keeps a topic's original publish date
if it is hidden and later shown again, so such a topic can arrive with an old
date and a low topic number.

Topics are matched by ID, not by date, because editing a topic moves it to the
top of the feed. The feed lists only the 50 most recently changed topics, so
`state.json` records every topic in the export as seen, not only those in the
feed. Otherwise editing an older topic would bring it into the feed as new.

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
