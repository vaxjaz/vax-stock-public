# D线盘中触发汇总

- updated_at: 2026-07-30T10:24:33
- trade_date: 2026-07-30
- triggers: 3
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 600276 恒瑞医药

- 触发: weak_rebound / severity=low / fire_count=1
- 时间: forecast_ts=2026-07-30T09:28:06; trade_time=09:27:39; trade_date=2026-07-30
- 实时行情: 现价=54.05; 涨跌幅=+0.30%; 振幅=0.00%; 成交额=0.20亿
- 均线偏离: MA5=+0.41%; MA20=-1.52%; MA60=+4.42%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 说明盘中虽有反弹，但未形成均线收复和量能配合，更像低质量弱修复。
- LLM客观评价: D线触发: 说明盘中虽有反弹，但未形成均线收复和量能配合，更像低质量弱修复。 观察目的: 验证恒瑞医药在恐慌市场下的 T+1 情绪修复是否能把价格重新拉回并守住 MA10/MA20，而不是只做弱反弹后继续受压。 主要风险: 20日线下方的反弹容易只是噪声，若量能和均线收复都跟不上，C线的上行假设会被证伪。 对C线反馈: panic_rebound_watch -> watch_only 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=panic_rebound_watch -> watch_only; baseline=20260729; task_id=20260729_20260730_600276_d_observe_llm_v2; MA20触发位置=-1.52%

## 2. 002475 立讯精密

- 触发: breakdown_confirm / severity=high / fire_count=3
- 时间: forecast_ts=2026-07-30T10:03:34; trade_time=10:03:30; trade_date=2026-07-30
- 实时行情: 现价=60.01; 涨跌幅=-3.75%; 振幅=3.00%; 成交额=26.18亿
- 均线偏离: MA5=-2.30%; MA20=-2.01%; MA60=-11.27%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 说明盘中不仅没有修复，反而出现对中期支撑的有效跌破或弱势扩散，C线的反弹假设被证伪。
- LLM客观评价: D线触发: 说明盘中不仅没有修复，反而出现对中期支撑的有效跌破或弱势扩散，C线的反弹假设被证伪。 观察目的: 验证 C线的“panic_rebound_watch”假设：在市场恐慌背景下，立讯精密次日盘中是否能通过站回短中期均线并伴随放量来确认情绪修复，而不是冲高回落继续转弱。 主要风险: 恐慌市里仅有技术性反弹但无法收复并稳定在MA20附近，导致反弹被快速证伪，重新回到弱势整理或继续下探。 对C线反馈: watch -> avoid_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> avoid_review; baseline=20260729; task_id=20260729_20260730_002475_d_observe_llm_v2; MA20触发位置=-2.01%

## 3. 601138 工业富联

- 触发: breakdown_confirm / severity=high / fire_count=1
- 时间: forecast_ts=2026-07-30T10:24:33; trade_time=10:24:16; trade_date=2026-07-30
- 实时行情: 现价=54.10; 涨跌幅=-6.32%; 振幅=5.78%; 成交额=38.48亿
- 均线偏离: MA5=-9.99%; MA20=-13.41%; MA60=-20.90%
- C线原始预测: action=watch_only; direction=neutral; confidence=45%
- 触发依据: 若继续处于 MA20 下方且弱势波动放大，说明盘中没有形成有效修复，C 线的谨慎/观望假设得到强化。
- LLM客观评价: D线触发: 若继续处于 MA20 下方且弱势波动放大，说明盘中没有形成有效修复，C 线的谨慎/观望假设得到强化。 观察目的: 明天盘中观察工业富联在 panic 市场里能否从 MA5/MA20 下方完成弱修复，还是继续延续弱势，用来验证 C 线的 watch_only/neutral 是否成立。 主要风险: 在市场恐慌背景下，当前右侧评分虽不低，但价格已明显低于多条均线且近阶段走势偏弱，最需要防范的是反弹只能算技术性修复、无法收复短均线，进而继续验证失败。 对C线反馈: watch_only -> reinforce_caution 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch_only -> reinforce_caution; baseline=20260729; task_id=20260729_20260730_601138_d_observe_llm_v2; MA20触发位置=-13.41%
