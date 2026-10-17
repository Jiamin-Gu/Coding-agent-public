from ..workspace import Workspace
from .base import Tool, ToolError
from .fs import EditFile, Grep, ListDir, ReadFile, WriteFile
from .process import PROCESS_TOOLS, ProcessManager
from .shell import RunCommand

ALL_TOOLS = [ListDir, ReadFile, Grep, WriteFile, EditFile, RunCommand]


def build_tools(workspace: Workspace, processes: ProcessManager | None = None, sandbox=None, mcp=None) -> dict[str, Tool]:
    """processes：后台进程管理器。同一个会话（包括团队里的所有 agent）共用一个，会话结束时统一终止。
    sandbox：沙箱容器（sandbox.DockerSandbox）。给了的话命令都在容器里执行，processes 也要用同一个沙箱创建。
    mcp：已经启动的 MCP 服务器（mcp.MCPManager），它们的工具一并加入。"""
    tools = {cls.name: cls(workspace) for cls in ALL_TOOLS if cls is not RunCommand}
    tools["run_command"] = RunCommand(workspace, sandbox)
    processes = processes or ProcessManager(sandbox)
    tools.update({cls.name: cls(workspace, processes) for cls in PROCESS_TOOLS})
    if mcp:  # MCP 服务器提供的工具（mcp.MCPManager）
        tools.update(mcp.tools(workspace))
    return tools


__all__ = ["Tool", "ToolError", "build_tools", "ALL_TOOLS", "ProcessManager"]
