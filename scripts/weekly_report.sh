#!/bin/bash
# Weekly auto-run: refresh behavior signal + pull Garmin sleep + re-analyze +
# build report + open it. Wire to cron or a launchd/systemd timer to run weekly.
# No step aborts the rest: the report is always rebuilt from the freshest data
# on disk, and any failure is logged with its reason.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"   # repo root, wherever it's cloned
PY="$ROOT/.venv/bin/python"
LOG="$ROOT/data/weekly_run.log"
cd "$ROOT" || exit 1
mkdir -p data

stamp() { date "+%Y-%m-%d %H:%M:%S"; }
echo "===== $(stamp) weekly run =====" >>"$LOG"

# 1. Behavior signal (local logs, no network — rarely fails). Optional: delete
#    this block if you supply your own factor CSV instead.
"$PY" scripts/extract_ai_usage.py >>"$LOG" 2>&1 \
  && echo "[$(stamp)] ai_usage OK" >>"$LOG" \
  || echo "[$(stamp)] ai_usage FAILED" >>"$LOG"

# 2. Garmin side (uses saved token; if it expired, skip and reuse last sleep data)
if "$PY" scripts/pull_garmin.py 90 >>"$LOG" 2>&1; then
  echo "[$(stamp)] garmin pull OK" >>"$LOG"
else
  echo "[$(stamp)] garmin pull FAILED — token may have expired; using existing sleep data" >>"$LOG"
fi

# 3. Merge + analyze + build the visual report
"$PY" scripts/analyze.py >>"$LOG" 2>&1 \
  && echo "[$(stamp)] analyze OK" >>"$LOG" \
  || echo "[$(stamp)] analyze FAILED" >>"$LOG"
"$PY" scripts/build_report.py >>"$LOG" 2>&1 \
  && echo "[$(stamp)] report OK" >>"$LOG" \
  || echo "[$(stamp)] report FAILED" >>"$LOG"

# 4. Open the report (macOS `open`; use `xdg-open` on Linux). Drop this line for
#    a headless server.
[ -f reports/report.html ] && command -v open >/dev/null && open reports/report.html
echo "[$(stamp)] done" >>"$LOG"
