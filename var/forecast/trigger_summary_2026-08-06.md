# D线盘中触发汇总

- updated_at: 2026-08-06T09:38:13
- trade_date: 2026-08-06
- triggers: 4
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 002475 立讯精密

- 触发: breakdown_confirm / severity=high / fire_count=2
- 时间: forecast_ts=2026-08-06T09:28:04; trade_time=09:25:00; trade_date=2026-08-06
- 实时行情: 现价=54.15; 涨跌幅=-3.08%; 振幅=0.00%; 成交额=0.53亿
- 均线偏离: MA5=-3.61%; MA20=-9.12%; MA60=-18.32%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明盘中未出现有效修复，弱势延续而非单日噪声。
- LLM客观评价: D线触发: 说明盘中未出现有效修复，弱势延续而非单日噪声。 观察目的: 验证C线“非panic且评分<2，次日以回避为主”的判断是否成立：盘中是否继续受20日线压制、反抽是否缺乏延续、以及是否出现收复关键均线的逆转信号。 主要风险: 若次日盘中出现放量修复并重新站上5日线/20日线，当前的回避判断可能失效，说明这不是延续下行而是超跌修复。 对C线反馈: confirm_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=confirm_avoid; baseline=20260805; task_id=20260805_20260806_002475_d_observe_llm_v2; MA20触发位置=-9.12%

## 2. 600276 恒瑞医药

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-08-06T09:28:06; trade_time=09:27:51; trade_date=2026-08-06
- 实时行情: 现价=53.65; 涨跌幅=+0.21%; 振幅=0.00%; 成交额=0.30亿
- 均线偏离: MA5=-0.16%; MA20=-1.77%; MA60=+3.68%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 如果只能靠弱反弹贴近MA5，但仍未收复MA20且量能不足/RSI偏弱，说明修复不具备确认条件。
- LLM客观评价: D线触发: 如果只能靠弱反弹贴近MA5，但仍未收复MA20且量能不足/RSI偏弱，说明修复不具备确认条件。 观察目的: 明天重点验证恒瑞医药是否会在弱势均线结构下继续回避，还是能通过盘中重新站回MA20/MA10来否定“低优先级回避”这一判断。 主要风险: 价格继续压在MA20下方并伴随弱反弹失败，说明当前不是可确认的修复段，C线的回避判断会被盘中弱势延续所支持。 对C线反馈: watch -> avoid_review 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> avoid_review; baseline=20260805; task_id=20260805_20260806_600276_d_observe_llm_v2; MA20触发位置=-1.77%

## 3. 600875 东方电气

- 触发: noise_filter / severity=low / fire_count=1
- 时间: forecast_ts=2026-08-06T09:38:11; trade_time=09:38:08; trade_date=2026-08-06
- 实时行情: 现价=27.85; 涨跌幅=-0.36%; 振幅=1.68%; 成交额=1.95亿
- 均线偏离: MA5=+5.21%; MA20=+5.69%; MA60=-9.41%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 若全天窄幅波动且量能不扩张，则更像噪音区间，不足以对 C 线形成有效证伪或确认。
- LLM客观评价: D线触发: 若全天窄幅波动且量能不扩张，则更像噪音区间，不足以对 C 线形成有效证伪或确认。 观察目的: 观察东方电气明天盘中是否延续前一日的高位强势并进一步站稳，还是回落失守短中期支撑，从而验证 C 线“回避/中性”判断。 主要风险: 高位强势被盘中继续放大，导致“默认回避”的假设失效；或者冲高后快速回落并跌回 20 日线附近，说明前一日上涨更像短线噪音而非可延续趋势。 对C线反馈: observe_only 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=observe_only; baseline=20260805; task_id=20260805_20260806_600875_d_observe_llm_v2; MA20触发位置=+5.69%

## 4. 601138 工业富联

- 触发: breakout_confirm / severity=medium / fire_count=3
- 时间: forecast_ts=2026-08-06T09:38:13; trade_time=09:38:08; trade_date=2026-08-06
- 实时行情: 现价=66.39; 涨跌幅=+0.71%; 振幅=2.43%; 成交额=24.02亿
- 均线偏离: MA5=+13.58%; MA20=+8.87%; MA60=-2.25%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 说明强势延续仍有效，盘中表现支持C线的偏强判断。
- LLM客观评价: D线触发: 说明强势延续仍有效，盘中表现支持C线的偏强判断。 观察目的: 验证C线对工业富联次日继续偏强的假设：高位右侧结构能否守住20日线之上并延续放量上攻，还是在AI板块上限约束下转为冲高回落。 主要风险: 高位依赖趋势延续与板块环境共振，最核心风险是盘中失去20日线支撑后，强势结构退化为回吐或弱修复。 对C线反馈: watch -> confirm_strength 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> confirm_strength; baseline=20260805; task_id=20260805_20260806_601138_d_observe_llm_v2; MA20触发位置=+8.87%
