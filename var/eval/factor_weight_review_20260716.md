# Factor Weight Review 20260716

> 本报告只给人工调权复盘证据,不自动修改 scoring.py,不回写 factor_snapshots/results。
> low/high bucket 采用冻结因子值的底部/顶部三分位; pending 或未回填样本只计数,不进入收益统计。
> N 直接展示,不按样本数隐藏结论; evidence_strength 只提示证据厚薄。

- horizon: T+1
- total_snapshots: 670
- evaluated_rows: 628
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
| pb_percentile_1y | 628 | 0 | 0~47.2 | +0.51% | 52.63% | 89.6~99.6 | -1.02% | 41.63% | -1.53% | strong | consider_penalty_for_high_value_or_inverse_weight |
| position_20d_pct | 628 | 0 | -13.63~20.73 | +0.41% | 48.80% | 52.75~104.7 | -0.73% | 44.50% | -1.14% | strong | consider_penalty_for_high_value_or_inverse_weight |
| pe_percentile_1y | 613 | 15 | 0~34.2 | +0.31% | 50.98% | 83.5~99.6 | -0.83% | 42.65% | -1.14% | strong | consider_penalty_for_high_value_or_inverse_weight |
| position_52w_pct | 628 | 0 | -4.082~45.27 | +0.51% | 47.85% | 69.85~102.4 | -0.62% | 45.93% | -1.13% | strong | consider_penalty_for_high_value_or_inverse_weight |
| rsi_14 | 628 | 0 | 10.78~42.24 | +0.21% | 49.28% | 54.31~97.02 | -0.65% | 43.54% | -0.85% | strong | watch_no_change |
| right_side_score | 628 | 0 | -2~0.5 | +0.03% | 45.93% | 1.5~4 | -0.63% | 42.58% | -0.66% | strong | watch_no_change |
| inflow_slope | 628 | 0 | -1.528e+09~-3.328e+07 | -0.26% | 45.45% | 4.29e+07~1.075e+09 | -0.83% | 44.50% | -0.57% | strong | watch_no_change |
| turnover_zscore | 628 | 0 | -1.96~-0.53 | +0.11% | 48.80% | 0.32~3.86 | -0.40% | 42.58% | -0.51% | strong | watch_no_change |
| roe_avg | 628 | 0 | 0.1994~1.884 | -0.05% | 41.15% | 4.212~17.55 | -0.44% | 46.89% | -0.39% | strong | watch_no_change |
| main_inflow_5d | 628 | 0 | -8.56e+09~-4.283e+08 | -0.44% | 41.15% | 1.798e+08~7.771e+09 | -0.67% | 45.45% | -0.24% | strong | watch_no_change |
| volume_ratio_5d | 628 | 0 | 0.1387~0.8356 | -0.22% | 43.06% | 1.027~1.895 | -0.43% | 42.58% | -0.21% | strong | watch_no_change |
| np_yoy | 628 | 0 | -81.97~4.833 | -0.07% | 44.02% | 62.9~2138 | -0.01% | 48.80% | +0.06% | strong | watch_no_change |

## 人工处理规则
- `consider_up_weight_for_high_value`: 高值桶相对低值桶超额更强,可人工复核是否提高该因子正向权重。
- `consider_penalty_for_high_value_or_inverse_weight`: 高值桶明显弱于低值桶,可人工复核是否降低权重或改成反向惩罚。
- `watch_no_change`: 暂无足够方向性证据,保留观察。
- `collect_more`: 缺少可比较样本或字段缺失,继续积累。
- 任何采纳都必须另开 PR,显式说明样本、阈值、改动原因,并保持历史样本 append-only。
