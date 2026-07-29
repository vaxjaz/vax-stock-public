# AI 外部锚点概率模型 MVP

状态：已接入 Research v2 与 EOD，始终为 shadow evidence，
`production_eligible=false`。

## 目标与边界

MVP 回答两个不同问题，禁止混为一个“看多/看空”：

1. 观察池当日冻结的“AI算力”概念篮子，在 T+1/T+5/T+20
   是否取得正绝对收益；
2. 同一篮子是否跑赢当前可审计基准 `000001.SH`。

它不生成个股目标价、买卖动作、持仓调整或盘中通知。当前基准只是历史
`factor_results.jsonl` 已有的上证指数口径，不是理想的 AI 行业基准。

## F 维数据

`research.global_anchor_dimension` 将 EOD 已经取得的 `payload.us_market`
规范化为 point-in-time F 维事实：

- NVDA、SOXX、QQQ、VIX 的完成交易日收盘、前收盘和单日收益；
- 四个单锚方向；
- NVDA/SOXX/QQQ 的多数方向。

来源继续使用现有 `sources.us_market`/yfinance 链路，不新增密钥和网络请求。
yfinance 没有权威发布时间，因此 `available_at` 保守使用系统首次取得时刻。
缺失、日期错误或收益不一致一律显式记录，不填中性值。

完成的美股 T 日收盘只能作为 A 股 T+1 开盘前上下文，不能伪装成 A 股
T 日收盘时可执行的信息。

## group 与 select

- F 维是市场上下文，不参与股票横截面排序。
- `contextual_group_v3` 将五个锚状态写入每只股票的
  `selection_context`。
- `walk_forward_group_spread_v4` 只允许锚条件附着到预登记且概念匹配的
  赛道相对轴，避免把相关锚点与所有股票因子做笛卡尔积。
- NVDA/SOXX/QQQ 高度相关，MVP 不把单锚概率相乘；多数方向是主条件，
  单锚只作边际证据。

## 概率估计

`research.anchor_trend_forecast`：

- 每个交易日是一个独立样本，不把同日多只股票当成多个独立日期；
- 使用当日 point-in-time “AI算力”成员，等权计算篮子收益；
- 只要目标 horizon 任一成员结果缺失，该交易日整体剔除并保留缺失清单；
- 总体概率使用 `Beta(1,1)`，条件概率以固定强度 5 向总体概率收缩；
- 输出近似 90% 后验区间、基础样本 N、条件样本 N 与完整性审计；
- 条件 N 小于 5 时保留原始概率估计，但方向必须 `ABSTAIN`；
- 所有阈值均为预登记 MVP guardrail，不宣称已经 effective 或完成 OOS 校准。

不可变审计文件：

```text
var/research/anchor_forecasts/
  anchor_trend_forecast_<trade_date>__anchor_ai_track_probability_v1.json
```

同一交易日重跑使用已冻结 F 因子的 `calculated_at`，不读取重跑墙钟作为
decision time；相同输入返回 `already_complete`，内容变化则报不可变冲突。

## EOD 顺序

```text
snapshot
  → global anchor
  → curve
  → contextual group
  → group outcome
  → anchor probability forecast
  → walk-forward select
  → conditional group forecast
  → evaluation
```

外部锚与锚概率任一失败只标记 shadow stage 失败，不阻断原 Research v2
链路，也不触碰持仓和盘中任务。

## 历史重放

部署后，先把旧报告中的外部市场事实回放，再重建新版本 group/select：

```bash
PYTHONPATH=src python -m vaxstock.services.global_anchor_refresh \
  --reports-dir var/reports --research-dir var/research
PYTHONPATH=src python -m vaxstock.services.group_refresh \
  --replay --output-dir var/research
PYTHONPATH=src python -m vaxstock.services.group_outcome_refresh
PYTHONPATH=src python -m vaxstock.services.select_refresh \
  --trade-date YYYYMMDD
PYTHONPATH=src python -m vaxstock.services.anchor_forecast_refresh \
  --trade-date YYYYMMDD
```

这些步骤不修改 `var/reports`、`factor_snapshots.jsonl` 或
`factor_results.jsonl`；Research v2 原始事实 append-only，算法升级写新
factor/select/forecast 版本。

## 2026-07-28 隔离 replay 验收基线

仓库现有真实数据隔离重放得到：

- 24 个报告交易日、24 个 F 维 run，0 个阻断；
- T+1 完整独立日 23，当前多数方向条件 N=12；
- T+5 完整独立日 19，当前多数方向条件 N=9；
- T+20 完整独立日 4，当前多数方向条件 N=1，因此方向强制
  `ABSTAIN`。

该结果只证明数据、时点、动态成分与估计链路可工作；T+1/T+5 当前概率仍为
样本内、未完成 OOS 校准的候选证据，不能据此宣布锚点 effective。

