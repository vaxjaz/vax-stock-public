# D线盘中触发汇总

- updated_at: 2026-08-04T09:35:02
- trade_date: 2026-08-04
- triggers: 6
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 002475 立讯精密

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-08-04T09:29:49; trade_time=09:25:00; trade_date=2026-08-04
- 实时行情: 现价=54.00; 涨跌幅=+0.54%; 振幅=0.00%; 成交额=0.47亿
- 均线偏离: MA5=-7.53%; MA20=-10.46%; MA60=-19.40%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 说明盘中有反弹动作，但仍未收复短线均线，属于弱反抽而非趋势修复。
- LLM客观评价: D线触发: 说明盘中有反弹动作，但仍未收复短线均线，属于弱反抽而非趋势修复。 观察目的: 验证C线的“watch/up”假设：立讯精密次日是否能从超跌状态转入有效修复，重点看是否收复MA5并向MA20靠拢，而不是继续沿下跌趋势走弱。 主要风险: 当前价格仍显著低于MA5/MA20/MA60，最大风险是反弹只停留在弱修复或日内噪音，最终演变为继续破位下探，从而证伪C线偏乐观的观察方向。 对C线反馈: watch -> cautious_observe 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> cautious_observe; baseline=20260803; task_id=20260803_20260804_002475_d_observe_llm_v2; MA20触发位置=-10.46%

## 2. 002475 立讯精密

- 触发: risk_off_confirm / severity=medium / fire_count=2
- 时间: forecast_ts=2026-08-04T09:29:52; trade_time=09:25:00; trade_date=2026-08-04
- 实时行情: 现价=54.00; 涨跌幅=+0.54%; 振幅=0.00%; 成交额=0.47亿
- 均线偏离: MA5=-7.53%; MA20=-10.46%; MA60=-19.40%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 若长均线压制仍明显且动量维持低位，说明更偏向风险规避而非修复交易窗口。
- LLM客观评价: D线触发: 若长均线压制仍明显且动量维持低位，说明更偏向风险规避而非修复交易窗口。 观察目的: 验证C线的“watch/up”假设：立讯精密次日是否能从超跌状态转入有效修复，重点看是否收复MA5并向MA20靠拢，而不是继续沿下跌趋势走弱。 主要风险: 当前价格仍显著低于MA5/MA20/MA60，最大风险是反弹只停留在弱修复或日内噪音，最终演变为继续破位下探，从而证伪C线偏乐观的观察方向。 对C线反馈: watch -> risk_off_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> risk_off_review; baseline=20260803; task_id=20260803_20260804_002475_d_observe_llm_v2; MA20触发位置=-10.46%

## 3. 600875 东方电气

- 触发: reclaim_confirm / severity=high / fire_count=1
- 时间: forecast_ts=2026-08-04T09:29:54; trade_time=09:29:03; trade_date=2026-08-04
- 实时行情: 现价=27.08; 涨跌幅=+1.12%; 振幅=0.00%; 成交额=0.28亿
- 均线偏离: MA5=+6.48%; MA20=+2.66%; MA60=-12.91%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明盘中修复不是弱反弹而是有效重新站稳短中期均线，C线的回避假设需要重新审视。
- LLM客观评价: D线触发: 说明盘中修复不是弱反弹而是有效重新站稳短中期均线，C线的回避假设需要重新审视。 观察目的: 观察东方电气次日盘中是否能在非panic背景下守住短中期均线并延续修复，还是出现放量回落来验证C线的回避判断。 主要风险: 核心风险是开盘后或盘中反弹乏力、重新跌回MA5/MA20下方并伴随放量，说明当前回避逻辑并非只是静态低优先级，而是短线走弱被实盘确认。 对C线反馈: avoid_reassess 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=avoid_reassess; baseline=20260803; task_id=20260803_20260804_600875_d_observe_llm_v2; MA20触发位置=+2.66%

## 4. 601138 工业富联

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-08-04T09:29:56; trade_time=09:29:16; trade_date=2026-08-04
- 实时行情: 现价=56.81; 涨跌幅=+1.63%; 振幅=0.00%; 成交额=0.45亿
- 均线偏离: MA5=+0.64%; MA20=-7.14%; MA60=-16.45%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 说明只出现弱反弹但仍未摆脱中期均线压制，更适合标记为观察中的修复而非确认转强。
- LLM客观评价: D线触发: 说明只出现弱反弹但仍未摆脱中期均线压制，更适合标记为观察中的修复而非确认转强。 观察目的: 验证C线“watch/up”是否能在次日盘中完成对短均线的修复，还是继续在MA5/MA20下方延续弱势回撤。 主要风险: 当前价格仍显著低于MA5/MA20/MA60，且近5日与近20日回撤未止，最大风险是任何盘中反弹都只是弱修复，无法形成结构性转强。 对C线反馈: watch -> weak_rebound_follow 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> weak_rebound_follow; baseline=20260803; task_id=20260803_20260804_601138_d_observe_llm_v2; MA20触发位置=-7.14%

## 5. 601179 中国西电

- 触发: noise_filter / severity=low / fire_count=1
- 时间: forecast_ts=2026-08-04T09:29:58; trade_time=09:29:16; trade_date=2026-08-04
- 实时行情: 现价=14.10; 涨跌幅=+1.37%; 振幅=0.00%; 成交额=0.24亿
- 均线偏离: MA5=+4.48%; MA20=+8.59%; MA60=-5.59%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若只是维持在相对偏强区间但没有明显二次突破，更像噪音而非有效方向验证，避免把普通波动误判为趋势确认。
- LLM客观评价: D线触发: 若只是维持在相对偏强区间但没有明显二次突破，更像噪音而非有效方向验证，避免把普通波动误判为趋势确认。 观察目的: 明天盘中重点验证中国西电是否会从当前高位相对强势转为失守短均线的弱化走势，从而确认 C 线的回避判断；若出现放量延续上行，则反证该判断。 主要风险: 当前位置偏高且近5/20日表现偏弱，核心风险是盘中一旦失去 MA5/MA20 支撑，昨天的相对强势会被证伪；另一端风险是放量继续扩张使回避判断失效。 对C线反馈: watch_only 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch_only; baseline=20260803; task_id=20260803_20260804_601179_d_observe_llm_v2; MA20触发位置=+8.59%

## 6. 600276 恒瑞医药

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-08-04T09:35:02; trade_time=09:34:59; trade_date=2026-08-04
- 实时行情: 现价=54.18; 涨跌幅=+2.23%; 振幅=1.72%; 成交额=4.57亿
- 均线偏离: MA5=+0.74%; MA20=-1.02%; MA60=+4.62%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 出现上涨但仍在MA20下方，且动量/量能没有同步修复，表示只是弱反弹而非趋势确认。
- LLM客观评价: D线触发: 出现上涨但仍在MA20下方，且动量/量能没有同步修复，表示只是弱反弹而非趋势确认。 观察目的: 验证恒瑞医药次日盘中是否能把“评分≥2但仍低于MA20”的弱势位置修复为重新站回短期均线的确认行情，还是继续沿MA20下方偏弱运行并考验MA60支撑。 主要风险: 主风险是反弹缺乏量能、仅形成弱修复而无法收复MA20，随后重新转弱并逼近或失守MA60，使C线的向上观察假设失效。 对C线反馈: watch -> weak_rebound 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> weak_rebound; baseline=20260803; task_id=20260803_20260804_600276_d_observe_llm_v2; MA20触发位置=-1.02%
