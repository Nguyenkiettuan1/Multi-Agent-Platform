import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { api, ApiError } from '../../api/client'
import type { AdminUser, UserRole } from '../../api/types'
import { useAuth } from '../../auth/AuthContext'
import { MaterialIcon } from '../../components/ui/MaterialIcon'
import { useAsync } from '../../hooks/useAsync'
import { lastValidOffset, pageInfo } from '../../lib/knowledge'
import {
  lastSignInLabel,
  statusLabel,
  userActionError,
  userPasswordProblem,
  validateNewUser,
  type NewUserErrors,
  type UserAction,
  type UserActionError,
  type UserField,
} from '../../lib/users'

const PAGE_SIZE = 25

const headCell = 'px-6 py-4 text-label-sm uppercase tracking-wider text-on-surface-variant'
const inputClass =
  'w-full rounded-lg border border-border-subtle bg-surface px-3 py-2 text-body-md text-on-surface focus:border-secondary focus:ring-1 focus:ring-secondary focus:outline-none aria-invalid:border-error'
const secondaryButton =
  'rounded-lg border border-border-subtle bg-surface px-3 py-1.5 text-label-md text-primary hover:bg-surface-container-low disabled:opacity-50'

function errorOf(action: UserAction, err: unknown): UserActionError {
  const status = err instanceof ApiError ? err.status : undefined
  return userActionError(action, status, err instanceof Error ? err.message : '')
}

function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null
  return (
    <p id={id} className="mt-1 text-label-sm text-error">
      {message}
    </p>
  )
}

function PasswordInput({
  id,
  value,
  onChange,
  error,
  errorId,
  hint,
  initialFocus,
}: {
  id: string
  value: string
  onChange: (value: string) => void
  error?: string
  errorId: string
  hint: string
  /** Marks the field the dialog should focus once it is open (see useModal). */
  initialFocus?: boolean
}) {
  const [shown, setShown] = useState(false)
  return (
    <>
      <div className="flex gap-2">
        <input
          id={id}
          type={shown ? 'text' : 'password'}
          autoComplete="new-password"
          data-autofocus={initialFocus ? '' : undefined}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${errorId} ${id}-hint` : `${id}-hint`}
          className={inputClass}
        />
        <button type="button" onClick={() => setShown((s) => !s)} className={`${secondaryButton} shrink-0`}>
          {shown ? 'Hide password' : 'Show password'}
        </button>
      </div>
      <FieldError id={errorId} message={error} />
      <p id={`${id}-hint`} className="mt-1 text-label-sm text-on-surface-variant">
        {hint}
      </p>
    </>
  )
}

const dialogClass =
  'm-auto w-[min(32rem,calc(100vw-2rem))] rounded-xl border border-border-subtle bg-surface p-0 text-on-surface shadow-xl backdrop:bg-black/40'

/**
 * Shared shell for the two confirm dialogs: native <dialog>.showModal() traps focus, Esc closes and focus
 * returns to the opener. While `busy`, Esc and Cancel are ignored so an in-flight request keeps its dialog.
 */
function useModal(busyRef: { current: boolean }, final: boolean) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const dialog = ref.current
    if (dialog && !dialog.open) dialog.showModal()
    // React's autoFocus runs before showModal(), when the dialog cannot take focus yet.
    dialog?.querySelector<HTMLElement>('[data-autofocus]')?.focus()
  }, [])
  // The confirm button unmounts once retrying cannot help; if it held focus, a modal dialog would be left
  // with focus on <body> and Enter/Space would do nothing. Hand focus to the dismiss button instead.
  useEffect(() => {
    if (final) ref.current?.querySelector<HTMLElement>('[data-dismiss]')?.focus()
  }, [final])
  const handlers = {
    onCancel: (e: { preventDefault: () => void }) => {
      if (busyRef.current) e.preventDefault()
    },
  }
  return { ref, handlers }
}

function Spinner() {
  return (
    <span aria-hidden="true">
      <MaterialIcon name="progress_activity" size={18} className="animate-spin" />
    </span>
  )
}

function LockDialog({
  user,
  onClose,
  onStart,
  onDone,
  onStale,
}: {
  user: AdminUser
  /** Called from the native close event, after the browser has restored focus to the opener. */
  onClose: () => void
  onStart: () => void
  onDone: (updated: AdminUser) => void
  onStale: () => void
}) {
  const locking = user.is_active
  const busyRef = useRef(false)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  // True once retrying cannot help (user gone, or the server refuses on principle): only Close is offered.
  const [final, setFinal] = useState(false)
  const { ref, handlers } = useModal(busyRef, final)

  const confirm = async () => {
    if (busyRef.current) return
    busyRef.current = true
    setBusy(true)
    setFailure(null)
    onStart()
    try {
      const updated = await api.setUserActive(user.id, !user.is_active)
      busyRef.current = false
      onDone(updated)
      ref.current?.close()
    } catch (err) {
      const status = err instanceof ApiError ? err.status : undefined
      setFailure(errorOf('lock', err).message)
      if (status === 404 || status === 409) setFinal(true)
      if (status === 404) onStale()
      busyRef.current = false
      setBusy(false)
    }
  }

  return (
    <dialog
      ref={ref}
      aria-labelledby="lock-user-title"
      aria-describedby="lock-user-body"
      {...handlers}
      onClose={() => {
        if (busyRef.current) {
          if (!ref.current?.open) ref.current?.showModal()
        } else {
          onClose()
        }
      }}
      className={dialogClass}
    >
      <div className="p-6">
        <h2 id="lock-user-title" className="text-title-md font-semibold text-primary">
          {locking ? 'Lock this account?' : 'Unlock this account?'}
        </h2>
        <div id="lock-user-body" className="mt-3 space-y-2 text-body-md text-on-surface-variant">
          <p>
            <strong className="break-words font-semibold text-primary">{user.email}</strong>
            {locking
              ? ' will be signed out everywhere and cannot sign in until you unlock the account.'
              : ' will be able to sign in again.'}
          </p>
        </div>
        {failure && (
          <p
            role="alert"
            className="mt-4 rounded-lg border border-error/30 bg-error-container/30 px-4 py-3 text-body-md text-on-error-container"
          >
            {failure}
          </p>
        )}
        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            data-autofocus=""
            data-dismiss=""
            aria-disabled={busy}
            onClick={() => {
              if (!busyRef.current) ref.current?.close()
            }}
            className="rounded-lg border border-border-subtle bg-surface px-4 py-2 text-label-md text-primary hover:bg-surface-container-low aria-disabled:opacity-50"
          >
            {final ? 'Close' : 'Cancel'}
          </button>
          {!final && (
            <button
              type="button"
              aria-disabled={busy}
              onClick={() => void confirm()}
              className={`flex items-center gap-2 rounded-lg px-4 py-2 text-label-md hover:opacity-90 aria-disabled:cursor-wait aria-disabled:opacity-60 ${
                locking ? 'bg-error text-on-error' : 'bg-primary text-on-primary'
              }`}
            >
              {busy && <Spinner />}
              {busy ? (locking ? 'Locking…' : 'Unlocking…') : failure ? 'Try again' : locking ? 'Lock account' : 'Unlock account'}
            </button>
          )}
        </div>
      </div>
    </dialog>
  )
}

function ResetPasswordDialog({
  user,
  isSelf,
  onClose,
  onStart,
  onDone,
  onStale,
}: {
  user: AdminUser
  isSelf: boolean
  onClose: () => void
  onStart: () => void
  onDone: () => void
  onStale: () => void
}) {
  const busyRef = useRef(false)
  const [busy, setBusy] = useState(false)
  const [password, setPassword] = useState('')
  const [fieldError, setFieldError] = useState<string | undefined>()
  const [failure, setFailure] = useState<string | null>(null)
  const [stale, setStale] = useState(false)
  const { ref, handlers } = useModal(busyRef, stale)
  const ids = useId()
  const inputId = `${ids}-password`
  const errorId = `${ids}-password-error`

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (busyRef.current) return
    const problem = userPasswordProblem(password, user.email)
    if (problem) {
      setFieldError(problem)
      document.getElementById(inputId)?.focus()
      return
    }
    busyRef.current = true
    setBusy(true)
    setFieldError(undefined)
    setFailure(null)
    onStart()
    try {
      await api.resetUserPassword(user.id, password)
      busyRef.current = false
      onDone()
      ref.current?.close()
    } catch (err) {
      const status = err instanceof ApiError ? err.status : undefined
      const { field, message } = errorOf('reset', err)
      if (field) {
        setFieldError(message)
        document.getElementById(inputId)?.focus()
      } else {
        setFailure(message)
      }
      if (status === 404) {
        setStale(true)
        onStale()
      }
      busyRef.current = false
      setBusy(false)
    }
  }

  return (
    <dialog
      ref={ref}
      aria-labelledby={`${ids}-title`}
      aria-describedby={`${ids}-body`}
      {...handlers}
      onClose={() => {
        if (busyRef.current) {
          if (!ref.current?.open) ref.current?.showModal()
        } else {
          onClose()
        }
      }}
      className={dialogClass}
    >
      <form onSubmit={(e) => void submit(e)} noValidate className="p-6">
        <h2 id={`${ids}-title`} className="text-title-md font-semibold text-primary">
          Reset password
        </h2>
        <p id={`${ids}-body`} className="mt-3 text-body-md text-on-surface-variant">
          Set a temporary password for{' '}
          <strong className="break-words font-semibold text-primary">{user.email}</strong>. They are signed out
          everywhere and must choose a new password the next time they sign in. Share the temporary password
          through a private channel.
        </p>
        {isSelf && (
          <p className="mt-3 rounded-lg border border-[#fde68a] bg-[#fffbeb] px-4 py-3 text-body-md text-[#92400e]">
            This is your own account. You will be signed out everywhere and must choose a new password to get
            back in.
          </p>
        )}
        <div className="mt-4">
          <label htmlFor={inputId} className="mb-2 block text-label-sm text-on-surface-variant">
            Temporary password
          </label>
          <PasswordInput
            id={inputId}
            value={password}
            onChange={setPassword}
            error={fieldError}
            errorId={errorId}
            hint="12 to 128 characters, not the email address."
            initialFocus
          />
        </div>
        {failure && (
          <p
            role="alert"
            className="mt-4 rounded-lg border border-error/30 bg-error-container/30 px-4 py-3 text-body-md text-on-error-container"
          >
            {failure}
          </p>
        )}
        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            data-dismiss=""
            aria-disabled={busy}
            onClick={() => {
              if (!busyRef.current) ref.current?.close()
            }}
            className="rounded-lg border border-border-subtle bg-surface px-4 py-2 text-label-md text-primary hover:bg-surface-container-low aria-disabled:opacity-50"
          >
            {stale ? 'Close' : 'Cancel'}
          </button>
          {!stale && (
            <button
              type="submit"
              aria-disabled={busy}
              className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-label-md text-on-primary hover:opacity-90 aria-disabled:cursor-wait aria-disabled:opacity-60"
            >
              {busy && <Spinner />}
              {busy ? 'Resetting…' : 'Reset password'}
            </button>
          )}
        </div>
      </form>
    </dialog>
  )
}

const emptyForm = { email: '', display_name: '', role: 'user' as UserRole, password: '' }

function CreateUserForm({ onStart, onCreated }: { onStart: () => void; onCreated: (email: string) => void }) {
  const ids = useId()
  const [form, setForm] = useState(emptyForm)
  const [errors, setErrors] = useState<NewUserErrors>({})
  const [failure, setFailure] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // Remounts the password field after a create so "Show" does not stay on for the next temporary password.
  const [passwordKey, setPasswordKey] = useState(0)
  const busyRef = useRef(false)
  const emailRef = useRef<HTMLInputElement>(null)

  const idOf = (field: UserField) => `${ids}-${field}`
  const errorIdOf = (field: UserField) => `${ids}-${field}-error`
  const set = <K extends keyof typeof emptyForm>(field: K, value: (typeof emptyForm)[K]) => {
    setForm((f) => ({ ...f, [field]: value }))
    // Clear the message of the field being edited; the others still apply.
    if (field in errors) setErrors((prev) => ({ ...prev, [field]: undefined }))
  }

  const focusFirst = (found: NewUserErrors) => {
    const first = (['email', 'display_name', 'role', 'password'] as const).find((f) => found[f])
    if (first) document.getElementById(idOf(first))?.focus()
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (busyRef.current) return
    const found = validateNewUser(form)
    setErrors(found)
    setFailure(null)
    if (Object.keys(found).length > 0) {
      focusFirst(found)
      return
    }
    busyRef.current = true
    setBusy(true)
    onStart()
    const email = form.email.trim()
    try {
      await api.createUser({ ...form, email, display_name: form.display_name.trim() })
      setForm(emptyForm)
      setPasswordKey((k) => k + 1)
      onCreated(email)
      emailRef.current?.focus()
    } catch (err) {
      const { field, message } = errorOf('create', err)
      if (field) {
        const next = { [field]: message }
        setErrors(next)
        focusFirst(next)
      } else {
        setFailure(message)
      }
    } finally {
      busyRef.current = false
      setBusy(false)
    }
  }

  const describe = (field: UserField) => (errors[field] ? errorIdOf(field) : undefined)
  const label = 'mb-2 block text-label-sm text-on-surface-variant'

  return (
    <form onSubmit={(e) => void submit(e)} noValidate className="mb-8 rounded-xl border border-border-subtle bg-surface p-6">
      <h2 className="text-title-md font-semibold text-primary">Create user</h2>
      <p className="mt-1 text-body-md text-on-surface-variant">
        The temporary password must be changed by the user at their first sign-in.
      </p>
      <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
        <div>
          <label htmlFor={idOf('email')} className={label}>Email</label>
          <input
            ref={emailRef}
            id={idOf('email')}
            type="email"
            autoComplete="off"
            value={form.email}
            onChange={(e) => set('email', e.target.value)}
            aria-invalid={errors.email ? true : undefined}
            aria-describedby={describe('email')}
            className={inputClass}
          />
          <FieldError id={errorIdOf('email')} message={errors.email} />
        </div>
        <div>
          <label htmlFor={idOf('display_name')} className={label}>Display name</label>
          <input
            id={idOf('display_name')}
            type="text"
            autoComplete="off"
            value={form.display_name}
            onChange={(e) => set('display_name', e.target.value)}
            aria-invalid={errors.display_name ? true : undefined}
            aria-describedby={describe('display_name')}
            className={inputClass}
          />
          <FieldError id={errorIdOf('display_name')} message={errors.display_name} />
        </div>
        <div>
          <label htmlFor={idOf('role')} className={label}>Role</label>
          <select
            id={idOf('role')}
            value={form.role}
            onChange={(e) => set('role', e.target.value === 'admin' ? 'admin' : 'user')}
            aria-invalid={errors.role ? true : undefined}
            aria-describedby={describe('role')}
            className={inputClass}
          >
            <option value="user">User</option>
            <option value="admin">Admin</option>
          </select>
          <FieldError id={errorIdOf('role')} message={errors.role} />
        </div>
        <div>
          <label htmlFor={idOf('password')} className={label}>Temporary password</label>
          <PasswordInput
            key={passwordKey}
            id={idOf('password')}
            value={form.password}
            onChange={(v) => set('password', v)}
            error={errors.password}
            errorId={errorIdOf('password')}
            hint="12 to 128 characters, not the email address."
          />
        </div>
      </div>
      {failure && (
        <p
          role="alert"
          className="mt-4 rounded-lg border border-error/30 bg-error-container/30 px-4 py-3 text-body-md text-on-error-container"
        >
          {failure}
        </p>
      )}
      <div className="mt-6">
        <button
          type="submit"
          aria-disabled={busy}
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-label-md text-on-primary hover:opacity-90 aria-disabled:cursor-wait aria-disabled:opacity-60"
        >
          {busy && <Spinner />}
          {busy ? 'Creating…' : 'Create user'}
        </button>
      </div>
    </form>
  )
}

type Dialog = { kind: 'lock' | 'reset'; user: AdminUser } | null

export function UsersPage() {
  const { state } = useAuth()
  const selfId = state.status === 'authenticated' ? state.user.id : null
  const [offset, setOffset] = useState(0)
  const [dialog, setDialog] = useState<Dialog>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const focusHeadingAfterDialog = useRef(false)

  const { data, loading, error, reload } = useAsync(() => api.adminUsers({ limit: PAGE_SIZE, offset }), [offset])

  // Locking cannot shrink the list, but a shrunk list (another admin's change) can strand the offset.
  useEffect(() => {
    if (data && offset > 0 && offset >= data.total) setOffset(lastValidOffset(data.total, PAGE_SIZE))
  }, [data, offset])

  // After a 404 the row that opened the dialog disappears, so focus would fall to <body>.
  useEffect(() => {
    if (dialog || !focusHeadingAfterDialog.current) return
    focusHeadingAfterDialog.current = false
    headingRef.current?.focus()
    // The browser may still be restoring focus for the closed dialog (to its removed opener, i.e. <body>);
    // if that lands after the call above, take focus back on the next frame.
    const frame = requestAnimationFrame(() => {
      if (document.activeElement === document.body) headingRef.current?.focus()
    })
    return () => cancelAnimationFrame(frame)
  }, [dialog])

  const onStale = () => {
    focusHeadingAfterDialog.current = true
    reload()
  }

  const users = data?.items ?? []
  const total = data?.total ?? 0
  const page = pageInfo(offset, PAGE_SIZE, total)
  const firstLoad = loading && !data

  return (
    <div className="mx-auto max-w-[1200px] p-margin-page">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 ref={headingRef} tabIndex={-1} className="text-display-lg text-primary focus:outline-none">
            Users
          </h1>
          <p className="mt-2 text-body-md text-on-surface-variant">
            Create accounts, lock or unlock access, and reset passwords.
          </p>
        </div>
        <button
          type="button"
          onClick={reload}
          disabled={loading}
          className="flex items-center gap-2 rounded-lg border border-border-subtle bg-surface px-4 py-2 text-label-md text-primary hover:bg-surface-container-low disabled:opacity-50"
        >
          <span aria-hidden="true">
            <MaterialIcon name="refresh" size={18} className={loading ? 'animate-spin' : ''} />
          </span>
          Refresh
        </button>
      </div>

      {error && (
        <div
          role="alert"
          className="mb-6 rounded-lg border border-error/30 bg-error-container/30 px-4 py-3 text-body-md text-on-error-container"
        >
          {error}
        </div>
      )}

      {/* Always mounted so screen readers announce the text changes. */}
      <div role="status" className={notice ? 'mb-6' : undefined}>
        {notice && (
          <p className="rounded-lg border border-[#a7f3d0] bg-[#ecfdf5] px-4 py-3 text-body-md text-[#065f46]">
            {notice}
          </p>
        )}
      </div>

      <CreateUserForm
        onStart={() => setNotice(null)}
        onCreated={(email) => {
          setNotice(`Created ${email}. They must change the temporary password when they first sign in.`)
          if (offset === 0) reload()
          else setOffset(0)
        }}
      />

      <div className="overflow-hidden rounded-xl border border-border-subtle bg-surface">
        <div className="relative overflow-x-auto">
          <table className="w-full border-collapse text-left">
            <caption className="sr-only">Users</caption>
            <thead>
              <tr className="border-b border-border-subtle bg-surface-container-low">
                <th scope="col" className={headCell}>Email</th>
                <th scope="col" className={headCell}>Name</th>
                <th scope="col" className={headCell}>Role</th>
                <th scope="col" className={headCell}>Status</th>
                <th scope="col" className={headCell}>Last sign-in</th>
                <th scope="col" className={headCell}>
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {firstLoad ? (
                <tr>
                  <td colSpan={6} className="px-6 py-8 text-center text-on-surface-variant">Loading…</td>
                </tr>
              ) : users.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-8 text-center text-on-surface-variant">No users yet.</td>
                </tr>
              ) : (
                users.map((user) => (
                  <tr key={user.id} className="transition-colors hover:bg-surface-container-low">
                    <td className="px-6 py-4 break-all text-primary">
                      {user.email}
                      {user.id === selfId && (
                        <span className="ml-2 rounded-full bg-surface-container-high px-2 py-0.5 text-xs font-medium text-on-surface">
                          You
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-on-surface">{user.display_name}</td>
                    <td className="px-6 py-4 text-on-surface-variant">{user.role === 'admin' ? 'Admin' : 'User'}</td>
                    <td className="px-6 py-4">
                      <span
                        className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${
                          user.is_active
                            ? 'border-[#a7f3d0] bg-[#ecfdf5] text-[#065f46]'
                            : 'border-[#fecaca] bg-[#fef2f2] text-[#991b1b]'
                        }`}
                      >
                        {statusLabel(user.is_active)}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-on-surface-variant">{lastSignInLabel(user.last_login_at)}</td>
                    <td className="px-6 py-4">
                      <div className="flex flex-wrap justify-end gap-2">
                        <button
                          type="button"
                          aria-label={`${user.is_active ? 'Lock' : 'Unlock'} ${user.email}`}
                          onClick={() => setDialog({ kind: 'lock', user })}
                          className={secondaryButton}
                        >
                          {user.is_active ? 'Lock' : 'Unlock'}
                        </button>
                        <button
                          type="button"
                          aria-label={`Reset password for ${user.email}`}
                          onClick={() => setDialog({ kind: 'reset', user })}
                          className={secondaryButton}
                        >
                          Reset password
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border-subtle bg-surface-container-lowest px-6 py-4">
          <span className="text-label-sm text-on-surface-variant">
            Showing {page.from}–{page.to} of {total} users
          </span>
          {total > PAGE_SIZE && (
            <div className="flex items-center gap-3">
              <span className="text-label-sm text-on-surface-variant">
                Page {page.page} of {page.pages}
              </span>
              <button
                type="button"
                disabled={!page.hasPrev || loading}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                className={secondaryButton}
              >
                Previous
              </button>
              <button
                type="button"
                disabled={!page.hasNext || loading}
                onClick={() => setOffset(offset + PAGE_SIZE)}
                className={secondaryButton}
              >
                Next
              </button>
            </div>
          )}
        </div>
      </div>

      {dialog?.kind === 'lock' && (
        <LockDialog
          key={dialog.user.id}
          user={dialog.user}
          onClose={() => setDialog(null)}
          onStart={() => setNotice(null)}
          onDone={(updated) => {
            setNotice(
              updated.is_active ? `Unlocked ${updated.email}.` : `Locked ${updated.email}. Their sessions were ended.`,
            )
            reload()
          }}
          onStale={onStale}
        />
      )}
      {dialog?.kind === 'reset' && (
        <ResetPasswordDialog
          key={dialog.user.id}
          user={dialog.user}
          isSelf={dialog.user.id === selfId}
          onClose={() => setDialog(null)}
          onStart={() => setNotice(null)}
          onDone={() => setNotice(`Password reset for ${dialog.user.email}. They must change it at next sign-in.`)}
          onStale={onStale}
        />
      )}
    </div>
  )
}
