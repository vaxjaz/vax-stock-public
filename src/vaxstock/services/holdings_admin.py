# -*- coding: utf-8 -*-
"""VPS-local complete holdings snapshot replacement.

The command accepts a complete broker snapshot in compact form and writes only
the private ``holdings_state.json`` selected by ``config.HOLDINGS_STATE_FILE``.
Git-tracked ``holdings.json`` is metadata fallback only; it is never modified.
"""

import argparse
import datetime as dt
import json
import math
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

from vaxstock import config


_CODE_RE = re.compile(r"^\d{6}$")
_MAIN_BOARD_PREFIXES = ("60", "00")
DEFAULT_BACKUP_DIR = Path("/var/backups/vaxstock/holdings")


def _now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _read_object(path: Path, *, missing_ok: bool = False) -> Dict[str, Any]:
    if not path.exists():
        if missing_ok:
            return {}
        raise ValueError(f"required_json_missing:{path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid_json:{path}:{type(exc).__name__}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"json_root_not_object:{path}")
    return data


def _write_json_atomic(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f"{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _positive_int(value: str, field: str) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field}_invalid:{value}") from exc
    if not math.isfinite(number) or number <= 0 or not number.is_integer():
        raise ValueError(f"{field}_invalid:{value}")
    return int(number)


def _positive_float(value: str, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field}_invalid:{value}") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{field}_invalid:{value}")
    return number


def parse_position_spec(spec: str) -> Dict[str, Any]:
    """Parse ``CODE:SHARES:COST[:NAME]`` without inferring missing numbers."""
    parts = str(spec or "").strip().split(":", 3)
    if len(parts) not in {3, 4}:
        raise ValueError(f"position_format_invalid:{spec}")
    code, shares_raw, cost_raw = (part.strip() for part in parts[:3])
    if not _CODE_RE.fullmatch(code):
        raise ValueError(f"code_invalid:{code}")
    if not code.startswith(_MAIN_BOARD_PREFIXES):
        raise ValueError(f"code_not_tradeable_main_board:{code}")
    row: Dict[str, Any] = {
        "code": code,
        "shares": _positive_int(shares_raw, "shares"),
        "cost": _positive_float(cost_raw, "cost"),
    }
    if len(parts) == 4:
        name = parts[3].strip()
        if not name:
            raise ValueError(f"name_empty:{code}")
        row["name"] = name
    return row


def _metadata_index(base: Mapping[str, Any], current: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for source in (base.get("holdings") or {}, current.get("holdings") or {}):
        if not isinstance(source, dict):
            continue
        for code, row in source.items():
            if isinstance(row, dict):
                out[str(code)] = {**out.get(str(code), {}), **row}
    return out


def build_replacement_state(
    current: Mapping[str, Any],
    base: Mapping[str, Any],
    positions: Iterable[Mapping[str, Any]],
    *,
    as_of_trade_date: Optional[str] = None,
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a complete private-state replacement while preserving real history."""
    timestamp = generated_at or _now_iso()
    if as_of_trade_date is not None and not re.fullmatch(r"\d{8}", str(as_of_trade_date)):
        raise ValueError(f"as_of_trade_date_invalid:{as_of_trade_date}")

    metadata = _metadata_index(base, current)
    current_holdings = current.get("holdings") or {}
    if not isinstance(current_holdings, dict):
        raise ValueError("current_holdings_not_object")

    replacement: Dict[str, Dict[str, Any]] = {}
    for position in positions:
        code = str(position.get("code") or "")
        if code in replacement:
            raise ValueError(f"duplicate_code:{code}")
        if not _CODE_RE.fullmatch(code) or not code.startswith(_MAIN_BOARD_PREFIXES):
            raise ValueError(f"code_invalid_or_not_tradeable:{code}")

        shares = position.get("shares")
        cost = position.get("cost")
        if (
            not isinstance(shares, int)
            or isinstance(shares, bool)
            or shares <= 0
        ):
            raise ValueError(f"shares_invalid:{code}:{shares}")
        if (
            not isinstance(cost, (int, float))
            or isinstance(cost, bool)
            or not math.isfinite(float(cost))
            or float(cost) <= 0
        ):
            raise ValueError(f"cost_invalid:{code}:{cost}")

        old_row = current_holdings.get(code)
        old_row = dict(old_row) if isinstance(old_row, dict) else {}
        known = metadata.get(code) or {}
        name = str(position.get("name") or known.get("name") or "").strip()
        if not name:
            raise ValueError(f"name_missing:{code}:use_CODE:SHARES:COST:NAME")

        changed = bool(old_row) and (
            old_row.get("shares") != shares
            or old_row.get("cost") != cost
        )
        row = dict(old_row)
        row.update({"name": name, "shares": shares, "cost": float(cost)})
        if "concepts" not in row and known.get("concepts"):
            row["concepts"] = list(known["concepts"])

        # available_shares is a separate broker fact.  Never carry it across a
        # changed position when the compact snapshot did not provide that fact.
        if changed:
            row.pop("available_shares", None)
            if isinstance(row.get("entry_history"), dict):
                history = dict(row["entry_history"])
                history.setdefault("status_before_quick_update", history.get("status"))
                history["status"] = "stale_after_complete_snapshot"
                history["stale_at"] = timestamp
                row["entry_history"] = history
        replacement[code] = row

    if not replacement:
        raise ValueError("complete_snapshot_empty")

    result = dict(current)
    result["schema_version"] = max(int(result.get("schema_version") or 1), 2)
    result["holdings"] = replacement
    result["last_quick_update"] = {
        "at": timestamp,
        "source": "vps_local_complete_snapshot",
        "position_count": len(replacement),
    }
    if as_of_trade_date is not None:
        result["as_of_trade_date"] = str(as_of_trade_date)
    return result


def replace_holdings(
    specs: Sequence[str],
    *,
    state_path: Optional[Path] = None,
    base_path: Optional[Path] = None,
    backup_dir: Optional[Path] = None,
    as_of_trade_date: Optional[str] = None,
    dry_run: bool = False,
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    state_file = Path(state_path or config.HOLDINGS_STATE_FILE).resolve()
    base_file = Path(base_path or config.HOLDINGS_BASE_FILE).resolve()
    current = _read_object(state_file, missing_ok=True)
    base = _read_object(base_file, missing_ok=True)
    positions = [parse_position_spec(spec) for spec in specs]
    updated = build_replacement_state(
        current,
        base,
        positions,
        as_of_trade_date=as_of_trade_date,
        generated_at=generated_at,
    )

    old_codes = set((current.get("holdings") or {}).keys())
    new_codes = set(updated["holdings"].keys())
    backup_path = None
    if not dry_run:
        if state_file.exists():
            directory = Path(backup_dir or DEFAULT_BACKUP_DIR).resolve()
            directory.mkdir(parents=True, exist_ok=True)
            stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            backup_path = directory / f"holdings_state-{stamp}.json"
            shutil.copy2(state_file, backup_path)
        _write_json_atomic(state_file, updated)

    return {
        "status": "dry_run" if dry_run else "updated",
        "state_path": str(state_file),
        "backup_path": str(backup_path) if backup_path else None,
        "as_of_trade_date": updated.get("as_of_trade_date"),
        "holdings": [
            {
                "code": code,
                "name": updated["holdings"][code].get("name"),
                "shares": updated["holdings"][code].get("shares"),
                "cost": updated["holdings"][code].get("cost"),
            }
            for code in sorted(new_codes)
        ],
        "removed_codes": sorted(old_codes - new_codes),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replace VPS-private holdings from a complete compact snapshot."
    )
    parser.add_argument(
        "positions",
        nargs="+",
        metavar="CODE:SHARES:COST[:NAME]",
        help="Complete snapshot. Omitted existing codes are removed.",
    )
    parser.add_argument(
        "--as-of",
        dest="as_of_trade_date",
        metavar="YYYYMMDD",
        required=True,
        help="Broker snapshot trade date; never inferred from the VPS clock.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = replace_holdings(
            args.positions,
            as_of_trade_date=args.as_of_trade_date,
            dry_run=args.dry_run,
        )
    except ValueError as exc:
        print(f"HOLDINGS update rejected: {exc}", flush=True)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
