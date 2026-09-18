#!/usr/bin/env python3
"""Fetch a Polymarket NBA futures snapshot and write it to snapshots/ as CSV.

Prices come from the CLOB prices-history endpoint, so a snapshot can be taken
for any past timestamp (the last trade price at or before the target time).

Usage:
  python3 scripts/snapshot.py                     # snapshot at the most recent 6:00 AM ET
  python3 scripts/snapshot.py --at "2026-09-10 06:00"
  python3 scripts/snapshot.py --backfill 14       # last 14 days of 6:00 AM ET snapshots
  python3 scripts/snapshot.py --cron              # exit quietly unless the current ET hour is 6

Existing snapshot files are never overwritten (reruns are no-ops).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_DIR = ROOT / "snapshots"
GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
EASTERN = ZoneInfo("America/New_York")
SNAPSHOT_HOUR = 6  # 6:00 AM ET

EVENTS = [
    "nba-2027-champion",
    "nba-2027-eastern-conference-champion-20260624155838911",
    "nba-2027-western-conference-champion-20260624160106318",
    "nba-team-to-make-playoffs-20260708210742372",
    "nba-playoffs-team-to-advance-to-eastern-conference-semifinals",
    "nba-playoffs-team-to-advance-to-western-conference-semifinals",
    "nba-playoffs-team-to-advance-to-eastern-conference-finals",
    "nba-playoffs-team-to-advance-to-western-conference-finals",
    "nba-2026-27-rookie-of-the-year-20260624161716143",
]

COLUMNS = [
    "requested_snapshot_et", "requested_snapshot_timezone", "requested_snapshot_utc",
    "observed_at_utc", "observation_lag_seconds", "event_id", "event_slug", "event_title",
    "market_id", "condition_id", "market_slug", "market_question", "outcome", "token_id",
    "data_status", "price", "market_open_time", "market_close_time",
]


def request_json(url: str, query: dict[str, Any] | None = None, attempts: int = 4) -> Any:
    if query:
        url += "?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "NBASnapshot/1.0"})
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(0.5 * (2 ** attempt))
    raise RuntimeError(f"Request failed for {url}: {last_error}")


def parse_iso(value: Any, fallback: float) -> float:
    if not value:
        return fallback
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return fallback


def parse_array(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def fetch_event(slug: str, target_epoch: int) -> list[dict[str, Any]]:
    event = request_json(f"{GAMMA}/events/slug/{urllib.parse.quote(slug)}")
    found: list[dict[str, Any]] = []
    for market in event.get("markets", []):
        opened = parse_iso(market.get("startDate") or market.get("createdAt") or event.get("startDate"), 0)
        closed = parse_iso(market.get("endDate") or event.get("endDate"), float("inf"))
        outcomes = parse_array(market.get("outcomes"))
        token_ids = parse_array(market.get("clobTokenIds"))
        yes_index = next((i for i, o in enumerate(outcomes) if str(o).lower() == "yes"), 0)
        if opened <= target_epoch < closed and yes_index < len(token_ids):
            found.append({**market, "_event_id": event.get("id"), "_event_slug": slug,
                          "_event_title": event.get("title") or slug, "_yes_token": token_ids[yes_index],
                          "_yes_outcome": outcomes[yes_index] if yes_index < len(outcomes) else "Yes"})
    return found


def fetch_history(token: str, target_epoch: int) -> tuple[str, dict[str, Any] | None, str | None]:
    """Last trade price at or before target. Widening windows / coarser fidelity."""
    received_response = False
    last_error: str | None = None
    for seconds, fidelity in ((3600, 1), (86400, 15), (7 * 86400, 60), (30 * 86400, 180)):
        try:
            payload = request_json(f"{CLOB}/prices-history", {
                "market": token, "startTs": target_epoch - seconds, "endTs": target_epoch, "fidelity": fidelity,
            })
            received_response = True
            eligible = [p for p in payload.get("history", []) if int(p.get("t", 0)) <= target_epoch]
            point = max(eligible, key=lambda item: int(item.get("t", 0)), default=None)
            if point:
                return token, point, None
        except RuntimeError as error:
            last_error = str(error)
    return token, None, None if received_response else last_error


def snapshot_path(snapshot: datetime) -> Path:
    return SNAPSHOT_DIR / f"nba_markets_snapshot_{snapshot.strftime('%Y-%m-%d_%H%M')}_{snapshot.tzname()}.csv"


def take_snapshot(snapshot: datetime) -> Path | None:
    path = snapshot_path(snapshot)
    if path.exists():
        print(f"exists, skipping: {path.name}")
        return None
    target_epoch = int(snapshot.timestamp())

    markets: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(fetch_event, slug, target_epoch) for slug in EVENTS]
        for future in as_completed(futures):
            for market in future.result():
                markets[str(market.get("id"))] = market
    market_list = sorted(markets.values(), key=lambda m: (m["_event_slug"], m.get("groupItemTitle") or m.get("question") or ""))
    if not market_list:
        raise RuntimeError("No open markets found at target time; nothing written.")

    history: dict[str, dict[str, Any] | None] = {}
    errors: set[str] = set()
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(fetch_history, str(m["_yes_token"]), target_epoch) for m in market_list]
        for future in as_completed(futures):
            token, point, error = future.result()
            history[token] = point
            if error:
                errors.add(token)
    if errors:
        raise RuntimeError(f"History requests failed for {len(errors)} markets; no snapshot written.")

    requested_et = snapshot.strftime("%Y-%m-%d %H:%M")
    requested_utc = snapshot.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    rows = []
    for market in market_list:
        token = str(market["_yes_token"])
        point = history.get(token)
        observed_epoch = int(point["t"]) if point else None
        rows.append({
            "requested_snapshot_et": requested_et, "requested_snapshot_timezone": snapshot.tzname(),
            "requested_snapshot_utc": requested_utc,
            "observed_at_utc": datetime.fromtimestamp(observed_epoch, timezone.utc).isoformat().replace("+00:00", "Z") if observed_epoch else "",
            "observation_lag_seconds": target_epoch - observed_epoch if observed_epoch else "",
            "event_id": market.get("_event_id"), "event_slug": market.get("_event_slug"),
            "event_title": market.get("_event_title"), "market_id": market.get("id"),
            "condition_id": market.get("conditionId"), "market_slug": market.get("slug"),
            "market_question": market.get("question"),
            "outcome": market.get("groupItemTitle") or market.get("_yes_outcome"), "token_id": token,
            "data_status": "ok" if point else "no_history",
            "price": point.get("p") if point else "",
            "market_open_time": market.get("startDate"), "market_close_time": market.get("endDate"),
        })

    SNAPSHOT_DIR.mkdir(exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    ok = sum(1 for r in rows if r["data_status"] == "ok")
    print(f"wrote {path.name}: {len(rows)} markets ({ok} with prices)")
    return path


def most_recent_snapshot_time(now_et: datetime) -> datetime:
    target = now_et.replace(hour=SNAPSHOT_HOUR, minute=0, second=0, microsecond=0)
    if target > now_et:
        target -= timedelta(days=1)
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--at", help='Target time in ET, e.g. "2026-09-10 06:00"')
    parser.add_argument("--backfill", type=int, metavar="N", help="Take the last N days of 6:00 AM ET snapshots")
    parser.add_argument("--cron", action="store_true",
                        help=f"Exit quietly unless the current ET hour is {SNAPSHOT_HOUR} (for UTC schedulers)")
    args = parser.parse_args()

    now_et = datetime.now(EASTERN)
    if args.cron and now_et.hour != SNAPSHOT_HOUR:
        print(f"cron guard: ET hour is {now_et.hour}, not {SNAPSHOT_HOUR}; exiting")
        return

    if args.at:
        targets = [datetime.strptime(args.at, "%Y-%m-%d %H:%M").replace(tzinfo=EASTERN)]
    elif args.backfill:
        latest = most_recent_snapshot_time(now_et)
        targets = [latest - timedelta(days=i) for i in range(args.backfill - 1, -1, -1)]
    else:
        targets = [most_recent_snapshot_time(now_et)]

    wrote = 0
    for target in targets:
        if take_snapshot(target) is not None:
            wrote += 1
    print(f"done: {wrote} snapshot(s) written, {len(targets) - wrote} skipped")


if __name__ == "__main__":
    main()
