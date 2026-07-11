#!/usr/bin/env python3
"""
Extract per-night AI-usage signal from local Claude Code + Codex logs.

The single most-correlated variable in 鸭哥's sleep analysis was the *time of the
last AI use that evening*. This script reconstructs that (and late-night intensity
+ a concurrency proxy) from logs already on this machine — no wearable needed.

Output: data/ai_usage.csv, one row per "night" keyed by a 04:00-local cutoff so
that a 01:30 session counts toward the previous evening (the night it wrecked).

Timestamps are converted to the machine's LOCAL timezone automatically, so
"last AI use" is real wall-clock evening time wherever you are.
"""
from __future__ import annotations
import csv, glob, json, os, re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOME = Path.home()
CLAUDE_GLOB = str(HOME / ".claude" / "projects" / "**" / "*.jsonl")
CODEX_ROLLOUTS = str(HOME / ".codex" / "archived_sessions" / "rollout-*.jsonl")
CODEX_HISTORY = HOME / ".codex" / "history.jsonl"
TOKENSTEP_JSON = (HOME / "Library" / "Application Support" / "TokenStep"
                  / "data" / "usage.json")
OUT = Path(__file__).resolve().parent.parent / "data" / "ai_usage.csv"

NIGHT_CUTOFF_HOUR = 4  # events before 04:00 local belong to the previous evening
TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}")


def parse_iso(s: str) -> datetime | None:
    if not isinstance(s, str):
        return None
    s = s.strip()
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone()  # -> system local tz


def night_key(local_dt: datetime) -> tuple[str, float]:
    """Return (night_date_iso, lateness_decimal). lateness carries past midnight:
    01:30 -> 25.5 so ordering/comparison across midnight is monotonic."""
    h = local_dt.hour + local_dt.minute / 60 + local_dt.second / 3600
    if local_dt.hour < NIGHT_CUTOFF_HOUR:
        night = (local_dt - timedelta(days=1)).date()
        lateness = h + 24
    else:
        night = local_dt.date()
        lateness = h
    return night.isoformat(), lateness


class NightAgg:
    __slots__ = ("n", "n_claude", "n_codex", "last", "after20", "after22",
                 "after24", "late_sessions", "first")

    def __init__(self):
        self.n = self.n_claude = self.n_codex = 0
        self.last = -1.0
        self.first = 99.0
        self.after20 = self.after22 = self.after24 = 0
        self.late_sessions: set[str] = set()

    def add(self, lateness: float, source: str, session: str | None):
        self.n += 1
        if source == "codex":
            self.n_codex += 1
        else:
            self.n_claude += 1
        self.last = max(self.last, lateness)
        self.first = min(self.first, lateness)
        if lateness >= 20:
            self.after20 += 1
            if session:
                self.late_sessions.add(session)
        if lateness >= 22:
            self.after22 += 1
        if lateness >= 24:
            self.after24 += 1


def decimal_to_hhmm(d: float) -> str:
    if d < 0:
        return ""
    h = int(d) % 24
    m = int(round((d - int(d)) * 60))
    if m == 60:
        h, m = (h + 1) % 24, 0
    nxt = " (+1)" if d >= 24 else ""
    return f"{h:02d}:{m:02d}{nxt}"


def scan_claude(nights: dict[str, NightAgg]) -> dict:
    files = glob.glob(CLAUDE_GLOB, recursive=True)
    events = 0
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or '"timestamp"' not in line:
                        continue
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    dt = parse_iso(d.get("timestamp", ""))
                    if dt is None:
                        continue
                    key, lateness = night_key(dt)
                    sess = d.get("sessionId") or d.get("session_id")
                    nights.setdefault(key, NightAgg()).add(lateness, "claude", sess)
                    events += 1
        except (OSError, UnicodeDecodeError):
            continue
    return {"files": len(files), "events": events}


def _last_ts_in_file(path: str) -> datetime | None:
    """Best-effort last real timestamp inside a Codex rollout jsonl."""
    last = None
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if '"timestamp"' not in line and not TS_RE.search(line):
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                for k in ("timestamp", "ts", "time", "created_at"):
                    dt = parse_iso(d.get(k, "")) if isinstance(d, dict) else None
                    if dt:
                        last = dt if last is None else max(last, dt)
                        break
    except OSError:
        return None
    return last


def scan_codex(nights: dict[str, NightAgg]) -> dict:
    files = glob.glob(CODEX_ROLLOUTS)
    sessions = 0
    used_mtime = 0
    for f in files:
        base = os.path.basename(f)
        m = re.search(r"rollout-(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2})", base)
        start = None
        if m:
            # filename encodes start as YYYY-MM-DDTHH-MM-SS -> rebuild ISO
            raw = m.group(1)
            start = parse_iso(f"{raw[:13]}:{raw[14:16]}:{raw[17:19]}")
        end = _last_ts_in_file(f)
        if end is None:
            try:
                end = datetime.fromtimestamp(os.path.getmtime(f)).astimezone()
                used_mtime += 1
            except OSError:
                end = None
        session_id = base
        for marker in (start, end):
            if marker is None:
                continue
            key, lateness = night_key(marker)
            nights.setdefault(key, NightAgg()).add(lateness, "codex", session_id)
        sessions += 1
    return {"sessions": sessions, "end_from_mtime": used_mtime}


def tokenstep_by_night() -> dict[str, tuple[int, int]]:
    """night_iso -> (tokens_day, tokens_evening) from the TokenStep app's store.

    tokens_day: TokenStep's daily total for the night's calendar date (how hard
    the day's AI work was). tokens_evening: hourly-rhythm tokens in 20:00-24:00
    of that date plus 00:00-04:00 of the next — same cutoff as night_key().
    Missing app / missing date -> absent key (caller writes "", not a fake 0).
    """
    if not TOKENSTEP_JSON.exists():
        return {}
    try:
        with open(TOKENSTEP_JSON, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return {}
    day_total = {r["date"]: int(r.get("total_tokens") or 0)
                 for r in d.get("daily", []) if r.get("date")}
    buckets = {r["date"]: {b.get("hour"): int(b.get("tokens") or 0)
                           for b in r.get("buckets", [])}
               for r in d.get("rhythms", []) if r.get("date")}
    out = {}
    for date_iso, total in day_total.items():
        nxt = (datetime.fromisoformat(date_iso) + timedelta(days=1)).date().isoformat()
        eve = sum(buckets.get(date_iso, {}).get(h, 0) for h in (20, 21, 22, 23)) \
            + sum(buckets.get(nxt, {}).get(h, 0) for h in range(NIGHT_CUTOFF_HOUR))
        out[date_iso] = (total, eve)
    return out


def main():
    nights: dict[str, NightAgg] = {}
    c = scan_claude(nights)
    x = scan_codex(nights)
    tokens = tokenstep_by_night()

    # Fill a continuous date range so zero-AI nights (the "good sleep" controls)
    # appear explicitly — the regression needs the contrast, not just busy nights.
    rows = []
    if nights:
        d0 = datetime.fromisoformat(min(nights)).date()
        d1 = datetime.fromisoformat(max(nights)).date()
        day = d0
        while day <= d1:
            key = day.isoformat()
            a = nights.get(key)
            if a is None:
                rows.append({
                    "date": key, "last_ai_decimal": "", "last_ai_local": "",
                    "n_ai_events": 0, "n_claude": 0, "n_codex": 0,
                    "n_after_2000": 0, "n_after_2200": 0, "n_after_0000": 0,
                    "distinct_late_convos": 0,
                })
            else:
                rows.append({
                    "date": key,
                    "last_ai_decimal": round(a.last, 3) if a.last >= 0 else "",
                    "last_ai_local": decimal_to_hhmm(a.last),
                    "n_ai_events": a.n,
                    "n_claude": a.n_claude,
                    "n_codex": a.n_codex,
                    "n_after_2000": a.after20,
                    "n_after_2200": a.after22,
                    "n_after_0000": a.after24,
                    # distinct conversations active after 20:00. NOTE: inflated by
                    # subagent/workflow fan-out — a weak concurrency proxy, not a
                    # count of human parallel threads.
                    "distinct_late_convos": len(a.late_sessions),
                })
            day += timedelta(days=1)

    for row in rows:
        t = tokens.get(row["date"])
        row["tokens_day"] = t[0] if t else ""
        row["tokens_evening"] = t[1] if t else ""

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["date"])
        w.writeheader()
        w.writerows(rows)

    span = f"{rows[0]['date']} .. {rows[-1]['date']}" if rows else "—"
    print(f"Claude: {c['files']} files, {c['events']} events")
    print(f"Codex : {x['sessions']} sessions "
          f"({x['end_from_mtime']} used file-mtime as session end)")
    print(f"Nights: {len(rows)}  span {span}")
    print(f"Wrote  {OUT}")


if __name__ == "__main__":
    main()
