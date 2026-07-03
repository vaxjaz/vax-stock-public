# Regime Audit 20260701

> 本报告解释 market_regime 的原始输入和判定过程; 不重新取数, 不修改 regime 状态。

- trade_date: 20260701
- raw_regime: value
- smoothed_regime: value
- reason: sh - growth_avg = 2.63% >= 1.0%
- indices_source: tushare
- market_overview_source: tushare

## Inputs
| field | value |
|---|---:|
| limit_down_count | 11 |
| limit_down_threshold | 50 |
| sh_change_pct | 0.4408 |
| cyb_change_pct | -1.888 |
| kc50_change_pct | -2.483 |
| growth_avg_change_pct | -2.1855 |
| growth_minus_sh_pct | -2.6263 |
| sh_minus_growth_pct | 2.6263 |

## Rules
- `limit_down_count > 50` => raw `panic`。
- `growth_avg - sh >= 2.0%` => raw `momentum`。
- `sh - growth_avg >= 1.0%` => raw `value`。
- 其他情况按当前规则 raw `momentum`。
- smoothing: panic 单日生效; panic 解除需连续2日非 panic; momentum/value 切换需连续2日同向。
