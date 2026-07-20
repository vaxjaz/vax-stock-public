# D线盘中触发汇总

- updated_at: 2026-07-20T14:39:36
- trade_date: 2026-07-20
- triggers: 19
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 002371 北方华创

- 触发: weak_rebound / severity=medium / fire_count=3
- 时间: forecast_ts=2026-07-20T09:27:16; trade_time=09:25:00; trade_date=2026-07-20
- 实时行情: 现价=704.00; 涨跌幅=+3.99%; 振幅=0.00%; 成交额=1.26亿
- 均线偏离: MA5=-3.85%; MA20=-11.80%; MA60=+5.83%
- C线原始预测: action=watch_only; direction=neutral; confidence=45%
- 触发依据: 说明出现了反弹，但修复力度不足、动量仍弱，更像是弱反弹而非结构性转强。
- LLM客观评价: D线触发: 说明出现了反弹，但修复力度不足、动量仍弱，更像是弱反弹而非结构性转强。 观察目的: 明天盘中验证北方华创在 panic 环境下是继续弱化破位，还是能真正收复短中期均线，从而检验 C 线的 watch_only 判断。 主要风险: 在市场恐慌背景下，盘中反弹可能只是技术性回抽，无法修复 MA5/MA10/MA20，最终延续下行。 对C线反馈: watch_only -> keep_monitor 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch_only -> keep_monitor; baseline=20260717; task_id=20260717_20260720_002371_d_observe_llm_v2; MA20触发位置=-11.80%

## 2. 002463 沪电股份

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-20T09:27:18; trade_time=09:25:00; trade_date=2026-07-20
- 实时行情: 现价=130.35; 涨跌幅=+2.00%; 振幅=0.00%; 成交额=0.79亿
- 均线偏离: MA5=-1.78%; MA20=-5.24%; MA60=+4.27%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 若仅在短线均线下方做弱修复、且量能未改善或动能仍弱，则更像技术性反抽而非有效修复。
- LLM客观评价: D线触发: 若仅在短线均线下方做弱修复、且量能未改善或动能仍弱，则更像技术性反抽而非有效修复。 观察目的: 验证在 panic 市场中，沪电股份次日盘中是否能从短线超跌状态转入有效修复，重点看对短均线的回收与反弹是否有量能配合。 主要风险: 当前仍处于 MA20 下方且近10日主力净流入为负，次日最核心的风险是反弹弱、修复不成形，最终演变为继续失守中期支撑。 对C线反馈: weak_rebound -> keep neutral-to-cautious interpretation of direction/confidence 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。 ⚠️[铁律校验] 检测到疑似越界(盘中新评分/买卖价/资金臆测), 以EOD报告为准, 盘中未定论
- C线反哺线索: expected_feedback_to_c=weak_rebound -> keep neutral-to-cautious interpretation of direction/confidence; baseline=20260717; task_id=20260717_20260720_002463_d_observe_llm_v2; MA20触发位置=-5.24%

## 3. 603667 五洲新春

- 触发: weak_rebound / severity=medium / fire_count=3
- 时间: forecast_ts=2026-07-20T09:27:20; trade_time=09:26:52; trade_date=2026-07-20
- 实时行情: 现价=54.08; 涨跌幅=+0.02%; 振幅=0.00%; 成交额=0.06亿
- 均线偏离: MA5=-6.65%; MA20=-14.37%; MA60=-22.83%
- C线原始预测: action=panic_rebound_probe; direction=neutral; confidence=40%
- 触发依据: 说明出现了反弹，但仍未摆脱短中期均线压制，更像超跌反抽而非趋势修复。
- LLM客观评价: D线触发: 说明出现了反弹，但仍未摆脱短中期均线压制，更像超跌反抽而非趋势修复。 观察目的: 明天盘中重点验证：在 panic 市场与明显弱势位置下，五洲新春是否只出现低质量超跌修复，还是能真正摆脱继续破位的风险。 主要风险: 当前股价仍显著低于 MA5/20/60，最大风险是盘中任何反弹都只是弱修复，随后重新走低并延续下探。 对C线反馈: 反馈为弱反弹成立，但不支持上修为趋势性修复 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=反馈为弱反弹成立，但不支持上修为趋势性修复; baseline=20260717; task_id=20260717_20260720_603667_d_observe_llm_v2; MA20触发位置=-14.37%

## 4. 002384 东山精密

- 触发: breakdown_confirm / severity=high / fire_count=2
- 时间: forecast_ts=2026-07-20T09:32:29; trade_time=09:32:21; trade_date=2026-07-20
- 实时行情: 现价=231.01; 涨跌幅=-4.51%; 振幅=6.48%; 成交额=24.50亿
- 均线偏离: MA5=-9.07%; MA20=-7.67%; MA60=+2.40%
- C线原始预测: action=watch_only; direction=neutral; confidence=45%
- 触发依据: 若同时出现更深的均线下压和负收益扩展，说明恐慌延续而非修复，C线的“仅观察”应偏向风险确认。
- LLM客观评价: D线触发: 若同时出现更深的均线下压和负收益扩展，说明恐慌延续而非修复，C线的“仅观察”应偏向风险确认。 观察目的: 验证在市场恐慌背景下，东山精密次日盘中是继续失守短中期均线并确认弱势，还是能重新站回MA10/MA20从而推翻C线的“仅观察、不直接介入”判断。 主要风险: 恐慌市中高位品种失去MA20支撑后继续下探，导致前期业绩与资金优势无法转化为有效承接，C线的watch_only可能仍偏乐观。 对C线反馈: watch_only -> risk_off_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch_only -> risk_off_review; baseline=20260717; task_id=20260717_20260720_002384_d_observe_llm_v2; MA20触发位置=-7.67%

## 5. 600276 恒瑞医药

- 触发: panic_rebound_probe / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-20T09:32:31; trade_time=09:32:23; trade_date=2026-07-20
- 实时行情: 现价=53.99; 涨跌幅=+1.50%; 振幅=2.07%; 成交额=2.99亿
- 均线偏离: MA5=-2.63%; MA20=+1.03%; MA60=+4.05%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 说明盘中出现恐慌后的初步修复，但还未完全确认是否能转为有效反弹。
- LLM客观评价: D线触发: 说明盘中出现恐慌后的初步修复，但还未完全确认是否能转为有效反弹。 观察目的: 验证恒瑞医药在大盘恐慌背景下，次日是否能围绕MA20完成情绪修复并延续弱反弹，而不是仅出现盘中脉冲后再失守。 主要风险: 恐慌市下的修复力度不足，反弹只停留在MA20下方的弱修复，随后重新转为失守。 对C线反馈: watch -> hold_rebound_observation 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> hold_rebound_observation; baseline=20260717; task_id=20260717_20260720_600276_d_observe_llm_v2; MA20触发位置=+1.03%

## 6. 600900 长江电力

- 触发: panic_rebound_probe / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-20T09:32:33; trade_time=09:32:27; trade_date=2026-07-20
- 实时行情: 现价=28.18; 涨跌幅=+0.68%; 振幅=1.61%; 成交额=2.57亿
- 均线偏离: MA5=-0.69%; MA20=+2.97%; MA60=+3.38%
- C线原始预测: action=panic_rebound_probe; direction=neutral; confidence=40%
- 触发依据: 说明盘中确实出现了探针式修复，但尚未完成全面站稳；用于验证 C 线的中性反弹假设是否按剧本展开。
- LLM客观评价: D线触发: 说明盘中确实出现了探针式修复，但尚未完成全面站稳；用于验证 C 线的中性反弹假设是否按剧本展开。 观察目的: 明天盘中观察这只高位公用事业票在恐慌市中是否只出现短线修复探针，还是能进一步站回短均线以验证 C 线的 panic_rebound_probe 假设。 主要风险: 恐慌环境下的修复只是盘中脉冲，无法同时守住 MA20 和 MA5，最终回落证伪反弹假设。 对C线反馈: probe_seen -> keep_neutral 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=probe_seen -> keep_neutral; baseline=20260717; task_id=20260717_20260720_600900_d_observe_llm_v2; MA20触发位置=+2.97%

## 7. 600183 生益科技

- 触发: breakdown_confirm / severity=high / fire_count=2
- 时间: forecast_ts=2026-07-20T09:42:55; trade_time=09:42:43; trade_date=2026-07-20
- 实时行情: 现价=129.05; 涨跌幅=-2.45%; 振幅=5.59%; 成交额=18.42亿
- 均线偏离: MA5=-9.64%; MA20=-19.06%; MA60=-0.50%
- C线原始预测: action=watch_only; direction=neutral; confidence=45%
- 触发依据: 若中期支撑同时失守且波动/放量放大，说明恐慌延续而非正常回撤。
- LLM客观评价: D线触发: 若中期支撑同时失守且波动/放量放大，说明恐慌延续而非正常回撤。 观察目的: 验证C线的核心假设：在恐慌市环境下，生益科技虽有业绩与预增支撑，但盘中更可能先表现为趋势修复不足或继续破位，而不是直接走出强反转。 主要风险: 恐慌环境压过基本面，导致股价连20日线和60日线的修复都失败，弱反弹后再度转弱。 对C线反馈: watch -> risk_off_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> risk_off_review; baseline=20260717; task_id=20260717_20260720_600183_d_observe_llm_v2; MA20触发位置=-19.06%

## 8. 002463 沪电股份

- 触发: breakdown_confirm / severity=high / fire_count=3
- 时间: forecast_ts=2026-07-20T09:48:05; trade_time=09:47:57; trade_date=2026-07-20
- 实时行情: 现价=123.05; 涨跌幅=-3.72%; 振幅=6.64%; 成交额=22.76亿
- 均线偏离: MA5=-7.28%; MA20=-10.55%; MA60=-1.57%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 若盘中失守 MA60 且伴随放量或波动扩大，说明反弹假设被中期支撑破坏，C 线的修复预期应被明显削弱。
- LLM客观评价: D线触发: 若盘中失守 MA60 且伴随放量或波动扩大，说明反弹假设被中期支撑破坏，C 线的修复预期应被明显削弱。 观察目的: 验证在 panic 市场中，沪电股份次日盘中是否能从短线超跌状态转入有效修复，重点看对短均线的回收与反弹是否有量能配合。 主要风险: 当前仍处于 MA20 下方且近10日主力净流入为负，次日最核心的风险是反弹弱、修复不成形，最终演变为继续失守中期支撑。 对C线反馈: invalidate_rebound -> downgrade action=panic_rebound_watch and mark risk_off 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。 ⚠️[铁律校验] 检测到疑似越界(盘中新评分/买卖价/资金臆测), 以EOD报告为准, 盘中未...
- C线反哺线索: expected_feedback_to_c=invalidate_rebound -> downgrade action=panic_rebound_watch and mark risk_off; baseline=20260717; task_id=20260717_20260720_002463_d_observe_llm_v2; MA20触发位置=-10.55%

## 9. 600900 长江电力

- 触发: reclaim_confirm / severity=high / fire_count=3
- 时间: forecast_ts=2026-07-20T09:53:15; trade_time=09:53:11; trade_date=2026-07-20
- 实时行情: 现价=28.40; 涨跌幅=+1.46%; 振幅=2.61%; 成交额=13.72亿
- 均线偏离: MA5=+0.08%; MA20=+3.77%; MA60=+4.19%
- C线原始预测: action=panic_rebound_probe; direction=neutral; confidence=40%
- 触发依据: 若同时站回 MA5/MA20 且量能不弱，说明修复强于‘探针’，C 线应被反馈为更强的修复状态。
- LLM客观评价: D线触发: 若同时站回 MA5/MA20 且量能不弱，说明修复强于‘探针’，C 线应被反馈为更强的修复状态。 观察目的: 明天盘中观察这只高位公用事业票在恐慌市中是否只出现短线修复探针，还是能进一步站回短均线以验证 C 线的 panic_rebound_probe 假设。 主要风险: 恐慌环境下的修复只是盘中脉冲，无法同时守住 MA20 和 MA5，最终回落证伪反弹假设。 对C线反馈: probe_strengthened -> confirm_repair 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=probe_strengthened -> confirm_repair; baseline=20260717; task_id=20260717_20260720_600900_d_observe_llm_v2; MA20触发位置=+3.77%

## 10. 603728 鸣志电器

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-20T09:58:28; trade_time=09:58:21; trade_date=2026-07-20
- 实时行情: 现价=50.04; 涨跌幅=+1.01%; 振幅=3.17%; 成交额=1.12亿
- 均线偏离: MA5=-7.59%; MA20=-15.38%; MA60=-18.85%
- C线原始预测: action=watch_only; direction=neutral; confidence=45%
- 触发依据: 说明盘中虽有反弹，但仍未摆脱弱势区间，属于可观察的修复脉冲而非有效转强。
- LLM客观评价: D线触发: 说明盘中虽有反弹，但仍未摆脱弱势区间，属于可观察的修复脉冲而非有效转强。 观察目的: 观察明天盘中这只票在panic环境下是继续沿MA10/MA20下方弱势延续，还是出现对关键均线的修复性回收，用来验证C线的watch_only判断。 主要风险: 市场恐慌背景叠加近端跌幅较大，最需要防范的是反弹无持续性、继续失守趋势均线并把C线的“仅观察”进一步坐实为弱势延续。 对C线反馈: watch_only -> weak_rebound_observed 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch_only -> weak_rebound_observed; baseline=20260717; task_id=20260717_20260720_603728_d_observe_llm_v2; MA20触发位置=-15.38%

## 11. 600522 中天科技

- 触发: breakdown_confirm / severity=high / fire_count=2
- 时间: forecast_ts=2026-07-20T10:34:32; trade_time=10:34:24; trade_date=2026-07-20
- 实时行情: 现价=32.41; 涨跌幅=-3.68%; 振幅=8.35%; 成交额=45.10亿
- 均线偏离: MA5=-17.28%; MA20=-36.36%; MA60=-28.91%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 说明恐慌下跌继续扩散，盘中并未形成有效修复，反弹假设被证伪。
- LLM客观评价: D线触发: 说明恐慌下跌继续扩散，盘中并未形成有效修复，反弹假设被证伪。 观察目的: 验证在 panic 市场中是否出现超跌修复，并确认盘中能否回收短均线来检验 C 线的 T+1 反弹观察假设。 主要风险: 反弹只是一段弱修复，无法收复短中期均线，最终仍被系统性恐慌和下跌惯性继续压制。 对C线反馈: invalidate rebound_watch 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=invalidate rebound_watch; baseline=20260717; task_id=20260717_20260720_600522_d_observe_llm_v2; MA20触发位置=-36.36%

## 12. 601138 工业富联

- 触发: breakdown_confirm / severity=high / fire_count=3
- 时间: forecast_ts=2026-07-20T10:34:34; trade_time=10:34:27; trade_date=2026-07-20
- 实时行情: 现价=56.40; 涨跌幅=-2.07%; 振幅=6.06%; 成交额=42.64亿
- 均线偏离: MA5=-9.88%; MA20=-17.03%; MA60=-18.47%
- C线原始预测: action=watch_only; direction=neutral; confidence=45%
- 触发依据: 若盘中继续远离MA20/MA60且跌幅扩大，说明弱势延续而非单日扰动，验证C线的防守判断。
- LLM客观评价: D线触发: 若盘中继续远离MA20/MA60且跌幅扩大，说明弱势延续而非单日扰动，验证C线的防守判断。 观察目的: 验证工业富联在panic市场下是否仍维持均线下方弱势，C线的watch_only是否被盘中继续破位或无效修复所支持。 主要风险: 盘中进一步下破并伴随波动放大，说明评分与业绩支撑不足以对抗panic环境，C线的低置信观察结论需要继续偏防守。 对C线反馈: watch_only -> breakdown_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch_only -> breakdown_review; baseline=20260717; task_id=20260717_20260720_601138_d_observe_llm_v2; MA20触发位置=-17.03%

## 13. 603728 鸣志电器

- 触发: breakdown_confirm / severity=high / fire_count=2
- 时间: forecast_ts=2026-07-20T10:34:35; trade_time=10:34:30; trade_date=2026-07-20
- 实时行情: 现价=48.06; 涨跌幅=-2.99%; 振幅=4.91%; 成交额=1.90亿
- 均线偏离: MA5=-11.24%; MA20=-18.73%; MA60=-22.06%
- C线原始预测: action=watch_only; direction=neutral; confidence=45%
- 触发依据: 说明弱势没有得到修复，反而继续向下扩展，能够验证C线在panic环境下对风险的判断是否成立。
- LLM客观评价: D线触发: 说明弱势没有得到修复，反而继续向下扩展，能够验证C线在panic环境下对风险的判断是否成立。 观察目的: 观察明天盘中这只票在panic环境下是继续沿MA10/MA20下方弱势延续，还是出现对关键均线的修复性回收，用来验证C线的watch_only判断。 主要风险: 市场恐慌背景叠加近端跌幅较大，最需要防范的是反弹无持续性、继续失守趋势均线并把C线的“仅观察”进一步坐实为弱势延续。 对C线反馈: confirm_panic_bias -> keep_watch_only 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=confirm_panic_bias -> keep_watch_only; baseline=20260717; task_id=20260717_20260720_603728_d_observe_llm_v2; MA20触发位置=-18.73%

## 14. 601138 工业富联

- 触发: panic_rebound_probe / severity=medium / fire_count=4
- 时间: forecast_ts=2026-07-20T10:50:04; trade_time=10:50:00; trade_date=2026-07-20
- 实时行情: 现价=57.68; 涨跌幅=+0.16%; 振幅=6.63%; 成交额=48.18亿
- 均线偏离: MA5=-7.83%; MA20=-15.15%; MA60=-16.62%
- C线原始预测: action=watch_only; direction=neutral; confidence=45%
- 触发依据: 若出现正向修复且波动放大，需要观察这是否只是panic中的脉冲反弹，还是具备继续修复的基础。
- LLM客观评价: D线触发: 若出现正向修复且波动放大，需要观察这是否只是panic中的脉冲反弹，还是具备继续修复的基础。 观察目的: 验证工业富联在panic市场下是否仍维持均线下方弱势，C线的watch_only是否被盘中继续破位或无效修复所支持。 主要风险: 盘中进一步下破并伴随波动放大，说明评分与业绩支撑不足以对抗panic环境，C线的低置信观察结论需要继续偏防守。 对C线反馈: watch_only -> rebound_quality_check 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch_only -> rebound_quality_check; baseline=20260717; task_id=20260717_20260720_601138_d_observe_llm_v2; MA20触发位置=-15.15%

## 15. 603009 北特科技

- 触发: breakdown_confirm / severity=high / fire_count=2
- 时间: forecast_ts=2026-07-20T13:06:40; trade_time=13:06:37; trade_date=2026-07-20
- 实时行情: 现价=41.47; 涨跌幅=-1.31%; 振幅=4.38%; 成交额=2.23亿
- 均线偏离: MA5=-7.27%; MA20=-11.07%; MA60=-14.44%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 说明盘中并未出现修复，反而继续处于弱势下探状态，C线的恐慌修复假设需要被证伪。
- LLM客观评价: D线触发: 说明盘中并未出现修复，反而继续处于弱势下探状态，C线的恐慌修复假设需要被证伪。 观察目的: 验证北特科技在恐慌市下是否能出现有效盘中修复，重点看短均线收复与量价配合能否支持C线的T+1反弹假设。 主要风险: 反弹只是缩量弱修复，价格继续停留在MA5/MA20下方并伴随动能走弱，导致C线的恐慌修复判断失效。 对C线反馈: watch -> avoid_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> avoid_review; baseline=20260717; task_id=20260717_20260720_603009_d_observe_llm_v2; MA20触发位置=-11.07%

## 16. 603667 五洲新春

- 触发: breakdown_confirm / severity=high / fire_count=4
- 时间: forecast_ts=2026-07-20T13:42:47; trade_time=13:42:45; trade_date=2026-07-20
- 实时行情: 现价=52.30; 涨跌幅=-3.27%; 振幅=8.32%; 成交额=8.61亿
- 均线偏离: MA5=-9.72%; MA20=-17.19%; MA60=-25.37%
- C线原始预测: action=panic_rebound_probe; direction=neutral; confidence=40%
- 触发依据: 说明盘中不是修复而是继续破位，C线的 rebound probe 假设被直接削弱。
- LLM客观评价: D线触发: 说明盘中不是修复而是继续破位，C线的 rebound probe 假设被直接削弱。 观察目的: 明天盘中重点验证：在 panic 市场与明显弱势位置下，五洲新春是否只出现低质量超跌修复，还是能真正摆脱继续破位的风险。 主要风险: 当前股价仍显著低于 MA5/20/60，最大风险是盘中任何反弹都只是弱修复，随后重新走低并延续下探。 对C线反馈: 将反馈为继续回避/下调修复可信度 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=将反馈为继续回避/下调修复可信度; baseline=20260717; task_id=20260717_20260720_603667_d_observe_llm_v2; MA20触发位置=-17.19%

## 17. 002475 立讯精密

- 触发: panic_rebound_probe / severity=high / fire_count=4
- 时间: forecast_ts=2026-07-20T13:48:03; trade_time=13:47:51; trade_date=2026-07-20
- 实时行情: 现价=57.40; 涨跌幅=-0.88%; 振幅=4.59%; 成交额=48.07亿
- 均线偏离: MA5=-4.57%; MA20=-11.59%; MA60=-16.40%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 在深度偏离短中期均线的背景下，若同时出现波动和量能抬升，说明盘中存在恐慌修复/止跌尝试，需要重点验证 C 线的 T+1 修复假设。
- LLM客观评价: D线触发: 在深度偏离短中期均线的背景下，若同时出现波动和量能抬升，说明盘中存在恐慌修复/止跌尝试，需要重点验证 C 线的 T+1 修复假设。 观察目的: 验证立讯精密在 panic 市场中次日是否出现带量的弱反弹或短均线收复，以检验 C线“情绪修复”假设。 主要风险: 反弹只停留在盘中抽拉，无法收复 MA5/MA10，且继续受 MA20/MA60 压制，导致修复假设失效。 对C线反馈: 若触发则支持 panic_rebound_watch，并保留情绪修复方向 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=若触发则支持 panic_rebound_watch，并保留情绪修复方向; baseline=20260717; task_id=20260717_20260720_002475_d_observe_llm_v2; MA20触发位置=-11.59%

## 18. 002475 立讯精密

- 触发: risk_off_confirm / severity=high / fire_count=5
- 时间: forecast_ts=2026-07-20T13:53:13; trade_time=13:53:06; trade_date=2026-07-20
- 实时行情: 现价=57.00; 涨跌幅=-1.57%; 振幅=5.04%; 成交额=50.04亿
- 均线偏离: MA5=-5.24%; MA20=-12.21%; MA60=-16.98%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 若价格继续远离中长期均线且波动放大，说明盘中修复失败、风险偏好未改善，C 线的 panic_rebound 假设需要下调。
- LLM客观评价: D线触发: 若价格继续远离中长期均线且波动放大，说明盘中修复失败、风险偏好未改善，C 线的 panic_rebound 假设需要下调。 观察目的: 验证立讯精密在 panic 市场中次日是否出现带量的弱反弹或短均线收复，以检验 C线“情绪修复”假设。 主要风险: 反弹只停留在盘中抽拉，无法收复 MA5/MA10，且继续受 MA20/MA60 压制，导致修复假设失效。 对C线反馈: 若触发则转为 risk_off_review，并削弱 rebound 置信度 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=若触发则转为 risk_off_review，并削弱 rebound 置信度; baseline=20260717; task_id=20260717_20260720_002475_d_observe_llm_v2; MA20触发位置=-12.21%

## 19. 002371 北方华创

- 触发: breakdown_confirm / severity=high / fire_count=4
- 时间: forecast_ts=2026-07-20T14:39:36; trade_time=14:39:27; trade_date=2026-07-20
- 实时行情: 现价=660.11; 涨跌幅=-2.49%; 振幅=8.50%; 成交额=111.38亿
- 均线偏离: MA5=-9.84%; MA20=-17.30%; MA60=-0.77%
- C线原始预测: action=watch_only; direction=neutral; confidence=45%
- 触发依据: 说明不仅短中期趋势未修复，连中期支撑也被压制，并且伴随量能或波动放大，符合恐慌延续。
- LLM客观评价: D线触发: 说明不仅短中期趋势未修复，连中期支撑也被压制，并且伴随量能或波动放大，符合恐慌延续。 观察目的: 明天盘中验证北方华创在 panic 环境下是继续弱化破位，还是能真正收复短中期均线，从而检验 C 线的 watch_only 判断。 主要风险: 在市场恐慌背景下，盘中反弹可能只是技术性回抽，无法修复 MA5/MA10/MA20，最终延续下行。 对C线反馈: watch_only -> reinforce_risk_off 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch_only -> reinforce_risk_off; baseline=20260717; task_id=20260717_20260720_002371_d_observe_llm_v2; MA20触发位置=-17.30%
