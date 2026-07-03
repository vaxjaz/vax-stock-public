# var/reports 目录说明

本目录保存每日 EOD 报告三件套。每个交易日一个子目录:

```text
var/reports/<YYYY-MM-DD>/
  payload.json
  claude.json
  claude.md
```

交易日以 EOD payload 里的真实 `market_overview.trade_date` 为准,不是运行机器的当天日期。EOD 正常由 systemd timer 在次日 05:00 跑,所以目录名通常是上一交易日。

## 文件作用

| 文件 | 作用 | 来源/写入者 |
|---|---|---|
| `payload.json` | EOD 原始全量 payload,是报告三件套里的 SSOT。后续 replay、排查字段、重渲染都优先看它。 | `vaxstock.report.store.store_report`,输入来自 `services.collect.collect_payload` |
| `claude.json` | 压缩后的结构化数据,给报告渲染、盘中 T-1 基准注入使用。E4-6 起会带 `prediction_summary`。字段比 `payload.json` 少,但更适合人读/模型读。 | `report.claude_md.compact_for_claude` 后由 `services.eod` 注入摘要,再由 `store_report` 写入 |
| `claude.md` | 人读 Markdown 报告,也是邮件附件里的完整报告。E4-6 起包含“昨日预测核验”小节。 | `report.claude_md.build_claude_markdown` 后由 `store_report` 写入 |

## 核心字段

### `payload.json`

| 字段 | 含义 |
|---|---|
| `generated_at` | 报告生成时刻,只表示程序运行时间,不作为交易日基准。 |
| `data_sources` | 本次报告使用的数据源状态。 |
| `indices` | 指数快照。 |
| `stocks` | 持仓和观察池个股全量数据。 |
| `market_overview.trade_date` | 本次 EOD 报告的真实交易日锚点。 |
| `market_regime` | 市场 regime 结论,如 `momentum`/`value`/`panic`。 |
| `macro` | 宏观 7 维 regime 相关数据和结论。 |
| `us_market` | 美股参考数据,用于 AI 赛道择时等口径。 |
| `tracks` | 赛道纵切结果,如 AI 赛道。 |

### `payload.json.stocks[]`

| 字段 | 含义 |
|---|---|
| `group` | `holding` 或 `watchlist`。 |
| `code` / `configured_name` | 股票代码和配置里的名称。 |
| `concepts` | 概念标签。 |
| `realtime` | 当次采集的行情快照。 |
| `metrics` | 技术、估值、资金、评分等计算结果。 |
| `forecast` | 个股动作建议/评分相关结构。 |
| `history_tail` | 最近 K 线尾部数据,用于追溯指标。 |

### `claude.json`

| 字段 | 含义 |
|---|---|
| `analysis_instruction` | 给报告/模型的分析要求。 |
| `market_overview` | 压缩后的市场概览。 |
| `market_regime` | 当前市场 regime。 |
| `stocks` | 压缩后的个股列表,盘中 T-1 基准读取主要使用这里。 |
| `prediction_summary` | target 交易日 EOD Prediction 核验摘要:预测数、已核验、pending、平均超额、正超额率、action/direction 命中。 |
| `stocks[].right_side_score` | 右侧评分,用于 EOD 分析和盘中基准引用。 |
| `stocks[].price` / `change_pct` | 个股价格与涨跌幅快照。 |

## 使用原则

- 查最完整事实:先看 `payload.json`。
- 查盘中 T-1 基准或轻量结构:看 `claude.json`。
- 人工复盘/邮件附件:看 `claude.md`。
- 同一交易日重跑 EOD 会覆盖本目录三件套;它们是报告产物,不是 append-only 样本。
