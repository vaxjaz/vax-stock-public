# var/prediction 目录说明

本目录保存 EOD Prediction 线,也就是“预测 -> 核验 -> 分析 -> 规则建议”的自我修复闭环。

它回答的问题是:

```text
当时系统给出的动作/方向/置信度,后来到底对不对?
```

注意:这里验证的是动作预测,不是单纯验证 `right_side_score` 分档未来收益。score 分档验证在 `var/eval`。

## 文件作用

| 文件 | 作用 | 来源/写入者 |
|---|---|---|
| `eod_predictions.jsonl` | EOD 预测原文。基于 `baseline_trade_date` 的定稿数据,预测 `target_trade_date` 的走势/动作。 | `services.eod_predictor` |
| `eod_prediction_results.jsonl` | 预测核验结果。用真实收益、基准收益、超额收益检查预测是否命中。 | `services.prediction_evaluator` |
| `prediction_layer2_report_<trade_date>.md` | Prediction Layer2 分析报告,按 action/direction/confidence/market/concept 分桶统计命中和超额。 | `research.prediction_eval.run_prediction_layer2` |
| `rule_suggestions_<trade_date>.md` | 规则建议报告。按 action/market/concept 汇总证据,只建议,不自动改参数。 | `research.rule_suggester.run_rule_suggestions` |

## 核心字段

### `eod_predictions.jsonl`

每行是一条冻结预测。写入后不得因未来结果而修改。

| 字段 | 含义 |
|---|---|
| `schema_version` | 记录结构版本。 |
| `prediction_id` | 预测唯一 ID,用于和结果表 join。 |
| `generated_at` | 预测生成时间。 |
| `generation_mode` | `replay` 表示历史重放,`live` 表示真实 EOD 生成。 |
| `baseline_trade_date` | 预测依据的 EOD 基准日。 |
| `target_trade_date` | 要预测/核验的目标交易日。 |
| `code` / `name` | 股票代码和名称。 |
| `group` | `holding` 或 `watchlist`。 |
| `concepts` | 概念标签。 |
| `features_ref` | 当时使用的特征引用,如价格、评分、市场 regime。 |
| `features_ref.right_side_score` | 当时冻结的右侧评分。 |
| `features_ref.market_regime` | 当时市场 regime。 |
| `features_ref.macro_regime` | 当时宏观 regime。 |
| `prediction.action` | 动作预测,如 `avoid`、`watch`、`candidate_buy`、`panic_rebound_watch`。 |
| `prediction.direction` | 方向预测,如 `up`、`down`、`neutral`。 |
| `prediction.confidence` | 置信度。 |
| `prediction.horizon` | 预测窗口,当前主要是 `T+1`。 |
| `prediction.expected_excess_bucket` | 对超额收益的预期,如 `positive`、`non_positive`、`uncertain`。 |
| `rule_version` | 规则版本。规则升级必须 bump 它。 |
| `model_version` | 预测模型/规则模型版本。 |

### `eod_prediction_results.jsonl`

每行是一条 prediction 的核验结果。

| 字段 | 含义 |
|---|---|
| `prediction_id` | 对应 `eod_predictions.jsonl` 的 ID。 |
| `horizon` | 核验窗口,如 `1` 表示 T+1。 |
| `actual.ret` | 个股真实收益。 |
| `actual.mkt_ret` | 基准收益。 |
| `actual.excess` | 超额收益,即 `ret - mkt_ret`。 |
| `actual.source` | 真实收益来源,当前复用 `factor_results`。 |
| `evaluation.direction_hit` | 方向是否命中。预测 `up` 且个股收益为正则命中。 |
| `evaluation.positive_excess` | 实际超额是否为正。 |
| `evaluation.action_hit` | 动作是否命中。比如预期正超额且实际超额为正。 |
| `evaluation.deviation` | 偏离类型,如 `as_expected`、`missed_positive_excess`。 |
| `evaluation.error_type` | 核验错误类型;正常为 `None`。 |

### `prediction_layer2_report_<trade_date>.md`

| 字段/栏目 | 含义 |
|---|---|
| `generation_mode` | `replay` 和 `live` 分开统计。 |
| `predictions` | 桶内预测总数。 |
| `evaluated` | 已有结果并参与统计的数量。 |
| `pending` | 尚未核验的数量;不进入收益/命中率。 |
| `avg_ret` | 已核验样本的个股平均收益。 |
| `avg_excess` | 已核验样本的平均超额收益。 |
| `excess>0` | 正超额率。 |
| `action_hit` | 动作命中率。 |
| `direction_hit` | 方向命中率。 |

### `rule_suggestions_<trade_date>.md`

| 字段/栏目 | 含义 |
|---|---|
| `report_date` | 报告锚定交易日,取最新已核验 `target_trade_date`。 |
| `source_predictions` | 读取到的预测总数,包含 pending。 |
| `evaluated` | 已有核验结果并进入建议证据的数量。 |
| `pending` | 尚未核验的数量;只展示,不进入命中率/收益统计。 |
| `min_evaluated` | 建议强弱分级阈值。低于阈值仍展示,但标为 `thin` 并提示不升级规则。 |
| `priority` | 建议优先级,如 `P1`/`P2`/`P3`。 |
| `scope` | 证据作用范围,如 `action:watch`、`market:panic|bear`、`concept:机器人`。 |
| `evidence_strength` | `strong`/`medium`/`thin`,只表示样本证据强弱,不是自动交易结论。 |
| `suggestion` | 人工审核用规则建议。它不会自动改生产参数。 |
| `next_step` | 建议的人工动作,通常是复核样本后另开 PR 并 bump `rule_version`。 |

## 术语说明

| 术语 | 含义 |
|---|---|
| `panic` | 市场恐慌状态。当前规则里主要由全市场跌停数量触发,代表先防守。 |
| `panic 修复` | panic 后的情绪修复交易观察,不等同于右侧追涨,也不等同于立即买入。 |
| `panic_rebound_watch/probe` | panic 修复分支下的动作标签; `watch` 偏观察,`probe` 偏轻仓试探候选,均需人工确认。 |
| `watch` | 高优先观察,不是买入指令; 后续仍需要盘中行为、资金和基本面交叉确认。 |
| `watch_only` | 只观察,明确不进入买入候选。 |
| `avoid` | 回避或低优先级,不等于永久剔除该股票。 |
| `confidence` | 规则先验置信度,用于分桶观察,不是统计概率,也不是胜率承诺。 |
| `pending` | 还没有真实结果的预测; 只计数,不进入收益、超额、命中率统计。 |
| `avg_excess` / `正超额` | `avg_excess` 是桶内平均超额收益; 正超额表示个股收益跑赢基准指数。 |
| `action_hit` | 动作预测是否与真实超额方向匹配; 例如预期正超额且最终 `excess > 0`。 |
| `direction_hit` | 方向预测是否与真实个股涨跌方向匹配。 |
| `thin/medium/strong` | 只描述样本证据厚薄,不是自动交易结论。 |
## 例子

如果某条预测:

```text
prediction.action = panic_rebound_watch
prediction.direction = up
prediction.expected_excess_bucket = positive
```

后来真实结果:

```text
actual.ret = +5%
actual.mkt_ret = +2%
actual.excess = +3%
```

那么:

```text
direction_hit = True
action_hit = True
```

因为股票上涨了,且跑赢基准 3%。

## 使用原则

- `eod_predictions.jsonl` 和 `eod_prediction_results.jsonl` 都是 append-only。
- live prediction 在目标日结果出来前只算 pending,不能提前算命中。
- `prediction_layer2_report_*.md` 是可重生成报告。
- 规则只能前滚升级 `rule_version`,不能回头改历史 prediction 原文。
