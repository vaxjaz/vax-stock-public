# D线盘中触发汇总

- updated_at: 2026-07-27T09:54:00
- trade_date: 2026-07-27
- triggers: 8
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 002475 立讯精密

- 触发: noise_filter / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-27T09:28:24; trade_time=09:25:00; trade_date=2026-07-27
- 实时行情: 现价=61.00; 涨跌幅=+0.68%; 振幅=0.00%; 成交额=0.18亿
- 均线偏离: MA5=+2.29%; MA20=-1.73%; MA60=-10.25%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 说明盘中只是低量区间震荡或弱反抽，信息增量有限，不足以支持对 C 线作方向性强化。
- LLM客观评价: D线触发: 说明盘中只是低量区间震荡或弱反抽，信息增量有限，不足以支持对 C 线作方向性强化。 观察目的: 验证 C 线“次日偏强、继续观察”的假设：看 002475 是否能在低于 MA20 的位置先收复并稳住短均线，同时用量能判断这次修复是真反弹还是弱修复。 主要风险: 当前价格仍低于 MA20 且 5 日量能偏低，若盘中不能放量收回短均线，C 线的看多观察很容易退化为缩量反抽或继续回落。 对C线反馈: watch -> neutral_check 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> neutral_check; baseline=20260724; task_id=20260724_20260727_002475_d_observe_llm_v2; MA20触发位置=-1.73%

## 2. 600276 恒瑞医药

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-27T09:28:26; trade_time=09:28:11; trade_date=2026-07-27
- 实时行情: 现价=53.90; 涨跌幅=+0.84%; 振幅=0.00%; 成交额=0.56亿
- 均线偏离: MA5=-1.73%; MA20=-1.61%; MA60=+4.03%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 说明盘中有反弹但仍未完成均线修复，且量能/动能不足，更像弱修复而不是趋势确认。
- LLM客观评价: D线触发: 说明盘中有反弹但仍未完成均线修复，且量能/动能不足，更像弱修复而不是趋势确认。 观察目的: 明天重点验证恒瑞医药能否从当前偏弱于MA5/MA20的位置完成盘中收复，并确认C线“看多观察”是否只是弱修复还是具备继续向上延续的条件。 主要风险: 最大风险是反弹无力、始终收不回MA20/MA5，导致当前的向上观察假设退化为弱反弹或进一步走弱。 对C线反馈: watch -> remain_observe 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> remain_observe; baseline=20260724; task_id=20260724_20260727_600276_d_observe_llm_v2; MA20触发位置=-1.61%

## 3. 600900 长江电力

- 触发: noise_filter / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-27T09:28:28; trade_time=09:27:52; trade_date=2026-07-27
- 实时行情: 现价=29.15; 涨跌幅=+0.87%; 振幅=0.00%; 成交额=0.77亿
- 均线偏离: MA5=+0.77%; MA20=+4.35%; MA60=+6.28%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若全天低量窄幅震荡，则更像噪声区间，不足以单独推翻或强化C线判断。
- LLM客观评价: D线触发: 若全天低量窄幅震荡，则更像噪声区间，不足以单独推翻或强化C线判断。 观察目的: 验证C线“回避/低优先级”是否成立：明天盘中重点看长江电力能否继续维持高位但不放量突破，还是出现失守短线均线后的走弱。 主要风险: 高位偏热状态下若盘中继续放量上攻，C线的回避判断会被推翻。 对C线反馈: watch -> hold 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> hold; baseline=20260724; task_id=20260724_20260727_600900_d_observe_llm_v2; MA20触发位置=+4.35%

## 4. 601179 中国西电

- 触发: failed_breakout / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-27T09:28:30; trade_time=09:28:13; trade_date=2026-07-27
- 实时行情: 现价=13.32; 涨跌幅=-1.70%; 振幅=0.00%; 成交额=0.82亿
- 均线偏离: MA5=+3.59%; MA20=+0.56%; MA60=-12.93%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 盘中未能延续、转为冲高回落，说明反弹质量不足，更接近弱修复而非有效突破。
- LLM客观评价: D线触发: 盘中未能延续、转为冲高回落，说明反弹质量不足，更接近弱修复而非有效突破。 观察目的: 验证C线“回避/非正收益”假设：明天盘中重点看该股是否只是短线反弹后回落，还是会继续失守短中期均线并走弱。 主要风险: 盘中继续放量站稳MA5/MA20并向上延伸，从而推翻当前回避判断。 对C线反馈: keep_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=keep_avoid; baseline=20260724; task_id=20260724_20260727_601179_d_observe_llm_v2; MA20触发位置=+0.56%

## 5. 603009 北特科技

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-27T09:28:32; trade_time=09:27:57; trade_date=2026-07-27
- 实时行情: 现价=38.34; 涨跌幅=-1.67%; 振幅=0.00%; 成交额=0.03亿
- 均线偏离: MA5=-6.97%; MA20=-16.90%; MA60=-19.86%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 出现低位反弹但仍压在短均线下且指标未真正修复，说明只是弱修复，不足以推翻回避假设。
- LLM客观评价: D线触发: 出现低位反弹但仍压在短均线下且指标未真正修复，说明只是弱修复，不足以推翻回避假设。 观察目的: 明天盘中验证 C线“非 panic、评分<2、默认回避”是否会被持续破位和弱修复行为证实，还是被快速收复短均线推翻。 主要风险: 当前已明显弱于 MA5/MA20，若盘中只是超卖后的无量反抽而不能站回关键均线，回避假设会被继续证实；若出现快速收复并维持，说明 C 线偏保守可能失效。 对C线反馈: watch -> maintain_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> maintain_avoid; baseline=20260724; task_id=20260724_20260727_603009_d_observe_llm_v2; MA20触发位置=-16.90%

## 6. 600875 东方电气

- 触发: weak_rebound / severity=low / fire_count=2
- 时间: forecast_ts=2026-07-27T09:33:37; trade_time=09:33:34; trade_date=2026-07-27
- 实时行情: 现价=25.62; 涨跌幅=+0.16%; 振幅=0.94%; 成交额=0.26亿
- 均线偏离: MA5=-2.09%; MA20=-6.43%; MA60=-21.15%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 说明存在反弹，但仍未摆脱中期均线下方弱势，更像技术性修复而非趋势反转。
- LLM客观评价: D线触发: 说明存在反弹，但仍未摆脱中期均线下方弱势，更像技术性修复而非趋势反转。 观察目的: 验证 C线“watch/up”假设：次日盘中是否能从 20 日线下方的弱势结构中完成修复，还是继续演变为均线下方的延续性回撤。 主要风险: 20日线下方的反弹若缺少有效修复，容易被判定为短暂技术性反抽；在AI闸门减档、市场广度偏弱的背景下，主趋势继续走弱是核心风险。 对C线反馈: watch -> unconfirmed_rebound 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> unconfirmed_rebound; baseline=20260724; task_id=20260724_20260727_600875_d_observe_llm_v2; MA20触发位置=-6.43%

## 7. 601179 中国西电

- 触发: reclaim_confirm / severity=medium / fire_count=3
- 时间: forecast_ts=2026-07-27T09:33:39; trade_time=09:33:33; trade_date=2026-07-27
- 实时行情: 现价=13.90; 涨跌幅=+2.58%; 振幅=5.61%; 成交额=3.49亿
- 均线偏离: MA5=+8.10%; MA20=+4.94%; MA60=-9.14%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若能持续站稳短中期均线并伴随扩量，说明当前回避前提被削弱，需重新评估C线判断。
- LLM客观评价: D线触发: 若能持续站稳短中期均线并伴随扩量，说明当前回避前提被削弱，需重新评估C线判断。 观察目的: 验证C线“回避/非正收益”假设：明天盘中重点看该股是否只是短线反弹后回落，还是会继续失守短中期均线并走弱。 主要风险: 盘中继续放量站稳MA5/MA20并向上延伸，从而推翻当前回避判断。 对C线反馈: invalidate_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=invalidate_avoid; baseline=20260724; task_id=20260724_20260727_601179_d_observe_llm_v2; MA20触发位置=+4.94%

## 8. 601138 工业富联

- 触发: weak_rebound / severity=medium / fire_count=3
- 时间: forecast_ts=2026-07-27T09:54:00; trade_time=09:53:57; trade_date=2026-07-27
- 实时行情: 现价=60.99; 涨跌幅=+1.23%; 振幅=2.67%; 成交额=11.29亿
- 均线偏离: MA5=+1.20%; MA20=-4.99%; MA60=-11.26%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 说明虽然有反弹，但仍未真正摆脱均线压制，动量和参与度都不足，更像弱修复而非趋势恢复。
- LLM客观评价: D线触发: 说明虽然有反弹，但仍未真正摆脱均线压制，动量和参与度都不足，更像弱修复而非趋势恢复。 观察目的: 验证 C线“watch/up”假设能否在盘中完成对MA10与MA20的修复，还是继续停留在MA20下方形成弱反弹后回落。 主要风险: 当前价格仍明显低于MA20，且EOD主力净流入为负；若盘中无法收复MA10并向MA20靠拢，C线的上行判断容易被弱修复证伪。 对C线反馈: watch -> weak_hold 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> weak_hold; baseline=20260724; task_id=20260724_20260727_601138_d_observe_llm_v2; MA20触发位置=-4.99%
