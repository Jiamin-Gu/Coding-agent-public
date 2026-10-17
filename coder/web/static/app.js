// coder 前端：通过 WebSocket 接收 agent 事件并渲染。没有框架，没有构建步骤。
"use strict";

const $ = (id) => document.getElementById(id);
const els = {
  messages: $("messages"), empty: $("empty"), welcome: $("welcome"), input: $("input"),
  send: $("send"), stop: $("stop"), composer: $("composer"), auto: $("auto"), team: $("team"), usage: $("usage"),
  model: $("model"), wsBtn: $("wsBtn"), wsName: $("wsName"), conn: $("conn"), tree: $("tree"),
  viewer: $("viewer"), viewerPath: $("viewerPath"), viewerCode: $("viewerCode"),
  side: $("side"), nav: $("nav"), convList: $("convList"), wsModal: $("wsModal"),
  attachments: $("attachments"), attachBtn: $("attachBtn"), fileInput: $("fileInput"), dropHint: $("dropHint"),
};

let ws = null;
let state = { busy: false, conversation: null, recent_workspaces: [] };
let changed = new Set();
let openFile = null;
let streaming = null; // 正在流式输出的消息 { el, text, reasoning }
let pendingImages = []; // 待发送的图片（data URL）
let serverVersion = null; // 第一次连上时服务的版本

function showBanner(level, html) {
  const b = $("banner");
  b.className = "banner " + level;
  b.innerHTML = html;
  b.hidden = false;
}

let toastTimer = null;
function toast(text) {
  const t = $("toast");
  t.textContent = text;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, 3000);
}
const toolCards = new Map(); // 工具调用 id -> 卡片元素
const collapsedDirs = new Set();

// ---------- 工具函数 ----------

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function el(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html !== undefined) e.innerHTML = html;
  return e;
}

function inline(s) {
  return esc(s)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
}

// 轻量 Markdown：代码块、标题、有序/无序列表、段落、行内代码、加粗、链接。不引入依赖。
function markdown(src) {
  const out = [];
  const lines = String(src).split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (/^```/.test(line)) {
      const buf = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]);
      i++; // 跳过结尾的 ```（流式输出时可能还没到）
      out.push(`<pre><code>${esc(buf.join("\n"))}</code></pre>`);
    } else if (/^#{1,4}\s/.test(line)) {
      const level = line.match(/^#+/)[0].length;
      out.push(`<h${level}>${inline(line.replace(/^#+\s*/, ""))}</h${level}>`);
      i++;
    } else if (/^\s*([-*]|\d+\.)\s/.test(line)) {
      const ordered = /^\s*\d+\./.test(line);
      const items = [];
      while (i < lines.length && /^\s*([-*]|\d+\.)\s/.test(lines[i])) {
        items.push(`<li>${inline(lines[i].replace(/^\s*([-*]|\d+\.)\s/, ""))}</li>`);
        i++;
      }
      out.push(ordered ? `<ol>${items.join("")}</ol>` : `<ul>${items.join("")}</ul>`);
    } else if (!line.trim()) {
      i++;
    } else {
      const buf = [];
      while (i < lines.length && lines[i].trim() && !/^(```|#{1,4}\s|\s*([-*]|\d+\.)\s)/.test(lines[i])) buf.push(lines[i++]);
      out.push(`<p>${buf.map(inline).join("<br>")}</p>`);
    }
  }
  return out.join("");
}

function renderDiff(text) {
  return text.split("\n").map((line) => {
    if (line.startsWith("+++") || line.startsWith("---")) return esc(line);
    if (line.startsWith("+")) return `<span class="add">${esc(line)}</span>`;
    if (line.startsWith("-")) return `<span class="del">${esc(line)}</span>`;
    if (line.startsWith("@@")) return `<span class="hunk">${esc(line)}</span>`;
    return esc(line);
  }).join("\n").replace(/<\/span>\n/g, "</span>").replace(/\n<span/g, "<span"); // 着色行是块元素，自带换行
}

// 工具卡片标题上显示的主要参数
function primaryArg(args) {
  if (args.command) return "$ " + args.command;
  if (args.pattern) return `/${args.pattern}/` + (args.path && args.path !== "." ? "  " + args.path : "");
  if (args.path) return args.path;
  return "";
}

function baseName(p) {
  return String(p).replace(/[\\/]+$/, "").split(/[\\/]/).pop() || p;
}

function timeAgo(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const s = (Date.now() - d.getTime()) / 1000;
  if (s < 60) return "刚刚";
  if (s < 3600) return `${Math.floor(s / 60)} 分钟前`;
  const pad = (n) => String(n).padStart(2, "0");
  if (d.toDateString() === new Date().toDateString()) return `今天 ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  return `${d.getMonth() + 1}-${d.getDate()}`;
}

function scrollDown(force) {
  const m = els.messages;
  if (force || m.scrollHeight - m.scrollTop - m.clientHeight < 240) m.scrollTop = m.scrollHeight;
}

function append(node) {
  els.empty.hidden = true;
  removeThinking();
  els.messages.appendChild(node);
  updateThinking();
  scrollDown();
}

// ---------- “正在工作”提示 ----------

function removeThinking() {
  els.messages.querySelector(".thinking")?.remove();
}

function updateThinking() {
  removeThinking();
  const waiting = els.messages.querySelector(".perm-actions");
  if (state.busy && !waiting && !streaming) {
    els.messages.appendChild(el("div", "thinking", '<span class="dots"><span></span><span></span><span></span></span>agent 正在工作…'));
  }
}

// ---------- 助手消息（流式） ----------

function newAssistantBlock() {
  const node = el("div", "msg-assistant");
  node.innerHTML = `
    <details class="reasoning" hidden><summary>思考过程</summary><div class="reasoning-body"></div></details>
    <div class="msg-text"></div>`;
  return node;
}

function fillAssistant(node, text, reasoning, live) {
  const r = node.querySelector(".reasoning");
  if (reasoning) {
    r.hidden = false;
    r.querySelector(".reasoning-body").textContent = reasoning;
    r.querySelector("summary").textContent = live && !text ? "思考中…" : "思考过程";
  }
  const box = node.querySelector(".msg-text");
  box.innerHTML = markdown(text);
  if (!live) box.querySelectorAll("pre").forEach(addCopyButton);
}

// 代码块右上角的复制按钮：方便把答案贴回 LeetCode 等地方
function addCopyButton(pre) {
  const btn = el("button", "copy-btn", "复制");
  btn.type = "button";
  btn.onclick = async () => {
    const code = pre.querySelector("code")?.textContent ?? pre.textContent;
    try {
      await navigator.clipboard.writeText(code);
    } catch {
      // 剪贴板 API 不可用时的兜底
      const ta = el("textarea");
      ta.value = code;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
    btn.textContent = "已复制";
    btn.classList.add("done");
    setTimeout(() => { btn.textContent = "复制"; btn.classList.remove("done"); }, 1500);
  };
  pre.appendChild(btn);
}

let renderPending = false;
function scheduleStreamRender() {
  if (renderPending) return;
  renderPending = true;
  requestAnimationFrame(() => {
    renderPending = false;
    if (!streaming) return;
    fillAssistant(streaming.el, streaming.text, streaming.reasoning, true);
    const body = streaming.el.querySelector(".reasoning-body");
    body.scrollTop = body.scrollHeight;
    scrollDown();
  });
}

function finishStreaming(text, reasoning) {
  if (!streaming) return false;
  const node = streaming.el;
  node.classList.remove("streaming");
  node.querySelector(".reasoning").open = false;
  fillAssistant(node, text ?? streaming.text, reasoning ?? streaming.reasoning, false);
  if (!(text ?? streaming.text) && !(reasoning ?? streaming.reasoning)) node.remove();
  streaming = null;
  return true;
}

// ---------- 事件处理 ----------

const handlers = {
  state(ev) {
    // 版本检查：没有 version 字段说明连到了旧版本的服务（比如之前启动后没关的）
    if (!ev.version) {
      showBanner("error", "你连接的是旧版本的 coder 服务，功能会不正常。请关闭之前启动的 coder（在它的终端窗口按 Ctrl+C），然后重新运行 <code>python -m coder.web</code>");
      return;
    }
    if (serverVersion && ev.version !== serverVersion) {
      location.reload(); // 服务升级后重启了，刷新页面加载新的前端
      return;
    }
    serverVersion = ev.version;
    if (ev.demo) {
      showBanner("warn", "演示模式：使用按固定剧本执行的假模型，不会调用真实 API。要使用真实模型，请关闭此服务后运行 <code>python -m coder.web</code>");
    } else {
      $("banner").hidden = true;
    }
    const prevRecent = JSON.stringify(state.recent_workspaces);
    const wasWelcome = !state.conversation && !els.welcome.hidden;
    state = { ...ev, conversations: state.conversations };
    const conv = ev.conversation;
    els.model.textContent = ev.model;
    els.model.title = ev.configured ? `接口地址：${ev.base_url}\n点击修改模型设置` : "点击设置模型和 API Key";
    if (!ev.demo && !ev.configured && !settingsPrompted) {
      settingsPrompted = true;
      openSettings();  // 第一次使用还没配置模型：直接打开设置
    }
    els.wsName.textContent = conv ? (conv.scratch ? "临时工作区" : baseName(conv.workspace)) : "选择工作区";
    els.wsBtn.title = conv ? (conv.scratch ? "临时工作区（不在你的项目里，agent 自己测试用）" : conv.workspace)
      + "\n点击切换工作区" : "选择工作区";
    els.auto.checked = ev.auto;
    $("sandboxChip").hidden = !ev.sandbox;
    refreshSandboxCards();
    // 沙箱里的开发服务器：端口转发到本机后显示预览链接
    $("previews").innerHTML = (ev.previews || []).map((p) =>
      `<a class="chip preview-chip" href="${esc(p.url)}" target="_blank" rel="noopener" title="在新标签页打开沙箱里的服务（容器端口 ${p.port}）">预览 :${p.port} ↗</a>`).join("");
    $("undoBtn").disabled = !ev.undo || ev.busy;
    $("undoBtn").title = ev.undo ? `撤销「${ev.undo}」这一轮的文件修改` : "没有可以撤销的文件修改";
    els.team.checked = ev.team;
    const u = ev.usage;
    els.usage.textContent = `${(u.prompt + u.completion).toLocaleString()} tokens`;
    els.usage.title = `本对话：输入 ${u.prompt.toLocaleString()}（缓存命中 ${u.cached.toLocaleString()}）· 输出 ${u.completion.toLocaleString()}`;
    els.send.hidden = ev.busy;
    els.stop.hidden = !ev.busy;
    els.input.disabled = false;
    els.attachBtn.disabled = false;
    els.input.placeholder = !conv ? "直接提问（会用临时工作区），或者先在上面选择工作区"
      : ev.busy ? "任务运行中：可以补充说明，Enter 发送（在当前这一步结束后交给 agent）"
      : "描述你的任务，Enter 发送，Shift+Enter 换行";
    els.welcome.hidden = !!conv;
    els.empty.hidden = !conv || els.messages.querySelector(".msg-user-group") !== null;
    // 只在首次显示或“最近使用”变化时重绘，避免冲掉正在输入的路径
    if (!conv && (!wasWelcome || prevRecent !== JSON.stringify(ev.recent_workspaces))) renderPicker($("welcomePicker"));
    document.title = conv ? `${conv.title} · coder` : "coder";
    setChanged(ev.changed);
    renderConversations();
    updateThinking();
  },

  conversations(ev) {
    state.conversations = ev.items;
    renderConversations();
  },

  user(ev) {
    const group = el("div", "msg-user-group" + (ev.interject ? " interject" : ""));
    if (ev.interject) group.appendChild(el("div", "interject-tag", "运行中补充"));
    if (ev.images?.length) {
      const imgs = el("div", "msg-images");
      for (const id of ev.images) {
        const img = el("img");
        img.src = "/api/image/" + encodeURIComponent(id);
        img.alt = "图片";
        img.onclick = () => openLightbox(img.src);
        imgs.appendChild(img);
      }
      group.appendChild(imgs);
    }
    if (ev.text) group.appendChild(el("div", "msg-user", esc(ev.text)));
    append(group);
    scrollDown(true);
  },

  delta(ev) {
    if (!streaming) {
      const node = newAssistantBlock();
      node.classList.add("streaming");
      streaming = { el: node, text: "", reasoning: "" };
      append(node);
      node.querySelector(".reasoning").open = true; // 思考时展开，结束后收起
    }
    streaming[ev.kind === "reasoning" ? "reasoning" : "text"] += ev.text;
    scheduleStreamRender();
  },

  assistant(ev) {
    if (finishStreaming(ev.text, ev.reasoning)) return;
    const node = newAssistantBlock();
    fillAssistant(node, ev.text, ev.reasoning, false);
    append(node);
  },

  tool_call(ev) {
    finishStreaming();
    const card = el("div", "tool");
    card.innerHTML = `
      <div class="tool-head">
        <span class="status running"></span>
        ${ev.agent ? `<span class="tool-agent" title="子 agent">${esc(ev.agent)}</span>` : ""}
        <span class="tool-name">${esc(ev.name)}</span>
        <span class="tool-arg">${esc(primaryArg(ev.args))}</span>
        <span class="chev">▶</span>
      </div>
      <div class="tool-body">
        <div class="tool-section"><div class="label">参数</div><pre class="pre">${esc(JSON.stringify(ev.args, null, 2))}</pre></div>
      </div>`;
    card.querySelector(".tool-head").onclick = () => card.classList.toggle("open");
    toolCards.set(ev.id, card);
    append(card);
  },

  tool_result(ev) {
    const card = toolCards.get(ev.id);
    if (!card) return;
    card.querySelector(".status").className = "status " + (ev.is_error ? "err" : "ok");
    const sec = el("div", "tool-section", `<div class="label">结果</div><pre class="pre ${ev.is_error ? "err" : ""}"></pre>`);
    sec.querySelector("pre").textContent = ev.result;
    card.querySelector(".tool-body").appendChild(sec);
    if (ev.is_error) card.classList.add("open"); // 出错时自动展开，方便看原因
  },

  permission_request(ev) {
    const card = toolCards.get(ev.call_id);
    if (!card) return;
    card.classList.add("open");
    card.querySelector(".status").className = "status wait";
    const sec = el("div", "tool-section perm");
    sec.dataset.req = ev.id;
    sec.innerHTML = `
      <div class="perm-title">需要你确认：${esc(ev.tool)}${ev.network ? "（这个命令要联网）" : ""}</div>
      <pre class="pre diff">${renderDiff(ev.preview)}</pre>
      <div class="perm-actions"></div>`;
    const actions = sec.querySelector(".perm-actions");
    const showButtons = () => {
      if (ev.network) {  // 沙箱里的命令申请联网：自动模式和白名单都不算数，必须亲自确认
        actions.innerHTML = `
        <button class="btn ok" data-c="y">允许这一次联网</button>
        <button class="btn" data-c="a">本对话允许命令联网</button>
        <button class="btn" data-c="n">拒绝…</button>`;
        return;
      }
      actions.innerHTML = `
        <button class="btn ok" data-c="y">允许</button>
        <button class="btn" data-c="a">本对话总是允许 ${esc(ev.tool)}</button>
        ${ev.prefix ? `<button class="btn" data-c="p" title="保存在项目的 .coder/permissions.json">以后总是允许「${esc(ev.prefix)}」开头的命令</button>` : ""}
        <button class="btn" data-c="n">拒绝…</button>`;
    };
    showButtons();
    actions.onclick = (e) => {
      const c = e.target.dataset.c;
      if (!c) return;
      if (c === "n") {
        // 拒绝时可以附上理由，理由会回传给模型
        actions.innerHTML = `
          <input placeholder="告诉 agent 原因或改进建议（可留空）">
          <button class="btn danger" data-c="n!">确认拒绝</button>
          <button class="btn ghost" data-c="back">返回</button>`;
        const input = actions.querySelector("input");
        input.focus();
        input.onkeydown = (k) => { if (k.key === "Enter" && !k.isComposing) send({ type: "permission_response", id: ev.id, choice: "n", feedback: input.value }); };
        return;
      }
      if (c === "back") return showButtons();
      const feedback = c === "n!" ? actions.querySelector("input").value : "";
      send({ type: "permission_response", id: ev.id, choice: c === "n!" ? "n" : c, feedback });
    };
    card.querySelector(".tool-body").appendChild(sec);
    removeThinking();
    scrollDown(true);
  },

  permission_resolved(ev) {
    const sec = document.querySelector(`.perm[data-req="${ev.id}"]`);
    if (!sec) return;
    const label = { y: "✓ 已允许", a: "✓ 已允许（本对话不再询问）", p: "✓ 已允许（已添加命令前缀规则）", n: "✕ 已拒绝" }[ev.choice] || ev.choice;
    sec.querySelector(".perm-actions").outerHTML = `<div class="perm-done">${label}</div>`;
    sec.querySelector(".perm-title").remove();
    sec.classList.remove("perm");
    const card = sec.closest(".tool");
    if (ev.choice !== "n") {
      card.querySelector(".status").className = "status running";
      card.classList.remove("open");
    }
    updateThinking();
  },

  notice(ev) {
    finishStreaming();
    append(el("div", "notice " + ev.level, esc(ev.text)));
  },

  // 沙箱模式：一轮结束，列出副本里的改动，用户决定应用到真实项目还是放弃
  sandbox_changes(ev) {
    finishStreaming();
    const card = el("div", "sbx-card");
    const ch = ev.changes || {};
    const rows = [["added", "+", "新增"], ["modified", "~", "修改"], ["deleted", "−", "删除"]]
      .flatMap(([k, mark, label]) => (ch[k] || []).map((f) => `<li class="sbx-${k}" title="${label}">${mark} ${esc(f)}</li>`));
    card.innerHTML = `<div class="sbx-title">🧪 沙箱里的改动还没应用到项目</div>
      <div class="sbx-summary">${esc(ev.summary.split("：")[0])}</div>
      <ul class="sbx-files">${rows.slice(0, 30).join("")}${rows.length > 30 ? `<li>……共 ${rows.length} 个文件</li>` : ""}</ul>
      <div class="sbx-actions"><button class="btn ok" data-a="sandbox_apply">应用到项目</button>
        <button class="btn" data-a="sandbox_discard">放弃</button></div>`;
    card.querySelector(".sbx-actions").onclick = (e) => {
      const a = e.target.dataset.a;
      if (!a) return;
      if (a === "sandbox_discard" && !confirm("放弃沙箱里的这些改动？副本会恢复成项目现在的样子，改动不能找回。")) return;
      send({ type: a });
    };
    append(card);
    refreshSandboxCards();
    scrollDown(true);
  },

  undo_conflict(ev) {
    if (confirm(ev.text.replace("确定要撤销请用强制撤销", "仍然撤销（覆盖这些修改）？"))) send({ type: "undo", force: true });
  },

  files_changed(ev) {
    setChanged(ev.changed);
    loadTree(true);
    if (openFile) viewFile(openFile);
  },

  done() {
    finishStreaming();
    removeThinking();
  },

  reset() {
    streaming = null;
    els.messages.querySelectorAll(":scope > :not(#empty):not(#welcome)").forEach((n) => n.remove());
    toolCards.clear();
    closeViewer();
    els.wsModal.hidden = true;
    loadTree();
  },
};

// ---------- 对话列表 ----------

// 只有最后一张改动卡片、而且确实还有待应用的改动时，按钮才能点；其余的显示"已处理"
function refreshSandboxCards() {
  const cards = [...document.querySelectorAll(".sbx-card")];
  cards.forEach((card, i) => {
    const live = i === cards.length - 1 && state.sandbox_changes && !state.busy;
    card.classList.toggle("done", !live);
    const actions = card.querySelector(".sbx-actions");
    actions.hidden = !live;
    if (live) card.querySelector(".sbx-summary").textContent = state.sandbox_changes.summary.split("：")[0];
    else if (!card.querySelector(".sbx-done")) card.appendChild(el("div", "sbx-done", "已处理（应用或放弃过了，或者之后又有了新的改动）"));
    if (live) card.querySelector(".sbx-done")?.remove();
  });
}

function renderConversations() {
  const items = state.conversations || [];
  const activeId = state.conversation?.id;
  els.convList.innerHTML = "";
  if (!items.length) {
    els.convList.appendChild(el("div", "conv-empty", "还没有对话"));
    return;
  }
  for (const c of items) {
    const row = el("div", "conv" + (c.id === activeId ? " active" : ""));
    row.innerHTML = `
      <div class="conv-main">
        <div class="conv-title"></div>
        <div class="conv-meta"></div>
      </div>
      <button class="icon-btn del" title="删除对话">✕</button>`;
    row.querySelector(".conv-title").textContent = c.title;
    row.querySelector(".conv-meta").textContent = `${c.scratch ? "临时对话" : baseName(c.workspace)} · ${timeAgo(c.updated)}`;
    row.title = c.workspace;
    row.onclick = () => {
      els.nav.classList.remove("show");
      if (c.id !== activeId) send({ type: "open_conversation", id: c.id });
    };
    row.querySelector(".del").onclick = (e) => {
      e.stopPropagation();
      const tip = c.scratch ? "\n临时对话：它的临时工作区也会一起删除。" : "\n只删除对话记录，不会删除工作区里的文件。";
      if (confirm(`删除对话“${c.title}”？${tip}`)) send({ type: "delete_conversation", id: c.id });
    };
    els.convList.appendChild(row);
  }
}

// ---------- 工作区选择 ----------

function renderPicker(container) {
  container.innerHTML = `
    <div class="picker-row">
      <input placeholder="输入文件夹路径，例如 D:\\my-project" spellcheck="false">
      <button class="btn" data-act="browse">浏览…</button>
      <button class="btn primary" data-act="open">打开</button>
    </div>
    <div class="picker-error"></div>
    <div class="recent-wrap"></div>
    <button class="btn ghost scratch-btn" data-act="scratch">不用工作区，直接提问（临时对话）</button>`;
  const input = container.querySelector("input");
  const error = container.querySelector(".picker-error");
  const open = (path) => {
    path = (path || input.value).trim();
    if (!path) { error.textContent = "请输入路径，或点“浏览…”选择文件夹"; return; }
    error.textContent = "";
    send({ type: "new_conversation", workspace: path });
  };
  input.onkeydown = (e) => { if (e.key === "Enter" && !e.isComposing) open(); };
  container.querySelector('[data-act="scratch"]').onclick = () => send({ type: "new_conversation", scratch: true });
  container.querySelector('[data-act="open"]').onclick = () => open();
  container.querySelector('[data-act="browse"]').onclick = async (e) => {
    const btn = e.target;
    btn.disabled = true;
    btn.textContent = "请在弹出的窗口中选择…";
    try {
      const res = await (await fetch("/api/pick-folder", { method: "POST" })).json();
      if (res.error) error.textContent = res.error;
      if (res.path) { input.value = res.path; open(res.path); }
    } finally {
      btn.disabled = false;
      btn.textContent = "浏览…";
    }
  };
  const recent = state.recent_workspaces || [];
  if (recent.length) {
    const wrap = container.querySelector(".recent-wrap");
    wrap.innerHTML = '<div class="recent-label">最近使用</div><div class="recent"></div>';
    for (const p of recent) {
      const b = el("button");
      b.textContent = p;
      b.title = p;
      b.onclick = () => open(p);
      wrap.querySelector(".recent").appendChild(b);
    }
  }
  input.focus();
}

function openWorkspaceModal() {
  if (state.busy) return handlers.notice({ level: "error", text: "任务运行中，请先停止再切换工作区" });
  els.wsModal.hidden = false;
  renderPicker($("modalPicker"));
  const cur = state.conversation?.workspace;
  if (cur) $("modalPicker").querySelector("input").value = cur;
}

els.wsBtn.onclick = openWorkspaceModal;
$("wsModalClose").onclick = () => { els.wsModal.hidden = true; };
els.wsModal.onclick = (e) => { if (e.target === els.wsModal) els.wsModal.hidden = true; };
document.addEventListener("keydown", (e) => { if (e.key === "Escape") { els.wsModal.hidden = true; closeSettings(); } });

// ---------- 模型设置：选服务商、填密钥、选模型。保存到 .env，立即生效

let settings = null;          // /api/settings 的结果
let settingsPrompted = false; // 没配置模型时只自动弹出一次

async function openSettings() {
  if (state.busy) return toast("任务运行中，请先停止再修改设置");
  settings = await (await fetch("/api/settings")).json();
  const cur = settings.current;
  $("sProvider").innerHTML = settings.providers.map((p) => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join("");
  $("sProvider").value = cur.provider;
  fillProvider(false);
  $("sBaseUrl").value = cur.base_url;
  $("sModel").value = cur.model;
  $("sKey").value = "";
  $("sKey").placeholder = cur.has_key ? "已设置（留空则保持不变）" : "粘贴你的 API Key";
  $("sFile").textContent = `保存在 ${settings.file}（只存在你的电脑上，不会发给浏览器或提交到 Git）`;
  $("sError").textContent = "";
  renderRules(settings.rules, settings.workspace);
  $("sSandbox").checked = settings.sandbox.enabled;
  const states = { connected: "已连接", disabled: "已禁用", error: "启动失败" };
  $("sMcp").innerHTML = settings.mcp.length
    ? settings.mcp.map((s) => `<li title="${esc(s.error || s.tools.join(", "))}"><code>${esc(s.name)}</code>
        <span class="mcp-${s.state}">${states[s.state] || s.state}${s.state === "connected" ? ` · ${s.tools.length} 个工具` : ""}</span></li>`).join("")
    : `<li class="empty">（没有配置）</li>`;
  $("sSandboxStatus").textContent = settings.sandbox.status;
  $("settingsModal").hidden = false;
}

function renderRules(rules, workspace) {
  $("sRulesBox").hidden = !workspace;
  $("sRules").innerHTML = rules.length
    ? rules.map((r) => `<li><code>${esc(r)}</code><button type="button" class="icon-btn" data-rule="${esc(r)}" title="删除这条规则">✕</button></li>`).join("")
    : `<li class="empty">（还没有）</li>`;
}

$("sSandbox").onchange = async (e) => {
  const enabled = e.target.checked;
  const res = await fetch("/api/sandbox", { method: "POST", headers: { "Content-Type": "application/json" },
                                            body: JSON.stringify({ enabled }) });
  const data = await res.json();
  if (!res.ok) {
    e.target.checked = !enabled;
    $("sSandboxStatus").textContent = data.detail || "切换失败";
    return;
  }
  toast(enabled ? "已开启沙箱模式：之后的命令在 Docker 容器里执行" : "已关闭沙箱模式：命令在本机执行");
};

$("sRules").onclick = async (e) => {
  const prefix = e.target.dataset.rule;
  if (!prefix) return;
  const res = await fetch("/api/rules/remove", { method: "POST", headers: { "Content-Type": "application/json" },
                                                 body: JSON.stringify({ prefix }) });
  const data = await res.json();
  if (res.ok) renderRules(data.rules, settings.workspace);
};

function fillProvider(reset) {
  // 切换服务商：预设的接口地址自动填好（不能改），模型给出常用选项；自定义服务商自己填地址
  const p = settings.providers.find((x) => x.id === $("sProvider").value);
  $("sProviderNote").textContent = p.note;
  $("sBaseUrl").readOnly = !!p.base_url;
  if (reset) {
    $("sBaseUrl").value = p.base_url;
    $("sModel").value = p.models[0] || "";
  }
  $("sModels").innerHTML = p.models.map((m) => `<option value="${esc(m)}">`).join("");
}

function closeSettings() { $("settingsModal").hidden = true; }

$("settingsBtn").onclick = openSettings;
els.model.onclick = openSettings;
$("sProvider").onchange = () => fillProvider(true);
$("settingsClose").onclick = closeSettings;
$("settingsCancel").onclick = closeSettings;
$("settingsModal").onclick = (e) => { if (e.target.id === "settingsModal") closeSettings(); };
$("settingsForm").onsubmit = async (e) => {
  e.preventDefault();
  const body = { provider: $("sProvider").value, base_url: $("sBaseUrl").value.trim(),
                 model: $("sModel").value.trim(), api_key: $("sKey").value.trim() };
  const res = await fetch("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" },
                                             body: JSON.stringify(body) });
  const data = await res.json();
  if (!res.ok) { $("sError").textContent = data.detail?.[0]?.msg || data.detail || "保存失败"; return; }
  closeSettings();
  toast(data.note || `已保存，之后的请求使用 ${body.model}`);
};

$("newChat").onclick = () => {
  els.nav.classList.remove("show");
  if (!state.conversation) {
    toast("先选择一个工作区");
    return;
  }
  if (state.busy) return toast("任务运行中，请先停止再新建对话");
  // 当前对话还没发过消息，本身就是新对话：给出提示，而不是看起来毫无反应
  if (!els.messages.querySelector(".msg-user-group")) {
    toast("当前已经是新对话，直接输入任务即可。要换文件夹，点顶部的 📁");
    els.input.focus();
    return;
  }
  send({ type: "new_conversation" }); // 沿用当前工作区
};

// ---------- WebSocket ----------

function connect() {
  ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  ws.onopen = () => {
    els.conn.classList.add("on");
    els.conn.title = "已连接";
  };
  ws.onmessage = (m) => {
    const ev = JSON.parse(m.data);
    (handlers[ev.type] || (() => {}))(ev);
  };
  ws.onclose = () => {
    els.conn.classList.remove("on");
    els.conn.title = "连接已断开，正在重连…";
    setTimeout(connect, 1500);
  };
}

function send(msg) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
}

// ---------- 图片 ----------

const MAX_IMAGES = 4;
const MAX_SIDE = 2000; // 长边超过这个尺寸就缩小，省 token 也省带宽

function openLightbox(src) {
  const box = el("div", "lightbox");
  const img = el("img");
  img.src = src;
  box.appendChild(img);
  box.onclick = () => box.remove();
  document.body.appendChild(box);
}

function readAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("无法读取图片"));
    img.src = src;
  });
}

// 统一转成 PNG/JPEG，必要时缩小。截图多是文字，优先用 PNG 保证清晰，太大再用 JPEG。
async function prepareImage(file) {
  const url = await readAsDataURL(file);
  const img = await loadImage(url);
  const scale = Math.min(1, MAX_SIDE / Math.max(img.width, img.height));
  if (scale === 1 && /^image\/(png|jpeg)$/.test(file.type) && file.size < 1.5e6) return url;
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(img.width * scale);
  canvas.height = Math.round(img.height * scale);
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#fff"; // 透明背景转 JPEG 会变黑，先铺白底
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  const png = canvas.toDataURL("image/png");
  return png.length < 2.5e6 ? png : canvas.toDataURL("image/jpeg", 0.9);
}

async function addImages(files) {
  const images = [...files].filter((f) => f.type.startsWith("image/"));
  for (const f of images) {
    if (pendingImages.length >= MAX_IMAGES) {
      handlers.notice({ level: "warn", text: `一次最多发送 ${MAX_IMAGES} 张图片` });
      break;
    }
    try {
      pendingImages.push(await prepareImage(f));
    } catch (e) {
      handlers.notice({ level: "error", text: `${f.name || "图片"}：${e.message}` });
    }
  }
  renderAttachments();
  els.input.focus();
}

function renderAttachments() {
  els.attachments.innerHTML = "";
  els.attachments.hidden = !pendingImages.length;
  pendingImages.forEach((src, i) => {
    const item = el("div", "thumb-item");
    item.innerHTML = '<img alt="待发送的图片"><button type="button" class="rm" title="移除">✕</button>';
    item.querySelector("img").src = src;
    item.querySelector("img").onclick = () => openLightbox(src);
    item.querySelector(".rm").onclick = () => { pendingImages.splice(i, 1); renderAttachments(); };
    els.attachments.appendChild(item);
  });
  if (pendingImages.length) els.attachments.appendChild(el("span", "attach-note", "图片会和文字一起发给模型"));
}

els.attachBtn.onclick = () => els.fileInput.click();
els.fileInput.onchange = () => { addImages(els.fileInput.files); els.fileInput.value = ""; };

// Ctrl+V 粘贴截图：只拦截图片，粘贴文字照常
document.addEventListener("paste", (e) => {
  const files = [...(e.clipboardData?.files || [])].filter((f) => f.type.startsWith("image/"));
  if (!files.length) return;
  e.preventDefault();
  addImages(files);
});

// 拖进窗口
let dragDepth = 0;
const chatEl = document.querySelector(".chat");
const hasFiles = (e) => [...(e.dataTransfer?.types || [])].includes("Files");
chatEl.addEventListener("dragenter", (e) => { if (!hasFiles(e)) return; dragDepth++; els.dropHint.hidden = false; });
chatEl.addEventListener("dragleave", () => { if (--dragDepth <= 0) { dragDepth = 0; els.dropHint.hidden = true; } });
chatEl.addEventListener("dragover", (e) => { if (hasFiles(e)) e.preventDefault(); });
chatEl.addEventListener("drop", (e) => {
  if (!hasFiles(e)) return;
  e.preventDefault();
  dragDepth = 0;
  els.dropHint.hidden = true;
  addImages(e.dataTransfer.files);
});

// ---------- 输入 ----------

function submit() {
  const text = els.input.value.trim();
  if (!text && !pendingImages.length) return;  // 没选工作区也能发：服务端会用临时工作区
  if (state.busy && pendingImages.length) return toast("运行中补充的话只能是文字，图片请等任务结束后再发");
  send({ type: "user_message", text, images: pendingImages });
  els.input.value = "";
  pendingImages = [];
  renderAttachments();
  autosize();
}

function autosize() {
  els.input.style.height = "auto";
  els.input.style.height = Math.min(els.input.scrollHeight, 200) + "px";
}

els.composer.onsubmit = (e) => { e.preventDefault(); submit(); };
els.input.oninput = autosize;
els.input.onkeydown = (e) => {
  // isComposing：中文输入法选词时按 Enter 不应该发送
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); submit(); }
};
els.stop.onclick = () => send({ type: "cancel" });
$("undoBtn").onclick = () => {
  if (!state.undo) return;
  if (confirm(`撤销「${state.undo}」这一轮 agent 对文件的修改？\n\n改过的文件恢复原样，新建的文件删除。命令（run_command）产生的效果无法撤销。`))
    send({ type: "undo" });
};
els.auto.onchange = () => send({ type: "set_auto", value: els.auto.checked });
els.team.onchange = () => send({ type: "set_team", value: els.team.checked });
document.querySelectorAll(".example").forEach((b) => {
  b.onclick = () => { els.input.value = b.dataset.text || b.textContent; autosize(); els.input.focus(); };
});

// ---------- 文件树 ----------

function setChanged(list) {
  changed = new Set(list || []);
  els.tree.querySelectorAll(".node[data-path]").forEach((n) => n.classList.toggle("changed", changed.has(n.dataset.path)));
}

function buildTree(paths) {
  const root = { dirs: {}, files: [] };
  for (const p of paths) {
    const parts = p.split("/");
    let node = root;
    for (const d of parts.slice(0, -1)) node = node.dirs[d] ||= { dirs: {}, files: [] };
    node.files.push(p);
  }
  return root;
}

let knownFiles = new Set();

async function loadTree(flashNew = false) {
  let data;
  try {
    data = await (await fetch("/api/files")).json();
  } catch { return; }
  const before = knownFiles;
  knownFiles = new Set(data.files);
  els.tree.innerHTML = "";
  if (!data.files.length) {
    els.tree.appendChild(el("div", "tree-empty", state.conversation ? "工作区是空的" : "还没有选择工作区"));
    return;
  }
  const render = (node, prefix, depth) => {
    for (const name of Object.keys(node.dirs).sort()) {
      const full = prefix + name;
      const row = el("div", "node", `<span class="ic">${collapsedDirs.has(full) ? "▶" : "▼"}</span><span class="nm">${esc(name)}/</span>`);
      row.style.paddingLeft = 12 + depth * 14 + "px";
      row.onclick = () => { collapsedDirs.has(full) ? collapsedDirs.delete(full) : collapsedDirs.add(full); loadTree(); };
      els.tree.appendChild(row);
      if (!collapsedDirs.has(full)) render(node.dirs[name], full + "/", depth + 1);
    }
    for (const path of node.files) {
      const row = el("div", "node", `<span class="ic"></span><span class="nm">${esc(path.split("/").pop())}</span>`);
      row.dataset.path = path;
      row.style.paddingLeft = 12 + depth * 14 + "px";
      if (changed.has(path)) row.classList.add("changed");
      if (path === openFile) row.classList.add("active");
      if (flashNew && (!before.has(path) || changed.has(path))) row.classList.add("flash");
      row.onclick = () => viewFile(path);
      els.tree.appendChild(row);
    }
  };
  render(buildTree(data.files), "", 0);
  if (data.truncated) els.tree.appendChild(el("div", "tree-empty", "文件太多，只显示了一部分"));
}

async function viewFile(path) {
  const res = await fetch("/api/file?path=" + encodeURIComponent(path));
  if (!res.ok) { if (path === openFile) closeViewer(); return; }
  const data = await res.json();
  openFile = path;
  els.viewer.hidden = false;
  els.viewerPath.textContent = path;
  els.viewerCode.innerHTML = data.content === null
    ? `<span class="ln"></span>${esc(data.note)}`
    : data.content.split("\n").map((l, i) => `<span class="ln">${i + 1}</span>${esc(l)}`).join("\n");
  els.tree.querySelectorAll(".node").forEach((n) => n.classList.toggle("active", n.dataset.path === path));
}

function closeViewer() {
  openFile = null;
  els.viewer.hidden = true;
  els.tree.querySelectorAll(".node.active").forEach((n) => n.classList.remove("active"));
}

$("closeViewer").onclick = closeViewer;
$("refreshFiles").onclick = () => loadTree();
$("filesToggle").onclick = () => els.side.classList.toggle("show");
$("navToggle").onclick = () => els.nav.classList.toggle("show");

connect();
