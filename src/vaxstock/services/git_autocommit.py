# -*- coding: utf-8 -*-
"""Commit generated EOD/D-line artifacts after systemd jobs finish.

This module is intentionally narrow:
  - it only stages whitelisted generated data paths;
  - it refuses to run when non-whitelisted files are dirty;
  - it never stores credentials or changes remotes.

Production usage is via systemd ExecStartPost:
    python -m vaxstock.services.git_autocommit --stage eod
    python -m vaxstock.services.git_autocommit --stage dline
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from vaxstock import config


DEFAULT_REMOTE = "origin"
DEFAULT_AUTHOR_NAME = "vaxstock-bot"
DEFAULT_AUTHOR_EMAIL = "vaxstock-bot@users.noreply.github.com"

STAGE_PATHS: Dict[str, Tuple[str, ...]] = {
    # EOD owns A/B/C outputs plus the D-line async job envelope.
    "eod": (
        "var/reports",
        "var/eval",
        "var/prediction",
        "var/forecast/current_job.json",
        "var/forecast/observation_jobs.jsonl",
    ),
    # D-line planner owns task history and the current readable task snapshot.
    "dline": (
        "var/forecast/current_job.json",
        "var/forecast/current_tasks.json",
        "var/forecast/current_tasks.md",
        "var/forecast/observation_tasks.jsonl",
    ),
    "all": (
        "var/reports",
        "var/eval",
        "var/prediction",
        "var/forecast",
    ),
}


@dataclass(frozen=True)
class GitStatusEntry:
    status: str
    path: str
    raw: str


@dataclass
class GitCommandResult:
    returncode: int
    stdout: str
    stderr: str


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _log(message: str) -> None:
    print(f"{_now()} git-autocommit: {message}", flush=True)


def _truthy(value: Optional[str], default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _norm_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def is_allowed_path(path: str, allowed_paths: Iterable[str]) -> bool:
    normalized = _norm_path(path)
    for allowed in allowed_paths:
        prefix = _norm_path(allowed).rstrip("/")
        if normalized == prefix or normalized.startswith(prefix + "/"):
            return True
    return False


def parse_status_porcelain(output: str) -> List[GitStatusEntry]:
    """Parse `git status --porcelain=v1` text output.

    We only need status and destination path. For renames, git prints
    `old -> new`; the destination decides whether the generated artifact is
    inside the whitelist.
    """
    entries: List[GitStatusEntry] = []
    for raw in output.splitlines():
        if not raw:
            continue
        if len(raw) < 4:
            entries.append(GitStatusEntry(status=raw[:2], path="", raw=raw))
            continue
        status = raw[:2]
        path = raw[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        entries.append(GitStatusEntry(status=status, path=_norm_path(path), raw=raw))
    return entries


def blocking_status_entries(entries: Iterable[GitStatusEntry],
                            allowed_paths: Iterable[str]) -> List[GitStatusEntry]:
    return [entry for entry in entries if not is_allowed_path(entry.path, allowed_paths)]


def _run_git(args: Sequence[str], cwd: Path, timeout: int = 120) -> GitCommandResult:
    env = os.environ.copy()
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    env.setdefault("GCM_INTERACTIVE", "never")
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
    )
    return GitCommandResult(proc.returncode, proc.stdout.strip(), proc.stderr.strip())


def _stage_paths_existing(root: Path, allowed_paths: Iterable[str]) -> List[str]:
    out: List[str] = []
    for path in allowed_paths:
        if (root / path).exists():
            out.append(path)
    return out


def _current_branch(root: Path) -> Optional[str]:
    res = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], root)
    if res.returncode != 0:
        return None
    branch = res.stdout.strip()
    if not branch or branch == "HEAD":
        return None
    return branch


def _infer_trade_date(root: Path, stage: str) -> str:
    if stage == "dline":
        current_tasks = root / "var" / "forecast" / "current_tasks.json"
        if current_tasks.exists():
            try:
                import json

                data = json.loads(current_tasks.read_text(encoding="utf-8"))
                target = data.get("target_trade_date")
                if target:
                    return str(target)
            except Exception:
                pass
    reports = root / "var" / "reports"
    if reports.exists():
        dirs = sorted(p.name for p in reports.iterdir() if p.is_dir())
        if dirs:
            return dirs[-1].replace("-", "")
    return datetime.now().strftime("%Y%m%d")


def _commit(root: Path, stage: str, trade_date: str) -> GitCommandResult:
    author_name = os.getenv("GIT_AUTOCOMMIT_AUTHOR_NAME", DEFAULT_AUTHOR_NAME)
    author_email = os.getenv("GIT_AUTOCOMMIT_AUTHOR_EMAIL", DEFAULT_AUTHOR_EMAIL)
    message = f"chore(data): auto {stage} {trade_date}"
    body = "Generated by vaxstock.services.git_autocommit."
    return _run_git(
        [
            "-c",
            f"user.name={author_name}",
            "-c",
            f"user.email={author_email}",
            "commit",
            "-m",
            message,
            "-m",
            body,
        ],
        root,
        timeout=180,
    )


def _push(root: Path, remote: str, branch: str) -> Tuple[bool, str]:
    fetch = _run_git(["fetch", remote, branch], root, timeout=180)
    if fetch.returncode != 0:
        return False, f"fetch failed: {fetch.stderr or fetch.stdout}"

    remote_ref = f"{remote}/{branch}"
    verify = _run_git(["rev-parse", "--verify", remote_ref], root)
    if verify.returncode == 0:
        rebase = _run_git(["rebase", remote_ref], root, timeout=300)
        if rebase.returncode != 0:
            abort = _run_git(["rebase", "--abort"], root, timeout=120)
            abort_msg = "" if abort.returncode == 0 else f"; rebase abort failed: {abort.stderr or abort.stdout}"
            return False, f"rebase failed: {rebase.stderr or rebase.stdout}{abort_msg}"

    push = _run_git(["push", remote, f"HEAD:{branch}"], root, timeout=300)
    if push.returncode != 0:
        return False, f"push failed: {push.stderr or push.stdout}"
    return True, push.stdout or push.stderr or "pushed"


def run_autocommit(stage: str, root: Optional[Path] = None, dry_run: bool = False) -> Dict[str, object]:
    if stage not in STAGE_PATHS:
        raise ValueError(f"unknown stage: {stage}")

    enabled = _truthy(os.getenv("GIT_AUTOCOMMIT_ENABLED"), default=False)
    if not enabled:
        _log("disabled; set GIT_AUTOCOMMIT_ENABLED=1 to enable")
        return {"status": "disabled", "stage": stage}

    repo = root or config.PROJECT_ROOT
    allowed_paths = STAGE_PATHS[stage]
    status_res = _run_git(["status", "--porcelain=v1", "--untracked-files=all"], repo)
    if status_res.returncode != 0:
        _log(f"status failed: {status_res.stderr or status_res.stdout}")
        return {"status": "error", "stage": stage, "error": "status_failed"}

    entries = parse_status_porcelain(status_res.stdout)
    blockers = blocking_status_entries(entries, allowed_paths)
    if blockers:
        preview = "; ".join(entry.raw for entry in blockers[:8])
        _log(f"skip: non-whitelisted dirty files present: {preview}")
        return {
            "status": "skipped_dirty",
            "stage": stage,
            "blocking": [entry.raw for entry in blockers],
        }

    stage_paths = _stage_paths_existing(repo, allowed_paths)
    if not stage_paths:
        _log(f"skip: no configured paths exist for stage={stage}")
        return {"status": "clean", "stage": stage}

    if dry_run:
        changed = [entry.raw for entry in entries]
        _log(f"dry-run stage={stage} changed={len(changed)}")
        return {"status": "dry_run", "stage": stage, "changed": changed}

    add = _run_git(["add", "-A", "--", *stage_paths], repo, timeout=180)
    if add.returncode != 0:
        _log(f"git add failed: {add.stderr or add.stdout}")
        return {"status": "error", "stage": stage, "error": "add_failed"}

    diff = _run_git(["diff", "--cached", "--quiet", "--exit-code"], repo)
    if diff.returncode == 0:
        _log(f"clean: no staged generated changes for stage={stage}")
        return {"status": "clean", "stage": stage}
    if diff.returncode != 1:
        _log(f"diff failed: {diff.stderr or diff.stdout}")
        return {"status": "error", "stage": stage, "error": "diff_failed"}

    trade_date = _infer_trade_date(repo, stage)
    commit = _commit(repo, stage, trade_date)
    if commit.returncode != 0:
        _log(f"commit failed: {commit.stderr or commit.stdout}")
        return {"status": "error", "stage": stage, "error": "commit_failed"}

    commit_line = commit.stdout.splitlines()[-1] if commit.stdout else "committed"
    _log(f"committed stage={stage} date={trade_date}: {commit_line}")

    push_enabled = _truthy(os.getenv("GIT_AUTOCOMMIT_PUSH"), default=True)
    if not push_enabled:
        return {"status": "committed", "stage": stage, "trade_date": trade_date}

    branch = os.getenv("GIT_AUTOCOMMIT_BRANCH") or _current_branch(repo)
    if not branch:
        _log("push skipped: detached HEAD or branch unknown")
        return {"status": "committed_no_push", "stage": stage, "trade_date": trade_date}

    remote = os.getenv("GIT_AUTOCOMMIT_REMOTE", DEFAULT_REMOTE)
    ok, msg = _push(repo, remote, branch)
    if not ok:
        _log(msg)
        return {"status": "commit_push_failed", "stage": stage, "trade_date": trade_date, "error": msg}
    _log(f"pushed stage={stage} branch={branch}")
    return {"status": "pushed", "stage": stage, "trade_date": trade_date, "branch": branch}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Auto-commit generated vaxstock data artifacts.")
    parser.add_argument("--stage", choices=sorted(STAGE_PATHS), required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = run_autocommit(args.stage, dry_run=args.dry_run)
        print(f"GIT autocommit done: {result}", flush=True)
        return 0
    except subprocess.TimeoutExpired as exc:
        _log(f"timeout: {exc}")
        return 1
    except Exception as exc:
        _log(f"unexpected error: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
