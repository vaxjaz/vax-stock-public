# AI 历史概率引擎 v1

## 目标

本引擎不以项目此前逐日积累的 A/B/C/D 证据线为训练地基。它直接从可重建的
多年历史原始数据回答两个问题：

1. 当前 AI 基础设施组合在未来 T+1/T+5/T+20 取得正收益、跑赢沪深300的概率；
2. 在相同 AI 赛道及海外锚状态下，每只 AI 成分取得正收益、跑赢 AI 等权组合的
   概率。

v1 是独立研究入口，不接管 EOD、盘中通知、仓位或交易动作，
`production_eligible=false`。

## 原始数据

| 数据 | 来源 | v1用途 |
|---|---|---|
| A股日线 | Tushare `daily` | OHLCV及交易日 |
| 复权因子 | Tushare `adj_factor` | `adj_close = close × adj_factor`，构造历史收益 |
| 每日指标 | Tushare `daily_basic` | 换手、PE-TTM、PB、市值 |
| 沪深300 | Tushare `index_daily(000300.SH)` | 市场基准 |
| NVDA/SOXX/QQQ/VIX/TNX/DXY | yfinance adjusted history | AI、风险偏好、利率及汇率锚 |

`daily_basic` 缺失不会补中性值；对应因子保持缺失。`daily` 或 `adj_factor`
缺失的股票不能进入复权收益计算，会在数据审计中列明。

## 当前股票池语义

v1 复用 `tracks.ai.AIDC_BASKET`，但明确标注为
`current_constituent_historical_proxy`：

- 当前成分不能冒充历史时点的官方概念成分；
- 新上市股票只从首次存在有效复权收益后进入组合；
- 某日不要求所有当前成分同时存在，只要求至少5只有效成员；
- 每日输出实际成员数和覆盖率。

这解决“新增成员无历史就整日出局”的问题，但没有消除当前成分回溯带来的
幸存者偏差。

## group / select / forecast

### group

因子按经济语义分组，而不是把所有数值使用同一变换：

- AI组合趋势及相对趋势；
- 内部宽度、离散度、波动和回撤；
- 换手与估值；
- NVDA/SOXX 等海外AI锚；
- QQQ/VIX 风险偏好；
- TNX/DXY 宏观锚；
- 个股自身趋势、相对AI强弱、风险、换手和估值。

### select

每个 horizon 分开选择因子：

1. 前瞻标签只用复权K线重建；
2. T+N 标签按 N 个交易日抽取非重叠样本，避免把重叠收益伪装成独立 N；
3. 用按时间切分的秩相关检查符号稳定性；
4. 每个语义因子族最多2个，总计最多6个；
5. 当前值缺失的因子不参与本次预测，不填默认值。

### forecast

在选中因子的稳健标准化空间寻找历史相似状态，以距离加权收益估计概率，并用
固定强度的 Beta 先验向历史基础胜率收缩。输出：

- 正收益/正超额概率及90%区间；
- 期望收益；
- 相似历史收益 P10/P50/P90；
- 历史训练日、非重叠独立日、有效邻居数；
- 选中因子、当前状态和最相似交易日；
- 赛道层 walk-forward Brier score 与相对基础胜率的 skill。

个股层 v1 暂不运行逐票 walk-forward，明确标记
`not_run_for_stock_layer_v1`，不能把赛道层验证结果冒充个股层验证。

## 时间口径

对 A 股 T 日收盘后、T+1 日盘前的预测：

- A股因子使用 T 日已完成收盘；
- 海外锚使用美股 T 日完成交易；
- 标签为从 A股 T 日复权收盘到未来 T+N 收盘的方向，属于方向基线，
  不是宣称可在 T 日收盘成交的收益。

若在美股 T 日尚未收盘时提前运行，输出
`decision_readiness=lagged_anchor_or_run_before_overseas_close`。凌晨5点取得同日
完成锚后重跑会产生新的不可变数据版本，并更新 `latest.json` 指针。

## 落盘与幂等

```text
var/research/ai_historical_probability/
├── datasets/<dataset_digest>/
│   ├── cn_stocks.jsonl
│   ├── benchmark.jsonl
│   ├── anchors.jsonl
│   └── manifest.json
├── forecasts/
│   └── ai_probability_<date>__<model>__<data_digest>__<run_spec>.json
└── latest.json
```

历史数据集和预测文件按内容摘要不可变保存。相同数据和运行参数重跑返回
`already_complete`；上游历史修订会产生新数据摘要和新预测文件，不覆盖旧证据。
`latest.json` 只是当前版本指针。

## VPS 首次运行

凌晨5点、美股同日收盘完成后：

```bash
cd /opt/stock-reportv2/vax-stock-public
set -a
. /etc/vaxstock/vaxstock.env
set +a
PYTHONPATH=src /opt/stock-reportv2/venv/bin/python \
  -m vaxstock.services.ai_probability_refresh \
  --start 20200101 \
  --end YYYYMMDD
```

首次运行需要逐只拉取历史数据；后续相同边界会利用传输缓存和内容寻址数据集。
不触网重算指定数据集：

```bash
PYTHONPATH=src /opt/stock-reportv2/venv/bin/python \
  -m vaxstock.services.ai_probability_refresh \
  --start 20200101 \
  --end YYYYMMDD \
  --dataset-dir var/research/ai_historical_probability/datasets/<digest>
```

## v1 明确未完成

- 历史时点概念成分；
- 海内外头部企业资本开支、自由现金流和债务杠杆慢变量；
- 历史一致预期修正；
- 个股层独立 walk-forward 校准；
- EOD 邮件展示和自动调度。

这些缺口不能用默认值填充，也不妨碍先验证价格、内部结构和市场锚是否提供
稳定概率增量。
