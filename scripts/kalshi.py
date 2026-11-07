#!/usr/bin/env python3
"""Kalshi bid/ask midpoint snapshots; --backfill matches every Polymarket timestamp."""
import argparse
import csv
import math
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from snapshot import EASTERN, SNAPSHOT_DIR, parse_iso, request_json, snapshot_path

API = "https://external-api.kalshi.com/trade-api/v2"
EVENTS = dict(zip(
    ['KXNBA-27', 'KXNBAEAST-27', 'KXNBAWEST-27', 'KXNBAPLAYOFF-27', 'KXNBAROY-27', 'KXNBAMVP-27'],
    ['NBA: 2027 Champion', 'NBA: 2027 Eastern Conference Champion',
     'NBA: 2027 Western Conference Champion', 'NBA: Team to Make Playoffs',
     'NBA: 2026-27 Rookie of the Year', 'NBA: 2026-27 MVP']))
COLUMNS = ['requested_snapshot_utc', 'ticker', 'event_ticker', 'outcome', 'market_title',
           'market_open_time', 'market_close_time', 'candle_end_ts', 'data_status', 'yes_bid', 'yes_ask', 'midpoint']


def path_for(snapshot):
    return snapshot_path(snapshot).with_name(snapshot_path(snapshot).name.replace('nba_markets_', 'kalshi_nba_markets_'))


@lru_cache(maxsize=1)
def markets():
    def fetch(event):
        result, cursor = [], ''
        while True:
            payload = request_json(API + '/markets', {'event_ticker': event, 'limit': 1000, 'cursor': cursor})
            result.extend(m for m in payload['markets'] if m['event_ticker'] == event)
            cursor = payload.get('cursor')
            if not cursor:
                break
        if not result:
            raise ValueError(f'No markets returned for {event}')
        return result
    with ThreadPoolExecutor(max_workers=6) as pool:
        return sorted(sum(pool.map(fetch, EVENTS), []), key=lambda m: m['ticker'])


def midpoint(candle):
    bid = (candle or {}).get('yes_bid', {}).get('close_dollars')
    ask = (candle or {}).get('yes_ask', {}).get('close_dollars')
    if bid is None or ask is None:
        return None, None, None
    bid, ask = float(bid), float(ask)
    if not (math.isfinite(bid) and math.isfinite(ask) and 0 <= bid <= ask <= 1):
        raise ValueError(f'Invalid Kalshi quote: {bid}, {ask}')
    return bid, ask, (bid + ask) / 2


def take_snapshot(snapshot):
    from datetime import timezone
    path = path_for(snapshot)
    if path.exists():
        return None
    target = int(snapshot.timestamp())
    listed = markets()
    active = [m for m in listed if parse_iso(m.get('open_time'), float('inf')) <= target < parse_iso(m.get('close_time'), 0)]
    candles = {}
    for start in range(0, len(active), 60):
        chunk = active[start:start + 60]
        payload = request_json(API + '/markets/candlesticks', {
            'market_tickers': ','.join(m['ticker'] for m in chunk), 'start_ts': target - 60,
            'end_ts': target, 'period_interval': 1, 'include_latest_before_start': 'true'})
        returned = {item['market_ticker'] for item in payload['markets']}
        if returned != {m['ticker'] for m in chunk}:
            raise ValueError('Incomplete Kalshi candlestick response; no snapshot written')
        for item in payload['markets']:
            eligible = [c for c in item['candlesticks'] if int(c['end_period_ts']) <= target]
            candles[item['market_ticker']] = max(eligible, key=lambda c: c['end_period_ts'], default=None)
    rows = []
    for m in listed:
        candle = candles.get(m['ticker'])
        bid, ask, price = midpoint(candle)
        status = 'ok' if price is not None else ('not_open' if parse_iso(m.get('open_time'), float('inf')) > target else 'no_quote')
        rows.append(dict(zip(COLUMNS, [snapshot.astimezone(timezone.utc).isoformat(), m['ticker'], m['event_ticker'],
            m['yes_sub_title'], m['title'], m['open_time'], m['close_time'],
            candle['end_period_ts'] if candle else None, status, bid, ask, price])))
    path.parent.mkdir(exist_ok=True)
    temp = path.with_suffix('.tmp')
    with temp.open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(path)
    print(f"wrote {path.name}: {sum(r['data_status'] == 'ok' for r in rows)}/{len(rows)} quotes", flush=True)
    return path


if __name__ == '__main__':
    from build_data import snapshot_files
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backfill', action='store_true', required=True)
    parser.parse_args()
    for dt, _, _ in snapshot_files():
        take_snapshot(dt.replace(tzinfo=EASTERN))
