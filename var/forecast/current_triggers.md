# D线盘中触发汇总

- updated_at: 2026-09-17T09:50:31
- trade_date: 2026-09-17
- triggers: 3
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 600875 东方电气

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-09-17T09:35:23; trade_time=09:35:18; trade_date=2026-09-17
- 实时行情: 现价=24.14; 涨跌幅=+0.79%; 振幅=1.63%; 成交额=0.65亿
- 均线偏离: MA5=-1.93%; MA20=-4.31%; MA60=-8.97%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 价格上涨但仍受短期均线压制，MA20负偏离明显且量能未扩张，属于弱反弹状态通知，不能单凭该快照认定反弹最终失败。
- LLM客观评价: D线触发: 价格上涨但仍受短期均线压制，MA20负偏离明显且量能未扩张，属于弱反弹状态通知，不能单凭该快照认定反弹最终失败。 观察目的: 观察20260917东方电气是否延续均线下方弱势或仅出现弱反弹，验证C线低优先级、T+1超额收益非正的假设，并捕捉放量修复的反证。 主要风险: 基准日价格偏离MA20约-5.06%、近5日下跌约9.14%，近期已回填收益持续跑输市场，需区分弱势延续与超跌修复；低位置不等于止跌，单日上涨也不等于正超额收益。C线方向为neutral，不应将avoid解释为必然下跌。 对C线反馈: avoid -> 弱修复观察复核；暂不把上涨视作低优先级假设被推翻。 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=avoid -> 弱修复观察复核；暂不把上涨视作低优先级假设被推翻。; baseline=20260916; task_id=20260916_20260917_600875_d_observe_llm_v2; MA20触发位置=-4.31%

## 2. 002475 立讯精密

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-09-17T09:45:29; trade_time=09:45:24; trade_date=2026-09-17
- 实时行情: 现价=53.00; 涨跌幅=+0.21%; 振幅=1.30%; 成交额=5.75亿
- 均线偏离: MA5=-0.80%; MA20=-3.95%; MA60=-9.61%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 触发时呈现上涨但未收复MA5、距MA20仍远且量能未放大的弱反弹快照，支持低优先级假设，但不证明全天修复失败或超额非正。
- LLM客观评价: D线触发: 触发时呈现上涨但未收复MA5、距MA20仍远且量能未放大的弱反弹快照，支持低优先级假设，但不证明全天修复失败或超额非正。 观察目的: 观察20260917立讯精密是否继续呈现均线下方弱修复，验证C线avoid、neutral及预期超额非正的低优先级假设，同时捕捉放量修复的反证。 主要风险: 核心风险是将短期反弹误判为趋势修复，或反向将低评分机械等同于次日下跌。基线价格低于MA20约4.14%，近5日跌幅约5.32%，但最近一期单日收益和超额已转正，需双向验证；允许字段不含基准盘中收益，不能直接判断盘中超额是否非正。 对C线反馈: avoid -> weak_rebound_review：记录弱修复证据，保留neutral的方向解释，待EOD核验。 这是客观观察，不是交易指令；盘中未定论，评分和资金...
- C线反哺线索: expected_feedback_to_c=avoid -> weak_rebound_review：记录弱修复证据，保留neutral的方向解释，待EOD核验。; baseline=20260916; task_id=20260916_20260917_002475_d_observe_llm_v2; MA20触发位置=-3.95%

## 3. 600276 恒瑞医药

- 触发: weak_rebound / severity=medium / fire_count=2
- 时间: forecast_ts=2026-09-17T09:50:31; trade_time=09:50:27; trade_date=2026-09-17
- 实时行情: 现价=43.61; 涨跌幅=+0.21%; 振幅=1.03%; 成交额=3.84亿
- 均线偏离: MA5=+1.23%; MA20=-4.58%; MA60=-14.84%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 上涨但仍显著低于MA20且量能不足，符合弱反弹观察情形；这是对低优先级判断的有限支持，不是回避规则命中的最终结论。
- LLM客观评价: D线触发: 上涨但仍显著低于MA20且量能不足，符合弱反弹观察情形；这是对低优先级判断的有限支持，不是回避规则命中的最终结论。 观察目的: 观察20260917恒瑞医药的低位修复是否仍属缩量弱反弹，验证C线avoid、neutral及次日超额收益non_positive假设，并识别需要复核该判断的放量修复证据。 主要风险: 价格仍低于MA20约4.78%、低于MA60约15.01%，短期站上MA5可能只是下行过程中的修复；但RSI14为22.84且近期已回填短窗口多为正超额，也存在默认低评分回避规则遗漏超跌修复的风险。C线neutral不等于预测必然下跌。 对C线反馈: avoid -> weak_rebound_review；记录低评分背景下的弱修复，不因单次上涨直接推翻neutral。 这是客观观察，不是...
- C线反哺线索: expected_feedback_to_c=avoid -> weak_rebound_review；记录低评分背景下的弱修复，不因单次上涨直接推翻neutral。; baseline=20260916; task_id=20260916_20260917_600276_d_observe_llm_v2; MA20触发位置=-4.58%
