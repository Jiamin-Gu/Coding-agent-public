from pathlib import Path

from billing import api, core, report


def test_new_name_works():
    assert core.compute_total([(10, 2), (5, 1)]) == 25
    assert core.compute_total([(100, 1)], tax_rate=0.06) == 106


def test_callers_updated():
    assert report.summary({"A1": [(3, 3)]}) == {"A1": 9}
    assert api.quote([(100, 1)], "us") == {"region": "us", "total": 108}
    import main
    assert main.run() == 1


def test_old_name_gone():
    for f in Path(".").rglob("*.py"):
        if "_eval_tests" in f.parts:
            continue
        assert "calc_total" not in f.read_text(encoding="utf-8"), f
