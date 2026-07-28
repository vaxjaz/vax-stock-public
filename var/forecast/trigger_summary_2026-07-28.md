# D线盘中触发汇总

- updated_at: 2026-07-28T09:27:34
- trade_date: 2026-07-28
- triggers: 1
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 601138 工业富联

- 触发: breakdown_confirm / severity=high / fire_count=2
- 时间: forecast_ts=2026-07-28T09:27:34; trade_time=09:26:55; trade_date=2026-07-28
- 实时行情: 现价=58.88; 涨跌幅=-4.34%; 振幅=0.00%; 成交额=1.75亿
- 均线偏离: MA5=-3.91%; MA20=-7.70%; MA60=-14.19%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 说明回撤进一步扩大并且出现放大波动或持续走弱，偏多观察假设被破坏。
- LLM客观评价: D线触发: 说明回撤进一步扩大并且出现放大波动或持续走弱，偏多观察假设被破坏。 观察目的: 验证C线“偏多观察”假设：次日盘中是否能完成对20日线的修复并维持短均线之上，从而证明当前回调只是趋势中的技术整理而非转弱。 主要风险: 股价仍在20日线下方，且AI算力赛道被设置为减档上限；若盘中不能站回并稳定在20日线附近，偏多观察将被证伪。 对C线反馈: watch -> invalidate_bullish_case 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> invalidate_bullish_case; baseline=20260727; task_id=20260727_20260728_601138_d_observe_llm_v2; MA20触发位置=-7.70%
