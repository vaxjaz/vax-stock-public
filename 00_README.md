# 00 README — Vax A股分析系统

> **作者**: Vax · **当前版本**: v1.3 (2026-06-13) · **架构**: 双源单职责 + 10段强制模板 + Macro Regime
> **本文件是新窗口启动的唯一入口**,任何 Claude 新会话必读这一份。
 
---

## 一、项目是什么

这是一个 Claude+VPS 协作的 A 股分析系统。**Claude 负责智能分析**,**VPS 负责数据采集**,**用户(Vax)负责持仓更新和观察池调整**。

### 1.1 三方职责

| 角色 | 职责 | 数据所有权 |
|---|---|---|
| **Claude(本 project)** | 每日报告分析,持仓变更生成,策略迭代,文档维护 | `holdings.json` (持仓真相) |
| **VPS** `/opt/stock-report/` | 每日 16:00 cron 跑数据采集,生成 `claude_stock_prompt_*.md` | `watchlist.json` (观察池) + 6维度宏观缓存 |
| **用户** | 上传日报,买卖后给截图,跑 manage.py 调观察池,每月更新 yield_10y_pct | 操作执行 + 一致性保证 |

### 1.2 单一数据源原则(SSOT)

**冲突时按优先级**:
- 持仓真相 → `holdings.json` > memory > VPS 报告任何字段
- 观察池 → VPS `watchlist.json` > 任何记忆
- 当日数据 → 当日上传附件 > web_search > Claude 训练记忆
- 策略版本 → `06_quant_framework.md` 顶部版本号 > memory 描述
---

## 二、Project 文件清单(应该 / 不应该)

### 2.1 应该在 Claude project 的文件

| 序号 | 文件名 | 类型 | 职责 | 更新频率 |
|---|---|---|---|---|
| 00 | `00_README.md` | 元信息 SSOT | 项目导读+启动checklist(本文件) | 文档结构变化时 |
| 01 | `01_principles.md` | 规则 SSOT | 投资原则+硬约束(科创板不可投/止损纪律) | 季度回顾 |
| 02 | `holdings.json` | 数据 SSOT ⚠️ | **持仓真相**(本地唯一) | 每次买卖后 |
| 04 | `06_quant_framework.md` | 规则 SSOT | 当前策略框架 v1.3 | 策略升级时 |
| 05 | `05_manage_commands.md` | 参考 | VPS manage.py 命令速查 | 新命令时 |
| 06 | `stock_report_enhanced.py` | 代码副本 | 供 Claude 理解主脚本逻辑 | 重大重构时 |
| 07 | `macro_indicators.py` | 代码副本 | 供 Claude 理解宏观采集 | 重大重构时 |
| 08 | `hot_sector_scanner.py` | 代码副本 | 供 Claude 理解热门赛道 | 重大重构时 |
| 09 | `opportunity_scanner.py` | 代码副本 | 供 Claude 理解机会仓 | 重大重构时 |
| 10 | `tushare_source.py` | 代码副本 | 供 Claude 理解 Tushare 调用 | 重大重构时 |
| 11 | `09_changelog.md` | 历史 | 变更日志(append-only) | **每次变更必须** |
| 12 | `10_known_issues.md` | 跟踪 | 已知 bug + workaround | 发现/修复时 |

### 2.2 绝对不应该在 Claude project 的文件

| 文件 | 原因 |
|---|---|
| `portfolio.json` | 已废弃(v2 双源架构后),持仓拆到 `holdings.json`,token 拆到 `secrets.json` |
| `watchlist.json` | 在 VPS,不应该在本地有副本(避免双向漂移) |
| `secrets.json` | 含 tushare_token,泄露后会被滥用 |
| `*.parquet` 缓存 | 数据缓存,只在 VPS |
| `regime_history.json` | VPS 运行状态文件 |
| `cron.log` / `stock_report.log` | VPS 日志 |
| 任何 `*_v1.bak.*` 旧版备份 | 保持 project 清爽,备份留在 VPS |

### 2.3 VPS 上的文件(只在 VPS,不上传 Claude)

| 文件 | 位置 | 内容 |
|---|---|---|
| `watchlist.json` | `/opt/stock-report/` | 观察池+赛道偏好 SSOT |
| `secrets.json` | `/opt/stock-report/` (chmod 600) | tushare_token + yield_10y_pct |
| `regime_history.json` | `/opt/stock-report/` | 短期 regime 平滑状态 |
| `opportunity_book.json` | `/opt/stock-report/` | 机会仓持仓 |
| `.cache_macro/*.parquet` | `/opt/stock-report/.cache_macro/` | 宏观6维度缓存 |
| `.cache_tushare/*` | `/opt/stock-report/.cache_tushare/` | Tushare 通用缓存 |
| `cron.log` | `/opt/stock-report/` | 运行日志 |
 
---

## 三、新窗口启动 Checklist(每次开新对话都跑一遍)

任何 Claude 新窗口启动后,在分析之前**必须完成这 5 步**:

1. **读** `/mnt/project/00_README.md` — 项目导读(本文件)
2. **读** `/mnt/project/holdings.json` — 持仓真相
3. **读** `/mnt/project/06_quant_framework.md` 顶部 — 确认策略版本
4. **读** `/mnt/project/09_changelog.md` 顶部 3 条 — 最近发生了什么
5. **读** 用户上传的当日 `claude_stock_prompt_YYYYMMDD_HHMM.md` — 今日数据
   完成 5 步前,**不要开始分析**。任何冲突 → 按 SSOT 优先级处理(见 1.2)。

---

## 四、Claude 每次分析必须遵守的规则

### 4.1 持仓校验(强制 fail-safe)

读完 `holdings.json` 后,**提取所有 code**,检查这些 code 是否都在今日 VPS 报告里:

- ✅ **全部都在**: 正常进入 10 段输出
- 🚨 **有缺失**: 必须在分析最开头红字警告 + 给 add-watch 命令,且本次持仓段标"数据缺失"
```
🚨 警告: 持仓股 600276(恒瑞医药) 不在今日 VPS 报告中!
请在 VPS 执行:
    python manage.py add-watch 600276 恒瑞医药 --concepts "医药,创新药,化学制药"
本次分析持仓段标"数据缺失",仅以基本面+板块归属判断
```

### 4.2 10 段强制输出模板(v1.3)

接收 `claude_stock_prompt` 报告后,**必须按 10 段输出**。每段都要有(无信号也写"无,原因X"),禁止合并/压缩/跳过:

| 段 | 标题 | 内容 |
|---|---|---|
| ① | 大盘环境 | 短期regime + 涨跌家数 + 北向 + 普涨/结构性 |
| ② | **宏观环境 v1.3** | Macro Regime + 6维度信号汇总 + 短期×宏观叠加仓位建议 |
| ③ | 美股传导 | 赛道ETF对照A股板块表 + 顺风/逆风 |
| ④ | 板块结构 | 强势/弱势TOP + 热门赛道今日表现 |
| ⑤ | 持仓评估 | holdings.json 为准,逐只:今日表现 + 板块归属 + 操作判断 |
| ⑥ | 观察池信号 | v1.2评分分档(≥2.0可介入/1.0-1.5观察/<0.5回避)+ 派发陷阱标记 |
| ⑦ | 热门赛道扫描 | 报告第四节算法龙头 + 是否纳入观察池 + 理由 |
| ⑧ | 机会仓信号 | 报告第七节信号A/B + 是否参与 + 理由 |
| ⑨ | 风险预警 | 派发/价值陷阱/趋势恶化集群 + 宏观异常变化高亮 |
| ⑩ | 明日策略 | 必做/等待/不做 + 3-5个盘中跟踪指标和阈值 + 基于短期×宏观叠加给仓位建议 |

**深度可伸缩,范围不可省略**。

### 4.3 宏观环境异常变化高亮规则(段②)

正常呈现 + 主动强调以下变化:

| 触发条件 | Claude 必须强调 |
|---|---|
| 任一维度信号从 ✅ 翻转为 ❌(或反向) | 🚨 加粗 + "信号翻转" |
| 任一指标进入历史前 10% 或 后 10% | ⚡ "历史极值" |
| ERP σ倍数 > +2 或 < -2 | 🔔 "极端机会/风险" |
| 单日 ETF 净申赎 > +20亿 或 < -20亿 | 💥 "放量异动" |
| 融资买入比单日变化 > +2pp 或 < -2pp | 🔥 "杠杆剧烈变化" |

### 4.4 短期 × 宏观双层 Regime 叠加(段⑩明日策略仓位建议)

| 短期 v1.2 | 宏观 v1.3 | 应对策略 | 仓位建议 |
|---|---|---|---|
| momentum | 🟢看多 | 强势上涨期 | 加仓 60-80% |
| momentum | 🟡中性 | 谨慎跟随 | 维持 40-60% |
| momentum | 🔴看空 | **顶部警告** | 降至 30-40% |
| value | 🟢看多 | **价值底确认** | 加仓 70-90% |
| value | 🟡中性 | 选股优先 | 维持 40-60% |
| value | 🔴看空 | 价值陷阱多 | 维持 30-40% |
| panic | 🟢看多 | **黄金底** | 大胆加仓 80-100% |
| panic | 🟡中性 | 逐步建仓 | 加仓 50-70% |
| panic | 🔴看空 | 双杀,坚守现金 | **降至 20% 以下** |

### 4.5 永远不做的事

| 禁止 | 原因 |
|---|---|
| 不给具体买卖价格指令(如"明天在46.50加仓500股") | 用户要的是方向判断,不是执行指令 |
| 不直接修改 `holdings.json` | 必须用户确认后生成新版,用户手动替换 |
| 不直接对 VPS 发命令(用户跑) | VPS 是用户的,Claude 只给命令清单 |
| 不引用过时的训练数据当作"今日价格" | 必须可追溯到附件 JSON 字段或 web_search 当日结果 |
| 不在没有 holdings.json 校验的情况下分析 | fail-safe 规则,必须先校验 |
 
---

## 五、用户每次/定期需要做的事

### 5.1 每日(交易日 16:30 之后)

1. 从 VPS 下载 `claude_stock_prompt_YYYYMMDD_HHMM.md` 和对应的 `.json`
2. 上传到 Claude 对话
3. Claude 自动按 10 段输出分析
### 5.2 买卖后(立即)

1. 在券商 app 截图持仓页
2. 上传截图 + 说"同步持仓"
3. Claude:
    - OCR 识别截图
    - 对比当前 `holdings.json`
    - 输出 diff 表(等用户确认)
    - 用户确认后,Claude 生成新版完整 `holdings.json`
4. 用户:
    - 复制 Claude 给的 `holdings.json` 内容,替换本地文件
    - **在 Claude project 删除旧 holdings.json,上传新版**
    - 如新持仓 code 不在 VPS watchlist,Claude 会给 add-watch 命令,用户去 VPS 跑
### 5.3 调观察池(用户驱动 VPS)

直接在 VPS 跑命令,Claude 不参与:

```bash
cd /opt/stock-report
python manage.py add-watch <code> <name> --concepts "概念1,概念2"
python manage.py remove-watch <code>
python manage.py status                  # 查看当前 watchlist
python manage.py concepts <code> --set "新概念A,新概念B"  # 改概念
```

### 5.4 每月维护

| 项 | 频率 | 操作 |
|---|---|---|
| 更新 `secrets.json` 的 `yield_10y_pct` | 月初 | 查东方财富/中国债券信息网,改为最新10年国债收益率值 |
| 检查 `.cache_macro/` 磁盘占用 | 月初 | `du -sh .cache_macro/`,通常 1-2GB 内 |
| 审视 `holdings.json` 准确性 | 周末 | 对照券商持仓核对 |
| 看 changelog 是否漏更新 | 周末 | 翻一遍最近 7 天有没有变更没记录 |

### 5.5 季度回顾(每季度末)

| 项 | 操作 |
|---|---|
| 回测 IC 因子 | 用最新3个月数据重跑 backtest,看权重是否需要调整 |
| 复盘 `01_principles.md` | 看投资原则是否还合理 |
| 审视 v1.x 策略 | 是否需要升级到 v1.4 |
| 清理 changelog | 把太老的归档到 archive/ |
 
---

## 六、后续迭代"五要"

1. **要更新 changelog**: 任何变更立即在 `09_changelog.md` 顶部 append 一行
2. **要同步 memory**: 涉及核心状态的变更(策略版本/持仓/工作流),同时改 memory 和文档
3. **要先做难度评估再实现**: 新需求先评估代码量/数据可获得性/风险,再决定做不做
4. **要分阶段交付**: 大需求拆分阶段,每阶段独立可验证
5. **要做 mock 测试**: 任何新模块写完先跑 mock 数据测试,通过再部署 VPS
## 七、后续迭代"五不要"

1. **不要直接改 portfolio.json**: 已废弃文件,直接 ignore
2. **不要把 secrets.json 上传 Claude project**: token 会泄露,我能看到上下文里的所有内容
3. **不要破坏 SSOT 原则**: 同一信息只有一个权威来源
4. **不要绕过 manage.py 直接改 watchlist.json**: 用命令保证数据完整性校验
5. **不要在不同窗口手动维护持仓信息**: 持仓只能截图驱动更新
---

## 八、应急 FAQ

### Q1: VPS cron 跑失败怎么办?
A: SSH 到 VPS 看 `cron.log` 最后几行,通常是接口限流或网络抖动。手动跑 `python stock_report_enhanced.py` 重试。

### Q2: Claude 报"持仓股不在 VPS 报告里"?
A: 跑 `python manage.py add-watch <code> <name> --concepts "..."`,下个交易日报告就有了。

### Q3: holdings.json 和券商截图不一致?
A: 截图为准。重新跑"同步持仓"工作流(见 5.2)。

### Q4: 宏观维度某项报错(errors 不为空)?
A: 看 `10_known_issues.md` 是否已记录。如果是新 bug,加进去。常见:
- `yc_cb` 无权限 → secrets.json 加 `yield_10y_pct` fallback
- `000985.SH` 偶尔抽风 → 代码已 fallback 到 `000300.SH`,自动处理
### Q5: 想加新观察池标的怎么办?
A: 直接 VPS 跑 `python manage.py add-watch <code> <name> --concepts "概念"`,下日报告生效,Claude 自动识别。

### Q6: 想升级策略到 v1.4 怎么办?
A: 跑流程:
1. 在 Claude 新窗口讨论需求
2. Claude 给难度评估
3. 分阶段实现 + mock 测试
4. 部署 VPS
5. 更新 `06_quant_framework.md` 到 v1.4
6. 更新 `09_changelog.md`
7. 同步 memory
### Q7: tushare token 泄露了怎么办?
A: 立刻去 tushare.pro 后台重置 token,更新 VPS 上的 `secrets.json`,把旧 token 加入 `10_known_issues.md` 标"已废弃"。

### Q8: 新窗口的 Claude 给出错误的输出格式(比如只有 8 段)?
A: 直接指出"请按 00_README.md 第 4.2 节的 10 段模板重新输出"。如果反复出问题,检查 memory 里 #4 是否还存在。
 
---

## 九、版本与维护

- 文档版本: v1.0 (2026-06-13 建立)
- 适配系统版本: v1.3
- 维护者: Vax + Claude (协同)
- 修改本文件需同步更新 `09_changelog.md`
 