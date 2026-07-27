import json
from pathlib import Path

import pytest

from vaxstock.services.holdings_admin import (
    build_replacement_state,
    parse_position_spec,
    replace_holdings,
)


def test_parse_position_spec_accepts_compact_main_board_position():
    assert parse_position_spec("601138:1200:70.481") == {
        "code": "601138",
        "shares": 1200,
        "cost": 70.481,
    }
    assert parse_position_spec("002475:400:68.421:Luxshare")["name"] == "Luxshare"


@pytest.mark.parametrize(
    "spec",
    [
        "688001:100:10.0",
        "300001:100:10.0",
        "601138:0:10.0",
        "601138:100:0",
        "601138:100",
    ],
)
def test_parse_position_spec_rejects_invalid_or_disallowed_position(spec):
    with pytest.raises(ValueError):
        parse_position_spec(spec)


def test_build_replacement_preserves_history_and_marks_changed_reconciliation_stale():
    current = {
        "schema_version": 2,
        "holdings": {
            "601138": {
                "name": "FII",
                "shares": 1100,
                "available_shares": 1100,
                "cost": 71.454,
                "entry_history": {"status": "complete_cost_reconciled", "fills": [{"shares": 1100}]},
            },
            "600900": {"name": "Sold", "shares": 100, "cost": 20.0},
        },
    }
    base = {"holdings": {"601138": {"name": "FII", "concepts": ["AI"]}}}
    updated = build_replacement_state(
        current,
        base,
        [{"code": "601138", "shares": 1200, "cost": 70.481}],
        as_of_trade_date="20260722",
        generated_at="2026-07-27T12:00:00+08:00",
    )

    assert set(updated["holdings"]) == {"601138"}
    row = updated["holdings"]["601138"]
    assert row["shares"] == 1200
    assert row["cost"] == 70.481
    assert "available_shares" not in row
    assert row["entry_history"]["fills"] == [{"shares": 1100}]
    assert row["entry_history"]["status"] == "stale_after_complete_snapshot"
    assert updated["as_of_trade_date"] == "20260722"


def test_replace_holdings_writes_atomic_state_and_backup(tmp_path: Path):
    state_path = tmp_path / "private" / "holdings_state.json"
    base_path = tmp_path / "holdings.json"
    backup_dir = tmp_path / "backups"
    state_path.parent.mkdir()
    state_path.write_text(json.dumps({
        "holdings": {"600900": {"name": "Sold", "shares": 100, "cost": 20.0}}
    }), encoding="utf-8")
    base_path.write_text(json.dumps({
        "holdings": {"601138": {"name": "FII", "concepts": ["AI"]}}
    }), encoding="utf-8")

    result = replace_holdings(
        ["601138:1200:70.481"],
        state_path=state_path,
        base_path=base_path,
        backup_dir=backup_dir,
        as_of_trade_date="20260722",
        generated_at="2026-07-27T12:00:00+08:00",
    )

    assert result["status"] == "updated"
    assert result["removed_codes"] == ["600900"]
    assert Path(result["backup_path"]).exists()
    written = json.loads(state_path.read_text(encoding="utf-8"))
    assert written["holdings"]["601138"]["shares"] == 1200
    assert written["last_quick_update"]["source"] == "vps_local_complete_snapshot"


def test_replace_holdings_dry_run_does_not_write(tmp_path: Path):
    state_path = tmp_path / "holdings_state.json"
    base_path = tmp_path / "holdings.json"
    original = {"holdings": {"601138": {"name": "FII", "shares": 1100, "cost": 71.454}}}
    state_path.write_text(json.dumps(original), encoding="utf-8")
    base_path.write_text(json.dumps({"holdings": {}}), encoding="utf-8")

    result = replace_holdings(
        ["601138:1200:70.481"],
        state_path=state_path,
        base_path=base_path,
        backup_dir=tmp_path / "backups",
        dry_run=True,
    )

    assert result["status"] == "dry_run"
    assert json.loads(state_path.read_text(encoding="utf-8")) == original
    assert not (tmp_path / "backups").exists()
