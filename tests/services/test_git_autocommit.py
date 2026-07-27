# -*- coding: utf-8 -*-

from vaxstock.services import git_autocommit as ga


def test_parse_status_porcelain_plain_and_rename():
    entries = ga.parse_status_porcelain(
        " M var/reports/2026-07-03/claude.md\n"
        "?? var/forecast/current_tasks.md\n"
        "R  old/name.json -> var/eval/factor_results.jsonl\n"
    )

    assert [entry.status for entry in entries] == [" M", "??", "R "]
    assert [entry.path for entry in entries] == [
        "var/reports/2026-07-03/claude.md",
        "var/forecast/current_tasks.md",
        "var/eval/factor_results.jsonl",
    ]


def test_blocking_status_entries_refuses_code_changes():
    entries = ga.parse_status_porcelain(
        " M var/reports/2026-07-03/payload.json\n"
        "?? src/vaxstock/services/debug_tmp.py\n"
        " M script/config/secrets.json\n"
    )

    blockers = ga.blocking_status_entries(entries, ga.STAGE_PATHS["eod"])

    assert [entry.path for entry in blockers] == [
        "src/vaxstock/services/debug_tmp.py",
        "script/config/secrets.json",
    ]


def test_eod_and_preopen_allow_normalized_research_outputs():
    entries = ga.parse_status_porcelain(
        " M var/research/observations.jsonl\n"
        "?? var/research/factor_values/20260728.jsonl\n"
        " M var/research/run_manifests.jsonl\n"
    )

    assert ga.blocking_status_entries(entries, ga.STAGE_PATHS["eod"]) == []
    assert ga.blocking_status_entries(entries, ga.STAGE_PATHS["preopen"]) == []


def test_preopen_trade_date_comes_from_expectation_manifest(tmp_path):
    target = tmp_path / "var" / "research"
    target.mkdir(parents=True)
    (target / "run_manifests.jsonl").write_text(
        '{"stage":"legacy_replay","as_of_trade_date":"20260727"}\n'
        '{"stage":"expectation_refresh","as_of_trade_date":"20260728"}\n',
        encoding="utf-8",
    )

    assert ga._infer_trade_date(tmp_path, "preopen") == "20260728"


def test_dline_stage_allows_current_markdown_and_task_history():
    entries = ga.parse_status_porcelain(
        " M var/forecast/current_tasks.json\n"
        "?? var/forecast/current_tasks.md\n"
        " M var/forecast/observation_tasks.jsonl\n"
    )

    assert ga.blocking_status_entries(entries, ga.STAGE_PATHS["dline"]) == []




def test_intraday_stage_allows_forecasts_and_task_context_only():
    entries = ga.parse_status_porcelain(
        " M var/forecast/forecasts.jsonl\n"
        " M var/forecast/current_tasks.json\n"
        "?? src/vaxstock/services/tmp_debug.py\n"
    )

    blockers = ga.blocking_status_entries(entries, ga.STAGE_PATHS["intraday"])

    assert [entry.path for entry in blockers] == ["src/vaxstock/services/tmp_debug.py"]



def test_stage_specific_intraday_filter_allows_forecasts_row():
    entries = ga.parse_status_porcelain(" M var/forecast/forecasts.jsonl\n")

    assert ga.blocking_status_entries_for_stage("intraday", entries) == []



def test_run_autocommit_intraday_dry_run_does_not_block_forecasts(monkeypatch=None):
    class FakeStatus:
        returncode = 0
        stdout = " M var/forecast/forecasts.jsonl\n M src/vaxstock/services/tmp_debug.py\n"
        stderr = ""

    old_run_git = ga._run_git
    old_enabled = ga.os.environ.get("GIT_AUTOCOMMIT_ENABLED")
    try:
        ga.os.environ["GIT_AUTOCOMMIT_ENABLED"] = "1"
        ga._run_git = lambda *a, **k: FakeStatus()
        result = ga.run_autocommit("intraday", root=ga.Path("."), dry_run=True)
        assert result["status"] == "dry_run"
        assert result["changed"] == [" M var/forecast/forecasts.jsonl", " M src/vaxstock/services/tmp_debug.py"]
    finally:
        ga._run_git = old_run_git
        if old_enabled is None:
            ga.os.environ.pop("GIT_AUTOCOMMIT_ENABLED", None)
        else:
            ga.os.environ["GIT_AUTOCOMMIT_ENABLED"] = old_enabled

if __name__ == "__main__":
    import sys

    failed = 0
    for name, fn in sorted((n, f) for n, f in globals().items() if n.startswith("test_")):
        try:
            fn()
            print(f"  [PASS] {name}")
        except AssertionError as exc:
            failed += 1
            print(f"  [FAIL] {name}: {exc}")
    print(f"\n{6 - failed}/6 passed")
    sys.exit(1 if failed else 0)
