# NBA Futures Tracker

Static GitHub Pages site that shows how each day of the NBA season moves
Kalshi and Polymarket implied probabilities for end-of-season outcomes (champion,
conference champions, make playoffs, Rookie of the Year, MVP). Snapshotted
automatically every morning at 6:00 AM ET.

Site lives in `docs/` (GitHub Pages source). Snapshots are taken by GitHub
Actions (`.github/workflows/snapshot.yml`), which fetches prices, rebuilds the
JSON, commits, and pushes — Pages redeploys automatically. No manual steps.

Polymarket prices come from Polymarket's (polymarket.com) CLOB `prices-history` endpoint:
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

# Backfill Kalshi at every existing Polymarket timestamp (existing files skipped)
python3 scripts/kalshi.py --backfill

# Rebuild docs/data/data.json from all snapshot CSVs
python3 scripts/build_data.py
```

Then commit and push; GitHub Pages redeploys on push.

## Trigger a snapshot on GitHub now

Scheduled runs are often delayed. To run the snapshot workflow immediately
(works from any folder):

```bash
gh workflow run snapshot.yml --repo millxing/nba-futures-tracker
```

Once it finishes, pull the new commit into the local copy:

```bash
git -C ~/Dropbox/CC/NBA_Information pull
```

## Tracked series

Defined in `scripts/snapshot.py` (`EVENTS`, Polymarket event slugs) and ordered
in `scripts/build_data.py` (`SERIES_ORDER`, event titles). To add a series, add
its slug + title to those two lists. NBA MVP was added once it listed on
polymarket.com (Oct 2026); its history starts at the first snapshot after that.

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
- `scripts/snapshot.py` — fetches one or more snapshots from both exchanges
- `scripts/kalshi.py` — collects historical Kalshi midpoint quotes and backfills existing dates
- `scripts/build_data.py` — converts all snapshots to `docs/data/data.json`
- `docs/` — the site: `index.html`, `app.js`, `style.css`, `data/data.json`
- `.github/workflows/snapshot.yml` — daily 6 AM ET automation

## Team pages and favorites

The **Teams** tab groups each team's futures, MVP candidates, and Rookie of
the Year candidates. Team links use hash routes (for example `#teams/washington-wizards`),
so they work directly on GitHub Pages. Player award history follows the player;
team affiliations reflect the cached current roster, not historical rosters.

Star teams or individual markets from Teams, Daily Movers, or chart selections.
The **Favorites** tab includes all markets for saved teams plus individually
saved markets, deduplicated. Favorites use browser local storage, with no account
or cross-device sync. If storage is blocked, favorites work for the current visit.

`python3 scripts/update_rosters.py` refreshes `docs/data/rosters.json` from ESPN's
team roster API. The daily workflow refreshes it before rebuilding new snapshot
data. A failed or incomplete refresh preserves the last complete cache. Team
pages show its update time; unmatched candidates remain available in Daily
Movers and can still be favorited individually. Names are matched without case,
accents, or punctuation; LA Clippers is normalized to Los Angeles Clippers.

`scripts/roster_supplements.json` records sourced roster omissions (such as G League
assignments). Supplements apply only when the player is absent from every ESPN
roster, so an explicit new team from ESPN takes precedence. Review supplements
when affiliations change; each entry includes its verification date and source.

## Price sources and history

The global Kalshi / Polymarket / Average selector applies to Movers, Time Series,
Teams, and Favorites. Average is the equal-weight mean of the two prices and
requires both observations. Missing prices remain blank; no single-source fallback.
Movers resets to Average To % (latest probability), descending, on every open or refresh.
Switching sources preserves row order. Clicking a sort header, changing dates,
or filtering recalculates the order using the selected source. Teams and Favorites
keep their latest Average price order across source changes.

Kalshi snapshots use the historical YES bid/ask midpoint at or before each exact
Polymarket snapshot timestamp. Separate `kalshi_nba_markets_snapshot_*.csv` files
preserve quote values and candle timestamps. The initial backfill covers all 63
snapshots, September 5–November 6, 2026: 10,110 quotes across 162 contracts.
The 96 missing contract/date observations precede the opening of Kawhi Leonard's
MVP contract or Ryan Conwell's Rookie of the Year contract. No prices are invented
for those dates. Kalshi-only candidates are retained with stable IDs; Average is
blank wherever Polymarket has no corresponding observation. Explicit 2027 event
mappings prevent prices from different seasons being combined.

Daily automation collects both exchanges via `snapshot.py`. Reruns independently
skip each existing source file. The data build fails if a matching Kalshi snapshot
is missing. Existing Polymarket history and favorite IDs are preserved.

Validation: `python3 -m unittest discover -s tests`. For the UI regression check,
install `jsdom` outside the repository and run
`NODE_PATH=/path/to/node_modules node tests/check_ui.cjs`.
