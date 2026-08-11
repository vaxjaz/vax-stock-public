# D线盘中触发汇总

- updated_at: 2026-08-05T13:12:06
- trade_date: 2026-08-05
- triggers: 3
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 601138 工业富联

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-08-05T09:25:36; trade_time=09:25:17; trade_date=2026-08-05
- 实时行情: 现价=59.00; 涨跌幅=-1.55%; 振幅=0.00%; 成交额=1.57亿
- 均线偏离: MA5=+3.84%; MA20=-3.26%; MA60=-13.10%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明只是弱反弹且缺乏量能确认，通常不足以改变回避结论。
- LLM客观评价: D线触发: 说明只是弱反弹且缺乏量能确认，通常不足以改变回避结论。 观察目的: 验证C线“avoid/neutral”是否成立，重点看次日盘中能否继续受制于20日线，还是出现带量重新站上并证伪回避判断。 主要风险: 低评分下仍出现放量收复MA20并转强，导致“非panic+默认回避”的假设失效。 对C线反馈: stay_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=stay_avoid; baseline=20260804; task_id=20260804_20260805_601138_d_observe_llm_v2; MA20触发位置=-3.26%

## 2. 601138 工业富联

- 触发: reclaim_confirm / severity=high / fire_count=3
- 时间: forecast_ts=2026-08-05T09:35:41; trade_time=09:35:37; trade_date=2026-08-05
- 实时行情: 现价=62.40; 涨跌幅=+4.12%; 振幅=5.97%; 成交额=17.73亿
- 均线偏离: MA5=+9.83%; MA20=+2.32%; MA60=-8.09%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明盘中修复强于预期，回避假设可能被推翻，需要复核C线判断。
- LLM客观评价: D线触发: 说明盘中修复强于预期，回避假设可能被推翻，需要复核C线判断。 观察目的: 验证C线“avoid/neutral”是否成立，重点看次日盘中能否继续受制于20日线，还是出现带量重新站上并证伪回避判断。 主要风险: 低评分下仍出现放量收复MA20并转强，导致“非panic+默认回避”的假设失效。 对C线反馈: avoid_to_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=avoid_to_review; baseline=20260804; task_id=20260804_20260805_601138_d_observe_llm_v2; MA20触发位置=+2.32%

## 3. 002475 立讯精密

- 触发: weak_rebound / severity=low / fire_count=3
- 时间: forecast_ts=2026-08-05T13:12:06; trade_time=13:12:03; trade_date=2026-08-05
- 实时行情: 现价=55.72; 涨跌幅=+0.43%; 振幅=5.68%; 成交额=81.73亿
- 均线偏离: MA5=-3.05%; MA20=-7.00%; MA60=-16.40%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若盘中出现的是低量、弱幅度反弹，但仍无法修复短均线和动量，说明只是技术性喘息，不足以推翻回避思路。
- LLM客观评价: D线触发: 若盘中出现的是低量、弱幅度反弹，但仍无法修复短均线和动量，说明只是技术性喘息，不足以推翻回避思路。 观察目的: 验证C线“回避/中性”假设是否成立：明天盘中重点看该票能否在短均线下方继续弱势运行，还是出现放量修复并重新站回MA5/MA10。 主要风险: 盘中弱反弹后再次失守短均线，说明下跌惯性未被修复；若反而放量收复MA5/MA10，则当前回避判断可能偏保守。 对C线反馈: keep_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=keep_avoid; baseline=20260804; task_id=20260804_20260805_002475_d_observe_llm_v2; MA20触发位置=-7.00%
