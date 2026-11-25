import { useEffect, useId, useRef, useState, type Ref } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { useAuth } from '../../auth/AuthContext'
import { MaterialIcon } from '../ui/MaterialIcon'

type TopNavBarProps = {
  variant?: 'user' | 'admin'
  onMenuClick?: () => void
  menuButtonRef?: Ref<HTMLButtonElement>
}

// Disclosure rather than role="menu": the panel holds plain text plus one button, so the full menu keyboard
// model (arrow keys, roving focus) would add behaviour without adding value. Esc and outside click close it.
function AccountMenu() {
  const { state, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [signingOut, setSigningOut] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const panelId = useId()

  useEffect(() => {
    if (!open) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      setOpen(false)
      buttonRef.current?.focus()
    }
    const onPointerDown = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('keydown', onKeyDown)
    document.addEventListener('pointerdown', onPointerDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.removeEventListener('pointerdown', onPointerDown)
    }
  }, [open])

  if (state.status !== 'authenticated') return null
  const { user } = state

  const handleSignOut = async () => {
    if (signingOut) return
    setSigningOut(true)
    setError(null)
    try {
      await logout()
    } catch {
      setError('Could not sign out. Try again.')
      setSigningOut(false)
    }
  }

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={buttonRef}
        type="button"
        aria-label="Account"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => {
          setError(null)
          setOpen((v) => !v)
        }}
        className="rounded-full p-2 text-on-surface-variant transition-colors hover:bg-surface-container-low"
      >
        <MaterialIcon name="account_circle" />
      </button>
      {open && (
        <div
          id={panelId}
          className="absolute right-0 top-full mt-2 w-64 rounded-lg border border-border-subtle bg-surface-container-lowest p-4 shadow-lg"
        >
          <p className="truncate text-label-md text-primary" title={user.email}>
            {user.email}
          </p>
          <p className="mb-3 text-label-sm text-on-surface-variant">{user.role === 'admin' ? 'Administrator' : 'User'}</p>
          <button
            type="button"
            aria-disabled={signingOut}
            onClick={handleSignOut}
            className="w-full rounded-lg border border-border-subtle px-3 py-2 text-label-md text-primary transition-colors hover:bg-surface-container-low aria-disabled:cursor-not-allowed aria-disabled:opacity-60"
          >
            {signingOut ? 'Signing out…' : 'Sign out'}
          </button>
          <p role="alert" className="mt-2 text-label-sm text-error empty:hidden">
            {error}
          </p>
        </div>
      )}
    </div>
  )
}

export function TopNavBar({ variant = 'user', onMenuClick, menuButtonRef }: TopNavBarProps) {
  const { state } = useAuth()
  const isAdmin = state.status === 'authenticated' && state.user.role === 'admin'

  return (
    <header className="fixed top-0 left-0 z-50 flex h-16 w-full items-center justify-between border-b border-border-subtle bg-surface px-gutter-md">
      <div className="flex items-center gap-4">
        {onMenuClick && (
          <button
            ref={menuButtonRef}
            type="button"
            aria-label="Menu"
            onClick={onMenuClick}
            className="rounded-md p-2 text-on-surface-variant transition-colors hover:bg-surface-container-low md:hidden"
          >
            <MaterialIcon name="menu" />
          </button>
        )}
        <span className="text-headline-md font-headline-md text-primary">Agent Workspace</span>
        {(variant === 'admin' || isAdmin) && (
          <nav className="ml-8 hidden h-full md:flex">
            <NavLink
              to="/admin"
              aria-current="true"
              className={({ isActive }) =>
                `flex h-full items-center border-b-2 px-4 text-headline-sm font-bold transition-colors hover:bg-surface-container-low ${
                  isActive ? 'border-secondary text-secondary' : 'border-transparent text-on-surface-variant'
                }`
              }
            >
              Admin
            </NavLink>
          </nav>
        )}
      </div>
      <div className="flex items-center gap-2">
        <Link
          to="/settings"
          aria-label="Settings"
          className="rounded-full p-2 text-on-surface-variant transition-colors hover:bg-surface-container-low"
        >
          <MaterialIcon name="settings" />
        </Link>
        <AccountMenu />
      </div>
    </header>
  )
}
