# D线盘中触发汇总

- updated_at: 2026-07-23T10:21:05
- trade_date: 2026-07-23
- triggers: 9
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 600276 恒瑞医药

- 触发: noise_filter / severity=low / fire_count=3
- 时间: forecast_ts=2026-07-23T09:30:03; trade_time=09:29:50; trade_date=2026-07-23
- 实时行情: 现价=55.39; 涨跌幅=0.00%; 振幅=0.00%; 成交额=0.30亿
- 均线偏离: MA5=+0.68%; MA20=+2.00%; MA60=+6.80%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 若全天仅窄幅低量波动且动量未改善，则更像横盘噪音，不足以验证C线。
- LLM客观评价: D线触发: 若全天仅窄幅低量波动且动量未改善，则更像横盘噪音，不足以验证C线。 观察目的: 观察恒瑞医药次日盘中能否在弱市背景下稳住MA20并回收MA10，以验证C线的“watch/up”是否成立。 主要风险: 量能不足叠加近期5日回撤，使得盘中若失守MA20，右侧修复预期会被证伪。 对C线反馈: watch -> defer_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> defer_review; baseline=20260722; task_id=20260722_20260723_600276_d_observe_llm_v2; MA20触发位置=+2.00%

## 2. 600900 长江电力

- 触发: noise_filter / severity=low / fire_count=1
- 时间: forecast_ts=2026-07-23T09:30:05; trade_time=09:29:30; trade_date=2026-07-23
- 实时行情: 现价=29.09; 涨跌幅=0.00%; 振幅=0.00%; 成交额=0.52亿
- 均线偏离: MA5=+1.69%; MA20=+5.07%; MA60=+6.34%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若只是高位缩量窄幅震荡，则不构成对C线方向判断的有效证伪，更多属于噪声区间。
- LLM客观评价: D线触发: 若只是高位缩量窄幅震荡，则不构成对C线方向判断的有效证伪，更多属于噪声区间。 观察目的: 验证C线“默认回避/中性”是否成立：次日盘中重点看长江电力在高位是继续缩量横盘，还是出现失守20日线后的回吐转弱；若强势延续，则观察该避让判断是否被推翻。 主要风险: 高位位置偏高且RSI已过热，最需要防范的是盘中转为回撤并失守20日线后形成高位转弱，从而证实回避逻辑。 对C线反馈: hold_observation 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=hold_observation; baseline=20260722; task_id=20260722_20260723_600900_d_observe_llm_v2; MA20触发位置=+5.07%

## 3. 601138 工业富联

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-23T09:30:07; trade_time=09:29:29; trade_date=2026-07-23
- 实时行情: 现价=61.99; 涨跌幅=+2.11%; 振幅=0.00%; 成交额=0.59亿
- 均线偏离: MA5=+3.73%; MA20=-5.21%; MA60=-10.00%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 若出现短反弹但仍明显低于MA20且量能不强，更接近技术性弱修复，需要继续观察是否能转为真正的均线收复。
- LLM客观评价: D线触发: 若出现短反弹但仍明显低于MA20且量能不强，更接近技术性弱修复，需要继续观察是否能转为真正的均线收复。 观察目的: 验证C线的“watch/up”假设：明日盘中是否能从MA20下方的弱势结构转为短均线修复，而不是继续沿MA20/MA60下方下探。 主要风险: 当前股价仍明显低于MA20和MA60，且近5日回撤偏弱、主力资金10日净流出较大；在AI算力板块减档背景下，若盘中不能放量修复，C线的上行观察假设容易失效。 对C线反馈: watch -> partial_repair_not_confirmed 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。 ⚠️[铁律校验] 检测到疑似越界(盘中新评分/买卖价/资金臆测), 以EOD报告为准, 盘中未定论
- C线反哺线索: expected_feedback_to_c=watch -> partial_repair_not_confirmed; baseline=20260722; task_id=20260722_20260723_601138_d_observe_llm_v2; MA20触发位置=-5.21%

## 4. 601179 中国西电

- 触发: weak_rebound / severity=medium / fire_count=4
- 时间: forecast_ts=2026-07-23T09:30:09; trade_time=09:29:27; trade_date=2026-07-23
- 实时行情: 现价=12.70; 涨跌幅=+2.34%; 振幅=0.00%; 成交额=0.30亿
- 均线偏离: MA5=+5.08%; MA20=-5.47%; MA60=-17.61%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若只是低位小幅反弹但仍远离MA20，说明反弹力度不足，更多是弱修复而非趋势扭转。
- LLM客观评价: D线触发: 若只是低位小幅反弹但仍远离MA20，说明反弹力度不足，更多是弱修复而非趋势扭转。 观察目的: 明天盘中重点验证该票是否只能做弱修复、无法有效收复短中期均线，从而确认C线的avoid/neutral判断。 主要风险: 超跌后出现放量快速收复MA10并逼近MA20，导致原先的弱势回避假设被推翻。 对C线反馈: watch_keep_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch_keep_avoid; baseline=20260722; task_id=20260722_20260723_601179_d_observe_llm_v2; MA20触发位置=-5.47%

## 5. 002475 立讯精密

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-23T09:35:14; trade_time=09:35:09; trade_date=2026-07-23
- 实时行情: 现价=59.88; 涨跌幅=+1.22%; 振幅=2.20%; 成交额=4.29亿
- 均线偏离: MA5=+1.15%; MA20=-5.11%; MA60=-12.25%
- C线原始预测: action=candidate_buy; direction=up; confidence=75%
- 触发依据: 说明只是低质量反弹，价格虽有回升但量能和动能不足，不能把它当成趋势确认
- LLM客观评价: D线触发: 说明只是低质量反弹，价格虽有回升但量能和动能不足，不能把它当成趋势确认 观察目的: 验证 C 线 candidate_buy 假设：次日盘中是否能在 AI 板块减档背景下完成对 MA5/MA20 的修复并站稳，还是继续处于弱势回撤/反抽失败状态 主要风险: 最核心风险是价格始终受制于 MA20 且反弹无量，导致右侧修复被证伪并延续最近20日的弱趋势 对C线反馈: candidate_buy -> weak_rebound_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=candidate_buy -> weak_rebound_review; baseline=20260722; task_id=20260722_20260723_002475_d_observe_llm_v2; MA20触发位置=-5.11%

## 6. 603009 北特科技

- 触发: breakdown_confirm / severity=high / fire_count=1
- 时间: forecast_ts=2026-07-23T09:40:19; trade_time=09:40:17; trade_date=2026-07-23
- 实时行情: 现价=40.78; 涨跌幅=-3.34%; 振幅=3.74%; 成交额=0.59亿
- 均线偏离: MA5=-4.03%; MA20=-12.46%; MA60=-15.15%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 表示下探进一步扩大，弱势并未被修复，C线的回避判断被强化。
- LLM客观评价: D线触发: 表示下探进一步扩大，弱势并未被修复，C线的回避判断被强化。 观察目的: 明天盘中重点验证：在当前已显著低于中短期均线、且量能偏弱的背景下，北特科技是否只能出现弱反弹而无法完成对MA5/MA20的有效修复，从而支持C线的回避判断。 主要风险: 核心风险是盘中出现短暂反抽后再次回落，说明弱势延续而非真正修复，C线的低置信度回避判断需要被进一步确认。 对C线反馈: validate_avoid / downside_extension 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=validate_avoid / downside_extension; baseline=20260722; task_id=20260722_20260723_603009_d_observe_llm_v2; MA20触发位置=-12.46%

## 7. 601179 中国西电

- 触发: reclaim_confirm / severity=high / fire_count=5
- 时间: forecast_ts=2026-07-23T09:50:31; trade_time=09:50:26; trade_date=2026-07-23
- 实时行情: 现价=13.18; 涨跌幅=+6.20%; 振幅=4.27%; 成交额=10.50亿
- 均线偏离: MA5=+9.05%; MA20=-1.89%; MA60=-14.50%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若盘中能够收复MA10并显著逼近MA20，且不是无量修复，则说明超跌后的技术性反弹开始具备反转观察价值。
- LLM客观评价: D线触发: 若盘中能够收复MA10并显著逼近MA20，且不是无量修复，则说明超跌后的技术性反弹开始具备反转观察价值。 观察目的: 明天盘中重点验证该票是否只能做弱修复、无法有效收复短中期均线，从而确认C线的avoid/neutral判断。 主要风险: 超跌后出现放量快速收复MA10并逼近MA20，导致原先的弱势回避假设被推翻。 对C线反馈: falsify_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=falsify_avoid; baseline=20260722; task_id=20260722_20260723_601179_d_observe_llm_v2; MA20触发位置=-1.89%

## 8. 603009 北特科技

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-23T10:10:53; trade_time=10:10:50; trade_date=2026-07-23
- 实时行情: 现价=42.58; 涨跌幅=+0.92%; 振幅=4.57%; 成交额=1.39亿
- 均线偏离: MA5=+0.21%; MA20=-8.60%; MA60=-11.40%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 表示盘中虽有反抽，但仍未脱离中期弱势区，且量能未给出有效确认。
- LLM客观评价: D线触发: 表示盘中虽有反抽，但仍未脱离中期弱势区，且量能未给出有效确认。 观察目的: 明天盘中重点验证：在当前已显著低于中短期均线、且量能偏弱的背景下，北特科技是否只能出现弱反弹而无法完成对MA5/MA20的有效修复，从而支持C线的回避判断。 主要风险: 核心风险是盘中出现短暂反抽后再次回落，说明弱势延续而非真正修复，C线的低置信度回避判断需要被进一步确认。 对C线反馈: validate_avoid / weak_rebound_only 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=validate_avoid / weak_rebound_only; baseline=20260722; task_id=20260722_20260723_603009_d_observe_llm_v2; MA20触发位置=-8.60%

## 9. 600875 东方电气

- 触发: reclaim_confirm / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-23T10:21:05; trade_time=10:21:01; trade_date=2026-07-23
- 实时行情: 现价=27.53; 涨跌幅=+5.32%; 振幅=3.79%; 成交额=10.54亿
- 均线偏离: MA5=+7.37%; MA20=-0.41%; MA60=-16.49%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 说明盘中修复已经不是单纯弱反弹，而是开始具备回到均线结构内的确认信号。
- LLM客观评价: D线触发: 说明盘中修复已经不是单纯弱反弹，而是开始具备回到均线结构内的确认信号。 观察目的: 明天盘中重点验证这只票能否在弱市环境下完成对MA5/MA10的修复，并进一步向MA20靠拢，从而确认C线的“watch/up”假设是否成立。 主要风险: 当前价格仍明显低于MA20且近20日趋势偏弱，叠加AI算力链条存在上限约束，核心风险是盘中反弹只能停留在弱修复，无法形成均线重新站稳。 对C线反馈: watch -> strengthen_confidence 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> strengthen_confidence; baseline=20260722; task_id=20260722_20260723_600875_d_observe_llm_v2; MA20触发位置=-0.41%
