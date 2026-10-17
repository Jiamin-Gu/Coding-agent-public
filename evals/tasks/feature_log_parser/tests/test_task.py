from log_stats import analyze


def test_sample_log():
    r = analyze("logs/app.log")
    assert r["total"] == 7
    assert r["by_level"] == {"INFO": 3, "ERROR": 3, "WARN": 1}
    assert r["error_users"] == ["alice", "bob"]
    assert r["avg_latency_ms"] == 1544.3
    assert r["slowest"] == "search"


def test_only_bad_lines(tmp_path):
    f = tmp_path / "bad.log"
    f.write_text("garbage\n\nnot a log line at all\n", encoding="utf-8")
    r = analyze(str(f))
    assert r["total"] == 0
    assert r["by_level"] == {}
    assert r["error_users"] == []
    assert r["avg_latency_ms"] == 0.0
    assert r["slowest"] is None
