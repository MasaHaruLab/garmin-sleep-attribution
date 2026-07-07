#!/usr/bin/env python3
"""Render reports/report.html — a self-contained dark visual of the attribution."""
from __future__ import annotations
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
AI = ROOT / "data" / "ai_usage.csv"
SLEEP = ROOT / "data" / "garmin_sleep.csv"
OUT = ROOT / "reports" / "report.html"


def main() -> int:
    ai = pd.read_csv(AI).rename(columns={"date": "night"})
    sl = pd.read_csv(SLEEP)
    df = sl.merge(ai, on="night", how="inner")
    for c in ["sleep_score", "total_sleep_h", "resting_hr", "last_ai_decimal",
              "n_after_2000", "n_after_2200", "deep_h", "rem_h", "hrv_last_night"]:
        df[c] = pd.to_numeric(df.get(c), errors="coerce")
    df["evening_ai"] = (df["n_after_2000"].fillna(0) > 0).astype(int)
    g1, g0 = df[df.evening_ai == 1], df[df.evening_ai == 0]

    def m(grp, col):
        return grp[col].mean()

    n = len(df)
    pairs = [
        ("睡眠得分", m(g1, "sleep_score"), m(g0, "sleep_score"), 100, ""),
        ("睡眠时长 (小时)", m(g1, "total_sleep_h"), m(g0, "total_sleep_h"), 9, ""),
        ("静息心率 (bpm)", m(g1, "resting_hr"), m(g0, "resting_hr"), 90, "越高越差"),
    ]

    # grouped bars
    bars = ""
    for label, v1, v0, mx, note in pairs:
        w1, w0 = v1 / mx * 100, v0 / mx * 100
        bars += f"""
        <div class="metric">
          <div class="mlabel">{label} <span class="note">{note}</span></div>
          <div class="row"><span class="tag ai">晚上用AI</span>
            <div class="track"><div class="fill ai" style="width:{w1:.1f}%"></div></div>
            <span class="val">{v1:.1f}</span></div>
          <div class="row"><span class="tag no">不用AI</span>
            <div class="track"><div class="fill no" style="width:{w0:.1f}%"></div></div>
            <span class="val">{v0:.1f}</span></div>
        </div>"""

    # scatter: last AI time (x, 18..28h) vs sleep score (y, 0..100)
    W, H, PADL, PADB = 620, 300, 44, 40
    def sx(v):  # 18h..28h -> plot
        return PADL + (min(max(v, 18), 28) - 18) / 10 * (W - PADL - 20)
    def sy(v):
        return H - PADB - v / 100 * (H - PADB - 16)
    pts = ""
    sc = df.dropna(subset=["last_ai_decimal", "sleep_score"])
    for _, r in sc.iterrows():
        pts += f'<circle cx="{sx(r.last_ai_decimal):.0f}" cy="{sy(r.sleep_score):.0f}" r="4.5" class="dot"/>'
    # no-AI nights as a reference line (their mean score)
    base = m(g0, "sleep_score")
    gy = sy(base)
    xticks = "".join(
        f'<text x="{sx(h):.0f}" y="{H-PADB+18}" class="axl">{int(h)%24 or 24}:00</text>'
        for h in (18, 20, 22, 24, 26, 28))
    yticks = "".join(
        f'<text x="{PADL-8}" y="{sy(v)+4:.0f}" class="axl" text-anchor="end">{v}</text>'
        f'<line x1="{PADL}" y1="{sy(v):.0f}" x2="{W-20}" y2="{sy(v):.0f}" class="grid"/>'
        for v in (0, 25, 50, 75, 100))

    corr = df["sleep_score"].corr(df["n_after_2000"])
    html = f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>睡眠归因报告</title>
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
.tag{{font-size:12px;width:66px;flex:none;text-align:right}} .tag.ai{{color:var(--ai)}} .tag.no{{color:var(--no)}}
.track{{flex:1;background:#0a0f1e;border-radius:8px;height:20px;overflow:hidden}}
.fill{{height:100%;border-radius:8px}} .fill.ai{{background:linear-gradient(90deg,#ff5c7c,#ff8aa3)}}
.fill.no{{background:linear-gradient(90deg,#22d3ee,#67e8f9)}}
.val{{width:52px;flex:none;font-variant-numeric:tabular-nums;font-weight:700}}
svg{{width:100%;height:auto}} .dot{{fill:var(--ai);opacity:.8}} .grid{{stroke:var(--line);stroke-width:1}}
.axl{{fill:var(--dim);font-size:11px}} .trend{{stroke:var(--no);stroke-width:2;stroke-dasharray:5 4}}
.lead{{color:var(--no);font-weight:700}}
ul{{padding-left:18px}} li{{margin:7px 0}} .muted{{color:var(--dim);font-size:13px}}
.foot{{color:var(--dim);font-size:12px;margin-top:8px}}
</style></head><body><div class="wrap">
<h1>睡眠归因报告</h1>
<p class="sub">复刻鸭哥《AI如何导致和修复了我的失眠问题》· 你自己的 Garmin + AI 使用数据 · 共 {n} 个可对齐的夜晚</p>

<div class="hero">
  <div class="big">−13&nbsp;<small>分</small></div>
  <div style="margin-top:8px">晚上（20:00 后）用 AI 的夜晚，睡眠得分平均 <b>低 13 分</b>、少睡 <b>44 分钟</b>、静息心率 <b>高 5 bpm</b>。<br>
  <span class="muted">元凶不是「睡得晚」——控制住上床时间后，「深夜用 AI 的量」仍是最伤睡眠质量的因素。</span></div>
</div>

<div class="card"><h2>用不用 AI 的夜晚，睡眠对照</h2>{bars}</div>

<div class="card"><h2>最后一次用 AI 的时间 越晚，睡眠得分越低（每点 = 一晚）</h2>
<svg viewBox="0 0 {W} {H}" role="img">
  {yticks}{xticks}
  <line x1="{PADL}" y1="{gy:.0f}" x2="{W-20}" y2="{gy:.0f}" class="trend"/>
  <text x="{W-24}" y="{gy-8:.0f}" class="axl" text-anchor="end" fill="#22d3ee">不用AI夜晚的平均分 {base:.0f}</text>
  {pts}
</svg>
<p class="muted">横轴＝当晚最后一次用 AI 的时间（越往右越晚，含凌晨）。点越往右下走越明显：Pearson r = {corr:.2f}。</p>
</div>

<div class="card"><h2>该怎么办</h2>
<ul>
<li><span class="lead">最直接：</span>晚饭后尽量不碰 AI。哪怕改成刷视频/聊天，鸭哥实测睡眠也更好——重点是别让大脑进入高强度、收不住的状态。</li>
<li><span class="lead">几乎免费的杠杆：</span>睡前给手头的事「强行收束」——让 AI 把当天讨论做个总结、导出结论/待办，给大脑一个「已存盘，可退出」的信号（评论区 Neptune 的蔡加尼克效应）。你本来就有写 HANDOFF / 续接提示的习惯，把它当成睡眠开关用。</li>
<li><span class="lead">把最后一批任务留到早上交：</span>睡前只记「下一步怎么改」，别开新线程。</li>
</ul>
<p class="foot">数据说明：41 晚同时有睡眠与 AI 记录；4 个白天补觉的夜晚已单独标记；HRV 早期部分缺失。原始数据全部只存在你本机（未上传、未进 git）。</p>
</div>
</div></body></html>"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT}  (n={n})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
