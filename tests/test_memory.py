"""项目记忆：需求切分、模块卡片、持久化，以及团队模式里"主 agent 看摘要、子 agent 拿完整上下文"。"""
import json

from coder.memory import ProjectMemory, module_card, render_card, split_sections
from coder.permissions import PermissionManager
from coder.team import Team

from test_agent import FakeLLM, SilentUI, reply, tool_call
from test_team import WAIT, SubLLM, done

SPEC = """# 记账工具

一个命令行记账工具。

## 1. 金额
金额保留两位小数。

```python
# 这不是标题
x = 1
```

## 2. 报表
### 2.1 月报
按月汇总。
"""


def test_split_sections_keeps_text_and_ignores_code_blocks():
    secs = split_sections(SPEC)
    assert [(s["id"], s["level"], s["title"]) for s in secs] == [
        ("S1", 1, "记账工具"), ("S2", 2, "1. 金额"), ("S3", 2, "2. 报表"), ("S4", 3, "2.1 月报")]
    assert "# 这不是标题" in secs[1]["text"] and secs[1]["text"].startswith("## 1. 金额")
    assert secs[0]["first"] == "一个命令行记账工具。" and secs[3]["text"] == "### 2.1 月报\n按月汇总。"


def test_module_card_extracts_interface_and_project_imports():
    src = '''"""金额工具：解析和格式化。"""
from decimal import Decimal
from .errors import ValidationError
from shopkit.util import clean

LIMIT = 10


def parse(value: str) -> Decimal:
    return Decimal(value)


def _private():
    pass


class Money(Base):
    def __init__(self, amount):
        pass

    def add(self, other: "Money") -> "Money":
        pass

    def _hidden(self):
        pass
'''
    card = module_card("shopkit/money.py", src)
    assert card["summary"] == "金额工具：解析和格式化。"
    assert card["interface"] == ["LIMIT = …", "def parse(value: str) -> Decimal",
                                 "class Money(Base): __init__(amount); add(other: 'Money') -> 'Money'"]
    assert card["imports"] == [".errors: ValidationError", "shopkit.util: clean"]  # 标准库不算依赖
    assert "### shopkit/money.py" in render_card(card)
    assert "语法错误" in module_card("bad.py", "def (:")["summary"]


def test_memory_persists_and_reloads(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "SPEC.md").write_text(SPEC, encoding="utf-8")
    (tmp_path / "money.py").write_text('"""金额工具。"""\ndef parse(v):\n    return v\n', encoding="utf-8")
    mem = ProjectMemory(tmp_path)
    mem.index_doc("docs/SPEC.md")
    mem.update_card("money.py", task="core", spec=["S2"])
    mem.save_board({"contracts": {"money": {"owner": "lead", "text": "parse(v)"}}, "tasks": {}})
    text, missing = mem.sections(["S2", "S9"])
    assert "金额保留两位小数" in text and missing == ["S9"]
    overview = mem.overview()
    assert "S3 2. 报表" in overview and "def parse(v)" in overview and "money（lead）：parse(v)" in overview
    assert (tmp_path / ".coder" / "memory" / "MEMORY.md").is_file()
    again = ProjectMemory(tmp_path)  # 重启后读回来
    assert again.cards["money.py"]["task"] == "core" and again.board["contracts"]["money"]["text"] == "parse(v)"
    assert "按月汇总" in again.sections(["S4"])[0]


def make_team(tmp_path, scripts):
    queue = [FakeLLM(scripts[0])] + [SubLLM(s) for s in scripts[1:]]
    llms = list(queue)
    team = Team(lambda: queue.pop(0), tmp_path, PermissionManager(ask=lambda *a: ("y", ""), auto=True),
                SilentUI(), max_steps=10, quality_roles=False)
    return team, llms


def test_lead_sees_summary_sub_agent_gets_full_task_context(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "SPEC.md").write_text(SPEC, encoding="utf-8")
    plan = {"tasks": [
        {"id": "money", "role": "backend", "description": "实现金额", "files": ["money.py"], "spec_sections": ["S2"]},
        {"id": "report", "role": "backend", "description": "实现月报", "files": ["report.py"], "depends": ["money"],
         "spec_sections": ["S4"]}],
        "contracts": [{"name": "money", "text": "parse(v) -> str"}]}
    lead = [reply(calls=[tool_call("i", "index_docs", paths=["docs/SPEC.md"])]),
            reply(calls=[tool_call("p", "plan_tasks", **plan)]),
            reply(calls=[tool_call("d1", "dispatch", task_ids=["money"])]), WAIT,
            reply(calls=[tool_call("d2", "dispatch", task_ids=["report"])]), WAIT,
            reply(calls=[tool_call("m", "memory")]),
            reply("完成")]
    money = [reply(calls=[tool_call("w", "write_file", path="money.py",
                                    content='"""金额工具。"""\ndef parse(v):\n    return f"{v:.2f}"\n')]),
             done("money 完成")]
    report = [reply(calls=[tool_call("s", "spec_section", ids=["S1"])]),
              reply(calls=[tool_call("w", "write_file", path="report.py", content='"""月报。"""\n')]),
              done("report 完成")]
    team, llms = make_team(tmp_path, [lead, money, report])
    team.run("按 docs/SPEC.md 实现")

    assert "S2 1. 金额" in llms[0].seen[1][-1]["content"]  # index_docs 返回目录
    money_first = llms[1].seen[0][1]["content"]
    assert "金额保留两位小数" in money_first and "按月汇总" not in money_first  # 只拿到自己的需求小节原文
    report_first = llms[2].seen[0][1]["content"]
    assert "按月汇总" in report_first and "金额保留两位小数" not in report_first
    assert "def parse(v)" in report_first and 'return f"{v:.2f}"' not in report_first  # 依赖模块只给接口，不给实现
    assert "一个命令行记账工具" in llms[2].seen[1][-1]["content"]  # 子 agent 可以按需读别的小节
    overview = llms[0].seen[7][-1]["content"]  # 主 agent 的 memory()：摘要版
    assert "money.py" in overview and "金额工具。" in overview and "report [done]" in overview
    saved = json.loads((tmp_path / ".coder" / "memory" / "memory.json").read_text(encoding="utf-8"))
    assert saved["board"]["tasks"]["money"]["status"] == "done" and "money.py" in saved["cards"]
    assert saved["cards"]["money.py"]["task"] == "money" and saved["cards"]["money.py"]["spec"] == ["S2"]


def test_lead_compaction_keeps_project_memory(tmp_path):
    big = "很长的输出" * 2000
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "SPEC.md").write_text(SPEC, encoding="utf-8")
    lead = [reply(calls=[tool_call("i", "index_docs", paths=["docs/SPEC.md"])]),
            reply(calls=[tool_call("r", "read_file", path="docs/SPEC.md")]),
            reply("摘要：建了索引"), reply("完成")]
    team, llms = make_team(tmp_path, [lead])
    team.lead.context_limit = 3000
    team.lead.max_tool_output = 100_000
    team.lead.tools["read_file"].run = lambda **kw: big
    team.run("实现")
    summary = [m["content"] for m in team.lead.messages if "压缩为以下摘要" in str(m.get("content"))][0]
    assert "【项目记忆】" in summary and "S4 2.1 月报" in summary  # 压缩后不用重读整个项目
