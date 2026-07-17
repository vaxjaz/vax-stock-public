# D线盘中触发汇总

- updated_at: 2026-07-16T14:47:56
- trade_date: 2026-07-16
- triggers: 17
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 002371 北方华创

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-16T09:25:32; trade_time=09:25:00; trade_date=2026-07-16
- 实时行情: 现价=732.96; 涨跌幅=-1.31%; 振幅=0.00%; 成交额=0.97亿
- 均线偏离: MA5=-7.47%; MA20=-8.44%; MA60=+11.40%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 说明仅出现低质量反弹，尚未形成对C线偏多判断的有效确认。
- LLM客观评价: D线触发: 说明仅出现低质量反弹，尚未形成对C线偏多判断的有效确认。 观察目的: 观察北方华创次日盘中能否从5/10/20日线下方完成修复并放量，验证C线的“watch/up”是可被盘中证实的修复，还是只是高位回撤后的弱反弹。 主要风险: 股价已低于5日线和20日线、MACD为负且近5日回撤偏大；如果盘中不能同步收复短均线并改善量能，C线偏多观察将被证伪。 对C线反馈: watch -> hold 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> hold; baseline=20260715; task_id=20260715_20260716_002371_d_observe_llm_v2; MA20触发位置=-8.44%

## 2. 002475 立讯精密

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-16T09:25:35; trade_time=09:25:00; trade_date=2026-07-16
- 实时行情: 现价=60.86; 涨跌幅=+0.64%; 振幅=0.00%; 成交额=0.51亿
- 均线偏离: MA5=-1.11%; MA20=-7.52%; MA60=-11.48%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 说明盘中有波动但缺乏趋势修复力度，更像弱反弹或低位整理，不能支持强上行解读。
- LLM客观评价: D线触发: 说明盘中有波动但缺乏趋势修复力度，更像弱反弹或低位整理，不能支持强上行解读。 观察目的: 验证立讯精密次日是否能从均线下方弱势结构中完成短线修复，还是继续呈现破位/弱反弹，从而确认C线“watch up”是否成立。 主要风险: 当前价格仍明显位于MA5/MA10/MA20下方，若量能不配合，盘中修复大概率只是弱反弹而非有效反转。 对C线反馈: watch -> weak_rebound_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> weak_rebound_review; baseline=20260715; task_id=20260715_20260716_002475_d_observe_llm_v2; MA20触发位置=-7.52%

## 3. 600183 生益科技

- 触发: breakdown_confirm / severity=high / fire_count=1
- 时间: forecast_ts=2026-07-16T09:25:37; trade_time=09:25:05; trade_date=2026-07-16
- 实时行情: 现价=148.00; 涨跌幅=-2.91%; 振幅=0.00%; 成交额=1.21亿
- 均线偏离: MA5=-0.21%; MA20=-9.58%; MA60=+16.21%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 说明弱势继续扩大，20日线下方的修复假设失效，需把C线上行预期降级。
- LLM客观评价: D线触发: 说明弱势继续扩大，20日线下方的修复假设失效，需把C线上行预期降级。 观察目的: 验证明日盘中是否能从20日线下方的弱势修复，转为站回短中期均线并维持，从而确认C线的“watch/up”假设。 主要风险: 当前价格仍低于20日线，MACD为负且AI算力赛道上限被压制，若盘中修复失败，C线的上行判断会被继续走弱所证伪。 对C线反馈: watch -> avoid_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> avoid_review; baseline=20260715; task_id=20260715_20260716_600183_d_observe_llm_v2; MA20触发位置=-9.58%

## 4. 600522 中天科技

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-16T09:25:38; trade_time=09:25:02; trade_date=2026-07-16
- 实时行情: 现价=39.51; 涨跌幅=-2.92%; 振幅=0.00%; 成交额=0.99亿
- 均线偏离: MA5=-9.35%; MA20=-25.38%; MA60=-12.95%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 说明反弹力度不足，仍停留在弱势区间，C线的正向预期只能被视为低质量观察。
- LLM客观评价: D线触发: 说明反弹力度不足，仍停留在弱势区间，C线的正向预期只能被视为低质量观察。 观察目的: 验证次日盘中超跌修复是否能真正收复短均线，还是继续在20日线下方演化为弱势延续。 主要风险: 当前处于明显超跌但中期趋势仍弱，最大风险是任何盘中反弹都只是噪声修复，最终继续破位下行。 对C线反馈: watch -> downgrade_confidence 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> downgrade_confidence; baseline=20260715; task_id=20260715_20260716_600522_d_observe_llm_v2; MA20触发位置=-25.38%

## 5. 600900 长江电力

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-16T09:25:40; trade_time=09:25:12; trade_date=2026-07-16
- 实时行情: 现价=28.65; 涨跌幅=-0.10%; 振幅=0.00%; 成交额=0.33亿
- 均线偏离: MA5=+1.27%; MA20=+5.18%; MA60=+5.30%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 价格仍在高位但波动收敛、量能未改善，说明更多是高位钝化而非有效修复，符合继续观察而非强化乐观的情形。
- LLM客观评价: D线触发: 价格仍在高位但波动收敛、量能未改善，说明更多是高位钝化而非有效修复，符合继续观察而非强化乐观的情形。 观察目的: 验证长江电力次日是否只是高位超买后的弱整理/回撤，而不是在当前高位继续维持强势并尝试加速延续。 主要风险: 高位超买背景下短线支撑失守，出现放量回撤或快速走弱，使‘观察等待/回避’被盘中结构证实。 对C线反馈: avoid -> hold_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=avoid -> hold_review; baseline=20260715; task_id=20260715_20260716_600900_d_observe_llm_v2; MA20触发位置=+5.18%

## 6. 002384 东山精密

- 触发: failed_breakout / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-16T09:30:51; trade_time=09:30:42; trade_date=2026-07-16
- 实时行情: 现价=254.12; 涨跌幅=-3.19%; 振幅=1.71%; 成交额=13.95亿
- 均线偏离: MA5=+0.59%; MA20=+1.17%; MA60=+14.26%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 仍在均线上方但无法维持正向推进，属于假突破或弱承接，需要下调对看多延续的信任度。
- LLM客观评价: D线触发: 仍在均线上方但无法维持正向推进，属于假突破或弱承接，需要下调对看多延续的信任度。 观察目的: 明日盘中验证东山精密在高位区间能否延续C线的看多观察假设，重点看上方延续是否被放量确认，还是出现高位冲高回落或破位。 主要风险: 高位乖离较大且AI算力上限偏保守，若次日盘中量能跟不上，最容易出现冲高回落并削弱C线的看多观察逻辑。 对C线反馈: watch -> downgrade_confidence 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> downgrade_confidence; baseline=20260715; task_id=20260715_20260716_002384_d_observe_llm_v2; MA20触发位置=+1.17%

## 7. 603009 北特科技

- 触发: breakdown_confirm / severity=high / fire_count=1
- 时间: forecast_ts=2026-07-16T09:30:53; trade_time=09:30:47; trade_date=2026-07-16
- 实时行情: 现价=45.04; 涨跌幅=-1.62%; 振幅=2.40%; 成交额=0.04亿
- 均线偏离: MA5=-2.73%; MA20=-3.30%; MA60=-7.57%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 若继续显著远离20日线并逼近更弱位置，说明右侧修复失败，C线的向上观察假设被证伪。
- LLM客观评价: D线触发: 若继续显著远离20日线并逼近更弱位置，说明右侧修复失败，C线的向上观察假设被证伪。 观察目的: 验证北特科技次日能否从20日线下方完成修复并重新站稳，还是继续弱势回撤，从而确认C线“watch/up”假设是否成立。 主要风险: 当前价格仍低于MA5、MA20和MA60，且5日量比偏低，核心风险是修复不成反而演变为弱反弹或继续回撤。 对C线反馈: watch -> avoid_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> avoid_review; baseline=20260715; task_id=20260715_20260716_603009_d_observe_llm_v2; MA20触发位置=-3.30%

## 8. 600183 生益科技

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-16T09:41:14; trade_time=09:41:01; trade_date=2026-07-16
- 实时行情: 现价=152.69; 涨跌幅=+0.17%; 振幅=5.88%; 成交额=18.89亿
- 均线偏离: MA5=+2.95%; MA20=-6.71%; MA60=+19.89%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 说明盘中有修复但仍受20日线压制，更像弱反弹而不是趋势转强。
- LLM客观评价: D线触发: 说明盘中有修复但仍受20日线压制，更像弱反弹而不是趋势转强。 观察目的: 验证明日盘中是否能从20日线下方的弱势修复，转为站回短中期均线并维持，从而确认C线的“watch/up”假设。 主要风险: 当前价格仍低于20日线，MACD为负且AI算力赛道上限被压制，若盘中修复失败，C线的上行判断会被继续走弱所证伪。 对C线反馈: watch -> lower_confidence 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> lower_confidence; baseline=20260715; task_id=20260715_20260716_600183_d_observe_llm_v2; MA20触发位置=-6.71%

## 9. 002050 三花智控

- 触发: weak_rebound / severity=low / fire_count=1
- 时间: forecast_ts=2026-07-16T09:46:24; trade_time=09:46:15; trade_date=2026-07-16
- 实时行情: 现价=42.04; 涨跌幅=+1.30%; 振幅=3.30%; 成交额=4.48亿
- 均线偏离: MA5=-0.42%; MA20=-4.03%; MA60=-10.07%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明只是弱反弹而非结构扭转，仍支持回避框架。
- LLM客观评价: D线触发: 说明只是弱反弹而非结构扭转，仍支持回避框架。 观察目的: 验证 C线“非 panic 且默认回避”在次日是否表现为继续弱于20日线的技术性延续，还是被快速收复5/10日线所推翻。 主要风险: 盘中若出现对5日线和10日线的同步收复，说明回避依据可能只是短期回撤而非结构性走弱。 对C线反馈: hold_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=hold_avoid; baseline=20260715; task_id=20260715_20260716_002050_d_observe_llm_v2; MA20触发位置=-4.03%

## 10. 002384 东山精密

- 触发: breakout_confirm / severity=high / fire_count=2
- 时间: forecast_ts=2026-07-16T09:46:26; trade_time=09:46:15; trade_date=2026-07-16
- 实时行情: 现价=267.50; 涨跌幅=+1.91%; 振幅=8.84%; 成交额=87.30亿
- 均线偏离: MA5=+5.88%; MA20=+6.50%; MA60=+20.27%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 盘中继续站稳短均并伴随放量/波动扩张，说明C线的看多观察假设被有效确认。
- LLM客观评价: D线触发: 盘中继续站稳短均并伴随放量/波动扩张，说明C线的看多观察假设被有效确认。 观察目的: 明日盘中验证东山精密在高位区间能否延续C线的看多观察假设，重点看上方延续是否被放量确认，还是出现高位冲高回落或破位。 主要风险: 高位乖离较大且AI算力上限偏保守，若次日盘中量能跟不上，最容易出现冲高回落并削弱C线的看多观察逻辑。 对C线反馈: watch -> confirm_upside 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> confirm_upside; baseline=20260715; task_id=20260715_20260716_002384_d_observe_llm_v2; MA20触发位置=+6.50%

## 11. 600276 恒瑞医药

- 触发: breakdown_confirm / severity=high / fire_count=1
- 时间: forecast_ts=2026-07-16T09:46:28; trade_time=09:46:18; trade_date=2026-07-16
- 实时行情: 现价=55.66; 涨跌幅=-3.20%; 振幅=3.29%; 成交额=22.26亿
- 均线偏离: MA5=-0.40%; MA20=+5.52%; MA60=+7.15%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明股价已从高位强势区转弱，短线承接失败，C线的回避判断得到盘中验证。
- LLM客观评价: D线触发: 说明股价已从高位强势区转弱，短线承接失败，C线的回避判断得到盘中验证。 观察目的: 验证恒瑞医药次日是否只是高位弱势震荡或回落，而不是在高位继续放量上冲形成新的强势延续。 主要风险: 高位强势惯性继续扩展，导致C线的回避判断被盘中突破行为推翻。 对C线反馈: maintain_avoid -> confirm_weakness 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=maintain_avoid -> confirm_weakness; baseline=20260715; task_id=20260715_20260716_600276_d_observe_llm_v2; MA20触发位置=+5.52%

## 12. 601689 拓普集团

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-16T09:46:30; trade_time=09:46:20; trade_date=2026-07-16
- 实时行情: 现价=55.03; 涨跌幅=+0.97%; 振幅=3.58%; 成交额=3.29亿
- 均线偏离: MA5=-0.31%; MA20=-3.85%; MA60=-11.36%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明出现的是弱修复而非结构性转强，更多是对回避判断的边际噪音。
- LLM客观评价: D线触发: 说明出现的是弱修复而非结构性转强，更多是对回避判断的边际噪音。 观察目的: 验证C线“非panic且评分<2→回避”的假设：明天盘中是否仍以MA20/MA60下方弱势运行，还是出现有效收复并转为修复。 主要风险: 盘中若快速收复短中期均线并放量，当前回避判断会失效；反之若继续在MA20下方走弱，则C线回避得到验证。 对C线反馈: watch_only 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch_only; baseline=20260715; task_id=20260715_20260716_601689_d_observe_llm_v2; MA20触发位置=-3.85%

## 13. 603667 五洲新春

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-16T09:46:32; trade_time=09:46:22; trade_date=2026-07-16
- 实时行情: 现价=59.31; 涨跌幅=+0.02%; 振幅=3.02%; 成交额=1.51亿
- 均线偏离: MA5=-0.68%; MA20=-7.69%; MA60=-15.93%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明只出现弱反弹且量能不足，属于典型技术性修复而非趋势反转，更符合低优先级观察而非追认强势。
- LLM客观评价: D线触发: 说明只出现弱反弹且量能不足，属于典型技术性修复而非趋势反转，更符合低优先级观察而非追认强势。 观察目的: 明天盘中观察五洲新春是否继续维持低于20日线的弱势回避状态，还是出现放量收复短中期均线从而推翻 C 线的 avoid 判断。 主要风险: 盘中若快速收复MA5/MA20且成交放大，说明‘非 panic、评分偏低而回避’的结论可能失效。 对C线反馈: support_avoid_neutral 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=support_avoid_neutral; baseline=20260715; task_id=20260715_20260716_603667_d_observe_llm_v2; MA20触发位置=-7.69%

## 14. 600580 卧龙电驱

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-16T09:56:52; trade_time=09:56:40; trade_date=2026-07-16
- 实时行情: 现价=31.80; 涨跌幅=+1.15%; 振幅=3.59%; 成交额=2.22亿
- 均线偏离: MA5=-1.33%; MA20=-6.41%; MA60=-15.07%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 说明有反弹，但力度仍偏弱，更像技术性修复而不是趋势确认。
- LLM客观评价: D线触发: 说明有反弹，但力度仍偏弱，更像技术性修复而不是趋势确认。 观察目的: 明天盘中重点验证卧龙电驱是否能把EOD的弱势回撤转成有效修复，确认C线“watch/up”是静态评分驱动还是有真实的盘中均线收复迹象。 主要风险: 当前价格仍显著低于MA20且近5日、近20日都偏弱，若明天只出现缩量反弹而不能改善均线位置，这个上行观察假设很容易失效。 对C线反馈: watch -> keep_monitor 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> keep_monitor; baseline=20260715; task_id=20260715_20260716_600580_d_observe_llm_v2; MA20触发位置=-6.41%

## 15. 601689 拓普集团

- 触发: breakdown_confirm / severity=high / fire_count=2
- 时间: forecast_ts=2026-07-16T11:19:20; trade_time=11:19:17; trade_date=2026-07-16
- 实时行情: 现价=54.90; 涨跌幅=+0.73%; 振幅=4.59%; 成交额=10.15亿
- 均线偏离: MA5=-0.54%; MA20=-4.07%; MA60=-11.57%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明弱势延续并伴随波动放大，C线“回避”假设得到强化。
- LLM客观评价: D线触发: 说明弱势延续并伴随波动放大，C线“回避”假设得到强化。 观察目的: 验证C线“非panic且评分<2→回避”的假设：明天盘中是否仍以MA20/MA60下方弱势运行，还是出现有效收复并转为修复。 主要风险: 盘中若快速收复短中期均线并放量，当前回避判断会失效；反之若继续在MA20下方走弱，则C线回避得到验证。 对C线反馈: keep_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=keep_avoid; baseline=20260715; task_id=20260715_20260716_601689_d_observe_llm_v2; MA20触发位置=-4.07%

## 16. 603667 五洲新春

- 触发: breakdown_confirm / severity=high / fire_count=2
- 时间: forecast_ts=2026-07-16T13:04:55; trade_time=13:04:49; trade_date=2026-07-16
- 实时行情: 现价=59.05; 涨跌幅=-0.42%; 振幅=4.32%; 成交额=5.33亿
- 均线偏离: MA5=-1.11%; MA20=-8.10%; MA60=-16.30%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明弱势没有被盘中修复，价格仍处在中长期均线下方并且动量不强，C线的回避结论得到强化。
- LLM客观评价: D线触发: 说明弱势没有被盘中修复，价格仍处在中长期均线下方并且动量不强，C线的回避结论得到强化。 观察目的: 明天盘中观察五洲新春是否继续维持低于20日线的弱势回避状态，还是出现放量收复短中期均线从而推翻 C 线的 avoid 判断。 主要风险: 盘中若快速收复MA5/MA20且成交放大，说明‘非 panic、评分偏低而回避’的结论可能失效。 对C线反馈: validate_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=validate_avoid; baseline=20260715; task_id=20260715_20260716_603667_d_observe_llm_v2; MA20触发位置=-8.10%

## 17. 002463 沪电股份

- 触发: breakdown_confirm / severity=high / fire_count=1
- 时间: forecast_ts=2026-07-16T14:47:56; trade_time=14:47:48; trade_date=2026-07-16
- 实时行情: 现价=134.60; 涨跌幅=-1.92%; 振幅=7.16%; 成交额=102.47亿
- 均线偏离: MA5=+1.09%; MA20=-3.20%; MA60=+8.67%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若继续在MA20下方走弱且波动/量能同步放大，说明弱势延续，C线的avoid判断得到强化。
- LLM客观评价: D线触发: 若继续在MA20下方走弱且波动/量能同步放大，说明弱势延续，C线的avoid判断得到强化。 观察目的: 验证沪电股份次日盘中是否仍被MA20压制、延续弱势回避逻辑，还是出现放量收复MA20的修复信号。 主要风险: 最大的风险是盘中有效收复并稳定站上MA20，导致C线的avoid/neutral判断被修正。 对C线反馈: confirm_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=confirm_avoid; baseline=20260715; task_id=20260715_20260716_002463_d_observe_llm_v2; MA20触发位置=-3.20%
