# D线盘中触发汇总

- updated_at: 2026-08-21T10:11:20
- trade_date: 2026-08-21
- triggers: 3
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 002475 立讯精密

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-08-21T09:41:03; trade_time=09:40:57; trade_date=2026-08-21
- 实时行情: 现价=53.33; 涨跌幅=-0.02%; 振幅=1.16%; 成交额=5.20亿
- 均线偏离: MA5=-4.77%; MA20=-6.81%; MA60=-15.61%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 说明出现了反弹外观，但量能和动量不足，更像弱修复而非有效反转，需要对 C 线的反弹力度降级评价。
- LLM客观评价: D线触发: 说明出现了反弹外观，但量能和动量不足，更像弱修复而非有效反转，需要对 C 线的反弹力度降级评价。 观察目的: 观察立讯精密在大盘恐慌环境下是否出现对前一日超跌状态的盘中修复，并验证 C 线的 T+1 恐慌反弹假设能否成立。 主要风险: 弱势环境中反弹无量或修复失败，价格继续远离短中期均线并扩大超跌，导致 C 线的反弹预期失效。 对C线反馈: watch -> weaken_confidence 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> weaken_confidence; baseline=20260820; task_id=20260820_20260821_002475_d_observe_llm_v2; MA20触发位置=-6.81%

## 2. 601138 工业富联

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-08-21T09:46:07; trade_time=09:46:05; trade_date=2026-08-21
- 实时行情: 现价=62.25; 涨跌幅=+0.19%; 振幅=1.51%; 成交额=8.22亿
- 均线偏离: MA5=-4.11%; MA20=-0.95%; MA60=-7.70%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 有涨但仍压在均线之下且量能不足，说明修复偏弱。
- LLM客观评价: D线触发: 有涨但仍压在均线之下且量能不足，说明修复偏弱。 观察目的: 验证 C 线“panic_rebound_watch”在次日盘中是否兑现为对 MA20/MA5 的情绪修复，而不是缩量反弹后再度走弱。 主要风险: 恐慌环境下反弹无量、仅短暂修复后重新跌回 MA20/MA5，导致 T+1 上涨假设失效。 对C线反馈: watch -> downgrade_confidence 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> downgrade_confidence; baseline=20260820; task_id=20260820_20260821_601138_d_observe_llm_v2; MA20触发位置=-0.95%

## 3. 601138 工业富联

- 触发: panic_rebound_probe / severity=medium / fire_count=2
- 时间: forecast_ts=2026-08-21T10:11:20; trade_time=10:11:14; trade_date=2026-08-21
- 实时行情: 现价=62.56; 涨跌幅=+0.69%; 振幅=2.09%; 成交额=14.64亿
- 均线偏离: MA5=-3.63%; MA20=-0.46%; MA60=-7.24%
- C线原始预测: action=panic_rebound_watch; direction=up; confidence=50%
- 触发依据: 盘中出现修复探针，但尚未完全站稳，属于验证 C 线反弹假设的观察点。
- LLM客观评价: D线触发: 盘中出现修复探针，但尚未完全站稳，属于验证 C 线反弹假设的观察点。 观察目的: 验证 C 线“panic_rebound_watch”在次日盘中是否兑现为对 MA20/MA5 的情绪修复，而不是缩量反弹后再度走弱。 主要风险: 恐慌环境下反弹无量、仅短暂修复后重新跌回 MA20/MA5，导致 T+1 上涨假设失效。 对C线反馈: watch -> keep_observe 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> keep_observe; baseline=20260820; task_id=20260820_20260821_601138_d_observe_llm_v2; MA20触发位置=-0.46%
