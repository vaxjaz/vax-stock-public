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
    print(f"\n{5 - failed}/5 passed")
    sys.exit(1 if failed else 0)
