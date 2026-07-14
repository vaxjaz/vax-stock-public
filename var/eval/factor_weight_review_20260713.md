# Factor Weight Review 20260713

> 本报告只给人工调权复盘证据,不自动修改 scoring.py,不回写 factor_snapshots/results。
> low/high bucket 采用冻结因子值的底部/顶部三分位; pending 或未回填样本只计数,不进入收益统计。
> N 直接展示,不按样本数隐藏结论; evidence_strength 只提示证据厚薄。

- horizon: T+1
- total_snapshots: 544
- evaluated_rows: 502
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
| pb_percentile_1y | 502 | 0 | 0~50.2 | +0.84% | 56.89% | 90.5~99.6 | -0.96% | 42.51% | -1.80% | strong | consider_penalty_for_high_value_or_inverse_weight |
| position_52w_pct | 502 | 0 | -4.082~47.82 | +0.71% | 51.50% | 73.42~102.4 | -0.63% | 44.91% | -1.34% | strong | consider_penalty_for_high_value_or_inverse_weight |
| right_side_score | 502 | 0 | -2~0.5 | +0.23% | 47.31% | 1.5~4 | -0.98% | 40.72% | -1.21% | strong | consider_penalty_for_high_value_or_inverse_weight |
| position_20d_pct | 502 | 0 | -13.63~25.28 | +0.37% | 48.50% | 56.95~104.7 | -0.76% | 44.31% | -1.13% | strong | consider_penalty_for_high_value_or_inverse_weight |
| pe_percentile_1y | 490 | 12 | 0~35.5 | +0.30% | 52.76% | 86.1~99.6 | -0.70% | 42.94% | -1.00% | strong | watch_no_change |
| inflow_slope | 502 | 0 | -1.528e+09~-3.417e+07 | -0.10% | 47.31% | 4.696e+07~1.075e+09 | -1.00% | 43.71% | -0.90% | strong | watch_no_change |
| roe_avg | 502 | 0 | 0.1994~1.884 | +0.20% | 42.51% | 4.212~17.55 | -0.68% | 45.51% | -0.88% | strong | watch_no_change |
| rsi_14 | 502 | 0 | 12.14~43.41 | +0.05% | 49.70% | 56.26~97.02 | -0.54% | 45.51% | -0.59% | strong | watch_no_change |
| main_inflow_5d | 502 | 0 | -8.56e+09~-4.845e+08 | -0.47% | 41.32% | 1.822e+08~7.771e+09 | -0.92% | 45.51% | -0.44% | strong | watch_no_change |
| volume_ratio_5d | 502 | 0 | 0.1387~0.8456 | -0.07% | 44.31% | 1.048~1.895 | -0.48% | 41.32% | -0.41% | strong | watch_no_change |
| np_yoy | 502 | 0 | -81.97~4.833 | -0.03% | 44.91% | 62.9~2138 | -0.31% | 47.31% | -0.28% | strong | watch_no_change |
| turnover_zscore | 502 | 0 | -1.96~-0.43 | -0.18% | 47.31% | 0.39~3.86 | -0.36% | 41.32% | -0.19% | strong | watch_no_change |

## 人工处理规则
- `consider_up_weight_for_high_value`: 高值桶相对低值桶超额更强,可人工复核是否提高该因子正向权重。
- `consider_penalty_for_high_value_or_inverse_weight`: 高值桶明显弱于低值桶,可人工复核是否降低权重或改成反向惩罚。
- `watch_no_change`: 暂无足够方向性证据,保留观察。
- `collect_more`: 缺少可比较样本或字段缺失,继续积累。
- 任何采纳都必须另开 PR,显式说明样本、阈值、改动原因,并保持历史样本 append-only。
