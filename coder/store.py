"""本地持久化：对话历史、图片和最近使用的工作区，保存在 ~/.coder/（可用 CODER_HOME 修改）。"""
import base64
import binascii
import hashlib
import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path

MAX_RECENT = 8
MAX_IMAGE_BYTES = 8_000_000
# 只接受 PNG / JPEG：前端会把其他格式统一转换，这两种格式模型都支持
IMAGE_DATA_URL = re.compile(r"^data:image/(png|jpeg);base64,([A-Za-z0-9+/=\s]+)$")
IMAGE_ID = re.compile(r"^[0-9a-f]{16}\.(png|jpeg)$")
IMAGE_REF = "coder-image:"  # 对话文件里用引用代替 base64，避免文件被撑大


def new_id() -> str:
    # 时间在前，按文件名排序就是时间顺序
    return datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Store:
    def __init__(self, home: str | Path | None = None):
        self.home = Path(home or os.getenv("CODER_HOME") or Path.home() / ".coder")
        self.conv_dir = self.home / "conversations"
        self.conv_dir.mkdir(parents=True, exist_ok=True)
        self.image_dir = self.home / "images"
        self.image_dir.mkdir(exist_ok=True)
        self.settings_path = self.home / "settings.json"

    # ---------- 对话 ----------

    def _path(self, conv_id: str) -> Path:
        # id 只允许字母数字和横线，防止路径注入
        if not conv_id or not all(c.isalnum() or c == "-" for c in conv_id):
            raise ValueError(f"非法的对话 id：{conv_id}")
        return self.conv_dir / f"{conv_id}.json"

    def save(self, data: dict) -> None:
        path = self._path(data["id"])
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)  # 先写临时文件再替换，避免写一半崩溃导致文件损坏

    def load(self, conv_id: str) -> dict | None:
        try:
            return json.loads(self._path(conv_id).read_text(encoding="utf-8"))
        except (ValueError, OSError):  # 非法 id、文件不存在或损坏
            return None

    def delete(self, conv_id: str) -> None:
        try:
            self._path(conv_id).unlink(missing_ok=True)
        except ValueError:
            pass

    def list_conversations(self) -> list[dict]:
        """所有对话的摘要，最近更新的在前。"""
        items = []
        for p in self.conv_dir.glob("*.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            items.append({k: d.get(k) for k in ("id", "title", "workspace", "updated", "scratch")})
        return sorted(items, key=lambda d: d["updated"] or "", reverse=True)

    # ---------- 图片 ----------

    def save_image(self, data_url: str) -> str:
        """保存 data URL 格式的图片，返回图片 id。同一张图片只存一份（按内容哈希命名）。"""
        m = IMAGE_DATA_URL.match(data_url or "")
        if not m:
            raise ValueError("只支持 PNG 或 JPEG 图片")
        try:
            raw = base64.b64decode(m.group(2), validate=False)
        except binascii.Error:
            raise ValueError("图片数据损坏")
        if len(raw) > MAX_IMAGE_BYTES:
            raise ValueError(f"图片太大（超过 {MAX_IMAGE_BYTES // 1_000_000} MB）")
        image_id = hashlib.sha256(raw).hexdigest()[:16] + "." + m.group(1)
        path = self.image_dir / image_id
        if not path.exists():
            path.write_bytes(raw)
        return image_id

    def image_path(self, image_id: str) -> Path | None:
        if not IMAGE_ID.match(image_id or ""):
            return None
        path = self.image_dir / image_id
        return path if path.is_file() else None

    def image_data_url(self, image_id: str) -> str | None:
        path = self.image_path(image_id)
        if not path:
            return None
        mime = "image/" + image_id.rsplit(".", 1)[1]
        return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()

    def pack_messages(self, messages: list[dict]) -> list[dict]:
        """保存前：把消息里的图片 data URL 换成引用。"""
        return [self._map_images(m, lambda url: IMAGE_REF + self.save_image(url)
                                 if url.startswith("data:") else url) for m in messages]

    def unpack_messages(self, messages: list[dict]) -> list[dict]:
        """加载后：把图片引用还原成 data URL。图片文件丢失时换成一段文字说明。"""
        def restore(url):
            if url.startswith(IMAGE_REF):
                return self.image_data_url(url[len(IMAGE_REF):])
            return url
        return [self._map_images(m, restore) for m in messages]

    @staticmethod
    def _map_images(message: dict, fn) -> dict:
        content = message.get("content")
        if not isinstance(content, list):
            return message
        parts = []
        for part in content:
            if part.get("type") == "image_url":
                url = fn(part["image_url"]["url"])
                part = ({"type": "image_url", "image_url": {"url": url}} if url
                        else {"type": "text", "text": "[图片已丢失]"})
            parts.append(part)
        return {**message, "content": parts}

    # ---------- 设置 ----------

    def _settings(self) -> dict:
        try:
            return json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def recent_workspaces(self) -> list[str]:
        return [p for p in self._settings().get("recent_workspaces", []) if Path(p).is_dir()]

    def add_recent_workspace(self, path: str) -> None:
        s = self._settings()
        recent = [p for p in s.get("recent_workspaces", []) if p != path]
        s["recent_workspaces"] = [path] + recent[:MAX_RECENT - 1]
        self.settings_path.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
