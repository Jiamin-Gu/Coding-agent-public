import subprocess
import sys
from pathlib import Path

from report import summarize

EXPECTED = Path("data/expected.txt").read_text(encoding="utf-8").splitlines()


def test_sample_file():
    assert summarize("data/sales.csv") == EXPECTED


def test_script_output():
    out = subprocess.run([sys.executable, "report.py", "data/sales.csv"], capture_output=True,
                         text=True, encoding="utf-8")
    assert out.returncode == 0 and out.stdout.splitlines() == EXPECTED


def test_other_file(tmp_path):
    f = tmp_path / "other.csv"
    f.write_text('date,region,amount,notes\n'
                 '2025-12-31,west,"-1,000.50",big refund\n'
                 '2025-12-01,west,"3,333.33","multi\nline, with comma"\n'
                 '\n'
                 '2026-01-01,west,0.10,\n'
                 '2026-01-02,west,0.20,""\n'
                 '2026-01-02,east,5,"say ""hi"""\n', encoding="utf-8")   # 没有 BOM
    assert summarize(str(f)) == ["2025-12 west 2332.83", "2026-01 east 5.00", "2026-01 west 0.30"]


def test_header_only(tmp_path):
    f = tmp_path / "empty.csv"
    f.write_text("\ufeffdate,region,amount,notes\n", encoding="utf-8")
    assert summarize(str(f)) == []
