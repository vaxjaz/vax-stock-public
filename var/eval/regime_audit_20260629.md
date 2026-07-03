# Regime Audit 20260629

> 本报告解释 market_regime 的原始输入和判定过程; 不重新取数, 不修改 regime 状态。

- trade_date: 20260629
- raw_regime: panic
- smoothed_regime: panic
- reason: limit_down_count=51 > 50
- indices_source: tushare
- market_overview_source: tushare

## Inputs
| field | value |
|---|---:|
| limit_down_count | 51 |
| limit_down_threshold | 50 |
| sh_change_pct | 1.158 |
| cyb_change_pct | 0.5362 |
| kc50_change_pct | 4.6119 |
| growth_avg_change_pct | 2.57405 |
| growth_minus_sh_pct | 1.4160500000000003 |
| sh_minus_growth_pct | -1.4160500000000003 |

## Rules
- `limit_down_count > 50` => raw `panic`。
- `growth_avg - sh >= 2.0%` => raw `momentum`。
- `sh - growth_avg >= 1.0%` => raw `value`。
- 其他情况按当前规则 raw `momentum`。
- smoothing: panic 单日生效; panic 解除需连续2日非 panic; momentum/value 切换需连续2日同向。
