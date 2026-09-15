# D线盘中触发汇总

- updated_at: 2026-09-03T09:55:16
- trade_date: 2026-09-03
- triggers: 6
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 002475 立讯精密

- 触发: reclaim_confirm / severity=medium / fire_count=2
- 时间: forecast_ts=2026-09-03T09:29:55; trade_time=09:25:00; trade_date=2026-09-03
- 实时行情: 现价=57.49; 涨跌幅=+0.72%; 振幅=0.00%; 成交额=0.19亿
- 均线偏离: MA5=+0.72%; MA20=+2.34%; MA60=-5.57%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若盘中能稳定回到20日线上方，并且动能或量能同步改善，则‘低评分直接回避’这一假设需要重新审视。
- LLM客观评价: D线触发: 若盘中能稳定回到20日线上方，并且动能或量能同步改善，则‘低评分直接回避’这一假设需要重新审视。 观察目的: 观察次日盘中是否延续弱势并确认对20日线的失守，还是出现放量回收20日线的反向修复，从而验证C线的回避判断。 主要风险: 在非panic背景下，个股若盘中重新站稳20日线并伴随量能与动能修复，会削弱“score<2所以回避”的假设。 对C线反馈: avoid -> review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=avoid -> review; baseline=20260902; task_id=20260902_20260903_002475_d_observe_llm_v2; MA20触发位置=+2.34%

## 2. 600276 恒瑞医药

- 触发: noise_filter / severity=low / fire_count=1
- 时间: forecast_ts=2026-09-03T09:29:57; trade_time=09:29:33; trade_date=2026-09-03
- 实时行情: 现价=45.60; 涨跌幅=+0.07%; 振幅=0.00%; 成交额=0.10亿
- 均线偏离: MA5=-2.06%; MA20=-9.21%; MA60=-12.03%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若只是低能量、低振幅的超跌反抽，更像噪声修复，不构成对回避判断的实质挑战。
- LLM客观评价: D线触发: 若只是低能量、低振幅的超跌反抽，更像噪声修复，不构成对回避判断的实质挑战。 观察目的: 明天盘中验证 C线“回避”判断是否成立：在强看空市场与自身超跌背景下，这只票更可能继续弱势下探，还是只出现无量弱反弹、无法收复短均线。 主要风险: 最需要防范的是盘中快速收复5日/10日均线并伴随放量，导致“回避”判断失效。 对C线反馈: avoid -> unchanged 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=avoid -> unchanged; baseline=20260902; task_id=20260902_20260903_600276_d_observe_llm_v2; MA20触发位置=-9.21%

## 3. 600875 东方电气

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-09-03T09:30:00; trade_time=09:29:27; trade_date=2026-09-03
- 实时行情: 现价=24.66; 涨跌幅=+0.45%; 振幅=0.00%; 成交额=0.03亿
- 均线偏离: MA5=-2.74%; MA20=-6.43%; MA60=-10.48%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明盘中出现弱反弹，但仍未摆脱均线压制，更偏向技术性修复而非趋势反转。
- LLM客观评价: D线触发: 说明盘中出现弱反弹，但仍未摆脱均线压制，更偏向技术性修复而非趋势反转。 观察目的: 验证 C线“非 panic、默认回避/低优先级”是否成立：次日盘中重点看东方电气是继续弱势下探并放大跌幅，还是出现有量的短均线收复。 主要风险: 弱势延续导致回撤进一步扩大；如果盘中无法修复短均线且继续远离20日线，C线的回避判断会被强化；若快速收复短均线，则回避假设失真。 对C线反馈: neutral_watch -> rebound_quality_check 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=neutral_watch -> rebound_quality_check; baseline=20260902; task_id=20260902_20260903_600875_d_observe_llm_v2; MA20触发位置=-6.43%

## 4. 601179 中国西电

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-09-03T09:30:03; trade_time=09:29:31; trade_date=2026-09-03
- 实时行情: 现价=12.56; 涨跌幅=+0.56%; 振幅=0.00%; 成交额=0.01亿
- 均线偏离: MA5=-1.24%; MA20=-5.39%; MA60=-8.51%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明只是弱反抽，未形成有效修复，仍偏向验证 C 线的回避结论。
- LLM客观评价: D线触发: 说明只是弱反抽，未形成有效修复，仍偏向验证 C 线的回避结论。 观察目的: 验证 C 线“回避/中性”判断是否成立，重点看盘中是否延续弱势、是否出现对 20 日线的有效收复失败，以及是否有放量反抽把弱势结论推翻。 主要风险: 若盘中快速收复 5 日线和 20 日线并伴随放量，说明当前回避假设可能失效，原先的弱势延续判断需要重估。 对C线反馈: watch -> maintain_caution 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> maintain_caution; baseline=20260902; task_id=20260902_20260903_601179_d_observe_llm_v2; MA20触发位置=-5.39%

## 5. 601138 工业富联

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-09-03T09:35:06; trade_time=09:35:05; trade_date=2026-09-03
- 实时行情: 现价=63.57; 涨跌幅=+2.86%; 振幅=1.63%; 成交额=7.22亿
- 均线偏离: MA5=+0.12%; MA20=-1.33%; MA60=-2.87%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明只是弱反弹，没有形成对中期均线的有效修复，更像低质量修复而非趋势反转。
- LLM客观评价: D线触发: 说明只是弱反弹，没有形成对中期均线的有效修复，更像低质量修复而非趋势反转。 观察目的: 明天盘中验证工业富联是否仍处于均线下方的弱势运行状态，重点看 C线的 avoid 是否会被继续破位证实，或被快速收复短中期均线推翻。 主要风险: 在宏观强看空和AI算力闸门收紧背景下，若盘中继续受压于 ma10/ma20 且无法修复，弱势延续会支持回避判断；若快速收复关键均线，则说明当前回避可能过于保守。 对C线反馈: action=avoid 维持；偏向 weak_rebound 结论 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=action=avoid 维持；偏向 weak_rebound 结论; baseline=20260902; task_id=20260902_20260903_601138_d_observe_llm_v2; MA20触发位置=-1.33%

## 6. 600276 恒瑞医药

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-09-03T09:55:15; trade_time=09:55:09; trade_date=2026-09-03
- 实时行情: 现价=45.90; 涨跌幅=+0.72%; 振幅=0.75%; 成交额=3.97亿
- 均线偏离: MA5=-1.42%; MA20=-8.62%; MA60=-11.45%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若出现弱反弹但仍明显受制于中期均线，通常说明只是技术性修复而非趋势反转。
- LLM客观评价: D线触发: 若出现弱反弹但仍明显受制于中期均线，通常说明只是技术性修复而非趋势反转。 观察目的: 明天盘中验证 C线“回避”判断是否成立：在强看空市场与自身超跌背景下，这只票更可能继续弱势下探，还是只出现无量弱反弹、无法收复短均线。 主要风险: 最需要防范的是盘中快速收复5日/10日均线并伴随放量，导致“回避”判断失效。 对C线反馈: watch -> hold 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> hold; baseline=20260902; task_id=20260902_20260903_600276_d_observe_llm_v2; MA20触发位置=-8.62%
