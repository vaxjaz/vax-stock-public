# D线盘中触发汇总

- updated_at: 2026-08-17T13:39:41
- trade_date: 2026-08-17
- triggers: 3
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 002475 立讯精密

- 触发: weak_rebound / severity=medium / fire_count=3
- 时间: forecast_ts=2026-08-17T09:28:07; trade_time=09:25:00; trade_date=2026-08-17
- 实时行情: 现价=56.61; 涨跌幅=+0.05%; 振幅=0.00%; 成交额=0.17亿
- 均线偏离: MA5=+0.58%; MA20=-2.29%; MA60=-11.99%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若只是上涨但仍未站上MA20且量能偏弱，属于典型弱反弹，更多是验证‘不追高、维持观察’而不是确认转强。
- LLM客观评价: D线触发: 若只是上涨但仍未站上MA20且量能偏弱，属于典型弱反弹，更多是验证‘不追高、维持观察’而不是确认转强。 观察目的: 验证C线“avoid/neutral”假设：次日盘中是否仍受制于MA20、反弹是否缺乏量能支持，从而确认这只票在强看空大环境下应保持低优先级观察。 主要风险: 盘中出现短暂反弹但无法收复关键均线，随后重新转弱，说明当前更像弱修复而非趋势转强。 对C线反馈: validate_avoid -> weak_rebound_only 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=validate_avoid -> weak_rebound_only; baseline=20260814; task_id=20260814_20260817_002475_d_observe_llm_v2; MA20触发位置=-2.29%

## 2. 600875 东方电气

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-08-17T09:28:11; trade_time=09:27:49; trade_date=2026-08-17
- 实时行情: 现价=27.00; 涨跌幅=+0.33%; 振幅=0.00%; 成交额=0.07亿
- 均线偏离: MA5=-0.31%; MA20=+1.94%; MA60=-8.17%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 反弹但仍压在5日线下且量能不足，属于弱修复，更多是对回避判断的边际确认而非证伪。
- LLM客观评价: D线触发: 反弹但仍压在5日线下且量能不足，属于弱修复，更多是对回避判断的边际确认而非证伪。 观察目的: 观察次日盘中是否出现对20日线的有效失守或有效收复，以验证C线“回避/低优先级”判断是否成立。 主要风险: 盘中若出现放量收复并稳定在5日线与20日线上方，说明当前回避结论可能被短线修复行情推翻。 对C线反馈: maintain_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=maintain_avoid; baseline=20260814; task_id=20260814_20260817_600875_d_observe_llm_v2; MA20触发位置=+1.94%

## 3. 002475 立讯精密

- 触发: reclaim_confirm / severity=high / fire_count=4
- 时间: forecast_ts=2026-08-17T13:39:41; trade_time=13:39:36; trade_date=2026-08-17
- 实时行情: 现价=58.53; 涨跌幅=+3.45%; 振幅=4.05%; 成交额=48.27亿
- 均线偏离: MA5=+3.99%; MA20=+1.03%; MA60=-9.00%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若盘中能同时收复MA10和MA20并伴随量能抬升，说明当前并非单纯弱势回避结构，C线的avoid假设被明显削弱。
- LLM客观评价: D线触发: 若盘中能同时收复MA10和MA20并伴随量能抬升，说明当前并非单纯弱势回避结构，C线的avoid假设被明显削弱。 观察目的: 验证C线“avoid/neutral”假设：次日盘中是否仍受制于MA20、反弹是否缺乏量能支持，从而确认这只票在强看空大环境下应保持低优先级观察。 主要风险: 盘中出现短暂反弹但无法收复关键均线，随后重新转弱，说明当前更像弱修复而非趋势转强。 对C线反馈: falsify_avoid -> review_higher_attention 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=falsify_avoid -> review_higher_attention; baseline=20260814; task_id=20260814_20260817_002475_d_observe_llm_v2; MA20触发位置=+1.03%
