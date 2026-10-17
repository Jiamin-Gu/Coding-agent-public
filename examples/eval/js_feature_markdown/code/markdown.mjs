// 评论区的 Markdown 渲染器，规则见 docs/SPEC.md

const ESCAPES = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

// 所有来自用户的文字都要做 HTML 转义。
function escapeHtml(text) {
  return text.replace(/[&<>"']/g, (ch) => ESCAPES[ch]);
}

// 在同一段（已转义的）文字里处理加粗、斜体。加粗先于斜体，都是非贪婪、至少一个字符。
function applyEmphasis(text) {
  return text
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>");
}

// 处理不含行内代码的一段文字：先转义，再解析链接、加粗、斜体。
function renderPlain(raw) {
  const escaped = escapeHtml(raw);
  const linkRe = /\[([^\]]*)\]\(([^)\s]*)\)/g;
  let out = "";
  let last = 0;
  let match;

  while ((match = linkRe.exec(escaped)) !== null) {
    out += applyEmphasis(escaped.slice(last, match.index));

    const label = applyEmphasis(match[1]);
    const href = match[2].trim();

    if (/^(?:https?:\/\/|mailto:)/i.test(href)) {
      out += `<a href="${href}">${label}</a>`;
    } else {
      out += label;
    }

    last = linkRe.lastIndex;
  }

  out += applyEmphasis(escaped.slice(last));
  return out;
}

// 行内格式：先切出行内代码，其余部分再交给 renderPlain。
function renderInline(raw) {
  const codeRe = /`([^`]*)`/g;
  let out = "";
  let last = 0;
  let match;

  while ((match = codeRe.exec(raw)) !== null) {
    out += renderPlain(raw.slice(last, match.index));
    out += `<code>${escapeHtml(match[1])}</code>`;
    last = codeRe.lastIndex;
  }

  out += renderPlain(raw.slice(last));
  return out;
}

// 标题：1~3 个 # 后跟一个空格。其他情况返回 null，按普通段落处理。
function parseHeading(line) {
  const match = /^(#{1,3}) (.*)$/.exec(line);
  if (!match) return null;
  return { level: match[1].length, text: match[2] };
}

export function render(source) {
  const text = String(source).replace(/\r\n/g, "\n");
  if (text.trim() === "") return "";

  const lines = text.split("\n");
  const blocks = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // 代码块：以 ``` 开头的行开始，遇到去掉首尾空白后恰好是 ``` 的行结束。
    if (line.startsWith("```")) {
      const info = line.slice(3);
      const content = [];
      let j = i + 1;
      while (j < lines.length && lines[j].trim() !== "```") {
        content.push(lines[j]);
        j += 1;
      }

      const lang = /^[\w+-]+$/.test(info) ? info : "";
      const cls = lang ? ` class="language-${lang}"` : "";
      blocks.push(`<pre><code${cls}>${escapeHtml(content.join("\n"))}</code></pre>`);

      i = j < lines.length ? j + 1 : j;
      continue;
    }

    // 标题
    const heading = parseHeading(line);
    if (heading) {
      blocks.push(
        `<h${heading.level}>${renderInline(heading.text.trim())}</h${heading.level}>`
      );
      i += 1;
      continue;
    }

    // 列表：连续的 "- " 行
    if (line.startsWith("- ")) {
      const items = [];
      while (i < lines.length && lines[i].startsWith("- ")) {
        items.push(`<li>${renderInline(lines[i].slice(2).trim())}</li>`);
        i += 1;
      }
      blocks.push(`<ul>${items.join("")}</ul>`);
      continue;
    }

    // 空行：只作分隔
    if (line.trim() === "") {
      i += 1;
      continue;
    }

    // 段落：直到空行、代码块、标题或列表开始为止
    const paragraph = [];
    while (i < lines.length) {
      const current = lines[i];
      if (
        current.trim() === "" ||
        current.startsWith("```") ||
        parseHeading(current) !== null ||
        current.startsWith("- ")
      ) {
        break;
      }
      paragraph.push(current.trim());
      i += 1;
    }
    blocks.push(`<p>${renderInline(paragraph.join(" "))}</p>`);
  }

  return blocks.join("\n");
}
