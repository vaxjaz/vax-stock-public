import json
from vaxstock import config
from vaxstock.services._t1_baseline import load_t1_baseline


def test_current_baseline_replaces_date_archives(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STATE_DIR", tmp_path)
    path = tmp_path / 'eod/current_baseline.json'
    path.parent.mkdir()
    path.write_text(json.dumps({'market_overview': {'trade_date': '20260703'},
                               'stocks': [{'code': '002475', 'right_side_score': 2.5,
                                           'main_inflow_10d_yuan': 1e8}]}))
    assert load_t1_baseline('002475') == {
        'score': 2.5, 'grade': None, 'position_20d_pct': None,
        'main_inflow_10d': 1e8, 'np_yoy': None, 'baseline_date': '2026-07-03'}
    assert load_t1_baseline('600519') is None
    path.write_text('{}')
    assert load_t1_baseline('002475') is None


def test_missing_current_baseline_does_not_read_old_report(tmp_path, monkeypatch):
    monkeypatch.setattr(config, 'STATE_DIR', tmp_path)
    monkeypatch.setattr(config, 'REPORTS_DIR', tmp_path / 'reports')
    path = tmp_path / 'reports/2026-07-03'
    path.mkdir(parents=True)
    (path / 'claude.json').write_text(json.dumps({'stocks': [{'code': '002475'}]}))
    assert load_t1_baseline('002475') is None
