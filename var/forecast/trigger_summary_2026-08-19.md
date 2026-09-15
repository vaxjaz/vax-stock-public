# D线盘中触发汇总

- updated_at: 2026-08-19T09:27:27
- trade_date: 2026-08-19
- triggers: 2
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 601138 工业富联

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-08-19T09:27:24; trade_time=09:27:17; trade_date=2026-08-19
- 实时行情: 现价=64.10; 涨跌幅=-3.17%; 振幅=0.00%; 成交额=0.96亿
- 均线偏离: MA5=-3.30%; MA20=+2.02%; MA60=-5.33%
- C线原始预测: action=watch; direction=up; confidence=55%
- 触发依据: 说明盘中只有弱反弹而非趋势延续，向上观察价值下降
- LLM客观评价: D线触发: 说明盘中只有弱反弹而非趋势延续，向上观察价值下降 观察目的: 明天盘中观察工业富联能否在强看空宏观下继续维持20日线上方强势，验证C线“watch / up”的次日向上观察假设是否成立 主要风险: 高位区间内一旦失守5日线和20日线，右侧结构可能被宏观逆风放大为假突破或回撤 对C线反馈: watch -> reduce_confidence 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> reduce_confidence; baseline=20260818; task_id=20260818_20260819_601138_d_observe_llm_v2; MA20触发位置=+2.02%

## 2. 601179 中国西电

- 触发: noise_filter / severity=low / fire_count=2
- 时间: forecast_ts=2026-08-19T09:27:27; trade_time=09:27:12; trade_date=2026-08-19
- 实时行情: 现价=13.44; 涨跌幅=-1.32%; 振幅=0.00%; 成交额=0.06亿
- 均线偏离: MA5=-2.21%; MA20=-2.13%; MA60=-5.98%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 窄幅缩量或中性波动不构成方向验证，主要用于过滤盘中噪音。
- LLM客观评价: D线触发: 窄幅缩量或中性波动不构成方向验证，主要用于过滤盘中噪音。 观察目的: 验证该票次日盘中是否只能维持弱势震荡/修复失败，还是会放量重回短中期均线形成右侧修复，从而推翻“回避”判断。 主要风险: 盘中若放量回收20日线并带动短线均线转强，当前“低分回避”的假设会失效。 对C线反馈: no_change_noise_only 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=no_change_noise_only; baseline=20260818; task_id=20260818_20260819_601179_d_observe_llm_v2; MA20触发位置=-2.13%
