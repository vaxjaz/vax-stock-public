# D线盘中触发汇总

- updated_at: 2026-07-07T13:35:03
- trade_date: 2026-07-07
- triggers: 14
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 002050 三花智控

- 触发: reclaim_confirm / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-07T09:25:10; trade_time=09:25:00; trade_date=2026-07-07
- 实时行情: 现价=46.17; 涨跌幅=+0.04%; 振幅=0.00%; 成交额=0.35亿
- 均线偏离: MA5=+1.21%; MA20=+2.71%; MA60=-1.77%
- C线原始预测: action=panic_rebound_probe; direction=neutral; confidence=40%
- 触发依据: 若能同时站回 MA20 和 MA5，且动量不再明显走弱，说明 C 线的恐慌修复假设得到支持。
- LLM客观评价: D线触发: 若能同时站回 MA20 和 MA5，且动量不再明显走弱，说明 C 线的恐慌修复假设得到支持。 观察目的: 明天盘中主要验证三花智控在 panic 市场下的反弹是否只是弱修复，重点看其能否围绕 MA20 附近完成回收并保持，还是很快重新转弱。 主要风险: 在右侧评分回避、10日主力净流出偏大且市场情绪处于 panic 的背景下，最大的风险是反弹只是短暂修复，无法站稳 MA20，随后再次跌回弱势区间。 对C线反馈: probe_valid -> continue_monitor 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。 ⚠️[铁律校验] 检测到疑似越界(盘中新评分/买卖价/资金臆测), 以EOD报告为准, 盘中未定论
- C线反哺线索: expected_feedback_to_c=probe_valid -> continue_monitor; baseline=20260706; task_id=20260706_20260707_002050_d_observe_llm_v2; MA20触发位置=+2.71%

## 2. 600580 卧龙电驱

- 触发: reclaim_confirm / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-07T09:25:15; trade_time=09:25:00; trade_date=2026-07-07
- 实时行情: 现价=37.88; 涨跌幅=-0.08%; 振幅=0.00%; 成交额=0.20亿
- 均线偏离: MA5=+7.88%; MA20=+7.84%; MA60=-0.39%
- C线原始预测: action=panic_rebound_probe; direction=neutral; confidence=40%
- 触发依据: 价格重新站回短中期均线，且有一定量能或波动配合，说明‘恐慌修复’不是纯噪声。
- LLM客观评价: D线触发: 价格重新站回短中期均线，且有一定量能或波动配合，说明‘恐慌修复’不是纯噪声。 观察目的: 观察其在恐慌市中是否出现对20日线与5日线的修复性回升，以验证 C 线的 panic_rebound_probe 假设是否成立。 主要风险: 低分回避票在盘中只是弱反抽而非真正修复，若重新跌回20日线下方并伴随波动放大，则反弹观察假设失效。 对C线反馈: validate panic_rebound_probe -> keep_observing 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=validate panic_rebound_probe -> keep_observing; baseline=20260706; task_id=20260706_20260707_600580_d_observe_llm_v2; MA20触发位置=+7.84%

## 3. 600900 长江电力

- 触发: noise_filter / severity=low / fire_count=1
- 时间: forecast_ts=2026-07-07T09:25:18; trade_time=09:25:01; trade_date=2026-07-07
- 实时行情: 现价=27.19; 涨跌幅=0.00%; 振幅=0.00%; 成交额=0.38亿
- 均线偏离: MA5=+1.23%; MA20=+0.36%; MA60=+0.64%
- C线原始预测: action=panic_rebound_probe; direction=neutral; confidence=40%
- 触发依据: 用于过滤仅在均线附近小幅震荡、量能也偏弱的普通噪声，避免把无方向波动误判为有效信号。
- LLM客观评价: D线触发: 用于过滤仅在均线附近小幅震荡、量能也偏弱的普通噪声，避免把无方向波动误判为有效信号。 观察目的: 明天盘中主要验证：长江电力在“panic_rebound_probe”框架下，是否能从EOD轻微站上均线的状态继续完成修复，还是在恐慌市中快速回落并证伪反弹假设。 主要风险: 最核心风险是盘中修复不成立，价格重新跌回20日线下方并伴随弱势放量，说明C线把它定义为恐慌修复观察的前提不足。 对C线反馈: hold_observation 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=hold_observation; baseline=20260706; task_id=20260706_20260707_600900_d_observe_llm_v2; MA20触发位置=+0.36%

## 4. 601179 中国西电

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-07T09:25:21; trade_time=09:25:01; trade_date=2026-07-07
- 实时行情: 现价=14.13; 涨跌幅=+0.78%; 振幅=0.00%; 成交额=0.03亿
- 均线偏离: MA5=-1.59%; MA20=-5.18%; MA60=-13.33%
- C线原始预测: action=panic_rebound_probe; direction=neutral; confidence=40%
- 触发依据: 说明盘中出现了反弹，但仍未修复到短均线之上，更符合弱修复/噪音反抽的特征。
- LLM客观评价: D线触发: 说明盘中出现了反弹，但仍未修复到短均线之上，更符合弱修复/噪音反抽的特征。 观察目的: 观察这只票在恐慌市中是否出现可机械验证的短线修复，重点看反弹能否重新站回短均线，还是只出现无量弱反抽后继续走弱，以验证 C 线的 panic_rebound_probe 假设。 主要风险: 低位反弹失败并继续压在 MA20 下方，盘中任何上冲若缺少量能配合都更像噪音而非有效修复。 对C线反馈: panic_rebound_probe -> weak_confirm 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=panic_rebound_probe -> weak_confirm; baseline=20260706; task_id=20260706_20260707_601179_d_observe_llm_v2; MA20触发位置=-5.18%

## 5. 601689 拓普集团

- 触发: reclaim_confirm / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-07T09:25:24; trade_time=09:25:03; trade_date=2026-07-07
- 实时行情: 现价=60.76; 涨跌幅=+0.31%; 振幅=0.00%; 成交额=0.18亿
- 均线偏离: MA5=+3.63%; MA20=+1.53%; MA60=-2.83%
- C线原始预测: action=panic_rebound_probe; direction=neutral; confidence=40%
- 触发依据: 若短均线重新被站稳且量能不弱，说明次日盘中修复并非纯噪声，C线的 panic_rebound_probe 得到阶段性验证。
- LLM客观评价: D线触发: 若短均线重新被站稳且量能不弱，说明次日盘中修复并非纯噪声，C线的 panic_rebound_probe 得到阶段性验证。 观察目的: 验证在 panic 市场中，拓普集团次日盘中是否只是对低分票的弱修复试探，还是能完成短线均线修复并摆脱回落风险。 主要风险: 市场情绪仍偏恐慌、且该票EOD评分为回避，次日最核心风险是反弹仅为短暂修复，随后重新失守短均线并转入更深的弱势波动。 对C线反馈: confirm -> validate panic_rebound_probe 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=confirm -> validate panic_rebound_probe; baseline=20260706; task_id=20260706_20260707_601689_d_observe_llm_v2; MA20触发位置=+1.53%

## 6. 603728 鸣志电器

- 触发: panic_rebound_probe / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-07T09:30:35; trade_time=09:30:34; trade_date=2026-07-07
- 实时行情: 现价=65.98; 涨跌幅=+1.37%; 振幅=1.54%; 成交额=0.08亿
- 均线偏离: MA5=+2.92%; MA20=+6.61%; MA60=+6.56%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 说明盘中已经出现对短均线的主动修复，C线“恐慌后反弹观察”开始获得验证。
- LLM客观评价: D线触发: 说明盘中已经出现对短均线的主动修复，C线“恐慌后反弹观察”开始获得验证。 观察目的: 验证鸣志电器在大盘恐慌环境下，是否能完成对短均线的盘中修复并把 C 线的“panic_rebound_watch”从观察状态推进为可确认的反弹行为。 主要风险: 恐慌市环境下，前期5日强势更容易演化为弱修复或回落失守；如果不能重新站稳短均线，C线对次日情绪修复的判断就会失真。 对C线反馈: confirm_rebound_watch 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=confirm_rebound_watch; baseline=20260706; task_id=20260706_20260707_603728_d_observe_llm_v2; MA20触发位置=+6.61%

## 7. 600183 生益科技

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-07T09:35:46; trade_time=09:35:37; trade_date=2026-07-07
- 实时行情: 现价=150.78; 涨跌幅=-2.26%; 振幅=3.95%; 成交额=7.07亿
- 均线偏离: MA5=-6.37%; MA20=-8.92%; MA60=+28.36%
- C线原始预测: action=watch_only; direction=neutral; confidence=45%
- 触发依据: 若出现一定振幅但量能跟不上、相对位置仍弱，说明更像技术性反抽而非有效扭转，需要把这类反弹归为弱反弹而非确认修复。
- LLM客观评价: D线触发: 若出现一定振幅但量能跟不上、相对位置仍弱，说明更像技术性反抽而非有效扭转，需要把这类反弹归为弱反弹而非确认修复。 观察目的: 验证生益科技在 panic 市场中是否只是弱修复，还是能盘中重新站回短中期均线并否定继续走弱假设。 主要风险: panic 情绪下反弹失真，价格继续远离均线并放量下破，导致 C 线的 watch_only 假设失效。 对C线反馈: watch -> no_confirm 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> no_confirm; baseline=20260706; task_id=20260706_20260707_600183_d_observe_llm_v2; MA20触发位置=-8.92%

## 8. 603009 北特科技

- 触发: reclaim_confirm / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-07T09:35:49; trade_time=09:35:42; trade_date=2026-07-07
- 实时行情: 现价=53.50; 涨跌幅=+1.13%; 振幅=3.48%; 成交额=0.41亿
- 均线偏离: MA5=+5.17%; MA20=+16.52%; MA60=+9.14%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 盘中维持正向修复且不失守短均线，说明 panic 下的修复假设得到初步确认。
- LLM客观评价: D线触发: 盘中维持正向修复且不失守短均线，说明 panic 下的修复假设得到初步确认。 观察目的: 观察北特科技在次日盘中是否能在恐慌市中完成弱修复并守住短均线，从而验证 C线的“panic_rebound_watch / 上行”假设。 主要风险: 高位高 RSI 背景下，盘中一旦反弹无力并跌破短均线支撑，恐慌环境会把修复预期直接证伪。 对C线反馈: support_rebound -> keep_up_bias 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=support_rebound -> keep_up_bias; baseline=20260706; task_id=20260706_20260707_603009_d_observe_llm_v2; MA20触发位置=+16.52%

## 9. 603667 五洲新春

- 触发: panic_rebound_probe / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-07T09:35:52; trade_time=09:35:43; trade_date=2026-07-07
- 实时行情: 现价=69.75; 涨跌幅=+1.77%; 振幅=4.77%; 成交额=3.49亿
- 均线偏离: MA5=+0.09%; MA20=+4.02%; MA60=-2.71%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 盘中若能在上涨状态下站回ma20附近并不再明显弱于ma5，说明恐慌后的修复正在兑现。
- LLM客观评价: D线触发: 盘中若能在上涨状态下站回ma20附近并不再明显弱于ma5，说明恐慌后的修复正在兑现。 观察目的: 观察五洲新春在次日盘中是否完成恐慌后的修复、重新站回短均线并获得基本量能配合，用来验证C线“panic_rebound_watch”的T+1情绪修复假设。 主要风险: 在市场panic背景下出现的只是弱反抽，无法重新收复ma5/ma20，导致C线关于次日情绪修复的判断失效。 对C线反馈: confirm_rebound_watch 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=confirm_rebound_watch; baseline=20260706; task_id=20260706_20260707_603667_d_observe_llm_v2; MA20触发位置=+4.02%

## 10. 002463 沪电股份

- 触发: weak_rebound / severity=low / fire_count=1
- 时间: forecast_ts=2026-07-07T09:41:05; trade_time=09:40:57; trade_date=2026-07-07
- 实时行情: 现价=130.33; 涨跌幅=+1.16%; 振幅=2.93%; 成交额=9.49亿
- 均线偏离: MA5=-5.90%; MA20=-6.66%; MA60=+9.53%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 说明盘中有弱修复，但强度不足，仍需继续观察是否能延续而非一波流。
- LLM客观评价: D线触发: 说明盘中有弱修复，但强度不足，仍需继续观察是否能延续而非一波流。 观察目的: 验证沪电股份在大盘panic环境下，次日盘中是否出现低位情绪修复并对EOD回撤形成止跌回拉，而不是继续沿短中期均线下方扩张跌势。 主要风险: AI算力板块处于减档环境，个股已明显低于ma5和ma20；若盘中修复无量或直接继续破位，则C线的恐慌修复假设失效。 对C线反馈: panic_rebound_watch -> weak_rebound_observed 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=panic_rebound_watch -> weak_rebound_observed; baseline=20260706; task_id=20260706_20260707_002463_d_observe_llm_v2; MA20触发位置=-6.66%

## 11. 600522 中天科技

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-07T09:41:08; trade_time=09:40:57; trade_date=2026-07-07
- 实时行情: 现价=48.31; 涨跌幅=+0.58%; 振幅=2.50%; 成交额=13.57亿
- 均线偏离: MA5=-9.17%; MA20=-12.68%; MA60=+10.73%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 表示有反弹但力度不足，仍停留在弱修复区间，更接近“盘中噪音”而不是结构性修复。
- LLM客观评价: D线触发: 表示有反弹但力度不足，仍停留在弱修复区间，更接近“盘中噪音”而不是结构性修复。 观察目的: 在 panic 市场下验证该票次日是否出现超跌修复，重点看能否从 MA20 下方的弱势区间收窄跌幅并避免跌破 MA60。 主要风险: 当前仍处于明显下行后的观察位，最大风险是盘中反弹仅属弱修复，若不能改善 price_vs_ma20_pct 且进一步失守 price_vs_ma60_pct，则 C 线的向上修复假设失效。 对C线反馈: watch -> keep_low_confidence_probe 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> keep_low_confidence_probe; baseline=20260706; task_id=20260706_20260707_600522_d_observe_llm_v2; MA20触发位置=-12.68%

## 12. 002371 北方华创

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-07T10:01:42; trade_time=10:01:33; trade_date=2026-07-07
- 实时行情: 现价=804.00; 涨跌幅=+0.05%; 振幅=3.25%; 成交额=22.77亿
- 均线偏离: MA5=-6.10%; MA20=+7.76%; MA60=+29.60%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 有反弹但仍压在短期均线下方，且量能与强度不足，更符合弱反抽而非有效修复。
- LLM客观评价: D线触发: 有反弹但仍压在短期均线下方，且量能与强度不足，更符合弱反抽而非有效修复。 观察目的: 明天盘中重点验证：在指数恐慌环境下，北方华创是否能完成一次仅限观察级别的情绪修复，即先收复短期均线再保持在20日线上方，而不是只是弱反抽后重新转弱。 主要风险: 恐慌市背景下，反弹无法穿越短期均线，最终回落并再次测试20日线，导致C线的盘中修复假设失效。 对C线反馈: watch -> remain_unconfirmed 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> remain_unconfirmed; baseline=20260706; task_id=20260706_20260707_002371_d_observe_llm_v2; MA20触发位置=+7.76%

## 13. 600875 东方电气

- 触发: risk_off_confirm / severity=high / fire_count=1
- 时间: forecast_ts=2026-07-07T10:01:45; trade_time=10:01:37; trade_date=2026-07-07
- 实时行情: 现价=29.42; 涨跌幅=-1.18%; 振幅=2.62%; 成交额=5.82亿
- 均线偏离: MA5=+1.98%; MA20=-2.81%; MA60=-17.68%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 说明不仅没有修复，反而继续向下扩展波动，C线的恐慌修复前提被明显削弱。
- LLM客观评价: D线触发: 说明不仅没有修复，反而继续向下扩展波动，C线的恐慌修复前提被明显削弱。 观察目的: 验证东方电气在大盘恐慌环境下，次日盘中能否完成对MA20附近的情绪修复，并判断这次上涨假设是弱反弹还是有效回收。 主要风险: 恐慌市中的反弹只是弱修复，无法收复MA20并维持，最终演变为继续走弱的假回升。 对C线反馈: watch -> downgrade_confidence 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> downgrade_confidence; baseline=20260706; task_id=20260706_20260707_600875_d_observe_llm_v2; MA20触发位置=-2.81%

## 14. 002384 东山精密

- 触发: panic_rebound_probe / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-07T13:35:03; trade_time=13:34:54; trade_date=2026-07-07
- 实时行情: 现价=235.71; 涨跌幅=+5.01%; 振幅=8.17%; 成交额=124.01亿
- 均线偏离: MA5=-0.76%; MA20=-2.85%; MA60=+12.33%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 说明盘中出现了从弱势区向修复区移动的反弹尝试，可用于验证 C线的 panic_rebound_watch 假设。
- LLM客观评价: D线触发: 说明盘中出现了从弱势区向修复区移动的反弹尝试，可用于验证 C线的 panic_rebound_watch 假设。 观察目的: 验证在大盘恐慌环境下，东山精密次日是否出现从MA20下方的情绪修复反弹，还是继续走弱演化为风险释放。 主要风险: 恐慌市中的反弹如果无法收复短期均线并得到量能配合，就更像弱修复而不是有效转强，C线的上行假设可能失效。 对C线反馈: watch -> confirm_probe 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> confirm_probe; baseline=20260706; task_id=20260706_20260707_002384_d_observe_llm_v2; MA20触发位置=-2.85%
