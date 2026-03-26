# Daily Crypto Airdrop Alerts

A lightweight Python script that builds a **daily digest of new crypto airdrops** from RSS/Atom feeds.

## What it does

- Pulls entries from a list of airdrop-related feeds.
- Filters to entries published in the last 24 hours.
- Deduplicates using a local state file (`.airdrop_seen.json`).
- Prints a daily digest to stdout.
- Optionally sends the digest by email with SMTP.

## Quick start

```bash
python3 daily_airdrop_alerts.py
```

## Configuration

### 1) Feed sources

Set custom sources with `AIRDROP_FEEDS` (comma-separated URLs):

```bash
export AIRDROP_FEEDS="https://example.com/feed.xml,https://www.reddit.com/r/airdrops/new/.rss"
```

If not set, the script uses built-in defaults.

### 2) Optional email delivery

Set these environment variables to enable email alerts:

- `SMTP_HOST`
- `SMTP_PORT` (default `587`)
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `ALERT_FROM`
- `ALERT_TO`

Example:

```bash
export SMTP_HOST="smtp.gmail.com"
export SMTP_PORT="587"
export SMTP_USERNAME="you@example.com"
export SMTP_PASSWORD="app-password"
export ALERT_FROM="you@example.com"
export ALERT_TO="you@example.com"
```

## Schedule it daily (cron)

Run every day at 09:00 UTC:

```bash
0 9 * * * cd /workspace/Daily-crypto-airdrop-alerts && /usr/bin/python3 daily_airdrop_alerts.py >> alerts.log 2>&1
```

## Notes

- Some sources may block automated requests. If a feed fails, the script logs a warning and continues.
- On first run, all recent items (last 24h) are treated as new.
