# D线盘中触发汇总

- updated_at: 2026-08-26T14:33:52
- trade_date: 2026-08-26
- triggers: 5
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 002475 立讯精密

- 触发: breakdown_confirm / severity=high / fire_count=2
- 时间: forecast_ts=2026-08-26T09:26:40; trade_time=09:25:00; trade_date=2026-08-26
- 实时行情: 现价=54.99; 涨跌幅=+0.24%; 振幅=0.00%; 成交额=0.45亿
- 均线偏离: MA5=+1.81%; MA20=-2.17%; MA60=-11.73%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若继续处于20日线下方且中期压制仍强，同时波动或量能放大，说明弱势延续而非修复。
- LLM客观评价: D线触发: 若继续处于20日线下方且中期压制仍强，同时波动或量能放大，说明弱势延续而非修复。 观察目的: 明天盘中验证 C线“回避/中性”假设：看立讯精密是否继续在20日线下方弱势震荡并延续回避，还是出现有效修复来推翻该判断。 主要风险: 20日线下方的弱修复失败后继续走弱，或反抽无量后再度失守关键均线，从而确认回避判断。 对C线反馈: watch -> avoid_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> avoid_review; baseline=20260825; task_id=20260825_20260826_002475_d_observe_llm_v2; MA20触发位置=-2.17%

## 2. 002475 立讯精密

- 触发: weak_rebound / severity=medium / fire_count=3
- 时间: forecast_ts=2026-08-26T09:26:43; trade_time=09:25:00; trade_date=2026-08-26
- 实时行情: 现价=54.99; 涨跌幅=+0.24%; 振幅=0.00%; 成交额=0.45亿
- 均线偏离: MA5=+1.81%; MA20=-2.17%; MA60=-11.73%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若出现站上5日线但仍未修复20日线、且量能和动量不配合，说明只是弱反弹，不能推翻回避判断。
- LLM客观评价: D线触发: 若出现站上5日线但仍未修复20日线、且量能和动量不配合，说明只是弱反弹，不能推翻回避判断。 观察目的: 明天盘中验证 C线“回避/中性”假设：看立讯精密是否继续在20日线下方弱势震荡并延续回避，还是出现有效修复来推翻该判断。 主要风险: 20日线下方的弱修复失败后继续走弱，或反抽无量后再度失守关键均线，从而确认回避判断。 对C线反馈: watch -> keep_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> keep_avoid; baseline=20260825; task_id=20260825_20260826_002475_d_observe_llm_v2; MA20触发位置=-2.17%

## 3. 600875 东方电气

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-08-26T09:26:45; trade_time=09:26:32; trade_date=2026-08-26
- 实时行情: 现价=26.05; 涨跌幅=+1.76%; 振幅=0.00%; 成交额=0.12亿
- 均线偏离: MA5=+1.09%; MA20=-2.14%; MA60=-7.86%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明盘中有修复动作，但仍停留在弱反弹区间，尚不足以推翻回避。
- LLM客观评价: D线触发: 说明盘中有修复动作，但仍停留在弱反弹区间，尚不足以推翻回避。 观察目的: 明天盘中验证 C线的“avoid/neutral”是否成立：重点看东方电气在低于20日均线的弱势区间内，是继续破位下探，还是出现能推翻回避判断的有效收复。 主要风险: 盘中快速收复10日/20日均线并形成持续回升，说明当前“非 panic、低优先级回避”的假设失效，C线的 avoid 结论需要重评。 对C线反馈: stay_avoid_watch 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=stay_avoid_watch; baseline=20260825; task_id=20260825_20260826_600875_d_observe_llm_v2; MA20触发位置=-2.14%

## 4. 601179 中国西电

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-08-26T09:42:00; trade_time=09:41:54; trade_date=2026-08-26
- 实时行情: 现价=12.89; 涨跌幅=+0.55%; 振幅=1.25%; 成交额=1.05亿
- 均线偏离: MA5=+0.33%; MA20=-5.13%; MA60=-7.82%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 仅有弱反弹但仍被MA10/MA20压制，说明属于超跌修复噪音，不足以改变回避结论。
- LLM客观评价: D线触发: 仅有弱反弹但仍被MA10/MA20压制，说明属于超跌修复噪音，不足以改变回避结论。 观察目的: 明天盘中验证“默认回避”是否成立：这只票在超跌状态下能否只是弱反弹，还是会出现重新站回短中期均线的修复信号从而推翻回避判断。 主要风险: 超跌后的快速修复如果同步收复MA10/MA20，C线的avoid与中性判断可能被推翻。 对C线反馈: watch_no_change 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch_no_change; baseline=20260825; task_id=20260825_20260826_601179_d_observe_llm_v2; MA20触发位置=-5.13%

## 5. 002475 立讯精密

- 触发: reclaim_confirm / severity=high / fire_count=4
- 时间: forecast_ts=2026-08-26T14:33:52; trade_time=14:33:48; trade_date=2026-08-26
- 实时行情: 现价=56.28; 涨跌幅=+2.59%; 振幅=5.16%; 成交额=56.97亿
- 均线偏离: MA5=+4.20%; MA20=+0.13%; MA60=-9.66%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若盘中有效收复20日线并同时站上10日线，说明‘回避/低优先级’假设被明显削弱。
- LLM客观评价: D线触发: 若盘中有效收复20日线并同时站上10日线，说明‘回避/低优先级’假设被明显削弱。 观察目的: 明天盘中验证 C线“回避/中性”假设：看立讯精密是否继续在20日线下方弱势震荡并延续回避，还是出现有效修复来推翻该判断。 主要风险: 20日线下方的弱修复失败后继续走弱，或反抽无量后再度失守关键均线，从而确认回避判断。 对C线反馈: watch -> review_avoid_invalidated 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> review_avoid_invalidated; baseline=20260825; task_id=20260825_20260826_002475_d_observe_llm_v2; MA20触发位置=+0.13%
