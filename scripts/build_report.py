#!/usr/bin/env python3
"""Render reports/report.html — a self-contained dark visual of the attribution.

Every number is computed from the merged data (nothing hardcoded), so the report
is honest for whoever runs it. Bilingual: each prose block is Chinese then
English, stacked (not interleaved). The example factor is evening AI use, but the
grouping is generic — swap `GROUP_COL` for any 0/1 factor column you added.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
AI = ROOT / "data" / "ai_usage.csv"
SLEEP = ROOT / "data" / "garmin_sleep.csv"
OUT = ROOT / "reports" / "report.html"

GROUP_COL = "n_after_2000"   # nights this is > 0 = "factor present" (evening AI use)


def main() -> int:
    ai = pd.read_csv(AI).rename(columns={"date": "night"})
    sl = pd.read_csv(SLEEP)
    df = sl.merge(ai, on="night", how="inner")
    for c in ["sleep_score", "total_sleep_h", "resting_hr", "last_ai_decimal",
              GROUP_COL, "deep_h", "rem_h", "hrv_last_night"]:
        df[c] = pd.to_numeric(df.get(c), errors="coerce")
    df["factor_on"] = (df[GROUP_COL].fillna(0) > 0).astype(int)
    g1, g0 = df[df.factor_on == 1], df[df.factor_on == 0]
    n = len(df)

    def m(grp, col):
        return grp[col].mean()

    # Computed hero deltas (factor-present minus factor-absent)
    d_score = m(g1, "sleep_score") - m(g0, "sleep_score")
    d_dur_min = (m(g1, "total_sleep_h") - m(g0, "total_sleep_h")) * 60
    d_rhr = m(g1, "resting_hr") - m(g0, "resting_hr")

    def signed(v, unit=""):
        return f"{v:+.0f}{unit}".replace("+", "+").replace("-", "−")

    pairs = [  # (zh label, en label, v1, v0, axis-max, higher-is-worse)
        ("睡眠得分", "Sleep score", m(g1, "sleep_score"), m(g0, "sleep_score"), 100, False),
        ("睡眠时长 (小时)", "Sleep (hours)", m(g1, "total_sleep_h"), m(g0, "total_sleep_h"), 9, False),
        ("静息心率 (bpm)", "Resting HR (bpm)", m(g1, "resting_hr"), m(g0, "resting_hr"), 90, True),
    ]
    bars = ""
    for zh, en, v1, v0, mx, worse_high in pairs:
        w1, w0 = v1 / mx * 100, v0 / mx * 100
        note_zh = "越高越差" if worse_high else ""
        note_en = "higher = worse" if worse_high else ""
        bars += f"""
        <div class="metric">
          <div class="mlabel">{zh} / {en} <span class="note">{note_zh}{' · ' if note_zh else ''}{note_en}</span></div>
          <div class="row"><span class="tag ai">有此因素 / on</span>
            <div class="track"><div class="fill ai" style="width:{w1:.1f}%"></div></div>
            <span class="val">{v1:.1f}</span></div>
          <div class="row"><span class="tag no">无 / off</span>
            <div class="track"><div class="fill no" style="width:{w0:.1f}%"></div></div>
            <span class="val">{v0:.1f}</span></div>
        </div>"""

    # scatter: last AI time (x, 18..28h) vs sleep score (y, 0..100)
    W, H, PADL, PADB = 620, 300, 44, 40
    def sx(v):
        return PADL + (min(max(v, 18), 28) - 18) / 10 * (W - PADL - 20)
    def sy(v):
        return H - PADB - v / 100 * (H - PADB - 16)
    pts = ""
    sc = df.dropna(subset=["last_ai_decimal", "sleep_score"])
    for _, r in sc.iterrows():
        pts += f'<circle cx="{sx(r.last_ai_decimal):.0f}" cy="{sy(r.sleep_score):.0f}" r="4.5" class="dot"/>'
    base = m(g0, "sleep_score")
    gy = sy(base)
    xticks = "".join(
        f'<text x="{sx(h):.0f}" y="{H-PADB+18}" class="axl">{int(h)%24 or 24}:00</text>'
        for h in (18, 20, 22, 24, 26, 28))
    yticks = "".join(
        f'<text x="{PADL-8}" y="{sy(v)+4:.0f}" class="axl" text-anchor="end">{v}</text>'
        f'<line x1="{PADL}" y1="{sy(v):.0f}" x2="{W-20}" y2="{sy(v):.0f}" class="grid"/>'
        for v in (0, 25, 50, 75, 100))
    corr = df["sleep_score"].corr(df[GROUP_COL])

    html = f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>睡眠归因报告 · Sleep Attribution Report</title>
<style>
:root{{--bg:#0a0e1a;--card:#121829;--ink:#e8eef7;--dim:#8595b0;--ai:#ff5c7c;--no:#22d3ee;--line:#1e2740}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.6 -apple-system,"PingFang SC",system-ui,sans-serif;padding:32px 20px}}
.wrap{{max-width:760px;margin:0 auto}}
h1{{font-size:26px;margin:0 0 4px}} .sub{{color:var(--dim);margin:0 0 28px}}
.hero{{background:linear-gradient(135deg,#16203a,#121829);border:1px solid var(--line);
border-radius:18px;padding:26px 28px;margin-bottom:24px}}
.hero .big{{font-size:52px;font-weight:800;color:var(--ai);line-height:1.05}}
.hero .big small{{font-size:20px;color:var(--dim);font-weight:600}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:22px 24px;margin-bottom:20px}}
.card h2{{font-size:17px;margin:0 0 16px;color:var(--ink)}}
.metric{{margin-bottom:16px}} .mlabel{{font-size:14px;color:var(--dim);margin-bottom:6px}}
.note{{color:var(--ai);font-size:12px}}
.row{{display:flex;align-items:center;gap:10px;margin:5px 0}}
.tag{{font-size:11px;width:100px;flex:none;text-align:right}} .tag.ai{{color:var(--ai)}} .tag.no{{color:var(--no)}}
.track{{flex:1;background:#0a0f1e;border-radius:8px;height:20px;overflow:hidden}}
.fill{{height:100%;border-radius:8px}} .fill.ai{{background:linear-gradient(90deg,#ff5c7c,#ff8aa3)}}
.fill.no{{background:linear-gradient(90deg,#22d3ee,#67e8f9)}}
.val{{width:52px;flex:none;font-variant-numeric:tabular-nums;font-weight:700}}
svg{{width:100%;height:auto}} .dot{{fill:var(--ai);opacity:.8}} .grid{{stroke:var(--line);stroke-width:1}}
.axl{{fill:var(--dim);font-size:11px}} .trend{{stroke:var(--no);stroke-width:2;stroke-dasharray:5 4}}
.lead{{color:var(--no);font-weight:700}}
ul{{padding-left:18px}} li{{margin:7px 0}} .muted{{color:var(--dim);font-size:13px}}
.en{{color:var(--dim);font-size:13px;margin-top:4px}}
.foot{{color:var(--dim);font-size:12px;margin-top:8px}}
</style></head><body><div class="wrap">
<h1>睡眠归因报告 · Sleep Attribution Report</h1>
<p class="sub">复刻鸭哥《AI如何导致和修复了我的失眠问题》· 你自己的数据 · 共 {n} 个可对齐的夜晚<br>
<span class="en">Replicating Yage's sleep-attribution method · your own data · {n} aligned nights</span></p>

<div class="hero">
  <div class="big">{signed(d_score)}&nbsp;<small>分 / pts</small></div>
  <div style="margin-top:8px">有此因素（本例：晚上 20:00 后用 AI）的夜晚，睡眠得分平均
  <b>{signed(d_score)} 分</b>、睡眠时长 <b>{signed(d_dur_min)} 分钟</b>、静息心率 <b>{signed(d_rhr)} bpm</b>。
  <div class="en">On nights with the factor present (here: AI use after 20:00), sleep score averages
  <b>{signed(d_score)} pts</b>, sleep duration <b>{signed(d_dur_min)} min</b>,
  resting HR <b>{signed(d_rhr)} bpm</b> vs. nights without it.</div></div>
</div>

<div class="card"><h2>有无此因素的夜晚对照 · With vs. without the factor</h2>{bars}</div>

<div class="card"><h2>最后一次用 AI 越晚，睡眠得分越低 · Later last-AI-use vs. sleep score（每点 = 一晚 / each dot = one night）</h2>
<svg viewBox="0 0 {W} {H}" role="img">
  {yticks}{xticks}
  <line x1="{PADL}" y1="{gy:.0f}" x2="{W-20}" y2="{gy:.0f}" class="trend"/>
  <text x="{W-24}" y="{gy-8:.0f}" class="axl" text-anchor="end" fill="#22d3ee">无此因素夜晚均分 / baseline {base:.0f}</text>
  {pts}
</svg>
<p class="muted">横轴 = 当晚最后一次用 AI 的时间（越右越晚，含凌晨）。Pearson r = {corr:.2f}。
<span class="en">X = clock time of the last AI use that evening (rightward = later, into the small hours).</span></p>
</div>

<div class="card"><h2>怎么用这份结果 · How to act on this</h2>
<ul>
<li><span class="lead">看有没有控制上床时间后的效应：</span>见 analysis.md 的回归——若「晚用 AI」在控制上床时间后仍伤睡眠，说明伤的是<b>质量</b>不只是让你睡得晚。
<div class="en"><span class="lead">Check the bedtime-controlled effect:</span> see the regression in analysis.md — if the factor still hurts after controlling for bedtime, it hurts sleep <b>quality</b>, not just duration.</div></li>
<li><span class="lead">改一个变量，再让下几周数据检验：</span>挑相关性最强的那个因素，只改它，别一次改一堆——否则下次分不清是哪一项起了作用。
<div class="en"><span class="lead">Change one variable, then let the next weeks verify:</span> pick the single strongest factor and change only it — changing several at once makes the next analysis unreadable.</div></li>
<li><span class="lead">这是相关不是因果：</span>留意共同原因（压力大的一天既让你熬夜用屏，也让你睡得差）。
<div class="en"><span class="lead">Correlation, not causation:</span> watch for common causes (a stressful day drives both late screen use and bad sleep).</div></li>
</ul>
<p class="foot">共 {n} 晚同时有睡眠与因素记录。原始数据只存在你本机（未上传、未进 git）。
<span class="en">{n} nights with both sleep and factor data. All raw data stays local — never uploaded, never committed.</span></p>
</div>
</div></body></html>"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT}  (n={n})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
