# Factor Weight Review 20260709

> 本报告只给人工调权复盘证据,不自动修改 scoring.py,不回写 factor_snapshots/results。
> low/high bucket 采用冻结因子值的底部/顶部三分位; pending 或未回填样本只计数,不进入收益统计。
> N 直接展示,不按样本数隐藏结论; evidence_strength 只提示证据厚薄。

- horizon: T+1
- total_snapshots: 460
- evaluated_rows: 418
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
| pb_percentile_1y | 418 | 0 | 0~50.6 | +1.05% | 56.83% | 90.9~99.6 | -0.50% | 48.20% | -1.54% | strong | consider_penalty_for_high_value_or_inverse_weight |
| position_20d_pct | 418 | 0 | -13.63~25.14 | +0.89% | 51.80% | 58.88~104.7 | -0.50% | 45.32% | -1.38% | strong | consider_penalty_for_high_value_or_inverse_weight |
| rsi_14 | 418 | 0 | 12.14~44.78 | +0.77% | 53.96% | 57.26~97.02 | -0.43% | 46.76% | -1.20% | strong | consider_penalty_for_high_value_or_inverse_weight |
| position_52w_pct | 418 | 0 | -4.082~48.12 | +0.85% | 50.36% | 73.9~102.4 | -0.23% | 48.92% | -1.08% | strong | consider_penalty_for_high_value_or_inverse_weight |
| pe_percentile_1y | 408 | 10 | 0~37.7 | +0.59% | 54.41% | 86.6~99.6 | -0.24% | 48.53% | -0.82% | strong | watch_no_change |
| main_inflow_5d | 418 | 0 | -8.56e+09~-5.708e+08 | -0.46% | 40.29% | 9.465e+07~7.138e+09 | +0.16% | 54.68% | +0.62% | strong | watch_no_change |
| right_side_score | 418 | 0 | -2~0.5 | +0.22% | 45.32% | 1.5~4 | -0.36% | 45.32% | -0.59% | strong | watch_no_change |
| roe_avg | 418 | 0 | 0.1994~1.884 | +0.43% | 42.45% | 4.212~17.55 | -0.10% | 51.08% | -0.53% | strong | watch_no_change |
| inflow_slope | 418 | 0 | -1.528e+09~-3.586e+07 | +0.02% | 46.76% | 4.29e+07~8.807e+08 | -0.46% | 48.92% | -0.48% | strong | watch_no_change |
| volume_ratio_5d | 418 | 0 | 0.1387~0.8277 | +0.01% | 43.17% | 1.022~1.895 | +0.44% | 49.64% | +0.43% | strong | watch_no_change |
| np_yoy | 418 | 0 | -81.97~4.833 | +0.11% | 45.32% | 62.9~2138 | +0.40% | 53.24% | +0.30% | strong | watch_no_change |
| turnover_zscore | 418 | 0 | -1.95~-0.43 | +0.18% | 50.36% | 0.39~3.86 | +0.11% | 43.88% | -0.06% | strong | watch_no_change |

## 人工处理规则
- `consider_up_weight_for_high_value`: 高值桶相对低值桶超额更强,可人工复核是否提高该因子正向权重。
- `consider_penalty_for_high_value_or_inverse_weight`: 高值桶明显弱于低值桶,可人工复核是否降低权重或改成反向惩罚。
- `watch_no_change`: 暂无足够方向性证据,保留观察。
- `collect_more`: 缺少可比较样本或字段缺失,继续积累。
- 任何采纳都必须另开 PR,显式说明样本、阈值、改动原因,并保持历史样本 append-only。
