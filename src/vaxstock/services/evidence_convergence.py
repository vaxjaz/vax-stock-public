# -*- coding: utf-8 -*-
"""Deterministic daily convergence brief built on the A/B/C/D evidence ledger."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from vaxstock import config
from vaxstock.services.evidence_ledger import load_hydrated_evidence


CONVERGENCE_POLICY_VERSION = "evidence_convergence_v1"
CONVERGENCE_DIR = config.STATE_DIR / "evidence"


def _trade_date(value: Any, *, field: str) -> str:
    text = re.sub(r"[^0-9]", "", str(value or ""))
    if len(text) != 8:
        raise ValueError(f"{field} must be YYYYMMDD: {value!r}")
    return text


def _finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _market_facts(payload: Mapping[str, Any], as_of: str) -> Dict[str, Any]:
    overview = payload.get("market_overview") or {}
    source_date = re.sub(r"[^0-9]", "", str(overview.get("trade_date") or ""))
    if source_date != as_of:
        return {
            "source_status": "trade_date_mismatch" if source_date else "missing",
            "expected_trade_date": as_of,
            "actual_trade_date": source_date or None,
        }
    total = _finite(overview.get("total"))
    down = _finite(overview.get("down_count"))
    macro = payload.get("macro") or {}
    indicators = macro.get("indicators") or {}
    breadth = indicators.get("breadth") or {}
    margin = indicators.get("margin_ratio") or {}
    tracks = [
        row for row in (payload.get("tracks") or [])
        if isinstance(row, dict) and row.get("available")
    ]
    ai_track = next(
        (row for row in tracks if "AI" in str(row.get("track_name") or "").upper()),
        {},
    )
    return {
        "source_status": "aligned",
        "trade_date": as_of,
        "market_regime": payload.get("market_regime"),
        "up_count": overview.get("up_count"),
        "down_count": overview.get("down_count"),
        "total": overview.get("total"),
        "limit_down_count": overview.get("limit_down_count"),
        "down_ratio": down / total if down is not None and total and total > 0 else None,
        "macro_regime": macro.get("macro_regime"),
        "above_ma60_pct": breadth.get("above_ma60_pct"),
        "margin_data_date": margin.get("latest_date"),
        "margin_stale": margin.get("stale"),
        "ai_track": {
            "track_name": ai_track.get("track_name"),
            "position_ceiling": ai_track.get("position_ceiling"),
            "vetoes": list(ai_track.get("vetoes") or []),
            "pending": list(ai_track.get("pending") or []),
        } if ai_track else {"source_status": "missing"},
    }


def _outcome_cells(row: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    outcomes = row.get("c_outcomes") or {}
    cells = {
        str(horizon): dict(value)
        for horizon, value in (outcomes.get("fixed_horizons") or {}).items()
        if isinstance(value, dict) and value.get("status") == "mature"
    }
    latest = outcomes.get("t_plus_now") or {}
    if latest.get("status") == "mature" and str(latest.get("horizon") or "").isdigit():
        cells[str(latest["horizon"])] = dict(latest)
    return cells


def _group_key(row: Mapping[str, Any]) -> Tuple[str, str, str, str]:
    identity = row.get("identity") or {}
    prediction = row.get("frozen_c_prediction") or {}
    features = prediction.get("features_ref") or {}
    return (
        str(identity.get("rule_version") or "unknown"),
        str(prediction.get("action") or "unknown"),
        str(prediction.get("direction") or "unknown"),
        str(features.get("market_regime") or "unknown"),
    )


def _thresholds(policy: Mapping[str, Any]) -> Dict[str, Any]:
    source = ((policy.get("action_rules") or {}).get("history_evidence") or {})
    values = {
        "minimum_preliminary_sessions": source.get("minimum_preliminary_samples"),
        "minimum_stable_sessions": source.get("minimum_stable_samples"),
        "support_min_hit_rate": source.get("support_min_absolute_action_hit_rate"),
        "conflict_max_hit_rate": source.get("conflict_max_absolute_action_hit_rate"),
    }
    if (
        type(values["minimum_preliminary_sessions"]) is not int
        or values["minimum_preliminary_sessions"] <= 0
        or type(values["minimum_stable_sessions"]) is not int
        or values["minimum_stable_sessions"] < values["minimum_preliminary_sessions"]
        or _finite(values["support_min_hit_rate"]) is None
        or _finite(values["conflict_max_hit_rate"]) is None
        or float(values["support_min_hit_rate"]) < float(values["conflict_max_hit_rate"])
    ):
        return {"available": False, "source": "strategy_policy.action_rules.history_evidence"}
    return {
        "available": True,
        **values,
        "support_min_hit_rate": float(values["support_min_hit_rate"]),
        "conflict_max_hit_rate": float(values["conflict_max_hit_rate"]),
        "source": "strategy_policy.action_rules.history_evidence",
        "independence_rule": "same group and target_trade_date counts as one market session",
    }


def _verdict(session_count: int, hit_rate: float, thresholds: Mapping[str, Any]) -> str:
    if not thresholds.get("available"):
        return "threshold_pending"
    if session_count < int(thresholds["minimum_preliminary_sessions"]):
        return "accumulating"
    strength = "stable" if session_count >= int(thresholds["minimum_stable_sessions"]) else "preliminary"
    if hit_rate >= float(thresholds["support_min_hit_rate"]):
        return f"{strength}_support"
    if hit_rate <= float(thresholds["conflict_max_hit_rate"]):
        return f"{strength}_conflict"
    return "mixed"


def _strategy_groups(rows: Iterable[Mapping[str, Any]], policy: Mapping[str, Any]) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[str, str, str, str], Dict[str, List[bool]]] = defaultdict(
        lambda: defaultdict(list)
    )
    observations: Dict[Tuple[str, str, str, str], int] = defaultdict(int)
    for row in rows:
        target = str((row.get("identity") or {}).get("target_trade_date") or "")
        cell = _outcome_cells(row).get("1")
        hit = (cell or {}).get("absolute_action_hit")
        if not target or not isinstance(hit, bool):
            continue
        key = _group_key(row)
        grouped[key][target].append(hit)
        observations[key] += 1
    thresholds = _thresholds(policy)
    result = []
    for key in sorted(grouped):
        session_rates = [
            sum(1 for hit in hits if hit) / len(hits)
            for _, hits in sorted(grouped[key].items())
            if hits
        ]
        if not session_rates:
            continue
        hit_rate = sum(session_rates) / len(session_rates)
        result.append({
            "group_key": "|".join(key),
            "rule_version": key[0],
            "action": key[1],
            "direction": key[2],
            "decision_market_regime": key[3],
            "observations": observations[key],
            "independent_sessions": len(session_rates),
            "session_weighted_hit_rate": hit_rate,
            "verdict": _verdict(len(session_rates), hit_rate, thresholds),
        })
    return result


def _horizon_reversals(rows: Iterable[Mapping[str, Any]], as_of: str) -> List[Dict[str, Any]]:
    result = []
    for row in rows:
        cells = _outcome_cells(row)
        t1, t5 = cells.get("1"), cells.get("5")
        if not t1 or not t5:
            continue
        ret1, ret5 = _finite(t1.get("ret")), _finite(t5.get("ret"))
        if ret1 is None or ret5 is None or (ret1 > 0) == (ret5 > 0):
            continue
        identity = row.get("identity") or {}
        stock = row.get("stock") or {}
        result.append({
            "evidence_id": row.get("evidence_id"),
            "code": stock.get("code") or identity.get("code"),
            "name": stock.get("name"),
            "target_trade_date": identity.get("target_trade_date"),
            "t1_return": ret1,
            "t5_return": ret5,
            "new_today": as_of in {
                str(t1.get("actual_trade_date") or ""),
                str(t5.get("actual_trade_date") or ""),
            },
        })
    return sorted(result, key=lambda item: (str(item["target_trade_date"]), str(item["code"])))


def _current_state_summary(groups, thresholds):
    maximum = max((int(row.get("independent_sessions") or 0) for row in groups), default=0)
    preliminary = thresholds.get("minimum_preliminary_sessions")
    if thresholds.get("available") and maximum < int(preliminary):
        return (
            f"当前{len(groups)}个策略分组均在积累，最多{maximum}个独立交易日，"
            f"尚未达到{preliminary}日初步证据门槛。"
        )
    settled = [row for row in groups if row.get("verdict") != "accumulating"]
    return f"当前{len(groups)}个策略分组中，{len(settled)}个已跨越积累阶段。"


def _previous_changes(groups, findings, thresholds, previous):
    state_summary = _current_state_summary(groups, thresholds)
    if not previous:
        return [{
            "type": "initial_baseline",
            "summary": f"建立首日证据收敛基线；{state_summary}",
        }]
    old_groups = {
        str(row.get("group_key")): str(row.get("verdict"))
        for row in ((previous.get("convergence") or {}).get("groups") or [])
    }
    changes = []
    for row in groups:
        before = old_groups.get(str(row.get("group_key")))
        after = str(row.get("verdict"))
        if before and before != after:
            changes.append({
                "type": "group_verdict_changed",
                "group_key": row.get("group_key"),
                "before": before,
                "after": after,
                "summary": f"{row.get('action')}/{row.get('direction')}由{before}变为{after}。",
            })
    old_codes = {str(row.get("code")) for row in (previous.get("special_findings") or [])}
    for row in findings:
        if str(row.get("code")) not in old_codes:
            changes.append({
                "type": "new_special_finding",
                "code": row.get("code"),
                "summary": row.get("summary"),
            })
    if not changes:
        changes.append({
            "type": "no_material_change",
            "summary": f"新增结果尚未使任何策略分组跨越证据门槛；{state_summary}",
        })
    return changes


def build_evidence_convergence(
    rows: Iterable[Mapping[str, Any]],
    *,
    as_of_trade_date: str,
    payload: Mapping[str, Any],
    strategy_policy: Mapping[str, Any],
    previous: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    as_of = _trade_date(as_of_trade_date, field="as_of_trade_date")
    live = [dict(row) for row in rows if row.get("evidence_role") == "decision_evidence"]
    current = [
        row for row in live
        if str((row.get("identity") or {}).get("target_trade_date") or "") == as_of
    ]
    market = _market_facts(payload, as_of)
    new_cells = []
    for row in live:
        for horizon, cell in _outcome_cells(row).items():
            if str(cell.get("actual_trade_date") or "") == as_of:
                new_cells.append((str(row.get("evidence_id")), horizon))
    selected = [
        row for row in current
        if (row.get("d_evidence") or {}).get("status") not in {
            None, "not_selected", "d_data_missing",
        }
    ]
    triggered = [
        row for row in selected
        if int((row.get("d_evidence") or {}).get("trigger_count") or 0) > 0
    ]
    trigger_records = sum(
        int((row.get("d_evidence") or {}).get("trigger_count") or 0) for row in selected
    )
    complete_paths = sum(
        int((row.get("d_evidence") or {}).get("complete_evolution_count") or 0)
        for row in selected
    )
    decision_regimes = sorted({
        str(((row.get("frozen_c_prediction") or {}).get("features_ref") or {}).get("market_regime"))
        for row in current
        if ((row.get("frozen_c_prediction") or {}).get("features_ref") or {}).get("market_regime")
    })
    findings: List[Dict[str, Any]] = []
    actual_regime = str(market.get("market_regime") or "")
    if actual_regime and decision_regimes and actual_regime not in decision_regimes:
        findings.append({
            "code": "decision_outcome_environment_shift",
            "severity": "attention",
            "summary": (
                f"决策时市场状态为{'/'.join(decision_regimes)}，结果日实际状态为{actual_regime}；"
                "本日结果需按环境切换样本解释，不能直接归因于个股规则。"
            ),
        })
    if len(triggered) >= 2:
        prefix = "恐慌环境下" if actual_regime == "panic" else ""
        findings.append({
            "code": "same_day_correlated_trigger_event",
            "severity": "attention",
            "summary": (
                f"{prefix}{len(triggered)}只股票在同一交易日触发D线，"
                "属于1个相关市场事件；保留逐股结果，但收敛判断不按"
                f"{len(triggered)}个独立市场样本计数。"
            ),
            "triggered_stock_count": len(triggered),
            "effective_environment_event_count": 1,
        })
    missing_paths = max(0, trigger_records - complete_paths)
    if missing_paths:
        findings.append({
            "code": "dline_post_trigger_path_missing",
            "severity": "data_gap",
            "summary": (
                f"D线触发{trigger_records}条，完整触发后演变{complete_paths}条，"
                f"仍有{missing_paths}条不能评价最佳操作时机。"
            ),
        })
    reversals = _horizon_reversals(live, as_of)
    new_reversals = [row for row in reversals if row.get("new_today")]
    if new_reversals:
        names = "、".join(str(row.get("name") or row.get("code")) for row in new_reversals[:3])
        findings.append({
            "code": "t1_t5_sign_reversal",
            "severity": "attention",
            "summary": (
                f"新增{len(new_reversals)}条T+1与T+5收益方向反转证据"
                f"（{names}{'等' if len(new_reversals) > 3 else ''}）；短期结论不能外推到持有5天。"
            ),
        })
    groups = _strategy_groups(live, strategy_policy)
    thresholds = _thresholds(strategy_policy)
    changes = _previous_changes(groups, findings, thresholds, previous)
    facts = {
        "live_evidence_objects": len(live),
        "current_target_evidence_objects": len(current),
        "new_matured_c_results": len(set(new_cells)),
        "dline_selected_stocks": len(selected),
        "dline_triggered_stocks": len(triggered),
        "dline_trigger_records": trigger_records,
        "dline_complete_evolution_paths": complete_paths,
        "dline_missing_evolution_paths": missing_paths,
        "horizon_reversal_total": len(reversals),
        "horizon_reversal_new": len(new_reversals),
    }
    result = {
        "schema_version": 1,
        "policy_version": CONVERGENCE_POLICY_VERSION,
        "as_of_trade_date": as_of,
        "status": "ready" if current else "partial_data",
        "market_context": market,
        "facts": facts,
        "convergence": {
            "thresholds": thresholds,
            "groups": groups,
            "changes": changes,
        },
        "special_findings": findings,
        "strategy_effect": {
            "automatic_rule_change": False,
            "status": "review_required" if findings else "no_change",
            "summary": (
                f"发现{len(findings)}项需要继续验证的问题；不自动修改今日动作，"
                "下方操作仍按持仓、C线与D线纪律生成。"
                if findings else
                "没有发现足以改变今日动作的新证据；下方操作保持原纪律。"
            ),
        },
        "source_contract": {
            "primary_return": "actual_stock_return",
            "same_day_dependence": "one_environment_event",
            "user_execution_used": False,
            "llm_interpretation_used": False,
        },
    }
    result["facts_digest"] = _digest({
        "as_of_trade_date": as_of,
        "market_context": market,
        "facts": facts,
        "convergence": result["convergence"],
        "special_findings": findings,
    })
    return result


def render_evidence_convergence(report: Mapping[str, Any]) -> str:
    as_of = report.get("as_of_trade_date") or "待验证"
    facts = report.get("facts") or {}
    changes = (report.get("convergence") or {}).get("changes") or []
    findings = report.get("special_findings") or []
    effect = report.get("strategy_effect") or {}
    change_text = "；".join(
        str(row.get("summary")).rstrip("。；") for row in changes[:4]
    )
    finding_text = "；".join(
        str(row.get("summary")).rstrip("。；") for row in findings[:4]
    )
    lines = [
        f"# {as_of} 证据收敛简报",
        "",
        (
            f"- 今日新增: 成熟C线结果{facts.get('new_matured_c_results', 0)}条；"
            f"D线选择{facts.get('dline_selected_stocks', 0)}只、触发"
            f"{facts.get('dline_triggered_stocks', 0)}只、完整演变"
            f"{facts.get('dline_complete_evolution_paths', 0)}条。"
        ),
        "- 结论变化: " + (change_text or "没有可确认的结论变化。"),
        "- 特殊情况: " + (
            finding_text or "未识别到新的环境冲突、集中触发或期限反转。"
        ),
        f"- 对今日动作: {effect.get('summary') or '待验证'}",
        f"- 事实哈希: `{report.get('facts_digest') or '待验证'}`",
        "",
    ]
    return "\n".join(lines)


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(content, encoding="utf-8", newline="\n")
    os.replace(temp, path)


def _read_previous(output_dir: Path, as_of: str) -> Optional[Dict[str, Any]]:
    candidates = []
    for path in output_dir.glob("convergence_????????.json"):
        match = re.search(r"(\d{8})$", path.stem)
        if match and match.group(1) < as_of:
            candidates.append((match.group(1), path))
    if not candidates:
        return None
    path = max(candidates)[1]
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def run_evidence_convergence(
    *,
    as_of_trade_date: str,
    payload: Mapping[str, Any],
    strategy_policy: Optional[Mapping[str, Any]] = None,
    output_dir: Path = CONVERGENCE_DIR,
    **evidence_paths: Any,
) -> Dict[str, Any]:
    as_of = _trade_date(as_of_trade_date, field="as_of_trade_date")
    out_dir = Path(output_dir)
    hydrated = load_hydrated_evidence(as_of_trade_date=as_of, **evidence_paths)
    report = build_evidence_convergence(
        hydrated,
        as_of_trade_date=as_of,
        payload=payload,
        strategy_policy=strategy_policy or config.load_strategy_policy(),
        previous=_read_previous(out_dir, as_of),
    )
    dated_json = out_dir / f"convergence_{as_of}.json"
    latest_json = out_dir / "convergence_latest.json"
    dated_md = out_dir / f"convergence_{as_of}.md"
    latest_md = out_dir / "convergence_latest.md"
    json_content = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    markdown = render_evidence_convergence(report)
    for path, content in (
        (dated_json, json_content),
        (latest_json, json_content),
        (dated_md, markdown),
        (latest_md, markdown),
    ):
        _atomic_write(path, content)
    return {
        "status": report["status"],
        "as_of_trade_date": as_of,
        "dated_json_path": str(dated_json),
        "dated_md_path": str(dated_md),
        "facts": report["facts"],
        "special_findings": len(report["special_findings"]),
        "facts_digest": report["facts_digest"],
    }
