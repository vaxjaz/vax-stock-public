# D线盘中触发汇总

- updated_at: 2026-09-07T09:34:53
- trade_date: 2026-09-07
- triggers: 6
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 002475 立讯精密

- 触发: breakdown_confirm / severity=high / fire_count=3
- 时间: forecast_ts=2026-09-07T09:29:37; trade_time=09:25:00; trade_date=2026-09-07
- 实时行情: 现价=54.60; 涨跌幅=+0.55%; 振幅=0.00%; 成交额=0.25亿
- 均线偏离: MA5=-3.22%; MA20=-2.59%; MA60=-9.83%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明次日不是正常波动，而是继续处在短中期均线下方的弱势延续，支持C线的回避判断。
- LLM客观评价: D线触发: 说明次日不是正常波动，而是继续处在短中期均线下方的弱势延续，支持C线的回避判断。 观察目的: 验证C线“非panic且右侧评分偏低，次日大概率回避”的假设：看它是否继续弱于短均线并且反弹无法形成有效回收。 主要风险: 如果盘中快速收复5日/20日附近失地并伴随放量，则“avoid/neutral”判断会被削弱，说明弱势并非延续而是修复启动。 对C线反馈: action_avoid -> confirm 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=action_avoid -> confirm; baseline=20260904; task_id=20260904_20260907_002475_d_observe_llm_v2; MA20触发位置=-2.59%

## 2. 002475 立讯精密

- 触发: weak_rebound / severity=medium / fire_count=4
- 时间: forecast_ts=2026-09-07T09:29:41; trade_time=09:25:00; trade_date=2026-09-07
- 实时行情: 现价=54.60; 涨跌幅=+0.55%; 振幅=0.00%; 成交额=0.25亿
- 均线偏离: MA5=-3.22%; MA20=-2.59%; MA60=-9.83%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明盘中虽然反弹，但仍未摆脱中期均线压制，属于弱修复而非有效转强。
- LLM客观评价: D线触发: 说明盘中虽然反弹，但仍未摆脱中期均线压制，属于弱修复而非有效转强。 观察目的: 验证C线“非panic且右侧评分偏低，次日大概率回避”的假设：看它是否继续弱于短均线并且反弹无法形成有效回收。 主要风险: 如果盘中快速收复5日/20日附近失地并伴随放量，则“avoid/neutral”判断会被削弱，说明弱势并非延续而是修复启动。 对C线反馈: action_avoid -> maintain 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=action_avoid -> maintain; baseline=20260904; task_id=20260904_20260907_002475_d_observe_llm_v2; MA20触发位置=-2.59%

## 3. 601138 工业富联

- 触发: reclaim_confirm / severity=high / fire_count=1
- 时间: forecast_ts=2026-09-07T09:29:43; trade_time=09:29:26; trade_date=2026-09-07
- 实时行情: 现价=64.60; 涨跌幅=+1.43%; 振幅=0.00%; 成交额=0.63亿
- 均线偏离: MA5=+2.06%; MA20=+1.02%; MA60=-0.95%
- C线原始预测: action=watch; direction=up; confidence=55%
- 触发依据: 说明短线已重新站回关键均线并获得量能或动能配合，C线的向上观察得到正向验证
- LLM客观评价: D线触发: 说明短线已重新站回关键均线并获得量能或动能配合，C线的向上观察得到正向验证 观察目的: 验证次日盘中能否把当前“略低于MA20、仍强于MA5/MA10”的弱修复延续为站回MA20；如果做不到，则确认在宏观看空背景下的反弹失效 主要风险: 当前仍在MA20下方且低于MA60，叠加宏观看空与AI算力上限偏紧，最需要防范的是弱反弹后重新回落并继续走弱 对C线反馈: watch -> validate_up 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> validate_up; baseline=20260904; task_id=20260904_20260907_601138_d_observe_llm_v2; MA20触发位置=+1.02%

## 4. 601179 中国西电

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-09-07T09:29:46; trade_time=09:29:18; trade_date=2026-09-07
- 实时行情: 现价=12.64; 涨跌幅=+0.32%; 振幅=0.00%; 成交额=0.04亿
- 均线偏离: MA5=+0.41%; MA20=-3.68%; MA60=-7.70%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明出现反弹但仍未摆脱中期压制，属于弱修复而非趋势反转，适合继续验证“非强势”判断。
- LLM客观评价: D线触发: 说明出现反弹但仍未摆脱中期压制，属于弱修复而非趋势反转，适合继续验证“非强势”判断。 观察目的: 验证 C线“回避/中性”假设：在低评分、弱趋势和偏空宏观下，次日盘中应主要表现为反弹无力、继续受制于 MA20/MA10，而不是形成有效修复。 主要风险: 盘中若快速收复短中期均线并放量延续，说明当前的回避假设可能失效，弱势并非继续延伸而是进入修复段。 对C线反馈: avoid -> watch 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=avoid -> watch; baseline=20260904; task_id=20260904_20260907_601179_d_observe_llm_v2; MA20触发位置=-3.68%

## 5. 600875 东方电气

- 触发: breakdown_confirm / severity=high / fire_count=3
- 时间: forecast_ts=2026-09-07T09:34:50; trade_time=09:34:47; trade_date=2026-09-07
- 实时行情: 现价=24.83; 涨跌幅=-0.96%; 振幅=1.44%; 成交额=0.79亿
- 均线偏离: MA5=-0.86%; MA20=-4.87%; MA60=-9.31%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明弱势继续深化，且下探并非静态横盘，而是有扩展性破位迹象。
- LLM客观评价: D线触发: 说明弱势继续深化，且下探并非静态横盘，而是有扩展性破位迹象。 观察目的: 验证次日盘中是否仍是MA20下方的弱势修复，而不是能推翻C线回避判断的有效重新站稳。 主要风险: 盘中如果只是低位反弹但始终受制于MA20/MA10，说明C线的avoid判断仍成立；若放量收复短中期均线，则该判断会被削弱。 对C线反馈: confirm_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=confirm_avoid; baseline=20260904; task_id=20260904_20260907_600875_d_observe_llm_v2; MA20触发位置=-4.87%

## 6. 601179 中国西电

- 触发: breakdown_confirm / severity=high / fire_count=2
- 时间: forecast_ts=2026-09-07T09:34:53; trade_time=09:34:48; trade_date=2026-09-07
- 实时行情: 现价=12.52; 涨跌幅=-0.63%; 振幅=1.27%; 成交额=0.87亿
- 均线偏离: MA5=-0.54%; MA20=-4.60%; MA60=-8.58%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明弱势没有被盘中修复，且在放量/波动放大下继续远离中期均线，C线的回避逻辑得到强化。
- LLM客观评价: D线触发: 说明弱势没有被盘中修复，且在放量/波动放大下继续远离中期均线，C线的回避逻辑得到强化。 观察目的: 验证 C线“回避/中性”假设：在低评分、弱趋势和偏空宏观下，次日盘中应主要表现为反弹无力、继续受制于 MA20/MA10，而不是形成有效修复。 主要风险: 盘中若快速收复短中期均线并放量延续，说明当前的回避假设可能失效，弱势并非继续延伸而是进入修复段。 对C线反馈: avoid -> reinforce 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=avoid -> reinforce; baseline=20260904; task_id=20260904_20260907_601179_d_observe_llm_v2; MA20触发位置=-4.60%
