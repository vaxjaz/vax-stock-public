# -*- coding: utf-8 -*-
"""deploy/ systemd 模板轻校验(纯文本解析, 零网络)。

不跑 systemd, 只断言关键不变量: EnvironmentFile 统一收口、ExecStart 指 v2 venv 入口、
EOD timer 含 Persistent=true。防 unit 模板被改坏(env 路径/入口/补跑漂移)。

跑法: /opt/stock-reportv2/venv/bin/python -m pytest tests/test_deploy_units.py -q
     PYTHONPATH=src python3 tests/test_deploy_units.py   # 无 pytest
"""

import configparser
import pathlib

_REPO = pathlib.Path(__file__).resolve().parents[1]
_DEPLOY = _REPO / "deploy"

_ENV_FILE = "/etc/vaxstock/vaxstock.env"
_VENV_PY = "/opt/stock-reportv2/venv/bin/python"
_WORKDIR = "/opt/stock-reportv2/vax-stock-public"

# (unit 文件, 期望的 v2 入口模块)
_SERVICES = {
    "stock-api.service": "vaxstock.services.api",
    "intraday-watch.service": "vaxstock.services.intraday",
    "vaxstock-eod.service": "vaxstock.services.eod",
    "vaxstock-preopen.service": "vaxstock.services.expectation_refresh",
    "vaxstock-dline-plan.service": "vaxstock.services.dline_plan",
}


def _parse(name):
    """systemd unit 是 ini 风格; 允许重复键(如 After/Wants), 用 strict=False。"""
    cp = configparser.ConfigParser(strict=False, interpolation=None)
    cp.optionxform = str  # 保留键大小写(ExecStart 等)
    cp.read(_DEPLOY / name, encoding="utf-8")
    return cp


def test_all_units_present():
    for name in list(_SERVICES) + [
        "vaxstock-eod.timer",
        "vaxstock-preopen.timer",
        "README.md",
    ]:
        assert (_DEPLOY / name).is_file(), f"deploy/{name} 缺失"


def test_services_env_entry_workdir():
    for name, mod in _SERVICES.items():
        cp = _parse(name)
        svc = cp["Service"]
        assert svc.get("EnvironmentFile") == _ENV_FILE, f"{name} env 未统一收口: {svc.get('EnvironmentFile')}"
        assert svc.get("WorkingDirectory") == _WORKDIR, f"{name} WorkingDirectory 漂移"
        exec_start = svc.get("ExecStart")
        assert exec_start.startswith(f"{_VENV_PY} -m {mod}"), f"{name} ExecStart 非 v2 venv 入口: {exec_start}"


def test_eod_is_oneshot_and_timer_persistent():
    # eod.service 必须 oneshot(由 timer 拉起, 非长驻)
    eod = _parse("vaxstock-eod.service")
    assert eod["Service"].get("Type") == "oneshot", "EOD 应为 oneshot"
    # eod.service 不应有 [Install](由 timer enable, 不自启)
    assert not eod.has_section("Install"), "EOD service 不应 WantedBy 自启(归 timer 管)"
    # timer: 凌晨5点 + Persistent 补跑防漏样本
    timer = _parse("vaxstock-eod.timer")
    t = timer["Timer"]
    assert t.get("Persistent") == "true", "timer 须 Persistent=true(宕机补跑防漏样本)"
    oncal = t.get("OnCalendar")
    assert "05:00" in oncal, f"EOD 调度时点应为凌晨05:00: {oncal}"
    assert "Tue-Sat" in oncal, f"EOD 应跑 Tue-Sat(周一~周五T日的次日凌晨): {oncal}"

def test_preopen_is_oneshot_and_timer_has_a_hard_preopen_schedule():
    service = _parse("vaxstock-preopen.service")
    assert service["Service"].get("Type") == "oneshot"
    assert not service.has_section("Install")
    assert "git_autocommit --stage preopen" in service["Service"].get(
        "ExecStartPost"
    )

    timer = _parse("vaxstock-preopen.timer")
    assert timer["Timer"].get("Persistent") == "true"
    oncal = timer["Timer"].get("OnCalendar")
    assert "Mon-Fri" in oncal
    assert "08:35" in oncal


def test_autocommit_hooks_are_wired_after_jobs():
    eod = (_DEPLOY / "vaxstock-eod.service").read_text(encoding="utf-8")
    eod_autocommit = "vaxstock.services.git_autocommit --stage eod"
    dline_start = "systemctl --no-block start vaxstock-dline-plan.service"
    assert eod_autocommit in eod, "EOD autocommit hook missing"
    assert dline_start in eod, "D-line async start hook missing"
    assert eod.index(eod_autocommit) < eod.index(dline_start), "EOD autocommit must run before D-line start"

    dline = (_DEPLOY / "vaxstock-dline-plan.service").read_text(encoding="utf-8")
    assert "vaxstock.services.git_autocommit --stage dline" in dline, "D-line autocommit hook missing"

def test_longrunning_services_restart_always():
    # api / intraday 长驻 -> Restart=always
    for name in ("stock-api.service", "intraday-watch.service"):
        cp = _parse(name)
        assert cp["Service"].get("Restart") == "always", f"{name} 应 Restart=always"
        assert cp.has_section("Install"), f"{name} 应有 [Install](开机自启)"


if __name__ == "__main__":
    import sys
    fns = sorted((n, f) for n, f in globals().items()
                 if n.startswith("test_") and callable(f))
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  [PASS] {name}")
        except AssertionError as e:
            failed += 1
            print(f"  [FAIL] {name}: {e}")
        except Exception as e:
            failed += 1
            print(f"  [ERROR] {name}: {type(e).__name__}: {e}")
    print(f"\n{len(fns)-failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
