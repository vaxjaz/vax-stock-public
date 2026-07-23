# D线盘中触发汇总

- updated_at: 2026-07-22T10:21:59
- trade_date: 2026-07-22
- triggers: 8
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 002475 立讯精密

- 触发: weak_rebound / severity=low / fire_count=1
- 时间: forecast_ts=2026-07-22T09:25:56; trade_time=09:25:00; trade_date=2026-07-22
- 实时行情: 现价=59.88; 涨跌幅=-0.89%; 振幅=0.00%; 成交额=0.25亿
- 均线偏离: MA5=+0.70%; MA20=-6.29%; MA60=-12.43%
- C线原始预测: action=watch_only; direction=neutral; confidence=45%
- 触发依据: 若只是短暂反弹到 MA5 附近，但仍被 MA10/MA20 压制且量能不配合，这更像失败修复而非趋势反转。
- LLM客观评价: D线触发: 若只是短暂反弹到 MA5 附近，但仍被 MA10/MA20 压制且量能不配合，这更像失败修复而非趋势反转。 观察目的: 明天盘中主要验证：在 panic 市场与 AI 线防御上限约束下，立讯精密是否只能维持弱势观察，还是能完成短线均线修复并推翻“仅观察、不介入”的判断。 主要风险: 最大风险是弱反弹后再次跌破关键均线，说明当前的右侧评分与基本面优势不足以对抗 panic regime 下的趋势压制，盘中表现更像被动修复而非有效转强。 对C线反馈: watch_only -> remain_cautious 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch_only -> remain_cautious; baseline=20260721; task_id=20260721_20260722_002475_d_observe_llm_v2; MA20触发位置=-6.29%

## 2. 601179 中国西电

- 触发: risk_off_confirm / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-22T09:25:59; trade_time=09:25:35; trade_date=2026-07-22
- 实时行情: 现价=12.20; 涨跌幅=-1.21%; 振幅=0.00%; 成交额=0.07亿
- 均线偏离: MA5=+1.48%; MA20=-10.47%; MA60=-21.33%
- C线原始预测: action=panic_rebound_probe; direction=neutral; confidence=40%
- 触发依据: 在超跌且仍远离MA20时若价格无正向进展，说明市场仍处于风险规避主导，修复预期偏弱。
- LLM客观评价: D线触发: 在超跌且仍远离MA20时若价格无正向进展，说明市场仍处于风险规避主导，修复预期偏弱。 观察目的: 观察中国西电在次日盘中是否只出现低位技术性修复，还是能从深度破位状态中完成对MA10/MA20的有效收复，以验证C线的panic_rebound_probe假设。 主要风险: 最核心风险是弱反弹失败后继续贴近或扩大对MA20/MA60的破位，说明当前修复仅是噪声而非有效回稳。 对C线反馈: panic_rebound_probe -> risk_off_confirm，反馈为修复概率不足 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=panic_rebound_probe -> risk_off_confirm，反馈为修复概率不足; baseline=20260721; task_id=20260721_20260722_601179_d_observe_llm_v2; MA20触发位置=-10.47%

## 3. 601179 中国西电

- 触发: breakdown_confirm / severity=high / fire_count=2
- 时间: forecast_ts=2026-07-22T09:31:04; trade_time=09:31:01; trade_date=2026-07-22
- 实时行情: 现价=12.14; 涨跌幅=-1.70%; 振幅=0.97%; 成交额=0.34亿
- 均线偏离: MA5=+0.98%; MA20=-10.91%; MA60=-21.72%
- C线原始预测: action=panic_rebound_probe; direction=neutral; confidence=40%
- 触发依据: 若盘中继续扩大对MA20/MA60的负偏离且伴随下跌或波动放大，说明不是修复而是破位延续。
- LLM客观评价: D线触发: 若盘中继续扩大对MA20/MA60的负偏离且伴随下跌或波动放大，说明不是修复而是破位延续。 观察目的: 观察中国西电在次日盘中是否只出现低位技术性修复，还是能从深度破位状态中完成对MA10/MA20的有效收复，以验证C线的panic_rebound_probe假设。 主要风险: 最核心风险是弱反弹失败后继续贴近或扩大对MA20/MA60的破位，说明当前修复仅是噪声而非有效回稳。 对C线反馈: panic_rebound_probe -> breakdown_confirm，C线修复假设失效 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=panic_rebound_probe -> breakdown_confirm，C线修复假设失效; baseline=20260721; task_id=20260721_20260722_601179_d_observe_llm_v2; MA20触发位置=-10.91%

## 4. 600276 恒瑞医药

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-22T09:36:09; trade_time=09:36:04; trade_date=2026-07-22
- 实时行情: 现价=54.94; 涨跌幅=+0.02%; 振幅=1.60%; 成交额=4.16亿
- 均线偏离: MA5=-0.89%; MA20=+1.66%; MA60=+5.90%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 价格只是维持在中期均线之上，但短线仍受压且量能不跟，说明修复力度偏弱。
- LLM客观评价: D线触发: 价格只是维持在中期均线之上，但短线仍受压且量能不跟，说明修复力度偏弱。 观察目的: 明天盘中重点验证：在市场 panic 背景下，恒瑞医药是否能把 EOD 的“观察等待/反弹试探”转成可确认的情绪修复，而不是短暂冲高后重新走弱。 主要风险: 恐慌市里出现弱反弹但无法站回短均线，最终回落到中短期趋势下方，从而推翻 C 线的 T+1 修复假设。 对C线反馈: watch_only -> lower_confidence 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch_only -> lower_confidence; baseline=20260721; task_id=20260721_20260722_600276_d_observe_llm_v2; MA20触发位置=+1.66%

## 5. 600276 恒瑞医药

- 触发: panic_rebound_probe / severity=high / fire_count=2
- 时间: forecast_ts=2026-07-22T09:41:19; trade_time=09:41:10; trade_date=2026-07-22
- 实时行情: 现价=55.62; 涨跌幅=+1.26%; 振幅=2.89%; 成交额=7.93亿
- 均线偏离: MA5=+0.33%; MA20=+2.91%; MA60=+7.21%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 盘中重新站上短均线且有一定波动/量能配合，才更符合“恐慌修复”而非单纯反抽。
- LLM客观评价: D线触发: 盘中重新站上短均线且有一定波动/量能配合，才更符合“恐慌修复”而非单纯反抽。 观察目的: 明天盘中重点验证：在市场 panic 背景下，恒瑞医药是否能把 EOD 的“观察等待/反弹试探”转成可确认的情绪修复，而不是短暂冲高后重新走弱。 主要风险: 恐慌市里出现弱反弹但无法站回短均线，最终回落到中短期趋势下方，从而推翻 C 线的 T+1 修复假设。 对C线反馈: confirm_rebound -> keep_up_bias 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=confirm_rebound -> keep_up_bias; baseline=20260721; task_id=20260721_20260722_600276_d_observe_llm_v2; MA20触发位置=+2.91%

## 6. 600875 东方电气

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-22T09:56:36; trade_time=09:56:28; trade_date=2026-07-22
- 实时行情: 现价=26.41; 涨跌幅=+0.88%; 振幅=2.44%; 成交额=3.36亿
- 均线偏离: MA5=+2.75%; MA20=-5.19%; MA60=-20.60%
- C线原始预测: action=watch_only; direction=neutral; confidence=45%
- 触发依据: 说明有反弹，但仍未修复到 MA10，且强度/量能不足，更像低质量修复而非趋势扭转。
- LLM客观评价: D线触发: 说明有反弹，但仍未修复到 MA10，且强度/量能不足，更像低质量修复而非趋势扭转。 观察目的: 验证 C 线的 watch_only 是否成立：在 panic 市场下，东方电气次日是继续失守 MA20 还是出现对 MA10/MA20 的有效修复。 主要风险: 最需要防范的是弱反弹后再次跌破 MA5/MA10 并放大回撤，说明右侧评分在 panic regime 下不足以支撑持续修复。 对C线反馈: watch_only -> weak_rebound_confirmed 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch_only -> weak_rebound_confirmed; baseline=20260721; task_id=20260721_20260722_600875_d_observe_llm_v2; MA20触发位置=-5.19%

## 7. 601179 中国西电

- 触发: weak_rebound / severity=medium / fire_count=3
- 时间: forecast_ts=2026-07-22T09:56:38; trade_time=09:56:28; trade_date=2026-07-22
- 实时行情: 现价=12.46; 涨跌幅=+0.89%; 振幅=3.56%; 成交额=4.79亿
- 均线偏离: MA5=+3.64%; MA20=-8.56%; MA60=-19.65%
- C线原始预测: action=panic_rebound_probe; direction=neutral; confidence=40%
- 触发依据: 若出现温和反弹但仍明显低于MA20，说明属于弱修复，只能验证是否存在超跌反抽，不能视为趋势反转。
- LLM客观评价: D线触发: 若出现温和反弹但仍明显低于MA20，说明属于弱修复，只能验证是否存在超跌反抽，不能视为趋势反转。 观察目的: 观察中国西电在次日盘中是否只出现低位技术性修复，还是能从深度破位状态中完成对MA10/MA20的有效收复，以验证C线的panic_rebound_probe假设。 主要风险: 最核心风险是弱反弹失败后继续贴近或扩大对MA20/MA60的破位，说明当前修复仅是噪声而非有效回稳。 对C线反馈: panic_rebound_probe -> weak_rebound，保留但下调修复强度判断 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=panic_rebound_probe -> weak_rebound，保留但下调修复强度判断; baseline=20260721; task_id=20260721_20260722_601179_d_observe_llm_v2; MA20触发位置=-8.56%

## 8. 601138 工业富联

- 触发: reclaim_confirm / severity=high / fire_count=1
- 时间: forecast_ts=2026-07-22T10:21:59; trade_time=10:21:57; trade_date=2026-07-22
- 实时行情: 现价=62.96; 涨跌幅=+3.25%; 振幅=5.08%; 成交额=43.81亿
- 均线偏离: MA5=+4.34%; MA20=-4.90%; MA60=-8.75%
- C线原始预测: action=watch_only; direction=neutral; confidence=45%
- 触发依据: 现价重新越过7月21日高点，并同时收窄至MA10下方0.5%以内、MA20下方5%以内；这比单纯上涨更能证明二日延续和趋势修复。
- LLM客观评价: D线触发: 现价重新越过7月21日高点，并同时收窄至MA10下方0.5%以内、MA20下方5%以内；这比单纯上涨更能证明二日延续和趋势修复。 观察目的: 不采用评分系统的 watch_only 结论作为盘中动作依据；独立验证 7月21日放量上涨7.93%究竟形成二日延续，还是仅为下跌趋势中的单日脉冲。以重新越过7月21日高点并逼近MA10/MA20作为强化证据，以失守MA5并出现明显回吐作为失败证据。只评价补仓前提，不输出买卖价指令。 主要风险: 7月21日收盘虽回到MA5上方，但仍低于MA10、MA20和MA60，且近20日跌幅为17.71%；单日上涨尚未改变中期下降结构。若次日不能延续并重新失守MA5，真反弹与补仓前提均未确认。 对C线反馈: 独立补仓前提得到正向盘中证据；C线watch_only仅保留为...
- C线反哺线索: expected_feedback_to_c=独立补仓前提得到正向盘中证据；C线watch_only仅保留为历史基线。; baseline=20260721; task_id=20260721_20260722_601138_d_observe_llm_v2_manual_add_v1; MA20触发位置=-4.90%
