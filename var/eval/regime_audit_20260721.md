# Regime Audit 20260721

> 本报告解释 market_regime 的原始输入和判定过程; 不重新取数, 不修改 regime 状态。

- trade_date: 20260721
- raw_regime: momentum
- smoothed_regime: panic
- reason: growth_avg - sh = 7.10% >= 2.0%
- indices_source: tushare
- market_overview_source: tushare

## Inputs
| field | value |
|---|---:|
| limit_down_count | 31 |
| limit_down_threshold | 50 |
| sh_change_pct | 1.7935 |
| cyb_change_pct | 7.0537 |
| kc50_change_pct | 10.7333 |
| growth_avg_change_pct | 8.8935 |
| growth_minus_sh_pct | 7.1 |
| sh_minus_growth_pct | -7.1 |

## Rules
- `limit_down_count > 50` => raw `panic`。
- `growth_avg - sh >= 2.0%` => raw `momentum`。
- `sh - growth_avg >= 1.0%` => raw `value`。
- 其他情况按当前规则 raw `momentum`。
- smoothing: panic 单日生效; panic 解除需连续2日非 panic; momentum/value 切换需连续2日同向。
