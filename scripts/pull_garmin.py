#!/usr/bin/env python3
"""
Pull sleep + recovery data from Garmin Connect using the saved login token.

    .venv/bin/python scripts/pull_garmin.py [days]   # default 90

Writes:
  data/garmin_sleep.csv     one row per night (joinable with ai_usage.csv on `night`)
  data/garmin_raw/<d>.json  raw responses, so no data is lost if a field is renamed

The `night` key uses the same 04:00 cutoff as the AI extractor: bedtime past
midnight still belongs to the previous evening, so the two datasets line up.
"""
from __future__ import annotations
import csv
import json
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import garminconnect

ROOT = Path(__file__).resolve().parent.parent
TOKENSTORE = ROOT / ".garmin_tokens"
RAW = ROOT / "data" / "garmin_raw"
OUT = ROOT / "data" / "garmin_sleep.csv"
ACT_OUT = ROOT / "data" / "garmin_exercise.csv"
NIGHT_CUTOFF_HOUR = 4


def dig(d, *paths, default=None):
    """Return the first path that resolves. Each path is a tuple of keys."""
    for path in paths:
        cur = d
        ok = True
        for k in path:
            if isinstance(cur, dict) and k in cur and cur[k] is not None:
                cur = cur[k]
            else:
                ok = False
                break
        if ok:
            return cur
    return default


def local_clock(ms: int | None) -> datetime | None:
    """Garmin *Local epoch-ms already carry the local offset; read as UTC to
    recover local wall-clock time."""
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).replace(tzinfo=None)


def night_key(dt: datetime) -> tuple[str, float]:
    h = dt.hour + dt.minute / 60
    if dt.hour < NIGHT_CUTOFF_HOUR:
        return (dt - timedelta(days=1)).date().isoformat(), h + 24
    return dt.date().isoformat(), h


def hhmm(dt: datetime | None) -> str:
    return dt.strftime("%H:%M") if dt else ""


def secs_to_h(s) -> str:
    return round(s / 3600, 2) if isinstance(s, (int, float)) else ""


def pull_exercise(g, days: int) -> None:
    """One call for the whole span; aggregate workouts per `night` (same 04:00
    cutoff), so a daytime workout attaches to the sleep it precedes that evening.
    Writes garmin_exercise.csv — empty (header only) until she resumes training."""
    start = (date.today() - timedelta(days=days)).isoformat()
    end = date.today().isoformat()
    try:
        acts = g.get_activities_by_date(start, end) or []
    except Exception as e:  # noqa: BLE001
        print(f"⚠ activities pull failed: {e}")
        acts = []

    by_night: dict[str, dict] = {}
    for a in acts:
        st = None
        raw = a.get("startTimeLocal") or ""
        try:
            st = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        night, dec = night_key(st)
        b = by_night.setdefault(night, {"date": st.date().isoformat(), "w": []})
        b["w"].append({
            "type": (a.get("activityType") or {}).get("typeKey"),
            "hour": dec,
            "dur_min": (a.get("duration") or 0) / 60,
            "avg_hr": a.get("averageHR"),
            "max_hr": a.get("maxHR"),
            "intensity": (a.get("moderateIntensityMinutes") or 0)
                         + (a.get("vigorousIntensityMinutes") or 0),
        })

    cols = ["night", "exercise_date", "exercised", "n_workouts", "exercise_types",
            "exercise_dur_min", "exercise_last_hour", "exercise_avg_hr",
            "exercise_max_hr", "exercise_intensity_min"]
    rows = []
    for night, b in by_night.items():
        ws = b["w"]
        hrs = [w["avg_hr"] for w in ws if isinstance(w["avg_hr"], (int, float))]
        mxs = [w["max_hr"] for w in ws if isinstance(w["max_hr"], (int, float))]
        rows.append({
            "night": night,
            "exercise_date": b["date"],
            "exercised": 1,
            "n_workouts": len(ws),
            "exercise_types": "|".join(sorted({w["type"] for w in ws if w["type"]})),
            "exercise_dur_min": round(sum(w["dur_min"] for w in ws), 1),
            "exercise_last_hour": round(max(w["hour"] for w in ws), 2),  # latest that day
            "exercise_avg_hr": round(sum(hrs) / len(hrs), 1) if hrs else "",
            "exercise_max_hr": max(mxs) if mxs else "",
            "exercise_intensity_min": sum(w["intensity"] for w in ws),
        })
    rows.sort(key=lambda r: r["night"])
    with open(ACT_OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(f"Pulled {len(acts)} activities → {len(rows)} workout-nights.  Wrote {ACT_OUT}")


def main() -> int:
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 90
    try:
        g = garminconnect.Garmin()
        g.login(str(TOKENSTORE))
    except Exception as e:  # noqa: BLE001
        print(f"✗ Could not resume Garmin session: {e}")
        print("  Run scripts/garmin_login.py first (in a real Terminal).")
        return 1

    RAW.mkdir(parents=True, exist_ok=True)
    rows = []
    today = date.today()
    got = 0
    for i in range(1, days + 1):
        d = today - timedelta(days=i)
        cd = d.isoformat()
        bundle = {}
        for name, fn in (
            ("sleep", lambda: g.get_sleep_data(cd)),
            ("rhr", lambda: g.get_rhr_day(cd)),
            ("hrv", lambda: g.get_hrv_data(cd)),
            ("stress", lambda: g.get_all_day_stress(cd)),
        ):
            try:
                bundle[name] = fn()
            except Exception as e:  # noqa: BLE001
                bundle[name] = {"_error": str(e)}
            time.sleep(0.25)
        (RAW / f"{cd}.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=1))

        s = bundle.get("sleep") or {}
        dto = s.get("dailySleepDTO") or {}
        start = local_clock(dig(dto, ("sleepStartTimestampLocal",)))
        end = local_clock(dig(dto, ("sleepEndTimestampLocal",)))
        total = dig(dto, ("sleepTimeSeconds",))
        if start is None and not total:
            continue  # no sleep recorded that night (watch off) — skip
        got += 1
        night, bed_dec = night_key(start) if start else (cd, "")
        rows.append({
            "night": night,
            "garmin_calendar_date": dig(dto, ("calendarDate",), default=cd),
            "bedtime": hhmm(start),
            "waketime": hhmm(end),
            "bedtime_decimal": round(bed_dec, 3) if isinstance(bed_dec, float) else "",
            "total_sleep_h": secs_to_h(total),
            "deep_h": secs_to_h(dig(dto, ("deepSleepSeconds",))),
            "light_h": secs_to_h(dig(dto, ("lightSleepSeconds",))),
            "rem_h": secs_to_h(dig(dto, ("remSleepSeconds",))),
            "awake_h": secs_to_h(dig(dto, ("awakeSleepSeconds",))),
            "sleep_score": dig(dto, ("sleepScores", "overall", "value")),
            "resting_hr": dig(s, ("restingHeartRate",), (), default=None)
                          or dig(bundle.get("rhr") or {}, ("restingHeartRate",),
                                 ("allMetrics", "metricsMap",
                                  "WELLNESS_RESTING_HEART_RATE", 0, "value")),
            "hrv_last_night": dig(bundle.get("hrv") or {},
                                  ("hrvSummary", "lastNightAvg"))
                              or dig(s, ("avgOvernightHrv",)),
            "avg_stress": dig(bundle.get("stress") or {}, ("avgStressLevel",)),
            "max_stress": dig(bundle.get("stress") or {}, ("maxStressLevel",)),
            "respiration_avg": dig(dto, ("averageRespirationValue",)),
            "spo2_avg": dig(dto, ("averageSpO2Value",)),
        })

    rows.sort(key=lambda r: r["night"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["night"])
        w.writeheader()
        w.writerows(rows)

    span = f"{rows[0]['night']} .. {rows[-1]['night']}" if rows else "—"
    print(f"Pulled {got} nights of sleep (of {days} requested).  span {span}")
    print(f"Wrote {OUT}")
    print(f"Raw   {RAW}/ (kept for schema fixes)")

    pull_exercise(g, days)  # workouts → garmin_exercise.csv (empty until she trains)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
