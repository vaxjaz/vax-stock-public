# D线盘中触发汇总

- updated_at: 2026-07-15T13:11:10
- trade_date: 2026-07-15
- triggers: 21
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 002384 东山精密

- 触发: panic_rebound_probe / severity=low / fire_count=3
- 时间: forecast_ts=2026-07-15T09:27:04; trade_time=09:25:00; trade_date=2026-07-15
- 实时行情: 现价=261.00; 涨跌幅=+0.24%; 振幅=0.00%; 成交额=7.15亿
- 均线偏离: MA5=+5.39%; MA20=+4.19%; MA60=+18.35%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 盘中保持在关键均线上方且出现正向变化，说明C线所说的恐慌修复有被验证的可能。
- LLM客观评价: D线触发: 盘中保持在关键均线上方且出现正向变化，说明C线所说的恐慌修复有被验证的可能。 观察目的: 验证东山精密在恐慌市场下次日是否能延续高位修复并稳定站在MA5/MA20之上，还是出现高位回落并把盘前反弹定义为弱修复。 主要风险: 高位区间叠加panic regime，次日反弹若缺少持续性，容易从情绪修复转为高位回落或破位。 对C线反馈: confirm_rebound_watch 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=confirm_rebound_watch; baseline=20260714; task_id=20260714_20260715_002384_d_observe_llm_v2; MA20触发位置=+4.19%

## 2. 002384 东山精密

- 触发: weak_rebound / severity=medium / fire_count=4
- 时间: forecast_ts=2026-07-15T09:27:06; trade_time=09:25:00; trade_date=2026-07-15
- 实时行情: 现价=261.00; 涨跌幅=+0.24%; 振幅=0.00%; 成交额=7.15亿
- 均线偏离: MA5=+5.39%; MA20=+4.19%; MA60=+18.35%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 价格虽为正但量能/动能不跟，说明更像弱反弹而不是强修复。
- LLM客观评价: D线触发: 价格虽为正但量能/动能不跟，说明更像弱反弹而不是强修复。 观察目的: 验证东山精密在恐慌市场下次日是否能延续高位修复并稳定站在MA5/MA20之上，还是出现高位回落并把盘前反弹定义为弱修复。 主要风险: 高位区间叠加panic regime，次日反弹若缺少持续性，容易从情绪修复转为高位回落或破位。 对C线反馈: downgrade_rebound_quality 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=downgrade_rebound_quality; baseline=20260714; task_id=20260714_20260715_002384_d_observe_llm_v2; MA20触发位置=+4.19%

## 3. 002463 沪电股份

- 触发: panic_rebound_probe / severity=high / fire_count=4
- 时间: forecast_ts=2026-07-15T09:27:08; trade_time=09:25:00; trade_date=2026-07-15
- 实时行情: 现价=140.98; 涨跌幅=+2.81%; 振幅=0.00%; 成交额=2.60亿
- 均线偏离: MA5=+7.33%; MA20=+1.26%; MA60=+14.48%
- C线原始预测: action=panic_rebound_probe; direction=neutral; confidence=40%
- 触发依据: 说明盘中不仅有反弹，而且已经把价格带回短中期均线上方，符合恐慌修复被验证的情形。
- LLM客观评价: D线触发: 说明盘中不仅有反弹，而且已经把价格带回短中期均线上方，符合恐慌修复被验证的情形。 观察目的: 验证在恐慌市背景下，沪电股份次日盘中是否能把低分票的“恐慌修复”演化为有效反弹，核心看能否放量收复并站稳20日线，而不是只做弱反抽后再度走弱。 主要风险: 在市场恐慌与近期资金净流出背景下，盘中反弹若始终无法收复20日线，修复大概率只是技术性回抽，后续容易重新转弱并回到破位风险。 对C线反馈: probe_confirm -> keep_observe 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。 ⚠️[铁律校验] 检测到疑似越界(盘中新评分/买卖价/资金臆测), 以EOD报告为准, 盘中未定论
- C线反哺线索: expected_feedback_to_c=probe_confirm -> keep_observe; baseline=20260714; task_id=20260714_20260715_002463_d_observe_llm_v2; MA20触发位置=+1.26%

## 4. 002475 立讯精密

- 触发: weak_rebound / severity=medium / fire_count=3
- 时间: forecast_ts=2026-07-15T09:27:10; trade_time=09:25:00; trade_date=2026-07-15
- 实时行情: 现价=62.25; 涨跌幅=+0.94%; 振幅=0.00%; 成交额=0.48亿
- 均线偏离: MA5=+0.49%; MA20=-5.89%; MA60=-9.46%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 若只是小幅反弹但仍远离MA20，且量能/动量没有同步改善，则更像弱修复而非有效反转。
- LLM客观评价: D线触发: 若只是小幅反弹但仍远离MA20，且量能/动量没有同步改善，则更像弱修复而非有效反转。 观察目的: 明天观察该票在 panic 市场中是否能完成从跌破MA20后的修复性反弹，验证 C线的 panic_rebound_watch 是否只是弱反抽还是具备真正修复信号。 主要风险: 反弹若无法收复MA5/MA10并继续受制于MA20，则很可能只是弱修复，随后重新转弱并延续对MA60的下压。 对C线反馈: watch -> weak_rebound_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> weak_rebound_review; baseline=20260714; task_id=20260714_20260715_002475_d_observe_llm_v2; MA20触发位置=-5.89%

## 5. 600183 生益科技

- 触发: panic_rebound_probe / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-15T09:27:11; trade_time=09:26:48; trade_date=2026-07-15
- 实时行情: 现价=154.01; 涨跌幅=+4.13%; 振幅=0.00%; 成交额=2.52亿
- 均线偏离: MA5=+4.83%; MA20=-6.68%; MA60=+22.28%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 盘中出现正向变化且重新贴近MA5，说明超跌修复开始被验证，但仍需进一步观察是否能延伸。
- LLM客观评价: D线触发: 盘中出现正向变化且重新贴近MA5，说明超跌修复开始被验证，但仍需进一步观察是否能延伸。 观察目的: 验证在 panic 市场中，生益科技次日盘中是否能出现有效情绪修复，并从超跌反抽进一步演化为对短中期均线的收复。 主要风险: 反弹只停留在弱修复，无法持续站回MA5/MA10并向MA20靠拢，最终在放量下行中重新确认弱势。 对C线反馈: watch -> rebound_validate 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> rebound_validate; baseline=20260714; task_id=20260714_20260715_600183_d_observe_llm_v2; MA20触发位置=-6.68%

## 6. 600183 生益科技

- 触发: reclaim_confirm / severity=high / fire_count=2
- 时间: forecast_ts=2026-07-15T09:27:13; trade_time=09:26:48; trade_date=2026-07-15
- 实时行情: 现价=154.01; 涨跌幅=+4.13%; 振幅=0.00%; 成交额=2.52亿
- 均线偏离: MA5=+4.83%; MA20=-6.68%; MA60=+22.28%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 如果盘中能同时改善短中期均线相对位置并伴随量能或动能回暖，说明C线的情绪修复假设获得更强验证。
- LLM客观评价: D线触发: 如果盘中能同时改善短中期均线相对位置并伴随量能或动能回暖，说明C线的情绪修复假设获得更强验证。 观察目的: 验证在 panic 市场中，生益科技次日盘中是否能出现有效情绪修复，并从超跌反抽进一步演化为对短中期均线的收复。 主要风险: 反弹只停留在弱修复，无法持续站回MA5/MA10并向MA20靠拢，最终在放量下行中重新确认弱势。 对C线反馈: rebound_confirm -> strengthen 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=rebound_confirm -> strengthen; baseline=20260714; task_id=20260714_20260715_600183_d_observe_llm_v2; MA20触发位置=-6.68%

## 7. 601689 拓普集团

- 触发: weak_rebound / severity=low / fire_count=1
- 时间: forecast_ts=2026-07-15T09:27:15; trade_time=09:26:40; trade_date=2026-07-15
- 实时行情: 现价=54.50; 涨跌幅=+0.26%; 振幅=0.00%; 成交额=0.06亿
- 均线偏离: MA5=-1.35%; MA20=-5.29%; MA60=-12.37%
- C线原始预测: action=panic_rebound_probe; direction=neutral; confidence=40%
- 触发依据: 说明盘中出现反弹但仍未摆脱短中期均线压制，更像弱反抽而非趋势修复。
- LLM客观评价: D线触发: 说明盘中出现反弹但仍未摆脱短中期均线压制，更像弱反抽而非趋势修复。 观察目的: 验证C线“panic_rebound_probe”是否只是弱修复，重点看次日盘中能否收复短均线并脱离弱势区，还是继续沿恐慌趋势下探。 主要风险: 恐慌环境下反弹失败，价格持续运行在MA5/MA20/MA60下方并扩大弱势，导致C线的弱修复假设被证伪。 对C线反馈: rebound_seen_but_unconfirmed 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=rebound_seen_but_unconfirmed; baseline=20260714; task_id=20260714_20260715_601689_d_observe_llm_v2; MA20触发位置=-5.29%

## 8. 600276 恒瑞医药

- 触发: noise_filter / severity=low / fire_count=3
- 时间: forecast_ts=2026-07-15T09:32:24; trade_time=09:32:16; trade_date=2026-07-15
- 实时行情: 现价=55.01; 涨跌幅=+0.35%; 振幅=1.88%; 成交额=3.16亿
- 均线偏离: MA5=-0.32%; MA20=+5.30%; MA60=+5.90%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 有反弹但仍未收复短线均线，更像噪音式修复，不能据此确认 C 线方向。
- LLM客观评价: D线触发: 有反弹但仍未收复短线均线，更像噪音式修复，不能据此确认 C 线方向。 观察目的: 验证 C 线的 panic_rebound_watch 假设：恒瑞医药在大盘恐慌环境下是否能完成盘中修复并守住短线均线，而不是只有弱反弹后回吐。 主要风险: 恐慌修复缺乏量能支撑，反弹停留在 ma5 下方或重新跌回 ma20 下方，最终演变成弱修复而非有效反弹。 对C线反馈: weak rebound only / keep observing 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=weak rebound only / keep observing; baseline=20260714; task_id=20260714_20260715_600276_d_observe_llm_v2; MA20触发位置=+5.30%

## 9. 600900 长江电力

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-15T09:32:27; trade_time=09:32:19; trade_date=2026-07-15
- 实时行情: 现价=28.47; 涨跌幅=-0.28%; 振幅=0.88%; 成交额=2.96亿
- 均线偏离: MA5=+1.24%; MA20=+4.81%; MA60=+4.78%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 价格没有明显转弱，但修复幅度和活跃度都不足，属于弱反弹或钝化状态，说明C线的修复预期兑现度有限。
- LLM客观评价: D线触发: 价格没有明显转弱，但修复幅度和活跃度都不足，属于弱反弹或钝化状态，说明C线的修复预期兑现度有限。 观察目的: 验证长江电力在大盘恐慌环境下，次日盘中是否能维持高位韧性并出现情绪修复，而不是从高位转入回撤或弱反弹失败。 主要风险: 高位强势后的恐慌环境压制修复力度，导致盘中冲高不持续、回落跌破关键均线，C线的panic_rebound_watch被证伪。 对C线反馈: watch -> downgrade_rebound_quality 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> downgrade_rebound_quality; baseline=20260714; task_id=20260714_20260715_600900_d_observe_llm_v2; MA20触发位置=+4.81%

## 10. 603728 鸣志电器

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-15T09:32:28; trade_time=09:32:23; trade_date=2026-07-15
- 实时行情: 现价=55.99; 涨跌幅=+0.52%; 振幅=1.76%; 成交额=0.28亿
- 均线偏离: MA5=-3.57%; MA20=-7.53%; MA60=-9.67%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 说明有反弹动作，但力度和量能都不足，更像低质量回拉而非真正修复。
- LLM客观评价: D线触发: 说明有反弹动作，但力度和量能都不足，更像低质量回拉而非真正修复。 观察目的: 验证 C线的 panic_rebound_watch 假设：明天盘中是否会出现从弱势区间向上修复、并非只是低量超跌反抽的情绪修复行为。 主要风险: 在 panic 市场里只出现无量弱反弹，价格仍持续受制于 MA5/MA20 下方，导致修复被证伪并回到下行趋势。 对C线反馈: panic_rebound_watch -> downgrade_rebound_quality 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=panic_rebound_watch -> downgrade_rebound_quality; baseline=20260714; task_id=20260714_20260715_603728_d_observe_llm_v2; MA20触发位置=-7.53%

## 11. 600276 恒瑞医药

- 触发: panic_rebound_probe / severity=medium / fire_count=4
- 时间: forecast_ts=2026-07-15T09:37:37; trade_time=09:37:31; trade_date=2026-07-15
- 实时行情: 现价=55.66; 涨跌幅=+1.53%; 振幅=2.65%; 成交额=8.11亿
- 均线偏离: MA5=+0.86%; MA20=+6.54%; MA60=+7.15%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 说明恐慌后的主动修复开始成立，而不是单纯低位震荡。
- LLM客观评价: D线触发: 说明恐慌后的主动修复开始成立，而不是单纯低位震荡。 观察目的: 验证 C 线的 panic_rebound_watch 假设：恒瑞医药在大盘恐慌环境下是否能完成盘中修复并守住短线均线，而不是只有弱反弹后回吐。 主要风险: 恐慌修复缺乏量能支撑，反弹停留在 ma5 下方或重新跌回 ma20 下方，最终演变成弱修复而非有效反弹。 对C线反馈: validate panic_rebound_watch / keep confidence 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=validate panic_rebound_watch / keep confidence; baseline=20260714; task_id=20260714_20260715_600276_d_observe_llm_v2; MA20触发位置=+6.54%

## 12. 600276 恒瑞医药

- 触发: reclaim_confirm / severity=high / fire_count=5
- 时间: forecast_ts=2026-07-15T09:37:39; trade_time=09:37:31; trade_date=2026-07-15
- 实时行情: 现价=55.66; 涨跌幅=+1.53%; 振幅=2.65%; 成交额=8.11亿
- 均线偏离: MA5=+0.86%; MA20=+6.54%; MA60=+7.15%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 短线均线被重新站上，说明修复从情绪层面升级为结构层面。
- LLM客观评价: D线触发: 短线均线被重新站上，说明修复从情绪层面升级为结构层面。 观察目的: 验证 C 线的 panic_rebound_watch 假设：恒瑞医药在大盘恐慌环境下是否能完成盘中修复并守住短线均线，而不是只有弱反弹后回吐。 主要风险: 恐慌修复缺乏量能支撑，反弹停留在 ma5 下方或重新跌回 ma20 下方，最终演变成弱修复而非有效反弹。 对C线反馈: confirm rebound / raise confidence 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=confirm rebound / raise confidence; baseline=20260714; task_id=20260714_20260715_600276_d_observe_llm_v2; MA20触发位置=+6.54%

## 13. 601138 工业富联

- 触发: breakdown_confirm / severity=high / fire_count=2
- 时间: forecast_ts=2026-07-15T09:37:41; trade_time=09:37:33; trade_date=2026-07-15
- 实时行情: 现价=65.02; 涨跌幅=-0.88%; 振幅=1.69%; 成交额=8.79亿
- 均线偏离: MA5=-1.63%; MA20=-7.04%; MA60=-5.96%
- C线原始预测: action=watch_only; direction=neutral; confidence=45%
- 触发依据: 若继续远离 MA20/MA60 且伴随波动或动能恶化，说明盘中是延续性走弱而不是有效修复。
- LLM客观评价: D线触发: 若继续远离 MA20/MA60 且伴随波动或动能恶化，说明盘中是延续性走弱而不是有效修复。 观察目的: 验证 C 线“评分≥2但处 panic 仅观察”的假设：明天盘中是向上收回短均线形成修复，还是继续在 MA20/MA60 下方破位延续。 主要风险: 在 panic 市场里，价格仍显著低于 MA20/MA60，若盘中无法重新站回短均线，当前反弹更可能只是弱修复而非有效止跌。 对C线反馈: watch_only -> confirm_panic_breakdown 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch_only -> confirm_panic_breakdown; baseline=20260714; task_id=20260714_20260715_601138_d_observe_llm_v2; MA20触发位置=-7.04%

## 14. 603728 鸣志电器

- 触发: risk_off_confirm / severity=high / fire_count=3
- 时间: forecast_ts=2026-07-15T09:37:43; trade_time=09:37:35; trade_date=2026-07-15
- 实时行情: 现价=54.83; 涨跌幅=-1.56%; 振幅=3.72%; 成交额=0.51亿
- 均线偏离: MA5=-5.56%; MA20=-9.45%; MA60=-11.54%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 说明盘中不是修复而是延续风险释放，反弹假设失效。
- LLM客观评价: D线触发: 说明盘中不是修复而是延续风险释放，反弹假设失效。 观察目的: 验证 C线的 panic_rebound_watch 假设：明天盘中是否会出现从弱势区间向上修复、并非只是低量超跌反抽的情绪修复行为。 主要风险: 在 panic 市场里只出现无量弱反弹，价格仍持续受制于 MA5/MA20 下方，导致修复被证伪并回到下行趋势。 对C线反馈: panic_rebound_watch -> invalidate_rebound 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=panic_rebound_watch -> invalidate_rebound; baseline=20260714; task_id=20260714_20260715_603728_d_observe_llm_v2; MA20触发位置=-9.45%

## 15. 002371 北方华创

- 触发: breakdown_confirm / severity=high / fire_count=4
- 时间: forecast_ts=2026-07-15T09:42:52; trade_time=09:42:45; trade_date=2026-07-15
- 实时行情: 现价=753.11; 涨跌幅=-2.72%; 振幅=5.30%; 成交额=18.40亿
- 均线偏离: MA5=-6.34%; MA20=-5.50%; MA60=+15.25%
- C线原始预测: action=watch_only; direction=neutral; confidence=45%
- 触发依据: 说明短线支撑进一步失效，panic 延续得到机械确认，C 线的 watch_only 假设应被视为偏弱势验证。
- LLM客观评价: D线触发: 说明短线支撑进一步失效，panic 延续得到机械确认，C 线的 watch_only 假设应被视为偏弱势验证。 观察目的: 验证在 panic 市场中，北方华创次日盘中是继续失守 MA20/MA10 并放大波动，还是完成收回确认短线修复。 主要风险: 短线修复失败，价格持续压在 MA20/MA10 下方并伴随波动放大，导致 C 线的“仅观察”假设被更强的风险回避信号证实。 对C线反馈: watch_only -> confirm_panic_downgrade 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch_only -> confirm_panic_downgrade; baseline=20260714; task_id=20260714_20260715_002371_d_observe_llm_v2; MA20触发位置=-5.50%

## 16. 603009 北特科技

- 触发: breakdown_confirm / severity=high / fire_count=3
- 时间: forecast_ts=2026-07-15T09:42:54; trade_time=09:42:48; trade_date=2026-07-15
- 实时行情: 现价=44.34; 涨跌幅=-1.90%; 振幅=3.08%; 成交额=0.36亿
- 均线偏离: MA5=-4.60%; MA20=-4.56%; MA60=-9.17%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 继续远离短均线并伴随成交放大或近5日跌势延续，说明修复失败并且弱势延续被确认。
- LLM客观评价: D线触发: 继续远离短均线并伴随成交放大或近5日跌势延续，说明修复失败并且弱势延续被确认。 观察目的: 验证在市场恐慌背景下，北特科技次日是否能完成对MA5/MA20的盘中修复，还是继续走出修复失败的弱势延续。 主要风险: 盘中反弹若不能收复短均线且量能不配合，很可能只是恐慌环境中的技术性抽拉，C线的T+1情绪修复假设会失效。 对C线反馈: watch -> avoid_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> avoid_review; baseline=20260714; task_id=20260714_20260715_603009_d_observe_llm_v2; MA20触发位置=-4.56%

## 17. 603009 北特科技

- 触发: weak_rebound / severity=medium / fire_count=4
- 时间: forecast_ts=2026-07-15T10:08:34; trade_time=10:08:30; trade_date=2026-07-15
- 实时行情: 现价=46.10; 涨跌幅=+1.99%; 振幅=4.87%; 成交额=0.93亿
- 均线偏离: MA5=-0.81%; MA20=-0.77%; MA60=-5.57%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 价格仍未完全收复关键均线，但修复幅度出现，属于弱反弹/半修复状态，需要继续观察是否能升级为确认。
- LLM客观评价: D线触发: 价格仍未完全收复关键均线，但修复幅度出现，属于弱反弹/半修复状态，需要继续观察是否能升级为确认。 观察目的: 验证在市场恐慌背景下，北特科技次日是否能完成对MA5/MA20的盘中修复，还是继续走出修复失败的弱势延续。 主要风险: 盘中反弹若不能收复短均线且量能不配合，很可能只是恐慌环境中的技术性抽拉，C线的T+1情绪修复假设会失效。 对C线反馈: watch -> continue_observe 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> continue_observe; baseline=20260714; task_id=20260714_20260715_603009_d_observe_llm_v2; MA20触发位置=-0.77%

## 18. 002463 沪电股份

- 触发: weak_rebound / severity=medium / fire_count=5
- 时间: forecast_ts=2026-07-15T10:13:46; trade_time=10:13:36; trade_date=2026-07-15
- 实时行情: 现价=139.10; 涨跌幅=+1.44%; 振幅=2.84%; 成交额=65.12亿
- 均线偏离: MA5=+5.90%; MA20=-0.09%; MA60=+12.96%
- C线原始预测: action=panic_rebound_probe; direction=neutral; confidence=40%
- 触发依据: 说明只有短线反抽但仍在20日线下方，更像弱修复而非趋势修复。
- LLM客观评价: D线触发: 说明只有短线反抽但仍在20日线下方，更像弱修复而非趋势修复。 观察目的: 验证在恐慌市背景下，沪电股份次日盘中是否能把低分票的“恐慌修复”演化为有效反弹，核心看能否放量收复并站稳20日线，而不是只做弱反抽后再度走弱。 主要风险: 在市场恐慌与近期资金净流出背景下，盘中反弹若始终无法收复20日线，修复大概率只是技术性回抽，后续容易重新转弱并回到破位风险。 对C线反馈: weak_rebound -> hold_observe 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。 ⚠️[铁律校验] 检测到疑似越界(盘中新评分/买卖价/资金臆测), 以EOD报告为准, 盘中未定论
- C线反哺线索: expected_feedback_to_c=weak_rebound -> hold_observe; baseline=20260714; task_id=20260714_20260715_002463_d_observe_llm_v2; MA20触发位置=-0.09%

## 19. 603009 北特科技

- 触发: reclaim_confirm / severity=high / fire_count=5
- 时间: forecast_ts=2026-07-15T10:24:04; trade_time=10:24:00; trade_date=2026-07-15
- 实时行情: 现价=46.93; 涨跌幅=+3.83%; 振幅=6.04%; 成交额=1.30亿
- 均线偏离: MA5=+0.98%; MA20=+1.01%; MA60=-3.87%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 价格同时收复MA5和MA20，且出现一定量能或波动配合，说明恐慌修复假设得到盘中验证。
- LLM客观评价: D线触发: 价格同时收复MA5和MA20，且出现一定量能或波动配合，说明恐慌修复假设得到盘中验证。 观察目的: 验证在市场恐慌背景下，北特科技次日是否能完成对MA5/MA20的盘中修复，还是继续走出修复失败的弱势延续。 主要风险: 盘中反弹若不能收复短均线且量能不配合，很可能只是恐慌环境中的技术性抽拉，C线的T+1情绪修复假设会失效。 对C线反馈: watch -> confirm_rebound 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> confirm_rebound; baseline=20260714; task_id=20260714_20260715_603009_d_observe_llm_v2; MA20触发位置=+1.01%

## 20. 600522 XD中天科

- 触发: breakdown_confirm / severity=high / fire_count=3
- 时间: forecast_ts=2026-07-15T11:25:38; trade_time=11:25:33; trade_date=2026-07-15
- 实时行情: 现价=41.28; 涨跌幅=-3.08%; 振幅=5.21%; 成交额=62.13亿
- 均线偏离: MA5=-7.06%; MA20=-23.01%; MA60=-8.62%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 若继续扩大对20日均线的负偏离且未见有效修复，说明恐慌未被消化，C线向上假设被削弱。
- LLM客观评价: D线触发: 若继续扩大对20日均线的负偏离且未见有效修复，说明恐慌未被消化，C线向上假设被削弱。 观察目的: 明天盘中重点观察中天科技在恐慌市场下是否出现超跌修复，并重新收复短均线，以验证 C线“panic_rebound_watch”的向上假设。 主要风险: 市场恐慌延续叠加个股技术面偏弱，利好预期无法转化为有效修复，价格继续停留在中长期均线下方并再次走弱。 对C线反馈: watch -> avoid_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> avoid_review; baseline=20260714; task_id=20260714_20260715_600522_d_observe_llm_v2; MA20触发位置=-23.01%

## 21. 601179 中国西电

- 触发: breakdown_confirm / severity=high / fire_count=1
- 时间: forecast_ts=2026-07-15T13:11:10; trade_time=13:11:07; trade_date=2026-07-15
- 实时行情: 现价=12.12; 涨跌幅=-2.57%; 振幅=3.62%; 成交额=7.03亿
- 均线偏离: MA5=-6.52%; MA20=-17.20%; MA60=-24.18%
- C线原始预测: action=panic_rebound_probe; direction=neutral; confidence=40%
- 触发依据: 深度弱势叠加继续下挫或放大波动，说明恐慌修复没有成立，盘中观察应转向证伪而非等待反弹。
- LLM客观评价: D线触发: 深度弱势叠加继续下挫或放大波动，说明恐慌修复没有成立，盘中观察应转向证伪而非等待反弹。 观察目的: 验证 C 线对中国西电的“恐慌后弱修复”判断：次日盘中究竟是超跌反抽、站回短均线，还是继续破位下探。 主要风险: 在 panic 市场与极低 RSI 背景下，当前反弹若无法修复价格对 MA5/MA20 的深度偏离，就更可能只是噪音修复，进而证伪 C 线的 rebound probe 假设。 对C线反馈: panic_rebound_probe -> rejection 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=panic_rebound_probe -> rejection; baseline=20260714; task_id=20260714_20260715_601179_d_observe_llm_v2; MA20触发位置=-17.20%
