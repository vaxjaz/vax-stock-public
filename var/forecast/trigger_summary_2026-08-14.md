# D线盘中触发汇总

- updated_at: 2026-08-14T10:26:09
- trade_date: 2026-08-14
- triggers: 6
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 600276 恒瑞医药

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-08-14T09:25:34; trade_time=09:25:27; trade_date=2026-08-14
- 实时行情: 现价=53.68; 涨跌幅=-0.15%; 振幅=0.00%; 成交额=0.27亿
- 均线偏离: MA5=-1.28%; MA20=-0.68%; MA60=+3.58%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明只是缩量弱反弹，未形成有效修复，适合继续验证C线的低优先级/回避判断。
- LLM客观评价: D线触发: 说明只是缩量弱反弹，未形成有效修复，适合继续验证C线的低优先级/回避判断。 观察目的: 观察明天盘中是否仍停留在MA5/MA10/MA20下方的弱反弹状态，还是能放量收复MA10/MA20，从而验证C线“回避/观望”是否成立。 主要风险: 盘中出现放量修复并重新站上MA10/MA20，导致当前“非panic、低优先级回避”的判断失效。 对C线反馈: keep_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=keep_avoid; baseline=20260813; task_id=20260813_20260814_600276_d_observe_llm_v2; MA20触发位置=-0.68%

## 2. 601138 工业富联

- 触发: noise_filter / severity=low / fire_count=3
- 时间: forecast_ts=2026-08-14T09:25:36; trade_time=09:25:10; trade_date=2026-08-14
- 实时行情: 现价=65.60; 涨跌幅=+0.57%; 振幅=0.00%; 成交额=0.56亿
- 均线偏离: MA5=-1.86%; MA20=+6.58%; MA60=-3.17%
- C线原始预测: action=watch; direction=up; confidence=55%
- 触发依据: 仍在20日线上方但始终无法收复5日线，且量能和振幅都不强，说明更多是区间内噪声而非有效修复。
- LLM客观评价: D线触发: 仍在20日线上方但始终无法收复5日线，且量能和振幅都不强，说明更多是区间内噪声而非有效修复。 观察目的: 明天盘中验证工业富联在宏观偏空与AI板块减档背景下，能否守住20日线并尝试收复5日线，以确认C线的“watch/up”到底是可延续修复还是弱反弹失败。 主要风险: 短线回撤后失守20日线，且无法重新站上5日线，导致当前上行观察被证伪为弱反弹或转弱。 对C线反馈: watch -> hold_and_observe 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> hold_and_observe; baseline=20260813; task_id=20260813_20260814_601138_d_observe_llm_v2; MA20触发位置=+6.58%

## 3. 601179 中国西电

- 触发: weak_rebound / severity=medium / fire_count=3
- 时间: forecast_ts=2026-08-14T09:25:38; trade_time=09:25:26; trade_date=2026-08-14
- 实时行情: 现价=13.81; 涨跌幅=-0.29%; 振幅=0.00%; 成交额=0.06亿
- 均线偏离: MA5=-0.76%; MA20=+2.34%; MA60=-4.28%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 仍在MA20之上但无法收复MA5/MA10，说明最多只是弱反弹，尚不足以否定回避判断。
- LLM客观评价: D线触发: 仍在MA20之上但无法收复MA5/MA10，说明最多只是弱反弹，尚不足以否定回避判断。 观察目的: 验证C线“回避/中性”假设：明天盘中是否继续呈现弱于短中期均线的走势，而不是出现有效修复后的趋势切换。 主要风险: 若盘中快速收复MA5和MA10并维持放量，当前回避判断可能被短线修复推翻。 对C线反馈: maintain_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=maintain_avoid; baseline=20260813; task_id=20260813_20260814_601179_d_observe_llm_v2; MA20触发位置=+2.34%

## 4. 002475 立讯精密

- 触发: weak_rebound / severity=medium / fire_count=3
- 时间: forecast_ts=2026-08-14T09:30:42; trade_time=09:30:39; trade_date=2026-08-14
- 实时行情: 现价=56.17; 涨跌幅=+0.20%; 振幅=1.05%; 成交额=1.06亿
- 均线偏离: MA5=-0.34%; MA20=-3.17%; MA60=-12.93%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若只是弱反弹但仍未脱离中期均线压制，属于修复不足，主要用于确认‘反弹不改变结构’。
- LLM客观评价: D线触发: 若只是弱反弹但仍未脱离中期均线压制，属于修复不足，主要用于确认‘反弹不改变结构’。 观察目的: 观察该票次日盘中是否继续运行在MA20下方并维持弱势，以验证C线“avoid/neutral”是否成立，重点看是否出现有效修复或继续破位。 主要风险: 盘中若从MA10/MA20下方快速收复并放量站稳，则“非panic、低优先级回避”的假设会失效。 对C线反馈: avoid -> maintain 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=avoid -> maintain; baseline=20260813; task_id=20260813_20260814_002475_d_observe_llm_v2; MA20触发位置=-3.17%

## 5. 002475 立讯精密

- 触发: noise_filter / severity=low / fire_count=4
- 时间: forecast_ts=2026-08-14T09:55:55; trade_time=09:55:51; trade_date=2026-08-14
- 实时行情: 现价=55.95; 涨跌幅=-0.20%; 振幅=1.93%; 成交额=8.67亿
- 均线偏离: MA5=-0.73%; MA20=-3.55%; MA60=-13.27%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若仍在均线下方但量能与振幅都不大，说明更多是常规整理而非可验证的方向性变化。
- LLM客观评价: D线触发: 若仍在均线下方但量能与振幅都不大，说明更多是常规整理而非可验证的方向性变化。 观察目的: 观察该票次日盘中是否继续运行在MA20下方并维持弱势，以验证C线“avoid/neutral”是否成立，重点看是否出现有效修复或继续破位。 主要风险: 盘中若从MA10/MA20下方快速收复并放量站稳，则“非panic、低优先级回避”的假设会失效。 对C线反馈: avoid -> hold 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=avoid -> hold; baseline=20260813; task_id=20260813_20260814_002475_d_observe_llm_v2; MA20触发位置=-3.55%

## 6. 601179 中国西电

- 触发: breakdown_confirm / severity=high / fire_count=4
- 时间: forecast_ts=2026-08-14T10:26:08; trade_time=10:26:04; trade_date=2026-08-14
- 实时行情: 现价=13.45; 涨跌幅=-2.89%; 振幅=2.74%; 成交额=9.02亿
- 均线偏离: MA5=-3.35%; MA20=-0.33%; MA60=-6.77%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 回到MA20下方且短线均线同时失守，说明弱势延续而不是正常噪音波动。
- LLM客观评价: D线触发: 回到MA20下方且短线均线同时失守，说明弱势延续而不是正常噪音波动。 观察目的: 验证C线“回避/中性”假设：明天盘中是否继续呈现弱于短中期均线的走势，而不是出现有效修复后的趋势切换。 主要风险: 若盘中快速收复MA5和MA10并维持放量，当前回避判断可能被短线修复推翻。 对C线反馈: confirm_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=confirm_avoid; baseline=20260813; task_id=20260813_20260814_601179_d_observe_llm_v2; MA20触发位置=-0.33%
