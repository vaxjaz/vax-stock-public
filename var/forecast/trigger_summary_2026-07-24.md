# D线盘中触发汇总

- updated_at: 2026-07-24T09:49:38
- trade_date: 2026-07-24
- triggers: 7
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 600276 恒瑞医药

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-24T09:29:08; trade_time=09:28:48; trade_date=2026-07-24
- 实时行情: 现价=55.00; 涨跌幅=+0.16%; 振幅=0.00%; 成交额=0.34亿
- 均线偏离: MA5=+0.37%; MA20=+0.83%; MA60=+6.09%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 表示虽未失守 MA20，但仍被 MA10 压制且量能不足，更像弱反弹而非有效修复。
- LLM客观评价: D线触发: 表示虽未失守 MA20，但仍被 MA10 压制且量能不足，更像弱反弹而非有效修复。 观察目的: 验证 C 线对恒瑞医药次日向上修复、并在盘中站稳 MA20 且进一步收复 MA10 的假设是否成立。 主要风险: 缩量反抽后再次回落，跌回 MA20 下方并形成失败突破或弱反弹。 对C线反馈: watch -> continue_monitor 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> continue_monitor; baseline=20260723; task_id=20260723_20260724_600276_d_observe_llm_v2; MA20触发位置=+0.83%

## 2. 600875 XD东方电

- 触发: breakdown_confirm / severity=high / fire_count=2
- 时间: forecast_ts=2026-07-24T09:29:10; trade_time=09:28:42; trade_date=2026-07-24
- 实时行情: 现价=26.65; 涨跌幅=-2.09%; 振幅=0.00%; 成交额=0.19亿
- 均线偏离: MA5=+2.40%; MA20=-3.18%; MA60=-18.59%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 跌回20日线下方且伴随量能或波动扩张，说明盘中修复失败，C线看多假设被证伪。
- LLM客观评价: D线触发: 跌回20日线下方且伴随量能或波动扩张，说明盘中修复失败，C线看多假设被证伪。 观察目的: 验证C线“看多观察”是否在盘中表现为守住20日线并继续向短线均线外延展，而不是在修复过程中再次转弱。 主要风险: 20日线附近的修复如果缺少延续性，容易变成冲高回落并重新失守短线支撑，从而证伪次日看多假设。 对C线反馈: watch -> invalidate_up_bias 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> invalidate_up_bias; baseline=20260723; task_id=20260723_20260724_600875_d_observe_llm_v2; MA20触发位置=-3.18%

## 3. 601138 工业富联

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-24T09:29:13; trade_time=09:28:33; trade_date=2026-07-24
- 实时行情: 现价=61.05; 涨跌幅=-2.91%; 振幅=0.00%; 成交额=0.75亿
- 均线偏离: MA5=+2.21%; MA20=-5.63%; MA60=-11.32%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 说明有反弹但仍受 MA20 压制，属于弱修复而非有效转强。
- LLM客观评价: D线触发: 说明有反弹但仍受 MA20 压制，属于弱修复而非有效转强。 观察目的: 验证 C线的“watch/up”假设是否能在盘中被 MA20 修复和放量延续所支持，还是继续受制于中期均线与弱势结构。 主要风险: 在 AI 算力减档约束和 10 日主力净流出背景下，盘中反弹若不能重新站回 MA20，容易被证明只是弱修复而非趋势延续。 对C线反馈: watch -> keep_cautious 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。 ⚠️[铁律校验] 检测到疑似越界(盘中新评分/买卖价/资金臆测), 以EOD报告为准, 盘中未定论
- C线反哺线索: expected_feedback_to_c=watch -> keep_cautious; baseline=20260723; task_id=20260723_20260724_601138_d_observe_llm_v2; MA20触发位置=-5.63%

## 4. 601138 工业富联

- 触发: breakdown_confirm / severity=high / fire_count=3
- 时间: forecast_ts=2026-07-24T09:29:14; trade_time=09:28:33; trade_date=2026-07-24
- 实时行情: 现价=61.05; 涨跌幅=-2.91%; 振幅=0.00%; 成交额=0.75亿
- 均线偏离: MA5=+2.21%; MA20=-5.63%; MA60=-11.32%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 说明弱势结构被进一步确认，盘中不是修复而是继续下探。
- LLM客观评价: D线触发: 说明弱势结构被进一步确认，盘中不是修复而是继续下探。 观察目的: 验证 C线的“watch/up”假设是否能在盘中被 MA20 修复和放量延续所支持，还是继续受制于中期均线与弱势结构。 主要风险: 在 AI 算力减档约束和 10 日主力净流出背景下，盘中反弹若不能重新站回 MA20，容易被证明只是弱修复而非趋势延续。 对C线反馈: watch -> avoid_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。 ⚠️[铁律校验] 检测到疑似越界(盘中新评分/买卖价/资金臆测), 以EOD报告为准, 盘中未定论
- C线反哺线索: expected_feedback_to_c=watch -> avoid_review; baseline=20260723; task_id=20260723_20260724_601138_d_observe_llm_v2; MA20触发位置=-5.63%

## 5. 601179 中国西电

- 触发: reclaim_confirm / severity=high / fire_count=3
- 时间: forecast_ts=2026-07-24T09:34:20; trade_time=09:34:17; trade_date=2026-07-24
- 实时行情: 现价=14.17; 涨跌幅=+3.81%; 振幅=3.52%; 成交额=13.35亿
- 均线偏离: MA5=+13.58%; MA20=+6.44%; MA60=-7.72%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若盘中重新站稳短中期均线且出现一定量能或波动配合，说明修复不是单纯反抽，C线回避假设可能被推翻。
- LLM客观评价: D线触发: 若盘中重新站稳短中期均线且出现一定量能或波动配合，说明修复不是单纯反抽，C线回避假设可能被推翻。 观察目的: 验证C线“回避/中性”判断是否会在次日盘中表现为失守短中期均线后的弱势延续，而不是放量修复后的强势回收。 主要风险: 盘中重新站回MA10/MA20并伴随波动放大，说明低评分回避假设失效，弱势判断可能被推翻。 对C线反馈: watch -> review_avoid_invalidated 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> review_avoid_invalidated; baseline=20260723; task_id=20260723_20260724_601179_d_observe_llm_v2; MA20触发位置=+6.44%

## 6. 002475 立讯精密

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-24T09:44:33; trade_time=09:44:24; trade_date=2026-07-24
- 实时行情: 现价=62.27; 涨跌幅=+1.76%; 振幅=4.40%; 成交额=10.46亿
- 均线偏离: MA5=+5.32%; MA20=-0.27%; MA60=-8.64%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 价格只是在20日线附近做弱修复，但动量和量能都不支持，说明反弹质量不足，更多是观察而非确认。
- LLM客观评价: D线触发: 价格只是在20日线附近做弱修复，但动量和量能都不支持，说明反弹质量不足，更多是观察而非确认。 观察目的: 验证次日盘中是否能重新站上并站稳20日线，区分“修复确认”与“继续弱势破位”两种路径。 主要风险: 当前价格仍略低于MA20，若盘中无法完成回到MA20上方并维持，反而继续下压并放大波动，则C线的偏多观察假设容易失效。 对C线反馈: watch -> hold_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> hold_review; baseline=20260723; task_id=20260723_20260724_002475_d_observe_llm_v2; MA20触发位置=-0.27%

## 7. 603009 北特科技

- 触发: breakdown_confirm / severity=high / fire_count=3
- 时间: forecast_ts=2026-07-24T09:49:38; trade_time=09:49:36; trade_date=2026-07-24
- 实时行情: 现价=40.25; 涨跌幅=-2.42%; 振幅=4.80%; 成交额=0.81亿
- 均线偏离: MA5=-3.75%; MA20=-13.19%; MA60=-16.10%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明价格仍处于明显弱势区间，且没有形成有效修复，支持回避判断继续成立。
- LLM客观评价: D线触发: 说明价格仍处于明显弱势区间，且没有形成有效修复，支持回避判断继续成立。 观察目的: 观察次日是否延续超跌弱势并无法修复到短均线之上，以验证 C 线的回避判断是否成立。 主要风险: 超跌后的快速修复把价格重新拉回短均线附近，导致原本的回避判断失效。 对C线反馈: confirm_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=confirm_avoid; baseline=20260723; task_id=20260723_20260724_603009_d_observe_llm_v2; MA20触发位置=-13.19%
