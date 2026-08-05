const API_KEY_STORAGE = 'multiagent_api_key'
const SESSIONS_STORAGE = 'multiagent_chat_sessions'

export type ChatSession = {
  id: string
  title: string
  updatedAt: string
}

export function getApiKey(): string {
  return localStorage.getItem(API_KEY_STORAGE) ?? ''
}

export function setApiKey(key: string): void {
  if (key.trim()) {
    localStorage.setItem(API_KEY_STORAGE, key.trim())
  } else {
    localStorage.removeItem(API_KEY_STORAGE)
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
