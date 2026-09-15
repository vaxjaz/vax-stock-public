# D线盘中触发汇总

- updated_at: 2026-08-28T09:26:17
- trade_date: 2026-08-28
- triggers: 3
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 002475 立讯精密

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-08-28T09:26:12; trade_time=09:25:00; trade_date=2026-08-28
- 实时行情: 现价=57.89; 涨跌幅=+1.24%; 振幅=0.00%; 成交额=0.53亿
- 均线偏离: MA5=+4.30%; MA20=+3.58%; MA60=-6.21%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 价格没有失守关键均线，但反弹缺少量能和波动，属于弱修复状态，仍更接近观察而非强势确认。
- LLM客观评价: D线触发: 价格没有失守关键均线，但反弹缺少量能和波动，属于弱修复状态，仍更接近观察而非强势确认。 观察目的: 验证C线“avoid/neutral”是否成立：次日盘中这只票是延续短线修复，还是在关键均线附近转弱并回到低优先级状态；同时检查是否出现放量收复MA60的反证。 主要风险: 在宏观强看空背景下，前一日的短线修复如果无法守住MA20，容易演变成冲高回落或重新转弱；反之，若能放量收复MA60，则C线的回避结论会被推翻。 对C线反馈: watch_hold 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch_hold; baseline=20260827; task_id=20260827_20260828_002475_d_observe_llm_v2; MA20触发位置=+3.58%

## 2. 601138 工业富联

- 触发: reclaim_confirm / severity=medium / fire_count=3
- 时间: forecast_ts=2026-08-28T09:26:14; trade_time=09:26:03; trade_date=2026-08-28
- 实时行情: 现价=64.04; 涨跌幅=+0.28%; 振幅=0.00%; 成交额=1.38亿
- 均线偏离: MA5=+4.02%; MA20=+0.59%; MA60=-3.24%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若盘中能同时站上短中期均线并获得量能/动能支持，说明回避前提被削弱，右侧修复成立度上升。
- LLM客观评价: D线触发: 若盘中能同时站上短中期均线并获得量能/动能支持，说明回避前提被削弱，右侧修复成立度上升。 观察目的: 验证 C线“非 panic 且评分偏低所以回避”的假设：明天盘中重点看工业富联是在强市弱背景下继续守住右侧结构，还是先失守 MA20 后转入回撤。 主要风险: 在大盘强看空、AI 赛道闸门减档、且近10日主力净流出偏重的背景下，股价若失守 MA20，当前的观察等待结构可能被证伪并转向更弱的修复形态。 对C线反馈: avoid_soften 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。 ⚠️[铁律校验] 检测到疑似越界(盘中新评分/买卖价/资金臆测), 以EOD报告为准, 盘中未定论
- C线反哺线索: expected_feedback_to_c=avoid_soften; baseline=20260827; task_id=20260827_20260828_601138_d_observe_llm_v2; MA20触发位置=+0.59%

## 3. 601138 工业富联

- 触发: noise_filter / severity=low / fire_count=4
- 时间: forecast_ts=2026-08-28T09:26:16; trade_time=09:26:03; trade_date=2026-08-28
- 实时行情: 现价=64.04; 涨跌幅=+0.28%; 振幅=0.00%; 成交额=1.38亿
- 均线偏离: MA5=+4.02%; MA20=+0.59%; MA60=-3.24%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若仅在 MA20 附近窄幅震荡、量能不强且 RSI 仍偏弱，说明只是噪音修复，不构成对 C 线回避判断的实质挑战。
- LLM客观评价: D线触发: 若仅在 MA20 附近窄幅震荡、量能不强且 RSI 仍偏弱，说明只是噪音修复，不构成对 C 线回避判断的实质挑战。 观察目的: 验证 C线“非 panic 且评分偏低所以回避”的假设：明天盘中重点看工业富联是在强市弱背景下继续守住右侧结构，还是先失守 MA20 后转入回撤。 主要风险: 在大盘强看空、AI 赛道闸门减档、且近10日主力净流出偏重的背景下，股价若失守 MA20，当前的观察等待结构可能被证伪并转向更弱的修复形态。 对C线反馈: watch_hold 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。 ⚠️[铁律校验] 检测到疑似越界(盘中新评分/买卖价/资金臆测), 以EOD报告为准, 盘中未定论
- C线反哺线索: expected_feedback_to_c=watch_hold; baseline=20260827; task_id=20260827_20260828_601138_d_observe_llm_v2; MA20触发位置=+0.59%
