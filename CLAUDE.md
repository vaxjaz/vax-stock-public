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

- [ ] **MR1 地基层**:`__init__/config/util/indicators(technical,valuation,regime)` + 骨架 + .gitignore + secrets.json.example
- [ ] **MR2 sources 层**:从巨石拆 eastmoney.py / sina.py,整合 tushare_src.py / us_market.py
- [ ] **MR3 indicators 补全**:scoring.py(right_side_score/derived_metrics)、macro.py(宏观7维)
- [ ] **MR4 analysis 层**:stock_item / holdings / ai_track / opportunity / hot_sector
- [ ] **MR5 report 层**:builder / render / email + 新增 store.py(报告落盘:时间戳/latest/hash)
- [ ] **MR6 services 层**:api.py(去副作用) / intraday / cron_daily,research/ 归位
- [ ] **MR7 文档同步**:README 版本号、宏观维度数(7维)、AI赛道体系、社融脉冲入 changelog

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