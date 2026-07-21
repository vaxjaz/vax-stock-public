# D线盘中触发汇总

- updated_at: 2026-07-21T11:14:25
- trade_date: 2026-07-21
- triggers: 19
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 002463 沪电股份

- 触发: weak_rebound / severity=medium / fire_count=3
- 时间: forecast_ts=2026-07-21T09:25:37; trade_time=09:25:00; trade_date=2026-07-21
- 实时行情: 现价=115.27; 涨跌幅=+0.22%; 振幅=0.00%; 成交额=0.76亿
- 均线偏离: MA5=-11.86%; MA20=-15.27%; MA60=-7.98%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 有反弹但仍完全压在短中期均线之下，通常属于弱修复，需要继续观察是否只是盘中噪音。
- LLM客观评价: D线触发: 有反弹但仍完全压在短中期均线之下，通常属于弱修复，需要继续观察是否只是盘中噪音。 观察目的: 明天盘中观察沪电股份在恐慌市中是否出现有量的超跌修复，并验证这次上涨假设能否从跌破短中期均线的弱势结构中真正恢复。 主要风险: 恐慌环境下的反弹如果缺乏量能并且始终无法收复短中期均线，就会演变成弱反抽后继续下行，直接削弱C线的T+1看涨假设。 对C线反馈: watch -> keep_neutral_validation 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> keep_neutral_validation; baseline=20260720; task_id=20260720_20260721_002463_d_observe_llm_v2; MA20触发位置=-15.27%

## 2. 002475 立讯精密

- 触发: weak_rebound / severity=medium / fire_count=3
- 时间: forecast_ts=2026-07-21T09:25:40; trade_time=09:25:00; trade_date=2026-07-21
- 实时行情: 现价=57.29; 涨跌幅=+0.86%; 振幅=0.00%; 成交额=0.24亿
- 均线偏离: MA5=-4.06%; MA20=-10.96%; MA60=-16.38%
- C线原始预测: action=watch_only; direction=neutral; confidence=45%
- 触发依据: 若有反弹但仍站不回短均线，且量能/指标修复不足，更符合弱反弹而非结构反转。
- LLM客观评价: D线触发: 若有反弹但仍站不回短均线，且量能/指标修复不足，更符合弱反弹而非结构反转。 观察目的: 明天盘中重点验证：在右侧评分勉强达标但整体处于恐慌市时，立讯精密是否只能出现弱反弹、还是会继续沿着均线下方走弱并完成风险证伪。 主要风险: 恐慌环境下的下跌延续与反弹失真，导致当前“可考虑介入”级别的右侧信号被市场弱势直接否定。 对C线反馈: watch_only -> weak_bounce_only 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch_only -> weak_bounce_only; baseline=20260720; task_id=20260720_20260721_002475_d_observe_llm_v2; MA20触发位置=-10.96%

## 3. 600276 恒瑞医药

- 触发: panic_rebound_probe / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-21T09:25:42; trade_time=09:25:14; trade_date=2026-07-21
- 实时行情: 现价=55.99; 涨跌幅=+0.76%; 振幅=0.00%; 成交额=0.64亿
- 均线偏离: MA5=+1.04%; MA20=+4.17%; MA60=+7.91%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 说明盘中反弹不仅没有失守短均，还出现一定强度的趋势修复，可用于验证 C 线的 T+1 修复假设。
- LLM客观评价: D线触发: 说明盘中反弹不仅没有失守短均，还出现一定强度的趋势修复，可用于验证 C 线的 T+1 修复假设。 观察目的: 验证 C 线的 panic_rebound_watch 是否能在盘中体现为对短均线的稳住与修复，而不是恐慌环境下的脉冲反弹后回落。 主要风险: 盘中反弹无法守住短均线，重新转入放量走弱，说明 panic 仍主导且 rebound 假设失效。 对C线反馈: confirm_rebound_watch 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=confirm_rebound_watch; baseline=20260720; task_id=20260720_20260721_600276_d_observe_llm_v2; MA20触发位置=+4.17%

## 4. 600900 长江电力

- 触发: reclaim_confirm / severity=medium / fire_count=3
- 时间: forecast_ts=2026-07-21T09:25:44; trade_time=09:25:17; trade_date=2026-07-21
- 实时行情: 现价=29.00; 涨跌幅=+0.07%; 振幅=0.00%; 成交额=1.05亿
- 均线偏离: MA5=+1.80%; MA20=+5.57%; MA60=+6.27%
- C线原始预测: action=panic_rebound_probe; direction=neutral; confidence=40%
- 触发依据: 说明价格仍维持在中短期均线之上，恐慌背景下的修复未被破坏。
- LLM客观评价: D线触发: 说明价格仍维持在中短期均线之上，恐慌背景下的修复未被破坏。 观察目的: 验证长江电力在恐慌市中是否只是高位弱修复探针，还是会在盘中回撤中暴露超买失效。 主要风险: 高位满位叠加RSI超买，在市场恐慌背景下很容易从修复转为转弱，导致C线的恐慌修复假设失真。 对C线反馈: action_review -> keep_neutral_rebound_probe 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=action_review -> keep_neutral_rebound_probe; baseline=20260720; task_id=20260720_20260721_600900_d_observe_llm_v2; MA20触发位置=+5.57%

## 5. 603009 北特科技

- 触发: panic_rebound_probe / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-21T09:25:46; trade_time=09:25:01; trade_date=2026-07-21
- 实时行情: 现价=42.29; 涨跌幅=+2.45%; 振幅=0.00%; 成交额=0.01亿
- 均线偏离: MA5=-3.40%; MA20=-9.36%; MA60=-12.46%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 说明出现低位反抽，但尚未完成趋势确认，需要继续观察是否延伸为有效修复。
- LLM客观评价: D线触发: 说明出现低位反抽，但尚未完成趋势确认，需要继续观察是否延伸为有效修复。 观察目的: 验证 C线的“panic_rebound_watch”是否成立：明天盘中能否从超跌区向短均线完成有效修复，而不是仅出现低位噪音反抽。 主要风险: 恐慌环境下的反弹失败，价格继续远离MA5/10/20并向MA60下压，导致上行假设失效。 对C线反馈: probe -> continue_watch 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=probe -> continue_watch; baseline=20260720; task_id=20260720_20260721_603009_d_observe_llm_v2; MA20触发位置=-9.36%

## 6. 002371 北方华创

- 触发: weak_rebound / severity=medium / fire_count=3
- 时间: forecast_ts=2026-07-21T09:30:55; trade_time=09:30:45; trade_date=2026-07-21
- 实时行情: 现价=692.07; 涨跌幅=+2.24%; 振幅=2.07%; 成交额=3.96亿
- 均线偏离: MA5=-3.17%; MA20=-12.93%; MA60=+3.45%
- C线原始预测: action=watch_only; direction=neutral; confidence=45%
- 触发依据: 说明出现反抽但强度不足，更像恐慌后的技术性回弹，不能证明 C 线的修复假设。
- LLM客观评价: D线触发: 说明出现反抽但强度不足，更像恐慌后的技术性回弹，不能证明 C 线的修复假设。 观察目的: 验证在 panic 市场中，北方华创是否只是评分≥2下的弱修复，还是会继续出现对 MA5/MA20 的有效收复或进一步破位。 主要风险: 整体恐慌环境下，前期资金优势无法转化为盘中承接，导致反弹无量后再次走弱并延续破位。 对C线反馈: watch_only -> weak_rebound 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch_only -> weak_rebound; baseline=20260720; task_id=20260720_20260721_002371_d_observe_llm_v2; MA20触发位置=-12.93%

## 7. 600183 生益科技

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-07-21T09:30:57; trade_time=09:30:46; trade_date=2026-07-21
- 实时行情: 现价=125.68; 涨跌幅=+1.90%; 振幅=3.46%; 成交额=2.08亿
- 均线偏离: MA5=-10.61%; MA20=-19.63%; MA60=-3.73%
- C线原始预测: action=watch_only; direction=neutral; confidence=45%
- 触发依据: 说明盘中出现超跌反抽，但力度仍不足以修复短均线结构，属于弱反弹观察而不是趋势确认。
- LLM客观评价: D线触发: 说明盘中出现超跌反抽，但力度仍不足以修复短均线结构，属于弱反弹观察而不是趋势确认。 观察目的: 验证 C线关于“评分尚可但处于 panic 环境下只观察、不直接介入”的假设，重点看明天盘中是继续破位扩散，还是仅出现弱反弹/修复确认。 主要风险: 在市场 panic 背景下，个股超跌继续加深，导致右侧评分无法转化为有效修复信号。 对C线反馈: watch_only -> weak_rebound_note 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch_only -> weak_rebound_note; baseline=20260720; task_id=20260720_20260721_600183_d_observe_llm_v2; MA20触发位置=-19.63%

## 8. 600276 恒瑞医药

- 触发: noise_filter / severity=low / fire_count=3
- 时间: forecast_ts=2026-07-21T09:30:59; trade_time=09:30:49; trade_date=2026-07-21
- 实时行情: 现价=55.25; 涨跌幅=-0.58%; 振幅=1.49%; 成交额=1.18亿
- 均线偏离: MA5=-0.30%; MA20=+2.80%; MA60=+6.48%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 过滤低波动、低量能的横盘噪声，避免把无效震荡误判为 rebound 验证。
- LLM客观评价: D线触发: 过滤低波动、低量能的横盘噪声，避免把无效震荡误判为 rebound 验证。 观察目的: 验证 C 线的 panic_rebound_watch 是否能在盘中体现为对短均线的稳住与修复，而不是恐慌环境下的脉冲反弹后回落。 主要风险: 盘中反弹无法守住短均线，重新转入放量走弱，说明 panic 仍主导且 rebound 假设失效。 对C线反馈: hold_observe 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=hold_observe; baseline=20260720; task_id=20260720_20260721_600276_d_observe_llm_v2; MA20触发位置=+2.80%

## 9. 603728 鸣志电器

- 触发: weak_rebound / severity=medium / fire_count=3
- 时间: forecast_ts=2026-07-21T09:31:01; trade_time=09:30:51; trade_date=2026-07-21
- 实时行情: 现价=48.48; 涨跌幅=+1.30%; 振幅=1.46%; 成交额=0.04亿
- 均线偏离: MA5=-7.73%; MA20=-17.15%; MA60=-21.15%
- C线原始预测: action=watch_only; direction=neutral; confidence=45%
- 触发依据: 说明出现的是偏弱修复，仍未摆脱短线偏空结构，只能验证为技术性反抽而非趋势反转。
- LLM客观评价: D线触发: 说明出现的是偏弱修复，仍未摆脱短线偏空结构，只能验证为技术性反抽而非趋势反转。 观察目的: 验证C线“评分≥2但在panic下仅watch_only”的假设：明天盘中是出现弱修复并逐步抬离20日线，还是继续向下破位并强化风险回避。 主要风险: 在恐慌市况下反弹无量、20日线修复失败，导致右侧评分与题材概念都不足以支撑有效修复。 对C线反馈: watch_only -> weak_rebound_observed 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch_only -> weak_rebound_observed; baseline=20260720; task_id=20260720_20260721_603728_d_observe_llm_v2; MA20触发位置=-17.15%

## 10. 002384 东山精密

- 触发: breakdown_confirm / severity=high / fire_count=2
- 时间: forecast_ts=2026-07-21T09:36:11; trade_time=09:36:03; trade_date=2026-07-21
- 实时行情: 现价=211.00; 涨跌幅=-3.09%; 振幅=7.34%; 成交额=36.01亿
- 均线偏离: MA5=-15.69%; MA20=-14.77%; MA60=-6.81%
- C线原始预测: action=watch_only; direction=neutral; confidence=45%
- 触发依据: 若继续深压在MA20/MA5下方且伴随放量或高波动，说明弱势延续而非修复，C线的恐慌降档假设被强化。
- LLM客观评价: D线触发: 若继续深压在MA20/MA5下方且伴随放量或高波动，说明弱势延续而非修复，C线的恐慌降档假设被强化。 观察目的: 验证C线“评分够但处panic仅观察”的假设：明天盘中是继续沿关键均线下方弱势消化，还是出现有效修复并重新站回短中期均线。 主要风险: 在恐慌市环境下继续失守MA20与MA10，弱反弹无持续性，从而证明当前只能watch_only而非修复确认。 对C线反馈: watch -> reinforce_panic_downgrade 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> reinforce_panic_downgrade; baseline=20260720; task_id=20260720_20260721_002384_d_observe_llm_v2; MA20触发位置=-14.77%

## 11. 002463 沪电股份

- 触发: breakdown_confirm / severity=high / fire_count=4
- 时间: forecast_ts=2026-07-21T09:36:13; trade_time=09:36:03; trade_date=2026-07-21
- 实时行情: 现价=112.63; 涨跌幅=-2.08%; 振幅=4.66%; 成交额=12.63亿
- 均线偏离: MA5=-13.88%; MA20=-17.21%; MA60=-10.08%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 若继续走弱且远离20日线，说明恐慌修复失败，C线看涨假设被明显削弱。
- LLM客观评价: D线触发: 若继续走弱且远离20日线，说明恐慌修复失败，C线看涨假设被明显削弱。 观察目的: 明天盘中观察沪电股份在恐慌市中是否出现有量的超跌修复，并验证这次上涨假设能否从跌破短中期均线的弱势结构中真正恢复。 主要风险: 恐慌环境下的反弹如果缺乏量能并且始终无法收复短中期均线，就会演变成弱反抽后继续下行，直接削弱C线的T+1看涨假设。 对C线反馈: watch -> avoid_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> avoid_review; baseline=20260720; task_id=20260720_20260721_002463_d_observe_llm_v2; MA20触发位置=-17.21%

## 12. 601179 中国西电

- 触发: breakdown_confirm / severity=high / fire_count=1
- 时间: forecast_ts=2026-07-21T09:36:15; trade_time=09:36:08; trade_date=2026-07-21
- 实时行情: 现价=12.03; 涨跌幅=-2.43%; 振幅=3.57%; 成交额=3.22亿
- 均线偏离: MA5=-0.08%; MA20=-12.95%; MA60=-22.89%
- C线原始预测: action=panic_rebound_probe; direction=neutral; confidence=40%
- 触发依据: 说明弱势继续扩展，盘中行为更接近破位延续而非恐慌修复。
- LLM客观评价: D线触发: 说明弱势继续扩展，盘中行为更接近破位延续而非恐慌修复。 观察目的: 验证中国西电在恐慌市况下是否出现站回短均线的技术性修复，还是继续沿着弱势趋势扩展破位。 主要风险: 盘中反弹若不能收复并稳住MA5/MA10，只是恐慌环境里的脉冲噪音，随后继续向MA20/MA60下方扩展弱势。 对C线反馈: downgrade_rebound_probe 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=downgrade_rebound_probe; baseline=20260720; task_id=20260720_20260721_601179_d_observe_llm_v2; MA20触发位置=-12.95%

## 13. 600522 中天科技

- 触发: breakdown_confirm / severity=high / fire_count=2
- 时间: forecast_ts=2026-07-21T09:46:38; trade_time=09:46:29; trade_date=2026-07-21
- 实时行情: 现价=31.25; 涨跌幅=-3.01%; 振幅=6.36%; 成交额=16.37亿
- 均线偏离: MA5=-16.36%; MA20=-36.94%; MA60=-31.44%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 说明盘中修复失败并转入继续破位，C线的恐慌修复假设应被判定为失效。
- LLM客观评价: D线触发: 说明盘中修复失败并转入继续破位，C线的恐慌修复假设应被判定为失效。 观察目的: 观察中天科技在极度超跌与市场恐慌背景下，次日盘中是否出现可被机械识别的修复反弹，并验证这种反弹能否脱离短线均线压制。 主要风险: 恐慌环境下的弱修复失败，反弹只是一日噪音，随后继续沿着 20 日线下方扩大跌幅。 对C线反馈: panic_rebound_watch -> invalidate 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=panic_rebound_watch -> invalidate; baseline=20260720; task_id=20260720_20260721_600522_d_observe_llm_v2; MA20触发位置=-36.94%

## 14. 601138 工业富联

- 触发: breakdown_confirm / severity=high / fire_count=3
- 时间: forecast_ts=2026-07-21T10:02:08; trade_time=10:02:03; trade_date=2026-07-21
- 实时行情: 现价=55.96; 涨跌幅=-0.96%; 振幅=3.65%; 成交额=21.79亿
- 均线偏离: MA5=-8.66%; MA20=-16.30%; MA60=-19.01%
- C线原始预测: action=watch_only; direction=neutral; confidence=45%
- 触发依据: 若在低位继续走弱并伴随放大波动，说明超跌后没有形成有效修复，盘面仍处于延续下压状态。
- LLM客观评价: D线触发: 若在低位继续走弱并伴随放大波动，说明超跌后没有形成有效修复，盘面仍处于延续下压状态。 观察目的: 验证 C 线对工业富联的假设：在 panic 市况下，次日盘中是继续弱势破位，还是出现有量的超跌修复，从而确认或推翻 watch_only 的判断。 主要风险: 恐慌环境下的超跌反弹失败，价格继续在短中期均线下方运行并延续下跌惯性。 对C线反馈: confirm watch_only, keep panic_downgrade valid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=confirm watch_only, keep panic_downgrade valid; baseline=20260720; task_id=20260720_20260721_601138_d_observe_llm_v2; MA20触发位置=-16.30%

## 15. 603009 北特科技

- 触发: breakdown_confirm / severity=high / fire_count=3
- 时间: forecast_ts=2026-07-21T10:02:10; trade_time=10:02:03; trade_date=2026-07-21
- 实时行情: 现价=41.05; 涨跌幅=-0.56%; 振幅=3.54%; 成交额=1.00亿
- 均线偏离: MA5=-6.23%; MA20=-12.02%; MA60=-15.03%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 说明修复失败并继续向中长均线下压，C线上行假设被证伪。
- LLM客观评价: D线触发: 说明修复失败并继续向中长均线下压，C线上行假设被证伪。 观察目的: 验证 C线的“panic_rebound_watch”是否成立：明天盘中能否从超跌区向短均线完成有效修复，而不是仅出现低位噪音反抽。 主要风险: 恐慌环境下的反弹失败，价格继续远离MA5/10/20并向MA60下压，导致上行假设失效。 对C线反馈: breakdown -> invalidate_rebound 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=breakdown -> invalidate_rebound; baseline=20260720; task_id=20260720_20260721_603009_d_observe_llm_v2; MA20触发位置=-12.02%

## 16. 002371 北方华创

- 触发: reclaim_confirm / severity=low / fire_count=4
- 时间: forecast_ts=2026-07-21T10:27:58; trade_time=10:27:45; trade_date=2026-07-21
- 实时行情: 现价=709.01; 涨跌幅=+4.74%; 振幅=5.55%; 成交额=61.76亿
- 均线偏离: MA5=-0.80%; MA20=-10.80%; MA60=+5.98%
- C线原始预测: action=watch_only; direction=neutral; confidence=45%
- 触发依据: 若能重新贴近并收复短线均线，说明 C 线的‘仅观察’假设被削弱，修复质量高于普通反抽。
- LLM客观评价: D线触发: 若能重新贴近并收复短线均线，说明 C 线的‘仅观察’假设被削弱，修复质量高于普通反抽。 观察目的: 验证在 panic 市场中，北方华创是否只是评分≥2下的弱修复，还是会继续出现对 MA5/MA20 的有效收复或进一步破位。 主要风险: 整体恐慌环境下，前期资金优势无法转化为盘中承接，导致反弹无量后再次走弱并延续破位。 对C线反馈: watch_only -> repair_confirm 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch_only -> repair_confirm; baseline=20260720; task_id=20260720_20260721_002371_d_observe_llm_v2; MA20触发位置=-10.80%

## 17. 002463 沪电股份

- 触发: panic_rebound_probe / severity=medium / fire_count=5
- 时间: forecast_ts=2026-07-21T10:38:16; trade_time=10:38:09; trade_date=2026-07-21
- 实时行情: 现价=116.67; 涨跌幅=+1.43%; 振幅=11.23%; 成交额=58.43亿
- 均线偏离: MA5=-10.79%; MA20=-14.24%; MA60=-6.86%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 出现正向反弹但仍明显低于20日线，说明进入恐慌修复观察段，适合验证C线的‘panic_rebound_watch’假设。
- LLM客观评价: D线触发: 出现正向反弹但仍明显低于20日线，说明进入恐慌修复观察段，适合验证C线的‘panic_rebound_watch’假设。 观察目的: 明天盘中观察沪电股份在恐慌市中是否出现有量的超跌修复，并验证这次上涨假设能否从跌破短中期均线的弱势结构中真正恢复。 主要风险: 恐慌环境下的反弹如果缺乏量能并且始终无法收复短中期均线，就会演变成弱反抽后继续下行，直接削弱C线的T+1看涨假设。 对C线反馈: watch -> confirm_rebound_probe 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> confirm_rebound_probe; baseline=20260720; task_id=20260720_20260721_002463_d_observe_llm_v2; MA20触发位置=-14.24%

## 18. 600875 东方电气

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-07-21T11:04:03; trade_time=11:03:55; trade_date=2026-07-21
- 实时行情: 现价=25.73; 涨跌幅=+2.14%; 振幅=3.45%; 成交额=6.73亿
- 均线偏离: MA5=-0.82%; MA20=-8.39%; MA60=-23.26%
- C线原始预测: action=watch_only; direction=neutral; confidence=45%
- 触发依据: 出现反弹但仍未脱离中期弱势区间，且量能/动能不够，说明更偏向技术性弱修复而非趋势反转
- LLM客观评价: D线触发: 出现反弹但仍未脱离中期弱势区间，且量能/动能不够，说明更偏向技术性弱修复而非趋势反转 观察目的: 验证这只票在 panic 环境下是仅有超跌噪音反弹，还是能对 MA5/MA10/MA20 形成有效修复，从而检验 C 线的 watch_only/neutral 结论是否成立 主要风险: 盘中反弹无量且重新跌回短中期均线下方，说明右侧结构仍被破坏，C 线的弱修复假设可能失效 对C线反馈: watch -> continue_monitor 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> continue_monitor; baseline=20260720; task_id=20260720_20260721_600875_d_observe_llm_v2; MA20触发位置=-8.39%

## 19. 600276 恒瑞医药

- 触发: risk_off_confirm / severity=high / fire_count=4
- 时间: forecast_ts=2026-07-21T11:14:25; trade_time=11:14:13; trade_date=2026-07-21
- 实时行情: 现价=54.54; 涨跌幅=-1.85%; 振幅=4.01%; 成交额=30.50亿
- 均线偏离: MA5=-1.58%; MA20=+1.47%; MA60=+5.11%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 说明反弹未能守住短均且出现重新走弱，属于 panic 延续而非有效修复。
- LLM客观评价: D线触发: 说明反弹未能守住短均且出现重新走弱，属于 panic 延续而非有效修复。 观察目的: 验证 C 线的 panic_rebound_watch 是否能在盘中体现为对短均线的稳住与修复，而不是恐慌环境下的脉冲反弹后回落。 主要风险: 盘中反弹无法守住短均线，重新转入放量走弱，说明 panic 仍主导且 rebound 假设失效。 对C线反馈: invalidate_rebound 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=invalidate_rebound; baseline=20260720; task_id=20260720_20260721_600276_d_observe_llm_v2; MA20触发位置=+1.47%
