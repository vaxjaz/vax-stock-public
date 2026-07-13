# Regime Audit 20260710

> 本报告解释 market_regime 的原始输入和判定过程; 不重新取数, 不修改 regime 状态。

- trade_date: 20260710
- raw_regime: value
- smoothed_regime: value
- reason: sh - growth_avg = 3.95% >= 1.0%
- indices_source: tushare
- market_overview_source: tushare

## Inputs
| field | value |
|---|---:|
| limit_down_count | 17 |
| limit_down_threshold | 50 |
| sh_change_pct | -1.0015 |
| cyb_change_pct | -4.3662 |
| kc50_change_pct | -5.5288 |
| growth_avg_change_pct | -4.9475 |
| growth_minus_sh_pct | -3.9459999999999997 |
| sh_minus_growth_pct | 3.9459999999999997 |

## Rules
- `limit_down_count > 50` => raw `panic`。
- `growth_avg - sh >= 2.0%` => raw `momentum`。
- `sh - growth_avg >= 1.0%` => raw `value`。
- 其他情况按当前规则 raw `momentum`。
- smoothing: panic 单日生效; panic 解除需连续2日非 panic; momentum/value 切换需连续2日同向。
