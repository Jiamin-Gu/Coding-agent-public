"""演示用的假模型：按固定剧本调用工具，不需要 API key，用来展示界面和完整流程。"""
import json
import time
from types import SimpleNamespace

HELLO_V1 = 'def greet(name):\n    return f"Hello, {name}!"\n\n\nif __name__ == "__main__":\n    print(greet("world"))\n'

# 每一步：(思考, 回复文字, 工具名, 参数)；工具名为 None 表示结束
SCRIPT = [
    ("用户想要一个 hello 程序。先看看工作区里已有什么文件。", "我先看看项目里有什么。", "list_dir", {"path": "."}),
    ("目录是空的，直接新建 hello.py，写一个 greet 函数。", "项目是空的，我来创建一个 hello.py。",
     "write_file", {"path": "hello.py", "content": HELLO_V1}),
    ("写完要运行验证。", "运行一下验证。", "run_command", {"command": "python hello.py"}),
    ("输出正确。用户要求把问候语改成中文，用 edit_file 精确替换那一行。", "运行正常。按要求把问候语改成中文。", "edit_file", {
        "path": "hello.py", "old_string": 'return f"Hello, {name}!"', "new_string": 'return f"你好，{name}！"'}),
    ("改完再运行一次确认。", "再运行一次确认修改生效。", "run_command", {"command": "python hello.py"}),
    ("两次运行都正常，可以总结了。", "完成了！我做了这些事：\n\n1. 新建 `hello.py`，包含一个 `greet` 函数\n"
     "2. 运行验证输出 `Hello, world!`\n3. 把问候语改成中文，再次运行确认\n\n"
     "```python\ndef greet(name):\n    return f\"你好，{name}！\"\n```", None, None),
]


class DemoLLM:
    def __init__(self, delay: float = 0.02):
        self.model = "demo（脚本化假模型）"
        self.base_url = "（演示模式，不调用 API）"
        self.delay = delay  # 每个字的间隔，模拟流式输出

    def _stream(self, kind, text, on_delta):
        if not on_delta:
            return
        for i in range(0, len(text), 3):
            on_delta(kind, text[i:i + 3])
            if self.delay:
                time.sleep(self.delay)

    def chat(self, messages, tools, on_delta=None):
        # 根据最后一条用户消息之后已有几轮回复，决定执行剧本的第几步
        last_user = max(i for i, m in enumerate(messages) if m["role"] == "user")
        step = sum(1 for m in messages[last_user:] if m["role"] == "assistant")
        thought, text, tool, args = SCRIPT[min(step, len(SCRIPT) - 1)]
        self._stream("reasoning", thought, on_delta)
        self._stream("text", text, on_delta)
        calls = None
        if tool:
            calls = [SimpleNamespace(id=f"demo_{last_user}_{step}", function=SimpleNamespace(
                name=tool, arguments=json.dumps(args, ensure_ascii=False)))]
        usage = SimpleNamespace(prompt=800 + 150 * step, completion=60, cached=600 if step else 0)
        return SimpleNamespace(content=text, reasoning_content=thought, tool_calls=calls, usage=usage)
