---
name: stock-trade-reviewer
description: Analyze user-provided stock trade statements in CSV, Excel, or locally sanitized PDF-derived CSV format to clean transaction data, compute historical metrics, diagnose trading behavior, simulate discipline rules on historical results, and generate Chinese Markdown/HTML personal trade review reports. Use only for historical self-review; never recommend stocks, predict prices, or advise buying/selling a security.
---

# 股票交割单复盘 Skill

## 使用场景

当用户提供股票交割单、成交记录、交易流水或 PDF 脱敏后的交易 CSV，并希望做个人交易复盘、行为诊断、风控检查、反事实规则验证或生成中文复盘报告时使用本 Skill。若用户希望在 Codex 中一句话启动处理真实 PDF，优先使用“隐私交互模式”。

## 输入文件

- 支持 `.csv`、`.xlsx`；PDF 先用 `scripts/sanitize_pdf_statement.py` 在本机脱敏成 `sanitized_trades.csv`。
- 真实文件不要上传给 AI。运行前提醒用户删除姓名、身份证、手机号、资金账号、银行卡号、客户号、股东账号、营业部、地址等信息。
- 如果字段缺失或数据不足，相关结论必须写 `无法判断`。

## 隐私交互模式

启动命令：

```bash
python3 scripts/interactive_runner.py --open
```

- 本地页面地址：`http://127.0.0.1:8787`
- 服务只监听 `127.0.0.1`，不监听 `0.0.0.0`。
- 用户在浏览器上传 PDF；原始 PDF 只保存在 `tempfile.TemporaryDirectory()`，不得进入项目目录。
- 脚本完成 PDF 脱敏后立即删除原始临时 PDF。
- Codex 不读取、不打印、不分析原始 PDF 内容。
- 真实输出默认写入 `local_outputs/`，该目录已加入 `.gitignore`。
- 交互完成后，Codex 只允许读取 `sanitized_trades.csv`、`privacy_guard_report.json`、`cleaned_trades.csv`、`metrics.json`、`trade_lifecycle.json`、`behavior_flags.json`、`counterfactual_report.json`、`trade_review_report.html`。

## 推荐工作流

### 方式一：浏览器隐私交互

1. 运行 `python3 scripts/interactive_runner.py --open`
2. 在本地页面上传 PDF。
3. 等待隐私检查和复盘流程完成。
4. 点击页面中的“打开 HTML 报告”。

### 方式二：命令行流程

1. PDF 本地脱敏：`python3 scripts/sanitize_pdf_statement.py 交割单.pdf -o sanitized_trades.csv`
2. 隐私检查：`python3 scripts/privacy_guard.py sanitized_trades.csv`
3. 标准化解析：`python3 scripts/parse_statement.py sanitized_trades.csv`
4. 计算指标：`python3 scripts/compute_metrics.py cleaned_trades.csv`
5. 构建生命周期：`python3 scripts/build_trade_lifecycle.py cleaned_trades.csv`
6. 行为诊断：`python3 scripts/detect_behavior_patterns.py cleaned_trades.csv metrics.json trade_lifecycle.json`
7. 反事实模拟：`python3 scripts/counterfactual_simulator.py metrics.json trade_lifecycle.json`
8. 生成 Markdown：`python3 scripts/generate_review_report.py`
9. 生成 HTML：`python3 scripts/generate_html_report.py`

## 输出文件

- `sanitized_trades.csv`
- `privacy_guard_report.json`
- `cleaned_trades.csv`
- `metrics.json`
- `trade_lifecycle.json`
- `behavior_flags.json`
- `counterfactual_report.json`
- `trade_review_report.md`
- `trade_review_report.html`
- 交互模式默认输出目录：`local_outputs/`

## 隐私边界

- 默认本地处理数据，不上传服务器。
- 不把原始 PDF 全文交给 AI 分析。
- 交互模式的原始 PDF 只能保存在系统临时目录，并在脱敏后删除。
- `sanitize_pdf_statement.py` 默认删除资金余额；只有用户传 `--keep-balance` 才保留。
- `privacy_guard.py` 发现身份、账号、手机号、银行卡、地址等敏感信息时必须失败。
- 公开仓库只能提交源码、文档和完全虚构样例，不提交真实 PDF、真实交割单、真实输出或真实账户信息。

## 投资边界

- 不荐股。
- 不预测未来涨跌。
- 不输出买入、卖出或持有某只股票的建议。
- 所有结论必须基于用户上传的历史成交数据。

## HTML 使用方式

- 打开 `docs/index.html` 查看中文使用说明。
- 打开 `tools/local-runner.html` 查看本地命令向导。
- 打开 `tools/privacy-upload.html` 或运行 `scripts/interactive_runner.py --open` 使用隐私交互模式。
- 运行 `scripts/generate_html_report.py` 后打开 `trade_review_report.html` 查看复盘报告。

## 字段不匹配时

读取 `references/broker_field_mapping.md`，展示已识别字段、未匹配字段和建议映射；不要凭空造字段。必要时请用户提供手动字段映射。

## 何时读取 references

- 字段别名或券商格式不一致：读 `broker_field_mapping.md`。
- 判断数据是否可靠：读 `data_quality_checks.md`。
- 行为诊断和风控规则：读 `risk_rules.md`。
- 五角色复盘：读 `review_roles.md`。
- 报告结构：读 `report_template.md`。
