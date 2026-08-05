import { api } from '../../api/client'
import { MaterialIcon } from '../../components/ui/MaterialIcon'
import { useAsync } from '../../hooks/useAsync'
import { formatAgentName } from '../../lib/format'

const tagStyles = [
  'bg-slate-200 text-on-primary-container',
  'bg-blue-100 text-blue-800',
  'bg-green-100 text-green-800',
  'bg-purple-100 text-purple-800',
  'bg-amber-100 text-amber-800',
]

function providerLetter(provider: string): string {
  return provider.charAt(0).toUpperCase()
}

export function ModelsPage() {
  const { data, loading, error, reload } = useAsync(() => api.models(), [])

  const catalog = data?.catalog ?? []
  const agents = data ? Object.entries(data.agents) : []
  const pipeline = data ? Object.entries(data.pipeline) : []

  const sourceCounts: Record<string, number> = {}
  for (const [, cfg] of agents) {
    sourceCounts[cfg.source] = (sourceCounts[cfg.source] ?? 0) + 1
  }
  for (const [, cfg] of pipeline) {
    sourceCounts[cfg.source] = (sourceCounts[cfg.source] ?? 0) + 1
  }
  const totalSources = Object.values(sourceCounts).reduce((a, b) => a + b, 0) || 1
  const usage = Object.entries(sourceCounts).map(([label, count]) => ({
    label,
    pct: Math.round((count / totalSources) * 100),
    color: label.includes('azure') ? 'bg-blue-500' : label.includes('openrouter') ? 'bg-orange-500' : 'bg-purple-500',
  }))

  return (
    <div className="p-margin-page">
      <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="mb-2 text-display-lg text-primary">Model &amp; Agent Catalog</h1>
          <p className="text-body-lg text-on-surface-variant">
            Manage and monitor LLM configuration and how models are assigned to system agents. Read-only mode.
          </p>
        </div>
        <button
          type="button"
          onClick={reload}
          disabled={loading}
          className="flex items-center gap-2 rounded-lg border border-border-subtle px-4 py-2 text-sm font-medium hover:bg-surface-container-high disabled:opacity-50"
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

      <div className="mb-8 flex flex-col items-start justify-between gap-4 rounded-xl border border-border-subtle bg-surface-container-low p-4 sm:flex-row sm:items-center">
        <div className="flex items-center gap-4">
          <div
            className={`flex h-10 w-10 items-center justify-center rounded-full bg-surface-container-high ${
              data?.llm_enabled ? 'text-status-success' : 'text-status-warning'
            }`}
          >
            <MaterialIcon name={data?.llm_enabled ? 'check_circle' : 'warning'} filled />
          </div>
          <div>
            <h3 className="text-headline-sm text-on-surface">
              System API Status: {data?.llm_enabled ? 'Healthy' : 'LLM not configured'}
            </h3>
            <p className="text-body-md text-on-surface-variant">
              {data?.llm_enabled
                ? `${catalog.length} models in catalog · ${agents.length} agents`
                : 'Configure OPENROUTER_API_KEY or OPENAI_API_KEY'}
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="flex flex-col overflow-hidden rounded-xl border border-border-subtle bg-surface shadow-sm xl:col-span-2">
          <div className="flex items-center justify-between border-b border-border-subtle bg-surface-bright p-5">
            <div className="flex items-center gap-2">
              <MaterialIcon name="dns" className="text-outline" />
              <h2 className="text-headline-sm text-primary">Available Models</h2>
            </div>
            <span className="rounded bg-surface-container-high px-2 py-1 text-xs font-medium text-on-surface-variant">
              Read-Only
            </span>
          </div>
          <div className="flex-1 overflow-x-auto">
            {loading ? (
              <p className="p-6 text-on-surface-variant">Loading…</p>
            ) : catalog.length === 0 ? (
              <p className="p-6 text-on-surface-variant">No models</p>
            ) : (
              <table className="w-full border-collapse text-left">
                <thead>
                  <tr className="border-b border-border-subtle bg-surface-container-low">
                    <th className="px-5 py-3 font-label-md font-semibold text-on-surface-variant">Provider</th>
                    <th className="px-5 py-3 font-label-md font-semibold text-on-surface-variant">Model ID</th>
                    <th className="px-5 py-3 font-label-md font-semibold text-on-surface-variant">Ref</th>
                    <th className="px-5 py-3 font-label-md font-semibold text-on-surface-variant">Tags / Capabilities</th>
                    <th className="px-5 py-3 text-right font-label-md font-semibold text-on-surface-variant">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-subtle">
                  {catalog.map((m) => (
                    <tr key={m.ref} className="transition-colors hover:bg-surface-bright">
                      <td className="px-5 py-3">
                        <div className="flex items-center gap-2">
                          <div className="flex h-6 w-6 items-center justify-center rounded bg-slate-100">
                            {providerLetter(m.provider)}
                          </div>
                          <span className="font-medium text-primary">{m.provider}</span>
                        </div>
                      </td>
                      <td className="px-5 py-3 font-body-code text-body-code text-on-surface-variant">{m.model_id}</td>
                      <td className="px-5 py-3 text-on-surface-variant">{m.ref}</td>
                      <td className="px-5 py-3">
                        <div className="flex flex-wrap gap-1">
                          {m.tags.map((tag) => (
                            <span
                              key={tag}
                              className="rounded-full border border-border-subtle bg-surface-container-high px-2 py-0.5 text-xs font-medium text-on-surface"
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="px-5 py-3 text-right">
                        <span className="inline-flex items-center gap-1 text-sm font-medium text-status-success">
                          <span className="h-2 w-2 rounded-full bg-status-success" />
                          Ready
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        <div className="flex flex-col gap-6 xl:col-span-1">
          <div className="rounded-xl border border-border-subtle bg-surface p-5 shadow-sm">
            <div className="mb-4 flex items-center gap-2">
              <MaterialIcon name="hub" className="text-outline" />
              <h2 className="text-headline-sm text-primary">Agent Assignments</h2>
            </div>
            <div className="space-y-4">
              {loading ? (
                <p className="text-on-surface-variant">Loading…</p>
              ) : agents.length === 0 ? (
                <p className="text-on-surface-variant">No agents</p>
              ) : (
                agents.map(([id, cfg], i) => (
                  <div key={id} className="rounded-lg border border-border-subtle bg-surface-bright p-3">
                    <div className="mb-2 flex items-start justify-between">
                      <div className="flex items-center gap-2">
                        <span
                          className={`rounded px-2 py-1 text-xs font-semibold uppercase tracking-wider ${tagStyles[i % tagStyles.length]}`}
                        >
                          {id}
                        </span>
                        <span className="font-label-md font-semibold">{formatAgentName(id)}</span>
                      </div>
                      <MaterialIcon name="link" size={14} className="text-on-surface-variant" />
                    </div>
                    <div className="flex items-center gap-2 rounded bg-surface-container-low p-2 text-sm text-on-surface-variant">
                      <MaterialIcon name="memory" size={16} />
                      <span className="font-body-code text-xs">{cfg.model}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {pipeline.length > 0 && (
            <div className="rounded-xl border border-border-subtle bg-surface p-5 shadow-sm">
              <h3 className="mb-3 text-headline-sm text-primary">Pipeline</h3>
              <div className="space-y-2">
                {pipeline.map(([name, cfg]) => (
                  <div key={name} className="flex justify-between text-body-md">
                    <span className="text-on-surface-variant">{name}</span>
                    <span className="font-body-code text-xs text-primary">{cfg.model}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {usage.length > 0 && (
            <div className="relative overflow-hidden rounded-xl border border-border-subtle bg-surface p-5 shadow-sm">
              <h3 className="relative z-10 mb-4 text-headline-sm text-primary">Model source allocation</h3>
              <div className="relative z-10 space-y-3">
                {usage.map((u) => (
                  <div key={u.label}>
                    <div className="mb-1 flex justify-between text-sm">
                      <span className="text-on-surface-variant">{u.label}</span>
                      <span className="font-medium">{u.pct}%</span>
                    </div>
                    <div className="h-2 w-full rounded-full bg-surface-container-high">
                      <div className={`h-2 rounded-full ${u.color}`} style={{ width: `${u.pct}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
