# NBA Futures Tracker

Static GitHub Pages site that shows how each day of the NBA season moves
Polymarket's implied probabilities for end-of-season outcomes (champion,
conference champions, make playoffs, Rookie of the Year). Snapshotted
automatically every morning at 6:00 AM ET.

Site lives in `docs/` (GitHub Pages source). Snapshots are taken by GitHub
Actions (`.github/workflows/snapshot.yml`), which fetches prices, rebuilds the
JSON, commits, and pushes — Pages redeploys automatically. No manual steps.

Prices come from Polymarket's (polymarket.com) CLOB `prices-history` endpoint:
the last trade at or before 6:00 AM ET. That also means snapshots can be taken
retroactively for any past date.

## Manual usage

```bash
# Snapshot at the most recent 6:00 AM ET
python3 scripts/snapshot.py

# Snapshot at an arbitrary ET time
python3 scripts/snapshot.py --at "2026-09-10 06:00"

# Backfill the last N days of 6:00 AM ET snapshots (existing files skipped)
python3 scripts/snapshot.py --backfill 14

# Rebuild docs/data/data.json from all snapshot CSVs
python3 scripts/build_data.py
```

Then commit and push; GitHub Pages redeploys on push.

## Tracked series

Defined in `scripts/snapshot.py` (`EVENTS`, Polymarket event slugs) and ordered
in `scripts/build_data.py` (`SERIES_ORDER`, event titles). To add a series, add
its slug + title to those two lists. NBA MVP is currently not listed on
polymarket.com (only on the separate polymarket.us exchange) — add it when it
appears.

The four playoff-advancement series (conference semifinal/final berths) are
snapshotted daily but hidden from the site (`EXCLUDED_SERIES` in
`build_data.py`): as of Sep 2026 they trade too thinly for last-trade prices to
read as probabilities. Remove them from that set once liquidity arrives — the
accumulated history will appear retroactively.

## Snapshot labels

Daily 6 AM snapshots get automatic date labels ("Sep 18"). Optional
`snapshots/labels.json` overrides a label by snapshot id, e.g.
`{"2026-10-20_0600": "Opening Night"}`.

## Layout

- `snapshots/` — raw snapshot CSVs (`nba_markets_snapshot_YYYY-MM-DD_HHMM_EDT.csv`)
- `scripts/snapshot.py` — fetches one or more snapshots from Polymarket
- `scripts/build_data.py` — converts all snapshots to `docs/data/data.json`
- `docs/` — the site: `index.html`, `app.js`, `style.css`, `data/data.json`
- `.github/workflows/snapshot.yml` — daily 6 AM ET automation
