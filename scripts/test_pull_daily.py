#!/usr/bin/env python3
"""Offline tests for build_daily_row / _bb_high_low (no network, plain asserts).
Run: .venv/bin/python scripts/test_pull_daily.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pull_garmin import build_daily_row, _bb_high_low  # noqa: E402

COLS = ["date", "steps", "body_battery_high", "body_battery_low", "stress_avg",
        "activity_names", "activity_minutes"]

# Full realistic day: bb via values array, two activities (typeKey + name fallback)
row = build_daily_row(
    "2025-05-01",
    {"totalSteps": 8500},
    {"charged": 50, "drained": 40, "bodyBatteryValuesArray": [[0, 30], [1, 80], [2, 45]]},
    {"avgStressLevel": 33},
    [{"activityType": {"typeKey": "running"}, "duration": 1800},
     {"activityName": "力量训练", "duration": 900}],
)
assert list(row.keys()) == COLS, f"column order broken: {list(row.keys())}"
assert row["steps"] == 8500
assert row["body_battery_high"] == 80 and row["body_battery_low"] == 30
assert row["stress_avg"] == 33
assert row["activity_names"] == "running|力量训练"
assert row["activity_minutes"] == 45

# Direct-key body battery variants
assert _bb_high_low({"max": 90, "min": 20}) == (90, 20)
assert _bb_high_low({"highestBatteryLevel": 77, "lowestBatteryLevel": 11}) == (77, 11)
assert _bb_high_low({}) == ("", "")

# Empty everything → empty cells, never crash
row = build_daily_row("2025-05-02", {}, {}, {}, [])
assert row == {"date": "2025-05-02", "steps": "", "body_battery_high": "",
               "body_battery_low": "", "stress_avg": "", "activity_names": "",
               "activity_minutes": ""}

# Garbage shapes → empty cells, never crash
row = build_daily_row("2025-05-03", None, None, None, [None, "junk"])
assert row["steps"] == "" and row["activity_names"] == ""

print("All tests passed.")
