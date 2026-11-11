"""Tests for deterministic benchmark reporting."""

from __future__ import annotations

import unittest

from benchmarks.run_benchmarks import run_benchmarks


class BenchmarkTests(unittest.TestCase):
    def test_synthetic_cases_report_savings_and_retain_all_designated_phrases(self) -> None:
        report = run_benchmarks()

        self.assertEqual(len(report["cases"]), 3)
        self.assertGreater(report["totals"]["original_tokens"], 0)
        self.assertGreaterEqual(report["totals"]["saved_tokens"], 0)
        self.assertEqual(report["totals"]["required_phrases"], 9)
        self.assertEqual(report["totals"]["retained_phrases"], 9)
        self.assertEqual(report["totals"]["retention_percent"], 100.0)
        self.assertTrue(all(not case["missing_phrases"] for case in report["cases"]))
        self.assertIn("not semantic", report["methodology"])


if __name__ == "__main__":
    unittest.main()
