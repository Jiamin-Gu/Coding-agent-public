// 评论区的 Markdown 渲染器，规则见 docs/SPEC.md

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

export function escapeHtml(text) {
  return text.replace(/[&<>"']/g, (c) => ESCAPES[c]);
}

function emphasis(escaped) {
  return escaped
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.+?)\*/g, "<em>$1</em>");
}

const SAFE_URL = /^(https?:\/\/|mailto:)/i;

function formatText(raw) {
  const escaped = escapeHtml(raw);
  const link = /\[([^\]]+)\]\(([^)\s]+)\)/g;
  let out = "";
  let last = 0;
  for (const m of escaped.matchAll(link)) {
    out += emphasis(escaped.slice(last, m.index));
    const text = emphasis(m[1]);
    const url = m[2].trim();
    out += SAFE_URL.test(url) ? `<a href="${url}">${text}</a>` : text;
    last = m.index + m[0].length;
  }
  return out + emphasis(escaped.slice(last));
}

export function inline(text) {
  let out = "";
  let last = 0;
  for (const m of text.matchAll(/`([^`]+)`/g)) {
    out += formatText(text.slice(last, m.index)) + `<code>${escapeHtml(m[1])}</code>`;
    last = m.index + m[0].length;
  }
  return out + formatText(text.slice(last));
}

const HEADING = /^(#{1,3}) (.*)$/;
const FENCE = /^```(.*)$/;

export function render(source) {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let paragraph = [];
  const endParagraph = () => {
    if (paragraph.length) blocks.push(`<p>${inline(paragraph.join(" "))}</p>`);
    paragraph = [];
  };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const fence = line.match(FENCE);
    if (fence) {
      endParagraph();
      const lang = fence[1].trim();
      const body = [];
      i++;
      while (i < lines.length && lines[i].trim() !== "```") body.push(lines[i++]);
      const cls = /^[A-Za-z0-9_+-]+$/.test(lang) ? ` class="language-${lang}"` : "";
      blocks.push(`<pre><code${cls}>${escapeHtml(body.join("\n"))}</code></pre>`);
      continue;
    }
    const heading = line.match(HEADING);
    if (heading) {
      endParagraph();
      const n = heading[1].length;
      blocks.push(`<h${n}>${inline(heading[2].trim())}</h${n}>`);
      continue;
    }
    if (line.startsWith("- ")) {
      endParagraph();
      const items = [];
      while (i < lines.length && lines[i].startsWith("- ")) items.push(`<li>${inline(lines[i++].slice(2).trim())}</li>`);
      i--;
      blocks.push(`<ul>${items.join("")}</ul>`);
      continue;
    }
    if (!line.trim()) {
      endParagraph();
      continue;
    }
    paragraph.push(line.trim());
  }
  endParagraph();
  return blocks.join("\n");
}
