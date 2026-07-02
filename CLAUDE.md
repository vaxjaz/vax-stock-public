# CLAUDE.md — vax-stock 项目工作约定

> 本文件由 Claude Code 在每次会话自动读取。它定义项目背景、架构目标、
> 重构路线与**不可违反的铁律**。任何代码改动都必须遵守本文件。

---

## 1. 项目定位

A股量化分析系统(主板,A-share)。核心是基于多因子评分 + 宏观 regime 的
系统化持仓管理,外加一套独立的 AI 赛道择时体系。当前市场判断为 K型分化,
主线为科技 AI,分析与策略以 AI 主线为先,但保留宏观/SOX 刹车不可折叠。

部署:VPS(`vaxjaz.duckdns.org`) 跑 FastAPI(`stock-api.service`) + 盘中盯盘
(`intraday-watch.service`),每日 cron 生成报告。本仓为**工程化重构的目标地**,
与 VPS 当前运行的生产副本**物理隔离**——重构不影响生产,验证通过后才切换。

---

## 2. P0 数据完整性铁律(最高优先级,不可妥协)

1. 所有指标计算/字段单位/信号结论必须 100% 可溯源到源码行、官方文档或实测数据。
   **禁止臆测。**
2. 禁用语言:把"大概/可能/应该/通常"当结论包装词 → 停下,要么验证,要么显式标"待验证"。
3. 区分「已证实」(可下定论) vs「待验证」(给验证方法,不给结论)。
4. 缺数据 ≠ 给默认值。拉不到就标"待验证",**绝不 fallback 给 0.5 / 中性值污染决策**。
5. 不臆测字段名/单位:首次接触新接口先打印真实字段再写解析。
6. 改代码前先看源码真实内容,不凭记忆推断函数行为。

---

## 3. 工程化目标架构

标准 python 包,单向分层依赖(上层依赖下层,无回环):

```
config -> sources -> indicators -> analysis -> report -> services
                                                          research(离线,独立)
```

```
src/vaxstock/
├── __init__.py          # 包定义
├── config.py            # 统一配置: 密钥环境变量优先, 路径集中, import无副作用
├── util.py              # safe_float/fmt_* 等通用工具
├── sources/             # 数据源层(纯取数, 无副作用, 显式init)
│   ├── tushare_src.py / eastmoney.py / sina.py / us_market.py
├── indicators/          # 计算层(纯函数, 最易测)
│   ├── technical.py     # EMA/MACD/RSI
│   ├── valuation.py     # PE/PB分位/换手Z/资金斜率
│   ├── scoring.py       # right_side_score/derived_metrics
│   ├── regime.py        # detect_market_regime
│   └── macro.py         # 宏观7维regime
├── analysis/            # 分析层
│   ├── stock_item.py / holdings.py / ai_track.py
│   ├── opportunity.py / hot_sector.py
├── report/              # 输出层
│   ├── builder.py / render.py / email.py / store.py
├── services/            # 入口
│   ├── api.py / intraday.py / cron_daily.py
└── research/            # 离线研究层(ic_engine/factor_calculator等)
```

**【硬规矩 · tracks 叶子契约不可污染】**

tracks/__init__.py 严禁 import ai 或任何会触网/加载重依赖(akshare/pandas 等)的赛道实现模块。原因:contract 是只 import typing 的叶子契约,report 层和任何只需要 TrackResult DTO 的地方必须用 from vaxstock.tracks.contract import ... 直接导入;若 __init__ 重导出了 ai,则 from vaxstock.tracks import TrackResult 会传递加载 akshare,污染叶子契约、拖慢 report。新增赛道模块同理,只在使用处显式 import,不在 tracks/__init__ 里 re-export。

---

## 4. 重构铁律(每个 MR 都必须遵守)

1. **逻辑零改动**:搬运函数只改"住哪",不改"做什么"。搬完必须实测输出与原版一致。
2. **不动巨石原文件**:`script/stock_report_enhanced.py` 及其他生产原文件**一行不许动**,
   保证 VPS 生产零影响。新结构在 `src/vaxstock/` 下平行建立。
3. **消除 import 副作用**:import 任何模块不得连网、不得初始化 client、不得读密钥触发IO。
   client 初始化改为显式调用。
4. **密钥环境变量优先**:所有密钥经 `config.py` 从环境变量读,secrets.json 仅本地兜底
   (已 gitignore)。代码里**禁止硬编码任何 token/密钥/邮箱**。
5. **路径集中**:不再用 `os.path.dirname(__file__)` 散落各处,统一走 `config.py` 的
   PROJECT_ROOT / STATE_DIR / CACHE_DIR / REPORTS_DIR。
6. **每个 MR 独立可验证**:小步提交,每个 MR 搬完用 `PYTHONPATH=src python3 -c`
   验证 import 无副作用 + 纯函数输出正确。
7. **PR 不自动 merge**:建分支 → commit → 创建 PR → **留给 vaxjaz 审核合并**。
   除非明确要求,不主动 merge。

---

## 5. 重构路线图(MR 顺序)

- [x] **MR1 地基层**:`__init__/config/util/indicators(technical,valuation,regime)` + 骨架 + .gitignore + secrets.json.example
- [x] **MR2 sources 层**:从巨石拆 sina.py,整合 tushare_src.py / us_market.py
- [x] **MR3 东财迁 Tushare**:东财砍除,板块④/热门赛道⑦诚实降级 available=False
- [x] **MR4 analysis 层**:stock_item / holdings / scoring 进 indicators(消 `_CURRENT_MARKET_REGIME` 全局)
- [x] **MR5 report 层**:claude_md / store / mailer
- [x] **MR-Track 赛道纵切**:contract.py 契约 + ai.py AI赛道
- [~] **MR6 services 层**:
    - [x] C1 api.py 去副作用(lite=1 前置 refresh_regime,消全局,惰性单例)
    - [x] C2a intraday 迁包 + codex/notify 抽离 + 盘中铁律硬校验器
    - [x] C2b codex 注入大盘背景/概念/触发次数
    - [x] C2c T-1基准注入 + 校验器白名单 + A样本线(forecast冻结)  # PR-A(PR#30)
    - [ ] C2d 盘中演变记忆 + 主动盘面体检 + /intraday/ask 咨询端点(C2c 未尽的演变记忆归此)
    - [x] B1+2 macro 迁包(骨架+5维: ETF/M1/融资/换手/ERP)
    - [x] B3 macro 维度5(全市场 breadth MA60/200 + MA250乖离)  # PR#27
    - [x] B4 macro 第7维 社融脉冲(sf_month 权限已确认✅)  # PR#28, 维度7迁入, macro 7维齐
    - [x] C3a deploy/ 纳入仓库(v2 三服务 systemd unit + EOD timer + README 切换手册)
    - [ ] C3b VPS 切线上(运维: v2 一刀切顶替 v1, 仅 backtest cron 保留; 切换非代码 PR)
- [ ] **MR-Eval 线(预测追踪反哺,独立线)**:
    - [ ] E0 文档/任务锚定:把 EOD Prediction 线的目标、任务拆解、文件落点/命名/作用写入本文件(本项先行,防后续 PR 走偏)
    - [ ] E1 全 watchlist 因子快照 append + T+k(1/3/5/10/20/30)回填(尽早,数据时间不可逆)
    - [ ] E2 research 分桶/前瞻IC/超额评估报告(攒够样本后)
    - [ ] E3 人工据报告反哺因子权重(不自动调参)
    - [x] C线 forecast 第三条数据线已立(EOD∪Layer2 之上的预测线; T-1基准注入 + JSON结构化预测冻结 var/forecast/forecasts.jsonl); 结果 T+k 回填留后续 PR  # PR-A(PR#30)
    - [ ] E4 EOD Prediction 线:基于 T-1 EOD 真数据生成 T 日 9:30 后走势/动作预测,次日 EOD 核验,长期 day-by-day 修复用户 universe 择股框架(详见 §9.10)
- [ ] **MR7 文档/README 全面同步**

---

## 6. 验证规范

每个 MR 完成后必须跑(且贴出结果):

```bash
# 语法 + import 无副作用 + 纯函数实测
PYTHONPATH=src python3 -c "
from vaxstock import config
from vaxstock.indicators.technical import calc_rsi
from vaxstock.indicators.regime import detect_market_regime
assert calc_rsi([10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25]) == 100.0
assert detect_market_regime([], {}) == 'momentum'
print('✅ import无副作用 + 纯函数验证通过')
"
```

---

## 7. 协作分工

- **施工(Claude Code, 本环境)**:改代码、重构、建分支、发 PR。
- **参谋(claude.ai Project Chat)**:每日盯盘、市场研判、信号分析、PR 内容审核。
- 投资判断、券商截图解读、数据交叉验证 → 在 Project Chat 做,**不在 Code 做**。

---

## 8. 交易硬约束(写代码涉及标的过滤时遵守)

- 不可交易 STAR Market(688 前缀)—— 永久。
- 不可交易 ChiNext(300 前缀)—— 2026年9月前临时禁止,9月后解禁。
- 所有可交易候选必须主板:60x / 00x / 002 前缀。

---

## 9. 关键架构决策(为什么这么定,后续窗口必读)

1. **交易日锚定铁律**:所有"交易日基准"(报告目录名/北向is_today/regime落盘/MR-Eval快照)必须取数据里的 trade_date(`market_overview["trade_date"]` / daily 返回值),**绝不用 `now()`/`date.today()`**。后者只允许用于"生成时刻戳"(`generated_at`)和"缓存key后缀"。原因:EOD 改为次日凌晨05:00(美股收盘后)跑,`now()` 是 T+1,用 now 当交易日必错一天。
2. **EOD 调度时点 = 次日凌晨 05:00**(美股收盘后跑 T 日 EOD)。红利:① daily/breadth 的 T 日已收盘定稿 → 增量缓存幂等天然成立(不必两段式);② us_market(NVDA/SOX/VIX)拿到美股 T 日完整收盘,AI赛道择时更准。注:margin/融资数据 Tushare(本账户2000积分)T+1 早晨仍未发布(实测 6/26 08:30 仍取不到 6/25),凌晨5点亦拿不到当日 margin,该维天然滞后 1-2 日,属数据源时效非 bug;报告应标注该维 data_date 与报告日的差。
3. **幂等是代码内在属性,不靠使用约束**(不靠"别在盘中跑")。写持久状态只接受"已定稿数据";会变的"当天"不进持久状态(或靠凌晨5点跑时当天已定稿)。regime 状态(`regime_history.json`):纯重放 + 按 trade_date 去重,同日跑N次结果恒定(PR#12)。macro 增量缓存(parquet, `append_unique keep=last`):同一定稿交易日写N次结果恒定。
4. **单一真相 / 消全局**:`_CURRENT_MARKET_REGIME` 已消除,regime 显式传 `build_stock_item`;intraday 是 api 纯消费者,大盘 regime 只走 `GET /market`(api REGIME_TTL 缓存),不自取 Tushare。
5. **盘中六铁律 = 输出层硬校验,不靠 codex 自觉**:codex 研判过 `enforce_intraday_rules`(正则拦评分/买卖价/资金臆测)。引入 T-1 基准后(C2c):"昨日/T-1"限定词的评分引用合法,盘中新生成评分非法——用限定词白名单区分。
6. **数据时效分层**:实时(新浪指数regime/lite个股)可信;Tushare daily 聚合(涨跌家数)T日收盘滞后,喂 codex 必标"T日收盘聚合, 盘中滞后"口径;T-1 EOD(评分/资金/位置)是"昨日定稿基准"可引用,非盘中新结论。
7. **MR-Eval 反哺原则**:主样本 = 全 watchlist 无条件每日快照(防幸存者偏差,非只记触发的);append-only(预测先于结果冻结);每条快照带市场状态(regime/宏观/宽度,用于按"世界状态"分桶 / 剔除特殊期如15股灾/AI暴涨);结果用 Tushare 真收盘机械算 + 指数基准算超额;反哺人工拍板,不自动调参(样本不足时自动=追噪音)。盘中触发(A)是该样本的带情境子集,分开存不混。

   **A/B 两条样本线区分(不可混)**:

   | | B 主样本(无偏全截面) | A 盯盘样本(触发子集) |
   |---|---|---|
   | 写入时点 | EOD 每天5点各票一条 | 盘中触发那一刻即时一条 |
   | 写入者 | eval_recorder(EOD调) | intraday notify(盯盘调) |
   | 数据 | T日定稿因子 | 触发时实时快照+当时regime+T-1基准 |
   | 文件 | factor_snapshots.jsonl + factor_results.jsonl | 独立盘中触发jsonl(另文件) |
   | 落点 | E1(已做 PR#22) | 并入 C2c(依赖盘中T-1基准) |

   铁律:A ⊂ B 但**分开存 / 分开记 / 分开写入时点**;A 绝不冒充 B 全样本(否则幸存者偏差污染反哺);分析按 (trade_date, code) join。E1 只立 B 线;A 线归 C2c,现未动。
8. **邮件输出设计**:邮件正文 = 精简摘要(大盘/宏观/赛道/持仓详情/观察池高分清单/明日重点);完整40票详情(claude.md)与全量数据(payload.json)走附件。正文不放观察池个股详情(持仓保留)。
9. **部署 = 基础设施即代码**:v2 三服务(api/intraday/eod-timer)unit 模板在 `deploy/`,`EnvironmentFile=/etc/vaxstock/vaxstock.env` 统一收口;EOD 走 systemd timer(凌晨05:00 + `Persistent=true` 补跑防漏样本),非 cron。v1(`/opt/stock-report`)除 backtest cron 外全退役。
10. **EOD Prediction 线(待实现,MR-Eval E4) = zz800 seed → 用户 universe 自我迭代**:

   **目标**:以 zz800 回测得到的当前 `right_side_score` 因子/阈值为 seed model,在用户持仓+观察池 universe 上形成"预测 → 核实 → 预测 → 核实"闭环。每天 05:00 跑 EOD 时,拿到的是上一交易日(T-1)已定稿真数据;EOD 落盘后立即基于 T-1 因子预测下一交易日 T 的 09:30 后走势/动作;再到 T+1 05:00 EOD 拿到 T 日真收盘后核验预测收益/超额/偏离。长期 day-by-day 积累,用于人工升级择股框架,**不自动调参**。

   **时间线例子(绝对日期)**:
   - `2026-07-02 05:00` 跑 EOD,报告基准日为 `2026-07-01`(T-1 真数据)。
   - 同次 EOD 后先核验历史预测中 `target_trade_date=20260701` 的预测结果。
   - 随后基于 `baseline_trade_date=20260701` 生成 `target_trade_date=20260702` 的 EOD predictions。
   - `2026-07-03 05:00` 跑出 `2026-07-02` 真数据后,核验 `target_trade_date=20260702` 的预测。

   **Step 0(本文件先行任务)**:
   - 明确目标:Prediction 线验证的是"当时策略动作是否正确",不只是 score 档未来收益。
   - 明确文件落点/命名/作用(见下表),后续 PR 不再新造隐式路径。
   - 明确 replay/live 区分:已有地基数据可重放生成预测,但必须标 `generation_mode=replay`;未来真实每日生成的预测标 `generation_mode=live`,报告中分开统计。

   **文件落点、名字与作用(单一真相)**:

   | 文件/目录 | 写入者 | 类型 | 作用 | 幂等/不可变规则 |
   |---|---|---|---|---|
   | `reports/<YYYY-MM-DD>/payload.json` | `report.store.store_report` | EOD 原始 SSOT | T 日 EOD 全量 payload,可重渲染/追溯 | 同交易日重跑可覆盖(报告产物) |
   | `reports/<YYYY-MM-DD>/claude.json` | `report.store.store_report` | EOD compact | 给 Claude/盘中 T-1 基准使用的压缩结构 | 同交易日重跑可覆盖 |
   | `reports/<YYYY-MM-DD>/claude.md` | `report.store.store_report` | EOD 人读报告 | 邮件附件/人工复盘 | 同交易日重跑可覆盖 |
   | `var/eval/factor_snapshots.jsonl` | `services.eval_recorder.record_snapshots` | B线输入快照 | 全 holdings+watchlist 每日无条件因子快照;防幸存者偏差 | append-only;同 `(trade_date,code)` 幂等跳过 |
   | `var/eval/factor_results.jsonl` | `services.eval_recorder.backfill` | B线结果 | 对 `factor_snapshots` 的 T+1/3/5/10/20/30 真收益、基准收益、超额回填 | append-only;仅新增 horizon 时追加 |
   | `var/eval/layer2_report_<trade_date>.md` | `research.layer2_eval.run_layer2` | B线分析报告 | score 档 × `regime|macro_regime` 分桶的前瞻收益/超额/胜率 | 可重生成覆盖 |
   | `var/forecast/forecasts.jsonl` | `services.forecast_recorder.record_forecast` | A线盘中触发预测 | 盘中触发时冻结 codex 结构化预测+T-1基准+lite快照+regime | append-only;触发样本,不可冒充全样本 |
   | `var/prediction/eod_predictions.jsonl` | **待建** `services.eod_predictor` | EOD Prediction 输入/动作 | 基于 `baseline_trade_date=T-1` EOD 真数据,预测 `target_trade_date=T` 的动作/方向/置信度 | append-only;同 `(baseline_trade_date,target_trade_date,code,rule_version,generation_mode)` 幂等 |
   | `var/prediction/eod_prediction_results.jsonl` | **待建** `services.prediction_evaluator` | EOD Prediction 核验结果 | T+1 EOD 后核验 target 日真实收益、benchmark、excess、方向命中、动作命中、偏离 | append-only;同 `prediction_id+horizon` 幂等 |
   | `var/prediction/prediction_layer2_report_<trade_date>.md` | **待建** `research.prediction_eval` | EOD Prediction 分析报告 | action/direction/confidence × 环境/概念分桶,评估预测动作而非单纯 score | 可重生成覆盖 |
   | `var/prediction/rule_suggestions_<trade_date>.md` | **待建** `research.rule_suggester` | 研究建议 | 基于足量样本提出规则升级建议;只建议,不自动改生产规则 | 可重生成覆盖;人工审核后另开 PR 升级 rule_version |

   **任务拆解(后续 PR 顺序)**:
   - **E4-1 Schema + writer**:`services/eod_predictor.py` 定义 prediction record,生成 `prediction_id`,append-only 写 `eod_predictions.jsonl`,并加单测。
   - **E4-2 Replay bootstrap**:读取已有 `factor_snapshots.jsonl`,按当前 `zz800_seed_v1` 规则重放生成 `generation_mode=replay` 的历史 predictions;最大化利用已上传地基数据。
   - **E4-3 Evaluator**:`services/prediction_evaluator.py` 优先复用 `factor_results.jsonl` 核验 replay predictions;live 场景可从 Tushare daily 机械算收益/超额;缺数据不写假结果。
   - **E4-4 接入 EOD**:`services/eod.py` 在报告落盘后先核验 pending predictions,再生成下一交易日 predictions;prediction 失败只 warning,不影响 EOD 三件套落盘。
   - **E4-5 Prediction Layer2**:`research/prediction_eval.py` join predictions/results,按 `action`/`direction`/`confidence_bucket`/`regime|macro_regime`/`concept` 分桶;`generation_mode=live/replay` 分开展示;样本不足不下结论。
   - **E4-6 EOD 摘要接入**:`report/claude_md.py` 增加"昨日预测核验"小节(预测数、已核验、action 命中、正超额率、pending),无数据时显示"待积累"。
   - **E4-7 Rule suggestions**:`research/rule_suggester.py` 只输出规则升级建议和证据,不自动改参数;升级必须人工确认并 bump `rule_version`。

   **记录字段最低要求**:
   - prediction: `prediction_id/generated_at/generation_mode/baseline_trade_date/target_trade_date/code/name/group/concepts/features_ref/prediction/rule_version/model_version`。
   - `features_ref` 至少含 `price_at_baseline/right_side_score/right_side_grade/main_inflow_10d/np_yoy/holder_change_pct/position_20d_pct/market_regime/macro_regime/ai_position_ceiling`。
   - result: `prediction_id/evaluated_at/baseline_trade_date/target_trade_date/code/horizon/actual/evaluation`。
   - `evaluation` 至少含 `direction_hit/positive_excess/action_hit/deviation/error_type`。

   **硬边界**:
   - Prediction 线验证"动作是否正确";现有 `factor_snapshots/results` 验证"score 档未来收益",两者互补但不可混。
   - replay 是历史输入重放,只用于快速 bootstrap 当前规则,报告必须与 live 分开。
   - 所有预测先于结果冻结;任何结果回填不得修改 prediction 原文。
   - 规则修复只能以新 `rule_version` 前滚,禁止回写历史预测或静默改变旧版本含义。

---

## 10. 踩坑与防护记录

- **依赖守卫测试**用静态 ast 解析 import,**绝不用运行时 sys.modules 检查**(pytest 同进程跨测试污染,PR#10)。
- **PR base 必须 main**:每个 PR 只从 main 切、只装一件事,别为自测 merge 别的未合 PR 进分支(MR2/PR#9)。
- **TypedDict 不能用 `dataclasses.asdict`**:TrackResult 是 TypedDict(运行时即 dict),序列化用 `dict(tr)`(PR#11)。
- **numpy 布尔不能用 `is` 比较**:`np.bool_(True) is True` → False;numpy 来源布尔字段断言用 `bool(x) is True`(PR#15)。
- **store 落盘路径**必须绝对 `config.REPORTS_DIR`,不用相对 `"./reports"`(cron workdir 漂移 + 落仓库根被 git 跟踪,PR#14)。reports/ 与 *.egg-info/ 已 gitignore。
- **pyarrow 必须显式声明**:MacroCache parquet 需 pyarrow,pandas 3.x 不自带;不声明则运行时 ImportError 被 collect 的 try 吞成静默 available=False(PR#19)。
- **触网墙钟超时统一 daemon线程+join,不用 ThreadPoolExecutor**(其 `shutdown(wait=True)` defeat 超时)。akshare(`_ak_safe`)/yfinance(`_yf_safe`)/Tushare(`source._safe_call`)均此模式。
- **lite=1 必须前置于 `refresh_regime()`**:冷缓存 refresh_regime 扫全市场卡数分钟,lite 盘中查询须在它之前 return。
- **东财已砍**:VPS 连不上东财(502/000),板块④/热门赛道⑦/opportunity⑧ 诚实返回 available=False,不 import 旧模块、不臆造;将来用 watchlist AI/机器人成分自聚合替代。
- **margin 等滞后维度**:summary 应带 stale/lag_days 标注(待办),让宏观维滞后对报告透明(凌晨5点跑也救不了 margin 滞后)。邮件 digest 已对 margin stale 标 data_date(PR-Digest)。
- **api 生产依赖必须主 dependencies, 不放 `[dev]`**:fastapi/uvicorn 是 api 生产运行必需(`services/api.py` 顶层 import fastapi + `__main__` uvicorn.run)。曾误把 fastapi 放 `[dev]`、uvicorn 完全没声明 → 生产 `pip install -e ".[tracks]"`(不带 dev)起 api 即 ModuleNotFoundError(实测 6/26 切线上时 uvicorn 缺,PR#24 修)。`[dev]` 只放测试桩(pytest/httpx)。同 pyarrow(PR#19)——依赖声明缺失被开发环境手动装侥幸掩盖,生产暴露。
- **依赖缺口的检出**:切线上前必须在干净 venv 验 `python -c "import <生产入口模块>"`(如 `import vaxstock.services.api`),而非只跑 pytest(测试装了 `[dev]` 会掩盖生产缺口)。
- **codex 盘中链路依赖三项齐全**:`CODEX_URL`(CLIProxyAPI 端点,如 `http://127.0.0.1:8317/v1/chat/completions`)+ `CODEX_TOKEN`(CLIProxyAPI 的 api-key,**不是** Codex OAuth token)+ `codex_model`(须在 CLIProxyAPI `/v1/models` 列表内,如 `gpt-5.5`)。
  - 故障对照:缺 URL → `Invalid URL None`;key 错 → 返回 `{"error":"Invalid API key"}`;model 不认 → 返回 JSON 但无 choices(报 `KeyError 'choices'`)。
  - 配置位置:可放 `secrets.json` 或 `/etc/vaxstock/vaxstock.env`,环境变量优先(`_ENV_OVERRIDES` 映射 `codex_url/codex_token/codex_model → CODEX_URL/CODEX_TOKEN/CODEX_MODEL`)。生产由 systemd `EnvironmentFile` 注入;手动跑须先 `set -a; . /etc/vaxstock/vaxstock.env; set +a` 导入,否则读不到。
  - 验证:`curl` 直打端点带 `Bearer` key,返回含 `choices` 即通。
  - 历史教训:C2a/C2b 期间该链路因 url/key 未配通,盘中一直静默走"无研判"分支;2026-06-26 PR-A 验证时首次点亮。
