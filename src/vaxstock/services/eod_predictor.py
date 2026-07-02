# -*- coding: utf-8 -*-
"""EOD Prediction 线(E4-1): 基于 EOD 因子快照生成下一交易日预测。

本模块只做 **schema + deterministic rule writer**:
  - 输入: E1 的 factor_snapshots 行,或 EOD payload 中的 stocks 行;
  - 输出: append-only `var/prediction/eod_predictions.jsonl`;
  - 不触网、不取数、不做结果回填(结果回填归 prediction_evaluator 后续 PR);
  - replay/live 必须显式标记 generation_mode,不可混写为同一种样本。

设计边界:
  - 这里验证的是"当时策略动作(action/direction/confidence)是否正确",不是单纯 score 档收益;
  - 当前 rule_version 只是 zz800 seed 的第一版动作映射,后续升级必须 bump rule_version;
  - prediction 原文一旦写入不得因未来结果回填而修改。
"""

import datetime as dt
import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from vaxstock import config

logger = logging.getLogger(__name__)

PREDICTION_DIR = config.STATE_DIR / "prediction"
PREDICTIONS_FILE = PREDICTION_DIR / "eod_predictions.jsonl"

SCHEMA_VERSION = 1
DEFAULT_RULE_VERSION = "zz800_seed_v1"
DEFAULT_MODEL_VERSION = "manual_rules_v1"
VALID_GENERATION_MODES = {"live", "replay"}
_REQUIRED_TOP_FIELDS = (
    "schema_version", "prediction_id", "generated_at", "generation_mode",
    "baseline_trade_date", "target_trade_date", "code", "features_ref",
    "prediction", "rule_version", "model_version",
)
_REQUIRED_FEATURE_FIELDS = (
    "price_at_baseline", "right_side_score", "right_side_grade",
    "main_inflow_10d", "np_yoy", "holder_change_pct", "position_20d_pct",
    "market_regime", "macro_regime", "ai_position_ceiling",
)
_REQUIRED_PREDICTION_FIELDS = (
    "action", "direction", "confidence", "horizon", "expected_excess_bucket",
    "reason_codes", "reason",
)


def _now_iso() -> str:
    """生成时刻戳(ISO); 仅作记录时刻,非交易日基准。"""
    return dt.datetime.now().isoformat(timespec="seconds")


def _read_jsonl(path) -> List[dict]:
    """读取 jsonl; 坏行跳过并 warning,不因单行损坏中断全文件。"""
    p = Path(path)
    if not p.exists():
        return []
    rows = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                logger.warning(f"prediction jsonl 行解析失败, 跳过: {line[:60]}")
    return rows


def _append_jsonl(path, row) -> None:
    """append-only 写一行 JSON。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def make_prediction_id(baseline_trade_date: str, target_trade_date: str, code: str,
                       rule_version: str = DEFAULT_RULE_VERSION,
                       generation_mode: str = "live") -> str:
    """生成稳定 prediction_id。

    generation_mode 纳入 id: 同一历史输入既可 replay 也可 live 记录,两者样本性质不同,不可互相覆盖。
    """
    return "_".join([
        str(baseline_trade_date),
        str(target_trade_date),
        str(code),
        str(rule_version),
        str(generation_mode),
    ])


def validate_prediction(prediction: Dict[str, Any]) -> None:
    """校验 prediction schema 与可追溯性约束; 不合法直接抛 ValueError。

    这是 writer 前最后一道防线: 后续 evaluator/layer2 会依赖这些字段做 join、分桶与版本追溯。
    因此宁可写入前失败,也不能把结构坏/ID 错/置信度越界的数据落进 append-only 文件。
    """
    missing = [k for k in _REQUIRED_TOP_FIELDS if k not in prediction]
    if missing:
        raise ValueError(f"prediction 缺必填字段: {missing}")
    if prediction.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version 必须为 {SCHEMA_VERSION}")
    mode = prediction.get("generation_mode")
    if mode not in VALID_GENERATION_MODES:
        raise ValueError(f"generation_mode 须为 {sorted(VALID_GENERATION_MODES)}")
    for key in ("baseline_trade_date", "target_trade_date", "code", "rule_version", "model_version"):
        if not prediction.get(key):
            raise ValueError(f"{key} 不能为空")

    expected_id = make_prediction_id(
        prediction["baseline_trade_date"],
        prediction["target_trade_date"],
        prediction["code"],
        rule_version=prediction["rule_version"],
        generation_mode=prediction["generation_mode"],
    )
    if prediction.get("prediction_id") != expected_id:
        raise ValueError(f"prediction_id 不匹配: got={prediction.get('prediction_id')} expected={expected_id}")

    features = prediction.get("features_ref")
    if not isinstance(features, dict):
        raise ValueError("features_ref 必须为 dict")
    missing_features = [k for k in _REQUIRED_FEATURE_FIELDS if k not in features]
    if missing_features:
        raise ValueError(f"features_ref 缺字段: {missing_features}")

    pred = prediction.get("prediction")
    if not isinstance(pred, dict):
        raise ValueError("prediction 必须为 dict")
    missing_pred = [k for k in _REQUIRED_PREDICTION_FIELDS if k not in pred]
    if missing_pred:
        raise ValueError(f"prediction 缺字段: {missing_pred}")
    conf = pred.get("confidence")
    if not isinstance(conf, (int, float)) or not (0.0 <= float(conf) <= 1.0):
        raise ValueError("prediction.confidence 必须为 0~1 数值")
    if not isinstance(pred.get("reason_codes"), list):
        raise ValueError("prediction.reason_codes 必须为 list")


def _score_grade(score: Optional[float]) -> Optional[str]:
    """当 snapshot 缺 right_side_grade 时,按现行评分阈值补一个展示 grade。"""
    if score is None:
        return None
    if score >= 3.5:
        return "强买入信号"
    if score >= 2.0:
        return "可考虑介入"
    if score >= 0.5:
        return "观察等待"
    return "回避"


def infer_prediction(metrics: Dict[str, Any], market: Dict[str, Any]) -> Dict[str, Any]:
    """zz800_seed_v1 的第一版动作映射(确定性,不触网)。

    目的不是立刻最优,而是把"基于当前规则当时会怎么判断"冻结下来:
      - 高分非 panic → candidate_buy/watch;
      - panic 下高分降级为 watch_only;
      - panic 下中低分保留 panic_rebound_* 观察动作,用于验证恐慌修复效应;
      - 无评分 -> no_prediction。
    """
    score = metrics.get("right_side_score")
    regime = (market or {}).get("regime")
    macro = (market or {}).get("macro_regime")
    reason_codes: List[str] = []

    if score is None:
        return {
            "action": "no_prediction",
            "direction": "neutral",
            "confidence": 0.0,
            "horizon": "T+1",
            "expected_excess_bucket": "unknown",
            "reason_codes": ["score_missing"],
            "reason": "缺 right_side_score,不生成方向性预测",
        }

    if score >= 3.5:
        reason_codes.append("score_ge_3_5")
        if regime == "panic":
            return {
                "action": "watch_only",
                "direction": "neutral",
                "confidence": 0.50,
                "horizon": "T+1",
                "expected_excess_bucket": "uncertain",
                "reason_codes": reason_codes + ["panic_downgrade"],
                "reason": "强分但处 panic,降级观察,等待盘中确认",
            }
        return {
            "action": "candidate_buy",
            "direction": "up",
            "confidence": 0.75,
            "horizon": "T+1",
            "expected_excess_bucket": "positive",
            "reason_codes": reason_codes,
            "reason": "评分≥3.5且非 panic,列为候选买入验证",
        }

    if score >= 2.0:
        reason_codes.append("score_ge_2")
        if regime == "panic":
            return {
                "action": "watch_only",
                "direction": "neutral",
                "confidence": 0.45,
                "horizon": "T+1",
                "expected_excess_bucket": "uncertain",
                "reason_codes": reason_codes + ["panic_downgrade"],
                "reason": "评分≥2但处 panic,不直接介入,仅观察确认",
            }
        if macro and "看空" in str(macro):
            reason_codes.append("macro_bearish_reduce_confidence")
        return {
            "action": "watch",
            "direction": "up",
            "confidence": 0.55 if "macro_bearish_reduce_confidence" in reason_codes else 0.60,
            "horizon": "T+1",
            "expected_excess_bucket": "positive",
            "reason_codes": reason_codes,
            "reason": "评分≥2,列为高优先观察,需盘中行为确认",
        }

    if regime == "panic":
        if score >= 0.5:
            return {
                "action": "panic_rebound_watch",
                "direction": "up",
                "confidence": 0.50,
                "horizon": "T+1",
                "expected_excess_bucket": "positive",
                "reason_codes": ["panic", "score_ge_0_5", "rebound_probe"],
                "reason": "panic 下观察档用于验证 T+1 情绪修复",
            }
        return {
            "action": "panic_rebound_probe",
            "direction": "neutral",
            "confidence": 0.40,
            "horizon": "T+1",
            "expected_excess_bucket": "uncertain",
            "reason_codes": ["panic", "score_lt_0_5", "rebound_probe"],
            "reason": "panic 下低分票仅作修复观察,不等同买入",
        }

    return {
        "action": "avoid",
        "direction": "neutral",
        "confidence": 0.55,
        "horizon": "T+1",
        "expected_excess_bucket": "non_positive",
        "reason_codes": ["score_lt_2", "non_panic"],
        "reason": "非 panic 且评分<2,默认回避/低优先级",
    }


def _features_from_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    metrics = snapshot.get("metrics") or {}
    market = snapshot.get("market") or {}
    ai_track = market.get("ai_track") or {}
    return {
        "price_at_baseline": snapshot.get("price_at_snapshot"),
        "right_side_score": metrics.get("right_side_score"),
        "right_side_grade": metrics.get("right_side_grade") or _score_grade(metrics.get("right_side_score")),
        "main_inflow_10d": metrics.get("main_inflow_10d"),
        "np_yoy": metrics.get("np_yoy"),
        "holder_change_pct": metrics.get("holder_change_pct"),
        "position_20d_pct": metrics.get("position_20d_pct"),
        "market_regime": market.get("regime"),
        "macro_regime": market.get("macro_regime"),
        "ai_position_ceiling": ai_track.get("position_ceiling"),
    }


def prediction_from_snapshot(snapshot: Dict[str, Any], target_trade_date: str, *,
                             generation_mode: str = "live",
                             rule_version: str = DEFAULT_RULE_VERSION,
                             model_version: str = DEFAULT_MODEL_VERSION,
                             generated_at: Optional[str] = None) -> Optional[dict]:
    """从 E1 snapshot 行生成一条 EOD prediction。

    缺 baseline_trade_date/code/target_trade_date 时返回 None,不臆造。
    """
    if generation_mode not in VALID_GENERATION_MODES:
        raise ValueError(f"generation_mode 须为 {sorted(VALID_GENERATION_MODES)}")
    baseline = snapshot.get("trade_date")
    code = snapshot.get("code")
    if not (baseline and target_trade_date and code):
        return None

    metrics = snapshot.get("metrics") or {}
    market = snapshot.get("market") or {}
    prediction = infer_prediction(metrics, market)
    pid = make_prediction_id(str(baseline), str(target_trade_date), str(code),
                             rule_version=rule_version, generation_mode=generation_mode)
    return {
        "schema_version": SCHEMA_VERSION,
        "prediction_id": pid,
        "generated_at": generated_at or _now_iso(),
        "generation_mode": generation_mode,
        "baseline_trade_date": str(baseline),
        "target_trade_date": str(target_trade_date),
        "code": code,
        "name": snapshot.get("name"),
        "group": snapshot.get("group"),
        "concepts": list(snapshot.get("concepts") or []),
        "features_ref": _features_from_snapshot(snapshot),
        "prediction": prediction,
        "rule_version": rule_version,
        "model_version": model_version,
    }


def _snapshot_from_payload_item(item: Dict[str, Any], payload: Dict[str, Any]) -> Optional[dict]:
    """把 EOD payload 的 stock item 适配成 snapshot 形状,复用 prediction_from_snapshot。"""
    td = (payload.get("market_overview") or {}).get("trade_date")
    code = item.get("code")
    if not (td and code):
        return None
    rt = item.get("realtime") or {}
    macro = payload.get("macro") or {}
    tracks = payload.get("tracks") or []
    ai_track = None
    if tracks:
        t0 = tracks[0] or {}
        ai_track = {
            "track_name": t0.get("track_name"),
            "position_ceiling": t0.get("position_ceiling"),
            "available": t0.get("available"),
        }
    return {
        "trade_date": str(td),
        "code": code,
        "name": rt.get("name") or item.get("configured_name"),
        "group": item.get("group"),
        "concepts": item.get("concepts", []),
        "price_at_snapshot": rt.get("price"),
        "metrics": item.get("metrics") or {},
        "market": {
            "regime": payload.get("market_regime"),
            "macro_regime": macro.get("macro_regime"),
            "ai_track": ai_track,
        },
    }


def predictions_from_payload(payload: Dict[str, Any], target_trade_date: str, *,
                             generation_mode: str = "live",
                             rule_version: str = DEFAULT_RULE_VERSION,
                             model_version: str = DEFAULT_MODEL_VERSION,
                             generated_at: Optional[str] = None) -> List[dict]:
    """从 EOD payload 生成全 stocks predictions。"""
    out = []
    for item in payload.get("stocks") or []:
        snap = _snapshot_from_payload_item(item, payload)
        if not snap:
            continue
        pred = prediction_from_snapshot(
            snap,
            target_trade_date,
            generation_mode=generation_mode,
            rule_version=rule_version,
            model_version=model_version,
            generated_at=generated_at,
        )
        if pred:
            out.append(pred)
    return out


def record_predictions(predictions: Iterable[dict], path=None) -> Dict[str, int]:
    """幂等写 predictions。返回 {"written": n, "skipped": m}。"""
    out_path = Path(path or PREDICTIONS_FILE)
    existing = {r.get("prediction_id") for r in _read_jsonl(out_path)}
    written = skipped = 0
    for pred in predictions:
        validate_prediction(pred)
        pid = pred.get("prediction_id")
        if not pid or pid in existing:
            skipped += 1
            continue
        _append_jsonl(out_path, pred)
        existing.add(pid)
        written += 1
    if written:
        logger.info(f"EOD Prediction 写入 {written} 条({out_path})")
    return {"written": written, "skipped": skipped}


def generate_predictions_from_snapshots(snapshots: Iterable[Dict[str, Any]], target_trade_date: str, *,
                                        generation_mode: str = "replay",
                                        rule_version: str = DEFAULT_RULE_VERSION,
                                        model_version: str = DEFAULT_MODEL_VERSION,
                                        generated_at: Optional[str] = None) -> List[dict]:
    """从已有 snapshot rows 批量生成 predictions(供 replay/bootstrap 与测试)。"""
    preds = []
    for snap in snapshots:
        pred = prediction_from_snapshot(
            snap,
            target_trade_date,
            generation_mode=generation_mode,
            rule_version=rule_version,
            model_version=model_version,
            generated_at=generated_at,
        )
        if pred:
            preds.append(pred)
    return preds
