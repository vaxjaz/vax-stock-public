# Research Pipeline V2 — 决策与统计契约

状态：MR1 契约冻结。本文描述稳定边界，不宣称尚未施工的模型已经可用。

## 1. 目标函数

系统不再把每日固定 T+N 数学预测当作研究成果。目标流程固定为：

```text
H_t = asof_join(A_t, B_t, C_t, D_t, E_t, ..., N_t)
C_t = causal_changes(H_<=t)
G_t = group_v(H_t, C_t, market_state_t)
S_t = select_v(G_t, portfolio_constraints_t)
Y_t = forecast_v(S_t, market_state_t)
Action_t = decide(Y_t, portfolio_t, risk_constraints_t)
```

- `A...N` 是可扩展的原子数据维度；新增 E/F/G 不改变框架。
- `causal_changes` 只使用截至决策时点可见的数据，输出 level、slope、acceleration、change-point、anomaly、相对赛道变化。
- `group` 负责把同类状态与市场环境分开；`select` 负责候选排序和弃权；`forecast` 输出可核验的条件分布，不直接等同买卖动作。
- `decide` 单独处理持仓、现金、仓位上限和交易约束，防止“预测正确”被错误翻译为“必须交易”。

## 2. Point-in-time 铁律

每条原子事实至少保存：

| 字段 | 含义 |
|---|---|
| `effective_date` | 数据属于哪个交易日、报告期或经济月份 |
| `available_at` | 当时最早可以合法用于决策的时间 |
| `retrieved_at` | 本系统实际取得数据的时间 |
| `source/source_ref` | 来源和可追溯引用 |
| `revision_id` | 同一事实的公告修订/数据修订身份 |
| `quality` | observed / revised / stale / missing |

回测、回放和实时计算都必须执行 `available_at <= as_of`。缺失、来源过期或关键交易日不一致时输出 `abstain`，不得补 0.5 或中性值。

## 3. 数据集与验证切分

- 主样本：每天全观察池无条件记录，保持无偏截面。
- 盘中 D 线：持仓观察/触发子集，独立存储，不冒充主样本。
- 时间验证：rolling / expanding walk-forward；所有参数只在训练段拟合。
- 相邻交易日重叠标签使用 purge + embargo，避免训练和验证共享未来收益窗口。
- 上市、停牌、涨跌停、调入观察池等 universe 变化按当日真实可交易集合回放，防止幸存者偏差。
- 多因子与多窗口搜索必须报告尝试次数，并使用稳定性、经济显著性和多重检验后的证据，不以单个 p 值或单一窗口命中下结论。

## 4. Benchmark 与 horizon

- 个股预测主 benchmark：对应赛道/行业当日可交易成分等权收益。
- 次 benchmark：中证 800（数据源未接入前标“待验证”，不以沪深 300 静默替代）。
- 绝对收益、主 benchmark 超额、次 benchmark 超额同时保留。
- horizon 属于策略，不再全票机械固定：事件策略可用公告窗口，趋势策略可用持有期/退出规则，风险策略可用次日与短窗。

## 5. 缓存、新鲜度与拐点时效

- 缓存身份必须包含 `input_digest + algorithm_version`；版本或输入改变即失效。
- 市场交易日取数据中的 `trade_date`，不取墙钟日期。
- EOD 的市场级 critical 输入交易日不一致时阻断整批 forecast；单票日线不一致时只对该票 abstain，并从其 D 线任务中排除。报告保留 blocked 原因。
- 公告/预告/快报/财务/股东户数属于事件源，至少每日刷新；旧的 7–30 天 TTL 不得阻止新公告被发现。
- 盘前事件重拉与新 E 维度一起接入；发现新修订时产生新 observation，不覆盖历史版本。
- T 日收盘已出现的可识别拐点，目标是在 T+1 开盘前的 EOD run 中产生；盘前新增公告由盘前 refresh 形成独立 run，不等待下一次 EOD。

## 6. 阶段交付与上线门槛

1. MR1：契约、旧 T+N 降级、事件缓存和 freshness P0。
2. MR2：append-only 原子/因子存储、run manifest、replay/backfill。
3. MR3：E 维度（公告前一致预期、公司指引、价格隐含预期）及盘前刷新。
4. MR4：连续曲线、因果导数、变点和异常检测。
5. MR5–MR7：group、select、forecast 与 walk-forward 评估。
6. MR8：portfolio decision 与专业报告。
7. MR9：shadow run；通过预先冻结的 OOS 门槛后才允许影响生产动作。

所有阶段保留原始数据和旧 baseline，版本前滚不覆盖历史。没有 OOS 证据的结果只能标为 candidate，不得写成 effective。
