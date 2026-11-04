type HasTraceId = { trace_id: string }

/**
 * Drops turns already shown, and repeats inside the page. Keyset paging should keep pages
 * disjoint; this is a defensive dedupe so a backend overlap can never render a turn twice.
 */
export function dropKnownTurns<T extends HasTraceId>(turns: T[], knownIds: ReadonlySet<string>): T[] {
  const seen = new Set(knownIds)
  const kept: T[] = []
  for (const turn of turns) {
    if (seen.has(turn.trace_id)) continue
    seen.add(turn.trace_id)
    kept.push(turn)
  }
  return kept
}

/**
 * Request tickets: every session change and every older-page request takes a new one, and only
 * the holder of the latest may apply its result or clear shared in-flight state. This is what
 * keeps a slow response from session A out of a later A view (A to B to A).
 */
export function createGeneration() {
  let current = 0
  return {
    next: () => ++current,
    isCurrent: (ticket: number) => ticket === current,
  }
}

/** Scroll offset that keeps the same content under the viewport after content was inserted above it. */
export function scrollTopAfterPrepend(oldScrollTop: number, oldScrollHeight: number, newScrollHeight: number): number {
  return Math.max(0, oldScrollTop + (newScrollHeight - oldScrollHeight))
}

/**
 * Whether the prepend may move focus to the first loaded turn. Only when focus is still where
 * the load started (the load button) or has fallen to the body; a user who moved on, say into
 * the textarea, keeps their focus.
 */
export function canMoveFocus(o: { wasOnButton: boolean; active: unknown; button: unknown; body: unknown }): boolean {
  if (o.active == null || o.active === o.body) return true
  return o.wasOnButton && o.active === o.button
}
