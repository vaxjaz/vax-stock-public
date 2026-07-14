# Regime Audit 20260713

> 本报告解释 market_regime 的原始输入和判定过程; 不重新取数, 不修改 regime 状态。

- trade_date: 20260713
- raw_regime: panic
- smoothed_regime: panic
- reason: limit_down_count=211 > 50
- indices_source: tushare
- market_overview_source: tushare

## Inputs
| field | value |
|---|---:|
| limit_down_count | 211 |
| limit_down_threshold | 50 |
| sh_change_pct | -2.0612 |
| cyb_change_pct | -3.1023 |
| kc50_change_pct | -3.4217 |
| growth_avg_change_pct | -3.262 |
| growth_minus_sh_pct | -1.2008 |
| sh_minus_growth_pct | 1.2008 |

## Rules
- `limit_down_count > 50` => raw `panic`。
- `growth_avg - sh >= 2.0%` => raw `momentum`。
- `sh - growth_avg >= 1.0%` => raw `value`。
- 其他情况按当前规则 raw `momentum`。
- smoothing: panic 单日生效; panic 解除需连续2日非 panic; momentum/value 切换需连续2日同向。
