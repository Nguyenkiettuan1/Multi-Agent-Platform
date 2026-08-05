import { useState } from 'react'
import { api } from '../../api/client'
import { StarRating } from '../../components/ui/StarRating'
import { MaterialIcon } from '../../components/ui/MaterialIcon'
import { useAsync } from '../../hooks/useAsync'
import { formatRelativeTime, formatScore, truncate } from '../../lib/format'

function feedbackStatus(rating: number | null, evalScore: number | null): {
  status: string
  statusType: 'success' | 'warning' | 'neutral'
} {
  if (rating != null && rating >= 4 && evalScore != null && evalScore >= 0.8) {
    return { status: 'High quality', statusType: 'success' }
  }
  if (rating != null && rating <= 2) {
    return { status: 'Needs review', statusType: 'warning' }
  }
  if (rating == null) {
    return { status: 'Not rated', statusType: 'neutral' }
  }
  return { status: 'Recorded', statusType: 'neutral' }
}

export function FeedbackPage() {
  const [minRating, setMinRating] = useState<number | undefined>(undefined)
  const [exporting, setExporting] = useState(false)

  const { data, loading, error, reload } = useAsync(
    () => api.adminFeedback({ limit: 50, min_rating: minRating }),
    [minRating],
  )

  const rows = data?.items ?? []
  const total = data?.count ?? 0

  const handleExport = async () => {
    setExporting(true)
    try {
      const blob = await api.exportFeedback({ min_rating: minRating ?? 4, format: 'jsonl' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'feedback-export.jsonl'
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Export failed')
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="mx-auto max-w-[1400px] p-margin-page">
      <div className="mb-8 flex flex-col items-start justify-between gap-4 md:flex-row md:items-center">
        <div>
          <h1 className="text-display-lg text-primary">Feedback Management</h1>
          <p className="mt-1 text-body-lg text-on-surface-variant">
            Review and analyze user feedback on agent performance.
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
        <div className="mb-6 rounded-lg border border-error/30 bg-error-container/30 px-4 py-3 text-body-md text-on-error-container">
          {error}
        </div>
      )}

      <div className="mb-6 flex flex-col items-center justify-between gap-4 rounded-xl border border-border-subtle bg-surface-container-lowest p-4 sm:flex-row">
        <div className="relative w-full sm:w-48">
          <select
            value={minRating ?? 'all'}
            onChange={(e) => {
              const v = e.target.value
              setMinRating(v === 'all' ? undefined : Number(v))
            }}
            className="w-full appearance-none rounded-lg border border-outline-variant bg-surface-bright px-4 py-2 text-body-md text-on-surface focus:border-secondary focus:ring-1 focus:ring-secondary focus:outline-none"
          >
            <option value="all">Minimum rating: All</option>
            <option value="3">Minimum rating: 3+</option>
            <option value="4">Minimum rating: 4+</option>
            <option value="5">Minimum rating: 5+</option>
          </select>
          <MaterialIcon
            name="expand_more"
            className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-outline-variant"
          />
        </div>
        <button
          type="button"
          disabled={exporting}
          onClick={() => void handleExport()}
          className="flex w-full items-center justify-center gap-2 whitespace-nowrap rounded-lg border border-outline-variant bg-surface-bright px-4 py-2 text-label-md text-on-surface hover:bg-surface-container-low disabled:opacity-50 sm:w-auto"
        >
          <MaterialIcon name="download" size={18} />
          {exporting ? 'Exporting…' : 'Export data'}
        </button>
      </div>

      <div className="overflow-hidden rounded-xl border border-border-subtle bg-surface-container-lowest">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[800px] border-collapse text-left">
            <thead>
              <tr className="border-b border-border-subtle bg-surface-container-low">
                <th className="w-1/4 p-4 text-label-sm font-semibold uppercase tracking-wider text-on-surface-variant">Question</th>
                <th className="w-1/4 p-4 text-label-sm font-semibold uppercase tracking-wider text-on-surface-variant">Agent Response</th>
                <th className="w-[120px] p-4 text-label-sm font-semibold uppercase tracking-wider text-on-surface-variant">Rating</th>
                <th className="w-[100px] p-4 text-label-sm font-semibold uppercase tracking-wider text-on-surface-variant">AI Score</th>
                <th className="w-[150px] p-4 text-label-sm font-semibold uppercase tracking-wider text-on-surface-variant">Status</th>
                <th className="w-[150px] p-4 text-label-sm font-semibold uppercase tracking-wider text-on-surface-variant">Time</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle text-body-md text-on-surface">
              {loading ? (
                <tr>
                  <td colSpan={6} className="p-8 text-center text-on-surface-variant">
                    Loading…
                  </td>
                </tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={6} className="p-8 text-center text-on-surface-variant">
                    No feedback yet
                  </td>
                </tr>
              ) : (
                rows.map((row) => {
                  const { status, statusType } = feedbackStatus(row.rating, row.eval_score)
                  const evalGood = row.eval_score == null || row.eval_score >= 0.7
                  return (
                    <tr key={row.trace_id} className="group cursor-pointer transition-colors hover:bg-surface-container-low">
                      <td className="p-4">
                        <p className="max-w-[250px] truncate text-primary group-hover:text-secondary">
                          {truncate(row.user_message, 60)}
                        </p>
                      </td>
                      <td className="p-4">
                        <p className="max-w-[250px] truncate text-on-surface-variant">{truncate(row.response, 60)}</p>
                      </td>
                      <td className="p-4">
                        <StarRating rating={row.rating ?? 0} />
                      </td>
                      <td className="p-4">
                        <span
                          className={`font-body-code rounded px-2 py-1 text-body-code ${
                            evalGood ? 'bg-surface-container-high' : 'bg-error-container text-on-error-container'
                          }`}
                        >
                          {formatScore(row.eval_score)}
                        </span>
                      </td>
                      <td className="p-4">
                        <span
                          className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-label-sm ${
                            statusType === 'success'
                              ? 'border-outline-variant bg-surface-container-high text-on-surface'
                              : statusType === 'warning'
                                ? 'border-border-subtle bg-surface-container-low text-on-surface-variant'
                                : 'border-border-subtle bg-surface-container-low text-on-surface-variant'
                          }`}
                        >
                          <span
                            className={`h-1.5 w-1.5 rounded-full ${
                              statusType === 'success'
                                ? 'bg-status-success'
                                : statusType === 'warning'
                                  ? 'bg-status-warning'
                                  : 'bg-outline-variant'
                            }`}
                          />
                          {status}
                        </span>
                      </td>
                      <td className="p-4 font-body-code text-body-code text-on-surface-variant">
                        {formatRelativeTime(row.created_at)}
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
        <div className="flex items-center justify-between border-t border-border-subtle bg-surface-container-low px-4 py-3">
          <span className="text-body-md text-on-surface-variant">
            Showing {rows.length} of {total} feedback entries
          </span>
        </div>
      </div>
    </div>
  )
}
