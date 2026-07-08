# Rule Suggestions 20260707

> 本报告只给规则升级建议和证据,不自动改参数、不修改历史 prediction、不 bump rule_version。
> N 直接展示; 样本薄会标注为 thin,但不会被隐藏。pending 样本不进入收益/命中率统计。
> concept 桶是一票多桶,只能作为候选证据,不能单独决定交易动作。

- source_predictions: 376
- evaluated: 334
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
| P1 | action:panic_rebound_watch | strong | 保留 panic 修复分支; 可作为左侧修复规则候选继续单独验证。 | N=60, 平均超额=+1.81%, 正超额率=65%, action命中=65% | 人工审核后再决定是否拆成 left/panic_repair 独立 rule_version。 |
| P1 | action:watch | strong | 收紧 watch 动作的触发条件,尤其避免在弱环境里把普通观察误判为正超额。 | N=82, 平均超额=-1.15%, 正超额率=41%, action命中=41% | 优先排查 watch 的 market/concept 子桶,只出建议,不直接调参。 |
| P1 | market:panic\|🔴 看空 | strong | panic 环境后的修复交易有正向证据,建议把 panic 修复和普通右侧追随分开评估。 | N=84, 平均超额=+2.16%, 正超额率=67%, action命中=71% | 候选方向: 单独建立 left_repair/panic_repair 规则,人工确认后 bump rule_version。 |
| P2 | concept:HVLP铜箔 | medium | 该概念桶阶段性拖累预测表现,不宜只因概念标签提高动作置信度。 | N=24, 平均超额=-1.86%, 正超额率=33%, action命中=43% | 人工复盘成分股差异; 暂不自动降权。 |
| P2 | concept:光模块 | medium | 该概念桶阶段性拖累预测表现,不宜只因概念标签提高动作置信度。 | N=32, 平均超额=-1.97%, 正超额率=31%, action命中=52% | 人工复盘成分股差异; 暂不自动降权。 |
| P3 | action:candidate_buy | thin | 样本薄,只记录观察,不建议升级规则。 | N=6, 平均超额=-1.08%, 正超额率=33%, action命中=33% | 继续积累样本; 人工复盘单票,不改 rule_version。 |
| P3 | action:watch_only | thin | 样本薄,只记录观察,不建议升级规则。 | N=10, 平均超额=+1.20%, 正超额率=60%, action命中=- | 继续积累样本; 人工复盘单票,不改 rule_version。 |

## Action 证据
| bucket | N | 平均超额 | 正超额率 | action命中 | direction命中 |
|---|---:|---:|---:|---:|---:|
| avoid | 120 | -0.21% | 42% | 58% | - |
| watch | 82 | -1.15% | 41% | 41% | 33% |
| panic_rebound_watch | 60 | +1.81% | 65% | 65% | 65% |
| panic_rebound_probe | 56 | +1.12% | 55% | - | - |
| watch_only | 10 | +1.20% | 60% | - | - |
| candidate_buy | 6 | -1.08% | 33% | 33% | 33% |

## Market 证据
| bucket | N | 平均超额 | 正超额率 | action命中 | direction命中 |
|---|---:|---:|---:|---:|---:|
| value\|🟡 中性 | 126 | -0.75% | 44% | 43% | 35% |
| panic\|🔴 看空 | 84 | +2.16% | 67% | 71% | 71% |
| momentum\|🔴 看空 | 42 | -1.45% | 31% | 57% | 33% |
| panic\|🟡 中性 | 42 | +0.05% | 48% | 53% | 53% |
| momentum\|🔴 强看空 | 40 | +0.74% | 45% | 70% | 28% |

## Concept 证据(Top by N)
| bucket | N | 平均超额 | 正超额率 | action命中 | direction命中 |
|---|---:|---:|---:|---:|---:|
| AI算力 | 214 | -0.50% | 45% | 57% | 44% |
| 人形机器人 | 88 | +1.83% | 57% | 48% | 50% |
| 创业板 | 72 | -0.09% | 43% | 57% | 42% |
| PCB | 40 | -1.11% | 42% | 58% | 45% |
| 科创板 | 40 | -0.17% | 57% | 61% | 54% |
| 光模块 | 32 | -1.97% | 31% | 52% | 28% |
| 特斯拉链 | 32 | +1.35% | 53% | 62% | 100% |
| AI芯片 | 24 | -0.08% | 62% | 61% | 52% |
| HVLP铜箔 | 24 | -1.86% | 33% | 43% | 35% |
| IDC | 24 | -0.51% | 29% | 71% | 20% |
| 灵巧手 | 24 | +1.28% | 50% | 47% | 33% |
| 丝杠 | 16 | +1.32% | 56% | 42% | 0% |
| 执行器 | 16 | +1.53% | 56% | 60% | - |
| 算力电源 | 16 | +3.74% | 56% | 50% | 57% |
| 配电 | 16 | -0.06% | 50% | 54% | 50% |

## 人工审核提醒
- 任何采纳都必须另开 PR,并显式 bump `rule_version`。
- 不回写 `eod_predictions.jsonl`; 历史预测原文保持可审计。
- 左侧/panic 修复若要落地,应独立命名规则,不要污染 `right_side_score`。
