"""一个极简的待办事项命令行工具，数据保存在当前目录的 todos.json。"""
import argparse
import json
from pathlib import Path

DB = Path("todos.json")


def load():
    if DB.exists():
        return json.loads(DB.read_text(encoding="utf-8"))
    return []


def save(todos):
    DB.write_text(json.dumps(todos, ensure_ascii=False, indent=2), encoding="utf-8")


def add(title):
    todos = load()
    todo = {"id": len(todos) + 1, "title": title, "done": False}
    todos.append(todo)
    save(todos)
    return todo


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_add = sub.add_parser("add")
    p_add.add_argument("title")
    sub.add_parser("list")
    args = parser.parse_args(argv)
    if args.cmd == "add":
        todo = add(args.title)
        print(f"已添加 #{todo['id']}: {todo['title']}")
    elif args.cmd == "list":
        for t in load():
            print(f"[{'x' if t['done'] else ' '}] #{t['id']} {t['title']}")


if __name__ == "__main__":
    main()
