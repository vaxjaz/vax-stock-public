# D线盘中触发汇总

- updated_at: 2026-08-25T10:20:21
- trade_date: 2026-08-25
- triggers: 4
- 口径: 仅汇总 `forecasts.jsonl` 中 `structured.source=dline_task_blueprint` 且 `dline_plan_version=d_observe_llm_v2` 的触发记录。
- 数据源: 现价/涨跌幅/振幅/成交额来自触发时 `quote_snapshot`; MA偏离来自 `trigger_values`; C线为 `evidence_pack.C_prediction` 原始字段; LLM客观评价为触发时写入的 `reasoning`。
- 边界: 本报告只做 D线触发复盘视图, 不给买卖建议, 不自动调参。

## 1. 601138 工业富联

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-08-25T09:29:57; trade_time=09:29:26; trade_date=2026-08-25
- 实时行情: 现价=58.75; 涨跌幅=-2.73%; 振幅=0.00%; 成交额=0.58亿
- 均线偏离: MA5=-6.27%; MA20=-6.63%; MA60=-12.34%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 仍处于均线下方、近期跌幅未被扭转且量能不强，说明更多是技术性弱反抽而不是趋势修复。
- LLM客观评价: D线触发: 仍处于均线下方、近期跌幅未被扭转且量能不强，说明更多是技术性弱反抽而不是趋势修复。 观察目的: 观察明日盘中是否能在财报与预增支撑下摆脱近期MA5/MA20下方弱势，验证C线“watch/up”到底是弱修复还是可收复的反弹。 主要风险: 近期回撤和中期均线下方状态仍在，且AI板块外部闸门偏弱；如果盘中不能收回MA20，C线的上行判断大概率只是在做弱反弹而非趋势修复。 对C线反馈: watch -> weak_rebound 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> weak_rebound; baseline=20260824; task_id=20260824_20260825_601138_d_observe_llm_v2; MA20触发位置=-6.63%

## 2. 002475 立讯精密

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-08-25T09:40:02; trade_time=09:39:57; trade_date=2026-08-25
- 实时行情: 现价=52.40; 涨跌幅=-2.46%; 振幅=1.53%; 成交额=9.44亿
- 均线偏离: MA5=-4.01%; MA20=-7.21%; MA60=-16.25%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 出现反弹但仍压在均线下方、动能不足，属于弱修复而不是反转，更接近对 C 线的正向验证。
- LLM客观评价: D线触发: 出现反弹但仍压在均线下方、动能不足，属于弱修复而不是反转，更接近对 C 线的正向验证。 观察目的: 验证 C 线“回避/中性”假设：明天盘中这只票是否继续弱势承压，还是出现能够推翻回避判断的有效修复。 主要风险: 当前已跌破20日线且近5日走势偏弱，核心风险是盘中只出现弱反弹或小幅波动，但最终仍无法收复关键均线，导致回避判断被确认。 对C线反馈: watch_only 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch_only; baseline=20260824; task_id=20260824_20260825_002475_d_observe_llm_v2; MA20触发位置=-7.21%

## 3. 600875 东方电气

- 触发: weak_rebound / severity=medium / fire_count=1
- 时间: forecast_ts=2026-08-25T09:40:04; trade_time=09:39:58; trade_date=2026-08-25
- 实时行情: 现价=25.25; 涨跌幅=-0.71%; 振幅=1.22%; 成交额=0.65亿
- 均线偏离: MA5=-3.50%; MA20=-5.01%; MA60=-11.19%
- C线原始预测: action=avoid; direction=neutral; confidence=55%
- 触发依据: 说明只是弱修复而非趋势反转，适合继续把它归入低优先级观察。
- LLM客观评价: D线触发: 说明只是弱修复而非趋势反转，适合继续把它归入低优先级观察。 观察目的: 验证C线“非panic且评分<2因此回避/低优先级”的假设，看次日盘中是否继续弱势并维持在短中期均线下方，还是出现放量收复导致回避逻辑失效。 主要风险: 盘中若快速收复MA10/MA20并伴随量能放大，当前低评分回避判断会被证伪。 对C线反馈: maintain_avoid 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=maintain_avoid; baseline=20260824; task_id=20260824_20260825_600875_d_observe_llm_v2; MA20触发位置=-5.01%

## 4. 601138 工业富联

- 触发: noise_filter / severity=low / fire_count=2
- 时间: forecast_ts=2026-08-25T10:20:21; trade_time=10:20:20; trade_date=2026-08-25
- 实时行情: 现价=59.86; 涨跌幅=-0.89%; 振幅=2.20%; 成交额=18.74亿
- 均线偏离: MA5=-4.50%; MA20=-4.86%; MA60=-10.68%
- C线原始预测: action=watch; direction=up; confidence=60%
- 触发依据: 处于均线下方窄区间且涨跌幅不大，优先视为盘中噪音，不应过度解释为趋势信号。
- LLM客观评价: D线触发: 处于均线下方窄区间且涨跌幅不大，优先视为盘中噪音，不应过度解释为趋势信号。 观察目的: 观察明日盘中是否能在财报与预增支撑下摆脱近期MA5/MA20下方弱势，验证C线“watch/up”到底是弱修复还是可收复的反弹。 主要风险: 近期回撤和中期均线下方状态仍在，且AI板块外部闸门偏弱；如果盘中不能收回MA20，C线的上行判断大概率只是在做弱反弹而非趋势修复。 对C线反馈: watch -> ignore_noise 这是客观观察，不是交易指令；盘中未定论，评分和资金以EOD定稿数据为准。
- C线反哺线索: expected_feedback_to_c=watch -> ignore_noise; baseline=20260824; task_id=20260824_20260825_601138_d_observe_llm_v2; MA20触发位置=-4.86%
