# D线盘中触发汇总

- updated_at: 2026-07-17T13:23:46
- trade_date: 2026-07-17
- triggers: 22
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 002475 立讯精密

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-17T09:28:40; trade_time=09:25:00; trade_date=2026-07-17
- 实时行情: 现价=61.00; 涨跌幅=-0.94%; 振幅=0.00%; 成交额=0.44亿
- 均线偏离: MA5=+0.05%; MA20=-6.90%; MA60=-11.32%
- C线原始预测: action=candidate_buy; direction=up; confidence=75%
- 触发依据: 说明盘中出现了反弹，但仍未拿回20日线且动能偏弱，更像技术性修复而不是趋势翻转。
- LLM客观评价: D线触发: 说明盘中出现了反弹，但仍未拿回20日线且动能偏弱，更像技术性修复而不是趋势翻转。 观察目的: 明天盘中重点验证：立讯精密在当前低于20/60日均线、但EOD被判为候选买入的情况下，是否能出现真正的均线回收修复，还是仅有弱反弹后继续走弱。 主要风险: C线的候选买入假设可能被中期均线压制与AI链上限减档共同否决，盘中若无法收复20日线，容易演化为弱反弹后的再度回撤。 对C线反馈: watch -> weak_rebound_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> weak_rebound_review; baseline=20260716; task_id=20260716_20260717_002475_d_observe_llm_v2; MA20触发位置=-6.90%

## 2. 002475 立讯精密

- 触发: noise_filter / severity=low / fire_count=3
- 时间: forecast_ts=2026-07-17T09:28:42; trade_time=09:25:00; trade_date=2026-07-17
- 实时行情: 现价=61.00; 涨跌幅=-0.94%; 振幅=0.00%; 成交额=0.44亿
- 均线偏离: MA5=+0.05%; MA20=-6.90%; MA60=-11.32%
- C线原始预测: action=candidate_buy; direction=up; confidence=75%
- 触发依据: 用于过滤低波动、低量的盘中噪音，避免把无效波动误判为对C线的实质验证。
- LLM客观评价: D线触发: 用于过滤低波动、低量的盘中噪音，避免把无效波动误判为对C线的实质验证。 观察目的: 明天盘中重点验证：立讯精密在当前低于20/60日均线、但EOD被判为候选买入的情况下，是否能出现真正的均线回收修复，还是仅有弱反弹后继续走弱。 主要风险: C线的候选买入假设可能被中期均线压制与AI链上限减档共同否决，盘中若无法收复20日线，容易演化为弱反弹后的再度回撤。 对C线反馈: watch -> no_material_change 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> no_material_change; baseline=20260716; task_id=20260716_20260717_002475_d_observe_llm_v2; MA20触发位置=-6.90%

## 3. 600183 生益科技

- 触发: breakdown_confirm / severity=high / fire_count=3
- 时间: forecast_ts=2026-07-17T09:28:44; trade_time=09:28:21; trade_date=2026-07-17
- 实时行情: 现价=144.84; 涨跌幅=-1.46%; 振幅=0.00%; 成交额=0.82亿
- 均线偏离: MA5=-0.95%; MA20=-10.60%; MA60=+12.58%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 若盘中进一步远离MA20并伴随弱动量确认，则说明公司事件并未阻止趋势继续走弱，C线向上判断需要降权。
- LLM客观评价: D线触发: 若盘中进一步远离MA20并伴随弱动量确认，则说明公司事件并未阻止趋势继续走弱，C线向上判断需要降权。 观察目的: 验证“预增+右侧评分”是否能在次日盘中推动股价完成短均线修复，并确认上行假设是否只是弱反弹。 主要风险: 当前价格仍明显低于MA20且MACD为负，最大风险是次日仅出现无量弱反弹，无法把C线的向上判断转化为可验证的修复行情。 对C线反馈: watch -> avoid_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> avoid_review; baseline=20260716; task_id=20260716_20260717_600183_d_observe_llm_v2; MA20触发位置=-10.60%

## 4. 600900 XD长江电

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-17T09:28:46; trade_time=09:28:24; trade_date=2026-07-17
- 实时行情: 现价=27.61; 涨跌幅=+0.58%; 振幅=0.00%; 成交额=0.39亿
- 均线偏离: MA5=-2.73%; MA20=+1.13%; MA60=+1.36%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 表示价格仍受5日线压制、量能未明显增强，但整体尚未跌破20日线，更像高位弱修复/整理。
- LLM客观评价: D线触发: 表示价格仍受5日线压制、量能未明显增强，但整体尚未跌破20日线，更像高位弱修复/整理。 观察目的: 验证C线“avoid/neutral”假设：次日盘中若仅表现为高位弱修复或回踩整理，而不是放量重回5日线后的持续转强，则支持回避判断。 主要风险: 当前位置已在20日线与52周相对高位附近，若次日放量重新收复5日线并延续，说明前一日的回避依据可能被盘中强度推翻。 对C线反馈: watch -> avoid_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> avoid_review; baseline=20260716; task_id=20260716_20260717_600900_d_observe_llm_v2; MA20触发位置=+1.13%

## 5. 601138 工业富联

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-17T09:28:48; trade_time=09:28:26; trade_date=2026-07-17
- 实时行情: 现价=62.02; 涨跌幅=-1.59%; 振幅=0.00%; 成交额=0.64亿
- 均线偏离: MA5=-3.57%; MA20=-10.12%; MA60=-10.43%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 说明仅有弱反弹或缩量修复，尚不足以支持上行延续。
- LLM客观评价: D线触发: 说明仅有弱反弹或缩量修复，尚不足以支持上行延续。 观察目的: 验证601138次日盘中能否从EOD的短中期均线下方弱势状态中完成收复，判断C线“watch/up”是低位修复还是继续承压反弹。 主要风险: 股价仍显著低于MA5/MA10/MA20/MA60，叠加近5日与10日趋势偏弱，盘中若不能收复短均线，上行假设容易退化为弱反抽；AI板块上限环境也会限制持续性。 对C线反馈: watch -> weak_rebound 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> weak_rebound; baseline=20260716; task_id=20260716_20260717_601138_d_observe_llm_v2; MA20触发位置=-10.12%

## 6. 601689 拓普集团

- 触发: weak_rebound / severity=low / fire_count=3
- 时间: forecast_ts=2026-07-17T09:28:50; trade_time=09:28:13; trade_date=2026-07-17
- 实时行情: 现价=54.90; 涨跌幅=+0.79%; 振幅=0.00%; 成交额=0.05亿
- 均线偏离: MA5=-0.05%; MA20=-3.60%; MA60=-11.42%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若只是小幅翻红但仍明显弱于MA20且动量未转强，更像弱反弹而非趋势修复。
- LLM客观评价: D线触发: 若只是小幅翻红但仍明显弱于MA20且动量未转强，更像弱反弹而非趋势修复。 观察目的: 明天盘中观察拓普集团是否继续运行在MA20下方、弱反弹是否失败，以验证C线“非panic、默认回避”的判断。 主要风险: 盘中若无法有效收复短中期均线并出现继续走弱，说明当前弱势结构仍在延续，C线的回避判断会被强化。 对C线反馈: watch_only -> no_upgrade 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch_only -> no_upgrade; baseline=20260716; task_id=20260716_20260717_601689_d_observe_llm_v2; MA20触发位置=-3.60%

## 7. 603667 五洲新春

- 触发: weak_rebound / severity=medium / fire_count=3
- 时间: forecast_ts=2026-07-17T09:28:52; trade_time=09:28:15; trade_date=2026-07-17
- 实时行情: 现价=58.07; 涨跌幅=-0.19%; 振幅=0.00%; 成交额=0.03亿
- 均线偏离: MA5=-2.27%; MA20=-9.03%; MA60=-17.45%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若只是小幅反弹但仍明显压在短均线下方，且量能不足，属于典型弱反弹，更多是对回避判断的旁证而非反证。
- LLM客观评价: D线触发: 若只是小幅反弹但仍明显压在短均线下方，且量能不足，属于典型弱反弹，更多是对回避判断的旁证而非反证。 观察目的: 观察明日盘中是否出现对MA5/MA20的有效收复，还是继续在中期均线下方弱势运行，从而验证C线“avoid/neutral”的回避判断。 主要风险: 非panic背景下的弱反弹无量失败：若反弹无法站回短均线，当前偏弱结构大概率延续，C线回避判断应被保留。 对C线反馈: avoid -> maintain_watch 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=avoid -> maintain_watch; baseline=20260716; task_id=20260716_20260717_603667_d_observe_llm_v2; MA20触发位置=-9.03%

## 8. 002384 东山精密

- 触发: breakdown_confirm / severity=high / fire_count=3
- 时间: forecast_ts=2026-07-17T09:34:03; trade_time=09:33:54; trade_date=2026-07-17
- 实时行情: 现价=242.07; 涨跌幅=-9.94%; 振幅=6.73%; 成交额=47.69亿
- 均线偏离: MA5=-4.75%; MA20=-3.85%; MA60=+7.98%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 说明高位支撑失效，盘中走弱已经把上行假设证伪。
- LLM客观评价: D线触发: 说明高位支撑失效，盘中走弱已经把上行假设证伪。 观察目的: 验证东山精密在高位区间是否能延续强势并维持在均线之上，确认C线“watch/up”是否被盘中价格与量能支持。 主要风险: 52周与20日位置都偏高，且AI算力上限为减档，盘中最容易出现冲高回落或跌回均线下方，从而证伪上行延续假设。 对C线反馈: watch -> avoid_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> avoid_review; baseline=20260716; task_id=20260716_20260717_002384_d_observe_llm_v2; MA20触发位置=-3.85%

## 9. 002463 沪电股份

- 触发: breakdown_confirm / severity=high / fire_count=2
- 时间: forecast_ts=2026-07-17T09:34:05; trade_time=09:33:54; trade_date=2026-07-17
- 实时行情: 现价=125.97; 涨跌幅=-7.86%; 振幅=8.28%; 成交额=13.14亿
- 均线偏离: MA5=-5.31%; MA20=-9.09%; MA60=+1.17%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若再次明显跌离20日线且伴随放量或波动扩张，说明盘中偏弱并支持继续回避。
- LLM客观评价: D线触发: 若再次明显跌离20日线且伴随放量或波动扩张，说明盘中偏弱并支持继续回避。 观察目的: 验证次日盘中是继续高位弱修复/横盘，还是能重新站回20日线并放量，从而推翻C线的avoid判断。 主要风险: 高位震荡中继续失守20日线，利好预期未转化为盘中有效修复，回避判断继续成立。 对C线反馈: confirm_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=confirm_avoid; baseline=20260716; task_id=20260716_20260717_002463_d_observe_llm_v2; MA20触发位置=-9.09%

## 10. 603009 北特科技

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-17T09:34:07; trade_time=09:34:02; trade_date=2026-07-17
- 实时行情: 现价=45.26; 涨跌幅=+1.46%; 振幅=2.11%; 成交额=0.32亿
- 均线偏离: MA5=-1.50%; MA20=-3.01%; MA60=-6.91%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 若价格只是靠近短均线但量能和动量都不强，更像弱反弹或技术性修复，不能直接支持C线的强度判断。
- LLM客观评价: D线触发: 若价格只是靠近短均线但量能和动量都不强，更像弱反弹或技术性修复，不能直接支持C线的强度判断。 观察目的: 观察北特科技次日盘中是否从均线下方的弱修复转为对MA5/MA20的重新站上确认，用以验证C线的“watch/up”是否成立，或被继续走弱证伪。 主要风险: 当前价格同时低于MA5和MA20，且近5日偏弱、量能不足；若盘中修复没有量能与动量配合，C线的上行观察很容易退化为弱反弹噪声。 对C线反馈: watch -> weak_confirm 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> weak_confirm; baseline=20260716; task_id=20260716_20260717_603009_d_observe_llm_v2; MA20触发位置=-3.01%

## 11. 600522 中天科技

- 触发: breakdown_confirm / severity=high / fire_count=2
- 时间: forecast_ts=2026-07-17T09:39:16; trade_time=09:39:09; trade_date=2026-07-17
- 实时行情: 现价=35.92; 涨跌幅=-3.93%; 振幅=6.39%; 成交额=15.46亿
- 均线偏离: MA5=-13.72%; MA20=-31.02%; MA60=-21.13%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 若继续扩大对 MA20 的远离并伴随低 RSI/放大波动，说明弱势惯性未止，盘中修复假设失败。
- LLM客观评价: D线触发: 若继续扩大对 MA20 的远离并伴随低 RSI/放大波动，说明弱势惯性未止，盘中修复假设失败。 观察目的: 验证中天科技次日盘中在超跌背景下是否出现可被机械确认的修复，还是继续沿着弱势结构破位下行，用来检验 C 线“watch/up”假设是否成立。 主要风险: 当前价格显著低于短中期均线、RSI 极低且近 5/20 日跌幅很深，核心风险不是没有波动，而是只有弱反弹却无法修复短线趋势，最终继续破位。 对C线反馈: watch -> avoid_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> avoid_review; baseline=20260716; task_id=20260716_20260717_600522_d_observe_llm_v2; MA20触发位置=-31.02%

## 12. 002050 三花智控

- 触发: risk_off_confirm / severity=high / fire_count=2
- 时间: forecast_ts=2026-07-17T09:49:37; trade_time=09:49:27; trade_date=2026-07-17
- 实时行情: 现价=40.65; 涨跌幅=-2.82%; 振幅=3.92%; 成交额=8.08亿
- 均线偏离: MA5=-3.25%; MA20=-6.91%; MA60=-12.93%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 表示价格继续处于MA20下方且短中期均线修复失败，回避逻辑被盘中行为支持。
- LLM客观评价: D线触发: 表示价格继续处于MA20下方且短中期均线修复失败，回避逻辑被盘中行为支持。 观察目的: 明天盘中重点验证：该票是否继续维持弱势回避结构，还是出现对MA20的快速收复从而推翻C线的“avoid/neutral”判断。 主要风险: 核心风险是盘中重新站回MA20并伴随有效放量，说明当前回避逻辑可能只是短线滞后而非趋势失效。 对C线反馈: confirm_avoid -> maintain_neutral 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=confirm_avoid -> maintain_neutral; baseline=20260716; task_id=20260716_20260717_002050_d_observe_llm_v2; MA20触发位置=-6.91%

## 13. 601689 拓普集团

- 触发: breakdown_confirm / severity=high / fire_count=4
- 时间: forecast_ts=2026-07-17T09:49:39; trade_time=09:49:33; trade_date=2026-07-17
- 实时行情: 现价=52.27; 涨跌幅=-4.04%; 振幅=5.95%; 成交额=5.62亿
- 均线偏离: MA5=-4.84%; MA20=-8.22%; MA60=-15.66%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若在更深的均线乖离下继续走弱且伴随放量或波动放大，说明弱势延续而非正常整理。
- LLM客观评价: D线触发: 若在更深的均线乖离下继续走弱且伴随放量或波动放大，说明弱势延续而非正常整理。 观察目的: 明天盘中观察拓普集团是否继续运行在MA20下方、弱反弹是否失败，以验证C线“非panic、默认回避”的判断。 主要风险: 盘中若无法有效收复短中期均线并出现继续走弱，说明当前弱势结构仍在延续，C线的回避判断会被强化。 对C线反馈: maintain_avoid -> stronger_negative_validation 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=maintain_avoid -> stronger_negative_validation; baseline=20260716; task_id=20260716_20260717_601689_d_observe_llm_v2; MA20触发位置=-8.22%

## 14. 603667 五洲新春

- 触发: breakdown_confirm / severity=high / fire_count=4
- 时间: forecast_ts=2026-07-17T09:49:41; trade_time=09:49:32; trade_date=2026-07-17
- 实时行情: 现价=57.02; 涨跌幅=-1.99%; 振幅=4.68%; 成交额=2.32亿
- 均线偏离: MA5=-4.04%; MA20=-10.68%; MA60=-18.94%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若继续向下远离MA20/MA60，说明弱势结构未被盘中修复，C线的非正收益预期得到强化。
- LLM客观评价: D线触发: 若继续向下远离MA20/MA60，说明弱势结构未被盘中修复，C线的非正收益预期得到强化。 观察目的: 观察明日盘中是否出现对MA5/MA20的有效收复，还是继续在中期均线下方弱势运行，从而验证C线“avoid/neutral”的回避判断。 主要风险: 非panic背景下的弱反弹无量失败：若反弹无法站回短均线，当前偏弱结构大概率延续，C线回避判断应被保留。 对C线反馈: avoid -> confirm 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=avoid -> confirm; baseline=20260716; task_id=20260716_20260717_603667_d_observe_llm_v2; MA20触发位置=-10.68%

## 15. 002371 北方华创

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-17T09:54:51; trade_time=09:54:42; trade_date=2026-07-17
- 实时行情: 现价=703.90; 涨跌幅=+0.16%; 振幅=4.96%; 成交额=29.42亿
- 均线偏离: MA5=-7.01%; MA20=-12.06%; MA60=+6.36%
- C线原始预测: action=candidate_buy; direction=up; confidence=75%
- 触发依据: 出现上涨但仍未收复短中期均线、且量能不强时，更像弱反弹或盘中噪声，不足以支持C线的积极结论。
- LLM客观评价: D线触发: 出现上涨但仍未收复短中期均线、且量能不强时，更像弱反弹或盘中噪声，不足以支持C线的积极结论。 观察目的: 验证次日盘中是否出现对MA5/MA20的有效修复，从而确认C线“高分候选买入”的短线反弹假设，或继续被近5日急跌与均线压制否定。 主要风险: 短线仍处于MA5和MA20下方，且近5日跌幅接近20%；如果盘中反弹没有量能配合，大概率只是弱修复而非趋势反转，C线候选买入假设容易失效。 对C线反馈: candidate_buy -> monitor_only 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=candidate_buy -> monitor_only; baseline=20260716; task_id=20260716_20260717_002371_d_observe_llm_v2; MA20触发位置=-12.06%

## 16. 600276 恒瑞医药

- 触发: failed_breakout / severity=high / fire_count=2
- 时间: forecast_ts=2026-07-17T09:54:53; trade_time=09:54:45; trade_date=2026-07-17
- 实时行情: 现价=54.34; 涨跌幅=-2.95%; 振幅=3.66%; 成交额=19.16亿
- 均线偏离: MA5=-2.90%; MA20=+2.15%; MA60=+4.62%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 说明高位上攻失败并开始跌破短均线保护，原本的向上预期被削弱。
- LLM客观评价: D线触发: 说明高位上攻失败并开始跌破短均线保护，原本的向上预期被削弱。 观察目的: 观察恒瑞医药次日是否能在高位延续上行并站稳短中期均线，还是出现高位转弱、跌回短均线甚至回撤到MA20附近，用来验证C线“watch、方向向上”的假设。 主要风险: 当前处于高位偏热区间且RSI接近超买，若次日没有量能配合，最容易出现冲高回落、跌破MA5/MA10并向MA20回撤。 对C线反馈: watch -> weaken_up 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> weaken_up; baseline=20260716; task_id=20260716_20260717_600276_d_observe_llm_v2; MA20触发位置=+2.15%

## 17. 601179 中国西电

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-17T09:54:55; trade_time=09:54:45; trade_date=2026-07-17
- 实时行情: 现价=12.00; 涨跌幅=+2.56%; 振幅=6.50%; 成交额=6.24亿
- 均线偏离: MA5=-3.29%; MA20=-15.63%; MA60=-24.07%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若出现超卖反抽，但仍卡在短均线下方且量能不配合，这更像弱修复而不是趋势反转。
- LLM客观评价: D线触发: 若出现超卖反抽，但仍卡在短均线下方且量能不配合，这更像弱修复而不是趋势反转。 观察目的: 明天盘中重点验证中国西电是否只是超卖后的弱反抽，还是继续破位下行，从而检验C线“回避”判断是否成立。 主要风险: 低位超卖引发的技术性反弹若能重新收复短均线并放量，C线的回避假设会被削弱；反之若继续失守中短均线，则弱势延续得到确认。 对C线反馈: keep_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=keep_avoid; baseline=20260716; task_id=20260716_20260717_601179_d_observe_llm_v2; MA20触发位置=-15.63%

## 18. 002371 北方华创

- 触发: breakdown_confirm / severity=high / fire_count=3
- 时间: forecast_ts=2026-07-17T10:25:54; trade_time=10:25:45; trade_date=2026-07-17
- 实时行情: 现价=685.00; 涨跌幅=-2.53%; 振幅=5.38%; 成交额=42.44亿
- 均线偏离: MA5=-9.51%; MA20=-14.42%; MA60=+3.50%
- C线原始预测: action=candidate_buy; direction=up; confidence=75%
- 触发依据: 若盘中仍深度压在MA20下方且近5日跌势延续，说明弱势结构未被修复，C线看多假设被继续证伪。
- LLM客观评价: D线触发: 若盘中仍深度压在MA20下方且近5日跌势延续，说明弱势结构未被修复，C线看多假设被继续证伪。 观察目的: 验证次日盘中是否出现对MA5/MA20的有效修复，从而确认C线“高分候选买入”的短线反弹假设，或继续被近5日急跌与均线压制否定。 主要风险: 短线仍处于MA5和MA20下方，且近5日跌幅接近20%；如果盘中反弹没有量能配合，大概率只是弱修复而非趋势反转，C线候选买入假设容易失效。 对C线反馈: candidate_buy -> avoid_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=candidate_buy -> avoid_review; baseline=20260716; task_id=20260716_20260717_002371_d_observe_llm_v2; MA20触发位置=-14.42%

## 19. 002475 立讯精密

- 触发: breakdown_confirm / severity=high / fire_count=4
- 时间: forecast_ts=2026-07-17T10:51:48; trade_time=10:51:39; trade_date=2026-07-17
- 实时行情: 现价=58.34; 涨跌幅=-5.26%; 振幅=5.68%; 成交额=39.15亿
- 均线偏离: MA5=-4.31%; MA20=-10.96%; MA60=-15.19%
- C线原始预测: action=candidate_buy; direction=up; confidence=75%
- 触发依据: 说明不仅继续位于关键均线下方，而且弱势扩散到更深层均线，配合放量或波动放大，属于对候选买入假设的明显证伪。
- LLM客观评价: D线触发: 说明不仅继续位于关键均线下方，而且弱势扩散到更深层均线，配合放量或波动放大，属于对候选买入假设的明显证伪。 观察目的: 明天盘中重点验证：立讯精密在当前低于20/60日均线、但EOD被判为候选买入的情况下，是否能出现真正的均线回收修复，还是仅有弱反弹后继续走弱。 主要风险: C线的候选买入假设可能被中期均线压制与AI链上限减档共同否决，盘中若无法收复20日线，容易演化为弱反弹后的再度回撤。 对C线反馈: watch -> avoid_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> avoid_review; baseline=20260716; task_id=20260716_20260717_002475_d_observe_llm_v2; MA20触发位置=-10.96%

## 20. 601138 工业富联

- 触发: breakdown_confirm / severity=high / fire_count=2
- 时间: forecast_ts=2026-07-17T10:51:50; trade_time=10:51:43; trade_date=2026-07-17
- 实时行情: 现价=59.34; 涨跌幅=-5.84%; 振幅=5.44%; 成交额=44.14亿
- 均线偏离: MA5=-7.74%; MA20=-14.00%; MA60=-14.30%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 说明弱势进一步恶化，盘中验证结果偏向继续下行而非修复。
- LLM客观评价: D线触发: 说明弱势进一步恶化，盘中验证结果偏向继续下行而非修复。 观察目的: 验证601138次日盘中能否从EOD的短中期均线下方弱势状态中完成收复，判断C线“watch/up”是低位修复还是继续承压反弹。 主要风险: 股价仍显著低于MA5/MA10/MA20/MA60，叠加近5日与10日趋势偏弱，盘中若不能收复短均线，上行假设容易退化为弱反抽；AI板块上限环境也会限制持续性。 对C线反馈: watch -> avoid_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> avoid_review; baseline=20260716; task_id=20260716_20260717_601138_d_observe_llm_v2; MA20触发位置=-14.00%

## 21. 600580 卧龙电驱

- 触发: breakdown_confirm / severity=high / fire_count=2
- 时间: forecast_ts=2026-07-17T13:03:06; trade_time=13:02:56; trade_date=2026-07-17
- 实时行情: 现价=30.61; 涨跌幅=-1.58%; 振幅=3.31%; 成交额=6.27亿
- 均线偏离: MA5=-3.77%; MA20=-9.41%; MA60=-17.96%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 若相对20日均线的负偏离继续扩大，并伴随波动或放量，说明弱势延续，C线的上行观察假设被明显削弱。
- LLM客观评价: D线触发: 若相对20日均线的负偏离继续扩大，并伴随波动或放量，说明弱势延续，C线的上行观察假设被明显削弱。 观察目的: 验证次日盘中是否出现对5日/20日均线的修复性反弹，还是延续弱势并进一步远离中期均线，从而检验C线“watch/up”是否成立。 主要风险: 当前价格已明显低于5日、20日和60日均线，且近阶段回撤与主力净流入偏弱；若盘中不能出现有效修复，C线的看多观察假设容易被延续下跌证伪。 对C线反馈: watch -> invalidate_up_bias 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。 ⚠️[铁律校验] 检测到疑似越界(盘中新评分/买卖价/资金臆测), 以EOD报告为准, 盘中未定论
- C线反哺线索: expected_feedback_to_c=watch -> invalidate_up_bias; baseline=20260716; task_id=20260716_20260717_600580_d_observe_llm_v2; MA20触发位置=-9.41%

## 22. 002050 三花智控

- 触发: breakdown_confirm / severity=high / fire_count=3
- 时间: forecast_ts=2026-07-17T13:23:46; trade_time=13:23:36; trade_date=2026-07-17
- 实时行情: 现价=39.72; 涨跌幅=-5.04%; 振幅=5.47%; 成交额=21.95亿
- 均线偏离: MA5=-5.46%; MA20=-9.04%; MA60=-14.92%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 表示在弱区间内继续走低且波动/成交同步放大，说明弱势不是静态横盘而是向下确认。
- LLM客观评价: D线触发: 表示在弱区间内继续走低且波动/成交同步放大，说明弱势不是静态横盘而是向下确认。 观察目的: 明天盘中重点验证：该票是否继续维持弱势回避结构，还是出现对MA20的快速收复从而推翻C线的“avoid/neutral”判断。 主要风险: 核心风险是盘中重新站回MA20并伴随有效放量，说明当前回避逻辑可能只是短线滞后而非趋势失效。 对C线反馈: confirm_avoid -> strengthen_risk_off 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=confirm_avoid -> strengthen_risk_off; baseline=20260716; task_id=20260716_20260717_002050_d_observe_llm_v2; MA20触发位置=-9.04%
