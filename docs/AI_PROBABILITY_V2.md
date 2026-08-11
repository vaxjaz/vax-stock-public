# AI 概率趋势模型 v2

## 目标

v2 不预测次日涨跌，也不把 AI 赛道历史上较高的正超额收益基率包装成模型能力。
唯一目标是判断：在交易日 T 收盘时已知的数据条件下，AI 等权组合在 T+20
相对沪深 300 取得正超额收益的概率，是否存在可重复的增量信息。

原始 content-addressed 数据集和 v1 输出均不修改。v2 是平行 challenger。

## group

字段只按预注册合同进入五个语义组：

- `internal_trend`：赛道趋势、相对强弱、宽度和回撤；
- `turning_point`：趋势、相对强弱、宽度、离散度、换手的 5 日一阶变化；
- `crowding_valuation`：离散度、波动、换手 Z 值、PE 历史分位；
- `external_ai_anchor`：NVDA、SOXX 和 QQQ 已完成海外交易日数据；
- `external_macro_risk`：VIX、美国 10 年期收益率和美元指数。

导数只由 T 及以前的值计算。当前数据集没有 point-in-time 的 Capex、负债和一致
预期历史，因此这些字段不进入 v2；缺失不能用中性值代替。

## select

候选合同固定为三套 ridge-logit：

1. 内部状态；
2. 内部状态 + 海外 AI 锚；
3. 全状态 + 拥挤估值 + 宏观风险。

每 20 个交易日重选一次。选择只使用当时已经到期的标签，在三个历史验证块上
比较 Brier score。候选必须同时优于扩展历史正收益率和 756 日滚动正收益率，
且多数验证块为正 skill，否则 `abstain`。

## forecast 与发布闸门

外层每天预测、T+20 到期结算。概率相邻标签存在重叠，因此另外检查 20 个错位
队列和长度 20 的 moving-block bootstrap。

数值概率进入分析师结论前，必须全部通过：

1. 至少 120 个已结算外层预测；
2. Brier skill 同时优于扩展基准和滚动基准；
3. 多数错位队列 skill 为正；
4. 区块自助法 skill 中位数为正。

若 5% 分位也为正，才标记为 robust。任一条件失败，正式输出是
`abstain / no proven edge`，内部概率仅保留用于审计。

## 运行

```bash
PYTHONPATH=src python -m vaxstock.services.ai_probability_backtest_v2 \
  --dataset-dir var/research/ai_historical_probability/datasets/<digest> \
  --horizon 20 \
  --bootstrap-repetitions 1000
```

