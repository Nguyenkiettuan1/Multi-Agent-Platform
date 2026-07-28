import { useMemo, useState } from 'react'
import { api } from '../../api/client'
import type { AuditRecord } from '../../api/types'
import { MaterialIcon } from '../../components/ui/MaterialIcon'
import { useAsync } from '../../hooks/useAsync'
import { formatDateTime } from '../../lib/format'

type LogLevel = 'ERROR' | 'WARN' | 'INFO' | 'DEBUG'

type LogEntry = {
  id: string
  level: LogLevel
  timestamp: string
  component: string
  message: string
  details?: string
}

const levelStyles: Record<LogLevel, string> = {
  ERROR: 'bg-error-container text-on-error-container border-error/20',
  WARN: 'bg-[#FEF3C7] text-[#92400E] border-[#F59E0B]/30',
  INFO: 'bg-surface-container-highest text-on-surface border-outline-variant/50',
  DEBUG: 'bg-surface-variant text-on-surface-variant border-outline-variant/50',
}

function auditToLog(row: AuditRecord): LogEntry {
  const isError = row.action.includes('error')
  const level: LogLevel = isError ? 'ERROR' : row.action.includes('warn') ? 'WARN' : 'INFO'
  const payload = row.payload ?? {}
  let message = row.action
  if (row.action === 'chat_start') {
    message = `Chat started — ${(payload.message_preview as string) ?? ''}`
  } else if (row.action === 'chat_complete') {
    message = `Chat completed — workers: ${payload.worker_count ?? '?'}`
  } else if (row.action === 'chat_error') {
    message = `Chat error — ${(payload.error as string) ?? 'unknown'}`
  }

  return {
    id: String(row.id ?? `${row.trace_id}-${row.action}`),
    level,
    timestamp: formatDateTime(row.created_at),
    component: row.agent_name ?? 'workflow',
    message,
    details: row.sql_executed
      ? `SQL: ${row.sql_executed}\nTrace: ${row.trace_id}`
      : `Trace: ${row.trace_id}\nUser: ${row.user_id ?? '—'}`,
  }
}

export function LogsPage() {
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [levelFilter, setLevelFilter] = useState<LogLevel | 'ALL'>('ALL')

  const { data, loading, error, reload } = useAsync(() => api.adminAudit({ limit: 100 }), [])

  const logs = useMemo(() => {
    const items = (data?.items ?? []).map(auditToLog)
    return items.filter((log) => {
      if (levelFilter !== 'ALL' && log.level !== levelFilter) return false
      if (!search.trim()) return true
      const q = search.toLowerCase()
      return (
        log.message.toLowerCase().includes(q) ||
        log.component.toLowerCase().includes(q) ||
        (log.details ?? '').toLowerCase().includes(q)
      )
    })
  }, [data?.items, levelFilter, search])

  return (
    <div className="flex h-[calc(100vh-64px)] flex-col overflow-hidden">
      <div className="shrink-0 border-b border-border-subtle bg-surface-container-lowest px-margin-page py-6">
        <div className="mb-6 flex flex-col justify-between gap-4 md:flex-row md:items-center">
          <div>
            <h1 className="text-display-lg text-on-surface">System Logs</h1>
            <p className="mt-1 text-body-md text-on-surface-variant">
              Sự kiện audit từ backend (chat_start, chat_complete, chat_error).
            </p>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={reload}
              disabled={loading}
              className="flex items-center gap-2 rounded bg-primary px-4 py-2 text-label-md text-on-primary hover:bg-on-surface disabled:opacity-50"
            >
              <MaterialIcon name="refresh" size={18} className={loading ? 'animate-spin' : ''} />
              Làm mới
            </button>
          </div>
        </div>

        {error && (
          <div className="mb-4 rounded-lg border border-error/30 bg-error-container/30 px-4 py-3 text-body-md text-on-error-container">
            {error}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3">
          <div className="relative min-w-[200px] max-w-md flex-1">
            <MaterialIcon name="search" className="absolute left-3 top-1/2 -translate-y-1/2 text-outline" size={20} />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search message, trace ID..."
              className="w-full rounded-md border border-outline-variant bg-surface-container-lowest py-2 pr-4 pl-9 text-body-md text-on-surface placeholder:text-outline focus:border-secondary focus:ring-1 focus:ring-secondary focus:outline-none"
            />
          </div>
          <select
            value={levelFilter}
            onChange={(e) => setLevelFilter(e.target.value as LogLevel | 'ALL')}
            className="appearance-none rounded-md border border-outline-variant bg-surface-container-lowest py-2 pr-10 pl-4 text-label-md text-on-surface focus:border-secondary focus:outline-none"
          >
            <option value="ALL">All Levels</option>
            <option value="ERROR">ERROR</option>
            <option value="WARN">WARN</option>
            <option value="INFO">INFO</option>
          </select>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-margin-page">
        <div className="flex h-full flex-col overflow-hidden rounded-lg border border-border-subtle bg-surface-container-lowest shadow-sm">
          <div className="sticky top-0 z-10 grid grid-cols-[160px_100px_180px_1fr] gap-4 border-b border-border-subtle bg-surface-sidebar p-4 text-label-sm uppercase tracking-wider text-on-surface-variant">
            <div>Timestamp</div>
            <div>Level</div>
            <div>Component</div>
            <div>Message / Details</div>
          </div>
          <div className="flex-1 overflow-y-auto font-body-code text-body-code">
            {loading ? (
              <p className="p-6 text-on-surface-variant">Đang tải…</p>
            ) : logs.length === 0 ? (
              <p className="p-6 text-on-surface-variant">Không có log</p>
            ) : (
              logs.map((log) => (
                <div
                  key={log.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => setExpandedId(expandedId === log.id ? null : log.id)}
                  onKeyDown={(e) => e.key === 'Enter' && setExpandedId(expandedId === log.id ? null : log.id)}
                  className="grid cursor-pointer grid-cols-[160px_100px_180px_1fr] gap-4 border-b border-border-subtle p-4 transition-colors hover:bg-surface-container-low"
                >
                  <div className="pt-1 text-on-surface-variant">{log.timestamp}</div>
                  <div>
                    <span className={`inline-flex items-center rounded border px-2 py-0.5 text-[11px] font-semibold ${levelStyles[log.level]}`}>
                      {log.level}
                    </span>
                  </div>
                  <div className="pt-1 text-on-surface">{log.component}</div>
                  <div className="flex flex-col gap-2">
                    <div
                      className={
                        log.level === 'ERROR'
                          ? 'font-medium text-error'
                          : log.level === 'WARN'
                            ? 'font-medium text-status-warning'
                            : 'text-on-surface'
                      }
                    >
                      {log.message}
                    </div>
                    {log.details && expandedId === log.id && (
                      <div className="rounded border border-outline-variant/30 bg-surface-container p-3 text-[13px] whitespace-pre text-on-surface-variant">
                        {log.details}
                      </div>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
          <div className="flex items-center justify-between border-t border-border-subtle bg-surface-container-lowest p-4 text-on-surface-variant">
            <span className="text-body-md">
              Hiển thị {logs.length} / {data?.count ?? 0} entries
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
