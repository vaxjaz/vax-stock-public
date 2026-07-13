# -*- coding: utf-8 -*-
"""EOD Prediction 线(E4-3): 核验已冻结的 EOD predictions。

本模块只做本地结果核验:
  - 输入: `var/prediction/eod_predictions.jsonl` + `var/eval/factor_results.jsonl`;
  - 输出: append-only `var/prediction/eod_prediction_results.jsonl`;
  - 优先复用 E1 机械回填出的真实收益/基准/超额, 不触网、不臆造缺失结果;
  - 结果回填不得修改 prediction 原文, 只按 prediction_id+horizon 幂等追加。
"""

import datetime as dt
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from vaxstock import config
from vaxstock.services.eod_predictor import PREDICTIONS_FILE

logger = logging.getLogger(__name__)

PREDICTION_RESULTS_FILE = config.STATE_DIR / "prediction" / "eod_prediction_results.jsonl"
SCHEMA_VERSION = 1
DEFAULT_HORIZON = "1"
MAX_PATH_HORIZON = 30


def _now_iso() -> str:
    """生成时刻戳(ISO); 仅作记录时刻, 非交易日基准。"""
    return dt.datetime.now().isoformat(timespec="seconds")


def _read_jsonl(path) -> List[dict]:
    """读取 jsonl; 坏行跳过并 warning, 不因单行损坏中断全文件。"""
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
                logger.warning(f"prediction result jsonl 行解析失败, 跳过: {line[:60]}")
    return rows


def _append_jsonl(path, row) -> None:
    """append-only 写一行 JSON。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def prediction_horizon(prediction: Dict[str, Any]) -> str:
    """把 prediction.horizon 转为 factor_results 的 horizon key。

    现阶段 seed 规则写 `T+1`; 若未来出现 `T+3`/`3日`, 取其中数字。缺失时回退 T+1。
    """
    raw = ((prediction.get("prediction") or {}).get("horizon") or "").strip()
    m = re.search(r"(\d+)", raw)
    return m.group(1) if m else DEFAULT_HORIZON


def build_factor_result_index(rows: Iterable[Dict[str, Any]]) -> Dict[Tuple[str, str], Dict[str, Dict[str, Any]]]:
    """把 factor_results rows 合并为 {(trade_date, code): {ret/mkt_ret/excess}}。

    factor_results 是 append-only, 同 key 后续行可能带更多 horizon。按文件顺序合并 dict,
    后写 horizon 覆盖同名 horizon, 不修改原文件。
    """
    idx: Dict[Tuple[str, str], Dict[str, Dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        td = str(row.get("trade_date") or "").strip()
        code = str(row.get("code") or "").strip()
        if not (td and code):
            continue
        box = idx.setdefault((td, code), {"ret": {}, "mkt_ret": {}, "excess": {}})
        for key in ("ret", "mkt_ret", "excess"):
            vals = row.get(key) or {}
            if isinstance(vals, dict):
                box[key].update(vals)
    return idx


def complete_horizons(actual_box: Dict[str, Dict[str, Any]], *,
                      max_horizon: int = MAX_PATH_HORIZON) -> List[str]:
    """Return positive horizons present in return, benchmark and excess."""
    keys = (
        set((actual_box.get("ret") or {}).keys())
        & set((actual_box.get("mkt_ret") or {}).keys())
        & set((actual_box.get("excess") or {}).keys())
    )
    values = []
    for key in keys:
        text = str(key)
        if text.isdigit() and 1 <= int(text) <= max_horizon:
            values.append(text)
    return sorted(values, key=int)


def _direction_hit(direction: str, ret: Optional[float]) -> Optional[bool]:
    """方向命中: up/down 用绝对收益判定; neutral 不作方向性评分。"""
    if ret is None:
        return None
    if direction == "up":
        return ret > 0
    if direction == "down":
        return ret < 0
    return None


def _action_hit(bucket: str, positive_excess: Optional[bool]) -> Optional[bool]:
    """动作命中: 只对明确 positive / non_positive 预期评分。"""
    if positive_excess is None:
        return None
    if bucket == "positive":
        return positive_excess is True
    if bucket == "non_positive":
        return positive_excess is False
    return None


def _deviation(bucket: str, positive_excess: Optional[bool], action_hit: Optional[bool]) -> str:
    if action_hit is True:
        return "as_expected"
    if action_hit is None:
        return "not_scored"
    if bucket == "positive" and positive_excess is False:
        return "expected_positive_but_non_positive"
    if bucket == "non_positive" and positive_excess is True:
        return "missed_positive_excess"
    return "unexpected"


def evaluate_prediction(prediction: Dict[str, Any], factor_index: Dict[Tuple[str, str], Dict[str, Dict[str, Any]]], *,
                        horizon: Optional[str] = None,
                        evaluated_at: Optional[str] = None) -> Optional[dict]:
    """核验单条 prediction; 缺真实收益/超额则返回 None, 不写假结果。"""
    if not isinstance(prediction, dict):
        return None
    pid = prediction.get("prediction_id")
    baseline = str(prediction.get("baseline_trade_date") or "").strip()
    target = str(prediction.get("target_trade_date") or "").strip()
    code = str(prediction.get("code") or "").strip()
    if not (pid and baseline and target and code):
        return None

    h = str(horizon or prediction_horizon(prediction))
    target_horizon = prediction_horizon(prediction)
    actual_box = factor_index.get((baseline, code))
    if not actual_box:
        return None

    ret = _to_float((actual_box.get("ret") or {}).get(h))
    mkt_ret = _to_float((actual_box.get("mkt_ret") or {}).get(h))
    excess = _to_float((actual_box.get("excess") or {}).get(h))
    if ret is None or mkt_ret is None or excess is None:
        return None

    pred = prediction.get("prediction") or {}
    direction = str(pred.get("direction") or "neutral")
    bucket = str(pred.get("expected_excess_bucket") or "unknown")
    positive_excess = excess > 0
    direction_hit = _direction_hit(direction, ret)
    action_hit = _action_hit(bucket, positive_excess)
    is_target_horizon = h == target_horizon
    evaluation_role = "target_horizon" if is_target_horizon else "post_prediction_path"

    return {
        "schema_version": SCHEMA_VERSION,
        "prediction_id": pid,
        "evaluated_at": evaluated_at or _now_iso(),
        "generation_mode": prediction.get("generation_mode"),
        "baseline_trade_date": baseline,
        "target_trade_date": target,
        "code": code,
        "horizon": h,
        "actual": {
            "ret": ret,
            "mkt_ret": mkt_ret,
            "excess": excess,
            "source": "factor_results",
        },
        "evaluation": {
            "evaluation_role": evaluation_role,
            "direction_hit": direction_hit if is_target_horizon else None,
            "positive_excess": positive_excess,
            "action_hit": action_hit if is_target_horizon else None,
            "path_direction_alignment": direction_hit,
            "path_action_alignment": action_hit,
            "deviation": _deviation(bucket, positive_excess, action_hit) if is_target_horizon else "post_prediction_path",
            "error_type": None,
        },
    }


def evaluate_predictions(predictions: Iterable[Dict[str, Any]], factor_results: Iterable[Dict[str, Any]], *,
                         horizon: Optional[str] = None,
                         evaluated_at: Optional[str] = None) -> List[dict]:
    """批量核验 predictions, 返回可写入的 result rows。"""
    factor_index = build_factor_result_index(factor_results)
    rows = []
    for pred in predictions:
        baseline = str((pred or {}).get("baseline_trade_date") or "").strip()
        code = str((pred or {}).get("code") or "").strip()
        actual_box = factor_index.get((baseline, code)) or {}
        horizons = [str(horizon)] if horizon is not None else complete_horizons(actual_box)
        for path_horizon in horizons:
            row = evaluate_prediction(
                pred,
                factor_index,
                horizon=path_horizon,
                evaluated_at=evaluated_at,
            )
            if row:
                rows.append(row)
    return rows


def record_prediction_results(results: Iterable[dict], path=None) -> Dict[str, int]:
    """幂等写 prediction results。返回 {written, skipped}。"""
    out_path = Path(path or PREDICTION_RESULTS_FILE)
    existing = {(r.get("prediction_id"), str(r.get("horizon"))) for r in _read_jsonl(out_path)}
    written = skipped = 0
    for row in results:
        key = (row.get("prediction_id"), str(row.get("horizon")))
        if not key[0] or key in existing:
            skipped += 1
            continue
        _append_jsonl(out_path, row)
        existing.add(key)
        written += 1
    if written:
        logger.info(f"EOD Prediction 核验写入 {written} 条({out_path})")
    return {"written": written, "skipped": skipped}


def evaluate_from_files(*, predictions_path=None, factor_results_path=None, output_path=None,
                        horizon: Optional[str] = None,
                        evaluated_at: Optional[str] = None) -> Dict[str, int]:
    """读取 prediction/factor_results 文件并幂等写入核验结果。"""
    if predictions_path is None:
        predictions_path = PREDICTIONS_FILE
    if factor_results_path is None:
        from vaxstock.services.eval_recorder import RESULTS_FILE
        factor_results_path = RESULTS_FILE

    predictions = _read_jsonl(predictions_path)
    factor_results = _read_jsonl(factor_results_path)
    rows = evaluate_predictions(predictions, factor_results, horizon=horizon, evaluated_at=evaluated_at)
    stats = record_prediction_results(rows, path=output_path)
    evaluated_predictions = {row.get("prediction_id") for row in rows if row.get("prediction_id")}
    stats.update({
        "source_predictions": len(predictions),
        "source_factor_results": len(factor_results),
        "generated": len(rows),
        "missing_or_pending": len(predictions) - len(evaluated_predictions),
    })
    return stats
