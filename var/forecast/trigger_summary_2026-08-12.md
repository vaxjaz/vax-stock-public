# D线盘中触发汇总

- updated_at: 2026-08-12T11:17:19
- trade_date: 2026-08-12
- triggers: 3
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 002475 立讯精密

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-08-12T09:26:25; trade_time=09:25:00; trade_date=2026-08-12
- 实时行情: 现价=55.68; 涨跌幅=+0.09%; 振幅=0.00%; 成交额=0.10亿
- 均线偏离: MA5=-0.64%; MA20=-4.72%; MA60=-14.33%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明出现反弹但力度和量能不足，更像弱修复而不是趋势扭转，适合继续验证C线的回避假设。
- LLM客观评价: D线触发: 说明出现反弹但力度和量能不足，更像弱修复而不是趋势扭转，适合继续验证C线的回避假设。 观察目的: 验证C线的回避判断是否成立：重点看次日是否继续运行在MA20下方、弱反弹是否无量、以及是否出现放量收复MA20的反证。 主要风险: 如果盘中放量重新站上MA20并带动短线动量修复，C线基于弱势与低评分得出的avoid判断会被削弱。 对C线反馈: hold_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=hold_avoid; baseline=20260811; task_id=20260811_20260812_002475_d_observe_llm_v2; MA20触发位置=-4.72%

## 2. 601179 中国西电

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-08-12T09:26:28; trade_time=09:26:12; trade_date=2026-08-12
- 实时行情: 现价=13.84; 涨跌幅=+0.29%; 振幅=0.00%; 成交额=0.03亿
- 均线偏离: MA5=-1.68%; MA20=+4.04%; MA60=-4.84%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若仅在20日线上方做弱反弹、但仍压在5日线下且量能不配合，通常只能视为修复未完成。
- LLM客观评价: D线触发: 若仅在20日线上方做弱反弹、但仍压在5日线下且量能不配合，通常只能视为修复未完成。 观察目的: 验证C线“回避”假设：明天盘中重点看中国西电是否在低量环境下继续走弱，还是出现放量修复并重新站稳短均线。 主要风险: 当前处于20日线上方但5日线下方、近5日回撤且量能偏弱，核心风险是弱势延续后对C线回避判断形成实盘证伪。 对C线反馈: watch -> neutral_no_change 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> neutral_no_change; baseline=20260811; task_id=20260811_20260812_601179_d_observe_llm_v2; MA20触发位置=+4.04%

## 3. 600875 东方电气

- 触发: reclaim_confirm / severity=high / fire_count=2
- 时间: forecast_ts=2026-08-12T11:17:19; trade_time=11:17:16; trade_date=2026-08-12
- 实时行情: 现价=27.38; 涨跌幅=+2.20%; 振幅=2.43%; 成交额=7.06亿
- 均线偏离: MA5=+0.20%; MA20=+4.22%; MA60=-8.48%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若同步收复短中期均线并不弱于均量，说明盘中修复力度足以削弱“默认回避”的依据。
- LLM客观评价: D线触发: 若同步收复短中期均线并不弱于均量，说明盘中修复力度足以削弱“默认回避”的依据。 观察目的: 观察明天盘中这只票是否继续弱势并失守20日线，用次日行为验证C线“低评分下默认回避”的判断是否成立。 主要风险: 若盘中快速收复5日线和10日线并进一步站稳20日线，当前回避假设会被明显削弱。 对C线反馈: avoid_to_recheck 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=avoid_to_recheck; baseline=20260811; task_id=20260811_20260812_600875_d_observe_llm_v2; MA20触发位置=+4.22%
