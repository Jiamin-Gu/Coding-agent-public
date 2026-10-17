"""工具基类。每个工具 = 名字 + 描述 + JSON Schema 参数 + 执行函数。"""
import json

from ..workspace import Workspace


class ToolError(Exception):
    """工具执行失败。消息会作为工具结果返回给模型，让它自己调整。"""


class Tool:
    name: str = ""
    description: str = ""
    parameters: dict = {"type": "object", "properties": {}}
    # 有副作用的工具（写文件、执行命令）需要用户确认
    needs_permission: bool = False

    def __init__(self, workspace: Workspace):
        self.ws = workspace

    def run(self, **kwargs) -> str:
        raise NotImplementedError

    def preview(self, **kwargs) -> str:
        """请求权限时展示给用户看的内容，比如改动的 diff。"""
        return json.dumps(kwargs, ensure_ascii=False, indent=2)

    def schema(self) -> dict:
        """转成 OpenAI 兼容的 function calling 格式（DeepSeek 也用这个格式）。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
