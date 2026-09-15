# Research v2 Forecast Calibration

- as_of_trade_date: `20260814`
- decision_at: `2026-08-15T05:04:43+08:00`
- status: `no_available_forecasts`
- select_version: `walk_forward_group_spread_v4`
- forecast_version: `conditional_group_spread_v2`
- production_eligible: `false`

| Horizon | Forecasts | Available | Abstain | Evaluated | Pending | Direction hit | MAE | Q10-Q90 coverage | Evidence |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| T+1 | 13 | 0 | 13 | 0 | 0 | NA | NA | NA | no_available_forecasts |
| T+3 | 13 | 0 | 13 | 0 | 0 | NA | NA | NA | no_available_forecasts |
| T+5 | 13 | 0 | 13 | 0 | 0 | NA | NA | NA | no_available_forecasts |
| T+10 | 13 | 0 | 13 | 0 | 0 | NA | NA | NA | no_available_forecasts |
| T+20 | 13 | 0 | 13 | 0 | 0 | NA | NA | NA | no_available_forecasts |

说明：一个独立样本等于一个 forecast date × horizon；逐股票行不作为独立样本。所有 N 均展示，但达到样本门槛也只进入人工复核，不自动认定因子有效。
