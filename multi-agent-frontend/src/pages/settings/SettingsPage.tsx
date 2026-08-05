import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { HealthResponse } from '../../api/types'
import { getApiKey, setApiKey } from '../../lib/storage'

export function SettingsPage() {
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
              <label className="mb-2 block text-label-sm text-on-surface-variant">Theme</label>
              <select className="w-full rounded-lg border border-border-subtle bg-surface px-3 py-2 text-body-md focus:border-secondary focus:ring-1 focus:ring-secondary focus:outline-none">
                <option>Light</option>
                <option>Dark</option>
                <option>System</option>
              </select>
            </div>
            <div>
              <label className="mb-2 block text-label-sm text-on-surface-variant">Language</label>
              <select className="w-full rounded-lg border border-border-subtle bg-surface px-3 py-2 text-body-md focus:border-secondary focus:ring-1 focus:ring-secondary focus:outline-none">
                <option>Vietnamese</option>
                <option>English</option>
              </select>
            </div>
          </div>
        </section>

        <section className="rounded-xl border border-border-subtle bg-surface p-6">
          <h2 className="mb-4 text-headline-sm text-primary">API Key (dev)</h2>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKeyInput(e.target.value)}
            placeholder="X-API-Key"
            className="mb-4 w-full rounded-lg border border-border-subtle bg-surface px-3 py-2 text-body-md focus:border-secondary focus:ring-1 focus:ring-secondary focus:outline-none"
          />
          <button
            type="button"
            onClick={handleSave}
            className="rounded-lg bg-primary px-4 py-2 text-label-md text-on-primary hover:bg-inverse-surface"
          >
            {saved ? 'Saved' : 'Save'}
          </button>
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
                <dd className="text-status-success">{health.status}</dd>
              </div>
              <div className="flex justify-between">
                <dt>Graph</dt>
                <dd className={health.graph_ready ? 'text-status-success' : 'text-status-warning'}>
                  {health.graph_ready ? 'Ready' : 'Not ready'}
                </dd>
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
