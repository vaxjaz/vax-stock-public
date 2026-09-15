# D线盘中触发汇总

- updated_at: 2026-09-01T10:41:24
- trade_date: 2026-09-01
- triggers: 6
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 002475 立讯精密

- 触发: weak_rebound / severity=low / fire_count=2
- 时间: forecast_ts=2026-09-01T09:25:23; trade_time=09:25:00; trade_date=2026-09-01
- 实时行情: 现价=57.55; 涨跌幅=-0.12%; 振幅=0.00%; 成交额=0.15亿
- 均线偏离: MA5=+1.55%; MA20=+2.69%; MA60=-6.02%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明只是低能量修复而非有效趋势确认，可用于区分弱反弹与真正转强。
- LLM客观评价: D线触发: 说明只是低能量修复而非有效趋势确认，可用于区分弱反弹与真正转强。 观察目的: 明天盘中验证该票在强看空大盘与AI闸门收缩背景下，是否只能维持弱修复/横盘，还是会因失守短均线并放大波动而证实 C 线的“回避”判断。 主要风险: 20日位置偏高且主力近10日净流出，若盘中跌回短均线下方并伴随波动放大，说明当前并非可持续修复而是高位转弱。 对C线反馈: watch_then_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。 ⚠️[铁律校验] 检测到疑似越界(盘中新评分/买卖价/资金臆测), 以EOD报告为准, 盘中未定论
- C线反哺线索: expected_feedback_to_c=watch_then_review; baseline=20260831; task_id=20260831_20260901_002475_d_observe_llm_v2; MA20触发位置=+2.69%

## 2. 600875 东方电气

- 触发: risk_off_confirm / severity=medium / fire_count=2
- 时间: forecast_ts=2026-09-01T09:25:26; trade_time=09:25:03; trade_date=2026-09-01
- 实时行情: 现价=25.50; 涨跌幅=-0.97%; 振幅=0.00%; 成交额=0.05亿
- 均线偏离: MA5=-0.63%; MA20=-4.28%; MA60=-8.15%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明弱势仍在延续，且短线修复力度不足，适合继续把它归为低优先级观察对象。
- LLM客观评价: D线触发: 说明弱势仍在延续，且短线修复力度不足，适合继续把它归为低优先级观察对象。 观察目的: 明天盘中观察这只票是否继续压在MA20下方并只能走弱反弹，以验证C线“avoid/neutral”是否成立。 主要风险: 盘中快速收复MA20/MA10并伴随放量，导致“非panic且应回避”的判断被证伪。 对C线反馈: maintain_avoid / confirm_no_followthrough 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=maintain_avoid / confirm_no_followthrough; baseline=20260831; task_id=20260831_20260901_600875_d_observe_llm_v2; MA20触发位置=-4.28%

## 3. 601138 工业富联

- 触发: weak_rebound / severity=low / fire_count=4
- 时间: forecast_ts=2026-09-01T09:25:28; trade_time=09:25:04; trade_date=2026-09-01
- 实时行情: 现价=64.35; 涨跌幅=-0.76%; 振幅=0.00%; 成交额=0.25亿
- 均线偏离: MA5=+2.64%; MA20=-0.20%; MA60=-2.19%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若只是小幅反弹且量能不配合，更像弱修复噪音，不足以推翻回避判断。
- LLM客观评价: D线触发: 若只是小幅反弹且量能不配合，更像弱修复噪音，不足以推翻回避判断。 观察目的: 明天盘中验证这只票在强看空宏观与AI上限受限背景下，是否仍只是低优先级回避，还是会出现超预期的回补走强或失守走弱。 主要风险: 当前并非恐慌型失控，核心风险是盘中重新站上关键均线后把‘回避’推翻；反过来，若再度跌回20日均线下方则说明弱势延续。 对C线反馈: avoid -> maintain 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=avoid -> maintain; baseline=20260831; task_id=20260831_20260901_601138_d_observe_llm_v2; MA20触发位置=-0.20%

## 4. 601179 中国西电

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-09-01T09:25:30; trade_time=09:25:08; trade_date=2026-09-01
- 实时行情: 现价=12.66; 涨跌幅=0.00%; 振幅=0.00%; 成交额=0.02亿
- 均线偏离: MA5=-1.37%; MA20=-5.90%; MA60=-8.13%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明盘中虽然有反弹动作，但仍未完成对短中期均线的修复，属于弱反弹而非趋势转强。
- LLM客观评价: D线触发: 说明盘中虽然有反弹动作，但仍未完成对短中期均线的修复，属于弱反弹而非趋势转强。 观察目的: 验证中国西电次日是否仍处于弱势修复失败状态：能否收复20日线/10日线，还是继续在中短期均线下方走弱。 主要风险: 在宏观强看空和自身趋势偏弱背景下，盘中反弹如果无法修复MA20/MA10，说明C线的回避判断仍然成立；若进一步失守MA60，则弱势延续风险加大。 对C线反馈: confirm_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=confirm_avoid; baseline=20260831; task_id=20260831_20260901_601179_d_observe_llm_v2; MA20触发位置=-5.90%

## 5. 601138 工业富联

- 触发: breakdown_confirm / severity=high / fire_count=5
- 时间: forecast_ts=2026-09-01T09:45:44; trade_time=09:45:40; trade_date=2026-09-01
- 实时行情: 现价=63.50; 涨跌幅=-2.07%; 振幅=1.82%; 成交额=11.68亿
- 均线偏离: MA5=+1.29%; MA20=-1.52%; MA60=-3.48%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若盘中重新跌破20日线且相对60日线继续走弱，说明回避逻辑得到强化，弱势并未结束。
- LLM客观评价: D线触发: 若盘中重新跌破20日线且相对60日线继续走弱，说明回避逻辑得到强化，弱势并未结束。 观察目的: 明天盘中验证这只票在强看空宏观与AI上限受限背景下，是否仍只是低优先级回避，还是会出现超预期的回补走强或失守走弱。 主要风险: 当前并非恐慌型失控，核心风险是盘中重新站上关键均线后把‘回避’推翻；反过来，若再度跌回20日均线下方则说明弱势延续。 对C线反馈: avoid -> reinforce_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=avoid -> reinforce_avoid; baseline=20260831; task_id=20260831_20260901_601138_d_observe_llm_v2; MA20触发位置=-1.52%

## 6. 600875 东方电气

- 触发: breakdown_confirm / severity=high / fire_count=3
- 时间: forecast_ts=2026-09-01T10:41:23; trade_time=10:41:15; trade_date=2026-09-01
- 实时行情: 现价=25.31; 涨跌幅=-1.71%; 振幅=1.17%; 成交额=4.42亿
- 均线偏离: MA5=-1.37%; MA20=-4.99%; MA60=-8.83%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明次日仍是弱势延续，且下方承压没有缓解，C线的回避判断得到强化。
- LLM客观评价: D线触发: 说明次日仍是弱势延续，且下方承压没有缓解，C线的回避判断得到强化。 观察目的: 明天盘中观察这只票是否继续压在MA20下方并只能走弱反弹，以验证C线“avoid/neutral”是否成立。 主要风险: 盘中快速收复MA20/MA10并伴随放量，导致“非panic且应回避”的判断被证伪。 对C线反馈: maintain_avoid / strengthen_low_priority 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=maintain_avoid / strengthen_low_priority; baseline=20260831; task_id=20260831_20260901_600875_d_observe_llm_v2; MA20触发位置=-4.99%
