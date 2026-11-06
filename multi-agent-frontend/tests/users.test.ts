import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { formatDateTime } from '../src/lib/format.ts'
import {
  lastSignInLabel,
  statusLabel,
  userActionError,
  userPasswordProblem,
  validateNewUser,
} from '../src/lib/users.ts'

describe('userPasswordProblem', () => {
  const email = 'lan@example.com'
  it('rejects 11 characters and accepts 12', () => {
    assert.match(userPasswordProblem('a'.repeat(11), email) ?? '', /at least 12/)
    assert.equal(userPasswordProblem('a'.repeat(12), email), null)
  })
  it('accepts 128 and rejects 129', () => {
    assert.equal(userPasswordProblem('a'.repeat(128), email), null)
    assert.match(userPasswordProblem('a'.repeat(129), email) ?? '', /at most 128/)
  })
  it('rejects an empty password', () => {
    assert.match(userPasswordProblem('', email) ?? '', /at least 12/)
  })
  it('counts astral characters as one code point each', () => {
    assert.equal(userPasswordProblem('😀'.repeat(12), email), null)
    assert.match(userPasswordProblem('😀'.repeat(11), email) ?? '', /at least 12/)
  })
  it('counts a decomposed Vietnamese letter once (NFD input is normalised to NFC)', () => {
    const nfd = 'Việt Nam123'.normalize('NFD') // 11 characters once composed
    assert.ok(nfd.length > 11)
    assert.match(userPasswordProblem(nfd, email) ?? '', /at least 12/)
    assert.equal(userPasswordProblem(`${nfd}4`, email), null)
  })
  it('rejects the email itself, ignoring case and surrounding spaces', () => {
    assert.match(userPasswordProblem('LAN@example.com', 'lan@example.com') ?? '', /email/)
    assert.match(userPasswordProblem('lan@example.com', ' lan@example.com ') ?? '', /email/)
  })
  it('does not trim the password: the backend does not, so "email + space" is a different password', () => {
    assert.equal(userPasswordProblem('lan@example.com ', 'lan@example.com'), null)
  })
})

describe('validateNewUser', () => {
  const good = { email: 'lan@example.com', display_name: 'Lan', role: 'user', password: 'correct horse battery' } as const
  it('returns no errors for a valid form', () => {
    assert.deepEqual(validateNewUser(good), {})
  })
  it('flags each empty or malformed field', () => {
    const errors = validateNewUser({ email: 'nope', display_name: '   ', role: 'user', password: 'short' })
    assert.deepEqual(errors, {
      email: 'Enter a valid email address.',
      display_name: 'Enter a display name.',
      password: 'Password must be at least 12 characters.',
    })
  })
  it('requires an email with something on both sides of the @', () => {
    assert.equal(validateNewUser({ ...good, email: '@example.com' }).email, 'Enter a valid email address.')
    assert.equal(validateNewUser({ ...good, email: 'lan@' }).email, 'Enter a valid email address.')
    assert.equal(validateNewUser({ ...good, email: ' lan@example.com ' }).email, undefined)
  })
  it('accepts Vietnamese display names', () => {
    assert.equal(validateNewUser({ ...good, display_name: 'Nguyễn Thị Lan' }).display_name, undefined)
  })
})

describe('statusLabel', () => {
  it('maps is_active to Active / Locked', () => {
    assert.equal(statusLabel(true), 'Active')
    assert.equal(statusLabel(false), 'Locked')
  })
})

describe('lastSignInLabel', () => {
  it('says Never when the user has not signed in', () => {
    assert.equal(lastSignInLabel(null), 'Never')
    assert.equal(lastSignInLabel(undefined), 'Never')
    assert.equal(lastSignInLabel(''), 'Never')
  })
  it('formats a timestamp like every other date in the admin UI', () => {
    const iso = '2026-11-04T08:30:00Z'
    assert.equal(lastSignInLabel(iso), formatDateTime(iso))
    assert.notEqual(lastSignInLabel(iso), 'Never')
  })
})

describe('userActionError', () => {
  it('puts a create 409 on the email field', () => {
    const e = userActionError('create', 409, 'Email already exists')
    assert.equal(e.field, 'email')
    assert.match(e.message, /already/i)
  })
  it('shows a string 422 about the password at the password field', () => {
    const e = userActionError('create', 422, 'Password must be at least 12 characters')
    assert.equal(e.field, 'password')
    assert.equal(e.message, 'Password must be at least 12 characters')
  })
  it('reads the field and message out of a FastAPI array detail', () => {
    const detail = JSON.stringify([
      { type: 'value_error', loc: ['body', 'email'], msg: 'value is not a valid email address', input: 'x' },
    ])
    const e = userActionError('create', 422, detail)
    assert.equal(e.field, 'email')
    assert.equal(e.message, 'value is not a valid email address')
  })
  it('strips the "Value error, " prefix Pydantic adds', () => {
    const detail = JSON.stringify([{ loc: ['body', 'password'], msg: 'Value error, Password must differ from the email' }])
    assert.equal(userActionError('create', 422, detail).message, 'Password must differ from the email')
  })
  it('never shows raw JSON: unknown shapes fall back to generic text', () => {
    for (const detail of ['[]', '{"x":1}', '[{"loc":[],"msg":""}]', '[1,2']) {
      const e = userActionError('create', 422, detail)
      assert.doesNotMatch(e.message, /[[{]/)
      assert.ok(e.message.length > 0)
    }
  })
  it('maps an unknown array location to no field', () => {
    const e = userActionError('create', 422, JSON.stringify([{ loc: ['body', 'role'], msg: 'bad role' }]))
    assert.equal(e.field, 'role')
    const e2 = userActionError('create', 422, JSON.stringify([{ loc: ['body', 'zzz'], msg: 'odd' }]))
    assert.equal(e2.field, undefined)
    assert.equal(e2.message, 'odd')
  })
  it('shows the server text for a lock 409 (self-lock / last admin) with no field', () => {
    const e = userActionError('lock', 409, 'Cannot lock the last active admin')
    assert.equal(e.field, undefined)
    assert.equal(e.message, 'Cannot lock the last active admin')
  })
  it('gives a lock 409 without usable text a clear fallback', () => {
    assert.match(userActionError('lock', 409, '').message, /own account|last/i)
  })
  it('explains 404 as the user being gone', () => {
    assert.equal(userActionError('lock', 404, 'Not found').message, 'This user no longer exists. Refresh the list.')
    assert.equal(userActionError('reset', 404, 'Not found').message, 'This user no longer exists. Refresh the list.')
  })
  it('puts a reset 422 array at the password field whatever its loc says', () => {
    const e = userActionError('reset', 422, JSON.stringify([{ loc: ['body', 'zzz'], msg: 'Value error, Too weak' }]))
    assert.deepEqual(e, { field: 'password', message: 'Too weak' })
  })
  it('puts a reset 422 at the password field', () => {
    assert.equal(userActionError('reset', 422, 'Password too short').field, 'password')
  })
  it('handles network failures and 403/5xx', () => {
    assert.match(userActionError('create', undefined, '').message, /reach the server/i)
    assert.match(userActionError('create', 403, 'Admin access required').message, /Admin access required/)
    assert.ok(userActionError('create', 500, '').message.length > 0)
  })
})
