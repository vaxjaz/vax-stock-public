# Factor Weight Review 20260722

> 本报告只给人工调权复盘证据,不自动修改 scoring.py,不回写 factor_snapshots/results。
> low/high bucket 采用冻结因子值的底部/顶部三分位; pending 或未回填样本只计数,不进入收益统计。
> N 直接展示,不按样本数隐藏结论; evidence_strength 只提示证据厚薄。

- horizon: T+1
- total_snapshots: 838
- evaluated_rows: 796
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
| pb_percentile_1y | 796 | 0 | 0~40.3 | +0.22% | 50.19% | 86.6~99.6 | -1.27% | 40.75% | -1.50% | strong | consider_penalty_for_high_value_or_inverse_weight |
| right_side_score | 796 | 0 | -2~0.5 | -0.11% | 46.79% | 1.5~4 | -1.16% | 38.87% | -1.05% | strong | consider_penalty_for_high_value_or_inverse_weight |
| position_52w_pct | 796 | 0 | -4.082~41.46 | -0.08% | 46.42% | 65.8~102.4 | -0.90% | 43.02% | -0.81% | strong | watch_no_change |
| rsi_14 | 796 | 0 | 10.19~38.51 | -0.12% | 47.92% | 51.71~97.02 | -0.88% | 41.89% | -0.76% | strong | watch_no_change |
| pe_percentile_1y | 777 | 19 | 0~29.9 | -0.23% | 48.26% | 78.8~99.6 | -0.85% | 42.47% | -0.63% | strong | watch_no_change |
| position_20d_pct | 796 | 0 | -13.63~16.34 | -0.10% | 49.06% | 44.43~104.7 | -0.71% | 45.28% | -0.61% | strong | watch_no_change |
| np_yoy | 796 | 0 | -81.97~4.833 | -0.36% | 42.26% | 62.9~2138 | -0.65% | 44.91% | -0.29% | strong | watch_no_change |
| roe_avg | 796 | 0 | 0.1994~1.884 | -0.37% | 40.75% | 4.212~17.55 | -0.64% | 44.91% | -0.27% | strong | watch_no_change |
| main_inflow_5d | 796 | 0 | -8.56e+09~-3.729e+08 | -0.85% | 39.62% | 1.51e+08~7.771e+09 | -0.74% | 45.28% | +0.11% | strong | watch_no_change |
| volume_ratio_5d | 796 | 0 | 0.1387~0.864 | -0.68% | 40.00% | 1.059~1.895 | -0.59% | 42.64% | +0.10% | strong | watch_no_change |
| turnover_zscore | 796 | 0 | -2.34~-0.55 | -0.56% | 43.40% | 0.27~3.98 | -0.62% | 43.02% | -0.07% | strong | watch_no_change |
| inflow_slope | 796 | 0 | -1.528e+09~-3.215e+07 | -0.90% | 41.51% | 4.067e+07~1.075e+09 | -0.88% | 44.15% | +0.02% | strong | watch_no_change |

## 人工处理规则
- `consider_up_weight_for_high_value`: 高值桶相对低值桶超额更强,可人工复核是否提高该因子正向权重。
- `consider_penalty_for_high_value_or_inverse_weight`: 高值桶明显弱于低值桶,可人工复核是否降低权重或改成反向惩罚。
- `watch_no_change`: 暂无足够方向性证据,保留观察。
- `collect_more`: 缺少可比较样本或字段缺失,继续积累。
- 任何采纳都必须另开 PR,显式说明样本、阈值、改动原因,并保持历史样本 append-only。
