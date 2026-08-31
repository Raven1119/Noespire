import katex from "katex";
import "katex/dist/katex.min.css";

interface Segment {
  kind: "text" | "math";
  value: string;
}

/** Split a statement into plain text and `$…$` inline-math segments. */
function segments(statement: string): Segment[] {
  const parts: Segment[] = [];
  const re = /\$([^$]+)\$/g;
  let last = 0;
  let match: RegExpExecArray | null;
  while ((match = re.exec(statement)) !== null) {
    if (match.index > last) {
      parts.push({ kind: "text", value: statement.slice(last, match.index) });
    }
    parts.push({ kind: "math", value: match[1] });
    last = match.index + match[0].length;
  }
  if (last < statement.length) {
    parts.push({ kind: "text", value: statement.slice(last) });
  }
  return parts;
}

/** Render a mathematical statement with inline `$…$` math via KaTeX. */
export function KatexStatement({ statement }: { statement: string }) {
  return (
    <span className="katex-statement">
      {segments(statement).map((part, i) =>
        part.kind === "math" ? (
          <span
            key={i}
            dangerouslySetInnerHTML={{
              __html: katex.renderToString(part.value, { throwOnError: false }),
            }}
          />
        ) : (
          <span key={i}>{part.value}</span>
        )
      )}
    </span>
  );
}
