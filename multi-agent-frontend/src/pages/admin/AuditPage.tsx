import { useMemo, useState } from 'react'
import { api } from '../../api/client'
import { MaterialIcon } from '../../components/ui/MaterialIcon'
import { useAsync } from '../../hooks/useAsync'
import { formatAgentName, formatDateTime, formatRelativeTime } from '../../lib/format'

const ALL_ACTIONS = ['chat_start', 'chat_complete', 'chat_error'] as const

function actionStyle(action: string): { actionColor: string; dotColor: string } {
  if (action.includes('error')) {
    return {
      actionColor: 'bg-error-container border-error/20 text-on-error-container',
      dotColor: 'bg-status-error',
    }
  }
  if (action.includes('complete')) {
    return {
      actionColor: 'bg-surface-container border-surface-tint/20 text-on-primary-container',
      dotColor: 'bg-status-success',
    }
  }
  return {
    actionColor: 'bg-surface-container border-surface-tint/20 text-on-primary-container',
    dotColor: 'bg-citation-knowledge',
  }
}

function agentIcon(name: string | null | undefined): string {
  if (!name) return 'support_agent'
  if (name.includes('legal')) return 'gavel'
  if (name.includes('db')) return 'database'
  if (name.includes('research')) return 'travel_explore'
  return 'support_agent'
}

export function AuditPage() {
  const [search, setSearch] = useState('')
  const [actions, setActions] = useState<string[]>([...ALL_ACTIONS])

  const traceFilter = search.trim().startsWith('trc_') || search.length > 20 ? search.trim() : undefined

  const { data, loading, error, reload } = useAsync(
    () => api.adminAudit({ limit: 50, trace_id: traceFilter }),
    [traceFilter],
  )

  const rows = useMemo(() => {
    const items = data?.items ?? []
    return items.filter((row) => {
      if (!actions.includes(row.action)) return false
      if (!search.trim() || traceFilter) return true
      const q = search.toLowerCase()
      return (
        row.trace_id.toLowerCase().includes(q) ||
        (row.user_id ?? '').toLowerCase().includes(q) ||
        (row.agent_name ?? '').toLowerCase().includes(q)
      )
    })
  }, [actions, data?.items, search, traceFilter])

  const toggleAction = (action: string) => {
    setActions((prev) => (prev.includes(action) ? prev.filter((a) => a !== action) : [...prev, action]))
  }

  return (
    <div className="flex flex-col">
      <div className="space-y-6 px-margin-page py-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="mb-2 text-display-lg text-on-surface">Audit Logs</h1>
            <p className="max-w-2xl text-body-md text-on-surface-variant">
              Track, search, and analyze all system activity and agent interactions.
            </p>
          </div>
          <button
            type="button"
            onClick={reload}
            disabled={loading}
            className="flex items-center gap-2 rounded-lg border border-border-subtle px-4 py-2 text-label-md text-primary hover:bg-surface-container-low disabled:opacity-50"
          >
            <MaterialIcon name="refresh" size={18} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>

        {error && (
          <div className="rounded-lg border border-error/30 bg-error-container/30 px-4 py-3 text-body-md text-on-error-container">
            {error}
          </div>
        )}

        <div className="flex flex-col items-center justify-between gap-4 rounded-xl border border-border-subtle bg-surface p-4 shadow-sm lg:flex-row">
          <div className="relative w-full lg:w-96">
            <MaterialIcon
              name="search"
              className="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant"
            />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by Trace ID or User ID..."
              className="w-full rounded-lg border border-border-subtle bg-surface-container-low py-2 pr-4 pl-10 text-body-md text-on-surface placeholder:text-on-surface-variant focus:border-secondary focus:ring-1 focus:ring-secondary focus:outline-none"
            />
          </div>
          <div className="flex w-full flex-wrap items-center gap-3 lg:w-auto">
            <span className="mr-1 text-label-md text-on-surface-variant">Action filter:</span>
            {ALL_ACTIONS.map((action) => (
              <label key={action} className="group flex cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  checked={actions.includes(action)}
                  onChange={() => toggleAction(action)}
                  className="h-4 w-4 rounded border-border-subtle text-secondary focus:ring-secondary"
                />
                <span className="text-body-md text-on-surface group-hover:text-primary">{action}</span>
              </label>
            ))}
          </div>
        </div>
      </div>

      <div className="flex-1 px-margin-page pb-margin-page">
        <div className="flex h-full flex-col overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-sm">
          <div className="flex-1 overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <thead className="sticky top-0 z-10 border-b border-border-subtle bg-surface-container-low">
                <tr>
                  <th className="whitespace-nowrap px-6 py-4 font-label-md font-medium text-on-surface-variant">Time</th>
                  <th className="whitespace-nowrap px-6 py-4 font-label-md font-medium text-on-surface-variant">Action</th>
                  <th className="whitespace-nowrap px-6 py-4 font-label-md font-medium text-on-surface-variant">Trace ID</th>
                  <th className="whitespace-nowrap px-6 py-4 font-label-md font-medium text-on-surface-variant">User ID</th>
                  <th className="whitespace-nowrap px-6 py-4 font-label-md font-medium text-on-surface-variant">Agent Name</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle bg-surface">
                {loading ? (
                  <tr>
                    <td colSpan={5} className="px-6 py-8 text-center text-on-surface-variant">
                      Loading…
                    </td>
                  </tr>
                ) : rows.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-6 py-8 text-center text-on-surface-variant">
                      No results
                    </td>
                  </tr>
                ) : (
                  rows.map((row) => {
                    const style = actionStyle(row.action)
                    const isError = row.action.includes('error')
                    return (
                      <tr
                        key={`${row.id ?? row.trace_id}-${row.action}-${row.created_at}`}
                        className={`group transition-colors hover:bg-surface-bright ${isError ? 'bg-error-container/10' : ''}`}
                      >
                        <td className="whitespace-nowrap px-6 py-4 font-body-code text-body-code text-on-surface">
                          {formatDateTime(row.created_at)}
                          <div className="mt-0.5 text-[11px] text-on-surface-variant">
                            {formatRelativeTime(row.created_at)}
                          </div>
                        </td>
                        <td className="whitespace-nowrap px-6 py-4">
                          <span
                            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-label-sm ${style.actionColor}`}
                          >
                            <span className={`h-1.5 w-1.5 rounded-full ${style.dotColor}`} />
                            {row.action}
                          </span>
                        </td>
                        <td className="whitespace-nowrap px-6 py-4">
                          <span className="flex items-center gap-1 font-body-code text-body-code text-secondary">
                            {row.trace_id.slice(0, 12)}…
                          </span>
                        </td>
                        <td className="whitespace-nowrap px-6 py-4 font-body-code text-body-code text-on-surface-variant">
                          {row.user_id ?? '—'}
                        </td>
                        <td className="whitespace-nowrap px-6 py-4">
                          <div className="flex items-center gap-2">
                            <div className="flex h-6 w-6 items-center justify-center rounded bg-surface-container text-primary">
                              <MaterialIcon name={agentIcon(row.agent_name)} size={14} />
                            </div>
                            <span className="text-body-md text-on-surface">
                              {formatAgentName(row.agent_name ?? 'system')}
                            </span>
                          </div>
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between border-t border-border-subtle bg-surface px-6 py-4">
            <span className="text-body-md text-on-surface-variant">
              Showing {rows.length} / {data?.count ?? 0} results
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
