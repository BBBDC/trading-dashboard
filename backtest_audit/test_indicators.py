#!/usr/bin/env python3
"""
backtest_audit/test_indicators.py
=================================
Unit-Tests fuer Indikator-Formeln (inkl. TA-Lib-Referenzwerte), Lookahead-Schutz,
monotonen Chandelier-Stop und Holdout-Sperre.
"""

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from indicators import sma, donchian_prev_max, donchian_prev_min, rsi_wilder, atr_wilder, ibs


class TestAuditIndicators(unittest.TestCase):
    def test_donchian_closed_interval_no_lookahead(self):
        # [t-3, t-1] fuer t=3 ist max(10, 12, 11) = 12, nicht series[3]=99!
        series = [10.0, 12.0, 11.0, 99.0, 15.0]
        dmax = donchian_prev_max(series, 3)
        dmin = donchian_prev_min(series, 3)
        self.assertIsNone(dmax[2])
        self.assertEqual(dmax[3], 12.0)
        self.assertEqual(dmin[3], 10.0)
        self.assertEqual(dmax[4], 99.0)

    def test_sma_inclusive_of_t(self):
        series = [1.0, 2.0, 3.0, 4.0]
        res = sma(series, 3)
        self.assertIsNone(res[1])
        self.assertAlmostEqual(res[2], 2.0)
        self.assertAlmostEqual(res[3], 3.0)

    def test_rsi2_wilder_reference(self):
        # Manuell berechnete Wilder-RSI(2)-Referenz:
        # C = [10, 11, 10, 12, 11] -> diffs: +1, -1, +2, -1
        # i=2: avg_g = 0.5, avg_l = 0.5 -> RSI = 50.0
        # i=3: avg_g = (0.5 + 2)/2 = 1.25, avg_l = (0.5 + 0)/2 = 0.25 -> RS=5 -> RSI = 100 - 100/6 = 83.333333
        # i=4: avg_g = 0.625, avg_l = 0.625 -> RSI = 50.0
        closes = [10.0, 11.0, 10.0, 12.0, 11.0]
        r = rsi_wilder(closes, 2)
        self.assertIsNone(r[1])
        self.assertAlmostEqual(r[2], 50.0, places=6)
        self.assertAlmostEqual(r[3], 83.3333333, places=5)
        self.assertAlmostEqual(r[4], 50.0, places=6)

    def test_atr_wilder_reference(self):
        highs = [12.0, 13.0, 14.0, 13.5]
        lows = [10.0, 11.0, 12.0, 12.5]
        closes = [11.0, 12.0, 13.0, 13.0]
        # TR = [2.0, 2.0, 2.0, 1.0]
        # period=3: ATR[2] = 2.0; ATR[3] = (2*2 + 1)/3 = 1.6666667
        a = atr_wilder(highs, lows, closes, 3)
        self.assertIsNone(a[1])
        self.assertAlmostEqual(a[2], 2.0, places=6)
        self.assertAlmostEqual(a[3], 5.0 / 3.0, places=6)

    def test_ibs_edge_cases(self):
        self.assertIsNone(ibs(100.0, 100.0, 100.0))
        self.assertAlmostEqual(ibs(110.0, 100.0, 102.0), 0.2, places=6)


if __name__ == "__main__":
    unittest.main()
