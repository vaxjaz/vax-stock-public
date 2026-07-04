# Regime Audit 20260703

> 本报告解释 market_regime 的原始输入和判定过程; 不重新取数, 不修改 regime 状态。

- trade_date: 20260703
- raw_regime: momentum
- smoothed_regime: value
- reason: 未触发 panic/value 阈值,按现行规则默认 momentum
- indices_source: tushare
- market_overview_source: tushare

## Inputs
| field | value |
|---|---:|
| limit_down_count | 27 |
| limit_down_threshold | 50 |
| sh_change_pct | 0.3658 |
| cyb_change_pct | 0.0662 |
| kc50_change_pct | -0.5883 |
| growth_avg_change_pct | -0.26105 |
| growth_minus_sh_pct | -0.62685 |
| sh_minus_growth_pct | 0.62685 |

## Rules
- `limit_down_count > 50` => raw `panic`。
- `growth_avg - sh >= 2.0%` => raw `momentum`。
- `sh - growth_avg >= 1.0%` => raw `value`。
- 其他情况按当前规则 raw `momentum`。
- smoothing: panic 单日生效; panic 解除需连续2日非 panic; momentum/value 切换需连续2日同向。
