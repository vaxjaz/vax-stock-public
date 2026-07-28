# Research Pipeline V2 — 决策与统计契约

状态：MR5 point-in-time 多视角 group 与历史重放已实现；select/forecast 尚未施工。本文描述稳定边界，
不宣称尚未施工或未经样本检验的模型已经可用。

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
3. MR3（已实现）：E 维度（公告前卖方预期、公司业绩预告、价格相对卖方估值）
   及盘前刷新。
4. MR4（已实现）：连续曲线、因果导数、变点和异常候选检测。
5. MR5（已实现）：label-free 多视角 group、薄样本/缺失状态与历史重放。
6. MR6–MR7：select、forecast 与 walk-forward 评估。
7. MR8：portfolio decision 与专业报告。
8. MR9：shadow run；通过预先冻结的 OOS 门槛后才允许影响生产动作。

所有阶段保留原始数据和旧 baseline，版本前滚不覆盖历史。没有 OOS 证据的结果只能标为 candidate，不得写成 effective。

## 7. MR2 已实现：存储、版本身份与历史回放

MR2 不替换现有 `var/eval/factor_snapshots.jsonl` 和
`factor_results.jsonl`。这两个文件继续服务当前报告、D 线和旧评估读取方；
Research v2 作为并行数据层积累，尚不直接改变交易动作。

| 路径 | 内容 | 不变量 |
|---|---|---|
| `var/research/observations.jsonl` | 原子来源事实；旧宽表迁移时保留为可追溯的原始 snapshot bundle | append-only；同 observation identity 改值必须换 revision |
| `var/research/factor_values/YYYYMMDD.jsonl` | 按交易日分区的长表因子 | append-only；`factor_id + factor_version + input_digest` 冻结身份 |
| `var/research/run_manifests.jsonl` | live/replay/backtest 的输入及算法版本身份 | 最后写入，作为一次 run 完成标记 |

写入顺序固定为 observations → factors → manifest。重试会补齐中断前已经写入
的前两层，manifest 只在全部校验通过后追加。同一身份、同一版本若出现不同值，
系统报冲突，不允许静默覆盖。新增历史因子必须使用新的 `factor_version`，旧值保留。

旧快照的迁移只保留现有字段和值，不推断 A/B/C/D 或未来 E/F/G 的经济含义。
旧 `snapshot_ts` 是系统捕获时刻，不是供应商原始发布时间；无时区的历史时间按本
项目交易时区 `Asia/Shanghai` 解释，并在 manifest 中显式记录该迁移规则。

全量历史回放命令：

```bash
PYTHONPATH=src python -m vaxstock.research.legacy_snapshot_replay
```

可用 `--from-date YYYYMMDD --to-date YYYYMMDD` 限定范围，或用
`--output-dir` 写入隔离目录验证。回放不修改 legacy 文件；同输入重复执行结果为
`already_complete`。EOD live 流程在旧 B 线写完后同步追加当天 Research v2 run。

当前能力边界：MR2 已解决“数据能否按时点、版本、输入重放”的问题；尚未声明任何
因子 effective，也尚未执行 `group/select/forecast`。这些字段在 ingestion manifest
中明确写为 `not_executed`，防止把数据施工误报成策略有效性。

## 8. MR3 已实现：E 维度预期事实与盘前快照

盘前服务 `vaxstock.services.expectation_refresh` 在交易日 08:35 运行，目标交易日和
前一交易日均由 `tushare.trade_cal` 验证。任务在开始或全部采集完成时达到 09:25
后都不会落盘；所有输入使用实际完成时刻作为 `retrieved_at`，不能把慢请求伪装成
更早可见的数据。

已接入的官方来源：

| 来源 | 原始事实 | 完整性规则 |
|---|---|---|
| `tushare.report_rc` | 卖方逐报告 EPS、净利润、报告内 PE、机构、预测期 | 必须证明全市场、完整分页、覆盖目标日前 90 个完整日历日；否则只记状态和原始行，不生成卖方一致预期 |
| `tushare.forecast` | 单股业绩预告净利润上下限及公告日 | 按观察池逐股精确拉取；来源失败与真实空集分开记录；首次系统取到的时刻作为保守 `available_at` |
| `tushare.daily_basic` | 前一交易日收盘价、PE TTM、总股本、总市值 | 精确指定 `trade_date`；代码、日期或字段不匹配时不生成价格相对因子 |

E 维候选因子只做确定性变换：

- 同一预测期、同一机构只取 90 日窗口内最新报告；机构同日多报告先取机构内中位数，
  再计算跨机构中位数，并同时保存机构数和报告行数。
- 公司预告中值严格按
  `(net_profit_min + net_profit_max) / 2` 计算，单位保持为万元。
- 公告前预期只使用 `report_date < ann_date` 且 `available_at` 早于公告日零点的
  卖方净利润预测，比较双方同为万元的净利润，避免把当前总股本换算的 EPS 冒充
  公司指引。两接口的官方字段均标为“净利润（万元）”，但会计口径是否完全等价仍
  属供应商定义，manifest 显式保留该限制，不能把候选差值直接称为业绩超预期。
- 价格层使用前一交易日收盘价计算
  `current_forward_pe = close / seller_consensus_eps`，并与卖方报告内 PE 中位数比较。
  `eps_required_at_seller_reported_pe_median` 的含义仅为“维持卖方报告 PE 中位数所需
  EPS”，不是独立模型推导出的市场隐含 EPS。

`report_rc.create_time` 是 Tushare 数据更新时间，存在时作为保守可见时点；缺失时
退化为报告日 23:59:59（中国时区）。所有因子都绑定原始 observation ID、查询完整性
状态和版本。MR3 仍将 `group/select/forecast` 写为 `not_executed`，不会改变当前报告、
盘中任务、评分权重或交易动作；是否 effective 必须由后续 walk-forward/OOS 统计证明。

## 9. MR4 已实现：因果曲线、赛道向量与候选事件

`research.causal_curve` 只处理显式登记的连续因子。新增一个数值字段不会自动进入
曲线计算；必须先审阅其单位和经济含义，再前滚
`continuous_factor_registry` 版本。计算使用交易日序号而非自然日：

- 3 交易日中位数平滑；
- 最近/此前两个互不重叠的 5 交易日 Theil–Sen 斜率及斜率差；
- 仅用历史窗口拟合的单步趋势残差和 MAD 异常分数；
- 剔除既有线性趋势后的 5×5 残差位移和持续度；
- 缺少窗口或稳健尺度时写明 `unavailable` / zero-scale 状态，不填中性值。

曲线结果按实体打包为向量：每只股票每日一条 `stock_curve_vector`；每个赛道每日
一条 `track_aggregate_vector` 和一条 `track_curve_vector`。赛道中位数只在该因子
当日至少有 3 个成员时生成，单票标签不会冒充赛道。当前向量只保存有限滚动状态，
并优先引用“上一交易日曲线向量 + 当日基础因子”；首次或断档时引用完整可见窗口。
因此依赖链仍能递归追溯到原始 observation，同时避免逐因子重复保存整段引用。

所有阈值均只产生 `candidate_not_validated` 候选特征。它们不进入盘中通知、不修改
评分、不执行 `group/select/forecast`，也不代表因子 effective。当前 22 个交易日只足以
验证时点、重放、幂等和数据形状；阈值有效性必须由后续 walk-forward/OOS 统计决定。

EOD 在当天 Research v2 基础快照后计算曲线；盘前 E 维刷新后也立即计算，因此新公告
不会等待下一次 EOD。历史引导命令：

```bash
PYTHONPATH=src python -m vaxstock.research.legacy_snapshot_replay
PYTHONPATH=src python -m vaxstock.services.curve_refresh --replay
```

第二条命令支持 `--from-date/--to-date/--output-dir`，按交易日顺序运行；相同输入重跑
不会追加重复 factor 或 manifest。非原生时点的晚到历史回填不会混入当时曲线；
`mode=live` 也只接受目标交易日当天或下一自然日的计算时刻，迟到手工运行会明确阻断。

## 10. MR5 已实现：label-free 多视角 group

`research.contextual_group` 不读取 `factor_results.jsonl`、未来收益或任何结果标签。
它只使用决策时点已经可见的 Research v2 observation/factor，将每只股票映射到彼此独立的
状态轴：

- 市场轴：当时可见的 `market.regime` 与 `market.macro_regime`；缺失时不产生组身份。
- 横截面轴：在当日完整用户观察池内，对已登记连续因子使用并列值共享中间秩的三分位分组。
  默认至少 9 个有效值、至少 3 个不同值；不足时写明 unavailable，不强制切桶。
- 股票曲线轴：最近斜率、加速度、turning/anomaly/change-point 候选状态。检测窗口未成熟时
  为 `null`；成熟但未触发时为显式控制状态 `none`，两者不可混。
- 赛道轴：成员关系取当时最新可见版本；少于 3 个当前成员标为 `thin_track`。只有已形成
  赛道中位数/曲线的因子，才生成股票相对赛道 level/slope 状态。

当前赛道成员来源是每日冻结的用户观察池 `concepts` 标签，不是官方行业指数的历史成分。
因此 `track_aggregate_vector` 的含义是“当前观察池内同标签股票中位数”，不能冒充行业
benchmark；将来接入官方 point-in-time 成分时必须新增 source/factor/group version。

这些轴不会在 group 阶段被拼成一个高维 cluster。后续 select 可以在训练窗内检验有限交叉，
但必须报告独立交易日数、多重尝试次数和 OOS 表现。`holding/watchlist` 是用户组合决策的
内生结果，只作为审计字段保存，不进入统计组，避免把历史持仓选择误当成预测因子。

group 输出仍写入 `factor_values/YYYYMMDD.jsonl`：

- 每日一个 `group_context_vector`：市场状态、横截面协议、赛道覆盖及状态向量字段顺序。
- 每票一个 `stock_group_vector`：该票的横截面桶、股票曲线状态向量、可用的相对赛道状态。

为控制长期存储，向量保存可审计的 `(axis, state, series_id, concept)` 状态元组，不在每个
位置重复 64 字节摘要。需要 join key 时由
`contextual_group.materialize_group_id` 按 manifest 中冻结的 SHA-256 协议确定性生成。
现有 22 日/922 票真实历史重放形成 944 条 group 向量；向量化后约 11.5 MB，相比首版
重复展开约 56.9 MB 降低约 80%。这只是工程与时点正确性验证，不是有效性结论。

历史重放顺序：

```bash
PYTHONPATH=src python -m vaxstock.research.legacy_snapshot_replay
PYTHONPATH=src python -m vaxstock.services.curve_refresh --replay
PYTHONPATH=src python -m vaxstock.services.group_refresh --replay
```

三步均幂等。EOD 和盘前 E 维刷新在曲线落盘后立即运行 group，因此不会因报告缓存等待到
下一个交易日；如果市场/成员/因子时点证据不完整，当前 run 阻断或局部 unavailable，
不会回填中性组。

## 11. MR6a 已实现：group 与成熟 outcome 的严格连接层

`research.group_outcome` 不做因子筛选，也不宣称任何因子有效。它把 legacy
`factor_results.jsonl` 的增量结果按 `(trade_date, code, horizon, field)` 严格合并，
并连接到同一 `(trade_date, code)` 最早一次包含 EOD 基础因子的 MR5
`stock_group_vector`：

- 同一字段/期限出现不同值时直接报冲突，不采用最后一行覆盖。
- `ret / mkt_ret / excess / horizon_trade_date` 首次齐全的原始行冻结为
  `outcome_available_at`；历史 `filled_ts` 无时区时按项目交易时区
  `Asia/Shanghai` 解释，并显式记录 `availability_timezone_inferred=true`。
- 强校验 `excess_ret = ret - benchmark_ret`。该 legacy benchmark 经
  `services.eval_recorder.BENCHMARK_INDEX` 源码验证为 `000001.SH` 上证综指；
  它不是赛道 benchmark，不能冒充未来的行业/赛道超额口径。
- 每个标签保存 group factor identity、group 计算/可见时点、结果首次完整行号、
  来源引用和输入摘要。结果先于 group 可见会触发 look-ahead 错误。
- 输出追加到 `var/research/outcomes/group_outcomes.jsonl`；写入带跨进程锁、
  `fsync`、身份冲突检测和重跑幂等。

EOD 顺序为基础快照 → curve → group → group outcome。当前阶段仍明确写
`selection_status=not_executed`、`forecast_status=not_executed`，不进入报告动作、
盘中通知、旧评分或自动调参。

历史审计命令：

```bash
PYTHONPATH=src python -m vaxstock.research.legacy_snapshot_replay
PYTHONPATH=src python -m vaxstock.services.curve_refresh --replay
PYTHONPATH=src python -m vaxstock.services.group_refresh --replay
PYTHONPATH=src python -m vaxstock.services.group_outcome_refresh
```

2026-07-28 本地真实回放得到 9,660 个成熟的股票×期限标签、21 个独立基准
交易日、0 个结果冲突和 0 个缺失 group；重复运行新增 0 行。统计层必须把
“股票×期限行数”和“独立基准交易日数”分开，不能把 9,660 行伪装成 9,660 个
独立样本。21 个交易日只验证连接层、时点和幂等，不足以证明因子 effective。

## 11. MR6a 已实现：group 与成熟 outcome 的严格连接层

`research.group_outcome` 不做因子筛选，也不宣称任何因子有效。它把 legacy
`factor_results.jsonl` 的增量结果按 `(trade_date, code, horizon, field)` 严格合并，
并连接到同一 `(trade_date, code)` 最早一次包含 EOD 基础因子的 MR5
`stock_group_vector`：

- 同一字段/期限出现不同值时直接报冲突，不采用最后一行覆盖。
- `ret / mkt_ret / excess / horizon_trade_date` 首次齐全的原始行冻结为
  `outcome_available_at`；历史 `filled_ts` 无时区时按项目交易时区
  `Asia/Shanghai` 解释，并显式记录 `availability_timezone_inferred=true`。
- 强校验 `excess_ret = ret - benchmark_ret`。该 legacy benchmark 经
  `services.eval_recorder.BENCHMARK_INDEX` 源码验证为 `000001.SH` 上证综指；
  它不是赛道 benchmark，不能冒充未来的行业/赛道超额口径。
- 每个标签保存 group factor identity、group 计算/可见时点、结果首次完整行号、
  来源引用和输入摘要。结果先于 group 可见会触发 look-ahead 错误。
- 输出追加到 `var/research/outcomes/group_outcomes.jsonl`；写入带跨进程锁、
  `fsync`、身份冲突检测和重跑幂等。

EOD 顺序为基础快照 → curve → group → group outcome。当前阶段仍明确写
`selection_status=not_executed`、`forecast_status=not_executed`，不进入报告动作、
盘中通知、旧评分或自动调参。

历史审计命令：

```bash
PYTHONPATH=src python -m vaxstock.research.legacy_snapshot_replay
PYTHONPATH=src python -m vaxstock.services.curve_refresh --replay
PYTHONPATH=src python -m vaxstock.services.group_refresh --replay
PYTHONPATH=src python -m vaxstock.services.group_outcome_refresh
```

2026-07-28 本地真实回放得到 9,660 个成熟的股票×期限标签、21 个独立基准
交易日、0 个结果冲突和 0 个缺失 group；重复运行新增 0 行。统计层必须把
“股票×期限行数”和“独立基准交易日数”分开，不能把 9,660 行伪装成 9,660 个
独立样本。21 个交易日只验证连接层、时点和幂等，不足以证明因子 effective。
