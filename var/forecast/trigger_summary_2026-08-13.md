# D线盘中触发汇总

- updated_at: 2026-08-13T14:35:17
- trade_date: 2026-08-13
- triggers: 8
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 600276 恒瑞医药

- 触发: noise_filter / severity=low / fire_count=1
- 时间: forecast_ts=2026-08-13T09:28:27; trade_time=09:28:07; trade_date=2026-08-13
- 实时行情: 现价=54.05; 涨跌幅=-0.57%; 振幅=0.00%; 成交额=0.22亿
- 均线偏离: MA5=+0.00%; MA20=-0.20%; MA60=+4.39%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明只是围绕MA20的低波动整理，没有形成可验证的方向性行为。
- LLM客观评价: D线触发: 说明只是围绕MA20的低波动整理，没有形成可验证的方向性行为。 观察目的: 明天盘中观察恒瑞医药是否只是低波动横盘，还是出现放量重回MA20/MA10的修复，从而验证C线‘回避/中性’假设。 主要风险: 盘中放量重新站上MA20/MA10，导致C线的回避判断失效。 对C线反馈: avoid -> hold_watch 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=avoid -> hold_watch; baseline=20260812; task_id=20260812_20260813_600276_d_observe_llm_v2; MA20触发位置=-0.20%

## 2. 600875 东方电气

- 触发: noise_filter / severity=low / fire_count=2
- 时间: forecast_ts=2026-08-13T09:28:29; trade_time=09:28:02; trade_date=2026-08-13
- 实时行情: 现价=27.56; 涨跌幅=+0.25%; 振幅=0.00%; 成交额=0.03亿
- 均线偏离: MA5=+1.20%; MA20=+4.70%; MA60=-7.28%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若只是20日线上方的低振幅、低量能震荡，说明没有形成可验证的强势或破位信号，C线的低优先级回避可继续保留。
- LLM客观评价: D线触发: 若只是20日线上方的低振幅、低量能震荡，说明没有形成可验证的强势或破位信号，C线的低优先级回避可继续保留。 观察目的: 验证这只票次日是否只是20日线上方的低优先级震荡，还是会出现放量失守或放量突破，从而证伪 C线的回避判断。 主要风险: 当前价格虽在20日线上方，但仍受60日线压制且近5日走势偏弱；盘中若出现放量向上突破并站稳60日线，C线的“avoid/neutral”假设会被推翻。 对C线反馈: avoid -> keep 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=avoid -> keep; baseline=20260812; task_id=20260812_20260813_600875_d_observe_llm_v2; MA20触发位置=+4.70%

## 3. 601138 工业富联

- 触发: reclaim_confirm / severity=high / fire_count=1
- 时间: forecast_ts=2026-08-13T09:28:31; trade_time=09:28:09; trade_date=2026-08-13
- 实时行情: 现价=67.99; 涨跌幅=+3.64%; 振幅=0.00%; 成交额=1.64亿
- 均线偏离: MA5=+0.80%; MA20=+10.66%; MA60=+0.29%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 说明盘中不仅守住20日线，还重新收复5日线并有一定量价配合，属于对C线上行假设的正向确认。
- LLM客观评价: D线触发: 说明盘中不仅守住20日线，还重新收复5日线并有一定量价配合，属于对C线上行假设的正向确认。 观察目的: 观察明天盘中能否从收盘回撤状态中重新站回5日线并守住20日线，以验证C线“watch/up”是否对应短线延续而非仅是高位修复。 主要风险: 高位回撤后无法重新收复短期均线，导致强势预期被证伪，尤其是5日线压制下出现弱反弹或直接跌破20日线。 对C线反馈: watch -> keep_positive 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> keep_positive; baseline=20260812; task_id=20260812_20260813_601138_d_observe_llm_v2; MA20触发位置=+10.66%

## 4. 601179 中国西电

- 触发: noise_filter / severity=low / fire_count=2
- 时间: forecast_ts=2026-08-13T09:28:33; trade_time=09:28:07; trade_date=2026-08-13
- 实时行情: 现价=13.79; 涨跌幅=0.00%; 振幅=0.00%; 成交额=0.03亿
- 均线偏离: MA5=-1.16%; MA20=+3.01%; MA60=-4.77%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明盘中只是低波动横盘或弱修复噪音，不足以对C线形成强证伪或强确认
- LLM客观评价: D线触发: 说明盘中只是低波动横盘或弱修复噪音，不足以对C线形成强证伪或强确认 观察目的: 观察次日盘中是否仅表现为弱反弹/缩量横盘，还是对MA5与MA20形成有效收复或失守，以验证C线“回避”判断是否成立 主要风险: 盘中快速收复MA5并站稳MA20，说明原先的回避假设被削弱，次日不再只是弱修复 对C线反馈: ignore_noise 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=ignore_noise; baseline=20260812; task_id=20260812_20260813_601179_d_observe_llm_v2; MA20触发位置=+3.01%

## 5. 601138 工业富联

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-08-13T09:38:38; trade_time=09:38:35; trade_date=2026-08-13
- 实时行情: 现价=67.22; 涨跌幅=+2.47%; 振幅=1.34%; 成交额=16.62亿
- 均线偏离: MA5=-0.34%; MA20=+9.41%; MA60=-0.85%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 说明仍站在20日线上方，但对5日线缺乏有效修复，盘中更像弱反弹而不是趋势延续。
- LLM客观评价: D线触发: 说明仍站在20日线上方，但对5日线缺乏有效修复，盘中更像弱反弹而不是趋势延续。 观察目的: 观察明天盘中能否从收盘回撤状态中重新站回5日线并守住20日线，以验证C线“watch/up”是否对应短线延续而非仅是高位修复。 主要风险: 高位回撤后无法重新收复短期均线，导致强势预期被证伪，尤其是5日线压制下出现弱反弹或直接跌破20日线。 对C线反馈: watch -> lower_conviction 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> lower_conviction; baseline=20260812; task_id=20260812_20260813_601138_d_observe_llm_v2; MA20触发位置=+9.41%

## 6. 002475 立讯精密

- 触发: noise_filter / severity=low / fire_count=2
- 时间: forecast_ts=2026-08-13T10:34:03; trade_time=10:34:00; trade_date=2026-08-13
- 实时行情: 现价=56.98; 涨跌幅=-0.65%; 振幅=3.28%; 成交额=31.08亿
- 均线偏离: MA5=+1.15%; MA20=-2.24%; MA60=-11.99%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 用于过滤均线附近的窄幅震荡，避免把普通波动误判成有效修复或有效破位
- LLM客观评价: D线触发: 用于过滤均线附近的窄幅震荡，避免把普通波动误判成有效修复或有效破位 观察目的: 验证次日盘中是否继续受MA20压制、只出现弱反弹无量，还是放量收复MA20从而推翻C线的回避判断 主要风险: 若盘中有效收复MA20并伴随量能抬升，则当前“非panic且评分<2所以回避”的假设会被证伪 对C线反馈: keep_observing 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=keep_observing; baseline=20260812; task_id=20260812_20260813_002475_d_observe_llm_v2; MA20触发位置=-2.24%

## 7. 601179 中国西电

- 触发: reclaim_confirm / severity=high / fire_count=3
- 时间: forecast_ts=2026-08-13T13:34:50; trade_time=13:34:45; trade_date=2026-08-13
- 实时行情: 现价=14.00; 涨跌幅=+1.52%; 振幅=2.54%; 成交额=12.32亿
- 均线偏离: MA5=+0.34%; MA20=+4.58%; MA60=-3.32%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明短线修复有效并重新站回关键均线区域，会直接削弱“回避”假设
- LLM客观评价: D线触发: 说明短线修复有效并重新站回关键均线区域，会直接削弱“回避”假设 观察目的: 观察次日盘中是否仅表现为弱反弹/缩量横盘，还是对MA5与MA20形成有效收复或失守，以验证C线“回避”判断是否成立 主要风险: 盘中快速收复MA5并站稳MA20，说明原先的回避假设被削弱，次日不再只是弱修复 对C线反馈: falsify_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=falsify_avoid; baseline=20260812; task_id=20260812_20260813_601179_d_observe_llm_v2; MA20触发位置=+4.58%

## 8. 002475 立讯精密

- 触发: breakdown_confirm / severity=high / fire_count=3
- 时间: forecast_ts=2026-08-13T14:35:16; trade_time=14:35:12; trade_date=2026-08-13
- 实时行情: 现价=56.33; 涨跌幅=-1.78%; 振幅=4.24%; 成交额=53.76亿
- 均线偏离: MA5=-0.00%; MA20=-3.35%; MA60=-12.99%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明不仅未修复MA20压制，且下行扩展或波动放大，回避假设得到加强
- LLM客观评价: D线触发: 说明不仅未修复MA20压制，且下行扩展或波动放大，回避假设得到加强 观察目的: 验证次日盘中是否继续受MA20压制、只出现弱反弹无量，还是放量收复MA20从而推翻C线的回避判断 主要风险: 若盘中有效收复MA20并伴随量能抬升，则当前“非panic且评分<2所以回避”的假设会被证伪 对C线反馈: confirm_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=confirm_avoid; baseline=20260812; task_id=20260812_20260813_002475_d_observe_llm_v2; MA20触发位置=-3.35%
