"""沙箱端口预览：agent 在沙箱里启动的开发服务器，用户能在自己的浏览器里打开。

沙箱默认断网（容器没有接入任何网络），Docker 的端口映射用不了。这里的做法和 kubectl port-forward 一样：
本机监听一个端口，每来一个连接，就用 `docker exec -i` 在容器里启动一个小转发程序连到容器内的端口，
两边的数据通过 docker exec 的标准输入输出来回传。容器始终不接入网络，本机端口只监听 127.0.0.1。

容器里新出现的监听端口（读 /proc/net/tcp）会被自动发现并转发，见 ProcessManager 里的调用。
"""
import socket
import subprocess
import threading

# 在容器里运行：连到容器内的端口，标准输入 → 端口，端口 → 标准输出
RELAY = r"""
import os, socket, sys, threading
s = socket.create_connection(("127.0.0.1", int(sys.argv[1])))
def up():
    while True:
        d = os.read(0, 65536)
        if not d:
            try: s.shutdown(socket.SHUT_WR)
            except OSError: pass
            return
        s.sendall(d)
threading.Thread(target=up, daemon=True).start()
while True:
    d = s.recv(65536)
    if not d:
        break
    os.write(1, d)
"""

# 列出容器里正在监听的 TCP 端口（/proc/net/tcp 里状态 0A 是 LISTEN；不依赖 ss / netstat）
LIST_PORTS = r"""
import sys
ports = set()
for name in ("/proc/net/tcp", "/proc/net/tcp6"):
    try:
        lines = open(name).read().splitlines()[1:]
    except OSError:
        continue
    for line in lines:
        parts = line.split()
        if len(parts) > 3 and parts[3] == "0A":
            ports.add(int(parts[1].rsplit(":", 1)[1], 16))
print(" ".join(map(str, sorted(ports))))
"""

CONTAINER_PYTHON = "/usr/local/bin/python3"  # 镜像自带的 Python（评测时 PATH 可能指向别的虚拟环境）


def _pipe(src, dst, close) -> None:
    try:
        while True:
            data = src(65536)
            if not data:
                break
            dst(data)
    except OSError:
        pass
    finally:
        close()


class PortForwarder:
    """把沙箱容器里的端口转发到本机 127.0.0.1。"""

    def __init__(self, sandbox):
        self.sandbox = sandbox
        self.forwards: dict[int, dict] = {}  # 容器端口 -> {host_port, server}
        self.lock = threading.Lock()
        self.on_change = None  # 转发列表变化时调用（网页界面显示预览链接）

    def listening_ports(self) -> set[int]:
        if not self.sandbox.started:
            return set()
        r = self.sandbox._docker("exec", self.sandbox.name, CONTAINER_PYTHON, "-c", LIST_PORTS, check=False)
        return {int(p) for p in r.stdout.split() if p.isdigit()} if r.returncode == 0 else set()

    def forward(self, port: int) -> int:
        """开始转发容器的 port，返回本机端口（尽量用同一个端口号，被占用就随机分配）。"""
        with self.lock:
            if port in self.forwards:
                return self.forwards[port]["host_port"]
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                server.bind(("127.0.0.1", port))
            except OSError:
                server.bind(("127.0.0.1", 0))
            server.listen(16)
            host_port = server.getsockname()[1]
            self.forwards[port] = {"host_port": host_port, "server": server}
            threading.Thread(target=self._accept, args=(server, port), daemon=True).start()
        self._changed()
        return host_port

    def _accept(self, server: socket.socket, port: int) -> None:
        while True:
            try:
                conn, _ = server.accept()
            except OSError:
                return  # 停止转发时关闭了监听
            threading.Thread(target=self._serve, args=(conn, port), daemon=True).start()

    def _serve(self, conn: socket.socket, port: int) -> None:
        sb = self.sandbox
        proc = subprocess.Popen([sb.docker, "exec", "-i", sb.name, CONTAINER_PYTHON, "-c", RELAY, str(port)],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                **({"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}))

        def close_up():
            try:
                proc.stdin.close()
            except OSError:
                pass

        def write_up(data):
            proc.stdin.write(data)
            proc.stdin.flush()

        up = threading.Thread(target=_pipe, args=(conn.recv, write_up, close_up), daemon=True)
        up.start()
        _pipe(proc.stdout.read1, conn.sendall, lambda: None)
        try:
            conn.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        conn.close()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()

    def sync(self) -> list[str]:
        """把容器里新出现的监听端口转发出来，已经关闭的端口停止转发。返回变化的说明（给模型和界面看）。"""
        listening = self.listening_ports()
        notes = []
        for port in sorted(listening - set(self.forwards)):
            host_port = self.forward(port)
            notes.append(f"容器端口 {port} → 预览地址 http://127.0.0.1:{host_port}（用户可以在自己的浏览器里打开）")
        for port in sorted(set(self.forwards) - listening):
            self.stop(port)
            notes.append(f"容器端口 {port} 已经不再监听，停止转发")
        return notes

    def items(self) -> list[dict]:
        with self.lock:
            return [{"port": p, "url": f"http://127.0.0.1:{f['host_port']}"} for p, f in sorted(self.forwards.items())]

    def stop(self, port: int) -> None:
        with self.lock:
            f = self.forwards.pop(port, None)
        if f:
            f["server"].close()
            self._changed()

    def stop_all(self) -> None:
        for port in list(self.forwards):
            self.stop(port)

    def _changed(self) -> None:
        if self.on_change:
            try:
                self.on_change(self.items())
            except Exception:
                pass
