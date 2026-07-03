# var/forecast 目录说明

本目录保存盘中触发预测,也就是 MR-Eval 的 A 线样本。

它回答的问题是:

```text
盘中某个触发发生时,系统当场怎么看?
```

注意:A 线是触发子集,不是全 universe 样本。全 universe 的无偏样本在 `var/eval`。

## 文件作用

| 文件 | 作用 | 来源/写入者 |
|---|---|---|
| `forecasts.jsonl` | 盘中触发时冻结的结构化预测,包含 T-1 基准、盘中 lite 快照、regime、Codex 结构化判断等。 | `services.forecast_recorder.record_forecast` |

## 核心字段

### `forecasts.jsonl`

每行是一条盘中触发预测。

| 字段 | 含义 |
|---|---|
| `schema_version` | 记录结构版本。 |
| `forecast_ts` | 盘中预测写入时间。 |
| `trade_date` | 盘中触发所属交易日。 |
| `code` | 股票代码。 |
| `trigger_note` | 触发原因/触发说明。 |
| `inputs_ref` | 当时输入引用,用于追溯预测依据。 |
| `inputs_ref.baseline_date` | 使用的 T-1 EOD 基准日。 |
| `inputs_ref.t1_baseline` | 从最新 EOD `claude.json` 读取的该票 T-1 基准。 |
| `inputs_ref.lite_snapshot` | 盘中 lite 行情快照。 |
| `inputs_ref.regime` | 当时市场 regime。 |
| `structured.verdict` | 结构化结论,如确认/否定/观察。 |
| `structured.direction` | 结构化方向判断。 |
| `structured.confidence` | 置信度。 |
| `structured.horizon` | 判断窗口。 |
| `structured.thesis_tags` | 支撑 thesis 的标签。 |
| `structured.falsify_if` | 证伪条件。 |
| `reasoning` | 模型原始推理/摘要。 |
| `falsify_if` | 顶层证伪条件冗余字段,便于快速读取。 |

## 使用原则

- A 线只记录“盘中触发那一刻”的情境样本。
- A 线不能冒充 B 线全样本,否则会有幸存者偏差。
- 回测/复盘时应按 `(trade_date, code)` 和 `var/eval` 的 B 线样本 join,不要混写。
- 如果缺 T-1 基准或 lite 快照,应标待验证,不要补默认中性值。
