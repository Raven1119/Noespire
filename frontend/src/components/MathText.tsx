import { useMemo } from "react";
import type { ReactNode } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";

/**
 * Minimal production math/text formatter (spec §9, task card §3/§8): inline
 * `$…$`, display `$$…$$`, plain prose, and clickable Fact references. Known
 * fact ids (from target_fact + supporting_closure) are replaced in the text
 * by math-styled buttons labelled "Lemma N" / "Main theorem" — never raw ids
 * in the body. Invalid LaTeX renders as readable source (throwOnError: false)
 * and never crashes the workspace. No Markdown engine.
 */

type Segment =
  | { kind: "text"; text: string }
  | { kind: "math"; tex: string; display: boolean }
  | { kind: "fact"; id: string };

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function tokenize(text: string, factIds: string[]): Segment[] {
  const factAlternation = factIds
    .slice()
    .sort((a, b) => b.length - a.length)
    .map(escapeRegExp)
    .join("|");
  const pattern = new RegExp(
    `\\$\\$([\\s\\S]+?)\\$\\$|\\$([^$]+?)\\$${factAlternation ? `|(${factAlternation})` : ""}`,
    "g"
  );
  const segments: Segment[] = [];
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    const index = match.index;
    if (index > last) {
      segments.push({ kind: "text", text: text.slice(last, index) });
    }
    if (match[1] !== undefined) {
      segments.push({ kind: "math", tex: match[1], display: true });
    } else if (match[2] !== undefined) {
      segments.push({ kind: "math", tex: match[2], display: false });
    } else {
      segments.push({ kind: "fact", id: match[3] });
    }
    last = index + match[0].length;
  }
  if (last < text.length) {
    segments.push({ kind: "text", text: text.slice(last) });
  }
  return segments;
}

export function Math({ tex, display = false }: { tex: string; display?: boolean }) {
  const html = useMemo(
    () => katex.renderToString(tex, { displayMode: display, throwOnError: false }),
    [tex, display]
  );
  return (
    <span
      className={display ? "math-display" : "math-inline"}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

interface MathTextProps {
  text: string;
  /** fact_id → display label ("Lemma 1", "Main theorem"). */
  factNames?: Map<string, string>;
  onFactRef?: (factId: string) => void;
}

export function MathText({ text, factNames, onFactRef }: MathTextProps) {
  const ids = factNames !== undefined ? [...factNames.keys()] : [];
  const segments = useMemo(() => tokenize(text, ids), [text, ids]);
  return (
    <>
      {segments.map((segment, index): ReactNode => {
        if (segment.kind === "math") {
          return <Math key={index} tex={segment.tex} display={segment.display} />;
        }
        if (segment.kind === "fact") {
          return (
            <button
              key={index}
              type="button"
              className="fact-ref"
              onClick={() => onFactRef?.(segment.id)}
            >
              {factNames?.get(segment.id) ?? segment.id}
            </button>
          );
        }
        return <span key={index}>{segment.text}</span>;
      })}
    </>
  );
}

/** Splits a proof body on blank lines into paragraphs of MathText. */
export function MathParagraphs({
  text,
  factNames,
  onFactRef,
}: MathTextProps) {
  const paragraphs = useMemo(() => text.split(/\n\n+/), [text]);
  return (
    <>
      {paragraphs.map((paragraph, index) => (
        <p key={index} className="math-paragraph">
          <MathText text={paragraph} factNames={factNames} onFactRef={onFactRef} />
        </p>
      ))}
    </>
  );
}
