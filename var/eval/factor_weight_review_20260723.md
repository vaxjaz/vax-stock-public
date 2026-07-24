# Factor Weight Review 20260723

> 本报告只给人工调权复盘证据,不自动修改 scoring.py,不回写 factor_snapshots/results。
> low/high bucket 采用冻结因子值的底部/顶部三分位; pending 或未回填样本只计数,不进入收益统计。
> N 直接展示,不按样本数隐藏结论; evidence_strength 只提示证据厚薄。

- horizon: T+1
- total_snapshots: 880
- evaluated_rows: 838
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
| pb_percentile_1y | 838 | 0 | 0~39 | +0.17% | 48.39% | 86.1~99.6 | -1.20% | 41.22% | -1.37% | strong | consider_penalty_for_high_value_or_inverse_weight |
| right_side_score | 838 | 0 | -2~0.5 | -0.08% | 47.31% | 1.5~4 | -1.11% | 37.63% | -1.02% | strong | consider_penalty_for_high_value_or_inverse_weight |
| rsi_14 | 838 | 0 | 10.19~38.19 | -0.02% | 47.31% | 51.2~97.02 | -0.89% | 40.86% | -0.87% | strong | watch_no_change |
| position_52w_pct | 838 | 0 | -4.082~40.43 | -0.08% | 45.16% | 64.93~102.4 | -0.92% | 42.29% | -0.83% | strong | watch_no_change |
| pe_percentile_1y | 818 | 20 | 0~29.4 | -0.23% | 45.96% | 77.9~99.6 | -0.92% | 41.54% | -0.69% | strong | watch_no_change |
| position_20d_pct | 838 | 0 | -13.63~16.2 | -0.15% | 47.67% | 43.02~104.7 | -0.72% | 44.09% | -0.57% | strong | watch_no_change |
| np_yoy | 838 | 0 | -81.97~4.833 | -0.39% | 41.58% | 62.9~2138 | -0.71% | 43.73% | -0.31% | strong | watch_no_change |
| roe_avg | 838 | 0 | 0.1994~1.884 | -0.37% | 40.14% | 4.212~17.55 | -0.66% | 44.44% | -0.30% | strong | watch_no_change |
| turnover_zscore | 838 | 0 | -2.34~-0.57 | -0.51% | 41.94% | 0.25~3.98 | -0.66% | 42.29% | -0.15% | strong | watch_no_change |
| main_inflow_5d | 838 | 0 | -8.56e+09~-3.621e+08 | -0.81% | 40.14% | 1.759e+08~7.771e+09 | -0.86% | 43.73% | -0.05% | strong | watch_no_change |
| volume_ratio_5d | 838 | 0 | 0.1387~0.8608 | -0.66% | 39.07% | 1.055~1.895 | -0.64% | 42.29% | +0.02% | strong | watch_no_change |
| inflow_slope | 838 | 0 | -1.528e+09~-3.073e+07 | -0.87% | 41.58% | 4.167e+07~1.075e+09 | -0.86% | 43.37% | +0.01% | strong | watch_no_change |

## 人工处理规则
- `consider_up_weight_for_high_value`: 高值桶相对低值桶超额更强,可人工复核是否提高该因子正向权重。
- `consider_penalty_for_high_value_or_inverse_weight`: 高值桶明显弱于低值桶,可人工复核是否降低权重或改成反向惩罚。
- `watch_no_change`: 暂无足够方向性证据,保留观察。
- `collect_more`: 缺少可比较样本或字段缺失,继续积累。
- 任何采纳都必须另开 PR,显式说明样本、阈值、改动原因,并保持历史样本 append-only。
