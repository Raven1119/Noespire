/**
 * Every verified artifact is labeled `LLM-verified` (ADR-0004). The bare word
 * "Verified" is never used; green is reserved for a future kernel-verified
 * state that will occupy this same slot with different styling.
 */
export function LlmVerifiedBadge() {
  return <span className="badge badge--llm-verified">LLM-verified</span>;
}
