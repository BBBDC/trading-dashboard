#!/usr/bin/env python3
"""
backtest_audit/test_monthly_engine.py
=====================================
Unit-Tests fuer L1 (Open/Close-Split), L2 (Driftende Gewichte),
L3 (Reiner Cash-Monat ohne taegliches Rebalancing), L6 (Erstes Signal vor Start).
"""

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from monthly_engine import run_monthly_allocation


class TestMonthlyEngineFixes(unittest.TestCase):
    def _synthetic_data(self):
        # 5 Handelstage: 2008-02-29 (vor Start), 2008-03-03..06 (Monat 1), 2008-04-01 (Monat 2)
        dates = ["2008-02-29", "2008-03-03", "2008-03-04", "2008-03-05", "2008-04-01"]
        rf = [0.0001] * 5
        # Asset A steigt am Open(03-03) um +10%, dann Open->Close +10%
        series = {
            "A": {
                "o": [100.0, 110.0, 121.0, 121.0, 121.0],
                "h": [100.0, 121.0, 121.0, 121.0, 121.0],
                "l": [100.0, 110.0, 121.0, 121.0, 121.0],
                "c": [100.0, 121.0, 121.0, 121.0, 121.0],
            }
        }
        return {"dates": dates, "rf_daily": rf, "series": series}

    def test_l3_all_cash_month_no_daily_rebalance(self):
        data = self._synthetic_data()
        # Immer 0% allokieren -> nur am 2008-03-03 (erste Allokation) und 2008-04-01 (Monat 2) darf rebalanced werden!
        res = run_monthly_allocation(data, ["A"], lambda t: {"A": 0.0}, start_date="2008-03-03", end_date="2008-04-01", cost_bps=10.0)
        self.assertEqual(res["rebal_count"], 2)
        self.assertEqual(res["cash_months"], 2)
        # Excess return bei 100% Cash == 0.0 jeden Tag!
        for ex in res["excess_rets"]:
            self.assertAlmostEqual(ex, 0.0, places=9)

    def test_l1_l6_open_close_split_and_first_signal(self):
        data = self._synthetic_data()
        # Signal am 2008-02-29 (vor Start): 100% in A -> wird am Open(2008-03-03) zu 110.0 gekauft!
        # Daher darf der Close->Open Sprung (100->110) NICHT mitgenommen werden, nur Open->Close (110->121 = +10%) minus 5bp!
        res = run_monthly_allocation(data, ["A"], lambda t: {"A": 1.0}, start_date="2008-03-03", end_date="2008-03-05", cost_bps=10.0)
        expected_day0_total = (1.0 - 0.0005) * 1.10 - 1.0 + 0.5 * 0.0001
        expected_day0_ex = expected_day0_total - 0.0001
        self.assertAlmostEqual(res["excess_rets"][0], expected_day0_ex, places=8)


if __name__ == "__main__":
    unittest.main()
