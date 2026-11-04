import type { Ref } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { MaterialIcon } from '../ui/MaterialIcon'

type TopNavBarProps = {
  variant?: 'user' | 'admin'
  showAdminLink?: boolean
  onMenuClick?: () => void
  menuButtonRef?: Ref<HTMLButtonElement>
}

export function TopNavBar({ variant = 'user', showAdminLink = true, onMenuClick, menuButtonRef }: TopNavBarProps) {
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
        {(variant === 'admin' || showAdminLink) && (
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
        <button
          type="button"
          aria-label="Account"
          className="rounded-full p-2 text-on-surface-variant transition-colors hover:bg-surface-container-low"
        >
          <MaterialIcon name="account_circle" />
        </button>
      </div>
    </header>
  )
}
