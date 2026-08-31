// THROWAWAY PROTOTYPE — Inspector: the right overlay drawer for machine
// metadata (CONTEXT.md). The main content stays mathematically clean; ids,
// route_id, artifacts and raw JSON live ONLY in here.
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'

export interface InspectorField {
  label: string
  value: ReactNode
  mono?: boolean
}

export interface InspectorContent {
  title: string
  subtitle?: string
  fields: InspectorField[]
  raw: unknown
}

const InspectorCtx = createContext<{ open: (content: InspectorContent) => void }>({
  open: () => {},
})

export const useInspector = () => useContext(InspectorCtx)

export function InspectorProvider({ children }: { children: ReactNode }) {
  const [content, setContent] = useState<InspectorContent | null>(null)
  const open = useCallback((c: InspectorContent) => setContent(c), [])
  const close = useCallback(() => setContent(null), [])

  useEffect(() => {
    if (!content) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [content, close])

  return (
    <InspectorCtx.Provider value={{ open }}>
      {children}
      {content && (
        <>
          <div className="scrim" onClick={close} />
          <aside className="inspector" role="dialog" aria-label="Inspector">
            <div className="inspector-head">
              <div>
                <h2 className="inspector-title">{content.title}</h2>
                {content.subtitle && <p className="inspector-sub">{content.subtitle}</p>}
              </div>
              <button className="icon-btn" onClick={close} title="Close (Esc)">
                ✕
              </button>
            </div>
            <div className="inspector-body">
              {content.fields.map((f, i) => (
                <div className="inspector-field" key={i}>
                  <div className="inspector-field-label">{f.label}</div>
                  <div className={`inspector-field-value${f.mono ? ' mono' : ''}`}>{f.value}</div>
                </div>
              ))}
              <div className="inspector-field-label" style={{ marginTop: 16 }}>
                Raw JSON
              </div>
              <pre className="inspector-raw">{JSON.stringify(content.raw, null, 2)}</pre>
            </div>
          </aside>
        </>
      )}
    </InspectorCtx.Provider>
  )
}
