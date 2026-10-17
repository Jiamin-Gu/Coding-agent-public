"""沙箱的工作区副本：复制、改动对比、应用（含冲突）、放弃、同步用户的修改、重启后恢复、跳过依赖目录和 .git。"""
import os

from coder.shadow import Shadow, describe


def make(tmp_path):
    real = tmp_path / "proj"
    (real / "src").mkdir(parents=True)
    (real / "src" / "a.py").write_text("a = 1\n", encoding="utf-8")
    (real / "README.md").write_text("# 项目\n", encoding="utf-8")
    (real / "node_modules" / "x").mkdir(parents=True)
    (real / "node_modules" / "x" / "big.js").write_text("// 依赖", encoding="utf-8")
    (real / ".git").mkdir()
    (real / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    s = Shadow(real, tmp_path / "copies" / "c1")
    s.ensure()
    return real, s


def test_copy_skips_dependencies_and_keeps_git(tmp_path):
    real, s = make(tmp_path)
    assert (s.copy / "src" / "a.py").read_text(encoding="utf-8") == "a = 1\n"
    assert not (s.copy / "node_modules").exists()          # 依赖目录不复制
    assert (s.copy / ".git" / "HEAD").is_file()              # .git 复制一份，agent 能看 git status
    assert not s.pending()


def test_changes_and_apply(tmp_path):
    real, s = make(tmp_path)
    (s.copy / "src" / "a.py").write_text("a = 2\n", encoding="utf-8")
    (s.copy / "src" / "b.py").write_text("b = 1\n", encoding="utf-8")
    (s.copy / "README.md").unlink()
    (s.copy / ".git" / "HEAD").write_text("被命令改了\n", encoding="utf-8")   # .git 的变化不算改动
    (s.copy / "node_modules").mkdir()
    (s.copy / "node_modules" / "new.js").write_text("x", encoding="utf-8")  # 容器里装的依赖也不算
    ch = s.changes()
    assert ch == {"added": ["src/b.py"], "modified": ["src/a.py"], "deleted": ["README.md"]}
    assert (real / "src" / "a.py").read_text(encoding="utf-8") == "a = 1\n"  # 真实项目没动
    assert "新增 1 个" in describe(ch) and "+src/b.py" in describe(ch)
    result = s.apply()
    assert sorted(result["applied"]) == ["README.md", "src/a.py", "src/b.py"] and not result["conflicts"]
    assert (real / "src" / "a.py").read_text(encoding="utf-8") == "a = 2\n" and (real / "src" / "b.py").is_file()
    assert not (real / "README.md").exists()
    assert (real / ".git" / "HEAD").read_text(encoding="utf-8") == "ref: refs/heads/main\n"
    assert not s.pending()


def test_conflict_when_user_edited_same_file(tmp_path):
    real, s = make(tmp_path)
    (s.copy / "src" / "a.py").write_text("agent 改的\n", encoding="utf-8")
    (s.copy / "README.md").write_text("# agent 也改了\n", encoding="utf-8")
    (real / "src" / "a.py").write_text("用户自己改的\n", encoding="utf-8")
    result = s.apply()
    assert result == {"applied": ["README.md"], "conflicts": ["src/a.py"]}
    assert (real / "src" / "a.py").read_text(encoding="utf-8") == "用户自己改的\n"  # 不覆盖用户的修改
    assert s.changes()["modified"] == ["src/a.py"]                                   # 冲突的仍然待处理


def test_discard_restores_copy(tmp_path):
    real, s = make(tmp_path)
    (s.copy / "src" / "a.py").write_text("a = 2\n", encoding="utf-8")
    (s.copy / "new.txt").write_text("x", encoding="utf-8")
    (s.copy / "README.md").unlink()
    assert sorted(s.discard()) == ["README.md", "new.txt", "src/a.py"]
    assert (s.copy / "src" / "a.py").read_text(encoding="utf-8") == "a = 1\n"
    assert not (s.copy / "new.txt").exists() and (s.copy / "README.md").is_file()
    assert not s.pending()


def test_refresh_brings_user_edits_into_copy(tmp_path):
    real, s = make(tmp_path)
    (real / "src" / "a.py").write_text("用户改了\n", encoding="utf-8")
    (real / "c.py").write_text("c = 1\n", encoding="utf-8")
    (real / "README.md").unlink()
    assert sorted(s.refresh()) == ["README.md", "c.py", "src/a.py"]
    assert (s.copy / "src" / "a.py").read_text(encoding="utf-8") == "用户改了\n" and (s.copy / "c.py").is_file()
    assert not (s.copy / "README.md").exists() and not s.pending()
    (s.copy / "c.py").write_text("agent 改的\n", encoding="utf-8")   # 有待应用的改动时不同步，免得盖掉
    (real / "src" / "a.py").write_text("用户又改了\n", encoding="utf-8")
    assert s.refresh() == []
    assert (s.copy / "src" / "a.py").read_text(encoding="utf-8") == "用户改了\n"


def test_state_survives_restart(tmp_path):
    real, s = make(tmp_path)
    (s.copy / "src" / "a.py").write_text("a = 2\n", encoding="utf-8")
    again = Shadow(real, s.copy)
    again.ensure()                                   # 服务重启：读回基准，不重新复制
    assert again.changes()["modified"] == ["src/a.py"]
    again.remove()
    assert not s.copy.exists() and not s.state_file.exists()


def test_unchanged_files_are_not_rehashed(tmp_path, monkeypatch):
    real, s = make(tmp_path)
    s.changes()
    import coder.shadow as mod
    calls = []
    monkeypatch.setattr(mod, "_sha", lambda p: calls.append(p) or "x")
    s.changes()
    assert calls == []                               # 大小和修改时间没变：不重新算哈希
    os.utime(s.copy / "src" / "a.py", (1, 1))
    s.changes()
    assert len(calls) == 1
