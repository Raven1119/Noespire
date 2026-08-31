// THROWAWAY PROTOTYPE — KaTeX wrapper.
// Renders fixture text that mixes prose, $inline$ / $$display$$ LaTeX, and
// [[fact:<id>|<label>]] reference markup into clickable mathematical text.
import { useMemo, type ReactNode } from 'react'
import katex from 'katex'

export function Math({ tex, display = false }: { tex: string; display?: boolean }) {
  const html = useMemo(
    () => katex.renderToString(tex, { displayMode: display, throwOnError: false }),
    [tex, display],
  )
  return <span className={display ? 'math-display' : 'math-inline'} dangerouslySetInnerHTML={{ __html: html }} />
}

type Segment =
  | { kind: 'text'; text: string }
  | { kind: 'math'; tex: string; display: boolean }
  | { kind: 'fact'; id: string; label: string }

const TOKEN_RE = /\$\$([\s\S]+?)\$\$|\$([^$]+?)\$|\[\[fact:([0-9a-f]+)\|([^\]]+?)\]\]/g

function tokenize(text: string): Segment[] {
  const segs: Segment[] = []
  let last = 0
  for (const match of text.matchAll(TOKEN_RE)) {
    const i = match.index
    if (i > last) segs.push({ kind: 'text', text: text.slice(last, i) })
    if (match[1] !== undefined) segs.push({ kind: 'math', tex: match[1], display: true })
    else if (match[2] !== undefined) segs.push({ kind: 'math', tex: match[2], display: false })
    else segs.push({ kind: 'fact', id: match[3], label: match[4] })
    last = i + match[0].length
  }
  if (last < text.length) segs.push({ kind: 'text', text: text.slice(last) })
  return segs
}

export function MathText({
  text,
  onFactRef,
}: {
  text: string
  onFactRef?: (factId: string) => void
}) {
  const segs = useMemo(() => tokenize(text), [text])
  return (
    <>
      {segs.map((seg, i): ReactNode => {
        if (seg.kind === 'math') return <Math key={i} tex={seg.tex} display={seg.display} />
        if (seg.kind === 'fact')
          return (
            <button key={i} type="button" className="fact-ref" onClick={() => onFactRef?.(seg.id)}>
              {seg.label}
            </button>
          )
        return <span key={i}>{seg.text}</span>
      })}
    </>
  )
}

/** Splits a proof body on blank lines into paragraphs of MathText. */
export function MathParagraphs({
  text,
  onFactRef,
}: {
  text: string
  onFactRef?: (factId: string) => void
}) {
  const paras = useMemo(() => text.split(/\n\n+/), [text])
  return (
    <>
      {paras.map((p, i) => (
        <p key={i}>
          <MathText text={p} onFactRef={onFactRef} />
        </p>
      ))}
    </>
  )
}
