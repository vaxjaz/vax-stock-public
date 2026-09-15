# Research v2 Forecast Calibration

- as_of_trade_date: `20260813`
- decision_at: `2026-08-14T05:04:19+08:00`
- status: `no_available_forecasts`
- select_version: `walk_forward_group_spread_v4`
- forecast_version: `conditional_group_spread_v2`
- production_eligible: `false`

| Horizon | Forecasts | Available | Abstain | Evaluated | Pending | Direction hit | MAE | Q10-Q90 coverage | Evidence |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| T+1 | 12 | 0 | 12 | 0 | 0 | NA | NA | NA | no_available_forecasts |
| T+3 | 12 | 0 | 12 | 0 | 0 | NA | NA | NA | no_available_forecasts |
| T+5 | 12 | 0 | 12 | 0 | 0 | NA | NA | NA | no_available_forecasts |
| T+10 | 12 | 0 | 12 | 0 | 0 | NA | NA | NA | no_available_forecasts |
| T+20 | 12 | 0 | 12 | 0 | 0 | NA | NA | NA | no_available_forecasts |

说明：一个独立样本等于一个 forecast date × horizon；逐股票行不作为独立样本。所有 N 均展示，但达到样本门槛也只进入人工复核，不自动认定因子有效。
