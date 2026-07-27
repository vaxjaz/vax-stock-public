# vaxstock v2 部署(systemd, 基础设施即代码)

v2 一刀切顶替 v1(不并存)。本目录是运行服务的 systemd 模板,env 统一收口到
`/etc/vaxstock/vaxstock.env`(已建,600)。**切换是运维动作(C3b),不在代码 PR 内。**

| 服务 | unit | 入口 | 说明 |
|---|---|---|---|
| API | `stock-api.service` | `python -m vaxstock.services.api` | FastAPI/Uvicorn,端口读 `API_PORT`(缺省80) |
| 盘中盯盘 | `intraday-watch.service` | `python -m vaxstock.services.intraday` | 长驻,触发推送 |
| EOD | `vaxstock-eod.service` + `.timer` | `python -m vaxstock.services.eod` | oneshot,次日凌晨05:00 由 timer 拉起 |
| 盘前预期刷新 | `vaxstock-preopen.service` + `.timer` | `python -m vaxstock.services.expectation_refresh` | oneshot,交易日 08:35 拉取 E 维数据；代码在 09:25 设置硬截止 |
| D线观察任务 | `vaxstock-dline-plan.service` | `python -m vaxstock.services.dline_plan` | EOD 成功后 `--no-block` 异步启动,消费 `var/forecast/current_job.json` |

> v2 入口已验:api(内部 uvicorn,`API_PORT` 缺省80)/ intraday(`[--once][--force]`)/ eod(oneshot,退出码 0/1)。

---

## v2 顶替上线步骤(一刀切,有数秒 api 停服窗口)

前置:`/etc/vaxstock/vaxstock.env` 已建(600),venv 已 `pip install -e ".[tracks,dev]"`。

1. 备份旧 unit:`cp /etc/systemd/system/{stock-api,intraday-watch}.service /root/v1-unit-backup/`
2. 禁旧 EOD cron:`crontab -e` 注释掉 `0 16 * * 1-5 ... stock_report_enhanced.py` 那行(避免 v1/v2 双 EOD)。**v1 backtest 那几条不动。**
3. 装 v2 unit:`cp deploy/*.service deploy/*.timer /etc/systemd/system/` ; `systemctl daemon-reload`
4. 切 api+intraday(配套):`systemctl restart stock-api.service intraday-watch.service`
5. 验证:`curl -s -m10 http://127.0.0.1/health` ; `systemctl status stock-api intraday-watch --no-pager | head`
6. 启 EOD 和盘前 timer:`systemctl enable --now vaxstock-eod.timer vaxstock-preopen.timer` ; `systemctl list-timers | grep vaxstock`
7. 手验一次 EOD:`systemctl start vaxstock-eod.service` ; `journalctl -u vaxstock-eod -n 30 --no-pager`

## 回滚(任一步失败)

- api/intraday:`cp /root/v1-unit-backup/*.service /etc/systemd/system/` ; `systemctl daemon-reload` ; `systemctl restart stock-api intraday-watch`
- EOD/盘前:`systemctl disable --now vaxstock-eod.timer vaxstock-preopen.timer` ; `crontab -e` 恢复 16:00 那行
- 说明:仅 unit 指向变化,v1 代码 `/opt/stock-report` 原样保留,回滚即恢复。

---

## Auto GitHub commit after EOD / pre-open / D-line / intraday triggers

`vaxstock-eod.service`, `vaxstock-preopen.service`, and
`vaxstock-dline-plan.service` call `python -m vaxstock.services.git_autocommit`
in `ExecStartPost`. The EOD and pre-open stages both whitelist `var/research`;
the pre-open stage whitelists no other generated tree. `intraday-watch.service`
is long-running, so `services.intraday` calls `git_autocommit --stage intraday`
immediately after a trigger forecast row is written.

Enable it explicitly in `/etc/vaxstock/vaxstock.env`:

```bash
GIT_AUTOCOMMIT_ENABLED=1
GIT_AUTOCOMMIT_PUSH=1
# optional
GIT_AUTOCOMMIT_REMOTE=origin
GIT_AUTOCOMMIT_BRANCH=main
```

The pre-open collector defaults to a 90-calendar-day global `report_rc`
window and at most 10 pages of 3000 rows. Optional environment overrides are
`EXPECTATION_REPORT_LOOKBACK_DAYS` and `EXPECTATION_REPORT_MAX_PAGES`.
Reducing the lookback below 90 or hitting the page cap does not create a
short-window substitute: the run records the source status and abstains from
all seller-consensus factors.

Safety rules:

- EOD stage only stages generated A/B/C/research data, the D-line job envelope, and market-only D-line feedback artifacts: `var/reports`, `var/eval`, `var/research`, `var/prediction`, `var/forecast/current_job.json`, `var/forecast/observation_jobs.jsonl`, `var/forecast/observation_coverage.jsonl`, `var/forecast/forecast_evolution.jsonl`, `var/forecast/market_health_events.jsonl`, `var/forecast/forecast_results.jsonl`, and `var/forecast/dline_reviews`.
- Pre-open stage only stages `var/research`.
- D-line stage only stages generated D-line task files: `var/forecast/current_job.json`, `var/forecast/current_tasks.json`, `var/forecast/current_tasks.md`, `var/forecast/observation_tasks.jsonl`.
- Intraday stage only stages live D-line/forecast trigger artifacts: `var/forecast/forecasts.jsonl`, `var/forecast/market_health_events.jsonl` plus the current D-line task context files needed to read the alert.
- If any non-whitelisted file is dirty, the autocommit step skips and prints the blocking paths.
- Push requires non-interactive GitHub credentials for root/systemd, such as SSH deploy key or a stored credential helper. The code never stores tokens.
- Git prompts are disabled (`GIT_TERMINAL_PROMPT=0`, `GCM_INTERACTIVE=never`); missing credentials fail fast in journal logs.
## Active market health check

`intraday-watch.service` also runs `services.market_health` inside its existing quote polling loop. During trading hours it evaluates at most once every 15 minutes by default; set `MARKET_HEALTH_INTERVAL_SECONDS` in `/etc/vaxstock/vaxstock.env` only when a reviewed cadence change is required. No separate timer or manual command is needed. A newly opened high-risk state sends one consolidated `[盘面体检] 高风险异常` notification; an unchanged state is suppressed, recovery is recorded, and recurrence starts a new episode. Runtime state is `var/forecast/current_market_health.json` (gitignored); append-only evidence is `var/forecast/market_health_events.jsonl`. User executions are not inputs.

## Private daily action artifact

After `vaxstock-dline-plan.service` reaches a terminal status, it refreshes `var/strategy/daily_action_latest.md` and sends the idempotent `[每日操作]` pre-market plan. During the session, the watcher atomically records per-task quote coverage in gitignored `var/forecast/current_observation_status.json`. After a trigger it also records restart-safe path state in gitignored `current_evolution_status.json`. After close it freezes versioned full-session coverage into append-only `observation_coverage.jsonl` and 15/30-minute plus last-verified-close paths into append-only `forecast_evolution.jsonl`; the next EOD backfills market-only `forecast_results.jsonl` and refreshes triggered-versus-qualified-no-trigger review reports. User executions are never inputs to D-line scoring. After 15:02 it reads same-day D-line v2 facts plus that coverage evidence, writes separate `var/strategy/close_review_<target>.md` / `close_review_latest.md` artifacts without overwriting the pre-market plan, and sends a separately idempotent `[收盘复盘]` email. A D-line trigger is never treated as an executed order; execution remains pending until confirmed holdings are updated. `status=done` sends the normal plan; `partial_done` / `partial_failed` / `missing_payload` sends an explicit degraded plan with all conditional adds disabled. These files contain private account amounts, are gitignored, and are never committed. Missing account data degrades to pending rather than fabricated amounts. The EOD process still writes A/B/C reports and queues D, but no longer sends the legacy digest email itself.

The daily action message includes the exact-baseline `var/evidence/convergence_<baseline>.json` brief after market context. It never substitutes a different-date latest view.
## Confirmed execution import

Create private `script/config/execution_confirmation.json` from a user-confirmed broker execution-detail screenshot plus a complete same-trade-date holdings screenshot, then validate before applying:

```bash
PYTHONPATH=src python -m vaxstock.services.execution_confirmation --input script/config/execution_confirmation.json --dry-run
PYTHONPATH=src python -m vaxstock.services.execution_confirmation --input script/config/execution_confirmation.json
```

The first command performs no writes. The second appends the confirmation event, reconciles it against `close_review_<trade_date>.json`, and atomically refreshes private `holdings_state.json`, `portfolio_state.json`, and `execution_review_*`. The tracked `holdings.json` remains the initial baseline. Re-running the identical confirmation is idempotent; a reused confirmation or execution id with different data is rejected.

## Quick complete holdings snapshot

For a broker holdings screenshot that confirms the complete current position
set but does not provide execution details, update the VPS-private
`holdings_state.json` directly. Position data never passes through Git:

```bash
bash deploy/vax-holdings --as-of YYYYMMDD \
  601138:1200:70.481 \
  002475:400:68.421
```

Each item is `CODE:SHARES:COST[:NAME]`. The command treats all items as one
complete snapshot, so an existing code omitted from the command is removed.
Known names/concepts and real entry history are preserved; a changed position
marks the old entry-history reconciliation stale instead of pretending it still
matches. The old private state is backed up under
`/var/backups/vaxstock/holdings`, the replacement is atomic, and the intraday
watcher is restarted only after a successful update. Use `--dry-run` to validate
without writing or restarting. Intraday consumption independently intersects
legacy rules and D-line tasks with current private holdings, so stale task files
cannot alert on sold stocks.

## D-line closeout retry

The next EOD runs `services.dline_closeout` after B-line backfill. Its replaceable operational status is `var/forecast/current_closeout_status.json`. `partial_data` names real missing evidence and `failed` names the failed stage; neither status fabricates intraday facts. Repeated retries are serialized and idempotent. User executions are never inputs.

```bash
set -a; . /etc/vaxstock/vaxstock.env; set +a
PYTHONPATH=src /opt/stock-reportv2/venv/bin/python -m vaxstock.services.dline_closeout --trade-date YYYYMMDD
```
## Strategy evidence ledger retry

EOD runs `services.evidence_ledger` after C-line result backfill and prediction freezing. It appends immutable roots and rebuilds the as-of Markdown view. Re-running the same date is idempotent. A/B/C identity conflicts are reported and omitted; missing D evidence remains explicitly missing.

EOD then runs `services.evidence_convergence` against the same as-of date before the D-line planner sends the daily action email. The convergence output is deterministic and does not change production rules automatically.

```bash
set -a; . /etc/vaxstock/vaxstock.env; set +a
PYTHONPATH=src /opt/stock-reportv2/venv/bin/python -m vaxstock.services.evidence_ledger --as-of YYYYMMDD
```

The command does not call an LLM and does not change strategy rules. Optional reviews live in a separate append-only file and require a reviewed forward-only `rule_version` before any production behavior changes.
