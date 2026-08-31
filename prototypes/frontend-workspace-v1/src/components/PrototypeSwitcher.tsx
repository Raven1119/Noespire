// THROWAWAY PROTOTYPE — floating variant switcher. Visually distinct from the
// page (dark pill), bottom-center, dev-build only. ←/→ cycling lives in App.
export interface VariantDef {
  key: string
  name: string
}

export function PrototypeSwitcher({
  variants,
  current,
  onSelect,
}: {
  variants: VariantDef[]
  current: string
  onSelect: (key: string) => void
}) {
  if (!import.meta.env.DEV) return null
  const idx = Math.max(0, variants.findIndex((v) => v.key === current))
  const cur = variants[idx]
  const step = (dir: number) => onSelect(variants[(idx + dir + variants.length) % variants.length].key)
  return (
    <div className="proto-switcher">
      <button onClick={() => step(-1)} title="Previous variant (←)">←</button>
      <span className="proto-switcher-label">
        <span className="proto-tag">prototype</span>
        {cur.key} — {cur.name}
      </span>
      <button onClick={() => step(1)} title="Next variant (→)">→</button>
    </div>
  )
}
