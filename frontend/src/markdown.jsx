// A small Markdown reader for the written plan: headings, bullet and numbered lists, **bold**, _italic_.
// It builds React elements (never raw HTML), so text from the AI can't inject anything.

function inline(text, keyBase) {
  const parts = [];
  const re = /(\*\*[^*]+\*\*|_[^_]+_)/g;
  let last = 0;
  let m;
  let i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const t = m[0];
    parts.push(t.startsWith("**") ? <b key={`${keyBase}-${i++}`}>{t.slice(2, -2)}</b> : <em key={`${keyBase}-${i++}`}>{t.slice(1, -1)}</em>);
    last = m.index + t.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

export default function Markdown({ text }) {
  const blocks = [];
  let list = null;
  const flush = () => {
    if (list) blocks.push(list);
    list = null;
  };
  text.split("\n").forEach((raw, n) => {
    const line = raw.trimEnd();
    const bullet = line.match(/^\s*[-*]\s+(.*)/);
    const numbered = line.match(/^\s*\d+[.)]\s+(.*)/);
    if (bullet || numbered) {
      const type = bullet ? "ul" : "ol";
      if (!list || list.type !== type) {
        flush();
        list = { type, items: [], key: n };
      }
      list.items.push(inline((bullet || numbered)[1], n));
      return;
    }
    flush();
    if (!line.trim()) return;
    const h = line.match(/^(#{1,4})\s+(.*)/);
    if (h) blocks.push({ type: h[1].length === 1 ? "h3" : "h4", content: inline(h[2], n), key: n });
    else blocks.push({ type: "p", content: inline(line, n), key: n });
  });
  flush();
  return (
    <div className="plan-doc">
      {blocks.map((b) => {
        if (b.type === "ul" || b.type === "ol") {
          const List = b.type;
          return <List key={b.key}>{b.items.map((it, j) => <li key={j}>{it}</li>)}</List>;
        }
        const Tag = b.type;
        return <Tag key={b.key}>{b.content}</Tag>;
      })}
    </div>
  );
}
