#!/usr/bin/env python3
"""
Convert the browser-scraped Garmin sleep CSV (data/garmin_web_raw.csv) into the
schema analyze.py expects (data/garmin_sleep.csv), keyed by the same 04:00 "night"
cutoff as the AI-usage extractor so the two datasets line up.

Bedtime datetime is reconstructed wake-anchored: wake is on the Garmin date D;
bedtime is on D unless its clock is later than wake's (then it was the prior
evening). night_key then anchors each sleep to the evening it belongs to.
"""
from __future__ import annotations
import csv
import re
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "garmin_web_raw.csv"
OUT = ROOT / "data" / "garmin_sleep.csv"
NIGHT_CUTOFF_HOUR = 4


def dur_to_h(s: str):
    if not s:
        return None
    h = re.search(r"(\d+)\s*h", s)
    m = re.search(r"(\d+)\s*m", s)
    return round((int(h.group(1)) if h else 0) + (int(m.group(1)) if m else 0) / 60, 3)


def clock_to_hm(s: str):
    """'3:36 AM' -> (3,36); '11:09 PM' -> (23,9); '12:04 AM' -> (0,4)."""
    m = re.match(r"(\d{1,2}):(\d{2})\s*([AP]M)", s.strip())
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2)), m.group(3)
    if ap == "AM":
        h = 0 if h == 12 else h
    else:
        h = 12 if h == 12 else h + 12
    return h, mi


def night_key(dt: datetime):
    h = dt.hour + dt.minute / 60
    if dt.hour < NIGHT_CUTOFF_HOUR:
        return (dt - timedelta(days=1)).date().isoformat(), round(h + 24, 3)
    return dt.date().isoformat(), round(h, 3)


def main() -> int:
    rows_out = []
    with open(SRC, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if not r.get("score"):
                continue  # night with no sleep recorded
            D = date.fromisoformat(r["date"])
            bed_hm = clock_to_hm(r["bed"]) if r.get("bed") else None
            wake_hm = clock_to_hm(r["wake"]) if r.get("wake") else None
            night, bed_dec, is_nap = r["date"], "", ""
            if bed_hm and wake_hm:
                bed_dt = datetime(D.year, D.month, D.day, bed_hm[0], bed_hm[1])
                wake_dt = datetime(D.year, D.month, D.day, wake_hm[0], wake_hm[1])
                if bed_dt >= wake_dt:  # bedtime was the previous evening
                    bed_dt -= timedelta(days=1)
                night, bed_dec = night_key(bed_dt)
                is_nap = 1 if 5 <= bed_dt.hour < 18 else ""
            rows_out.append({
                "night": night,
                "garmin_date": r["date"],
                "bedtime": r.get("bed", ""),
                "bedtime_decimal": bed_dec,
                "is_nap": is_nap,
                "total_sleep_h": dur_to_h(r.get("dur", "")),
                "deep_h": dur_to_h(r.get("deep", "")),
                "light_h": dur_to_h(r.get("light", "")),
                "rem_h": dur_to_h(r.get("rem", "")),
                "sleep_score": r.get("score") or "",
                "resting_hr": r.get("rhr") or "",
                "hrv_last_night": r.get("hrv") or "",
                "avg_stress": r.get("stress") or "",
            })

    rows_out.sort(key=lambda x: x["night"])
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows_out[0].keys()))
        w.writeheader()
        w.writerows(rows_out)
    naps = sum(1 for r in rows_out if r["is_nap"])
    print(f"Converted {len(rows_out)} nights with sleep ({naps} daytime naps flagged)")
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
