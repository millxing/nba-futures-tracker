import csv
import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import kalshi
import build_data


class KalshiTests(unittest.TestCase):
    def test_midpoint_and_missing_quote(self):
        self.assertEqual(kalshi.midpoint({'yes_bid': {'close_dollars': '0'}, 'yes_ask': {'close_dollars': '.02'}}), (0, .02, .01))
        self.assertEqual(kalshi.midpoint({'yes_bid': {'close_dollars': '.5'}}), (None, None, None))
        with self.assertRaises(ValueError):
            kalshi.midpoint({'yes_bid': {'close_dollars': '.7'}, 'yes_ask': {'close_dollars': '.6'}})

    def test_matching_aliases(self):
        self.assertEqual(build_data.name_key('LA Clippers'), build_data.name_key('Los Angeles Clippers'))
        self.assertEqual(build_data.name_key('Nikola Jokić'), build_data.name_key('Nikola Jokic'))

    def test_complete_backfill_and_no_future_quotes(self):
        files = build_data.snapshot_files()
        for dt, _, _ in files:
            target = dt.replace(tzinfo=kalshi.EASTERN)
            with kalshi.path_for(target).open() as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), len({r['ticker'] for r in rows}))
            self.assertEqual(set(r['event_ticker'] for r in rows), set(kalshi.EVENTS))
            for row in rows:
                self.assertEqual(datetime.fromisoformat(row['requested_snapshot_utc']).timestamp(), target.timestamp())
                if row['data_status'] == 'ok':
                    self.assertLessEqual(int(row['candle_end_ts']), target.timestamp())
                    self.assertAlmostEqual(float(row['midpoint']), (float(row['yes_bid']) + float(row['yes_ask'])) / 2)
                else:
                    self.assertEqual(row['data_status'], 'not_open')
                    self.assertGreater(datetime.fromisoformat(row['market_open_time']).timestamp(), target.timestamp())
        data = json.loads(Path(build_data.OUT_PATH).read_text())
        self.assertEqual(len(data['snapshots']), len(files))
        for m in data['markets']:
            for prices in m['prices'].values():
                self.assertEqual(len(prices), len(files))
                self.assertTrue(all(p is None or 0 <= p <= 100 for p in prices))

    def test_incomplete_api_response_writes_nothing(self):
        target = datetime(2026, 9, 5, 6, tzinfo=kalshi.EASTERN)
        market = {'ticker': 'KXNBA-27-BOS', 'open_time': '2026-06-01T00:00:00Z', 'close_time': '2027-06-01T00:00:00Z'}
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'snapshot.csv'
            with patch.object(kalshi, 'path_for', return_value=path), patch.object(kalshi, 'markets', return_value=[market]), patch.object(kalshi, 'request_json', return_value={'markets': []}):
                with self.assertRaises(ValueError):
                    kalshi.take_snapshot(target)
            self.assertFalse(path.exists())


if __name__ == '__main__':
    unittest.main()
