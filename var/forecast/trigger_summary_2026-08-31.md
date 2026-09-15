# D线盘中触发汇总

- updated_at: 2026-08-31T13:59:49
- trade_date: 2026-08-31
- triggers: 6
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 002475 立讯精密

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-08-31T09:28:19; trade_time=09:25:00; trade_date=2026-08-31
- 实时行情: 现价=55.90; 涨跌幅=-1.24%; 振幅=0.00%; 成交额=0.57亿
- 均线偏离: MA5=+0.01%; MA20=+0.10%; MA60=-8.99%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若只是站在短均线附近的小幅反弹、量能不扩张，属于典型弱修复，不足以推翻回避结论。
- LLM客观评价: D线触发: 若只是站在短均线附近的小幅反弹、量能不扩张，属于典型弱修复，不足以推翻回避结论。 观察目的: 验证C线“低分回避/中性”假设：次日盘中是否只能维持弱修复或再度走弱，而不是出现对20/60日线的有效收复并放量转强。 主要风险: 盘中重新收复20日线并继续上穿60日线且伴随放量，这会直接削弱“评分<2且非panic所以回避”的判断。 对C线反馈: watch -> keep_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> keep_avoid; baseline=20260828; task_id=20260828_20260831_002475_d_observe_llm_v2; MA20触发位置=+0.10%

## 2. 600875 东方电气

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-08-31T09:28:21; trade_time=09:28:12; trade_date=2026-08-31
- 实时行情: 现价=25.52; 涨跌幅=+1.07%; 振幅=0.00%; 成交额=0.17亿
- 均线偏离: MA5=-0.30%; MA20=-4.39%; MA60=-8.47%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 出现反弹但仍未回到关键均线之上，且强度不足，说明只是弱修复，仍偏向维持观察/回避。
- LLM客观评价: D线触发: 出现反弹但仍未回到关键均线之上，且强度不足，说明只是弱修复，仍偏向维持观察/回避。 观察目的: 验证 C线“非 panic 且评分偏低，次日应保持低优先级/回避”的假设，重点看盘中是否继续弱势下探或出现对 MA20 的有效修复。 主要风险: 盘中快速收复 MA20 并站稳，说明当前的回避判断可能只是短线噪音而非真实弱势延续。 对C线反馈: watch_maintain_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch_maintain_avoid; baseline=20260828; task_id=20260828_20260831_600875_d_observe_llm_v2; MA20触发位置=-4.39%

## 3. 600276 恒瑞医药

- 触发: breakdown_confirm / severity=high / fire_count=1
- 时间: forecast_ts=2026-08-31T09:48:30; trade_time=09:48:27; trade_date=2026-08-31
- 实时行情: 现价=46.69; 涨跌幅=-1.33%; 振幅=1.01%; 成交额=5.66亿
- 均线偏离: MA5=-0.63%; MA20=-9.04%; MA60=-9.97%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若盘中进一步跌离MA20/MA60且伴随波动或放量，说明弱势延续被机械确认。
- LLM客观评价: D线触发: 若盘中进一步跌离MA20/MA60且伴随波动或放量，说明弱势延续被机械确认。 观察目的: 验证C线“非panic、低评分回避”是否成立：次日盘中重点看恒瑞是否继续在MA20/MA60下方弱势运行，还是出现有效修复并重新夺回短中期均线。 主要风险: 若盘中放量有效收复MA20并进一步靠近MA60，则“回避/弱势延续”的假设会被推翻。 对C线反馈: avoid_review -> strengthen_caution 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=avoid_review -> strengthen_caution; baseline=20260828; task_id=20260828_20260831_600276_d_observe_llm_v2; MA20触发位置=-9.04%

## 4. 601138 工业富联

- 触发: weak_rebound / severity=low / fire_count=3
- 时间: forecast_ts=2026-08-31T10:23:58; trade_time=10:23:55; trade_date=2026-08-31
- 实时行情: 现价=63.43; 涨跌幅=-0.95%; 振幅=2.08%; 成交额=29.45亿
- 均线偏离: MA5=+2.63%; MA20=-0.94%; MA60=-3.81%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明只是弱反弹而非趋势修复，更符合低优先级观察而非追涨逻辑。
- LLM客观评价: D线触发: 说明只是弱反弹而非趋势修复，更符合低优先级观察而非追涨逻辑。 观察目的: 验证C线的avoid/neutral假设：在宏观强看空、AI算力上限减档与EOD资金净流出背景下，工业富联明天盘中是继续围绕20日线弱修复，还是出现有效放量重返短中期均线。 主要风险: 20日线附近失守后转为继续回撤，说明当前低评分、弱RSI和净流出背景下的回避判断成立。 对C线反馈: avoid -> weak_rebound_only 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。 ⚠️[铁律校验] 检测到疑似越界(盘中新评分/买卖价/资金臆测), 以EOD报告为准, 盘中未定论
- C线反哺线索: expected_feedback_to_c=avoid -> weak_rebound_only; baseline=20260828; task_id=20260828_20260831_601138_d_observe_llm_v2; MA20触发位置=-0.94%

## 5. 601138 工业富联

- 触发: failed_breakout / severity=medium / fire_count=4
- 时间: forecast_ts=2026-08-31T13:29:36; trade_time=13:29:34; trade_date=2026-08-31
- 实时行情: 现价=64.10; 涨跌幅=+0.09%; 振幅=2.64%; 成交额=46.01亿
- 均线偏离: MA5=+3.71%; MA20=+0.10%; MA60=-2.79%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明盘中曾尝试转强，但动能和量能不配合，容易形成冲高回落。
- LLM客观评价: D线触发: 说明盘中曾尝试转强，但动能和量能不配合，容易形成冲高回落。 观察目的: 验证C线的avoid/neutral假设：在宏观强看空、AI算力上限减档与EOD资金净流出背景下，工业富联明天盘中是继续围绕20日线弱修复，还是出现有效放量重返短中期均线。 主要风险: 20日线附近失守后转为继续回撤，说明当前低评分、弱RSI和净流出背景下的回避判断成立。 对C线反馈: avoid -> failed_turn_strong 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。 ⚠️[铁律校验] 检测到疑似越界(盘中新评分/买卖价/资金臆测), 以EOD报告为准, 盘中未定论
- C线反哺线索: expected_feedback_to_c=avoid -> failed_turn_strong; baseline=20260828; task_id=20260828_20260831_601138_d_observe_llm_v2; MA20触发位置=+0.10%

## 6. 601138 工业富联

- 触发: reclaim_confirm / severity=medium / fire_count=5
- 时间: forecast_ts=2026-08-31T13:59:49; trade_time=13:59:46; trade_date=2026-08-31
- 实时行情: 现价=64.58; 涨跌幅=+0.84%; 振幅=3.28%; 成交额=51.75亿
- 均线偏离: MA5=+4.49%; MA20=+0.85%; MA60=-2.06%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明盘中对20日线完成有效修复，回避结论需要重新评估。
- LLM客观评价: D线触发: 说明盘中对20日线完成有效修复，回避结论需要重新评估。 观察目的: 验证C线的avoid/neutral假设：在宏观强看空、AI算力上限减档与EOD资金净流出背景下，工业富联明天盘中是继续围绕20日线弱修复，还是出现有效放量重返短中期均线。 主要风险: 20日线附近失守后转为继续回撤，说明当前低评分、弱RSI和净流出背景下的回避判断成立。 对C线反馈: avoid -> review_positive_exception 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。 ⚠️[铁律校验] 检测到疑似越界(盘中新评分/买卖价/资金臆测), 以EOD报告为准, 盘中未定论
- C线反哺线索: expected_feedback_to_c=avoid -> review_positive_exception; baseline=20260828; task_id=20260828_20260831_601138_d_observe_llm_v2; MA20触发位置=+0.85%
