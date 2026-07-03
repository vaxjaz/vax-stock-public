# Factor Weight Review 20260702

> 本报告只给人工调权复盘证据,不自动修改 scoring.py,不回写 factor_snapshots/results。
> low/high bucket 采用冻结因子值的底部/顶部三分位; pending 或未回填样本只计数,不进入收益统计。
> N 直接展示,不按样本数隐藏结论; evidence_strength 只提示证据厚薄。

- horizon: T+1
- total_snapshots: 250
- evaluated_rows: 208
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
| position_52w_pct | 208 | 0 | -4.082~47.98 | +1.97% | 59.42% | 79.59~102.4 | -1.12% | 44.93% | -3.09% | strong | consider_penalty_for_high_value_or_inverse_weight |
| roe_avg | 208 | 0 | 0.1994~1.884 | +1.53% | 50.72% | 4.212~17.55 | -1.55% | 42.03% | -3.08% | strong | consider_penalty_for_high_value_or_inverse_weight |
| pb_percentile_1y | 208 | 0 | 0~55 | +1.64% | 57.97% | 94.8~99.6 | -0.93% | 46.38% | -2.57% | strong | consider_penalty_for_high_value_or_inverse_weight |
| right_side_score | 208 | 0 | -2~0.5 | +0.82% | 50.72% | 1.5~4 | -1.57% | 37.68% | -2.39% | strong | consider_penalty_for_high_value_or_inverse_weight |
| pe_percentile_1y | 203 | 5 | 0~35.1 | +1.42% | 58.21% | 92.6~99.6 | -0.79% | 47.76% | -2.21% | strong | consider_penalty_for_high_value_or_inverse_weight |
| main_inflow_5d | 208 | 0 | -8.56e+09~-6.55e+08 | -1.03% | 31.88% | 6.055e+06~7.138e+09 | +0.30% | 62.32% | +1.33% | strong | consider_up_weight_for_high_value |
| rsi_14 | 208 | 0 | 12.14~44.18 | +0.70% | 50.72% | 58.7~97.02 | -0.38% | 53.62% | -1.07% | strong | consider_penalty_for_high_value_or_inverse_weight |
| np_yoy | 208 | 0 | -81.97~4.833 | +1.12% | 55.07% | 62.9~2138 | +0.07% | 47.83% | -1.06% | strong | consider_penalty_for_high_value_or_inverse_weight |
| turnover_zscore | 208 | 0 | -1.34~-0.27 | -0.84% | 39.13% | 0.44~2.71 | +0.19% | 46.38% | +1.03% | strong | consider_up_weight_for_high_value |
| position_20d_pct | 208 | 0 | -13.63~29.32 | +0.51% | 43.48% | 63.78~104.7 | -0.06% | 55.07% | -0.57% | strong | watch_no_change |
| inflow_slope | 208 | 0 | -1.528e+09~-5.28e+07 | -0.68% | 42.03% | 2.272e+07~8.807e+08 | -1.14% | 50.72% | -0.46% | strong | watch_no_change |
| volume_ratio_5d | 208 | 0 | 0.1387~0.8248 | +0.58% | 44.93% | 1.005~1.74 | +0.34% | 50.72% | -0.24% | strong | watch_no_change |

## 人工处理规则
- `consider_up_weight_for_high_value`: 高值桶相对低值桶超额更强,可人工复核是否提高该因子正向权重。
- `consider_penalty_for_high_value_or_inverse_weight`: 高值桶明显弱于低值桶,可人工复核是否降低权重或改成反向惩罚。
- `watch_no_change`: 暂无足够方向性证据,保留观察。
- `collect_more`: 缺少可比较样本或字段缺失,继续积累。
- 任何采纳都必须另开 PR,显式说明样本、阈值、改动原因,并保持历史样本 append-only。
