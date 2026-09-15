# D线盘中触发汇总

- updated_at: 2026-09-04T14:44:13
- trade_date: 2026-09-04
- triggers: 4
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 002475 立讯精密

- 触发: reclaim_confirm / severity=medium / fire_count=2
- 时间: forecast_ts=2026-09-04T09:27:20; trade_time=09:25:00; trade_date=2026-09-04
- 实时行情: 现价=56.98; 涨跌幅=+1.44%; 振幅=0.00%; 成交额=0.39亿
- 均线偏离: MA5=+0.18%; MA20=+1.41%; MA60=-6.17%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若盘中重新站上MA10/MA20且量能或动量同步改善，说明不是简单弱势回避，而是出现修复确认。
- LLM客观评价: D线触发: 若盘中重新站上MA10/MA20且量能或动量同步改善，说明不是简单弱势回避，而是出现修复确认。 观察目的: 明天盘中主要验证立讯精密是否仍维持“弱势回避”而非出现对MA20/MA10的有效修复，重点看短中期均线附近是继续失守还是被放量收复。 主要风险: 盘中若快速收复price_vs_ma20_pct和price_vs_ma10_pct并伴随量能抬升，会削弱C线的avoid/neutral判断。 对C线反馈: avoid_to_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=avoid_to_review; baseline=20260903; task_id=20260903_20260904_002475_d_observe_llm_v2; MA20触发位置=+1.41%

## 2. 600875 东方电气

- 触发: noise_filter / severity=low / fire_count=2
- 时间: forecast_ts=2026-09-04T09:27:23; trade_time=09:27:14; trade_date=2026-09-04
- 实时行情: 现价=24.71; 涨跌幅=+0.53%; 振幅=0.00%; 成交额=0.04亿
- 均线偏离: MA5=-1.48%; MA20=-5.75%; MA60=-9.99%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明盘中主要是缩量弱震荡，属于噪声级别的波动，不应把普通反抽误判为结构性转强。
- LLM客观评价: D线触发: 说明盘中主要是缩量弱震荡，属于噪声级别的波动，不应把普通反抽误判为结构性转强。 观察目的: 验证C线“非panic、低优先级回避”假设：次日盘中是否仍维持在短中期均线下方的弱势结构，或只是缩量反抽后再度回落。 主要风险: 盘中出现有效回收短均线的弱修复，导致原本的回避判断失效。 对C线反馈: hold_avoid_watch 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=hold_avoid_watch; baseline=20260903; task_id=20260903_20260904_600875_d_observe_llm_v2; MA20触发位置=-5.75%

## 3. 600875 东方电气

- 触发: weak_rebound / severity=medium / fire_count=3
- 时间: forecast_ts=2026-09-04T09:27:25; trade_time=09:27:14; trade_date=2026-09-04
- 实时行情: 现价=24.71; 涨跌幅=+0.53%; 振幅=0.00%; 成交额=0.04亿
- 均线偏离: MA5=-1.48%; MA20=-5.75%; MA60=-9.99%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明盘中有反弹动作但力度不足，修复不成立，C线的回避逻辑仍然有效。
- LLM客观评价: D线触发: 说明盘中有反弹动作但力度不足，修复不成立，C线的回避逻辑仍然有效。 观察目的: 验证C线“非panic、低优先级回避”假设：次日盘中是否仍维持在短中期均线下方的弱势结构，或只是缩量反抽后再度回落。 主要风险: 盘中出现有效回收短均线的弱修复，导致原本的回避判断失效。 对C线反馈: maintain_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=maintain_avoid; baseline=20260903; task_id=20260903_20260904_600875_d_observe_llm_v2; MA20触发位置=-5.75%

## 4. 002475 立讯精密

- 触发: breakdown_confirm / severity=high / fire_count=3
- 时间: forecast_ts=2026-09-04T14:44:11; trade_time=14:44:09; trade_date=2026-09-04
- 实时行情: 现价=54.23; 涨跌幅=-3.45%; 振幅=5.04%; 成交额=56.99亿
- 均线偏离: MA5=-4.66%; MA20=-3.48%; MA60=-10.70%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若短中期均线同步转弱且波动放大，说明次日延续下行压力，C线的回避判断得到验证。
- LLM客观评价: D线触发: 若短中期均线同步转弱且波动放大，说明次日延续下行压力，C线的回避判断得到验证。 观察目的: 明天盘中主要验证立讯精密是否仍维持“弱势回避”而非出现对MA20/MA10的有效修复，重点看短中期均线附近是继续失守还是被放量收复。 主要风险: 盘中若快速收复price_vs_ma20_pct和price_vs_ma10_pct并伴随量能抬升，会削弱C线的avoid/neutral判断。 对C线反馈: confirm_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=confirm_avoid; baseline=20260903; task_id=20260903_20260904_002475_d_observe_llm_v2; MA20触发位置=-3.48%
