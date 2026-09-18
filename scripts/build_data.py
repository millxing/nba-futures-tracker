#!/usr/bin/env python3
"""Convert snapshot CSV files into docs/data/data.json for the site.

Usage: python3 scripts/build_data.py
Reads every snapshots/nba_markets_snapshot_*.csv, sorted chronologically by the
datetime in the filename. Optional snapshots/labels.json maps snapshot id ->
friendly label, e.g. {"2026-09-18_0600": "Opening Night"}; daily snapshots
default to a date label.
"""

import csv
import glob
import json
import os
import re
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT_DIR = os.path.join(ROOT, "snapshots")
OUT_PATH = os.path.join(ROOT, "docs", "data", "data.json")

# Display order: team series first (macro -> playoff rounds), then individuals.
SERIES_ORDER = [
    "NBA: 2027 Champion",
    "NBA: 2027 Eastern Conference Champion",
    "NBA: 2027 Western Conference Champion",
    "NBA: Team to Make Playoffs",
    "NBA Playoffs: Team to advance to Eastern Conference Semifinals",
    "NBA Playoffs: Team to advance to Western Conference Semifinals",
    "NBA Playoffs: Team to advance to Eastern Conference Finals",
    "NBA Playoffs: Team to advance to Western Conference Finals",
    "NBA: 2026-27 Rookie of the Year",
]
TEAM_SERIES = set(SERIES_ORDER[:8])

# Snapshotted but still too illiquid for last-trade prices to read as
# probabilities (sparse trades bouncing off the 50c book seed). Data keeps
# accruing in snapshots/; remove from this set once trading is real.
EXCLUDED_SERIES = {
    "NBA Playoffs: Team to advance to Eastern Conference Semifinals",
    "NBA Playoffs: Team to advance to Western Conference Semifinals",
    "NBA Playoffs: Team to advance to Eastern Conference Finals",
    "NBA Playoffs: Team to advance to Western Conference Finals",
}

FNAME_RE = re.compile(
    r"nba_markets_snapshot_(\d{4}-\d{2}-\d{2})_(\d{4})_E[SD]T\.csv$"
)


def snapshot_files():
    files = []
    for path in glob.glob(os.path.join(SNAPSHOT_DIR, "nba_markets_snapshot_*.csv")):
        base = os.path.basename(path)
        m = FNAME_RE.search(base)
        if not m:
            print(f"WARNING: skipping unrecognized filename {base}", file=sys.stderr)
            continue
        dt = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H%M")
        files.append((dt, f"{m.group(1)}_{m.group(2)}", path))
    files.sort()
    return files


def auto_label(dt):
    # Daily 6 AM snapshots get a plain date label; anything else keeps the time.
    if dt.hour == 6 and dt.minute == 0:
        return dt.strftime("%b %-d")
    hour = dt.strftime("%I:%M %p").lstrip("0")
    return f"{dt.strftime('%b %-d')}, {hour}"


def full_time(dt):
    hour = dt.strftime("%I:%M %p").lstrip("0")
    return f"{dt.strftime('%b %-d')}, {hour} ET"


def read_snapshot(path):
    """Return {market_id: row-dict} for one snapshot CSV."""
    out = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            if not row.get("market_id"):
                continue
            if row["event_title"].strip() in EXCLUDED_SERIES:
                continue
            price = row.get("price")
            out[row["market_id"]] = {
                "series": row["event_title"].strip(),
                "name": row["outcome"].strip(),
                "question": row["market_question"].strip(),
                "open_time": row.get("market_open_time") or "",
                "price": round(float(price) * 100, 1)
                if row.get("data_status") == "ok" and price
                else None,
            }
    return out


# New CLOB books are seeded at ~50c before any real trading, and prices-history
# reports that seed as if it were a price. Strip a market's leading run of
# ~50 prices when it sits within days of the market's open date and the first
# real price is a 20+ point cliff away; a market genuinely trading near 50
# drifts, it doesn't jump.
SEED_WINDOW = 7 * 86400  # seconds after market open
SEED_BAND = (49.0, 51.0)
SEED_JUMP = 20.0


def strip_seed_prices(prices, snap_epochs, open_time):
    try:
        opened = datetime.fromisoformat(open_time.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return prices
    first = next((i for i, p in enumerate(prices) if p is not None), None)
    if first is None:
        return prices
    run_end = first
    while (
        run_end < len(prices)
        and prices[run_end] is not None
        and SEED_BAND[0] <= prices[run_end] <= SEED_BAND[1]
        and snap_epochs[run_end] - opened <= SEED_WINDOW
    ):
        run_end += 1
    if run_end == first:
        return prices
    nxt = next((prices[i] for i in range(run_end, len(prices)) if prices[i] is not None), None)
    if nxt is None or abs(nxt - prices[first]) < SEED_JUMP:
        return prices
    return [None] * run_end + prices[run_end:]


def main():
    files = snapshot_files()
    if not files:
        sys.exit("No snapshot files found in snapshots/")

    labels = {}
    labels_path = os.path.join(SNAPSHOT_DIR, "labels.json")
    if os.path.exists(labels_path):
        with open(labels_path) as f:
            labels = json.load(f)

    snapshots = []
    per_snapshot = []
    for dt, sid, path in files:
        entry = labels.get(sid)
        if isinstance(entry, str):
            entry = {"label": entry}
        elif entry is None:
            entry = {}
        snapshots.append(
            {
                "id": sid,
                "label": entry.get("label", auto_label(dt)),
                "time": full_time(dt),
                "partial": bool(entry.get("partial")),
                "et": dt.strftime("%Y-%m-%d %H:%M"),
            }
        )
        per_snapshot.append(read_snapshot(path))
        print(f"  {sid}: {len(per_snapshot[-1])} markets")

    # Collect all markets across snapshots; metadata from latest appearance.
    meta = {}
    for snap in per_snapshot:
        for mid, row in snap.items():
            meta[mid] = row

    series_seen = {m["series"] for m in meta.values()}
    unknown = series_seen - set(SERIES_ORDER)
    if unknown:
        print(f"WARNING: series not in SERIES_ORDER (appended): {unknown}", file=sys.stderr)
    series = [s for s in SERIES_ORDER if s in series_seen] + sorted(unknown)
    series_rank = {s: i for i, s in enumerate(series)}

    snap_epochs = [
        datetime.strptime(s["et"], "%Y-%m-%d %H:%M").replace(tzinfo=EASTERN).timestamp()
        for s in snapshots
    ]
    markets = []
    stripped = 0
    for mid, m in meta.items():
        prices = [snap.get(mid, {}).get("price") for snap in per_snapshot]
        cleaned = strip_seed_prices(prices, snap_epochs, m["open_time"])
        if cleaned is not prices:
            stripped += 1
        markets.append(
            {
                "id": mid,
                "series": m["series"],
                "name": m["name"],
                "question": m["question"],
                "prices": cleaned,
            }
        )
    if stripped:
        print(f"  stripped seed prices from {stripped} newly-listed markets")
    markets.sort(key=lambda m: (series_rank[m["series"]], m["name"]))

    data = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "snapshots": snapshots,
        "series": series,
        "teamSeries": sorted(TEAM_SERIES & series_seen, key=series_rank.get),
        "markets": markets,
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(data, f, separators=(",", ":"))

    print(f"Wrote {OUT_PATH}")
    print(f"  snapshots: {len(snapshots)}")
    print(f"  series:    {len(series)}")
    print(f"  markets:   {len(markets)}")


if __name__ == "__main__":
    main()
