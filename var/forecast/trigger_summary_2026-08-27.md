# D线盘中触发汇总

- updated_at: 2026-08-27T10:49:46
- trade_date: 2026-08-27
- triggers: 5
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 002475 立讯精密

- 触发: breakout_confirm / severity=high / fire_count=4
- 时间: forecast_ts=2026-08-27T09:29:09; trade_time=09:25:00; trade_date=2026-08-27
- 实时行情: 现价=57.70; 涨跌幅=+1.03%; 振幅=0.00%; 成交额=1.06亿
- 均线偏离: MA5=+5.42%; MA20=+3.13%; MA60=-6.96%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明出现了超出回避预期的放量修复，C 线的低优先级判断需要被重新审视。
- LLM客观评价: D线触发: 说明出现了超出回避预期的放量修复，C 线的低优先级判断需要被重新审视。 观察目的: 验证 C 线“回避/中性”判断：明日盘中看该票是在强看空宏观和 AI 闸门压制下继续弱势震荡/回落，还是出现放量收复短均线的反向强修复。 主要风险: 如果盘中放量站回 MA5/MA20 并保持强势，C 线的 avoid 假设就会被推翻。 对C线反馈: reconsider_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=reconsider_avoid; baseline=20260826; task_id=20260826_20260827_002475_d_observe_llm_v2; MA20触发位置=+3.13%

## 2. 600276 恒瑞医药

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-08-27T09:29:12; trade_time=09:28:42; trade_date=2026-08-27
- 实时行情: 现价=46.78; 涨跌幅=+0.09%; 振幅=0.00%; 成交额=0.12亿
- 均线偏离: MA5=-1.40%; MA20=-10.08%; MA60=-9.77%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明即便出现反弹，也更像低量能、未收复均线的弱修复，通常不足以推翻回避判断。
- LLM客观评价: D线触发: 说明即便出现反弹，也更像低量能、未收复均线的弱修复，通常不足以推翻回避判断。 观察目的: 观察恒瑞医药次日盘中是否仍处于均线压制下的弱势延续状态，并验证任何反弹能否真正收复短均线来推翻C线回避判断。 主要风险: 盘中超跌修复若同步收复MA5/MA10并改善动能，会削弱“非panic、默认回避”的结论。 对C线反馈: maintain_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=maintain_avoid; baseline=20260826; task_id=20260826_20260827_600276_d_observe_llm_v2; MA20触发位置=-10.08%

## 3. 600875 东方电气

- 触发: breakdown_confirm / severity=high / fire_count=2
- 时间: forecast_ts=2026-08-27T09:29:14; trade_time=09:29:05; trade_date=2026-08-27
- 实时行情: 现价=25.59; 涨跌幅=-0.66%; 振幅=0.00%; 成交额=0.07亿
- 均线偏离: MA5=-0.58%; MA20=-3.91%; MA60=-9.09%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明价格仍在均线下方承压且波动/换手放大，回避与弱势判断得到确认。
- LLM客观评价: D线触发: 说明价格仍在均线下方承压且波动/换手放大，回避与弱势判断得到确认。 观察目的: 验证 C 线“非 panic、评分<2 因而回避”的假设：明天盘中主要看它是否继续运行在 MA20 下方并表现为弱势修复失败，而不是快速重获趋势位置。 主要风险: 盘中若出现有效回收 MA20/MA10 并放量，说明“回避/低优先级”判断可能被修正，C 线的 avoid 假设失效。 对C线反馈: avoid -> confirmed_weakness 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=avoid -> confirmed_weakness; baseline=20260826; task_id=20260826_20260827_600875_d_observe_llm_v2; MA20触发位置=-3.91%

## 4. 601138 工业富联

- 触发: failed_breakout / severity=medium / fire_count=1
- 时间: forecast_ts=2026-08-27T09:29:17; trade_time=09:28:54; trade_date=2026-08-27
- 实时行情: 现价=62.00; 涨跌幅=+2.36%; 振幅=0.00%; 成交额=1.18亿
- 均线偏离: MA5=+1.28%; MA20=-1.84%; MA60=-6.72%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明盘中有修复动作但仍未真正站回关键均线，属于反抽失败，更偏向噪声而非趋势反转。
- LLM客观评价: D线触发: 说明盘中有修复动作但仍未真正站回关键均线，属于反抽失败，更偏向噪声而非趋势反转。 观察目的: 验证C线“回避/中性”假设是否成立：明天盘中重点看工业富联能否在非恐慌环境下继续弱势、反抽失败并维持均线下方。 主要风险: 盘中若快速收复短中期均线并伴随放量，说明当前的回避判断可能被推翻，弱势回撤并非主导。 对C线反馈: watch -> keep_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> keep_avoid; baseline=20260826; task_id=20260826_20260827_601138_d_observe_llm_v2; MA20触发位置=-1.84%

## 5. 601138 工业富联

- 触发: reclaim_confirm / severity=high / fire_count=2
- 时间: forecast_ts=2026-08-27T10:49:46; trade_time=10:49:42; trade_date=2026-08-27
- 实时行情: 现价=64.17; 涨跌幅=+5.94%; 振幅=3.71%; 成交额=56.07亿
- 均线偏离: MA5=+4.82%; MA20=+1.59%; MA60=-3.46%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若盘中重新站上短中期均线并伴随放量，说明弱势假设被削弱，C线回避逻辑需要重新评估。
- LLM客观评价: D线触发: 若盘中重新站上短中期均线并伴随放量，说明弱势假设被削弱，C线回避逻辑需要重新评估。 观察目的: 验证C线“回避/中性”假设是否成立：明天盘中重点看工业富联能否在非恐慌环境下继续弱势、反抽失败并维持均线下方。 主要风险: 盘中若快速收复短中期均线并伴随放量，说明当前的回避判断可能被推翻，弱势回撤并非主导。 对C线反馈: watch -> falsify_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> falsify_avoid; baseline=20260826; task_id=20260826_20260827_601138_d_observe_llm_v2; MA20触发位置=+1.59%
