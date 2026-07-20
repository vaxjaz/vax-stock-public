# Factor Weight Review 20260717

> 本报告只给人工调权复盘证据,不自动修改 scoring.py,不回写 factor_snapshots/results。
> low/high bucket 采用冻结因子值的底部/顶部三分位; pending 或未回填样本只计数,不进入收益统计。
> N 直接展示,不按样本数隐藏结论; evidence_strength 只提示证据厚薄。

- horizon: T+1
- total_snapshots: 712
- evaluated_rows: 670
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
| pb_percentile_1y | 670 | 0 | 0~46.3 | +0.25% | 49.33% | 88.7~99.6 | -1.03% | 41.70% | -1.28% | strong | consider_penalty_for_high_value_or_inverse_weight |
| right_side_score | 670 | 0 | -2~0.5 | +0.08% | 47.09% | 1.5~4 | -0.95% | 39.01% | -1.03% | strong | consider_penalty_for_high_value_or_inverse_weight |
| pe_percentile_1y | 654 | 16 | 0~34.2 | +0.03% | 47.71% | 83.1~99.6 | -0.87% | 42.20% | -0.90% | strong | watch_no_change |
| position_52w_pct | 670 | 0 | -4.082~44.43 | +0.02% | 43.95% | 68.97~102.4 | -0.80% | 44.39% | -0.82% | strong | watch_no_change |
| position_20d_pct | 670 | 0 | -13.63~18.94 | -0.04% | 44.84% | 50.56~104.7 | -0.76% | 43.95% | -0.73% | strong | watch_no_change |
| rsi_14 | 670 | 0 | 10.78~41.47 | -0.21% | 45.29% | 53.75~97.02 | -0.80% | 42.15% | -0.59% | strong | watch_no_change |
| roe_avg | 670 | 0 | 0.1994~1.884 | -0.22% | 39.46% | 4.212~17.55 | -0.79% | 43.95% | -0.57% | strong | watch_no_change |
| main_inflow_5d | 670 | 0 | -8.56e+09~-4.431e+08 | -0.83% | 38.12% | 1.434e+08~7.771e+09 | -0.64% | 44.84% | +0.20% | strong | watch_no_change |
| turnover_zscore | 670 | 0 | -2.34~-0.58 | -0.33% | 43.50% | 0.27~3.86 | -0.51% | 42.15% | -0.18% | strong | watch_no_change |
| inflow_slope | 670 | 0 | -1.528e+09~-3.507e+07 | -0.74% | 41.26% | 4.038e+07~1.075e+09 | -0.91% | 43.50% | -0.18% | strong | watch_no_change |
| volume_ratio_5d | 670 | 0 | 0.1387~0.8329 | -0.47% | 40.36% | 1.015~1.895 | -0.43% | 43.05% | +0.05% | strong | watch_no_change |
| np_yoy | 670 | 0 | -81.97~4.833 | -0.28% | 41.26% | 62.9~2138 | -0.33% | 46.19% | -0.05% | strong | watch_no_change |

## 人工处理规则
- `consider_up_weight_for_high_value`: 高值桶相对低值桶超额更强,可人工复核是否提高该因子正向权重。
- `consider_penalty_for_high_value_or_inverse_weight`: 高值桶明显弱于低值桶,可人工复核是否降低权重或改成反向惩罚。
- `watch_no_change`: 暂无足够方向性证据,保留观察。
- `collect_more`: 缺少可比较样本或字段缺失,继续积累。
- 任何采纳都必须另开 PR,显式说明样本、阈值、改动原因,并保持历史样本 append-only。
