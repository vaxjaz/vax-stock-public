# Factor Weight Review 20260708

> 本报告只给人工调权复盘证据,不自动修改 scoring.py,不回写 factor_snapshots/results。
> low/high bucket 采用冻结因子值的底部/顶部三分位; pending 或未回填样本只计数,不进入收益统计。
> N 直接展示,不按样本数隐藏结论; evidence_strength 只提示证据厚薄。

- horizon: T+1
- total_snapshots: 418
- evaluated_rows: 376
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
| pb_percentile_1y | 376 | 0 | 0~52.8 | +0.99% | 55.20% | 91.8~99.6 | -0.79% | 46.40% | -1.78% | strong | consider_penalty_for_high_value_or_inverse_weight |
| position_52w_pct | 376 | 0 | -4.082~49.25 | +0.84% | 50.40% | 74.44~102.4 | -0.65% | 45.60% | -1.49% | strong | consider_penalty_for_high_value_or_inverse_weight |
| pe_percentile_1y | 367 | 9 | 0~38.1 | +0.53% | 53.28% | 87.4~99.6 | -0.83% | 44.26% | -1.37% | strong | consider_penalty_for_high_value_or_inverse_weight |
| rsi_14 | 376 | 0 | 12.14~45.67 | +0.57% | 50.40% | 57.98~97.02 | -0.68% | 45.60% | -1.25% | strong | consider_penalty_for_high_value_or_inverse_weight |
| roe_avg | 376 | 0 | 0.1994~1.884 | +0.30% | 42.40% | 4.212~17.55 | -0.82% | 45.60% | -1.12% | strong | consider_penalty_for_high_value_or_inverse_weight |
| inflow_slope | 376 | 0 | -1.528e+09~-3.722e+07 | -0.28% | 44.80% | 4.244e+07~8.807e+08 | -1.05% | 44.80% | -0.78% | strong | watch_no_change |
| position_20d_pct | 376 | 0 | -13.63~28.46 | +0.18% | 45.60% | 60.85~104.7 | -0.58% | 44.00% | -0.76% | strong | watch_no_change |
| right_side_score | 376 | 0 | -2~0.5 | +0.06% | 44.00% | 1.5~4 | -0.67% | 44.00% | -0.73% | strong | watch_no_change |
| volume_ratio_5d | 376 | 0 | 0.1387~0.8329 | -0.31% | 40.80% | 1.037~1.895 | +0.27% | 48.00% | +0.58% | strong | watch_no_change |
| turnover_zscore | 376 | 0 | -1.79~-0.4 | -0.56% | 44.00% | 0.44~3.86 | -0.27% | 41.60% | +0.29% | strong | watch_no_change |
| main_inflow_5d | 376 | 0 | -8.56e+09~-6.049e+08 | -0.55% | 39.20% | 8.859e+07~7.138e+09 | -0.48% | 50.40% | +0.07% | strong | watch_no_change |
| np_yoy | 376 | 0 | -81.97~4.833 | +0.09% | 45.60% | 62.9~2138 | +0.03% | 49.60% | -0.06% | strong | watch_no_change |

## 人工处理规则
- `consider_up_weight_for_high_value`: 高值桶相对低值桶超额更强,可人工复核是否提高该因子正向权重。
- `consider_penalty_for_high_value_or_inverse_weight`: 高值桶明显弱于低值桶,可人工复核是否降低权重或改成反向惩罚。
- `watch_no_change`: 暂无足够方向性证据,保留观察。
- `collect_more`: 缺少可比较样本或字段缺失,继续积累。
- 任何采纳都必须另开 PR,显式说明样本、阈值、改动原因,并保持历史样本 append-only。
