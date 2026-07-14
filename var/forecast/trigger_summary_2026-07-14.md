# D线盘中触发汇总

- updated_at: 2026-07-14T10:57:41
- trade_date: 2026-07-14
- triggers: 19
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 002463 沪电股份

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-14T09:29:55; trade_time=09:25:00; trade_date=2026-07-14
- 实时行情: 现价=128.55; 涨跌幅=+3.12%; 振幅=0.00%; 成交额=0.69亿
- 均线偏离: MA5=-1.01%; MA20=-7.55%; MA60=+5.02%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 出现了反弹，但仍未摆脱短中期压制，更符合弱修复而非强趋势反转。
- LLM客观评价: D线触发: 出现了反弹，但仍未摆脱短中期压制，更符合弱修复而非强趋势反转。 观察目的: 验证沪电股份在市场 panic 背景下，次日盘中是否能出现可被机械识别的情绪修复反弹，并通过收复短期均线来支撑 C 线的 T+1 看多假设。 主要风险: 反弹只是一段弱修复，无法收复短期均线，最终在 panic 市场里继续走弱并证伪 T+1 修复预期。 对C线反馈: panic_rebound_watch -> partial_validate 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=panic_rebound_watch -> partial_validate; baseline=20260713; task_id=20260713_20260714_002463_d_observe_llm_v2; MA20触发位置=-7.55%

## 2. 002463 沪电股份

- 触发: noise_filter / severity=low / fire_count=3
- 时间: forecast_ts=2026-07-14T09:29:57; trade_time=09:25:00; trade_date=2026-07-14
- 实时行情: 现价=128.55; 涨跌幅=+3.12%; 振幅=0.00%; 成交额=0.69亿
- 均线偏离: MA5=-1.01%; MA20=-7.55%; MA60=+5.02%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 只有低波动、低参与度的盘中噪声，没有足够证据支持对修复结论做强判断。
- LLM客观评价: D线触发: 只有低波动、低参与度的盘中噪声，没有足够证据支持对修复结论做强判断。 观察目的: 验证沪电股份在市场 panic 背景下，次日盘中是否能出现可被机械识别的情绪修复反弹，并通过收复短期均线来支撑 C 线的 T+1 看多假设。 主要风险: 反弹只是一段弱修复，无法收复短期均线，最终在 panic 市场里继续走弱并证伪 T+1 修复预期。 对C线反馈: watch -> no_clear_signal 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> no_clear_signal; baseline=20260713; task_id=20260713_20260714_002463_d_observe_llm_v2; MA20触发位置=-7.55%

## 3. 002475 立讯精密

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-14T09:29:59; trade_time=09:25:00; trade_date=2026-07-14
- 实时行情: 现价=58.50; 涨跌幅=-0.81%; 振幅=0.00%; 成交额=0.30亿
- 均线偏离: MA5=-6.05%; MA20=-11.99%; MA60=-14.86%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 表示有反抽但修复力度不足，仍更接近弱势震荡而非有效反转。
- LLM客观评价: D线触发: 表示有反抽但修复力度不足，仍更接近弱势震荡而非有效反转。 观察目的: 验证在 panic 市场下，立讯精密次日是否能把前一日的超跌状态修复成可确认的短均回收，而不是仅出现低位反抽后继续维持中期破位。 主要风险: 盘中反弹只是噪声，无法收复 MA5/MA10，最终仍以弱势运行在 MA20/MA60 下方，延续下跌趋势。 对C线反馈: watch -> weak_rebound_reject 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> weak_rebound_reject; baseline=20260713; task_id=20260713_20260714_002475_d_observe_llm_v2; MA20触发位置=-11.99%

## 4. 600276 恒瑞医药

- 触发: reclaim_confirm / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-14T09:30:01; trade_time=09:29:45; trade_date=2026-07-14
- 实时行情: 现价=55.75; 涨跌幅=0.00%; 振幅=0.00%; 成交额=0.20亿
- 均线偏离: MA5=+0.82%; MA20=+7.43%; MA60=+7.22%
- C线原始预测: action=panic_rebound_probe; direction=neutral; confidence=40%
- 触发依据: 说明盘中不是单纯弱反抽，而是重新站回短线结构并获得基础量能支持。
- LLM客观评价: D线触发: 说明盘中不是单纯弱反抽，而是重新站回短线结构并获得基础量能支持。 观察目的: 明天盘中主要验证恒瑞医药在大盘恐慌环境下的“弱修复/反弹探针”是否能真正守住短中期均线，还是快速回落并回到防守状态。 主要风险: 在 market_regime=panic 且右侧分数为回避的背景下，当前价格已明显偏离均线但 RSI 偏高，最大风险是盘中反弹不能持续，转为冲高回落或跌破短线支撑。 对C线反馈: rebound_probe -> confirm_hold 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=rebound_probe -> confirm_hold; baseline=20260713; task_id=20260713_20260714_600276_d_observe_llm_v2; MA20触发位置=+7.43%

## 5. 600276 恒瑞医药

- 触发: noise_filter / severity=low / fire_count=3
- 时间: forecast_ts=2026-07-14T09:30:03; trade_time=09:29:45; trade_date=2026-07-14
- 实时行情: 现价=55.75; 涨跌幅=0.00%; 振幅=0.00%; 成交额=0.20亿
- 均线偏离: MA5=+0.82%; MA20=+7.43%; MA60=+7.22%
- C线原始预测: action=panic_rebound_probe; direction=neutral; confidence=40%
- 触发依据: 若仅是窄幅低量波动，则不构成对 C线的有效证伪或确认，应视为噪音区间。
- LLM客观评价: D线触发: 若仅是窄幅低量波动，则不构成对 C线的有效证伪或确认，应视为噪音区间。 观察目的: 明天盘中主要验证恒瑞医药在大盘恐慌环境下的“弱修复/反弹探针”是否能真正守住短中期均线，还是快速回落并回到防守状态。 主要风险: 在 market_regime=panic 且右侧分数为回避的背景下，当前价格已明显偏离均线但 RSI 偏高，最大风险是盘中反弹不能持续，转为冲高回落或跌破短线支撑。 对C线反馈: hold_watch_no_decision 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=hold_watch_no_decision; baseline=20260713; task_id=20260713_20260714_600276_d_observe_llm_v2; MA20触发位置=+7.43%

## 6. 600900 长江电力

- 触发: reclaim_confirm / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-14T09:30:05; trade_time=09:29:27; trade_date=2026-07-14
- 实时行情: 现价=28.40; 涨跌幅=-0.07%; 振幅=0.00%; 成交额=0.45亿
- 均线偏离: MA5=+1.82%; MA20=+4.74%; MA60=+4.65%
- C线原始预测: action=panic_rebound_probe; direction=neutral; confidence=40%
- 触发依据: 说明恐慌背景下仍能维持在关键均线之上，并且不是纯粹的弱抽动，C 线的修复观察被部分验证。
- LLM客观评价: D线触发: 说明恐慌背景下仍能维持在关键均线之上，并且不是纯粹的弱抽动，C 线的修复观察被部分验证。 观察目的: 观察长江电力在恐慌市下，次日盘中是沿着 MA5/MA20 维持修复，还是因高位拥挤与超买出现回吐，用来验证 C 线的 panic_rebound_probe。 主要风险: 高位（20日/52周位置偏高）叠加 RSI 偏热，在 panic 环境里若失去 MA20 支撑，前一日修复更可能只是反弹噪音。 对C线反馈: watch -> confirm_repair 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> confirm_repair; baseline=20260713; task_id=20260713_20260714_600900_d_observe_llm_v2; MA20触发位置=+4.74%

## 7. 601138 工业富联

- 触发: noise_filter / severity=low / fire_count=2
- 时间: forecast_ts=2026-07-14T09:30:07; trade_time=09:29:25; trade_date=2026-07-14
- 实时行情: 现价=62.90; 涨跌幅=-0.29%; 振幅=0.00%; 成交额=0.22亿
- 均线偏离: MA5=-4.31%; MA20=-10.57%; MA60=-8.85%
- C线原始预测: action=watch_only; direction=neutral; confidence=45%
- 触发依据: 若全天波动和量能都很低，盘中变化更可能是噪音而非有效信号，避免对C线做过度解读。
- LLM客观评价: D线触发: 若全天波动和量能都很低，盘中变化更可能是噪音而非有效信号，避免对C线做过度解读。 观察目的: 明天盘中验证“评分≥2但处于panic环境时仅观察、不直接确认转强”这一假设：看工业富联是否继续沿短中期均线下方弱势运行，还是出现有效的均线收复与量价修复。 主要风险: 最需要防范的是panic环境下的弱势延续与再次失守短中期均线，导致右侧评分的正向信号无法在盘中得到验证。 对C线反馈: watch_only -> ignore_noise 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch_only -> ignore_noise; baseline=20260713; task_id=20260713_20260714_601138_d_observe_llm_v2; MA20触发位置=-10.57%

## 8. 603009 北特科技

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-14T09:30:09; trade_time=09:29:32; trade_date=2026-07-14
- 实时行情: 现价=46.00; 涨跌幅=0.00%; 振幅=0.00%; 成交额=0.01亿
- 均线偏离: MA5=-3.26%; MA20=-0.78%; MA60=-5.92%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 说明只能做出弱修复但无法站回短均线，属于“有反抽、无确认”的典型状态。
- LLM客观评价: D线触发: 说明只能做出弱修复但无法站回短均线，属于“有反抽、无确认”的典型状态。 观察目的: 明天盘中验证北特科技在 panic 市场里是否能从 20 日线下方完成修复并形成有效弱反弹，从而支持 C 线的 panic_rebound_watch 假设。 主要风险: 恐慌环境下反弹不成立，价格继续在 20 日线下方走弱并演变为破位，导致情绪修复验证失败。 对C线反馈: downgrade_rebound_strength 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=downgrade_rebound_strength; baseline=20260713; task_id=20260713_20260714_603009_d_observe_llm_v2; MA20触发位置=-0.78%

## 9. 002384 东山精密

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-14T09:35:18; trade_time=09:35:09; trade_date=2026-07-14
- 实时行情: 现价=238.55; 涨跌幅=+0.78%; 振幅=3.05%; 成交额=19.49亿
- 均线偏离: MA5=-1.81%; MA20=-4.37%; MA60=+9.12%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 表示有反弹动作，但仍未摆脱均线压制，更像弱修复而非确认性修复。
- LLM客观评价: D线触发: 表示有反弹动作，但仍未摆脱均线压制，更像弱修复而非确认性修复。 观察目的: 在大盘恐慌背景下，观察东山精密次日是否能先收复 MA5/MA10 并形成情绪修复，以验证 C 线的 panic_rebound_watch 假设是否成立。 主要风险: 盘中只出现短促反抽而无法收复短中期均线，最终继续压在 MA20 下方并转为弱修复失败。 对C线反馈: weak_rebound -> 说明仅弱修复，降低对 T+1 修复的信任 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=weak_rebound -> 说明仅弱修复，降低对 T+1 修复的信任; baseline=20260713; task_id=20260713_20260714_002384_d_observe_llm_v2; MA20触发位置=-4.37%

## 10. 603667 五洲新春

- 触发: breakdown_confirm / severity=high / fire_count=1
- 时间: forecast_ts=2026-07-14T09:35:20; trade_time=09:35:13; trade_date=2026-07-14
- 实时行情: 现价=58.03; 涨跌幅=-1.58%; 振幅=2.49%; 成交额=0.78亿
- 均线偏离: MA5=-4.11%; MA20=-10.72%; MA60=-18.19%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 说明不是恐慌修复而是继续破位，直接否定C线对次日修复的核心假设。
- LLM客观评价: D线触发: 说明不是恐慌修复而是继续破位，直接否定C线对次日修复的核心假设。 观察目的: 验证五洲新春在市场恐慌背景下，次日盘中是否能从弱势下探转入短线修复，并至少出现对短均线的有效收复迹象。 主要风险: 恐慌环境下的反弹只是盘中噪音，价格无法重新站回短均线并继续失守，导致C线的panic_rebound_watch假设失效。 对C线反馈: panic_rebound_watch -> invalidate 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=panic_rebound_watch -> invalidate; baseline=20260713; task_id=20260713_20260714_603667_d_observe_llm_v2; MA20触发位置=-10.72%

## 11. 002050 三花智控

- 触发: panic_rebound_probe / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-14T09:40:29; trade_time=09:40:21; trade_date=2026-07-14
- 实时行情: 现价=40.65; 涨跌幅=-2.28%; 振幅=3.00%; 成交额=3.76亿
- 均线偏离: MA5=-5.54%; MA20=-7.98%; MA60=-13.28%
- C线原始预测: action=panic_rebound_probe; direction=neutral; confidence=40%
- 触发依据: 说明超跌背景下已经出现盘中修复尝试，适合对 C 线的 rebound probe 假设做客观跟踪。
- LLM客观评价: D线触发: 说明超跌背景下已经出现盘中修复尝试，适合对 C 线的 rebound probe 假设做客观跟踪。 观察目的: 观察明天是否出现从超跌区发起的盘中修复，重点验证 C 线对“恐慌环境下仅作修复观察”的判断是否成立。 主要风险: 反弹失败、继续失守短中期均线并延续弱势，导致 C 线的修复假设失效。 对C线反馈: probe_candidate -> confirm_or_downgrade 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=probe_candidate -> confirm_or_downgrade; baseline=20260713; task_id=20260713_20260714_002050_d_observe_llm_v2; MA20触发位置=-7.98%

## 12. 002371 北方华创

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-14T09:40:31; trade_time=09:40:21; trade_date=2026-07-14
- 实时行情: 现价=770.31; 涨跌幅=+0.79%; 振幅=2.34%; 成交额=13.82亿
- 均线偏离: MA5=-4.96%; MA20=-2.79%; MA60=+18.79%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 说明出现反弹但仍未脱离中短期均线压制，更像弱修复而非趋势反转。
- LLM客观评价: D线触发: 说明出现反弹但仍未脱离中短期均线压制，更像弱修复而非趋势反转。 观察目的: 观察盘中是否出现恐慌后的修复反弹，重点验证价格能否从MA20下方回收并避免继续破位。 主要风险: 在大盘 panic 背景下，弱反弹后再次转弱，继续沿MA20下方扩散下跌，直接否定情绪修复假设。 对C线反馈: confirm_weak_rebound_branch 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=confirm_weak_rebound_branch; baseline=20260713; task_id=20260713_20260714_002371_d_observe_llm_v2; MA20触发位置=-2.79%

## 13. 603667 五洲新春

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-14T09:40:33; trade_time=09:40:25; trade_date=2026-07-14
- 实时行情: 现价=56.74; 涨跌幅=-3.77%; 振幅=4.09%; 成交额=1.34亿
- 均线偏离: MA5=-6.24%; MA20=-12.71%; MA60=-20.01%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 说明出现反弹，但仍未完成短线均线收复，属于弱修复而非强验证。
- LLM客观评价: D线触发: 说明出现反弹，但仍未完成短线均线收复，属于弱修复而非强验证。 观察目的: 验证五洲新春在市场恐慌背景下，次日盘中是否能从弱势下探转入短线修复，并至少出现对短均线的有效收复迹象。 主要风险: 恐慌环境下的反弹只是盘中噪音，价格无法重新站回短均线并继续失守，导致C线的panic_rebound_watch假设失效。 对C线反馈: panic_rebound_watch -> weak_confirm 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=panic_rebound_watch -> weak_confirm; baseline=20260713; task_id=20260713_20260714_603667_d_observe_llm_v2; MA20触发位置=-12.71%

## 14. 002371 北方华创

- 触发: panic_rebound_probe / severity=medium / fire_count=3
- 时间: forecast_ts=2026-07-14T09:55:59; trade_time=09:55:51; trade_date=2026-07-14
- 实时行情: 现价=778.52; 涨跌幅=+1.86%; 振幅=3.07%; 成交额=26.11亿
- 均线偏离: MA5=-3.94%; MA20=-1.75%; MA60=+20.06%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 说明盘中开始从恐慌状态修复，符合 C线的情绪反弹假设。
- LLM客观评价: D线触发: 说明盘中开始从恐慌状态修复，符合 C线的情绪反弹假设。 观察目的: 观察盘中是否出现恐慌后的修复反弹，重点验证价格能否从MA20下方回收并避免继续破位。 主要风险: 在大盘 panic 背景下，弱反弹后再次转弱，继续沿MA20下方扩散下跌，直接否定情绪修复假设。 对C线反馈: retain_panic_rebound_watch 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=retain_panic_rebound_watch; baseline=20260713; task_id=20260713_20260714_002371_d_observe_llm_v2; MA20触发位置=-1.75%

## 15. 002384 东山精密

- 触发: reclaim_confirm / severity=high / fire_count=3
- 时间: forecast_ts=2026-07-14T09:56:01; trade_time=09:55:51; trade_date=2026-07-14
- 实时行情: 现价=246.68; 涨跌幅=+4.22%; 振幅=4.98%; 成交额=61.75亿
- 均线偏离: MA5=+1.54%; MA20=-1.11%; MA60=+12.84%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 若能同时收复短均线并伴随更广泛的修复信号，说明 C 线的上修复方向得到更强验证。
- LLM客观评价: D线触发: 若能同时收复短均线并伴随更广泛的修复信号，说明 C 线的上修复方向得到更强验证。 观察目的: 在大盘恐慌背景下，观察东山精密次日是否能先收复 MA5/MA10 并形成情绪修复，以验证 C 线的 panic_rebound_watch 假设是否成立。 主要风险: 盘中只出现短促反抽而无法收复短中期均线，最终继续压在 MA20 下方并转为弱修复失败。 对C线反馈: reclaim_confirm -> 支持 direction=up 与 panic_rebound_watch 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=reclaim_confirm -> 支持 direction=up 与 panic_rebound_watch; baseline=20260713; task_id=20260713_20260714_002384_d_observe_llm_v2; MA20触发位置=-1.11%

## 16. 600522 中天科技

- 触发: weak_rebound / severity=low / fire_count=1
- 时间: forecast_ts=2026-07-14T09:56:03; trade_time=09:55:51; trade_date=2026-07-14
- 实时行情: 现价=41.52; 涨跌幅=+0.48%; 振幅=3.73%; 成交额=26.39亿
- 均线偏离: MA5=-8.34%; MA20=-23.17%; MA60=-7.58%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 说明有反弹但力度不足，更像超跌后的弱修复，需要和强修复区分开来。
- LLM客观评价: D线触发: 说明有反弹但力度不足，更像超跌后的弱修复，需要和强修复区分开来。 观察目的: 验证在市场恐慌背景下，中天科技次日是否能出现可被机械识别的超跌修复，而不是继续沿弱势均线下压。 主要风险: 恐慌市中的反弹可能只是缩量弱修复；如果无法收复短均线并且跌幅继续扩大，C线的T+1上涨假设会失效。 对C线反馈: watch -> weak_positive_only 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> weak_positive_only; baseline=20260713; task_id=20260713_20260714_600522_d_observe_llm_v2; MA20触发位置=-23.17%

## 17. 603009 北特科技

- 触发: panic_rebound_probe / severity=medium / fire_count=3
- 时间: forecast_ts=2026-07-14T09:56:05; trade_time=09:55:55; trade_date=2026-07-14
- 实时行情: 现价=46.03; 涨跌幅=+0.07%; 振幅=3.76%; 成交额=0.64亿
- 均线偏离: MA5=-3.20%; MA20=-0.72%; MA60=-5.86%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 说明盘中出现修复尝试，但仍未形成稳态确认，更适合用于观察 C 线的 T+1 情绪修复是否只是试探性反抽。
- LLM客观评价: D线触发: 说明盘中出现修复尝试，但仍未形成稳态确认，更适合用于观察 C 线的 T+1 情绪修复是否只是试探性反抽。 观察目的: 明天盘中验证北特科技在 panic 市场里是否能从 20 日线下方完成修复并形成有效弱反弹，从而支持 C 线的 panic_rebound_watch 假设。 主要风险: 恐慌环境下反弹不成立，价格继续在 20 日线下方走弱并演变为破位，导致情绪修复验证失败。 对C线反馈: maintain_observation_pending 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=maintain_observation_pending; baseline=20260713; task_id=20260713_20260714_603009_d_observe_llm_v2; MA20触发位置=-0.72%

## 18. 603667 五洲新春

- 触发: panic_rebound_probe / severity=medium / fire_count=3
- 时间: forecast_ts=2026-07-14T09:56:07; trade_time=09:55:55; trade_date=2026-07-14
- 实时行情: 现价=58.29; 涨跌幅=-1.14%; 振幅=4.16%; 成交额=2.52亿
- 均线偏离: MA5=-3.68%; MA20=-10.32%; MA60=-17.82%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 说明盘中已出现低位修复起点，C线的panic_rebound_watch开始进入可验证状态。
- LLM客观评价: D线触发: 说明盘中已出现低位修复起点，C线的panic_rebound_watch开始进入可验证状态。 观察目的: 验证五洲新春在市场恐慌背景下，次日盘中是否能从弱势下探转入短线修复，并至少出现对短均线的有效收复迹象。 主要风险: 恐慌环境下的反弹只是盘中噪音，价格无法重新站回短均线并继续失守，导致C线的panic_rebound_watch假设失效。 对C线反馈: panic_rebound_watch -> probe_confirm 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=panic_rebound_watch -> probe_confirm; baseline=20260713; task_id=20260713_20260714_603667_d_observe_llm_v2; MA20触发位置=-10.32%

## 19. 002371 北方华创

- 触发: breakdown_confirm / severity=high / fire_count=4
- 时间: forecast_ts=2026-07-14T10:57:41; trade_time=10:57:33; trade_date=2026-07-14
- 实时行情: 现价=754.40; 涨跌幅=-1.30%; 振幅=4.21%; 成交额=54.38亿
- 均线偏离: MA5=-6.92%; MA20=-4.79%; MA60=+16.34%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 说明恐慌延续并出现进一步破位，反弹假设失效。
- LLM客观评价: D线触发: 说明恐慌延续并出现进一步破位，反弹假设失效。 观察目的: 观察盘中是否出现恐慌后的修复反弹，重点验证价格能否从MA20下方回收并避免继续破位。 主要风险: 在大盘 panic 背景下，弱反弹后再次转弱，继续沿MA20下方扩散下跌，直接否定情绪修复假设。 对C线反馈: invalidate_panic_rebound_watch 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=invalidate_panic_rebound_watch; baseline=20260713; task_id=20260713_20260714_002371_d_observe_llm_v2; MA20触发位置=-4.79%
