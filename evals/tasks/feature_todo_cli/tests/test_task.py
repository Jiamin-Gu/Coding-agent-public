import json

import pytest

import todo


@pytest.fixture(autouse=True)
def in_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def test_add_and_list_format(capsys):
    todo.main(["add", "买牛奶"])
    todo.main(["list"])
    out = capsys.readouterr().out
    assert "已添加 #1: 买牛奶" in out
    assert "[ ] #1 买牛奶" in out


def test_done_command_and_function(capsys):
    todo.main(["add", "a"])
    todo.main(["add", "b"])
    todo.main(["done", "2"])
    capsys.readouterr()
    todo.main(["list"])
    out = capsys.readouterr().out
    assert "[ ] #1 a" in out and "[x] #2 b" in out
    assert todo.done(1)["done"] is True
    with pytest.raises(KeyError):
        todo.done(99)


def test_list_pending(capsys):
    todo.main(["add", "a"])
    todo.main(["add", "b"])
    todo.main(["done", "1"])
    capsys.readouterr()
    todo.main(["list", "--pending"])
    out = capsys.readouterr().out
    assert "#2 b" in out and "#1 a" not in out


def test_new_id_after_manual_delete():
    with open("todos.json", "w", encoding="utf-8") as f:
        json.dump([{"id": 1, "title": "a", "done": False}, {"id": 3, "title": "c", "done": False}], f)
    assert todo.add("d")["id"] == 4
