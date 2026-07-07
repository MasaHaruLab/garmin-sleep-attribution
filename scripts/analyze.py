#!/usr/bin/env python3
"""
Join AI-usage with Garmin sleep on `night` and rank what predicts bad sleep.

    .venv/bin/python scripts/analyze.py

Three views (mirrors 鸭哥's multivariate attribution, adapted):
  1. Group test  — nights you used AI after 20:00 vs nights you didn't.
  2. Correlations— each predictor vs each sleep outcome (Pearson + Spearman).
  3. Regression  — sleep_score ~ predictors, standardized, so we can see whether
                   "used AI late" still hurts AFTER controlling for a late bedtime
                   (going to bed late → short sleep is trivial; the real question
                   is whether AI hurts quality beyond that).

Writes reports/analysis.md and prints a summary.
"""
from __future__ import annotations
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
AI = ROOT / "data" / "ai_usage.csv"
SLEEP = ROOT / "data" / "garmin_sleep.csv"
ACT = ROOT / "data" / "garmin_exercise.csv"
REPORT = ROOT / "reports" / "analysis.md"

OUTCOMES = ["sleep_score", "total_sleep_h", "deep_h", "rem_h", "awake_h",
            "resting_hr", "hrv_last_night"]
PREDICTORS = ["last_ai_decimal", "n_after_2000", "n_after_2200", "n_after_0000",
              "n_ai_events", "distinct_late_convos", "bedtime_decimal",
              "exercised", "exercise_dur_min", "exercise_intensity_min",
              "exercise_last_hour"]
# On no-workout nights these are a true 0 (not missing); last_hour stays NaN.
EXERCISE_ZERO = ["exercised", "n_workouts", "exercise_dur_min", "exercise_intensity_min"]
# For these outcomes, a HIGHER value is WORSE sleep (so flip interpretation).
WORSE_IF_HIGH = {"awake_h", "resting_hr"}


def num(df, col):
    return pd.to_numeric(df[col], errors="coerce") if col in df else pd.Series(dtype=float)


def main() -> int:
    if not SLEEP.exists():
        print(f"✗ {SLEEP} not found — run pull_garmin.py first.")
        return 1
    ai = pd.read_csv(AI).rename(columns={"date": "night"})  # ai_usage keys nights as `date`
    sl = pd.read_csv(SLEEP)
    df = sl.merge(ai, on="night", how="inner")
    if ACT.exists():  # exercise is optional — merges in once she resumes training
        ex = pd.read_csv(ACT)
        df = df.merge(ex, on="night", how="left")
        for c in EXERCISE_ZERO:  # no workout logged = a real 0, not missing data
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    for c in set(OUTCOMES + PREDICTORS) & set(df.columns):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["evening_ai"] = (num(df, "n_after_2000").fillna(0) > 0).astype(int)

    n = len(df)
    lines = [f"# 睡眠归因分析\n", f"合并后共 **{n} 个夜晚** 同时有睡眠和 AI 使用数据。\n"]

    # 1. group test
    lines.append("## 1. 晚上用不用 AI（20:00 后）——鸭哥同款对照\n")
    g1 = df[df.evening_ai == 1]
    g0 = df[df.evening_ai == 0]
    lines.append(f"- 用了 AI 的夜晚: **{len(g1)}**  ·  没用的夜晚: **{len(g0)}**\n")
    lines.append("| 睡眠指标 | 晚上用AI | 晚上不用AI | 差值 |\n|---|---|---|---|")
    for o in OUTCOMES:
        if o not in df:
            continue
        m1, m0 = num(g1, o).mean(), num(g0, o).mean()
        if np.isnan(m1) or np.isnan(m0):
            continue
        arrow = "↓更差" if (o not in WORSE_IF_HIGH and m1 < m0) or (o in WORSE_IF_HIGH and m1 > m0) else ""
        lines.append(f"| {o} | {m1:.2f} | {m0:.2f} | {m1 - m0:+.2f} {arrow} |")
    lines.append("")

    # 2. correlations
    lines.append("\n## 2. 各因素与睡眠的相关性（Pearson r，绝对值越大越相关）\n")
    for o in OUTCOMES:
        if o not in df or num(df, o).notna().sum() < 5:
            continue
        cors = []
        for p in PREDICTORS:
            if p not in df:
                continue
            sub = df[[o, p]].apply(pd.to_numeric, errors="coerce").dropna()
            if len(sub) < 5 or sub[p].std() == 0:
                continue
            r = sub[o].corr(sub[p])
            rs = sub[o].rank().corr(sub[p].rank())  # Spearman = Pearson on ranks (no scipy)
            cors.append((abs(r), r, rs, p, len(sub)))
        if not cors:
            continue
        cors.sort(reverse=True)
        lines.append(f"**{o}** 的最强预测因素:")
        for _, r, rs, p, k in cors[:4]:
            lines.append(f"  - `{p}`: r={r:+.2f} (spearman {rs:+.2f}, n={k})")
        lines.append("")

    # 3. standardized regression: sleep_score ~ predictors (incl. bedtime control)
    lines.append("\n## 3. 多变量回归：控制住『上床晚』之后，晚用AI还伤睡眠吗？\n")
    reg_preds = [p for p in ["last_ai_decimal", "n_after_2200", "bedtime_decimal"]
                 if p in df]
    # Auto-fold exercise into the regression once she has ≥5 workout nights, so we
    # can see whether training helps sleep — or offsets late AI — net of bedtime.
    if "exercised" in df and num(df, "exercised").fillna(0).sum() >= 5:
        reg_preds.append("exercise_intensity_min"
                         if "exercise_intensity_min" in df else "exercised")
    sub = df[["sleep_score"] + reg_preds].apply(pd.to_numeric, errors="coerce").dropna()
    if len(sub) >= max(8, len(reg_preds) + 3):
        y = sub["sleep_score"].to_numpy()
        X = sub[reg_preds].to_numpy()
        Xs = (X - X.mean(0)) / (X.std(0) + 1e-9)
        ys = (y - y.mean()) / (y.std() + 1e-9)
        A = np.column_stack([np.ones(len(ys)), Xs])
        beta, *_ = np.linalg.lstsq(A, ys, rcond=None)
        lines.append(f"sleep_score（标准化）回归，n={len(sub)}：")
        for name, b in zip(reg_preds, beta[1:]):
            eff = "伤睡眠" if b < 0 else "利睡眠"
            lines.append(f"  - `{name}`: 标准化系数 {b:+.2f}  → {eff}")
        lines.append("\n> 若 `last_ai_decimal`/`n_after_2200` 的系数在控制 `bedtime_decimal` "
                     "后仍为负，说明晚用AI伤的是睡眠**质量**，不只是让你睡得晚。")
    else:
        lines.append(f"样本不足（n={len(sub)}），回归先跳过，等数据更多再跑。")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\nWrote {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
