# Factor Weight Review 20260727

> 本报告只给人工调权复盘证据,不自动修改 scoring.py,不回写 factor_snapshots/results。
> low/high bucket 采用冻结因子值的底部/顶部三分位; pending 或未回填样本只计数,不进入收益统计。
> N 直接展示,不按样本数隐藏结论; evidence_strength 只提示证据厚薄。

- horizon: T+1
- total_snapshots: 963
- evaluated_rows: 922
- pending_or_unfilled: 41
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
| pb_percentile_1y | 922 | 0 | 0~37.2 | +0.14% | 47.88% | 83.5~99.6 | -1.04% | 42.35% | -1.18% | strong | consider_penalty_for_high_value_or_inverse_weight |
| rsi_14 | 922 | 0 | 7.47~37.56 | +0.05% | 47.88% | 49.97~97.02 | -0.94% | 40.07% | -0.99% | strong | watch_no_change |
| right_side_score | 922 | 0 | -2~0.5 | +0.02% | 49.19% | 1.8~4 | -0.92% | 39.74% | -0.94% | strong | watch_no_change |
| position_52w_pct | 922 | 0 | -4.082~38.58 | +0.04% | 46.58% | 63.57~102.4 | -0.87% | 43.00% | -0.92% | strong | watch_no_change |
| position_20d_pct | 922 | 0 | -13.63~15.4 | -0.01% | 49.51% | 40.93~104.7 | -0.82% | 43.00% | -0.81% | strong | watch_no_change |
| pe_percentile_1y | 900 | 22 | 0~26.8 | -0.09% | 46.67% | 76.2~99.6 | -0.86% | 42.00% | -0.76% | strong | watch_no_change |
| volume_ratio_5d | 922 | 0 | 0.1387~0.8316 | -0.29% | 42.02% | 1.041~1.895 | -0.70% | 42.67% | -0.40% | strong | watch_no_change |
| turnover_zscore | 922 | 0 | -2.34~-0.67 | -0.34% | 43.97% | 0.16~3.98 | -0.61% | 42.35% | -0.28% | strong | watch_no_change |
| np_yoy | 922 | 0 | -81.97~4.833 | -0.35% | 42.35% | 62.9~2138 | -0.57% | 44.30% | -0.22% | strong | watch_no_change |
| roe_avg | 922 | 0 | 0.1994~1.884 | -0.33% | 40.72% | 4.212~17.55 | -0.54% | 45.60% | -0.20% | strong | watch_no_change |
| main_inflow_5d | 922 | 0 | -8.56e+09~-3.25e+08 | -0.81% | 39.74% | 1.953e+08~7.771e+09 | -0.67% | 45.28% | +0.14% | strong | watch_no_change |
| inflow_slope | 922 | 0 | -1.528e+09~-2.48e+07 | -0.72% | 42.67% | 4.258e+07~1.075e+09 | -0.69% | 44.95% | +0.04% | strong | watch_no_change |

## 人工处理规则
- `consider_up_weight_for_high_value`: 高值桶相对低值桶超额更强,可人工复核是否提高该因子正向权重。
- `consider_penalty_for_high_value_or_inverse_weight`: 高值桶明显弱于低值桶,可人工复核是否降低权重或改成反向惩罚。
- `watch_no_change`: 暂无足够方向性证据,保留观察。
- `collect_more`: 缺少可比较样本或字段缺失,继续积累。
- 任何采纳都必须另开 PR,显式说明样本、阈值、改动原因,并保持历史样本 append-only。
