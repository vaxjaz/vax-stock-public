# D线盘中触发汇总

- updated_at: 2026-08-11T10:14:52
- trade_date: 2026-08-11
- triggers: 3
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

## 2. 601138 工业富联

- 触发: failed_breakout / severity=high / fire_count=1
- 时间: forecast_ts=2026-08-11T09:39:35; trade_time=09:39:32; trade_date=2026-08-11
- 实时行情: 现价=66.23; 涨跌幅=-4.26%; 振幅=2.88%; 成交额=18.21亿
- 均线偏离: MA5=-0.10%; MA20=+8.01%; MA60=-2.45%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 涨幅回吐并跌回短均线附近，说明前一日强势未能转化为有效延续，假突破风险上升。
- LLM客观评价: D线触发: 涨幅回吐并跌回短均线附近，说明前一日强势未能转化为有效延续，假突破风险上升。 观察目的: 验证工业富联次日盘中是否能在高位延续强势、确认C线“watch/up”的上行动量，而不是冲高后回落失去延续性。 主要风险: 高位延续失败：在AI算力上限减档与近期快速上涨后的背景下，盘中若回落到短均线附近，C线的上行假设可能被证伪。 对C线反馈: watch -> invalidate_up_thesis 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> invalidate_up_thesis; baseline=20260810; task_id=20260810_20260811_601138_d_observe_llm_v2; MA20触发位置=+8.01%

## 3. 600875 东方电气

- 触发: noise_filter / severity=low / fire_count=1
- 时间: forecast_ts=2026-08-11T10:14:52; trade_time=10:14:48; trade_date=2026-08-11
- 实时行情: 现价=27.12; 涨跌幅=-0.26%; 振幅=1.54%; 成交额=2.98亿
- 均线偏离: MA5=-1.35%; MA20=+3.12%; MA60=-10.01%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若全天只是低振幅、低量能的窄幅波动，则更像噪音，不足以改变对C线的判断。
- LLM客观评价: D线触发: 若全天只是低振幅、低量能的窄幅波动，则更像噪音，不足以改变对C线的判断。 观察目的: 验证这只票次日是否继续体现“非panic、低优先级回避”的弱势/横盘特征，还是会在盘中重新站回短均线并放量，从而削弱C线的avoid判断。 主要风险: 盘中若重新收复MA5/MA10并伴随量能放大，说明昨日的回避假设可能失效，存在弱转强的反向修复风险。 对C线反馈: hold_no_change 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=hold_no_change; baseline=20260810; task_id=20260810_20260811_600875_d_observe_llm_v2; MA20触发位置=+3.12%
