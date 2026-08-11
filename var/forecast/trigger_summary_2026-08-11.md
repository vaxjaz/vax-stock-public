# D线盘中触发汇总

- updated_at: 2026-08-11T09:29:30
- trade_date: 2026-08-11
- triggers: 1
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 002475 立讯精密

- 触发: noise_filter / severity=low / fire_count=1
- 时间: forecast_ts=2026-08-11T09:29:30; trade_time=09:25:00; trade_date=2026-08-11
- 实时行情: 现价=55.31; 涨跌幅=-0.86%; 振幅=0.00%; 成交额=0.37亿
- 均线偏离: MA5=-1.24%; MA20=-5.84%; MA60=-15.27%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 只有窄幅震荡、没有均线修复也没有量能配合时，盘中波动更可能只是噪音，不能作为方向性验证。
- LLM客观评价: D线触发: 只有窄幅震荡、没有均线修复也没有量能配合时，盘中波动更可能只是噪音，不能作为方向性验证。 观察目的: 观察明天盘中是否能从当前偏弱位置完成对MA5/MA10的修复，并进一步验证对MA20压力的化解，从而检验C线“watch/up”假设。 主要风险: 低量弱修复后再度回落，说明右侧评分有但承接不足，C线的上行假设可能只停留在盘中反弹而非有效转强。 对C线反馈: watch -> keep_neutral_watch 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> keep_neutral_watch; baseline=20260810; task_id=20260810_20260811_002475_d_observe_llm_v2; MA20触发位置=-5.84%
