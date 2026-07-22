# Factor Weight Review 20260721

> 本报告只给人工调权复盘证据,不自动修改 scoring.py,不回写 factor_snapshots/results。
> low/high bucket 采用冻结因子值的底部/顶部三分位; pending 或未回填样本只计数,不进入收益统计。
> N 直接展示,不按样本数隐藏结论; evidence_strength 只提示证据厚薄。

- horizon: T+1
- total_snapshots: 796
- evaluated_rows: 754
- pending_or_unfilled: 42
- min_reference_for_strength: 20
- spread_threshold_reference: +1.00%

## 术语说明
- `low bucket` / `high bucket`: 按冻结因子值排序后的底部/顶部三分位样本。
- `low_avg_excess` / `high_avg_excess`: 低值桶/高值桶在目标 horizon 的平均超额收益。
- `high-low`: 高值桶平均超额减低值桶平均超额; 正数表示高值桶阶段性更占优,负数表示高值桶更弱。
- `evidence_strength`: `thin`/`medium`/`strong` 只提示样本证据厚薄,不隐藏任何桶,也不自动形成结论。
- `consider_up_weight_for_high_value`: 高值桶相对低值桶超额更强,可人工复核是否提高该因子的正向权重。
- `consider_penalty_for_high_value_or_inverse_weight`: 高值桶弱于低值桶,可人工复核是否降权或改成反向惩罚。
- `watch_no_change`: 暂无足够方向性证据,继续观察。
- `collect_more`: 缺少可比较样本或字段缺失,继续积累,不做调权动作。

## 因子证据总表
| factor | N | missing_metric | low_range | low_avg_excess | low_excess>0 | high_range | high_avg_excess | high_excess>0 | high-low | strength | review_action |
|---|---:|---:|---|---:|---:|---|---:|---:|---:|---|---|
| pb_percentile_1y | 754 | 0 | 0~41.1 | +0.26% | 52.19% | 87.4~99.6 | -1.19% | 41.43% | -1.45% | strong | consider_penalty_for_high_value_or_inverse_weight |
| position_52w_pct | 754 | 0 | -4.082~42.25 | +0.08% | 49.00% | 66.2~102.4 | -0.94% | 43.03% | -1.02% | strong | consider_penalty_for_high_value_or_inverse_weight |
| right_side_score | 754 | 0 | -2~0.5 | -0.00% | 48.21% | 1.5~4 | -1.01% | 41.04% | -1.00% | strong | consider_penalty_for_high_value_or_inverse_weight |
| rsi_14 | 754 | 0 | 10.19~39.51 | +0.16% | 52.19% | 52.38~97.02 | -0.84% | 42.23% | -1.00% | strong | watch_no_change |
| pe_percentile_1y | 736 | 18 | 0~30.7 | -0.04% | 51.43% | 79.2~99.6 | -0.72% | 43.27% | -0.68% | strong | watch_no_change |
| position_20d_pct | 754 | 0 | -13.63~15.49 | -0.05% | 50.20% | 45.16~104.7 | -0.64% | 45.42% | -0.59% | strong | watch_no_change |
| main_inflow_5d | 754 | 0 | -8.56e+09~-4.108e+08 | -0.81% | 39.44% | 1.388e+08~7.771e+09 | -0.52% | 47.01% | +0.29% | strong | watch_no_change |
| volume_ratio_5d | 754 | 0 | 0.1387~0.8563 | -0.60% | 40.64% | 1.047~1.895 | -0.43% | 45.02% | +0.17% | strong | watch_no_change |
| roe_avg | 754 | 0 | 0.1994~1.884 | -0.32% | 41.43% | 4.212~17.55 | -0.46% | 46.61% | -0.14% | strong | watch_no_change |
| turnover_zscore | 754 | 0 | -2.34~-0.56 | -0.54% | 44.22% | 0.25~3.98 | -0.41% | 43.82% | +0.14% | strong | watch_no_change |
| inflow_slope | 754 | 0 | -1.528e+09~-3.274e+07 | -0.74% | 42.63% | 3.944e+07~1.075e+09 | -0.84% | 44.62% | -0.10% | strong | watch_no_change |
| np_yoy | 754 | 0 | -81.97~4.833 | -0.35% | 42.63% | 62.9~2138 | -0.40% | 47.41% | -0.05% | strong | watch_no_change |

## 人工处理规则
- `consider_up_weight_for_high_value`: 高值桶相对低值桶超额更强,可人工复核是否提高该因子正向权重。
- `consider_penalty_for_high_value_or_inverse_weight`: 高值桶明显弱于低值桶,可人工复核是否降低权重或改成反向惩罚。
- `watch_no_change`: 暂无足够方向性证据,保留观察。
- `collect_more`: 缺少可比较样本或字段缺失,继续积累。
- 任何采纳都必须另开 PR,显式说明样本、阈值、改动原因,并保持历史样本 append-only。
