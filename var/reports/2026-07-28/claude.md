# 新研究 EOD 20260728

> 本报告已停用旧量化框架、旧因子排名和个股评分模板。底层结构化数据继续落盘，供回放与新算法使用。

## 数据口径

- trade_date: 20260728
- generated_at: 2026-07-29 09:16:22
- freshness: ready
- universe: 持仓5 / 观察池36 / 合计41

## 市场事实

- regime: **panic** | raw=panic | 原因=limit_down_count=62 > 50
- 全市场: 涨2603 / 跌2769 / 涨停71 / 跌停62

### 指数
- 上证指数: 3813.31 (-1.16%)
- 深证成指: 13509.68 (-4.52%)
- 创业板指: 3327.03 (-7.35%)
- 科创50: 1693.48 (-6.33%)
- 沪深300: 4569.52 (-2.83%)

## 新研究链路

- 基础快照: **already_complete** | observations=0, factors=0
- 连续曲线: **already_complete** | outputs=63, candidate_hits=0
- 动态分组: **already_complete** | stocks=41, memberships=2319
- 结果关联: **partial** | samples_ready=0, samples_written=0
- 因子选择: **blocked** | reason=group_outcomes_empty
- 预测: **not_executed**
- 预测核验: **not_executed**

### 事件观测
- state=none | direction=待验证 | breadth=0.0000 | families=0
- 事件字段仅为候选观测，不等于已经验证的交易信号。

## 决策结论

- **ABSTAIN：当前没有通过验证的新算法交易结论。**
- 不展示或回退任何旧评分与旧因子排名，不把候选拐点包装成有效信号。
- research_status: blocked
- blocking_stage: select
- reason: group_outcomes_empty

## 赛道原始状态

- AI算力: available=True | position_ceiling=减档 (单否决, 不加且高位减) | source_date=20260729（与报告交易日不一致）

## 审计边界

- 完整原始数据见同目录 payload.json；机器压缩视图见 claude.json。
- 本报告不因研究链路阻断而回退旧评分系统。
