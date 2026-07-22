# Rule Suggestions 20260721

> 本报告只给规则升级建议和证据,不自动改参数、不修改历史 prediction、不 bump rule_version。
> N 直接展示; 样本薄会标注为 thin,但不会被隐藏。pending 样本不进入收益/命中率统计。
> concept 桶是一票多桶,只能作为候选证据,不能单独决定交易动作。

- source_predictions: 796
- evaluated: 754
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
| P1 | action:watch | strong | 收紧 watch 动作的触发条件,尤其避免在弱环境里把普通观察误判为正超额。 | N=148, 平均超额=-1.72%, 正超额率=35%, action命中=35% | 优先排查 watch 的 market/concept 子桶,只出建议,不直接调参。 |
| P1 | market:panic\|🔴 看空 | strong | panic 环境后的修复交易有正向证据,建议把 panic 修复和普通右侧追随分开评估。 | N=84, 平均超额=+2.16%, 正超额率=67%, action命中=71% | 候选方向: 单独建立 left_repair/panic_repair 规则,人工确认后 bump rule_version。 |
| P1 | market:value\|🟡 中性 | strong | value/中性环境下当前动作预测偏弱,建议降低普通 watch 的正超额预期。 | N=252, 平均超额=-1.61%, 正超额率=34%, action命中=44% | 候选方向: value\|中性 桶要求额外资金/业绩确认,暂不自动改参数。 |
| P2 | action:avoid | strong | avoid 下限过滤目前有一定保护作用,建议保留为防守规则。 | N=168, 平均超额=-0.78%, 正超额率=36%, action命中=64% | 继续观察是否在强主线概念里过度回避。 |
| P2 | concept:HVLP铜箔 | strong | 该概念桶阶段性拖累预测表现,不宜只因概念标签提高动作置信度。 | N=54, 平均超额=-2.31%, 正超额率=35%, action命中=41% | 人工复盘成分股差异; 暂不自动降权。 |
| P3 | action:candidate_buy | thin | 样本薄,只记录观察,不建议升级规则。 | N=18, 平均超额=-2.88%, 正超额率=17%, action命中=17% | 继续积累样本; 人工复盘单票,不改 rule_version。 |

## Action 证据
| bucket | N | 平均超额 | 正超额率 | action命中 | direction命中 |
|---|---:|---:|---:|---:|---:|
| panic_rebound_watch | 196 | +0.53% | 55% | 55% | 59% |
| avoid | 168 | -0.78% | 36% | 64% | - |
| panic_rebound_probe | 165 | -0.08% | 50% | - | - |
| watch | 148 | -1.72% | 35% | 35% | 24% |
| watch_only | 59 | +0.62% | 56% | - | - |
| candidate_buy | 18 | -2.88% | 17% | 17% | 11% |

## Market 证据
| bucket | N | 平均超额 | 正超额率 | action命中 | direction命中 |
|---|---:|---:|---:|---:|---:|
| panic\|🟡 中性 | 336 | -0.16% | 50% | 51% | 55% |
| value\|🟡 中性 | 252 | -1.61% | 34% | 44% | 21% |
| panic\|🔴 看空 | 84 | +2.16% | 67% | 71% | 71% |
| momentum\|🔴 看空 | 42 | -1.45% | 31% | 57% | 33% |
| momentum\|🔴 强看空 | 40 | +0.74% | 45% | 70% | 28% |

## Concept 证据(Top by N)
| bucket | N | 平均超额 | 正超额率 | action命中 | direction命中 |
|---|---:|---:|---:|---:|---:|
| AI算力 | 484 | -0.60% | 45% | 52% | 42% |
| 人形机器人 | 198 | -0.14% | 45% | 47% | 40% |
| 创业板 | 162 | -0.62% | 44% | 51% | 41% |
| PCB | 90 | -0.69% | 46% | 50% | 42% |
| 科创板 | 90 | -0.32% | 51% | 58% | 47% |
| 光模块 | 72 | -0.96% | 43% | 54% | 40% |
| 特斯拉链 | 72 | -0.31% | 47% | 61% | 33% |
| AI芯片 | 54 | -0.02% | 56% | 57% | 48% |
| HVLP铜箔 | 54 | -2.31% | 35% | 41% | 33% |
| IDC | 54 | -0.16% | 41% | 67% | 44% |
| 灵巧手 | 54 | -0.17% | 44% | 44% | 38% |
| 丝杠 | 36 | -0.08% | 42% | 38% | 35% |
| 执行器 | 36 | -0.09% | 50% | 62% | - |
| 算力电源 | 36 | +0.35% | 44% | 45% | 40% |
| 配电 | 36 | -0.70% | 42% | 50% | 44% |

## 人工审核提醒
- 任何采纳都必须另开 PR,并显式 bump `rule_version`。
- 不回写 `eod_predictions.jsonl`; 历史预测原文保持可审计。
- 左侧/panic 修复若要落地,应独立命名规则,不要污染 `right_side_score`。
