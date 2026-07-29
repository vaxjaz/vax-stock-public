# D线盘中触发汇总

- updated_at: 2026-07-29T10:35:20
- trade_date: 2026-07-29
- triggers: 5
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 002475 立讯精密

- 触发: panic_rebound_probe / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-29T09:28:55; trade_time=09:25:00; trade_date=2026-07-29
- 实时行情: 现价=60.55; 涨跌幅=+0.75%; 振幅=0.00%; 成交额=0.23亿
- 均线偏离: MA5=-0.39%; MA20=-1.44%; MA60=-10.58%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 价格在未完全转强前出现正向修复，且没有明显恶化，说明 panic 后的修复开始被验证。
- LLM客观评价: D线触发: 价格在未完全转强前出现正向修复，且没有明显恶化，说明 panic 后的修复开始被验证。 观察目的: 明天盘中重点验证 C 线“panic_rebound_watch”假设是否成立：在整体 panic 环境下，立讯精密能否从 MA10/MA20 附近出现有效修复，而不是继续沿着弱势通道下探。 主要风险: 恐慌市环境叠加个股仍在 MA20 下方，反弹若缺少量能与持续性，容易演变为弱修复后再次破位。 对C线反馈: confirm_rebound_probe 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=confirm_rebound_probe; baseline=20260728; task_id=20260728_20260729_002475_d_observe_llm_v2; MA20触发位置=-1.44%

## 2. 002475 立讯精密

- 触发: reclaim_confirm / severity=high / fire_count=2
- 时间: forecast_ts=2026-07-29T09:39:05; trade_time=09:39:00; trade_date=2026-07-29
- 实时行情: 现价=61.98; 涨跌幅=+3.13%; 振幅=4.33%; 成交额=11.19亿
- 均线偏离: MA5=+1.96%; MA20=+0.89%; MA60=-8.46%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 说明次日盘中已从弱势修复推进到均线重建，C 线的情绪修复假设得到更强验证。
- LLM客观评价: D线触发: 说明次日盘中已从弱势修复推进到均线重建，C 线的情绪修复假设得到更强验证。 观察目的: 明天盘中重点验证 C 线“panic_rebound_watch”假设是否成立：在整体 panic 环境下，立讯精密能否从 MA10/MA20 附近出现有效修复，而不是继续沿着弱势通道下探。 主要风险: 恐慌市环境叠加个股仍在 MA20 下方，反弹若缺少量能与持续性，容易演变为弱修复后再次破位。 对C线反馈: confirm_repair 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=confirm_repair; baseline=20260728; task_id=20260728_20260729_002475_d_observe_llm_v2; MA20触发位置=+0.89%

## 3. 601179 中国西电

- 触发: panic_rebound_probe / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-29T09:49:17; trade_time=09:49:15; trade_date=2026-07-29
- 实时行情: 现价=13.55; 涨跌幅=+0.82%; 振幅=5.65%; 成交额=7.02亿
- 均线偏离: MA5=+0.91%; MA20=+3.23%; MA60=-10.77%
- C线原始预测: action=panic_rebound_probe; direction=neutral; confidence=40%
- 触发依据: 出现了反弹但仍未完成中短均线修复，符合“恐慌修复探针”而非强趋势修复。
- LLM客观评价: D线触发: 出现了反弹但仍未完成中短均线修复，符合“恐慌修复探针”而非强趋势修复。 观察目的: 明天盘中验证 C 线的“panic_rebound_probe”假设：在市场恐慌背景下，这只票是仅出现弱修复/冲高回落，还是能转成持续性修复。 主要风险: 盘中修复失败后重新失守短均线并放大波动，说明只是技术性反抽而不是有效修复。 对C线反馈: confirm_probe_but_keep_low_confidence 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=confirm_probe_but_keep_low_confidence; baseline=20260728; task_id=20260728_20260729_601179_d_observe_llm_v2; MA20触发位置=+3.23%

## 4. 601179 中国西电

- 触发: reclaim_confirm / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-29T09:49:19; trade_time=09:49:15; trade_date=2026-07-29
- 实时行情: 现价=13.55; 涨跌幅=+0.82%; 振幅=5.65%; 成交额=7.02亿
- 均线偏离: MA5=+0.91%; MA20=+3.23%; MA60=-10.77%
- C线原始预测: action=panic_rebound_probe; direction=neutral; confidence=40%
- 触发依据: 若能同时收复短均线和中均线，说明恐慌修复强于预期，C 线的低置信度偏保守。
- LLM客观评价: D线触发: 若能同时收复短均线和中均线，说明恐慌修复强于预期，C 线的低置信度偏保守。 观察目的: 明天盘中验证 C 线的“panic_rebound_probe”假设：在市场恐慌背景下，这只票是仅出现弱修复/冲高回落，还是能转成持续性修复。 主要风险: 盘中修复失败后重新失守短均线并放大波动，说明只是技术性反抽而不是有效修复。 对C线反馈: rebound_stronger_than_expected 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=rebound_stronger_than_expected; baseline=20260728; task_id=20260728_20260729_601179_d_observe_llm_v2; MA20触发位置=+3.23%

## 5. 600875 东方电气

- 触发: panic_rebound_probe / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-29T10:35:20; trade_time=10:35:16; trade_date=2026-07-29
- 实时行情: 现价=25.39; 涨跌幅=+2.05%; 振幅=3.38%; 成交额=4.57亿
- 均线偏离: MA5=-2.63%; MA20=-6.10%; MA60=-20.69%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 出现基础修复且未继续恶化，说明 panic_rebound_watch 至少进入可观察状态。
- LLM客观评价: D线触发: 出现基础修复且未继续恶化，说明 panic_rebound_watch 至少进入可观察状态。 观察目的: 观察明天盘中是否出现恐慌后的修复性反弹，并且能否把价格重新拉回短均线附近，以验证 C 线的 panic_rebound_watch 假设。 主要风险: 在 panic 市场里，当前仍明显位于 20 日线和 60 日线下方，反弹如果无法收复短均线，就更像超跌噪音而不是有效修复。 对C线反馈: watch -> confirm_rebound_probe 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> confirm_rebound_probe; baseline=20260728; task_id=20260728_20260729_600875_d_observe_llm_v2; MA20触发位置=-6.10%
