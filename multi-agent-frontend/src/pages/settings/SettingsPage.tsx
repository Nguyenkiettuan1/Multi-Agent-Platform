import { useEffect, useId, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError, api } from '../../api/client'
import type { HealthResponse } from '../../api/types'
import { useAuth } from '../../auth/AuthContext'
import { PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, changePasswordErrorMessage, passwordProblem } from '../../lib/auth'

// Both selects stay visible but inert until theming / i18n exist; disabled text is on-surface-variant,
// slightly lighter than normal to signal inactive while staying readable (8.52:1).
// 16px (text-body-lg) on form fields: iOS Safari zooms the page on focus below that.
const selectClass =
  'w-full rounded-lg border border-border-subtle bg-surface px-3 py-2 text-body-lg focus:border-secondary focus:ring-1 focus:ring-secondary focus:outline-none disabled:cursor-not-allowed disabled:bg-surface-container-low disabled:text-on-surface-variant'

const inputClass =
  'w-full rounded-lg border border-border-subtle bg-surface px-3 py-2 text-body-lg focus:border-secondary focus:ring-1 focus:ring-secondary focus:outline-none'

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
  const currentId = useId()
  const newId = useId()
  const confirmId = useId()
  const hintId = useId()
  const errorId = useId()
  const navigate = useNavigate()
  const { state, refresh } = useAuth()
  const mustChange = state.status === 'authenticated' && state.user.must_change_password
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [passwordBusy, setPasswordBusy] = useState(false)
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [passwordChanged, setPasswordChanged] = useState(false)
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [healthError, setHealthError] = useState<string | null>(null)

  useEffect(() => {
    api
      .health()
      .then(setHealth)
      .catch((err: unknown) => setHealthError(err instanceof Error ? err.message : 'Unable to connect to API'))
  }, [])

  const handleChangePassword = async (e: FormEvent) => {
    e.preventDefault()
    if (passwordBusy) return
    setPasswordChanged(false)
    const problem = passwordProblem(currentPassword, newPassword, confirmPassword)
    if (problem) {
      setPasswordError(problem)
      return
    }
    setPasswordBusy(true)
    setPasswordError(null)
    try {
      await api.changePassword(currentPassword, newPassword)
    } catch (err) {
      setPasswordError(
        err instanceof ApiError
          ? changePasswordErrorMessage(err.status, err.message, err.retryAfter)
          : changePasswordErrorMessage(undefined, ''),
      )
      setPasswordBusy(false)
      return
    }

    // The password is changed from here on, whatever happens to the follow-up refresh.
    setCurrentPassword('')
    setNewPassword('')
    setConfirmPassword('')
    setPasswordChanged(true)
    setPasswordBusy(false)
    try {
      // Clears must_change_password in the guard's view; a blocked user is then sent on to chat.
      await refresh()
      if (mustChange) navigate('/chat', { replace: true })
    } catch {
      setPasswordError('Password changed, but your account could not be reloaded. Reload the page to continue.')
    }
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
          <h2 className="mb-4 text-headline-sm text-primary">Password</h2>
          {mustChange && (
            <p className="mb-4 rounded-lg bg-surface-container-low px-3 py-2 text-body-md text-primary">
              Your password was set by an administrator. Choose a new one to start using the workspace.
            </p>
          )}
          <form onSubmit={handleChangePassword}>
            <div className="mb-4">
              <label htmlFor={currentId} className="mb-2 block text-label-sm text-on-surface-variant">Current password</label>
              <input
                id={currentId}
                type="password"
                autoComplete="current-password"
                required
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                aria-describedby={passwordError ? errorId : undefined}
                className={inputClass}
              />
            </div>
            <div className="mb-4">
              <label htmlFor={newId} className="mb-2 block text-label-sm text-on-surface-variant">New password</label>
              <input
                id={newId}
                type="password"
                autoComplete="new-password"
                required
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                aria-describedby={passwordError ? `${hintId} ${errorId}` : hintId}
                className={inputClass}
              />
              <p id={hintId} className="mt-1 text-label-sm text-on-surface-variant">
                {PASSWORD_MIN_LENGTH} to {PASSWORD_MAX_LENGTH} characters.
              </p>
            </div>
            <div className="mb-4">
              <label htmlFor={confirmId} className="mb-2 block text-label-sm text-on-surface-variant">Confirm new password</label>
              <input
                id={confirmId}
                type="password"
                autoComplete="new-password"
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                aria-describedby={passwordError ? errorId : undefined}
                className={inputClass}
              />
            </div>
            {/* Regions stay mounted so text appearing inside them is announced. */}
            <div id={errorId} role="alert" className="mb-4 text-body-md text-error empty:hidden">
              {passwordError}
            </div>
            <div className="flex items-center gap-3">
              <button
                type="submit"
                aria-disabled={passwordBusy}
                className="rounded-lg bg-primary px-4 py-2 text-label-md text-on-primary hover:bg-inverse-surface aria-disabled:cursor-not-allowed aria-disabled:opacity-60"
              >
                {passwordBusy ? 'Changing…' : 'Change password'}
              </button>
              <span role="status" className="text-label-md text-primary">
                {passwordChanged ? 'Password changed' : ''}
              </span>
            </div>
          </form>
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
