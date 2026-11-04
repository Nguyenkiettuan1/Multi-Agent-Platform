import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api } from '../api/client'
import type { User } from '../api/types'
import { AUTH_UNAUTHORIZED_EVENT } from '../lib/auth'
import { removeLegacyApiKey } from '../lib/storage'

// signedOut marks an explicit Sign out, so the guard sends the next person to a bare /login instead of
// carrying the previous user's path in ?next=.
type AuthState =
  | { status: 'loading' }
  | { status: 'anonymous'; signedOut?: boolean }
  | { status: 'authenticated'; user: User }

type AuthContextValue = {
  state: AuthState
  /** Throws ApiError on failure (401 = bad credentials, 429 = throttled). */
  login: (email: string, password: string) => Promise<void>
  /** Throws if the server could not revoke the session, so the UI never claims a sign-out that did not happen. */
  logout: () => Promise<void>
  /** Re-reads /auth/me, e.g. after a password change clears must_change_password. */
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: 'loading' })

  useEffect(() => {
    // Credential cleanup belongs with auth startup: a key left by an older build must not stay readable.
    removeLegacyApiKey()

    let cancelled = false
    api
      .me()
      .then(({ user }) => {
        if (!cancelled) setState({ status: 'authenticated', user })
      })
      .catch(() => {
        // 401 is the normal "not signed in"; any other failure also lands on the login page,
        // where signing in will surface a real connectivity error.
        if (!cancelled) setState({ status: 'anonymous' })
      })
    return () => {
      cancelled = true
    }
  }, [])

  // client.ts fires this on any 401 outside login: the session expired or was revoked mid-use.
  useEffect(() => {
    const onUnauthorized = () => setState({ status: 'anonymous' })
    window.addEventListener(AUTH_UNAUTHORIZED_EVENT, onUnauthorized)
    return () => window.removeEventListener(AUTH_UNAUTHORIZED_EVENT, onUnauthorized)
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const { user } = await api.login(email, password)
    setState({ status: 'authenticated', user })
  }, [])

  const logout = useCallback(async () => {
    await api.logout()
    setState({ status: 'anonymous', signedOut: true })
  }, [])

  const refresh = useCallback(async () => {
    const { user } = await api.me()
    setState({ status: 'authenticated', user })
  }, [])

  const value = useMemo(() => ({ state, login, logout, refresh }), [state, login, logout, refresh])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// The hook lives beside its provider on purpose: they share one context object and are always imported together.
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
