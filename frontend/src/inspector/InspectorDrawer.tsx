import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

export interface InspectorField {
  label: string;
  value: ReactNode;
  mono?: boolean;
}

interface InspectorDrawerProps {
  /** Object title — also the dialog's accessible name. */
  title: string;
  subtitle?: string;
  fields: InspectorField[];
  /** The focused object, serialized verbatim into the collapsible raw view. */
  raw: unknown;
  onClose: () => void;
}

/**
 * The right overlay drawer for machine metadata (spec §9/§10). Object-agnostic:
 * any object can be inspected; callers supply titled fields plus the raw
 * object. Dialog semantics: role=dialog, aria-modal, labelled ✕ close, Esc
 * closes, scrim click closes, focus moves into the drawer on open and returns
 * to the previously focused element on close. Raw JSON renders in a
 * collapsible <pre> — no JSON-viewer dependency.
 */
export function InspectorDrawer({
  title,
  subtitle,
  fields,
  raw,
  onClose,
}: InspectorDrawerProps) {
  const closeRef = useRef<HTMLButtonElement>(null);
  // Raw JSON mounts only when its disclosure is open — collapsed means
  // genuinely absent, not merely hidden.
  const [rawOpen, setRawOpen] = useState(false);

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previouslyFocused?.focus?.();
    };
  }, [onClose]);

  return (
    <>
      <div className="inspector-scrim" onClick={onClose} />
      <aside
        className="inspector-drawer"
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="inspector-drawer__head">
          <div>
            <h2 className="inspector-drawer__title">{title}</h2>
            {subtitle !== undefined && (
              <p className="inspector-drawer__subtitle">{subtitle}</p>
            )}
          </div>
          <button
            ref={closeRef}
            className="button button--icon"
            aria-label="Close inspector"
            title="Close (Esc)"
            onClick={onClose}
          >
            ✕
          </button>
        </div>
        <div className="inspector-drawer__body">
          {fields.map((field) => (
            <div className="inspector-field" key={field.label}>
              <div className="inspector-field__label">{field.label}</div>
              <div
                className={
                  field.mono === true
                    ? "inspector-field__value inspector-field__value--mono"
                    : "inspector-field__value"
                }
              >
                {field.value}
              </div>
            </div>
          ))}
          <details
            className="inspector-raw"
            onToggle={(event) =>
              setRawOpen((event.target as HTMLDetailsElement).open)
            }
          >
            <summary>Raw JSON</summary>
            {rawOpen && (
              <pre className="inspector-raw__pre">
                {JSON.stringify(raw, null, 2)}
              </pre>
            )}
          </details>
        </div>
      </aside>
    </>
  );
}
