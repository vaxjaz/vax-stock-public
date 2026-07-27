# -*- coding: utf-8 -*-
"""统一配置层。

职责:
    - 提供工程内所有路径锚点 (PROJECT_ROOT / CONFIG_DIR / STATE_DIR / CACHE_DIR / REPORTS_DIR)
    - 加载敏感配置 _load_secrets(): secrets.json 兜底 + 环境变量覆盖(环境变量优先)
    - 提供从单体脚本搬运的全局常量 (HISTORY_DAYS / REQUEST_SLEEP_SECONDS / INDEX_LIST / *_HEADERS)

约束:
    import 本模块只做本地文件系统操作(创建 var/ 目录、读取 secrets.json),
    绝不连网、绝不初始化任何外部 client(Tushare / SMTP 等)。
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

# ==================== 路径锚点 ====================
# config.py 位于 <repo>/src/vaxstock/config.py, 上溯三级得到仓库根
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

CONFIG_DIR: Path = PROJECT_ROOT / "script" / "config"
STATE_DIR: Path = PROJECT_ROOT / "var"
CACHE_DIR: Path = STATE_DIR / "cache"
REPORTS_DIR: Path = STATE_DIR / "reports"

# 运行期状态/缓存/报告目录自动创建 (本地 FS 操作, 非网络副作用)
for _d in (STATE_DIR, CACHE_DIR, REPORTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# 市场环境(regime)平滑状态文件 —— 从单体脚本的 script 同目录迁到 var/
REGIME_STATE_FILE: Path = STATE_DIR / "regime_history.json"

# secrets.json 路径 (建议 chmod 600, 已加入 .gitignore, 不上传任何外部系统)
SECRETS_FILE: Path = CONFIG_DIR / "secrets.json"

# 私有账户快照可由环境变量指向 VPS 本地文件；默认文件已 gitignore。
PORTFOLIO_STATE_FILE: Path = Path(os.getenv("PORTFOLIO_STATE_FILE") or (CONFIG_DIR / "portfolio_state.json"))
HOLDINGS_BASE_FILE: Path = CONFIG_DIR / "holdings.json"
HOLDINGS_STATE_FILE: Path = Path(os.getenv("HOLDINGS_STATE_FILE") or (CONFIG_DIR / "holdings_state.json"))
STRATEGY_POLICY_FILE: Path = CONFIG_DIR / "strategy_policy.json"


# ==================== 敏感配置加载 ====================

# 环境变量 -> secrets 字段 的覆盖映射(环境变量优先于 secrets.json)
_ENV_OVERRIDES: Dict[str, str] = {
    "tushare_token": "TUSHARE_TOKEN",
    "codex_token": "CODEX_TOKEN",
    "codex_url": "CODEX_URL",
    "codex_model": "CODEX_MODEL",
    "codex_timeout": "CODEX_TIMEOUT",
    "codex_dline_model": "CODEX_DLINE_MODEL",
    "codex_dline_timeout": "CODEX_DLINE_TIMEOUT",
    "email_enabled": "EMAIL_ENABLED",
    "email_user": "EMAIL_USER",
    "email_authcode": "EMAIL_AUTHCODE",
    "email_to": "EMAIL_TO",
    "email_cc": "EMAIL_CC",
    "pushplus_token": "PUSHPLUS_TOKEN",
    "yield_10y_pct": "YIELD_10Y_PCT",
    "auto_concept_sync": "AUTO_CONCEPT_SYNC",
    "cleanup_keep_days": "CLEANUP_KEEP_DAYS",
    "legacy_prediction_report_enabled": "LEGACY_PREDICTION_REPORT_ENABLED",
    "legacy_daily_research_enabled": "LEGACY_DAILY_RESEARCH_ENABLED",
}

# 需要类型转换的字段(来自环境变量的值恒为字符串)
_BOOL_FIELDS = {
    "email_enabled",
    "auto_concept_sync",
    "legacy_prediction_report_enabled",
    "legacy_daily_research_enabled",
}
_INT_FIELDS = {"cleanup_keep_days", "codex_timeout", "codex_dline_timeout"}
_FLOAT_FIELDS = {"yield_10y_pct"}


def _coerce(field: str, value: Any) -> Any:
    """把(主要来自环境变量的)值按字段类型转换; 失败则原样返回。"""
    if value is None:
        return None
    try:
        if field in _BOOL_FIELDS:
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in ("1", "true", "yes", "on")
        if field in _INT_FIELDS:
            return int(float(value))
        if field in _FLOAT_FIELDS:
            return float(value)
    except (ValueError, TypeError):
        return value
    return value


def _load_secrets() -> Dict[str, Any]:
    """加载敏感配置: secrets.json 兜底 + 环境变量覆盖(环境变量优先)。

    - secrets.json 缺失或损坏时不报错, 仅用默认值 + 环境变量。
    - 以 "_" 开头的键视为说明性元字段, 自动忽略。
    - tushare_enabled 由是否存在 tushare_token 推导(有 token 即 True)。
    - 仅读取本地文件 / 环境变量, 不连网, 不初始化任何 client。
    """
    secrets: Dict[str, Any] = {
        "tushare_token": None,
        "tushare_enabled": False,
        "auto_concept_sync": False,
        "cleanup_keep_days": 7,
        "yield_10y_pct": None,
        "email_enabled": False,
        "email_user": None,
        "email_authcode": None,
        "email_to": None,
        "email_cc": None,
        "pushplus_token": "",
        "codex_token": None,
        "codex_url": None,
        "codex_model": None,
        "codex_timeout": 30,
        "codex_dline_model": None,
        "codex_dline_timeout": None,
        # 旧 E4/T+N 继续作为 D 线内部 baseline 机械运行，但默认不进入
        # 用户报告，也不再每天生成重复的旧研究结论。
        "legacy_prediction_report_enabled": False,
        "legacy_daily_research_enabled": False,
    }

    # 第一步: secrets.json 兜底
    if SECRETS_FILE.exists():
        try:
            with open(SECRETS_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            for k, v in raw.items():
                if k.startswith("_"):  # 跳过 _说明 等元字段
                    continue
                secrets[k] = v
        except Exception:
            # 损坏的 secrets.json 不应让 import 失败, 静默回退到默认值 + 环境变量
            pass

    # 第二步: 环境变量覆盖(优先级高于 secrets.json)
    for field, env_name in _ENV_OVERRIDES.items():
        env_val = os.getenv(env_name)
        if env_val is not None and env_val != "":
            secrets[field] = _coerce(field, env_val)

    # 第三步: 有 token 即视为启用 tushare
    secrets["tushare_enabled"] = bool(secrets.get("tushare_token"))
    return secrets


# 模块级解析结果(只读本地配置, 无网络副作用)
SECRETS: Dict[str, Any] = _load_secrets()


# ==================== 全局常量 (从单体脚本搬运, 逻辑零改) ====================

HISTORY_DAYS = 250  # 扩展到一年, 以便算52周高低和3年估值百分位
REQUEST_SLEEP_SECONDS = 0.25

INDEX_LIST: List[Tuple[str, str]] = [
    ("sh000001", "上证指数"),
    ("sz399001", "深证成指"),
    ("sz399006", "创业板指"),
    ("sh000688", "科创50"),
    ("sz399300", "沪深300"),
]

SINA_HEADERS = {
    "Referer": "https://finance.sina.com.cn",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
}

EM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
}

# 个股盘中/日报预警阈值 (从单体脚本搬运, 逻辑零改; 供 indicators.scoring.calc_derived_metrics 使用)
ALERT_RULES = {
    "price_change_pct": 3.0,
    "amplitude_pct": 5.0,
    "volume_ratio": 1.8,
    "position_high_pct": 85.0,
    "position_low_pct": 15.0,
    "main_inflow_yi": 1.0,        # 主力净流入超过1亿提示
    "main_outflow_yi": -1.0,      # 主力净流出超过1亿提示
}


# ==================== 标的池加载(观察池 / 持仓) ====================
# 在使用处(如 services.collect)按需调用, 返回局部变量, 不建任何模块级 WATCHLIST/HOLDINGS 全局。

def _load_local_json_object(path: Path, label: str) -> Dict[str, Any]:
    """读取本地 JSON object；缺失或损坏返回空 dict，不补默认决策值。"""
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("top-level JSON is not an object")
        return data
    except Exception as e:
        logger.warning(f"{label} 解析失败,返回空数据: {str(e)[:80]}")
        return {}


def load_portfolio_state(path=None) -> Dict[str, Any]:
    """读取私有账户快照；缺失时返回空 dict，由策略层标记待验证。"""
    return _load_local_json_object(Path(path or PORTFOLIO_STATE_FILE), "portfolio_state.json")


def load_strategy_policy(path=None) -> Dict[str, Any]:
    """读取已审核的交易纪律配置；缺失时返回空 dict，不启用隐式策略。"""
    return _load_local_json_object(Path(path or STRATEGY_POLICY_FILE), "strategy_policy.json")

def load_watchlist() -> Tuple[Dict[str, str], Dict[str, List[str]]]:
    """从 CONFIG_DIR/watchlist.json 加载观察池。

    返回 (watchlist, concepts_map):
      - watchlist:    {code: name}
      - concepts_map: {code: [手动概念...]}
    文件缺失/损坏 -> ({}, {})(P0: 缺数据不臆造, 由调用方自行处理空池)。
    """
    path = CONFIG_DIR / "watchlist.json"
    if not path.exists():
        return {}, {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        watchlist: Dict[str, str] = {}
        concepts_map: Dict[str, List[str]] = {}
        for code, info in (cfg.get("watchlist") or {}).items():
            info = info or {}
            watchlist[code] = info.get("name", "")
            if info.get("concepts"):
                concepts_map[code] = list(info["concepts"])
        return watchlist, concepts_map
    except Exception as e:
        logger.warning(f"watchlist.json 解析失败,返回空池: {str(e)[:80]}")
        return {}, {}


def load_holdings(path=None) -> Dict[str, Dict[str, Any]]:
    """加载独立持仓池；私有成交后状态优先，仓库基线仅在其不存在时使用。

    返回 {code: {"name", "cost", "shares", "concepts"}}; 文件缺失/损坏 -> {}。
    holdings 与 watchlist 解耦:D线任务池会强制纳入 holdings,不要求持仓重复写入 watchlist。
    私有状态一旦存在但损坏，不回退到旧基线，避免过期持仓进入决策。
    """
    selected = Path(path) if path is not None else (
        HOLDINGS_STATE_FILE if HOLDINGS_STATE_FILE.exists() else HOLDINGS_BASE_FILE
    )
    if not selected.exists():
        return {}
    try:
        with open(selected, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return {code: (info or {}) for code, info in (cfg.get("holdings") or {}).items()}
    except Exception as e:
        logger.warning(f"{selected.name} 解析失败,返回空持仓: {str(e)[:80]}")
        return {}

def load_task_pool() -> Dict[str, Dict[str, Any]]:
    """从 CONFIG_DIR/task_pool.json 加载 D线任务候选池。

    返回 active 的 {code: info}; 文件缺失/损坏 -> {}。
    这里只表示从宽 watchlist 中抽出的 D线 LLM 候选;真实持仓由 load_holdings() 另行强制并入。
    """
    path = CONFIG_DIR / "task_pool.json"
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        out: Dict[str, Dict[str, Any]] = {}
        for code, info in (cfg.get("task_pool") or {}).items():
            info = info or {}
            if info.get("active") is False:
                continue
            out[code] = info
        return out
    except Exception as e:
        logger.warning(f"task_pool.json 解析失败,返回空任务池: {str(e)[:80]}")
        return {}
