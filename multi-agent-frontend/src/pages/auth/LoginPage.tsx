import { useId, useState, type FormEvent } from 'react'
import { Navigate, useSearchParams } from 'react-router-dom'
import { ApiError } from '../../api/client'
import { useAuth } from '../../auth/AuthContext'
import { loginErrorMessage, safeNextPath } from '../../lib/auth'

const inputClass =
  'w-full rounded-lg border border-border-subtle bg-surface px-3 py-2 text-body-lg focus:border-secondary focus:ring-1 focus:ring-secondary focus:outline-none'

export function LoginPage() {
  const { state, login } = useAuth()
  const [params] = useSearchParams()
  const emailId = useId()
  const passwordId = useId()
  const errorId = useId()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Covers both a successful sign-in (state flips) and opening /login while already signed in.
  if (state.status === 'authenticated') {
    return <Navigate to={safeNextPath(params.get('next'))} replace />
  }

  // The submit button uses aria-disabled (not disabled) while busy: a disabled button drops keyboard focus.
  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      await login(email.trim(), password)
    } catch (err) {
      setError(err instanceof ApiError ? loginErrorMessage(err.status, err.retryAfter) : loginErrorMessage(undefined))
      setBusy(false)
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-surface px-4 py-10 text-on-surface">
      <div className="w-full max-w-sm">
        <h1 className="mb-2 text-display-lg text-primary">Sign in</h1>
        <p className="mb-6 text-body-lg text-on-surface-variant">Sign in to Agent Workspace.</p>

        <form onSubmit={handleSubmit} className="rounded-xl border border-border-subtle bg-surface-container-lowest p-6">
          <div className="mb-4">
            <label htmlFor={emailId} className="mb-2 block text-label-sm text-on-surface-variant">
              Email
            </label>
            <input
              id={emailId}
              type="email"
              name="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              aria-describedby={error ? errorId : undefined}
              className={inputClass}
            />
          </div>
          <div className="mb-4">
            <label htmlFor={passwordId} className="mb-2 block text-label-sm text-on-surface-variant">
              Password
            </label>
            <input
              id={passwordId}
              type="password"
              name="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-describedby={error ? errorId : undefined}
              className={inputClass}
            />
          </div>

          {/* Region stays mounted so a message appearing inside it is announced. */}
          <div id={errorId} role="alert" className="mb-4 text-body-md text-error empty:hidden">
            {error}
          </div>

          <button
            type="submit"
            aria-disabled={busy}
            className="w-full rounded-lg bg-primary px-4 py-2 text-label-md text-on-primary hover:bg-inverse-surface aria-disabled:cursor-not-allowed aria-disabled:opacity-60"
          >
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <p className="mt-4 text-label-sm text-on-surface-variant">Single sign-on coming later.</p>
      </div>
    </main>
  )
}
