import { Link } from 'react-router-dom'
import { api } from '../../api/client'
import type { AuditRecord } from '../../api/types'
import { MaterialIcon } from '../../components/ui/MaterialIcon'
import { StarRating } from '../../components/ui/StarRating'
import { useAsync } from '../../hooks/useAsync'
import { formatAgentName, formatCount, formatDateTime, formatRelativeTime, truncate } from '../../lib/format'

const capabilityMeta = [
  { key: 'llm' as const, label: 'Mô hình Ngôn ngữ (LLM)', icon: 'memory' },
  { key: 'embeddings' as const, label: 'Embeddings', icon: 'schema' },
  { key: 'web_search' as const, label: 'Web Search', icon: 'language', web: true },
]

function auditLevel(action: string): { level: string; icon: string; color: string; error?: boolean } {
  if (action.includes('error')) {
    return { level: 'ERROR', icon: 'error', color: 'text-status-error', error: true }
  }
  if (action.includes('warn')) {
    return { level: 'WARN', icon: 'warning', color: 'text-status-warning' }
  }
  return { level: 'INFO', icon: 'check_circle', color: 'text-status-success' }
}

function auditMessage(row: AuditRecord): string {
  const payload = row.payload ?? {}
  if (row.action === 'chat_start') {
    const preview = payload.message_preview as string | undefined
    return preview ? `Bắt đầu chat: ${preview}` : 'Bắt đầu phiên chat'
  }
  if (row.action === 'chat_complete') {
    const workers = payload.worker_count as number | undefined
    return `Hoàn tất chat${workers != null ? ` (${workers} worker)` : ''}`
  }
  if (row.action === 'chat_error') {
    return `Lỗi chat: ${(payload.error as string) ?? 'unknown'}`
  }
  return row.action
}

export function DashboardPage() {
  const { data, loading, error, reload } = useAsync(() => api.adminOverview(), [])

  const kpis = data
    ? [
        {
          label: 'Tài liệu kiến thức',
          value: formatCount(data.counts.knowledge_documents),
          trend: `${formatCount(data.counts.knowledge_with_embedding)} có embedding`,
          up: true,
          to: '/admin/knowledge',
        },
        {
          label: 'Phản hồi người dùng',
          value: formatCount(data.counts.feedback),
          trend: `${formatCount(data.counts.feedback_rated)} đã đánh giá`,
          up: true,
          to: '/admin/feedback',
        },
        {
          label: 'Sự kiện kiểm tra (Audit)',
          value: formatCount(data.counts.audit_log),
          trend: 'Từ database',
          up: false,
          to: '/admin/audit',
        },
      ]
    : []

  return (
    <div className="mx-auto max-w-[1200px] space-y-8 p-margin-page">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-display-lg font-display-lg text-primary">Tổng quan hệ thống</h1>
          <p className="text-body-lg text-on-surface-variant">
            Giám sát hiệu suất và trạng thái các mô hình Agent AI.
            {data?.version && <span className="ml-2 text-label-sm">v{data.version}</span>}
          </p>
        </div>
        <button
          type="button"
          onClick={reload}
          disabled={loading}
          className="flex items-center gap-2 rounded-lg border border-border-subtle px-4 py-2 text-label-md text-primary hover:bg-surface-container-low disabled:opacity-50"
        >
          <MaterialIcon name="refresh" size={18} className={loading ? 'animate-spin' : ''} />
          Làm mới
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-error/30 bg-error-container/30 px-4 py-3 text-body-md text-on-error-container">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {capabilityMeta.map((cap) => {
          const enabled = data?.capabilities[cap.key] ?? false
          return (
            <div
              key={cap.key}
              className="flex items-center justify-between rounded-xl border border-border-subtle bg-surface p-5 shadow-sm"
            >
              <div className="flex items-center gap-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-surface-container-high text-secondary">
                  <MaterialIcon name={cap.icon} className={cap.web ? 'text-citation-web' : ''} />
                </div>
                <div>
                  <h3 className="text-label-md uppercase tracking-wider text-on-surface-variant">{cap.label}</h3>
                  <p className="mt-1 text-headline-sm text-primary">{enabled ? 'Connected' : 'Not configured'}</p>
                </div>
              </div>
              <div
                className={`h-3 w-3 rounded-full shadow-[0_0_8px_rgba(16,185,129,0.4)] ${
                  enabled ? 'bg-status-success' : 'bg-outline-variant'
                }`}
              />
            </div>
          )
        })}
      </div>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
        {kpis.map((kpi) => (
          <Link
            key={kpi.label}
            to={kpi.to}
            className="group relative overflow-hidden rounded-xl border border-border-subtle bg-surface p-6 transition-shadow hover:shadow-md"
          >
            <div className="absolute -right-6 -top-6 h-24 w-24 rounded-full bg-surface-container opacity-50 transition-transform group-hover:scale-110" />
            <p className="relative z-10 text-label-md text-on-surface-variant">{kpi.label}</p>
            <p className="relative z-10 mt-2 text-display-lg text-primary">{loading ? '…' : kpi.value}</p>
            <div
              className={`relative z-10 mt-4 flex items-center gap-2 text-label-sm ${
                kpi.up ? 'text-status-success' : 'text-status-warning'
              }`}
            >
              <MaterialIcon name={kpi.up ? 'trending_up' : 'trending_flat'} size={16} />
              <span>{kpi.trend}</span>
            </div>
          </Link>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-6 pb-12 lg:grid-cols-2">
        <div className="flex h-[400px] flex-col rounded-xl border border-border-subtle bg-surface">
          <div className="flex items-center justify-between rounded-t-xl border-b border-border-subtle bg-surface-container-lowest px-6 py-4">
            <h3 className="text-headline-sm text-primary">Phản hồi gần đây</h3>
            <Link to="/admin/feedback" className="text-label-md text-secondary hover:text-secondary-container">
              Xem tất cả
            </Link>
          </div>
          <div className="flex-1 overflow-auto p-4">
            {loading ? (
              <p className="text-body-md text-on-surface-variant">Đang tải…</p>
            ) : !data?.recent_feedback.length ? (
              <p className="text-body-md text-on-surface-variant">Chưa có phản hồi</p>
            ) : (
              <table className="w-full border-collapse text-left">
                <thead>
                  <tr className="border-b border-border-subtle">
                    <th className="px-3 py-2 text-label-sm text-on-surface-variant">Câu hỏi</th>
                    <th className="px-3 py-2 text-label-sm text-on-surface-variant">Đánh giá</th>
                    <th className="px-3 py-2 text-label-sm text-on-surface-variant">Thời gian</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_feedback.map((row) => (
                    <tr
                      key={row.trace_id}
                      className="group cursor-pointer border-b border-border-subtle transition-colors last:border-0 hover:bg-surface-container-low"
                    >
                      <td className="px-3 py-3">
                        <span className="text-body-md text-primary">{truncate(row.user_message, 50)}</span>
                      </td>
                      <td className="px-3 py-3">
                        <StarRating rating={row.rating ?? 0} />
                      </td>
                      <td className="px-3 py-3 text-label-sm text-on-surface-variant">
                        {formatRelativeTime(row.created_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        <div className="flex h-[400px] flex-col rounded-xl border border-border-subtle bg-surface">
          <div className="flex items-center justify-between rounded-t-xl border-b border-border-subtle bg-surface-container-lowest px-6 py-4">
            <h3 className="text-headline-sm text-primary">Nhật ký hệ thống</h3>
            <Link to="/admin/audit" className="flex items-center gap-1 text-label-md text-secondary hover:text-secondary-container">
              Xem audit <MaterialIcon name="filter_list" size={14} />
            </Link>
          </div>
          <div className="flex-1 overflow-auto p-4">
            {loading ? (
              <p className="text-body-md text-on-surface-variant">Đang tải…</p>
            ) : !data?.recent_audit.length ? (
              <p className="text-body-md text-on-surface-variant">Chưa có sự kiện audit</p>
            ) : (
              <ul className="space-y-3 font-body-code text-body-code">
                {data.recent_audit.map((log) => {
                  const meta = auditLevel(log.action)
                  return (
                    <li
                      key={`${log.id ?? log.trace_id}-${log.action}-${log.created_at}`}
                      className={`flex items-start gap-3 rounded p-2 transition-colors hover:bg-surface-container-low ${
                        meta.error ? 'bg-error-container/20 hover:bg-error-container/40' : ''
                      }`}
                    >
                      <MaterialIcon name={meta.icon} className={`mt-0.5 ${meta.color}`} />
                      <div>
                        <div className="flex items-center gap-2">
                          <span className={`font-bold ${meta.color}`}>[{meta.level}]</span>
                          <span className="text-[12px] text-outline">{formatDateTime(log.created_at)}</span>
                          {log.agent_name && (
                            <span className="text-[12px] text-on-surface-variant">
                              · {formatAgentName(log.agent_name)}
                            </span>
                          )}
                        </div>
                        <span className="mt-1 block text-primary">{auditMessage(log)}</span>
                      </div>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
