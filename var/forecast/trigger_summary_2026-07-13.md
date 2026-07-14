# D线盘中触发汇总

- updated_at: 2026-07-13T13:24:21
- trade_date: 2026-07-13
- triggers: 13
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 002050 三花智控

- 触发: breakdown_confirm / severity=high / fire_count=1
- 时间: forecast_ts=2026-07-13T09:25:09; trade_time=09:25:00; trade_date=2026-07-13
- 实时行情: 现价=42.44; 涨跌幅=-1.76%; 振幅=0.00%; 成交额=0.21亿
- 均线偏离: MA5=-3.42%; MA20=-4.28%; MA60=-9.58%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 继续弱于中短期均线并且近端跌幅未修复，说明弱势延续而非趋势反转
- LLM客观评价: D线触发: 继续弱于中短期均线并且近端跌幅未修复，说明弱势延续而非趋势反转 观察目的: 观察次日盘中是否继续受 MA10/MA20 压制并维持低优先级回避，还是出现放量修复从而推翻 C 线的 avoid 假设 主要风险: 盘中缩量反弹后重新站上 MA20/MA10，导致“回避”从弱势延续变成误判 对C线反馈: confirm_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=confirm_avoid; baseline=20260710; task_id=20260710_20260713_002050_d_observe_llm_v2; MA20触发位置=-4.28%

## 2. 002463 沪电股份

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-13T09:25:11; trade_time=09:25:00; trade_date=2026-07-13
- 实时行情: 现价=127.70; 涨跌幅=-1.34%; 振幅=0.00%; 成交额=0.58亿
- 均线偏离: MA5=-2.29%; MA20=-8.18%; MA60=+4.71%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 说明盘中有反弹，但仍未摆脱短中期均线压制，更像弱修复而不是有效转强。
- LLM客观评价: D线触发: 说明盘中有反弹，但仍未摆脱短中期均线压制，更像弱修复而不是有效转强。 观察目的: 验证沪电股份次日是否能把当前的短线回撤修复成有效的均线收复，并确认C线“watch/up”是否只是弱修复还是可以转为更强的盘中趋势行为。 主要风险: 短线价格已跌破ma5和ma20且MACD为负，若次日量能不能同步改善，最容易出现的就是弱反弹后继续回撤，而不是有效修复。 对C线反馈: watch -> keep_observe 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> keep_observe; baseline=20260710; task_id=20260710_20260713_002463_d_observe_llm_v2; MA20触发位置=-8.18%

## 3. 600900 长江电力

- 触发: failed_breakout / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-13T09:25:13; trade_time=09:25:00; trade_date=2026-07-13
- 实时行情: 现价=27.93; 涨跌幅=-0.36%; 振幅=0.00%; 成交额=0.30亿
- 均线偏离: MA5=+1.03%; MA20=+3.03%; MA60=+3.04%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若盘中保持高位但涨不动、分歧加大，说明上攻缺乏持续性，更贴近低优先级观察而非强趋势确认。
- LLM客观评价: D线触发: 若盘中保持高位但涨不动、分歧加大，说明上攻缺乏持续性，更贴近低优先级观察而非强趋势确认。 观察目的: 观察长江电力次日盘中是否继续呈现低波动、无明显放量的高位横盘或转弱，从而验证C线“评分<2、非panic、倾向回避”的判断。 主要风险: 价格仍处在20日线和52周相对高位附近，若盘中并未出现明显走弱，‘回避’判断将缺少证伪；若出现放量突破，则回避假设可能失效。 对C线反馈: avoid_hold -> failed_breakout 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=avoid_hold -> failed_breakout; baseline=20260710; task_id=20260710_20260713_600900_d_observe_llm_v2; MA20触发位置=+3.03%

## 4. 601138 工业富联

- 触发: breakdown_confirm / severity=high / fire_count=1
- 时间: forecast_ts=2026-07-13T09:25:15; trade_time=09:25:01; trade_date=2026-07-13
- 实时行情: 现价=65.30; 涨跌幅=-1.46%; 振幅=0.00%; 成交额=0.66亿
- 均线偏离: MA5=-0.81%; MA20=-7.62%; MA60=-5.28%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 若继续远离20/60日均线且放大波动，说明修复失败，C线看多假设被证伪。
- LLM客观评价: D线触发: 若继续远离20/60日均线且放大波动，说明修复失败，C线看多假设被证伪。 观察目的: 明天盘中重点验证工业富联能否在低于20日均线的背景下完成对5/10日均线的修复，并判断这是否只是弱反弹还是可延续的回升。 主要风险: 最大风险是仍处于20/60日均线下方且近10日主力净流出为负，盘中若修复无量或再次回落，C线的看多观察假设会失效。 对C线反馈: watch -> invalidate_bull_case 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。 ⚠️[铁律校验] 检测到疑似越界(盘中新评分/买卖价/资金臆测), 以EOD报告为准, 盘中未定论
- C线反哺线索: expected_feedback_to_c=watch -> invalidate_bull_case; baseline=20260710; task_id=20260710_20260713_601138_d_observe_llm_v2; MA20触发位置=-7.62%

## 5. 601179 中国西电

- 触发: breakdown_confirm / severity=high / fire_count=1
- 时间: forecast_ts=2026-07-13T09:25:17; trade_time=09:25:02; trade_date=2026-07-13
- 实时行情: 现价=13.27; 涨跌幅=-1.12%; 振幅=0.00%; 成交额=0.05亿
- 均线偏离: MA5=-1.85%; MA20=-10.40%; MA60=-17.76%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明盘中仍是深度弱势延续，C线“回避”假设被强化。
- LLM客观评价: D线触发: 说明盘中仍是深度弱势延续，C线“回避”假设被强化。 观察目的: 验证C线“回避/低优先级”假设：明日盘中重点看中国西电是否继续处于均线下方的弱势延续，还是出现对MA5/MA10的有效修复。 主要风险: 超跌后的技术性反抽若能重新收复短均线，可能推翻“默认回避”判断；否则则更像趋势延续而非反转。 对C线反馈: watch -> avoid_confirm 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> avoid_confirm; baseline=20260710; task_id=20260710_20260713_601179_d_observe_llm_v2; MA20触发位置=-10.40%

## 6. 603009 北特科技

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-13T09:25:19; trade_time=09:25:05; trade_date=2026-07-13
- 实时行情: 现价=47.98; 涨跌幅=-0.35%; 振幅=0.00%; 成交额=0.01亿
- 均线偏离: MA5=-1.94%; MA20=+3.86%; MA60=-1.97%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 说明价格仍在MA20之上但回升力度不足、量能偏弱，更像弱反弹或横盘修复，而不是可确认的趋势恢复。
- LLM客观评价: D线触发: 说明价格仍在MA20之上但回升力度不足、量能偏弱，更像弱反弹或横盘修复，而不是可确认的趋势恢复。 观察目的: 观察次日是否能在MA20上方完成对MA5/MA10的修复，并用量能判断这次回升是有效延续还是弱反弹回落。 主要风险: 近期5日回撤较大且当前仍在MA5/MA10下方，若不能放量收复短均线，C线的上行观察很可能只对应弱反弹而非趋势延续。 对C线反馈: watch -> keep_cautious 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> keep_cautious; baseline=20260710; task_id=20260710_20260713_603009_d_observe_llm_v2; MA20触发位置=+3.86%

## 7. 002384 东山精密

- 触发: weak_rebound / severity=low / fire_count=1
- 时间: forecast_ts=2026-07-13T09:30:28; trade_time=09:30:21; trade_date=2026-07-13
- 实时行情: 现价=243.59; 涨跌幅=+0.53%; 振幅=2.89%; 成交额=6.53亿
- 均线偏离: MA5=+1.28%; MA20=-1.97%; MA60=+12.20%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 说明仅出现弱反弹，但仍未完成中期趋势修复，更适合保守观察而非确认上行。
- LLM客观评价: D线触发: 说明仅出现弱反弹，但仍未完成中期趋势修复，更适合保守观察而非确认上行。 观察目的: 验证次日盘中能否把EOD收在MA20下方的偏弱状态修复为站回短中期均线的上行延续，还是继续走弱从而证伪C线的偏多观察假设。 主要风险: 高位位置叠加MACD为负，若盘中无法收复MA10/MA20并出现进一步下探，则当前的偏多观察会被回撤扩展风险证伪。 对C线反馈: watch -> keep_cautious 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> keep_cautious; baseline=20260710; task_id=20260710_20260713_002384_d_observe_llm_v2; MA20触发位置=-1.97%

## 8. 002475 立讯精密

- 触发: breakdown_confirm / severity=high / fire_count=1
- 时间: forecast_ts=2026-07-13T09:35:38; trade_time=09:35:30; trade_date=2026-07-13
- 实时行情: 现价=60.90; 涨跌幅=-2.00%; 振幅=1.75%; 成交额=7.22亿
- 均线偏离: MA5=-3.40%; MA20=-8.71%; MA60=-11.37%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 说明下行延续且相对均线劣势扩大，C线的up假设被破位行为证伪。
- LLM客观评价: D线触发: 说明下行延续且相对均线劣势扩大，C线的up假设被破位行为证伪。 观察目的: 验证 C线“watch/up”是否能在次日盘中完成短均线收复并摆脱近期回撤，还是继续在MA20下方走弱。 主要风险: 中性市下AI链条虽有修复基础，但当前价格仍弱于中短均线；若无法重新站稳，盘面更像弱反弹而不是趋势修复。 对C线反馈: watch -> avoid_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> avoid_review; baseline=20260710; task_id=20260710_20260713_002475_d_observe_llm_v2; MA20触发位置=-8.71%

## 9. 600183 生益科技

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-13T09:45:55; trade_time=09:45:47; trade_date=2026-07-13
- 实时行情: 现价=149.82; 涨跌幅=+0.29%; 振幅=2.51%; 成交额=12.49亿
- 均线偏离: MA5=-1.08%; MA20=-10.18%; MA60=+21.34%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 说明出现弱反弹但尚未真正收复短均线，只能支持继续观察，不能直接强化看多。
- LLM客观评价: D线触发: 说明出现弱反弹但尚未真正收复短均线，只能支持继续观察，不能直接强化看多。 观察目的: 明天盘中验证这只票能否从 MA5/MA10 下方完成弱修复，并确认 C线“watch/up、confidence=0.6”的上行假设是否成立。 主要风险: 当前价格仍显著低于 MA20，若盘中修复只停留在弱反弹或继续走弱，说明短线趋势未被修复，C线看多假设缺少行为验证。 对C线反馈: watch -> cautious_confirm 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> cautious_confirm; baseline=20260710; task_id=20260710_20260713_600183_d_observe_llm_v2; MA20触发位置=-10.18%

## 10. 600875 东方电气

- 触发: breakdown_confirm / severity=high / fire_count=1
- 时间: forecast_ts=2026-07-13T09:51:05; trade_time=09:50:59; trade_date=2026-07-13
- 实时行情: 现价=27.40; 涨跌幅=-2.63%; 振幅=3.77%; 成交额=3.16亿
- 均线偏离: MA5=-3.45%; MA20=-7.91%; MA60=-21.73%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 说明修复失败并继续破位，C线的看涨假设被证伪。
- LLM客观评价: D线触发: 说明修复失败并继续破位，C线的看涨假设被证伪。 观察目的: 观察东方电气次日是否能从MA5/MA20下方修复并以放量确认C线的看涨观察假设。 主要风险: 价格仍明显低于MA20且短线RSI偏弱，若修复没有量能配合，容易演变为弱反弹后再度走弱。 对C线反馈: watch -> invalidate 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> invalidate; baseline=20260710; task_id=20260710_20260713_600875_d_observe_llm_v2; MA20触发位置=-7.91%

## 11. 600276 恒瑞医药

- 触发: breakout_confirm / severity=high / fire_count=1
- 时间: forecast_ts=2026-07-13T10:01:22; trade_time=10:01:15; trade_date=2026-07-13
- 实时行情: 现价=55.59; 涨跌幅=-0.29%; 振幅=2.37%; 成交额=16.87亿
- 均线偏离: MA5=+0.16%; MA20=+7.88%; MA60=+6.90%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 表示价格继续维持在短中期均线上方且有量能或近期涨势配合，属于对C线看多假设的正向验证。
- LLM客观评价: D线触发: 表示价格继续维持在短中期均线上方且有量能或近期涨势配合，属于对C线看多假设的正向验证。 观察目的: 验证恒瑞医药次日是否能延续右侧结构并在高位保持强势，还是因高位偏热而回落，推翻C线的看多观察假设。 主要风险: 20日位置偏高且RSI已接近超买区，最大风险是冲高后无法持续，转为高位回落或假突破。 对C线反馈: watch -> confirm_uptrend 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> confirm_uptrend; baseline=20260710; task_id=20260710_20260713_600276_d_observe_llm_v2; MA20触发位置=+7.88%

## 12. 002371 北方华创

- 触发: breakdown_confirm / severity=high / fire_count=1
- 时间: forecast_ts=2026-07-13T11:08:07; trade_time=11:07:57; trade_date=2026-07-13
- 实时行情: 现价=782.06; 涨跌幅=-2.36%; 振幅=3.96%; 成交额=60.67亿
- 均线偏离: MA5=-4.43%; MA20=-0.69%; MA60=+21.49%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 说明MA20被跌破且近端趋势继续走弱，若同时伴随放量或波动放大，则上行观察假设被明显证伪。
- LLM客观评价: D线触发: 说明MA20被跌破且近端趋势继续走弱，若同时伴随放量或波动放大，则上行观察假设被明显证伪。 观察目的: 验证北方华创次日是否能在MA20上方完成短线修复，并重新收复MA5附近，以确认C线“watch/up”是假设中的弱转强路径。 主要风险: 高位品种在AI算力减档背景下修复失败，若MA20失守或反弹无量，则当前上行观察假设会被证伪。 对C线反馈: watch -> avoid_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> avoid_review; baseline=20260710; task_id=20260710_20260713_002371_d_observe_llm_v2; MA20触发位置=-0.69%

## 13. 603728 鸣志电器

- 触发: breakdown_confirm / severity=high / fire_count=1
- 时间: forecast_ts=2026-07-13T13:24:21; trade_time=13:24:19; trade_date=2026-07-13
- 实时行情: 现价=56.96; 涨跌幅=-5.63%; 振幅=5.15%; 成交额=4.15亿
- 均线偏离: MA5=-7.26%; MA20=-6.80%; MA60=-8.25%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 若价格进一步远离MA20并扩大对MA60的下方偏离，同时出现放量或波动放大，说明弱势延续被确认，盘中观察结论应偏向失效而不是修复。
- LLM客观评价: D线触发: 若价格进一步远离MA20并扩大对MA60的下方偏离，同时出现放量或波动放大，说明弱势延续被确认，盘中观察结论应偏向失效而不是修复。 观察目的: 验证鸣志电器在连续回撤后，次日盘中能否重新收复短中期均线并形成有效修复，从而确认C线“watch/up”判断是否成立。 主要风险: 近期5日回撤较深且收盘仍在MA5、MA20、MA60下方，若次日反弹无量或继续失守中短均线，C线对上行修复的假设会失效。 对C线反馈: watch -> downgrade_risk 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> downgrade_risk; baseline=20260710; task_id=20260710_20260713_603728_d_observe_llm_v2; MA20触发位置=-6.80%
