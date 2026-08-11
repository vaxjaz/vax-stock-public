# 新研究 EOD 20260731

> 本报告已停用旧量化框架、旧因子排名和个股评分模板。底层结构化数据继续落盘，供回放与新算法使用。

## 数据口径

- trade_date: 20260731
- generated_at: 2026-08-01 05:00:12
- freshness: ready
- universe: 持仓5 / 观察池36 / 合计41

## 市场事实

- regime: **panic** | raw=momentum | 原因=growth_avg - sh = 2.30% >= 2.0%
- 全市场: 涨4691 / 跌728 / 涨停112 / 跌停0

### 指数
- 上证指数: 3832.26 (0.72%)
- 深证成指: 13578.93 (2.21%)
- 创业板指: 3343.96 (3.06%)
- 科创50: 1635.96 (2.99%)
- 沪深300: 4588.20 (0.85%)

## 新研究链路

- 基础快照: **written** | observations=125, factors=2214
- 外部锚点时入库: **written** | anchors=4, equity_majority_direction=up
- 连续曲线: **written** | outputs=63, candidate_hits=0
- 动态分组: **written** | stocks=41, memberships=2344
- 结果关联: **written** | samples_ready=14656, samples_written=1062
- AI锚概率预测: **estimated**
- 因子选择: **abstain** | factor_series_tested=19, factor_series_total=19, candidate_tests=2074
- 预测: **abstain**
- 预测核验: **written** | pending_forecasts=0

### 事件观测
- state=none | direction=待验证 | breadth=0.0000 | families=0
- 事件字段仅为候选观测，不等于已经验证的交易信号。

### AI外部锚概率（shadow）

| 周期 | 绝对方向 | 上涨概率 | 相对方向 | 正超额概率 | 条件样本N | 证据等级 |
|---|---|---:|---|---:|---:|---|
| T+1 | down | 26.9% | negative_excess | 41.7% | 11 | estimated_not_oos_validated |
| T+5 | down | 10.2% | negative_excess | 11.5% | 11 | estimated_not_oos_validated |
| T+20 | ABSTAIN | 6.9% | ABSTAIN | 6.9% | 3 | sparse_estimate |

- 同时显示观察池“AI算力”概念篮子的绝对涨跌概率与相对上证指数的超额概率；上证指数只是当前可审计旧基准，不是理想行业基准。
- 概率使用小样本收缩估计，尚未经过独立样本外校准；不构成个股价格目标或持仓动作。

## 决策结论

- **ABSTAIN：当前没有通过验证的新算法交易结论。**
- 不展示或回退任何旧评分与旧因子排名，不把候选拐点包装成有效信号。
- research_status: abstain
- reason: no_production_eligible_forecast

## 赛道原始状态

- AI算力: available=True | position_ceiling=减档 (单否决, 不加且高位减) | source_date=20260801（与报告交易日不一致）

## 审计边界

- 完整原始数据见同目录 payload.json；机器压缩视图见 claude.json。
- 本报告不因研究链路阻断而回退旧评分系统。
