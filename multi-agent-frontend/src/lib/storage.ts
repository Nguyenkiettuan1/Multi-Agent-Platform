// The browser no longer holds an API key (auth is a httpOnly cookie); this name is only used to purge old copies.
const LEGACY_API_KEY_STORAGE = 'multiagent_api_key'
// The sidebar list now comes from the server per user; an old copy here would show another person's titles.
const LEGACY_SESSIONS_STORAGE = 'multiagent_chat_sessions'

/** Removes the key an earlier version stored in localStorage, where any script on the page could read it. */
export function removeLegacyApiKey(): void {
  try {
    localStorage.removeItem(LEGACY_API_KEY_STORAGE)
  } catch {
    /* storage blocked (private mode, policy): nothing to remove */
  }
}

/** Removes the locally cached conversation list an earlier version kept, shared by everyone on this browser. */
export function removeLegacyChatSessions(): void {
  try {
    localStorage.removeItem(LEGACY_SESSIONS_STORAGE)
  } catch {
    /* storage blocked (private mode, policy): nothing to remove */
  }
}
