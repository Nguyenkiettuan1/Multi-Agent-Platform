// The browser no longer holds an API key (auth is a httpOnly cookie); this name is only used to purge old copies.
const LEGACY_API_KEY_STORAGE = 'multiagent_api_key'
const SESSIONS_STORAGE = 'multiagent_chat_sessions'

export type ChatSession = {
  id: string
  title: string
  updatedAt: string
}

/** Removes the key an earlier version stored in localStorage, where any script on the page could read it. */
export function removeLegacyApiKey(): void {
  try {
    localStorage.removeItem(LEGACY_API_KEY_STORAGE)
  } catch {
    /* storage blocked (private mode, policy): nothing to remove */
  }
}

export function getChatSessions(): ChatSession[] {
  try {
    const raw = localStorage.getItem(SESSIONS_STORAGE)
    if (!raw) return []
    return JSON.parse(raw) as ChatSession[]
  } catch {
    return []
  }
}

export function upsertChatSession(session: ChatSession): void {
  const sessions = getChatSessions().filter((s) => s.id !== session.id)
  sessions.unshift(session)
  localStorage.setItem(SESSIONS_STORAGE, JSON.stringify(sessions.slice(0, 50)))
}
