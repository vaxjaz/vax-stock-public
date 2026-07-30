# AI T+N 逐交易日回测

## 目的

`T+N` 是预测期限，不是回测采样间隔。完整回测在每个符合训练条件的
历史交易日生成一次预测，并在对应的 `T+N` 交易日结算结果。

原始历史数据集只读。回测输出按数据摘要和运行参数内容寻址，不覆盖原始
数据或既有预测。

## 统计口径

- 日度连续账本保留全部预测，用于概率校准、状态变化和路径审计；
- 相邻日的 T+N 标签相互重叠，日度行数不能冒充独立样本数；
- 全部预测按交易日序号拆成 N 个错位队列；
- 每个队列内部相邻预测相隔 N 个交易日，前瞻收益区间不重叠；
- N 个队列用于检查起始相位敏感性，其样本数也不能相加后称为独立 N；
- 另用长度为 N 的 moving-block bootstrap 估计重叠标签下的统计区间。

旧的 `walk_forward_validate` 只保留一个错位相位且最多取 60 点，仅作为
历史预测文件的兼容诊断，不再用于判断模型是否有效。

## 运行

```bash
PYTHONPATH=src python -m vaxstock.services.ai_probability_backtest \
  --dataset-dir var/research/ai_historical_probability/datasets/<digest> \
  --horizon 20 \
  --target-kind excess \
  --bootstrap-repetitions 1000
```

输出：

```text
var/research/ai_historical_probability/backtests/
└── ai_daily_T20_excess__<model>__<dataset>__<run_spec>.json
```

主要字段：

- `rows`：逐交易日预测、到期结果、因子和近邻审计；
- `overall_daily_dependent_metrics`：全日度描述统计，明确存在标签重叠；
- `offset_cohorts`：N 个错位队列；
- `cohort_stability`：各起始相位的 Brier skill 稳定性；
- `probability_calibration`：预测概率与真实发生率；
- `moving_block_bootstrap`：重叠标签下的区块自助法区间；
- `by_year`：逐年稳定性。

