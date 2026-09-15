# D线盘中触发汇总

- updated_at: 2026-08-18T10:20:51
- trade_date: 2026-08-18
- triggers: 4
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 002475 立讯精密

- 触发: reclaim_confirm / severity=medium / fire_count=3
- 时间: forecast_ts=2026-08-18T09:25:22; trade_time=09:25:00; trade_date=2026-08-18
- 实时行情: 现价=58.87; 涨跌幅=+0.05%; 振幅=0.00%; 成交额=0.91亿
- 均线偏离: MA5=+3.48%; MA20=+1.44%; MA60=-8.15%
- C线原始预测: action=watch; direction=up; confidence=55%
- 触发依据: 说明价格结构仍在短中期均线之上，且盘中有一定延续性，C线的看多观察假设得到支持。
- LLM客观评价: D线触发: 说明价格结构仍在短中期均线之上，且盘中有一定延续性，C线的看多观察假设得到支持。 观察目的: 明天盘中主要验证立讯精密是否能在强看空宏观与AI闸门减档背景下继续守住20日线并延续右侧修复，而不是冲高后转为回落失守。 主要风险: 核心风险是盘中跌回20日线下方并伴随放量或波动放大，说明C线的“watch/up”假设只剩弱反弹而非有效延续。 对C线反馈: watch -> hold_confirm 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> hold_confirm; baseline=20260817; task_id=20260817_20260818_002475_d_observe_llm_v2; MA20触发位置=+1.44%

## 2. 600875 东方电气

- 触发: breakout_confirm / severity=high / fire_count=2
- 时间: forecast_ts=2026-08-18T09:35:28; trade_time=09:35:24; trade_date=2026-08-18
- 实时行情: 现价=28.40; 涨跌幅=+1.50%; 振幅=2.18%; 成交额=1.77亿
- 均线偏离: MA5=+4.25%; MA20=+6.67%; MA60=-2.96%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若在高位继续站稳并放量上攻，说明并非低优先级回避场景，C线的avoid前提需要复核。
- LLM客观评价: D线触发: 若在高位继续站稳并放量上攻，说明并非低优先级回避场景，C线的avoid前提需要复核。 观察目的: 明天盘中重点验证这只票是否只是高位弱震荡/回落，而不是在当前高位继续放量走强，从而检验C线的回避判断是否成立。 主要风险: 高位承接后重新转强并放量突破，导致原本的回避假设失效。 对C线反馈: invalidate_avoid -> review_positive_edge 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=invalidate_avoid -> review_positive_edge; baseline=20260817; task_id=20260817_20260818_600875_d_observe_llm_v2; MA20触发位置=+6.67%

## 3. 601179 中国西电

- 触发: reclaim_confirm / severity=medium / fire_count=1
- 时间: forecast_ts=2026-08-18T09:35:31; trade_time=09:35:24; trade_date=2026-08-18
- 实时行情: 现价=13.99; 涨跌幅=+0.29%; 振幅=2.08%; 成交额=2.19亿
- 均线偏离: MA5=+1.52%; MA20=+2.35%; MA60=-2.48%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明盘中重新站回短中期均线并伴随动能回升，属于对回避假设的反证。
- LLM客观评价: D线触发: 说明盘中重新站回短中期均线并伴随动能回升，属于对回避假设的反证。 观察目的: 验证 C线“回避/中性”假设：在宏观强看空背景下，观察中国西电次日是否继续弱于短中期均线、放量下探，还是出现有效回收20日线的修复。 主要风险: 若盘中放量站回20日线并同步修复短中期动能，C线的回避判断会被削弱。 对C线反馈: avoid -> challenge / confidence_down 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=avoid -> challenge / confidence_down; baseline=20260817; task_id=20260817_20260818_601179_d_observe_llm_v2; MA20触发位置=+2.35%

## 4. 601138 工业富联

- 触发: breakdown_confirm / severity=high / fire_count=1
- 时间: forecast_ts=2026-08-18T10:20:51; trade_time=10:20:49; trade_date=2026-08-18
- 实时行情: 现价=66.24; 涨跌幅=-2.92%; 振幅=2.35%; 成交额=45.55亿
- 均线偏离: MA5=-0.02%; MA20=+5.87%; MA60=-2.27%
- C线原始预测: action=watch; direction=up; confidence=55%
- 触发依据: 说明高位结构被破坏且短线转弱，若伴随放量或近5日回撤扩大，则可客观证伪“强势延续”的盘中假设。
- LLM客观评价: D线触发: 说明高位结构被破坏且短线转弱，若伴随放量或近5日回撤扩大，则可客观证伪“强势延续”的盘中假设。 观察目的: 验证工业富联在宏观强看空背景下，次日盘中能否继续维持高位强势并守住短均线，从而确认 C 线的“看多观察”假设。 主要风险: 高位位置偏高且宏观环境压制，最需要防范的是盘中冲高后失守短均线，演变为弱反弹或高位回落。 对C线反馈: watch_to_avoid_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch_to_avoid_review; baseline=20260817; task_id=20260817_20260818_601138_d_observe_llm_v2; MA20触发位置=+5.87%
