# Factor Weight Review 20260703

> 本报告只给人工调权复盘证据,不自动修改 scoring.py,不回写 factor_snapshots/results。
> low/high bucket 采用冻结因子值的底部/顶部三分位; pending 或未回填样本只计数,不进入收益统计。
> N 直接展示,不按样本数隐藏结论; evidence_strength 只提示证据厚薄。

- horizon: T+1
- total_snapshots: 292
- evaluated_rows: 250
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
| pb_percentile_1y | 250 | 0 | 0~52.8 | +2.30% | 63.86% | 93.9~99.6 | -0.87% | 44.58% | -3.17% | strong | consider_penalty_for_high_value_or_inverse_weight |
| position_52w_pct | 250 | 0 | -4.082~48.07 | +2.32% | 61.45% | 77.13~102.4 | -0.81% | 45.78% | -3.13% | strong | consider_penalty_for_high_value_or_inverse_weight |
| roe_avg | 250 | 0 | 0.1994~1.884 | +1.80% | 53.01% | 4.212~17.55 | -1.10% | 44.58% | -2.90% | strong | consider_penalty_for_high_value_or_inverse_weight |
| pe_percentile_1y | 244 | 6 | 0~36.4 | +1.78% | 62.96% | 89.6~99.6 | -0.81% | 45.68% | -2.59% | strong | consider_penalty_for_high_value_or_inverse_weight |
| main_inflow_5d | 250 | 0 | -8.56e+09~-7.837e+08 | -0.74% | 36.14% | 1.833e+07~7.138e+09 | +1.06% | 65.06% | +1.80% | strong | consider_up_weight_for_high_value |
| right_side_score | 250 | 0 | -2~0.5 | +1.33% | 53.01% | 1.5~4 | -0.41% | 44.58% | -1.74% | strong | consider_penalty_for_high_value_or_inverse_weight |
| rsi_14 | 250 | 0 | 12.14~45.54 | +0.98% | 53.01% | 58.5~97.02 | -0.31% | 50.60% | -1.29% | strong | consider_penalty_for_high_value_or_inverse_weight |
| np_yoy | 250 | 0 | -81.97~4.833 | +1.70% | 56.63% | 62.9~2138 | +0.44% | 50.60% | -1.25% | strong | consider_penalty_for_high_value_or_inverse_weight |
| turnover_zscore | 250 | 0 | -1.34~-0.26 | -0.51% | 43.37% | 0.47~2.71 | +0.72% | 50.60% | +1.23% | strong | consider_up_weight_for_high_value |
| volume_ratio_5d | 250 | 0 | 0.1387~0.8445 | +0.42% | 44.58% | 1.022~1.851 | +1.56% | 59.04% | +1.14% | strong | consider_up_weight_for_high_value |
| position_20d_pct | 250 | 0 | -13.63~29.1 | +0.89% | 50.60% | 63.15~104.7 | +0.06% | 53.01% | -0.83% | strong | watch_no_change |
| inflow_slope | 250 | 0 | -1.528e+09~-5.209e+07 | -0.31% | 45.78% | 2.272e+07~8.807e+08 | -0.14% | 54.22% | +0.17% | strong | watch_no_change |

## 人工处理规则
- `consider_up_weight_for_high_value`: 高值桶相对低值桶超额更强,可人工复核是否提高该因子正向权重。
- `consider_penalty_for_high_value_or_inverse_weight`: 高值桶明显弱于低值桶,可人工复核是否降低权重或改成反向惩罚。
- `watch_no_change`: 暂无足够方向性证据,保留观察。
- `collect_more`: 缺少可比较样本或字段缺失,继续积累。
- 任何采纳都必须另开 PR,显式说明样本、阈值、改动原因,并保持历史样本 append-only。
