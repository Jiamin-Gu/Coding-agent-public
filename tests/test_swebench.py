"""SWE-bench 适配器里不需要网络和 Docker 的部分：测试文件解析、结果判定。"""
import json

from coder import swebench as sb


def test_test_files_from_patch():
    patch = "diff --git a/testing/test_a.py b/testing/test_a.py\n--- a/x\n+++ b/x\ndiff --git a/tests/b.py b/tests/b.py\n"
    assert sb.test_files(patch) == ["testing/test_a.py", "tests/b.py"]


def test_every_selected_instance_has_an_environment_spec():
    versions = {"pytest-dev__pytest-7373": "5.4", "pallets__flask-4992": "2.3"}
    for iid, version in versions.items():
        repo = "pytest-dev/pytest" if "pytest" in iid else "pallets/flask"
        assert (repo, version) in sb.SPECS
    key = sb.env_key({"repo": "pallets/flask", "version": "2.3"})
    assert key.startswith("flask-2.3-") and sb.venv_path({"repo": "pallets/flask", "version": "2.3"}).endswith(key)


def test_pass_fail_parsing(monkeypatch, tmp_path):
    out = ("PASSED testing/test_a.py::test_ok\nPASSED testing/test_a.py::test_param[1]\n"
           "FAILED testing/test_a.py::test_bad - assert 1\nERROR testing/test_a.py::test_err\n")
    inst = {"base_commit": "abc", "test_patch": "diff --git a/testing/test_a.py b/testing/test_a.py\n",
            "FAIL_TO_PASS": json.dumps(["testing/test_a.py::test_param[1]"]),
            "PASS_TO_PASS": json.dumps(["testing/test_a.py::test_ok", "testing/test_a.py::test_bad"])}
    monkeypatch.setattr(sb, "git", lambda *a, **k: type("R", (), {"returncode": 1, "stdout": ""})())
    monkeypatch.setattr(sb, "apply_patch", lambda *a: None)
    monkeypatch.setattr(sb, "sh", lambda *a, **k: (1, out))
    solved, summary, detail = sb.run_tests(inst, tmp_path, None)
    assert not solved and detail["FAIL_TO_PASS"] == {"testing/test_a.py::test_param[1]": True}
    assert detail["PASS_TO_PASS_failed"] == ["testing/test_a.py::test_bad"] and summary.startswith("FAIL_TO_PASS 1/1")


def test_remove_tree_handles_read_only_files(tmp_path):
    """git 的对象文件是只读的（Windows 上 shutil.rmtree 默认删不掉），工作区要能删干净。"""
    import os
    import stat
    d = tmp_path / "ws" / ".git" / "objects"
    d.mkdir(parents=True)
    f = d / "pack.idx"
    f.write_text("x")
    os.chmod(f, stat.S_IREAD)
    sb.remove_tree(tmp_path / "ws")
    assert not (tmp_path / "ws").exists()
