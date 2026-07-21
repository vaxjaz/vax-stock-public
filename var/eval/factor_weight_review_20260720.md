# Factor Weight Review 20260720

> 本报告只给人工调权复盘证据,不自动修改 scoring.py,不回写 factor_snapshots/results。
> low/high bucket 采用冻结因子值的底部/顶部三分位; pending 或未回填样本只计数,不进入收益统计。
> N 直接展示,不按样本数隐藏结论; evidence_strength 只提示证据厚薄。

- horizon: T+1
- total_snapshots: 754
- evaluated_rows: 712
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
| pb_percentile_1y | 712 | 0 | 0~43.7 | -0.07% | 47.68% | 87.9~99.6 | -1.33% | 40.08% | -1.26% | strong | consider_penalty_for_high_value_or_inverse_weight |
| right_side_score | 712 | 0 | -2~0.5 | -0.14% | 45.99% | 1.5~4 | -1.38% | 37.55% | -1.24% | strong | consider_penalty_for_high_value_or_inverse_weight |
| pe_percentile_1y | 695 | 17 | 0~32.5 | -0.40% | 46.75% | 81.8~99.6 | -0.99% | 41.99% | -0.59% | strong | watch_no_change |
| position_52w_pct | 712 | 0 | -4.082~43.48 | -0.36% | 42.62% | 68.07~102.4 | -0.94% | 43.46% | -0.58% | strong | watch_no_change |
| roe_avg | 712 | 0 | 0.1994~1.884 | -0.50% | 38.40% | 4.212~17.55 | -0.96% | 43.46% | -0.45% | strong | watch_no_change |
| volume_ratio_5d | 712 | 0 | 0.1387~0.8456 | -0.64% | 40.08% | 1.036~1.895 | -1.00% | 40.08% | -0.36% | strong | watch_no_change |
| np_yoy | 712 | 0 | -81.97~4.833 | -0.53% | 39.66% | 62.9~2138 | -0.77% | 44.73% | -0.24% | strong | watch_no_change |
| inflow_slope | 712 | 0 | -1.528e+09~-3.452e+07 | -0.93% | 41.35% | 3.939e+07~1.075e+09 | -1.12% | 42.19% | -0.19% | strong | watch_no_change |
| main_inflow_5d | 712 | 0 | -8.56e+09~-4.335e+08 | -1.02% | 37.55% | 1.327e+08~7.771e+09 | -0.84% | 44.73% | +0.19% | strong | watch_no_change |
| rsi_14 | 712 | 0 | 10.19~40.76 | -0.65% | 44.73% | 53.17~97.02 | -0.80% | 42.62% | -0.15% | strong | watch_no_change |
| position_20d_pct | 712 | 0 | -13.63~16.9 | -0.84% | 41.77% | 48.48~104.7 | -0.70% | 45.15% | +0.14% | strong | watch_no_change |
| turnover_zscore | 712 | 0 | -2.34~-0.59 | -0.73% | 41.35% | 0.27~3.98 | -0.68% | 42.19% | +0.05% | strong | watch_no_change |

## 人工处理规则
- `consider_up_weight_for_high_value`: 高值桶相对低值桶超额更强,可人工复核是否提高该因子正向权重。
- `consider_penalty_for_high_value_or_inverse_weight`: 高值桶明显弱于低值桶,可人工复核是否降低权重或改成反向惩罚。
- `watch_no_change`: 暂无足够方向性证据,保留观察。
- `collect_more`: 缺少可比较样本或字段缺失,继续积累。
- 任何采纳都必须另开 PR,显式说明样本、阈值、改动原因,并保持历史样本 append-only。
