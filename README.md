# Garmin 睡眠归因 · Garmin Sleep Attribution

把模糊的「我最近怎么睡不好」变成一个数据问题:拉下你自己的 Garmin 睡眠数据,
和你想验证的行为因素放在一起做多变量归因,让 AI 找出真正拖垮你睡眠的那个变量——
而不是你先入为主猜的那个。

**核心哲学:工具的用户是 AI,不是人。** 脚本只负责把数据变成干净的 CSV,
相关性、回归、下结论都交给对话里的 AI 完成——不做花哨的 GUI,不做黑箱打分。

> 方法复刻自鸭哥《AI 如何导致和修复了我的失眠问题》。他的关键洞察:
> 先把全部原始信息收全,再整理→提假设→验证;人最容易「先解释,后观察」。

## 它怎么工作

三步,每步一个脚本,各吐一份干净 CSV:

1. **抓睡眠**:`garmin_login.py` 登录一次(密码只在你终端里输,存下一年期令牌),
   之后 `pull_garmin.py` 用令牌把睡眠 / 静息心率 / HRV / 压力逐夜拉成 `garmin_sleep.csv`。
2. **抓行为因素**:内置的例子是 `extract_ai_usage.py`——从本机 Claude Code / Codex
   日志里重建「每晚最后一次用 AI 的时间」等信号(鸭哥分析里相关性最强的变量)。
   你也可以换成任何自己的因素 CSV(咖啡、运动、屏幕时间……),只要按 `night` 对齐。
3. **归因**:`analyze.py` 按 04:00 为界把两份数据对到同一个「夜晚」,跑三层分析——
   分组对照、相关性排序、**控制上床时间后的标准化回归**(区分「睡得晚」和「睡得差」),
   AI 据此写结论;`build_report.py` 出一张自包含的可视化 HTML。

## 隐私模型(重要)

- **你的睡眠数据永远不进 git**:`data/`、`reports/` 全部 gitignore,纯本地。
- **Garmin 密码 AI 永不经手**:只由你本人在真终端里跑 `garmin_login.py` 输入;
  换来的登录令牌存 `.garmin_tokens/`(也 gitignore),之后不用再登录。
- 仓库里只有代码和合成样本,没有任何真人数据。

## 快速开始

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt

# 先不接手表试跑:把合成样本当数据,直接看分析长什么样
mkdir -p data reports
cp examples/sample_sleep.csv data/garmin_sleep.csv
cp examples/sample_ai_usage.csv data/ai_usage.csv
.venv/bin/python scripts/analyze.py          # 出 reports/analysis.md
.venv/bin/python scripts/build_report.py     # 出 reports/report.html

# 接自己的 Garmin(在真终端里跑,会问账号密码)
.venv/bin/python scripts/garmin_login.py     # 国际版; 佳明加 --cn
.venv/bin/python scripts/pull_garmin.py 90   # 拉最近 90 晚
.venv/bin/python scripts/extract_ai_usage.py # 或换成你自己的因素 CSV
.venv/bin/python scripts/analyze.py
```

`examples/sample_report.html` 是样本数据跑出来的报告长相。

## 致谢

- 方法来源:鸭哥《AI 如何导致和修复了我的失眠问题》。
- Garmin 数据经 [`python-garminconnect`](https://github.com/cyberjunky/python-garminconnect)(非官方)。

---

# English

Turn a vague "I've been sleeping badly lately" into a data question: pull your
own Garmin sleep data, put it next to whatever behavioral factors you want to
test, and let an AI find the variable that's actually wrecking your sleep —
not the one you assumed.

**Core philosophy: the user of the tool is the AI, not the human.** The scripts
only turn data into clean CSVs; the correlations, regression, and conclusions
are done by an AI in conversation — no fancy GUI, no black-box score.

> The method replicates 鸭哥 (Yage)'s essay *How AI caused, and then fixed, my
> insomnia*. His key insight: collect all the raw signal first, then organize →
> hypothesize → verify. Humans are wired to explain before they observe.

## How it works

Three steps, one script each, each emitting a clean CSV:

1. **Pull sleep**: `garmin_login.py` logs in once (password typed only in your
   terminal, saves a ~1-year token); then `pull_garmin.py` uses the token to
   pull nightly sleep / resting HR / HRV / stress into `garmin_sleep.csv`.
2. **Pull a behavior factor**: the built-in example is `extract_ai_usage.py`,
   which reconstructs "time of the last AI use each evening" and related signals
   from local Claude Code / Codex logs (the single most-correlated variable in
   Yage's analysis). Swap in any factor CSV of your own (caffeine, exercise,
   screen time…) as long as it keys on `night`.
3. **Attribute**: `analyze.py` joins both datasets on the same "night" (a 04:00
   cutoff, so a 1:30am session counts toward the evening it wrecked) and runs
   three views — a group test, a correlation ranking, and a **standardized
   regression that controls for bedtime** (so "went to bed late" is separated
   from "slept worse"). An AI writes the conclusion from it; `build_report.py`
   renders a self-contained visual HTML.

## Privacy model (important)

- **Your sleep data never enters git**: `data/` and `reports/` are gitignored,
  local-only.
- **The AI never handles your Garmin password**: only you run `garmin_login.py`
  in a real terminal; the resulting token lives in `.garmin_tokens/` (also
  gitignored), and you never log in again.
- The repo contains only code and synthetic samples — no real personal data.

## Quick start

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt

# Try it with no watch first: run the analysis on the synthetic sample
mkdir -p data reports
cp examples/sample_sleep.csv data/garmin_sleep.csv
cp examples/sample_ai_usage.csv data/ai_usage.csv
.venv/bin/python scripts/analyze.py          # writes reports/analysis.md
.venv/bin/python scripts/build_report.py     # writes reports/report.html

# Connect your own Garmin (run in a real terminal; it asks for your login)
.venv/bin/python scripts/garmin_login.py     # international; add --cn for garmin.cn
.venv/bin/python scripts/pull_garmin.py 90   # last 90 nights
.venv/bin/python scripts/extract_ai_usage.py # or swap in your own factor CSV
.venv/bin/python scripts/analyze.py
```

`examples/sample_report.html` shows what a report looks like on the sample data.

**Note:** the analysis output and the HTML report are written in Chinese (the
method's origin language). The code and this README are bilingual.

## Credits

- Method: 鸭哥 (Yage), *How AI caused, and then fixed, my insomnia*.
- Garmin data via [`python-garminconnect`](https://github.com/cyberjunky/python-garminconnect) (unofficial).

## License

MIT — see [LICENSE](LICENSE).
