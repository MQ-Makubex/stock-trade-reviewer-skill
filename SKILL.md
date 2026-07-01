---
name: stock-trading-coach-agent
description: Daily Chinese stock trading coach agent for user-provided historical trades, trade journals, and article viewpoints. It keeps the original stock statement privacy workflow, locally sanitizes PDF/CSV/XLSX statements, diagnoses behavior, checks narrative pollution, builds conservative playbooks, and generates Markdown/HTML/JSON daily coaching reports. Never recommend stocks, predict prices, or advise buying/selling.
---

# 股票教练智能体

## 使用场景

当用户希望复盘股票交割单、记录当天交易想法、分析阅读文章对交易的影响、沉淀个人交易模式或生成买入前风控反问时使用本 Skill。

默认行为：用户只说“请使用 $stock-trading-coach-agent”时，直接运行 `python3 scripts/interactive_runner.py --open`，打开本地每日教练页面。不要默认读取原始 PDF，不要输出长教程。

## 输入文件

- 支持 `.pdf`、`.csv`、`.xlsx`、`.xlsm` 交易文件；PDF 继续本地脱敏，CSV/XLSX 只在本机临时目录解析。
- 支持当天交易想法、交易意图、情绪状态、计划与复盘备注。
- 支持文章 URL 或粘贴文章文本；URL 可联网抓取，但长期只保存摘要和叙事污染检查，不保存全文。
- 支持手动更新宏观镜片，例如冰冰小美雪球主页；宏观镜片只用于市场环境观察和教练提问。
- 截图成交单仅在用户显式上传给 Codex 识别时使用 AI 抽取标准 trades；建议先裁剪或打码身份、账号、资金余额。

## 工作流

1. 本地交互：`python3 scripts/interactive_runner.py --open`
2. 上传一个或多个交易文件，填写交易想法和文章信息。
3. 本地完成隐私检查、标准化解析、交易统计、行为诊断和反事实模拟。
4. 生成 `daily_journal.json`、`article_digest.json`、`pre_trade_guard.json`。
5. 保守更新 `local_state/playbooks.json`。
6. 读取可选 `local_state/macro_lenses.json`，生成市场情况判断和教练判断理由。
7. 生成 `daily_coach_report.json`、`daily_coach_report.md`、`daily_coach_report.html`。
8. 生成用于雪球发布的 `daily_xueqiu_post.md`、`daily_xueqiu_post.html`。

手动更新宏观镜片：

```bash
python3 scripts/macro_lens_digest.py --source xueqiu --user-url "https://xueqiu.com/u/7143769715" --limit 50
```

该命令只保存标题、URL、摘要、宏观镜片和风险标签，不保存文章全文。若雪球页面需要登录或反爬，应改用具体文章 URL 或手动粘贴文本，不伪造抓取结果。

明确要求“只做交割单复盘”时，可以沿用原 `trade_review_report.html` 流程。

## Playbook 规则

- 单次交易成功不得直接进入 `可复制`。
- 至少 3 次类似证据后，才能从 `待验证` 升级为 `可复制`。
- 亏损或风险失控模式进入 `应避免`。
- 每条 playbook 必须包含：触发条件、入场理由类型、退出方式、最大风险、证据日期、验证状态。

## 文章叙事污染检查

`article_digest.py` 不只总结文章，还必须判断：

- 是否强化已有持仓偏见。
- 是否诱发追涨。
- 是否提供可验证事实。
- 是否只是情绪安慰。
- 是否影响当天交易动作。

## 输出文件

- `cleaned_trades.csv`
- `metrics.json`
- `trade_lifecycle.json`
- `behavior_flags.json`
- `counterfactual_report.json`
- `daily_journal.json`
- `article_digest.json`
- `pre_trade_guard.json`
- `daily_coach_report.json`
- `daily_coach_report.md`
- `daily_coach_report.html`
- `daily_xueqiu_post.md`
- `daily_xueqiu_post.html`
- `local_state/playbooks.json`
- `local_state/macro_lenses.json`

真实输出默认写入 `local_outputs/run_时间戳/`；最新 HTML 报告复制到 `local_outputs/daily_coach_report.html`。
雪球发布版稳定入口复制到 `local_outputs/daily_xueqiu_post.html`。

## 隐私边界

- 默认本地处理交易文件，不上传服务器。
- 不把原始 PDF 全文交给 AI 分析。
- 原始上传文件只保存在 `tempfile.TemporaryDirectory()`，处理后删除，不进入项目目录。
- `local_outputs/` 与 `local_state/` 不提交 Git。
- 公开仓库只能提交源码、文档和完全虚构样例，不提交真实 PDF、真实交割单、截图、真实 journal 或真实账户信息。

## 投资边界

- 不荐股。
- 不预测未来涨跌。
- 不输出买入、卖出或持有某只股票的建议。
- 明日计划必须写成条件触发式纪律，不能写确定性动作。
- 市场情况判断必须给出理由，说明依据来自成交事实、用户 journal、文章观点或宏观镜片；证据不足时写 `无法判断`。
- 所有结论必须基于用户提供的历史成交、当天想法和文章观点。
- 数据不足时必须写 `无法判断`。
- 稳定盈利定义为寻找可重复、可验证、风险可控的交易模式，而不是预测未来。

## 何时读取 references

- 字段别名或券商格式不一致：读 `broker_field_mapping.md`。
- 判断数据是否可靠：读 `data_quality_checks.md`。
- 行为诊断和风控规则：读 `risk_rules.md`。
- 五角色复盘：读 `review_roles.md`。
- 报告结构：读 `report_template.md`。
