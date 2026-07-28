import { Link } from 'react-router-dom'
import { MaterialIcon } from '../ui/MaterialIcon'

type TopNavBarProps = {
  variant?: 'user' | 'admin'
  showAdminLink?: boolean
  onMenuClick?: () => void
}

export function TopNavBar({ variant = 'user', showAdminLink = true, onMenuClick }: TopNavBarProps) {
  return (
    <header className="fixed top-0 left-0 z-50 flex h-16 w-full items-center justify-between border-b border-border-subtle bg-surface px-gutter-md">
      <div className="flex items-center gap-4">
        {onMenuClick && (
          <button
            type="button"
            aria-label="Menu"
            onClick={onMenuClick}
            className="rounded-md p-2 text-on-surface-variant transition-colors hover:bg-surface-container-low md:hidden"
          >
            <MaterialIcon name="menu" />
          </button>
        )}
        <span className="text-headline-md font-headline-md font-bold text-primary">Agent Workspace</span>
        {showAdminLink && variant === 'user' && (
          <nav className="ml-8 hidden h-full md:flex">
            <Link
              to="/admin"
              className="flex h-full items-center border-b-2 border-secondary px-4 text-headline-sm font-bold text-secondary transition-colors hover:bg-surface-container-low"
            >
              Admin
            </Link>
          </nav>
        )}
        {variant === 'admin' && (
          <nav className="ml-8 hidden h-full md:flex">
            <Link
              to="/admin"
              className="flex h-full items-center border-b-2 border-secondary px-4 text-headline-sm font-bold text-secondary transition-colors hover:bg-surface-container-low"
            >
              Admin
            </Link>
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
