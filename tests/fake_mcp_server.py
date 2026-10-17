"""测试用的迷你 MCP 服务器（stdio）：按行读 JSON-RPC，实现握手、分页列工具、调用工具，还会反过来向客户端请求 roots。"""
import json
import sys

TOOLS = [
    {"name": "echo", "description": "原样返回文字", "inputSchema": {
        "$schema": "http://json-schema.org/draft-07/schema#", "type": "object",
        "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    {"name": "screenshot", "description": "返回一张图片", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "broken", "description": "总是报错", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "where", "description": "问客户端工作区在哪", "inputSchema": {"type": "object", "properties": {}}},
]
PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
next_id = 1000


def send(msg):
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def read():
    line = sys.stdin.readline()
    return json.loads(line) if line else None


def main():
    global next_id
    sys.stderr.write("fake server starting\n")
    while True:
        msg = read()
        if msg is None:
            return
        method, rid = msg.get("method"), msg.get("id")
        if rid is None:  # 通知
            continue
        if method == "initialize":
            send({"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": msg["params"]["protocolVersion"], "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake", "version": "0.1"}}})
        elif method == "tools/list":  # 分两页
            cursor = (msg.get("params") or {}).get("cursor")
            page = TOOLS[2:] if cursor else TOOLS[:2]
            send({"jsonrpc": "2.0", "id": rid, "result": {"tools": page, **({} if cursor else {"nextCursor": "p2"})}})
        elif method == "tools/call":
            name, args = msg["params"]["name"], msg["params"].get("arguments", {})
            if name == "echo":
                result = {"content": [{"type": "text", "text": f"回声：{args['text']}"}]}
            elif name == "screenshot":
                result = {"content": [{"type": "text", "text": "截好了"}, {"type": "image", "data": PNG, "mimeType": "image/png"}]}
            elif name == "broken":
                result = {"content": [{"type": "text", "text": "页面打不开"}], "isError": True}
            elif name == "where":
                next_id += 1
                send({"jsonrpc": "2.0", "id": next_id, "method": "roots/list"})
                reply = read()
                result = {"content": [{"type": "text", "text": json.dumps(reply["result"]["roots"])}]}
            else:
                send({"jsonrpc": "2.0", "id": rid, "error": {"code": -32602, "message": f"unknown tool {name}"}})
                continue
            send({"jsonrpc": "2.0", "id": rid, "result": result})
        else:
            send({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "method not found"}})


if __name__ == "__main__":
    main()
