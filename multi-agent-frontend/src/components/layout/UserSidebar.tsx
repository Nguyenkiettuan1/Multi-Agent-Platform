import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { api } from '../../api/client'
import type { ChatSessionSummary } from '../../api/types'
import { useAuth } from '../../auth/AuthContext'
import { MaterialIcon } from '../ui/MaterialIcon'
import { appendSessionPage, canMoveFocus, createGeneration, SESSION_UPDATED_EVENT } from '../../lib/chatHistory'
import { truncate } from '../../lib/format'

type UserSidebarProps = {
  className?: string
  onNavigate?: () => void
}

// Fixed copy: the server's detail text is for logs, not for people.
const REFRESH_ERROR = 'Could not load your conversations. Check your connection, then try again.'
const MORE_ERROR = 'Could not load more conversations. Try again.'

export function UserSidebar({ className = '', onNavigate }: UserSidebarProps) {
  const { state } = useAuth()
  const isAdmin = state.status === 'authenticated' && state.user.role === 'admin'
  // The server answers 403 to every chat call until the password is changed; skip the fetch instead of showing an error.
  const mustChangePassword = state.status === 'authenticated' && state.user.must_change_password
  const { pathname } = useLocation()
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([])
  const [nextBefore, setNextBefore] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [refreshFailed, setRefreshFailed] = useState(false)
  const [moreFailed, setMoreFailed] = useState(false)
  // Separate tickets: a refresh supersedes only an older refresh, "Show more" only an older "Show more".
  // The two results are merged order-independently by appendSessionPage.
  const refreshGen = useRef(createGeneration())
  const moreGen = useRef(createGeneration())
  // True once "Show more" appended pages: a refresh then keeps that tail instead of collapsing the list.
  const extended = useRef(false)
  const moreRef = useRef<HTMLButtonElement>(null)
  const pendingFocus = useRef<{ id: string; wasOnButton: boolean } | null>(null)

  const refresh = useCallback(async () => {
    if (mustChangePassword) {
      setLoading(false)
      return
    }
    const ticket = refreshGen.current.next()
    try {
      const data = await api.chatSessions({ limit: 30 })
      if (!refreshGen.current.isCurrent(ticket)) return
      setSessions((prev) => (extended.current ? appendSessionPage(data.items, prev) : data.items))
      if (!extended.current) setNextBefore(data.has_more ? data.next_before : null)
      setRefreshFailed(false)
    } catch {
      if (refreshGen.current.isCurrent(ticket)) setRefreshFailed(true)
    } finally {
      if (refreshGen.current.isCurrent(ticket)) setLoading(false)
    }
  }, [mustChangePassword])

  // The list changes only when the user navigates or a turn finishes, so no polling: each fetch is a session lookup server-side.
  useEffect(() => {
    void refresh()
  }, [refresh, pathname])

  useEffect(() => {
    const onUpdated = () => void refresh()
    window.addEventListener(SESSION_UPDATED_EVENT, onUpdated)
    return () => window.removeEventListener(SESSION_UPDATED_EVENT, onUpdated)
  }, [refresh])

  const showMore = async () => {
    if (!nextBefore || loadingMore) return
    const ticket = moreGen.current.next()
    const wasOnButton = document.activeElement === moreRef.current
    setLoadingMore(true)
    setMoreFailed(false)
    try {
      const data = await api.chatSessions({ limit: 30, before: nextBefore })
      if (!moreGen.current.isCurrent(ticket)) return
      extended.current = true
      const known = new Set(sessions.map((x) => x.session_id))
      const first = data.items.find((x) => !known.has(x.session_id))
      if (first) pendingFocus.current = { id: first.session_id, wasOnButton }
      setSessions((prev) => appendSessionPage(prev, data.items))
      setNextBefore(data.has_more ? data.next_before : null)
    } catch {
      if (moreGen.current.isCurrent(ticket)) setMoreFailed(true)
    } finally {
      if (moreGen.current.isCurrent(ticket)) setLoadingMore(false)
    }
  }

  // The button unmounts after the last page, dropping focus to <body>; hand it to the first new row (Wave A pattern).
  useLayoutEffect(() => {
    const pending = pendingFocus.current
    if (!pending) return
    pendingFocus.current = null
    if (!canMoveFocus({ wasOnButton: pending.wasOnButton, active: document.activeElement, button: moreRef.current, body: document.body })) return
    document.querySelector<HTMLElement>(`[data-session-id="${CSS.escape(pending.id)}"]`)?.focus()
  }, [sessions])

  // Always mounted so a change of text is announced; empty it takes no space.
  const notice = refreshFailed ? REFRESH_ERROR : moreFailed ? MORE_ERROR : ''

  return (
    <aside
      className={`flex w-sidebar-width flex-col gap-2 border-r border-border-subtle bg-surface-sidebar p-4 ${className}`}
    >
      <NavLink
        to="/chat"
        onClick={onNavigate}
        className="mb-4 flex w-full items-center justify-center gap-2 rounded-lg border border-outline px-4 py-2 text-label-md text-on-surface transition-colors hover:bg-surface-container-low"
      >
        <MaterialIcon name="add" size={18} />
        New conversation
      </NavLink>

      <div className="flex-1 overflow-y-auto">
        <div className="mb-2 px-2 text-label-sm uppercase tracking-wider text-on-surface-variant">Recent</div>
        {loading ? (
          <p className="px-2 text-body-md text-on-surface-variant">Loading…</p>
        ) : mustChangePassword ? (
          <p className="px-2 text-body-md text-on-surface-variant">Change your password to see your conversations.</p>
        ) : sessions.length === 0 ? (
          !refreshFailed && <p className="px-2 text-body-md text-on-surface-variant">No conversations yet</p>
        ) : (
          <ul className="flex flex-col gap-1">
            {sessions.map((s) => (
              <li key={s.session_id}>
                <NavLink
                  to={`/chat/${s.session_id}`}
                  data-session-id={s.session_id}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    `flex items-center gap-3 rounded-lg px-3 py-2 text-label-md transition-colors focus-visible:outline-offset-[-2px] ${
                      isActive
                        ? 'bg-secondary-container font-semibold text-on-secondary-container'
                        : 'text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface'
                    }`
                  }
                >
                  <MaterialIcon name="chat" size={20} />
                  <span className="truncate">{truncate(s.title || 'Conversation', 40)}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        )}
        <div role="status" className={notice ? 'mt-2 px-2 text-label-sm text-on-error-container' : undefined}>
          {notice}
        </div>
        {refreshFailed && (
          <button
            type="button"
            onClick={() => void refresh()}
            className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-label-md text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-on-surface"
          >
            <MaterialIcon name="refresh" size={18} />
            Try again
          </button>
        )}
        {nextBefore && (
          <button
            ref={moreRef}
            type="button"
            aria-disabled={loadingMore}
            aria-busy={loadingMore}
            onClick={() => void showMore()}
            className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-label-md text-on-surface-variant transition-colors hover:bg-surface-container-high hover:text-on-surface aria-disabled:opacity-60"
          >
            <MaterialIcon name={loadingMore ? 'progress_activity' : moreFailed ? 'refresh' : 'expand_more'} size={18} className={loadingMore ? 'animate-spin' : undefined} />
            {loadingMore ? 'Loading…' : moreFailed ? 'Retry' : 'Show more'}
          </button>
        )}
      </div>

      {isAdmin && (
        <div className="mt-auto flex flex-col gap-1 border-t border-border-subtle pt-4">
          <NavLink
            to="/admin/support"
            onClick={onNavigate}
            className="flex items-center gap-3 rounded-lg px-3 py-2 text-label-md text-on-surface-variant hover:bg-surface-container-high"
          >
            <MaterialIcon name="help" size={20} />
            Support
          </NavLink>
        </div>
      )}
    </aside>
  )
}
