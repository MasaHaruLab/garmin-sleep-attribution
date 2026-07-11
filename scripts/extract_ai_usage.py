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

# Presence rule (CEO 2026-07-11): autonomous runs after she leaves (黑屏) are not
# her exposure. Each night's valid window = her FIRST human message that day →
# her LAST human message that night, plus a short wrap-up grace while she
# watches the final response land. Everything outside the window is ignored.
PRESENCE_GRACE = timedelta(minutes=30)


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


def is_human_msg(d: dict) -> bool:
    """A transcript line she actually typed — not tool results, not subagent
    sidechains, not harness meta messages that merely wear the user role."""
    if d.get("type") != "user" or d.get("isSidechain") or d.get("isMeta"):
        return False
    if "toolUseResult" in d:
        return False
    msg = d.get("message") or {}
    content = msg.get("content")
    if isinstance(content, list):
        return not any(isinstance(b, dict) and b.get("type") == "tool_result"
                       for b in content)
    return isinstance(content, str) and bool(content.strip())


def scan_claude() -> tuple[list, list, dict]:
    """Single walk -> (events, human message times, stats).

    Events are (dt, session) for every timestamped line; human times feed the
    presence windows. Only Claude Code messages define presence — Codex runs
    are dispatched automation, their prompts don't prove she was at the desk.
    """
    files = glob.glob(CLAUDE_GLOB, recursive=True)
    events: list[tuple[datetime, str | None]] = []
    human_times: list[datetime] = []
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
                    events.append((dt, d.get("sessionId") or d.get("session_id")))
                    if is_human_msg(d):
                        human_times.append(dt)
        except (OSError, UnicodeDecodeError):
            continue
    return events, human_times, {"files": len(files), "events": len(events),
                                 "human_msgs": len(human_times)}


def build_windows(human_times: list[datetime]) -> dict[str, tuple[datetime, datetime]]:
    """night_iso -> (first human msg, last human msg + grace) per night key."""
    windows: dict[str, tuple[datetime, datetime]] = {}
    for dt in human_times:
        key, _ = night_key(dt)
        cur = windows.get(key)
        windows[key] = (min(cur[0], dt), max(cur[1], dt)) if cur else (dt, dt)
    return {k: (a, b + PRESENCE_GRACE) for k, (a, b) in windows.items()}


def in_window(dt: datetime, windows: dict[str, tuple[datetime, datetime]]) -> bool:
    key, _ = night_key(dt)
    win = windows.get(key)
    return bool(win and win[0] <= dt <= win[1])


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


def scan_codex() -> tuple[list, dict]:
    """-> (markers, stats); markers are (dt, session_id) session start/end pairs."""
    files = glob.glob(CODEX_ROLLOUTS)
    markers: list[tuple[datetime, str]] = []
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
        for marker in (start, end):
            if marker is not None:
                markers.append((marker, base))
        sessions += 1
    return markers, {"sessions": sessions, "end_from_mtime": used_mtime}


def tokenstep_by_night(
    windows: dict[str, tuple[datetime, datetime]],
) -> dict[str, tuple[int, int, int, int]]:
    """night_iso -> (tokens_day, tokens_evening, hours_day, hours_evening).

    From the TokenStep app's store, presence-gated: an hourly rhythm bucket
    only counts when its hour overlaps that night's attended window, so
    autonomous runs after she leaves contribute nothing. All four figures are
    night-keyed (day = 04:00→04:00): tokens_day/hours_day span the whole
    attended day, the evening pair spans 20:00-04:00. Days inside TokenStep
    coverage but with no window are a true 0; days outside coverage are absent
    (caller writes "").
    """
    if not TOKENSTEP_JSON.exists():
        return {}
    try:
        with open(TOKENSTEP_JSON, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return {}
    coverage = sorted(r["date"] for r in d.get("daily", []) if r.get("date"))
    buckets = {r["date"]: {b.get("hour"): int(b.get("tokens") or 0)
                           for b in r.get("buckets", [])}
               for r in d.get("rhythms", []) if r.get("date")}

    def hour_start(date_iso: str, h: int) -> datetime:
        return datetime.fromisoformat(date_iso).replace(hour=h).astimezone()

    def gated(date_iso: str, h: int) -> int:
        t = buckets.get(date_iso, {}).get(h, 0)
        if t <= 0:
            return 0
        start = hour_start(date_iso, h)
        key, _ = night_key(start)
        win = windows.get(key)
        # the hour counts if any part of [start, start+1h) is attended
        if win and start <= win[1] and start + timedelta(hours=1) >= win[0]:
            return t
        return 0

    out = {}
    for date_iso in coverage:
        nxt = (datetime.fromisoformat(date_iso) + timedelta(days=1)).date().isoformat()
        day_hours = [gated(date_iso, h) for h in range(NIGHT_CUTOFF_HOUR, 24)] \
            + [gated(nxt, h) for h in range(NIGHT_CUTOFF_HOUR)]
        eve_hours = day_hours[20 - NIGHT_CUTOFF_HOUR:]
        out[date_iso] = (sum(day_hours), sum(eve_hours),
                         sum(1 for t in day_hours if t > 0),
                         sum(1 for t in eve_hours if t > 0))
    return out


def main():
    claude_events, human_times, c = scan_claude()
    codex_markers, x = scan_codex()
    windows = build_windows(human_times)

    nights: dict[str, NightAgg] = {}
    dropped = 0
    for dt, sess in claude_events:
        if in_window(dt, windows):
            key, lateness = night_key(dt)
            nights.setdefault(key, NightAgg()).add(lateness, "claude", sess)
        else:
            dropped += 1
    for dt, sess in codex_markers:
        if in_window(dt, windows):
            key, lateness = night_key(dt)
            nights.setdefault(key, NightAgg()).add(lateness, "codex", sess)
        else:
            dropped += 1

    tokens = tokenstep_by_night(windows)

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
        row["ai_hours_day"] = t[2] if t else ""
        row["ai_hours_evening"] = t[3] if t else ""

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["date"])
        w.writeheader()
        w.writerows(rows)

    span = f"{rows[0]['date']} .. {rows[-1]['date']}" if rows else "—"
    print(f"Claude: {c['files']} files, {c['events']} events "
          f"({c['human_msgs']} human messages)")
    print(f"Codex : {x['sessions']} sessions "
          f"({x['end_from_mtime']} used file-mtime as session end)")
    print(f"Presence gate: {len(windows)} attended days, "
          f"{dropped} unattended events dropped")
    print(f"Nights: {len(rows)}  span {span}")
    print(f"Wrote  {OUT}")


if __name__ == "__main__":
    main()
