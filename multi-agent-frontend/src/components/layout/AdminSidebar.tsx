import { NavLink } from 'react-router-dom'
import { MaterialIcon } from '../ui/MaterialIcon'

const mainNav = [
  { to: '/admin', label: 'Dashboard', icon: 'dashboard', end: true },
  { to: '/admin/knowledge', label: 'Knowledge', icon: 'database' },
  { to: '/admin/feedback', label: 'Feedback', icon: 'chat_bubble' },
  { to: '/admin/audit', label: 'Audit', icon: 'security' },
  { to: '/admin/models', label: 'Models', icon: 'model_training' },
] as const

const footerNav = [
  { to: '/admin/support', label: 'Support', icon: 'help' },
  { to: '/admin/logs', label: 'Logs', icon: 'history' },
] as const

type AdminSidebarProps = {
  className?: string
  onNavigate?: () => void
}

export function AdminSidebar({ className = '', onNavigate }: AdminSidebarProps) {
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 rounded-lg px-3 py-2 font-label-md text-label-md transition-all duration-200 ${
      isActive
        ? 'bg-secondary-container font-semibold text-on-secondary-container'
        : 'text-on-surface-variant hover:bg-surface-container-high hover:text-on-surface'
    }`

  return (
    <aside
      className={`flex w-sidebar-width flex-col gap-2 border-r border-border-subtle bg-surface-sidebar p-4 ${className}`}
    >
      <div className="mb-6 px-2">
        <h2 className="text-headline-sm font-headline-sm font-bold text-primary">Admin Console</h2>
        <p className="text-label-sm text-label-sm text-on-surface-variant">System Management</p>
      </div>

      <NavLink
        to="/chat"
        onClick={onNavigate}
        className="mb-4 flex w-full items-center justify-center gap-2 rounded-lg bg-secondary px-4 py-2.5 text-label-md font-label-md text-on-secondary shadow-sm transition-all hover:bg-secondary-container hover:text-on-secondary-container"
      >
        <MaterialIcon name="add" />
        New Chat
      </NavLink>

      <nav className="flex flex-1 flex-col gap-1">
        {mainNav.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={'end' in item ? item.end : false}
            onClick={onNavigate}
            className={linkClass}
          >
            {({ isActive }) => (
              <>
                <MaterialIcon name={item.icon} filled={isActive} />
                {item.label}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="mt-auto flex flex-col gap-1 border-t border-border-subtle pt-4">
        {footerNav.map((item) => (
          <NavLink key={item.to} to={item.to} onClick={onNavigate} className={linkClass}>
            {({ isActive }) => (
              <>
                <MaterialIcon name={item.icon} filled={isActive} />
                {item.label}
              </>
            )}
          </NavLink>
        ))}
      </div>
    </aside>
  )
}
