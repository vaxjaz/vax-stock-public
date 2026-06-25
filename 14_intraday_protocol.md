# 14_盘中实时分析协议 (Intraday Protocol)

> 适用范围: 盘中(09:30–15:00 CST)用户口头/简写给票, 经 VPS HTTP API 实时拉数并分析。
> 与 EOD 日报(06_quant_framework 10段模板)是**两套契约**, 不互相替代。
> 定稿决策: 用户 2026-06-22 三项 + 后续两项确认。

---

## 0. 数据通路 (硬约束)

- **API**: `http://vaxjaz.duckdns.org/`  (VPS 上 stock-api 服务, systemd 常驻)
  - `GET /health` — 探活, 返回 regime/tushare点数/今日次数
  - `GET /quote?codes=600276,600900` — 多票实时报价(Sina), 秒级, 无配额压力
  - `GET /market` — 大盘 regime(短线三态机) + 涨跌家数
  - `GET /analyze/{code}` — 单票完整四维(build_stock_item 流水线), 较慢(拉多个Tushare接口)
- **会话机制(关键)**: 域名白名单只在**会话创建时**注入沙箱。必须在
  `vaxjaz.duckdns.org` 已加入 `设置→Capabilities→Additional allowed domains`
  **之后新建的会话**里调用, 否则报 `Host not in allowlist`(无法在该会话内修复, 只能弃用)。
- **端口**: 服务在 80。沙箱出网仅走 80/443, 非标准端口(如8000)被丢弃。
- **配额**: `MAX_ANALYZE_PER_DAY=300`(/analyze 计数, /quote 不计)。

---

## 1. 解析层: 用户怎么给票 → 我怎么命中

**默认路径 = 临时票直分析。** 盘中给的票大多是临时指定, 不一定在持仓/观察池/任何册中。
任意 A 股(科创板 688 除外, 用户不可交易)均可直接 `/analyze`。

| 用户输入 | 触发 | 数据源 | 处理 |
|---|---|---|---|
| 纯代码 `600276` / 名称 `恒瑞医药` / 混合 `看看恒瑞和长电` | **默认** | 任意A股 | 解析出代码 → 直接分析 |
| `持仓` / `我的仓` / `持仓怎么样` | 显式 | `holdings.json` | 读 holdings 键(当前3只), **不读 watchlist.json** |
| `观察池` / `扫一遍` / `观察池信号` | 显式 | `watchlist.json` 的 `watchlist` 键 | 全量(当前41只), **一只不漏** |
| `医药强势的` / `板块` 等 | 显式 | `hot_sector_scanner`: `find_hot_sectors()`→`fetch_sector_constituents()` | 板块→成分股→筛选 |

**解析规则**:
- 名称→代码: 经 Sina 接口或本地 watchlist/holdings 名称匹配。匹配不到 → 明确报"无法解析XXX", 不猜。
- 688 开头(科创板): 标注"用户不可交易", 仍可分析但提示。
- 后三种(持仓/观察池/板块)**必须用户显式说**才触发; 否则一律当临时票直分析, 不主动翻名册。

---

## 2. 持仓 SSOT (不可混淆)

- **持仓真相 = `holdings.json`**(本地维护, 截图驱动更新)。VPS 不读此文件。
- `watchlist.json` 的 `holdings` 键为空, **永不作为持仓来源**。
- 当前持仓(holdings.json, 更新 2026-06-18):

  | 代码 | 名称 | 成本 | 股数 |
    |---|---|---|---|
  | 600276 | 恒瑞医药 | 46.844 | 700 |
  | 600900 | 长江电力 | 26.962 | 1100 |
  | 601138 | 工业富联 | 73.241 | 100 |

- 观察池 = watchlist.json `watchlist` 键, 当前 41 只(见文件)。
- 券商截图与 holdings.json 冲突时: 截图优先, 我生成 diff + 新版 holdings.json, 用户手动替换并重新上传后才标"已采纳"。

---

## 3. 未结算数据处理 (严格模式 — 用户决策)

盘中资金流、RSI、MACD、均线均以**当前未收盘价**作"今日收盘"计算, 是**代理值, 未结算**。

**铁规**:
- **盘中不发布 right_side_score 评分数值。** 评分(v1.2)是 EOD/结算因子, 盘中给数 = 用代理值冒充结算结论, 违反 P0 数据完整性。
- 盘中只报: **价格 / 涨跌幅 / 振幅 / 量能(量比) / 位置(20日·52周·PE分位) / 硬否决预警 / 提示**。
- 资金流盘中仅标"方向参考(未结算)", 不计入任何评分。
- 真实评分、完整四维结论 → **以当日 EOD 报告为准**。

**仍可盘中给出的硬判断**(因其不依赖结算价的微小漂移):
- **一级硬否决预警**: 52周位置 ≥95% **且** PE历史分位 ≥95% → 🚨 极端高位, 任何资金信号不豁免。
- **二级高位提示**: 52周 >85% 或 20日 >90%。
- **派发三件套预警**: 换手Z>2 + 户数分散 + 10日净流出 三者齐 → 🚨(注: 户数为季度值盘中稳定, 换手Z/10日流出为盘中代理, 标注之)。

---

## 4. 输出粒度 (先精简, 喊"详细"展开 — 用户决策)

### 默认: 精简对比表 + 逐票一行动作
- 一个横向表: 代码 | 名称 | 现价 | 涨跌% | 振幅% | 量比 | 20日位置 | 52周位置 | PE分位 | 否决预警 | 一行提示
- 表下: 每票一行动作判断(持有/观察/回避/触发X否决, 不报评分数)
- 顶部: 大盘 regime(/market) + 数据时间戳

### 用户喊"详细": 完整裁剪版(EOD 10段的盘中子集)
保留段: ① 市场环境 ⑤ 持仓评估(若含持仓) ⑥ 观察池信号(不报评分, 报分档语义+否决) ⑨ 风险预警 ⑩ 盘中策略(3-5个阈值指标)
降级段: ② 宏观6维(盘中数据多为日频, 若取不到标"EOD为准") ③ 美股传导(隔夜, 盘中不变) ④⑦⑧(板块/机会仓, 按需)

---

## 5. 批量扫描 (观察池/板块 — 用户决策: A 全量)

**A 模式(锁定)**: 批量场景**全量逐个 `/analyze`**, 每只完整四维, **一只不漏**(规则3)。
- 观察池41只 ≈ 41次 /analyze, 串行约3-5分钟, 占当日上限约14%。
- 执行: 先打 `/market` 取 regime → 逐个 `/analyze/{code}` → 汇总成对比表。
- **即便全量 analyze, 盘中仍不发布评分数值**(规则3优先), analyze 结果用于位置/否决/量能判断。
- 单只失败(超时/无数据): 标"数据缺失", 继续下一只, 不中断、不跳过名册。

---

## 6. 执行顺序 (每次盘中分析)

1. `/health` 或直接 `/market` — 确认服务活 + 取真实 regime(默认momentum是初始值, 必须打/market才真实)
2. 解析用户输入 → 确定票池(临时/持仓/观察池/板块)
3. 临时/少量 → 逐个 `/analyze`; 批量 → A模式全量 /analyze
4. 套本协议输出(默认精简, 喊详细展开), **不报评分, 标注未结算**
5. 名册核对: 若为持仓/观察池场景, 输出前核对数量(holdings 3 / watchlist 41), 缺一报🚨

---

## 7. 安全红线

- token 绝不进 URL / 对话 / project 文件。当前查询端点免鉴权(方案②: 只读、行情衍生、非PII + 域名难枚举 + 每日上限)。
- ⚠️ **已知未决**: watchlist.json 的 data_sources.tushare_token 为明文, 已暴露于对话上下文。建议重置并拆入 secrets.json(用户知情, 决定权在用户)。

---

## 8. 盘中 codex 自动研判链路 (2026-06-24 上线·已验通)

> 在第0节数据通路 + 第3节未结算铁规之上,新增"自动盯盘 → AI研判 → 推送"闭环。
> 与人工盘中分析(第1–6节)并行,互不替代。

### 8.1 链路
```
intraday_watch 轮询 /quote(秒级,免费)
  └─ 命中 watch_rules 价位触发(粗筛)
       └─ GET /analyze/{code}?lite=1 拉盘中快照
            └─ 喂 VPS本机 codex 研判
                 └─ 研判文本并入微信/邮件推送
```
触发门槛不变,codex 仅在命中时调用(省 token / 不刷屏)。

### 8.2 lite 快照端点 `GET /analyze/{code}?lite=1`
- **含**: 现价/涨跌/振幅/成交额 + MA5/10/20/60 + 各均线乖离 + ma_trend + 20日/52周位置 + 量比5d + RSI14 + MACD(全部来自 实时+历史K线)
- **严格剔除(第3节铁规)**: right_side_score 三件套(score/grade/signals)+ T-1 滞后的主力资金流(Tushare moneyflow 是昨日值,盘中不可当实时)
- 不计 `MAX_ANALYZE_PER_DAY` 配额
- **必须前置于 `refresh_regime()` 直接返回**: lite 输出不含 regime;若先调 refresh_regime,regime 冷缓存时会扫全市场,实测把 lite 拖到 2分43秒(已修)
- 冷缓存首次 ~3–10s(串行3个Tushare接口,各≤12s超时),当日热缓存 <1s

### 8.3 codex 部署 = CLIProxyAPI
- `router-for-me/CLIProxyAPI`,OpenAI 兼容,VPS 本机 **8317** 端口
- `POST /v1/chat/completions` + `Authorization: Bearer <api-key>`(api-key 来自 CLIProxyAPI config.yaml 的 api-keys)
- **model: `gpt-5.4`**(选型:指令遵循稳、速度够、省高级配额;备选 gpt-5.5 更强但费配额、gpt-5.4-mini 快但弱模型易破铁律)
- 配置走 `secrets.json`: `codex_token` / `codex_url` / `codex_model`(绝不进对话/URL/project)
- 注: CLIProxyAPI 底层走 Codex/Response 协议(返回 id 带 resp_ 前缀),但对外以标准 chat.completion 结构暴露,`choices[0].message.content` 可直接解析

### 8.4 codex 研判铁律 (`intraday_rules.md` = system prompt)
继承第3节,对 AI 输出硬约束:
1. 不出 right_side_score 或任何 0–3.5 评分
2. 不出买卖价格/目标价/止损价数字指令(只给方向倾向)
3. 结论必须标"盘中未定论",措辞用 提示/倾向,不用 确认/应该买卖
4. 不臆测资金方向(快照已剔除资金,因 T-1 滞后)
5. ≤3 行
6. 按模板: 状态 / 倾向 / 触发 + 固定尾注"(盘中代理,未定论;资金与评分以EOD报告为准)"

- `intraday_rules.md` 与 `intraday_watch.py` **同放 `/opt/stock-report/`**,每次调用重读当 system 消息传入(无状态,改规则即时生效,不需重启/重训)
- 脚本有 fallback 极简规则,文件丢失也不破铁律
- **2026-06-24 实测**: gpt-5.4 六律全守,对快照解读无幻觉,质量达标

### 8.5 容错
- lite 失败 / codex 失败 → **不影响原始价位告警**(仍推送价位信息)
- `fetch_lite` 超时 45s(容纳冷缓存串行3接口最坏36s)

### 8.6 运维红线(踩坑记录)
- **systemd 单元名**: api = `stock-api.service`,盘中 = `intraday-watch.service`,**两个服务各管各的**
- 改 `api.py` / `tushare_source.py` / `stock_report_enhanced.py` → **必须 `systemctl restart stock-api.service`** 才生效(光重跑 intraday_watch.py 不重载 api 服务)
- 改 `watch_rules.json` → 热重载,无需重启;改 `intraday_watch.py` 本身 → restart `intraday-watch.service`
- **`_safe_call` 超时实现**: 必须用 daemon 线程 + `join(timeout)`;**禁用 `with ThreadPoolExecutor`**——其退出 `shutdown(wait=True)` 会反过来等卡死线程跑完,令超时形同虚设(2026-06-24 真实踩坑)