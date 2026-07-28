import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import { TopNavBar } from './TopNavBar'
import { UserSidebar } from './UserSidebar'
import { MaterialIcon } from '../ui/MaterialIcon'

export function UserLayout() {
  const [drawerOpen, setDrawerOpen] = useState(false)

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-surface text-on-surface">
      <TopNavBar onMenuClick={() => setDrawerOpen(true)} />

      <div className="flex min-h-0 flex-1 pt-16">
        <div className="hidden md:flex">
          <UserSidebar className="fixed bottom-0 left-0 top-16 z-40" />
        </div>

        {drawerOpen && (
          <div className="fixed inset-0 z-[60] md:hidden">
            <button
              type="button"
              aria-label="Close menu"
              className="absolute inset-0 bg-primary/20 backdrop-blur-sm"
              onClick={() => setDrawerOpen(false)}
            />
            <aside className="absolute bottom-0 left-0 top-14 flex w-[280px] flex-col border-r border-border-subtle bg-surface-sidebar transition-transform">
              <UserSidebar className="border-0" onNavigate={() => setDrawerOpen(false)} />
            </aside>
          </div>
        )}

        <main className="relative flex min-h-0 flex-1 flex-col overflow-hidden md:ml-sidebar-width">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

export function MobileBottomNav() {
  const items = [
    { to: '/admin', icon: 'dashboard', label: 'Dashboard' },
    { to: '/admin/knowledge', icon: 'database', label: 'Knowledge' },
    { to: '/admin/feedback', icon: 'chat_bubble', label: 'Feedback' },
    { to: '/admin/logs', icon: 'history', label: 'Logs', active: true },
    { to: '/admin/models', icon: 'model_training', label: 'Models' },
  ]

  return (
    <nav className="fixed bottom-0 left-0 z-50 flex w-full items-center justify-around border-t border-border-subtle bg-surface px-2 py-2 shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.05)] md:hidden">
      {items.map((item) => (
        <a
          key={item.to}
          href={item.to}
          className={`relative flex min-w-[64px] flex-col items-center p-2 ${
            item.active ? 'font-bold text-secondary' : 'text-on-surface-variant'
          }`}
        >
          {item.active && (
            <div className="absolute top-0 left-1/2 h-1 w-8 -translate-x-1/2 rounded-b-full bg-secondary" />
          )}
          <MaterialIcon name={item.icon} filled={item.active} size={24} className="mb-1" />
          <span className="text-[10px] leading-none">{item.label}</span>
        </a>
      ))}
    </nav>
  )
}
