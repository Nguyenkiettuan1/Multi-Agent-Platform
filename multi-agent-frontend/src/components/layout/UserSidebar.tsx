import { useCallback, useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { api } from '../../api/client'
import { MaterialIcon } from '../ui/MaterialIcon'
import { getChatSessions, upsertChatSession, type ChatSession } from '../../lib/storage'
import { truncate } from '../../lib/format'

type UserSidebarProps = {
  className?: string
  onNavigate?: () => void
}

export function UserSidebar({ className = '', onNavigate }: UserSidebarProps) {
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [loading, setLoading] = useState(true)

  const syncSessions = useCallback(async () => {
    const local = getChatSessions()
    try {
      const data = await api.chatSessions(30)
      const fromApi: ChatSession[] = data.items.map((item) => ({
        id: item.session_id,
        title: truncate(item.title || 'Conversation', 40),
        updatedAt: item.updated_at ?? new Date().toISOString(),
      }))
      for (const s of fromApi) {
        upsertChatSession(s)
      }
      const merged = new Map<string, ChatSession>()
      for (const s of [...fromApi, ...local]) {
        const existing = merged.get(s.id)
        if (!existing || s.updatedAt > existing.updatedAt) {
          merged.set(s.id, s)
        }
      }
      const sorted = [...merged.values()].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
      setSessions(sorted)
    } catch {
      setSessions(local)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void syncSessions()
    const onStorage = () => setSessions(getChatSessions())
    window.addEventListener('storage', onStorage)
    const interval = setInterval(() => void syncSessions(), 5000)
    return () => {
      window.removeEventListener('storage', onStorage)
      clearInterval(interval)
    }
  }, [syncSessions])

  return (
    <aside
      className={`flex w-sidebar-width flex-col gap-2 border-r border-border-subtle bg-surface-sidebar p-4 ${className}`}
    >
      <div className="mb-4">
        <h2 className="text-headline-sm font-bold text-primary">Admin Console</h2>
        <p className="text-body-md text-on-surface-variant">System Management</p>
      </div>

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
        ) : sessions.length === 0 ? (
          <p className="px-2 text-body-md text-on-surface-variant">No conversations yet</p>
        ) : (
          <ul className="flex flex-col gap-1">
            {sessions.map((s) => (
              <li key={s.id}>
                <NavLink
                  to={`/chat/${s.id}`}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    `flex items-center gap-3 rounded-lg px-3 py-2 text-label-md transition-all ${
                      isActive
                        ? 'bg-secondary-container font-semibold text-on-secondary-container'
                        : 'text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface'
                    }`
                  }
                >
                  <MaterialIcon name="chat" size={20} />
                  <span className="truncate">{s.title}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="mt-auto flex flex-col gap-1 border-t border-border-subtle pt-4">
        <NavLink
          to="/admin/support"
          className="flex items-center gap-3 rounded-lg px-3 py-2 text-label-md text-on-surface-variant hover:bg-surface-container-high"
        >
          <MaterialIcon name="help" size={20} />
          Support
        </NavLink>
        <NavLink
          to="/admin/logs"
          className="flex items-center gap-3 rounded-lg px-3 py-2 text-label-md text-on-surface-variant hover:bg-surface-container-high"
        >
          <MaterialIcon name="history" size={20} />
          Logs
        </NavLink>
      </div>
    </aside>
  )
}
