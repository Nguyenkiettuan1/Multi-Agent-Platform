// Pure helpers for Admin › Users. No framework imports: tests run this file directly under node.
import { PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH, passwordLength } from './auth.ts'
import { formatDateTime } from './format.ts'

export type NewUserForm = { email: string; display_name: string; role: 'user' | 'admin'; password: string }
export type UserField = 'email' | 'display_name' | 'role' | 'password'
export type NewUserErrors = Partial<Record<UserField, string>>
export type UserAction = 'create' | 'lock' | 'reset'
export type UserActionError = { field?: UserField; message: string }

/**
 * Early warning only; the server stays the authority (D5). The backend never trims the password and
 * compares it case-folded with the stripped email, so only the email is trimmed here.
 */
export function userPasswordProblem(rawPassword: string, email: string): string | null {
  const password = rawPassword.normalize('NFC')
  const length = passwordLength(password)
  if (length < PASSWORD_MIN_LENGTH) return `Password must be at least ${PASSWORD_MIN_LENGTH} characters.`
  if (length > PASSWORD_MAX_LENGTH) return `Password must be at most ${PASSWORD_MAX_LENGTH} characters.`
  const normalizedEmail = email.normalize('NFC').trim().toLowerCase()
  if (normalizedEmail && password.toLowerCase() === normalizedEmail) {
    return 'Password must not be the same as the email address.'
  }
  return null
}

export function validateNewUser(form: NewUserForm): NewUserErrors {
  const errors: NewUserErrors = {}
  const email = form.email.trim()
  const at = email.indexOf('@')
  if (at < 1 || at === email.length - 1) errors.email = 'Enter a valid email address.'
  if (!form.display_name.trim()) errors.display_name = 'Enter a display name.'
  const password = userPasswordProblem(form.password, email)
  if (password) errors.password = password
  return errors
}

export function statusLabel(isActive: boolean): 'Active' | 'Locked' {
  return isActive ? 'Active' : 'Locked'
}

export function lastSignInLabel(iso: string | null | undefined): string {
  return iso ? formatDateTime(iso) : 'Never'
}

const FIELDS: readonly string[] = ['email', 'display_name', 'role', 'password']

function isUserField(value: unknown): value is UserField {
  return typeof value === 'string' && FIELDS.includes(value)
}

// ApiError stringifies non-string `detail` (FastAPI 422 arrays) as JSON; people must never see that.
function looksLikeJson(text: string): boolean {
  return /^\s*[[{]/.test(text)
}

function plainDetail(detail: string): string {
  return detail && !looksLikeJson(detail) ? detail : ''
}

function fieldFromText(text: string): UserField | undefined {
  if (/password/i.test(text)) return 'password'
  if (/e-?mail/i.test(text)) return 'email'
  if (/name/i.test(text)) return 'display_name'
  return undefined
}

/** First usable entry of a FastAPI validation array, or null when the detail is not one. */
function fromValidationArray(detail: string): UserActionError | null {
  let parsed: unknown
  try {
    parsed = JSON.parse(detail)
  } catch {
    return null
  }
  if (!Array.isArray(parsed)) return null
  for (const item of parsed) {
    if (typeof item !== 'object' || item === null) continue
    const { loc, msg } = item as { loc?: unknown; msg?: unknown }
    // Pydantic prefixes validator messages with "Value error, ".
    const message = typeof msg === 'string' ? msg.replace(/^Value error,\s*/i, '').trim() : ''
    if (!message) continue
    const last = Array.isArray(loc) ? loc[loc.length - 1] : undefined
    return isUserField(last) ? { field: last, message } : { message }
  }
  return null
}

export function userActionError(action: UserAction, status: number | undefined, detail: string): UserActionError {
  if (status === undefined) return { message: 'Could not reach the server. Check your connection and try again.' }
  const text = plainDetail(detail)

  if (status === 404) return { message: 'This user no longer exists. Refresh the list.' }
  if (status === 409) {
    if (action === 'create') return { field: 'email', message: 'A user with this email already exists.' }
    return { message: text || 'This would leave no active admin, or lock your own account. Nothing was changed.' }
  }
  if (status === 422) {
    const fromArray = looksLikeJson(detail) ? fromValidationArray(detail) : null
    if (fromArray) return action === 'reset' ? { field: 'password', message: fromArray.message } : fromArray
    if (action === 'reset') return { field: 'password', message: text || 'Password does not meet the password policy.' }
    if (text) return { field: fieldFromText(text), message: text }
    return { message: 'The server rejected these details. Check the fields and try again.' }
  }
  return { message: text || 'Something went wrong. Try again in a moment.' }
}
