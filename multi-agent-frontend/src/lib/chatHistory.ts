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

export type TurnOutcome = { kind: 'answer' } | { kind: 'note'; text: string }

/**
 * How a restored turn shows its reply. Failed and incomplete turns keep the user's bubble but get a
 * fixed muted note instead of an answer; the server's error detail is never shown. A missing or
 * unknown status is treated as completed so an older or newer backend cannot hide an answer.
 */
export function turnOutcome(status: string | null | undefined): TurnOutcome {
  if (status === 'failed') return { kind: 'note', text: 'No answer — the request failed' }
  if (status === 'incomplete') return { kind: 'note', text: 'No answer — the request did not finish' }
  return { kind: 'answer' }
}

/** Appends the next sidebar page, skipping sessions already listed (a new chat can shift a page boundary). */
export function appendSessionPage<T extends { session_id: string }>(current: T[], page: T[]): T[] {
  const seen = new Set(current.map((s) => s.session_id))
  const merged = [...current]
  for (const item of page) {
    if (seen.has(item.session_id)) continue
    seen.add(item.session_id)
    merged.push(item)
  }
  return merged
}

/** Window event ChatPage fires when a turn finishes or a session is created, so the sidebar refetches. */
export const SESSION_UPDATED_EVENT = 'chat:session-updated'

/**
 * The session id a chat error carries when the server created the session and then failed
 * (SSE `error` event payload, or the body of a failed POST /chat). Null when absent or malformed,
 * so a plain 404/500 never sends the reader anywhere.
 */
export function sessionIdFromErrorPayload(payload: unknown): string | null {
  if (!payload || typeof payload !== 'object') return null
  const { session_id: top, detail } = payload as { session_id?: unknown; detail?: unknown }
  if (typeof top === 'string' && top) return top
  if (detail && typeof detail === 'object') {
    const nested = (detail as { session_id?: unknown }).session_id
    if (typeof nested === 'string' && nested) return nested
  }
  return null
}
