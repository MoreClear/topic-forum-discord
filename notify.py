"""Post new topic.forum topics to a Discord channel via a webhook.

Run on a schedule. Each run fetches the forum's Atom feed, posts any topic
whose ID has not been seen before, and records it in state.json.

Environment variables:
  DISCORD_WEBHOOK_URL  the webhook to post to (required unless DRY_RUN is set)
  DRY_RUN              if set to 1, print what would be posted instead
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

FEED_URL = "https://topic.forum/api/forums/newspeak-house-2026-27/feed.atom"
EXPORT_URL = "https://topic.forum/api/forums/newspeak-house-2026-27/export"
STATE_FILE =Path(__file__).parent / "state.json"
USER_AGENT = "topic-forum-discord/1.0 (+https://topic.forum)"
EXCERPT_LENGTH = 300
EMBED_COLOUR = 0x5865F2
ATOM = {"a": "http://www.w3.org/2005/Atom"}


class TextExtractor(HTMLParser):
    """Collect the text of an HTML fragment, dropping the tags."""

    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in ("p", "br", "li", "div"):
            self.parts.append(" ")


def excerpt(html_text):
    parser = TextExtractor()
    parser.feed(html_text or "")
    text = " ".join("".join(parser.parts).split())
    if len(text) <= EXCERPT_LENGTH:
        return text
    return text[:EXCERPT_LENGTH].rsplit(" ", 1)[0] + "…"


def load_state():
    if not STATE_FILE.exists():
        return None
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def fetch_feed(etag):
    """Return (xml_bytes, etag), or (None, etag) if the feed is unchanged."""
    headers = {"User-Agent": USER_AGENT}
    if etag:
        headers["If-None-Match"] = etag
    request = urllib.request.Request(FEED_URL, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read(), response.headers.get("ETag")
    except urllib.error.HTTPError as error:
        if error.code == 304:
            return None, etag
        raise


def parse_entries(xml_bytes):
    entries = []
    for node in ET.fromstring(xml_bytes).findall("a:entry", ATOM):
        link = node.find("a:link[@rel='alternate']", ATOM)
        entries.append(
            {
                "id": node.findtext("a:id", namespaces=ATOM),
                "title": node.findtext("a:title", default="(untitled)", namespaces=ATOM),
                "url": link.get("href") if link is not None else None,
                "author": node.findtext("a:author/a:name", default="", namespaces=ATOM),
                "published": node.findtext("a:published", namespaces=ATOM),
                "content": node.findtext("a:content", default="", namespaces=ATOM),
            }
        )
    return entries


def ordinal(number):
    if 10 <= number % 100 <= 20:
        return f"{number}th"
    return f"{number}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(number % 10, 'th')}"


def fetch_counts():
    """Return {feed ID: footer text} giving each topic's place in the forum.

    A topic's number is its position by publish time, in the forum and among
    its author's topics. Returns {} if the export cannot be read, so that a
    problem here never stops a topic being posted.
    """
    request = urllib.request.Request(EXPORT_URL, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            topics = json.loads(response.read())["topics"]
        topics.sort(key=lambda t: t["publishedAt"])
        counts = {}
        per_host = {}
        for number, topic in enumerate(topics, start=1):
            host = topic["hostId"]
            per_host[host] = per_host.get(host, 0) + 1
            counts[f"urn:uuid:{topic['id']}"] = (
                f"Topic #{number} · {topic['hostName']}'s {ordinal(per_host[host])}"
            )
        return counts
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Could not read the export, posting without counts: {error}")
        return {}


def build_payload(entry, footer=None):
    embed = {
        "title": entry["title"][:256],
        "description": excerpt(entry["content"]),
        "color": EMBED_COLOUR,
    }
    if entry["url"]:
        embed["url"] = entry["url"]
    if entry["author"]:
        embed["author"] = {"name": entry["author"][:256]}
    if entry["published"]:
        embed["timestamp"] = entry["published"]
    if footer:
        embed["footer"] = {"text": footer[:2048]}
    # allowed_mentions stops topic text such as @everyone from pinging anyone.
    return {"embeds": [embed], "allowed_mentions": {"parse": []}}


def post_to_discord(webhook_url, payload):
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
    for _ in range(5):
        request = urllib.request.Request(webhook_url, data=body, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30):
                return
        except urllib.error.HTTPError as error:
            if error.code != 429:
                raise
            retry_after = json.loads(error.read()).get("retry_after", 5)
            time.sleep(float(retry_after) + 0.5)
    raise RuntimeError("Discord kept rate limiting the webhook")


def main():
    dry_run = os.environ.get("DRY_RUN") == "1"
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not dry_run and not webhook_url:
        sys.exit("DISCORD_WEBHOOK_URL is not set")

    state = load_state()
    first_run = state is None
    if first_run:
        state = {"etag": None, "seen": []}

    xml_bytes, etag = fetch_feed(state["etag"])
    if xml_bytes is None:
        print("Feed unchanged")
        return

    entries = parse_entries(xml_bytes)
    seen = set(state["seen"])

    if first_run:
        # Record everything already on the forum so the channel is not flooded.
        state = {"etag": etag, "seen": [e["id"] for e in entries]}
        save_state(state)
        print(f"First run: recorded {len(entries)} existing topics, posted nothing")
        return

    new_entries = [e for e in entries if e["id"] not in seen]
    new_entries.sort(key=lambda e: e["published"] or "")
    print(f"{len(new_entries)} new topic(s)")

    counts = fetch_counts() if new_entries else {}

    for entry in new_entries:
        payload = build_payload(entry, counts.get(entry["id"]))
        if dry_run:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            continue
        post_to_discord(webhook_url, payload)
        print(f"Posted: {entry['title']}")
        # Save after each post so a later failure does not cause a repost.
        state["seen"].append(entry["id"])
        save_state(state)
        time.sleep(1)

    if not dry_run:
        # Only keep the ETag once every new topic has been posted.
        state["etag"] = etag
        save_state(state)


if __name__ == "__main__":
    main()
