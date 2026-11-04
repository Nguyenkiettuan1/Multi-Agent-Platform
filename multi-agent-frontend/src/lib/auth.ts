// Pure helpers for the auth flow. No imports: tests run this file directly under node.

/** Dispatched on window by the API client on a 401; AuthContext listens (avoids a client <-> context import cycle). */
export const AUTH_UNAUTHORIZED_EVENT = 'auth:unauthorized'

export const DEFAULT_NEXT_PATH = '/chat'
export const PASSWORD_MIN_LENGTH = 12
export const PASSWORD_MAX_LENGTH = 128

// Browsers strip tab/newline before parsing a URL, so "/\t/evil.com" would become "//evil.com".
const PARSE_BASE = 'http://x'

function hasControlChar(value: string): boolean {
  for (let i = 0; i < value.length; i++) {
    const code = value.charCodeAt(i)
    if (code <= 0x1f || code === 0x7f) return true
  }
  return false
}

/**
 * Validates the `next` query param of /login. Only same-origin absolute paths are accepted:
 * must start with a single "/", no backslash (some browsers treat it as "/"), no control characters.
 * /login itself is refused so a successful sign-in never lands back on the sign-in form.
 */
export function safeNextPath(next: string | null | undefined): string {
  if (typeof next !== 'string' || next === '') return DEFAULT_NEXT_PATH
  if (!next.startsWith('/') || next.startsWith('//')) return DEFAULT_NEXT_PATH
  if (next.includes('\\') || hasControlChar(next)) return DEFAULT_NEXT_PATH

  // Resolve like a browser would, so "/./login", "/chat/../login" and "/%2e%2e/login" are judged by where they land.
  let url: URL
  try {
    url = new URL(next, PARSE_BASE)
  } catch {
    return DEFAULT_NEXT_PATH
  }
  if (url.origin !== PARSE_BASE) return DEFAULT_NEXT_PATH

  // The router matches case-insensitively and on the decoded path, so "/LOGIN" and "/%6Cogin" are /login too.
  let decoded: string
  try {
    decoded = decodeURIComponent(url.pathname).toLowerCase()
  } catch {
    return DEFAULT_NEXT_PATH
  }
  if (decoded === '/login' || decoded.startsWith('/login/')) return DEFAULT_NEXT_PATH
  return url.pathname + url.search + url.hash
}

export function loginRedirect(pathname: string, search: string): string {
  return `/login?next=${encodeURIComponent(pathname + search)}`
}

/** Retry-After as delta-seconds. HTTP-date form is not used by this API, so it maps to null. */
export function parseRetryAfter(header: string | null | undefined): number | null {
  if (!header || !/^\s*\d+\s*$/.test(header)) return null
  return Number(header.trim())
}

function plural(n: number, unit: string): string {
  return `${n} ${unit}${n === 1 ? '' : 's'}`
}

export function loginErrorMessage(status: number | undefined, retryAfterSeconds?: number | null): string {
  if (status === undefined) return 'Could not reach the server. Check your connection and try again.'
  if (status === 401) return 'Incorrect email or password.'
  if (status === 429) {
    if (!retryAfterSeconds || retryAfterSeconds <= 0) return 'Too many attempts. Try again later.'
    const wait =
      retryAfterSeconds < 60 ? plural(retryAfterSeconds, 'second') : plural(Math.ceil(retryAfterSeconds / 60), 'minute')
    return `Too many attempts. Try again in ${wait}.`
  }
  // 403 here means the server rejected the request itself (e.g. missing CSRF header), not the credentials.
  if (status === 403) return 'Sign-in was blocked by the server. Reload the page and try again.'
  return 'Sign-in failed. Try again in a moment.'
}

/**
 * Body of a successful response. 204/205 and empty bodies yield undefined even when the server labels them
 * application/json: parsing "" would throw after the server already did the work.
 */
export function parseResponseBody(status: number, contentType: string, text: string): unknown {
  if (status === 204 || status === 205 || text === '') return undefined
  return contentType.includes('application/json') ? JSON.parse(text) : text
}

/** Password length as the backend counts it: code points after NFC (a decomposed "ậ" is one character). */
export function passwordLength(raw: string): number {
  return [...raw.normalize('NFC')].length
}

/**
 * Client-side pre-check; the server stays the authority. Lengths count code points, not UTF-16 units, after
 * NFC normalisation, which is how the backend counts (a decomposed "ậ" is one character).
 */
export function passwordProblem(current: string, rawNext: string, rawConfirm: string): string | null {
  if (!current) return 'Enter your current password.'
  const next = rawNext.normalize('NFC')
  const confirm = rawConfirm.normalize('NFC')
  const length = passwordLength(next)
  if (length < PASSWORD_MIN_LENGTH) return `New password must be at least ${PASSWORD_MIN_LENGTH} characters.`
  if (length > PASSWORD_MAX_LENGTH) return `New password must be at most ${PASSWORD_MAX_LENGTH} characters.`
  if (next !== confirm) return 'New password and confirmation do not match.'
  if (next === current.normalize('NFC')) return 'Choose a password different from the current one.'
  return null
}

export function changePasswordErrorMessage(status: number | undefined, detail: string): string {
  if (status === undefined) return 'Could not reach the server. Check your connection and try again.'
  if (status === 400) return 'Current password is incorrect.'
  if (status === 422) {
    // ApiError stringifies non-string `detail` as JSON; do not show that to people.
    return detail && !/^[[{]/.test(detail) ? detail : 'New password does not meet the password policy.'
  }
  return detail || 'Could not change the password. Try again in a moment.'
}
