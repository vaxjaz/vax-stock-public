# Rule Suggestions 20260703

> 本报告只给规则升级建议和证据,不自动改参数、不修改历史 prediction、不 bump rule_version。
> N 直接展示; 样本薄会标注为 thin,但不会被隐藏。pending 样本不进入收益/命中率统计。
> concept 桶是一票多桶,只能作为候选证据,不能单独决定交易动作。

- source_predictions: 292
- evaluated: 250
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
| P1 | action:panic_rebound_probe | medium | 保留 panic 修复分支; 可作为左侧修复规则候选继续单独验证。 | N=39, 平均超额=+1.99%, 正超额率=64%, action命中=- | 人工审核后再决定是否拆成 left/panic_repair 独立 rule_version。 |
| P1 | action:panic_rebound_watch | medium | 保留 panic 修复分支; 可作为左侧修复规则候选继续单独验证。 | N=41, 平均超额=+2.37%, 正超额率=71%, action命中=71% | 人工审核后再决定是否拆成 left/panic_repair 独立 rule_version。 |
| P1 | market:panic\|🔴 看空 | strong | panic 环境后的修复交易有正向证据,建议把 panic 修复和普通右侧追随分开评估。 | N=84, 平均超额=+2.16%, 正超额率=67%, action命中=71% | 候选方向: 单独建立 left_repair/panic_repair 规则,人工确认后 bump rule_version。 |
| P2 | concept:人形机器人 | strong | 该概念桶有正超额证据,可作为动作规则的加分候选,但概念桶是一票多桶。 | N=66, 平均超额=+3.27%, 正超额率=70%, action命中=44% | 只纳入人工候选; 需要与个股基本面/资金确认交叉验证。 |
| P2 | concept:光模块 | medium | 该概念桶阶段性拖累预测表现,不宜只因概念标签提高动作置信度。 | N=24, 平均超额=-2.40%, 正超额率=29%, action命中=58% | 人工复盘成分股差异; 暂不自动降权。 |
| P2 | concept:特斯拉链 | medium | 该概念桶有正超额证据,可作为动作规则的加分候选,但概念桶是一票多桶。 | N=24, 平均超额=+2.98%, 正超额率=67%, action命中=53% | 只纳入人工候选; 需要与个股基本面/资金确认交叉验证。 |
| P3 | action:candidate_buy | thin | 样本薄,只记录观察,不建议升级规则。 | N=4, 平均超额=-0.82%, 正超额率=50%, action命中=50% | 继续积累样本; 人工复盘单票,不改 rule_version。 |
| P3 | action:watch_only | thin | 样本薄,只记录观察,不建议升级规则。 | N=4, 平均超额=+1.67%, 正超额率=50%, action命中=- | 继续积累样本; 人工复盘单票,不改 rule_version。 |

## Action 证据
| bucket | N | 平均超额 | 正超额率 | action命中 | direction命中 |
|---|---:|---:|---:|---:|---:|
| avoid | 97 | +0.29% | 44% | 56% | - |
| watch | 65 | -0.84% | 43% | 43% | 32% |
| panic_rebound_watch | 41 | +2.37% | 71% | 71% | 71% |
| panic_rebound_probe | 39 | +1.99% | 64% | - | - |
| candidate_buy | 4 | -0.82% | 50% | 50% | 50% |
| watch_only | 4 | +1.67% | 50% | - | - |

## Market 证据
| bucket | N | 平均超额 | 正超额率 | action命中 | direction命中 |
|---|---:|---:|---:|---:|---:|
| panic\|🔴 看空 | 84 | +2.16% | 67% | 71% | 71% |
| value\|🟡 中性 | 84 | +0.01% | 50% | 38% | 36% |
| momentum\|🔴 看空 | 42 | -1.45% | 31% | 57% | 33% |
| momentum\|🔴 强看空 | 40 | +0.74% | 45% | 70% | 28% |

## Concept 证据(Top by N)
| bucket | N | 平均超额 | 正超额率 | action命中 | direction命中 |
|---|---:|---:|---:|---:|---:|
| AI算力 | 160 | -0.44% | 44% | 60% | 44% |
| 人形机器人 | 66 | +3.27% | 70% | 44% | 64% |
| 创业板 | 54 | +0.38% | 44% | 61% | 45% |
| PCB | 30 | -1.13% | 47% | 62% | 48% |
| 科创板 | 30 | -0.63% | 50% | 57% | 45% |
| 光模块 | 24 | -2.40% | 29% | 58% | 31% |
| 特斯拉链 | 24 | +2.98% | 67% | 53% | 100% |
| AI芯片 | 18 | -0.48% | 56% | 56% | 44% |
| HVLP铜箔 | 18 | -1.01% | 39% | 50% | 42% |
| IDC | 18 | +1.07% | 39% | 77% | 33% |
| 灵巧手 | 18 | +3.40% | 67% | 43% | 50% |
| 丝杠 | 12 | +3.41% | 75% | 38% | - |
| 执行器 | 12 | +2.67% | 67% | 50% | - |
| 算力电源 | 12 | +4.56% | 58% | 50% | 60% |
| 配电 | 12 | -0.45% | 42% | 60% | 50% |

## 人工审核提醒
- 任何采纳都必须另开 PR,并显式 bump `rule_version`。
- 不回写 `eod_predictions.jsonl`; 历史预测原文保持可审计。
- 左侧/panic 修复若要落地,应独立命名规则,不要污染 `right_side_score`。
