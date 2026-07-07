---
name: garmin-sleep-attribution
description: Use when someone wants to find what is actually hurting their sleep from their own Garmin data — pull nightly sleep/HR/HRV, join it with a behavioral factor (late-night AI/screen use, caffeine, exercise…), and run multivariate attribution. The scripts only produce clean CSVs; YOU (the AI) run the analysis and write the conclusion. Triggers: "why am I sleeping badly", "analyze my Garmin sleep", "睡眠归因", "what's wrecking my sleep", "does late screen time hurt my sleep".
---

# Garmin Sleep Attribution

Your job in this skill is to be **the analyst**, not a GUI. The scripts turn raw
data into clean CSVs; you find the signal and state the conclusion in plain
language, with the caveats an honest analyst would give.

## The one rule that must not be broken

**Never handle the user's Garmin password.** Login is interactive and the user
runs it themselves in a real terminal (`garmin_login.py` uses hidden `getpass`).
You only ever touch the saved token afterward. Never ask them to paste a
password, and never echo `.garmin_tokens/`.

## Pipeline (drive it in this order)

1. **Setup** (once): `python -m venv .venv && .venv/bin/pip install -r requirements.txt`
2. **Login** (once, user runs it): tell the user to run
   `.venv/bin/python scripts/garmin_login.py` (add `--cn` for garmin.cn) in their
   terminal and report back. Token lasts ~1 year; they never log in again.
3. **Pull sleep**: `.venv/bin/python scripts/pull_garmin.py 90` → `data/garmin_sleep.csv`
   (+ raw JSON kept per night, so no field is lost if Garmin renames one).
4. **Pull a behavior factor**: `.venv/bin/python scripts/extract_ai_usage.py`
   for the built-in AI-usage example, OR have the user drop any factor CSV into
   `data/` keyed by a `night` (or `date`) column, `YYYY-MM-DD`.
5. **Analyze**: `.venv/bin/python scripts/analyze.py` → `reports/analysis.md`.
   Then `build_report.py` for the visual HTML.

## The night key (why joins line up)

Both extractors bucket events by a **04:00 local cutoff**: anything before 4am
counts toward the *previous* evening — the night it actually affected. Any factor
CSV you bring in must follow the same convention or the merge will be off by a day.

## How to read `analyze.py`'s three views

- **Group test** — average sleep on nights the factor was present vs absent. Fast
  gut check, but confounded (doesn't control for anything).
- **Correlations** — Pearson + Spearman of each predictor against each outcome.
  Spearman diverging from Pearson = a nonlinear or outlier-driven relationship.
- **Standardized regression** — the load-bearing one. `sleep_score ~ predictors`
  including `bedtime_decimal`. **This is what separates "went to bed late" from
  "slept worse".** If a late-usage coefficient stays negative *after* bedtime is
  in the model, the factor hurts sleep *quality*, not just duration.

## When you write the conclusion

- Lead with the single strongest, bedtime-controlled finding.
- **State n.** With < ~20 nights, call it suggestive, not proven. Regression
  auto-skips under ~8 usable rows — say so rather than inventing a result.
- Correlation ≠ causation. Name the obvious confounders (a stressful day drives
  both late screen use *and* bad sleep).
- End with one concrete, testable behavioral lever — then let the next weeks of
  data check whether it worked. That loop is the whole point.

## Adding your own factor

Any behavior you can timestamp becomes a predictor: write a small extractor that
emits `data/<factor>.csv` with a `night` column + your numeric columns, add those
column names to `PREDICTORS` in `analyze.py`, and it folds into all three views.
