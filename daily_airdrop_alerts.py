#!/usr/bin/env python3
"""Daily crypto airdrop alert tool.

Fetches RSS/Atom feeds, detects new entries, and creates a daily digest.
Optionally sends the digest by email via SMTP.
"""

from __future__ import annotations

import json
import os
import smtplib
import ssl
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Iterable
from urllib.error import URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

DEFAULT_FEEDS = [
    # You can override with AIRDROP_FEEDS="https://example.com/feed,https://..."
    "https://airdrops.io/feed/",
    "https://www.reddit.com/r/airdrops/new/.rss",
]
STATE_FILE = Path(".airdrop_seen.json")
USER_AGENT = "daily-crypto-airdrop-alerts/1.0"


@dataclass(frozen=True)
class Entry:
    entry_id: str
    title: str
    link: str
    published_at: datetime | None
    source: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    candidates = [
        "%a, %d %b %Y %H:%M:%S %z",  # RSS pubDate
        "%Y-%m-%dT%H:%M:%S%z",       # Atom common
        "%Y-%m-%dT%H:%M:%SZ",        # UTC suffix
    ]

    for fmt in candidates:
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue

    return None


def _find_text(elem: ET.Element, tags: Iterable[str]) -> str | None:
    for tag in tags:
        found = elem.find(tag)
        if found is not None and found.text:
            return found.text.strip()
    return None


def fetch_xml(url: str) -> ET.Element:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=20) as response:
        payload = response.read()
    return ET.fromstring(payload)


def parse_feed(feed_url: str) -> list[Entry]:
    root = fetch_xml(feed_url)
    entries: list[Entry] = []

    if root.tag.endswith("rss") or root.find("channel") is not None:
        channel = root.find("channel")
        if channel is None:
            return entries

        for item in channel.findall("item"):
            title = _find_text(item, ["title"]) or "(untitled)"
            link = _find_text(item, ["link"]) or feed_url
            entry_id = _find_text(item, ["guid", "link", "title"]) or f"{feed_url}:{title}"
            published_raw = _find_text(item, ["pubDate", "date"])
            entries.append(
                Entry(
                    entry_id=entry_id,
                    title=title,
                    link=link,
                    published_at=parse_datetime(published_raw),
                    source=feed_url,
                )
            )
        return entries

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    atom_entries = root.findall("atom:entry", ns)
    for item in atom_entries:
        title = _find_text(item, ["{http://www.w3.org/2005/Atom}title"]) or "(untitled)"
        link = feed_url
        for link_el in item.findall("{http://www.w3.org/2005/Atom}link"):
            href = link_el.attrib.get("href")
            if href:
                link = href
                break

        entry_id = (
            _find_text(item, ["{http://www.w3.org/2005/Atom}id"]) or link or f"{feed_url}:{title}"
        )
        published_raw = _find_text(
            item,
            [
                "{http://www.w3.org/2005/Atom}published",
                "{http://www.w3.org/2005/Atom}updated",
            ],
        )
        entries.append(
            Entry(
                entry_id=entry_id,
                title=title,
                link=link,
                published_at=parse_datetime(published_raw),
                source=feed_url,
            )
        )
    return entries


def load_seen_ids() -> set[str]:
    if not STATE_FILE.exists():
        return set()
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return set(data)
    except json.JSONDecodeError:
        return set()


def save_seen_ids(seen_ids: set[str]) -> None:
    STATE_FILE.write_text(json.dumps(sorted(seen_ids), indent=2), encoding="utf-8")


def recent_and_new(entries: list[Entry], seen_ids: set[str], window_hours: int = 24) -> list[Entry]:
    cutoff = utc_now() - timedelta(hours=window_hours)
    results: list[Entry] = []
    for entry in entries:
        if entry.entry_id in seen_ids:
            continue
        if entry.published_at is not None and entry.published_at < cutoff:
            continue
        results.append(entry)
    return results


def render_digest(entries: list[Entry]) -> str:
    date_label = utc_now().strftime("%Y-%m-%d")
    lines = [f"Daily Crypto Airdrop Alerts ({date_label}, UTC)", ""]

    if not entries:
        lines.append("No new airdrop entries found in the last 24 hours.")
        return "\n".join(lines)

    lines.append(f"Found {len(entries)} new entries:")
    lines.append("")
    for idx, entry in enumerate(entries, start=1):
        published = entry.published_at.isoformat() if entry.published_at else "Unknown time"
        lines.append(f"{idx}. {entry.title}")
        lines.append(f"   - Source: {entry.source}")
        lines.append(f"   - Published: {published}")
        lines.append(f"   - Link: {entry.link}")
    return "\n".join(lines)


def maybe_send_email(subject: str, body: str) -> bool:
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    from_addr = os.getenv("ALERT_FROM")
    to_addr = os.getenv("ALERT_TO")

    required = [host, username, password, from_addr, to_addr]
    if not all(required):
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(body)

    context = ssl.create_default_context()
    with smtplib.SMTP(host, port) as server:
        server.starttls(context=context)
        server.login(username, password)
        server.send_message(msg)

    return True


def feed_list_from_env() -> list[str]:
    env_value = os.getenv("AIRDROP_FEEDS", "").strip()
    if not env_value:
        return DEFAULT_FEEDS
    feeds = [x.strip() for x in env_value.split(",") if x.strip()]
    return feeds or DEFAULT_FEEDS


def main() -> int:
    feeds = feed_list_from_env()
    seen_ids = load_seen_ids()

    all_entries: list[Entry] = []
    for feed in feeds:
        try:
            all_entries.extend(parse_feed(feed))
        except (URLError, TimeoutError, ET.ParseError) as exc:
            print(f"Warning: failed to parse {feed}: {exc}", file=sys.stderr)

    fresh_entries = recent_and_new(all_entries, seen_ids)
    digest = render_digest(fresh_entries)
    print(digest)

    seen_ids.update(entry.entry_id for entry in fresh_entries)
    save_seen_ids(seen_ids)

    subject = f"Daily Crypto Airdrop Alerts - {utc_now().strftime('%Y-%m-%d')}"
    emailed = maybe_send_email(subject=subject, body=digest)
    if emailed:
        print("\nEmail alert sent.")
    else:
        print("\nEmail not sent (set SMTP_* and ALERT_* environment variables).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
f
