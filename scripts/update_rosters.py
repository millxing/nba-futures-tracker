#!/usr/bin/env python3
"""Refresh cached ESPN team rosters. Preserve the last complete cache on failure."""
import json
import os
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/data/rosters.json'
BASE = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams'


def normalize(name):
    return ''.join(c for c in unicodedata.normalize('NFKD', name).casefold() if c.isalnum())


def fetch(url):
    with urlopen(url, timeout=30) as response:
        return json.load(response)


def roster(entry):
    team = entry['team']
    name = team['displayName'].replace('LA Clippers', 'Los Angeles Clippers')
    url = f"{BASE}/{team['id']}/roster"
    data = fetch(url)
    players = [p['displayName'] for p in data['athletes']]
    if not players:
        raise ValueError(f'Empty roster: {name}')
    return {'id': team['abbreviation'].lower(), 'name': name, 'players': players, 'source': url}


def main():
    try:
        teams = fetch(BASE + '?limit=100')['sports'][0]['leagues'][0]['teams']
        with ThreadPoolExecutor(max_workers=6) as pool:
            rosters = sorted(pool.map(roster, teams), key=lambda t: t['name'])
        if len(rosters) != 30:
            raise ValueError(f'Expected 30 teams, got {len(rosters)}')
        owners = {}
        for team in rosters:
            for player in team['players']:
                key = normalize(player)
                if key in owners and owners[key] != team['id']:
                    raise ValueError(f'Ambiguous roster membership: {player}')
                owners[key] = team['id']
        supplements = json.loads((ROOT / 'scripts/roster_supplements.json').read_text())
        applied = []
        for entry in supplements:
            if normalize(entry['player']) not in owners:
                team = next(t for t in rosters if t['name'] == entry['team'])
                team['players'].append(entry['player'])
                applied.append(entry)
        data = {'updated': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'), 'teams': rosters, 'supplements': applied}
        tmp = OUT.with_suffix('.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
        os.replace(tmp, OUT)
        print(f'Updated {len(rosters)} team rosters')
    except Exception as error:
        if not OUT.exists():
            raise
        print(f'WARNING: keeping cached rosters: {error}', file=sys.stderr)


if __name__ == '__main__':
    main()
