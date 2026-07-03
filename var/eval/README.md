# var/eval 目录说明

本目录保存 MR-Eval 的 B 线数据:全 holdings + watchlist 的无偏每日样本,用于验证因子评分和未来收益/超额表现。

它回答的问题是:

```text
每天所有用户 universe 里的票,当时因子是什么样?
这些因子在 T+1/T+3/T+5/T+10/T+20/T+30 后对应的真实收益和超额表现如何?
```

## 文件作用

| 文件 | 作用 | 来源/写入者 |
|---|---|---|
| `factor_snapshots.jsonl` | 每日全 universe 因子快照。每个交易日每只股票一行,用于防止只记录触发票导致幸存者偏差。 | `services.eval_recorder.record_snapshots` |
| `factor_results.jsonl` | 对 `factor_snapshots` 的未来收益回填结果。 | `services.eval_recorder.backfill`/`record_and_backfill` |
| `layer2_report_<trade_date>.md` | B 线 Layer2 分析报告,按策略档和 `regime|macro_regime` 分桶展示前瞻收益/超额/胜率。 | `research.layer2_eval.run_layer2` |
| `factor_weight_review_<trade_date>.md` | E3 人工调权复盘报告,按冻结因子值 low/high 桶比较未来超额,只给人工 review_action。 | `research.factor_weight_review.run_factor_weight_review` |
| `regime_audit.jsonl` | market_regime 原始输入审计表,每个交易日一行,记录 raw/final、指数涨跌、跌停数和数据源。 | `services.regime_auditor.record_regime_audit` |
| `regime_audit_<trade_date>.md` | 单日 regime 判定说明,用于人工确认当时 regime 是否真实可信。 | `services.regime_auditor.record_regime_audit` |

## 核心字段

### `factor_snapshots.jsonl`

每行是一只股票在一个交易日的冻结快照。

| 字段 | 含义 |
|---|---|
| `schema_version` | 记录结构版本。 |
| `snapshot_ts` | 快照写入时间。 |
| `trade_date` | 因子快照对应的真实交易日。 |
| `code` / `name` | 股票代码和名称。 |
| `group` | `holding` 或 `watchlist`。 |
| `concepts` | 概念标签。 |
| `price_at_snapshot` | 快照时点价格。 |
| `metrics` | 技术、估值、资金、右侧评分等指标。 |
| `metrics.right_side_score` | 当前右侧评分,Layer2 会用它打策略档。 |
| `market.regime` | 当日市场 regime。 |
| `market.macro_regime` | 当日宏观 regime。 |
| `market.ai_track` | AI 赛道择时结果摘要。 |

### `factor_results.jsonl`

每行是某个 `(trade_date, code)` 的未来收益回填结果。

| 字段 | 含义 |
|---|---|
| `trade_date` | 与 `factor_snapshots.trade_date` 对齐的基准日。 |
| `code` | 股票代码。 |
| `ret` | 个股未来收益,按 horizon 存成 dict,如 `{"1": 0.02}` 表示 T+1 收益 2%。 |
| `mkt_ret` | 基准指数未来收益,同样按 horizon 存。 |
| `excess` | 超额收益,即 `ret - mkt_ret`。 |
| `complete` | 当前回填是否完整。 |
| `filled_ts` | 回填写入时间。 |

### `layer2_report_<trade_date>.md`

| 字段/栏目 | 含义 |
|---|---|
| `决策档` | 由 `right_side_score` 镜像打档,如强买入、可考虑介入、观察、回避。 |
| `环境桶` | `market.regime|market.macro_regime`。 |
| `N` | 已回填并参与统计的样本数。 |
| `平均ret` | 桶内个股未来收益均值。 |
| `平均excess` | 桶内超额收益均值。 |
| `胜率(excess>0)` | 超额收益为正的样本占比。 |

### `factor_weight_review_<trade_date>.md`

| 字段/栏目 | 含义 |
|---|---|
| `horizon` | 当前复盘的未来窗口,默认 `T+1`。 |
| `total_snapshots` | 读取到的冻结快照总数。 |
| `evaluated_rows` | 已有对应 horizon 超额结果、可进入统计的样本数。 |
| `pending_or_unfilled` | 尚未回填或缺少该 horizon 的样本数;只计数,不进入收益统计。 |
| `factor` | 被复盘的冻结因子字段,来自 `factor_snapshots.metrics`。 |
| `low_range` / `high_range` | 按因子值排序后的底部/顶部三分位取值区间。 |
| `low_avg_excess` / `high_avg_excess` | 低值桶/高值桶的平均超额收益。 |
| `high-low` | 高值桶平均超额减低值桶平均超额,用于人工判断因子方向。 |
| `evidence_strength` | `thin`/`medium`/`strong`,只提示样本厚薄,不隐藏任何桶。 |
| `review_action` | 人工动作建议,如继续观察、复核是否提高权重、复核是否反向惩罚。 |
### `regime_audit.jsonl` / `regime_audit_<trade_date>.md`

| 字段/栏目 | 含义 |
|---|---|
| `trade_date` | regime 对应的真实交易日。 |
| `raw_regime` | 当日原始判定: 先看跌停数,再看成长指数相对上证强弱。 |
| `smoothed_regime` | 平滑后的最终 `market_regime`; prediction/report 使用这个值。 |
| `reason` | 原始判定触发原因,如 `limit_down_count=60 > 50` 或 `sh - growth_avg >= 1.0%`。 |
| `inputs.limit_down_count` | 当日跌停数,来自 Tushare 全市场 daily 聚合。 |
| `inputs.sh_change_pct` | 上证指数涨跌幅,来自 Tushare `index_daily`。 |
| `inputs.cyb_change_pct` | 创业板指涨跌幅,来自 Tushare `index_daily`。 |
| `inputs.kc50_change_pct` | 科创50涨跌幅,来自 Tushare `index_daily`。 |
| `inputs.growth_avg_change_pct` | `(创业板指 + 科创50) / 2`。 |
| `sources` | 指数和全市场统计的数据源标记;缺失时必须显示待验证,不能臆造。 |

## 使用原则

- B 线是无偏全截面样本,不是盘中触发样本。
- `factor_snapshots/results` 是 append-only 样本地基,不要手工改旧行。
- `layer2_report_*.md` 是可重生成报告,用于看分桶统计,不作为原始事实源。
- `factor_weight_review_*.md` 只给人工调权复盘证据,不自动修改 `scoring.py`。
- `regime_audit.jsonl` 同交易日幂等跳过; `regime_audit_<trade_date>.md` 可重生成覆盖。
- 当前 Layer2 不按样本数屏蔽统计值,N 直接展示;样本厚薄由读者自己判断。
