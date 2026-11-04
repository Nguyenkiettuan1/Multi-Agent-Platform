import { useEffect, useId, useState } from 'react'
import { api } from '../../api/client'
import type { HealthResponse } from '../../api/types'
import { getApiKey, setApiKey } from '../../lib/storage'

// Both selects stay visible but inert until theming / i18n exist; disabled text is on-surface-variant,
// slightly lighter than normal to signal inactive while staying readable (8.52:1).
// 16px (text-body-lg) on form fields: iOS Safari zooms the page on focus below that.
const selectClass =
  'w-full rounded-lg border border-border-subtle bg-surface px-3 py-2 text-body-lg focus:border-secondary focus:ring-1 focus:ring-secondary focus:outline-none disabled:cursor-not-allowed disabled:bg-surface-container-low disabled:text-on-surface-variant'

// Status text uses primary (black) because the status-success/warning tokens fail 4.5:1 as text;
// the colored dot is decorative and the word carries the meaning.
function StatusValue({ tone, children }: { tone: 'success' | 'warning'; children: string }) {
  return (
    <dd className="flex items-center gap-2 text-primary">
      <span
        aria-hidden="true"
        className={`size-2 rounded-full ${tone === 'success' ? 'bg-status-success' : 'bg-status-warning'}`}
      />
      {children}
    </dd>
  )
}

export function SettingsPage() {
  const themeId = useId()
  const languageId = useId()
  const apiKeyId = useId()
  const [apiKey, setApiKeyInput] = useState(getApiKey())
  const [saved, setSaved] = useState(false)
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [healthError, setHealthError] = useState<string | null>(null)

  useEffect(() => {
    api
      .health()
      .then(setHealth)
      .catch((err: unknown) => setHealthError(err instanceof Error ? err.message : 'Unable to connect to API'))
  }, [saved])

  const handleSave = () => {
    setApiKey(apiKey)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div className="mx-auto max-w-2xl p-margin-page">
      <h1 className="mb-2 text-display-lg text-primary">Settings</h1>
      <p className="mb-8 text-body-lg text-on-surface-variant">Customize your Agent Workspace experience.</p>

      <div className="space-y-8">
        <section className="rounded-xl border border-border-subtle bg-surface p-6">
          <h2 className="mb-4 text-headline-sm text-primary">Appearance</h2>
          <div className="space-y-4">
            <div>
              <label htmlFor={themeId} className="mb-2 block text-label-sm text-on-surface-variant">Theme</label>
              <select id={themeId} disabled aria-describedby={`${themeId}-note`} className={selectClass}>
                <option>Light</option>
                <option>Dark</option>
                <option>System</option>
              </select>
              <p id={`${themeId}-note`} className="mt-1 text-label-sm text-on-surface-variant">Coming soon</p>
            </div>
            <div>
              <label htmlFor={languageId} className="mb-2 block text-label-sm text-on-surface-variant">Language</label>
              <select id={languageId} disabled aria-describedby={`${languageId}-note`} className={selectClass}>
                <option>Vietnamese</option>
                <option>English</option>
              </select>
              <p id={`${languageId}-note`} className="mt-1 text-label-sm text-on-surface-variant">Coming soon</p>
            </div>
          </div>
        </section>

        <section className="rounded-xl border border-border-subtle bg-surface p-6">
          <h2 className="mb-4 text-headline-sm text-primary">API Key (dev)</h2>
          <label htmlFor={apiKeyId} className="mb-2 block text-label-sm text-on-surface-variant">API key</label>
          <input
            id={apiKeyId}
            type="password"
            value={apiKey}
            onChange={(e) => setApiKeyInput(e.target.value)}
            placeholder="X-API-Key"
            className="mb-4 w-full rounded-lg border border-border-subtle bg-surface px-3 py-2 text-body-lg focus:border-secondary focus:ring-1 focus:ring-secondary focus:outline-none"
          />
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={handleSave}
              className="rounded-lg bg-primary px-4 py-2 text-label-md text-on-primary hover:bg-inverse-surface"
            >
              Save
            </button>
            {/* Region stays mounted so the text change is announced; a region inserted with its content is often missed. */}
            <span role="status" className="text-label-md text-primary">
              {saved ? 'Saved' : ''}
            </span>
          </div>
        </section>

        <section className="rounded-xl border border-border-subtle bg-surface p-6">
          <h2 className="mb-4 text-headline-sm text-primary">About</h2>
          {health ? (
            <dl className="space-y-2 text-body-md text-on-surface-variant">
              <div className="flex justify-between">
                <dt>Service</dt>
                <dd className="text-primary">{health.service}</dd>
              </div>
              <div className="flex justify-between">
                <dt>Version</dt>
                <dd className="text-primary">{health.version}</dd>
              </div>
              <div className="flex justify-between">
                <dt>Status</dt>
                <StatusValue tone="success">{health.status}</StatusValue>
              </div>
              <div className="flex justify-between">
                <dt>Graph</dt>
                <StatusValue tone={health.graph_ready ? 'success' : 'warning'}>
                  {health.graph_ready ? 'Ready' : 'Not ready'}
                </StatusValue>
              </div>
            </dl>
          ) : (
            <p className="text-body-md text-on-surface-variant">
              {healthError ?? 'Loading system info…'}
            </p>
          )}
        </section>
      </div>
    </div>
  )
}
