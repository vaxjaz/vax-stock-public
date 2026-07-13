# Factor Weight Review 20260710

> 本报告只给人工调权复盘证据,不自动修改 scoring.py,不回写 factor_snapshots/results。
> low/high bucket 采用冻结因子值的底部/顶部三分位; pending 或未回填样本只计数,不进入收益统计。
> N 直接展示,不按样本数隐藏结论; evidence_strength 只提示证据厚薄。

- horizon: T+1
- total_snapshots: 502
- evaluated_rows: 460
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
| pb_percentile_1y | 460 | 0 | 0~50.6 | +1.11% | 59.48% | 90.5~99.6 | -0.79% | 45.10% | -1.90% | strong | consider_penalty_for_high_value_or_inverse_weight |
| position_52w_pct | 460 | 0 | -4.082~48.07 | +1.04% | 54.90% | 73.83~102.4 | -0.53% | 46.41% | -1.57% | strong | consider_penalty_for_high_value_or_inverse_weight |
| position_20d_pct | 460 | 0 | -13.63~25.39 | +0.82% | 52.29% | 58.67~104.7 | -0.66% | 44.44% | -1.48% | strong | consider_penalty_for_high_value_or_inverse_weight |
| pe_percentile_1y | 449 | 11 | 0~36.8 | +0.59% | 55.70% | 86.6~99.6 | -0.59% | 44.97% | -1.19% | strong | consider_penalty_for_high_value_or_inverse_weight |
| roe_avg | 460 | 0 | 0.1994~1.884 | +0.53% | 45.10% | 4.212~17.55 | -0.57% | 47.06% | -1.11% | strong | consider_penalty_for_high_value_or_inverse_weight |
| rsi_14 | 460 | 0 | 12.14~44.06 | +0.56% | 54.25% | 56.91~97.02 | -0.41% | 46.41% | -0.98% | strong | watch_no_change |
| inflow_slope | 460 | 0 | -1.528e+09~-3.364e+07 | +0.21% | 50.33% | 4.783e+07~1.075e+09 | -0.76% | 45.75% | -0.96% | strong | watch_no_change |
| right_side_score | 460 | 0 | -2~0.5 | +0.18% | 46.41% | 1.5~4 | -0.68% | 43.14% | -0.86% | strong | watch_no_change |
| turnover_zscore | 460 | 0 | -1.95~-0.44 | +0.12% | 50.33% | 0.39~3.86 | -0.17% | 43.14% | -0.29% | strong | watch_no_change |
| np_yoy | 460 | 0 | -81.97~4.833 | +0.25% | 48.37% | 62.9~2138 | -0.00% | 49.67% | -0.25% | strong | watch_no_change |
| volume_ratio_5d | 460 | 0 | 0.1387~0.8329 | +0.10% | 45.75% | 1.037~1.895 | -0.13% | 45.10% | -0.23% | strong | watch_no_change |
| main_inflow_5d | 460 | 0 | -8.56e+09~-4.999e+08 | -0.31% | 43.14% | 1.434e+08~7.771e+09 | -0.52% | 48.37% | -0.21% | strong | watch_no_change |

## 人工处理规则
- `consider_up_weight_for_high_value`: 高值桶相对低值桶超额更强,可人工复核是否提高该因子正向权重。
- `consider_penalty_for_high_value_or_inverse_weight`: 高值桶明显弱于低值桶,可人工复核是否降低权重或改成反向惩罚。
- `watch_no_change`: 暂无足够方向性证据,保留观察。
- `collect_more`: 缺少可比较样本或字段缺失,继续积累。
- 任何采纳都必须另开 PR,显式说明样本、阈值、改动原因,并保持历史样本 append-only。
