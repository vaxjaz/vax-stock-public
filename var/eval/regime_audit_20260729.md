# Regime Audit 20260729

> 本报告解释 market_regime 的原始输入和判定过程; 不重新取数, 不修改 regime 状态。

- trade_date: 20260729
- raw_regime: momentum
- smoothed_regime: panic
- reason: 未触发 panic/value 阈值,按现行规则默认 momentum
- indices_source: tushare
- market_overview_source: tushare

## Inputs
| field | value |
|---|---:|
| limit_down_count | 17 |
| limit_down_threshold | 50 |
| sh_change_pct | 0.3974 |
| cyb_change_pct | 1.5529 |
| kc50_change_pct | -0.8705 |
| growth_avg_change_pct | 0.34119999999999995 |
| growth_minus_sh_pct | -0.05620000000000003 |
| sh_minus_growth_pct | 0.05620000000000003 |

## Rules
- `limit_down_count > 50` => raw `panic`。
- `growth_avg - sh >= 2.0%` => raw `momentum`。
- `sh - growth_avg >= 1.0%` => raw `value`。
- 其他情况按当前规则 raw `momentum`。
- smoothing: panic 单日生效; panic 解除需连续2日非 panic; momentum/value 切换需连续2日同向。
