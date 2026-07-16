# Rule Suggestions 20260715

> 本报告只给规则升级建议和证据,不自动改参数、不修改历史 prediction、不 bump rule_version。
> N 直接展示; 样本薄会标注为 thin,但不会被隐藏。pending 样本不进入收益/命中率统计。
> concept 桶是一票多桶,只能作为候选证据,不能单独决定交易动作。

- source_predictions: 628
- evaluated: 586
- pending: 42
- min_evaluated_reference: 20

## 术语说明
- `panic`: 市场恐慌状态。当前规则里主要由全市场跌停数量触发,代表先防守。
- `panic 修复`: panic 后的情绪修复交易观察,不等同于右侧追涨,也不等同于立即买入。
- `panic_rebound_watch/probe`: panic 修复分支下的动作标签; `watch` 偏观察,`probe` 偏轻仓试探候选,均需人工确认。
- `left_repair` / `panic_repair`: 候选的新规则名,表示左侧修复逻辑; 若采纳必须另开 PR 并 bump `rule_version`。
- `watch`: 高优先观察,不是买入指令; 后续仍需要盘中行为、资金和基本面交叉确认。
- `watch_only`: 只观察,明确不进入买入候选。
- `avoid`: 回避或低优先级,不等于永久剔除该股票。
- `action_hit`: 动作预测是否和真实超额方向匹配; 例如预期正超额且最终 `excess > 0`。
- `正超额`: 个股收益跑赢基准指数,即 `actual.excess = actual.ret - actual.mkt_ret > 0`。
- `thin/medium/strong`: 只描述样本证据厚薄,不是自动交易结论。

## 建议清单
| priority | scope | evidence_strength | suggestion | evidence | next_step |
|---|---|---|---|---|---|
| P1 | action:watch | strong | 收紧 watch 动作的触发条件,尤其避免在弱环境里把普通观察误判为正超额。 | N=105, 平均超额=-1.31%, 正超额率=39%, action命中=39% | 优先排查 watch 的 market/concept 子桶,只出建议,不直接调参。 |
| P1 | market:panic\|🔴 看空 | strong | panic 环境后的修复交易有正向证据,建议把 panic 修复和普通右侧追随分开评估。 | N=84, 平均超额=+2.16%, 正超额率=67%, action命中=71% | 候选方向: 单独建立 left_repair/panic_repair 规则,人工确认后 bump rule_version。 |
| P1 | market:value\|🟡 中性 | strong | value/中性环境下当前动作预测偏弱,建议降低普通 watch 的正超额预期。 | N=168, 平均超额=-1.30%, 正超额率=38%, action命中=46% | 候选方向: value\|中性 桶要求额外资金/业绩确认,暂不自动改参数。 |
| P2 | action:avoid | strong | avoid 下限过滤目前有一定保护作用,建议保留为防守规则。 | N=137, 平均超额=-0.65%, 正超额率=37%, action命中=63% | 继续观察是否在强主线概念里过度回避。 |
| P2 | concept:HVLP铜箔 | medium | 该概念桶阶段性拖累预测表现,不宜只因概念标签提高动作置信度。 | N=42, 平均超额=-1.85%, 正超额率=33%, action命中=44% | 人工复盘成分股差异; 暂不自动降权。 |
| P3 | action:candidate_buy | thin | 样本薄,只记录观察,不建议升级规则。 | N=8, 平均超额=-2.95%, 正超额率=25%, action命中=25% | 继续积累样本; 人工复盘单票,不改 rule_version。 |

## Action 证据
| bucket | N | 平均超额 | 正超额率 | action命中 | direction命中 |
|---|---:|---:|---:|---:|---:|
| panic_rebound_watch | 163 | +0.45% | 53% | 53% | 57% |
| avoid | 137 | -0.65% | 37% | 63% | - |
| panic_rebound_probe | 137 | +0.05% | 49% | - | - |
| watch | 105 | -1.31% | 39% | 39% | 29% |
| watch_only | 36 | +1.69% | 56% | - | - |
| candidate_buy | 8 | -2.95% | 25% | 25% | 25% |

## Market 证据
| bucket | N | 平均超额 | 正超额率 | action命中 | direction命中 |
|---|---:|---:|---:|---:|---:|
| panic\|🟡 中性 | 252 | -0.16% | 46% | 47% | 52% |
| value\|🟡 中性 | 168 | -1.30% | 38% | 46% | 28% |
| panic\|🔴 看空 | 84 | +2.16% | 67% | 71% | 71% |
| momentum\|🔴 看空 | 42 | -1.45% | 31% | 57% | 33% |
| momentum\|🔴 强看空 | 40 | +0.74% | 45% | 70% | 28% |

## Concept 证据(Top by N)
| bucket | N | 平均超额 | 正超额率 | action命中 | direction命中 |
|---|---:|---:|---:|---:|---:|
| AI算力 | 376 | -0.43% | 45% | 53% | 44% |
| 人形机器人 | 154 | +0.32% | 47% | 46% | 44% |
| 创业板 | 126 | -0.32% | 44% | 54% | 44% |
| PCB | 70 | -0.20% | 47% | 54% | 46% |
| 科创板 | 70 | -0.26% | 51% | 55% | 47% |
| 光模块 | 56 | -0.93% | 43% | 58% | 38% |
| 特斯拉链 | 56 | +0.03% | 48% | 68% | 100% |
| AI芯片 | 42 | -0.12% | 55% | 54% | 46% |
| HVLP铜箔 | 42 | -1.85% | 33% | 44% | 37% |
| IDC | 42 | -0.36% | 33% | 64% | 42% |
| 灵巧手 | 42 | +0.07% | 45% | 39% | 36% |
| 丝杠 | 28 | +0.24% | 46% | 35% | 38% |
| 执行器 | 28 | +0.27% | 50% | 67% | - |
| 算力电源 | 28 | +1.55% | 50% | 52% | 50% |
| 配电 | 28 | -0.83% | 43% | 50% | 50% |

## 人工审核提醒
- 任何采纳都必须另开 PR,并显式 bump `rule_version`。
- 不回写 `eod_predictions.jsonl`; 历史预测原文保持可审计。
- 左侧/panic 修复若要落地,应独立命名规则,不要污染 `right_side_score`。
