import { useState } from 'react'
import { Outlet } from 'react-router-dom'
import { TopNavBar } from './TopNavBar'
import { AdminSidebar } from './AdminSidebar'
import { MaterialIcon } from '../ui/MaterialIcon'

export function AdminLayout() {
  const [drawerOpen, setDrawerOpen] = useState(false)

  return (
    <div className="min-h-screen bg-background text-on-background">
      <TopNavBar variant="admin" onMenuClick={() => setDrawerOpen(true)} />

      <div className="flex h-screen overflow-hidden pt-16">
        <div className="hidden md:flex">
          <AdminSidebar className="fixed bottom-0 left-0 top-16 overflow-y-auto" />
        </div>

        {drawerOpen && (
          <div className="fixed inset-0 z-[60] md:hidden">
            <button
              type="button"
              aria-label="Close menu"
              className="absolute inset-0 bg-primary/20 backdrop-blur-sm"
              onClick={() => setDrawerOpen(false)}
            />
            <div className="absolute bottom-0 left-0 top-0 w-3/4 max-w-[300px] bg-surface-sidebar shadow-xl">
              <div className="flex items-center justify-between border-b border-border-subtle p-4">
                <div>
                  <h2 className="text-headline-sm font-bold text-primary">Admin Console</h2>
                  <p className="text-label-sm text-on-surface-variant">System Management</p>
                </div>
                <button
                  type="button"
                  onClick={() => setDrawerOpen(false)}
                  className="rounded-full p-2 text-on-surface-variant hover:bg-surface-container-high"
                >
                  <MaterialIcon name="close" />
                </button>
              </div>
              <AdminSidebar className="border-0" onNavigate={() => setDrawerOpen(false)} />
            </div>
          </div>
        )}

        <main className="flex-1 overflow-y-auto bg-surface-bright md:ml-sidebar-width">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
