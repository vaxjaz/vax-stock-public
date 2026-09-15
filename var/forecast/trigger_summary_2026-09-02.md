# D线盘中触发汇总

- updated_at: 2026-09-02T09:30:07
- trade_date: 2026-09-02
- triggers: 2
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 002475 立讯精密

- 触发: weak_rebound / severity=low / fire_count=2
- 时间: forecast_ts=2026-09-02T09:30:04; trade_time=09:25:00; trade_date=2026-09-02
- 实时行情: 现价=56.70; 涨跌幅=-0.39%; 振幅=0.00%; 成交额=0.22亿
- 均线偏离: MA5=-0.68%; MA20=+1.05%; MA60=-7.18%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 仅在MA20上方弱反弹但仍未收复MA5、且量能不足，更多属于噪音而非趋势修复
- LLM客观评价: D线触发: 仅在MA20上方弱反弹但仍未收复MA5、且量能不足，更多属于噪音而非趋势修复 观察目的: 验证该票次日是否继续维持低优先级弱势整理，还是在低评分背景下出现放量修复从而推翻回避结论 主要风险: 若盘中快速收复并站稳MA5/MA20且伴随量能放大，则“避开/中性”假设失效 对C线反馈: observe_only 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=observe_only; baseline=20260901; task_id=20260901_20260902_002475_d_observe_llm_v2; MA20触发位置=+1.05%

## 2. 601179 中国西电

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-09-02T09:30:07; trade_time=09:29:29; trade_date=2026-09-02
- 实时行情: 现价=12.61; 涨跌幅=-0.86%; 振幅=0.00%; 成交额=0.02亿
- 均线偏离: MA5=-1.61%; MA20=-5.69%; MA60=-8.35%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若只是低量弱反弹、仍明显弱于 MA20，说明修复质量不足，更接近‘回避但可观察’的结构
- LLM客观评价: D线触发: 若只是低量弱反弹、仍明显弱于 MA20，说明修复质量不足，更接近‘回避但可观察’的结构 观察目的: 验证 C线“非 panic 且评分偏低默认回避”是否会在次日盘中体现为均线下方的持续弱势，还是出现足以推翻回避假设的有效修复 主要风险: 盘中若快速收复短中期均线并伴随量能放大，回避/中性判断会失效；反之若继续在 MA20 下方走弱，则更支持 C 线回避 对C线反馈: watch_no_change / keep_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch_no_change / keep_avoid; baseline=20260901; task_id=20260901_20260902_601179_d_observe_llm_v2; MA20触发位置=-5.69%
