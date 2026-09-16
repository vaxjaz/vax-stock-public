# D线盘中触发汇总

- updated_at: 2026-09-16T10:34:00
- trade_date: 2026-09-16
- triggers: 1
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 601138 工业富联

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-09-16T10:34:00; trade_time=10:33:57; trade_date=2026-09-16
- 实时行情: 现价=61.46; 涨跌幅=+1.09%; 振幅=1.97%; 成交额=11.95亿
- 均线偏离: MA5=-2.63%; MA20=-2.38%; MA60=-3.96%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 价格虽上涨，但量能不足且仍受均线压制，支持弱反弹解释；这是向上方向的局部支持，不足以确认趋势修复或正超额预期。
- LLM客观评价: D线触发: 价格虽上涨，但量能不足且仍受均线压制，支持弱反弹解释；这是向上方向的局部支持，不足以确认趋势修复或正超额预期。 观察目的: 在20260916观察工业富联能否以量价修复验证C线基于score_ge_2给出的watch、T+1向上假设，重点区分放量收复、缩量弱反弹和进一步走弱；正超额预期留待EOD基准收益回填验证。 主要风险: 评分及已披露业绩增长与价格趋势存在背离：基线价格低于MA5、MA20和MA60，近5日下跌6.10%，近期已回填样本多日超额为负；宏观看多不能抵消市场广度偏弱及AI赛道海外闸门关闭的背景风险。核心是将下跌中的短暂反弹误认作趋势修复。 对C线反馈: watch -> weak_rebound_review：保留观察状态，区分短时上涨与有效修复，不因单次反弹提高置信判断。 这是客...
- C线反哺线索: expected_feedback_to_c=watch -> weak_rebound_review：保留观察状态，区分短时上涨与有效修复，不因单次反弹提高置信判断。; baseline=20260915; task_id=20260915_20260916_601138_d_observe_llm_v2; MA20触发位置=-2.38%
