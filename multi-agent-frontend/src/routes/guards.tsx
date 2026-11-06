import { useState } from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { MaterialIcon } from '../components/ui/MaterialIcon'
import { loginRedirect } from '../lib/auth'

const ADMIN_REQUIRED_NOTICE = 'Admin access required'

/** Router state carried by redirects that want the destination to say why the user was sent there. */
type NoticeState = { notice?: string } | null

function Notice({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  return (
    <div className="flex max-w-sm items-start gap-3 rounded-lg border border-border-subtle bg-surface-container-lowest px-4 py-3 text-body-md text-primary shadow-lg">
      <span className="flex-1">{message}</span>
      <button
        type="button"
        aria-label="Dismiss"
        onClick={onDismiss}
        className="-mr-1 rounded-full p-1 text-on-surface-variant transition-colors hover:bg-surface-container-low"
      >
        <MaterialIcon name="close" size={18} />
      </button>
    </div>
  )
}

/** Layout route: everything below requires a signed-in user whose password is not flagged for change. */
export function RequireAuth() {
  const { state } = useAuth()
  const location = useLocation()
  const [dismissedKey, setDismissedKey] = useState<string | null>(null)

  if (state.status === 'loading') {
    return (
      <div role="status" className="flex h-screen items-center justify-center bg-surface text-body-md text-on-surface-variant">
        Loading…
      </div>
    )
  }
  if (state.status === 'anonymous') {
    const to = state.signedOut ? '/login' : loginRedirect(location.pathname, location.search)
    return <Navigate to={to} replace />
  }
  // The server answers 403 to chat for these users anyway; Settings is the only way forward.
  if (state.user.must_change_password && location.pathname !== '/settings') {
    return <Navigate to="/settings" replace />
  }

  const notice = (location.state as NoticeState)?.notice
  return (
    <>
      <Outlet />
      {/* Always mounted: a live region that appears together with its text is often not announced. */}
      <div role="status" className="fixed right-gutter-md top-20 z-[70]">
        {notice && dismissedKey !== location.key && (
          <Notice message={notice} onDismiss={() => setDismissedKey(location.key)} />
        )}
      </div>
    </>
  )
}

/** Nested inside RequireAuth. The server enforces admin on every route; this only keeps the UI honest. */
export function RequireAdmin() {
  const { state } = useAuth()
  if (state.status !== 'authenticated') return null
  if (state.user.role !== 'admin') {
    const next: NoticeState = { notice: ADMIN_REQUIRED_NOTICE }
    return <Navigate to="/chat" replace state={next} />
  }
  return <Outlet />
}
