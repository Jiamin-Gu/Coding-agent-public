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
    todo = {"id": max((t["id"] for t in todos), default=0) + 1, "title": title, "done": False}
    todos.append(todo)
    save(todos)
    return todo


def done(todo_id):
    todos = load()
    for t in todos:
        if t["id"] == todo_id:
            t["done"] = True
            save(todos)
            return t
    raise KeyError(todo_id)


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_add = sub.add_parser("add")
    p_add.add_argument("title")
    p_list = sub.add_parser("list")
    p_list.add_argument("--pending", action="store_true")
    p_done = sub.add_parser("done")
    p_done.add_argument("id", type=int)
    args = parser.parse_args(argv)
    if args.cmd == "add":
        todo = add(args.title)
        print(f"已添加 #{todo['id']}: {todo['title']}")
    elif args.cmd == "list":
        for t in load():
            if args.pending and t["done"]:
                continue
            print(f"[{'x' if t['done'] else ' '}] #{t['id']} {t['title']}")
    elif args.cmd == "done":
        t = done(args.id)
        print(f"已完成 #{t['id']}: {t['title']}")


if __name__ == "__main__":
    main()
