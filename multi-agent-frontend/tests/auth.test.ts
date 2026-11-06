import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  changePasswordErrorMessage,
  loginErrorMessage,
  loginRedirect,
  parseResponseBody,
  parseRetryAfter,
  passwordProblem,
  safeNextPath,
} from '../src/lib/auth.ts'

test('safeNextPath keeps ordinary in-app paths, including query and hash', () => {
  assert.equal(safeNextPath('/chat/abc'), '/chat/abc')
  assert.equal(safeNextPath('/admin/knowledge?domain=hr#top'), '/admin/knowledge?domain=hr#top')
  assert.equal(safeNextPath('/'), '/')
})

test('safeNextPath rejects protocol-relative and backslash open redirects', () => {
  assert.equal(safeNextPath('//evil.com'), '/chat')
  assert.equal(safeNextPath('/\\evil'), '/chat')
  assert.equal(safeNextPath('/chat\\..\\evil'), '/chat')
})

test('safeNextPath rejects absolute URLs and anything not starting with a slash', () => {
  assert.equal(safeNextPath('https://x'), '/chat')
  assert.equal(safeNextPath('javascript:alert(1)'), '/chat')
  assert.equal(safeNextPath('chat'), '/chat')
})

test('safeNextPath rejects paths that dot-segments resolve to a protocol-relative URL', () => {
  assert.equal(safeNextPath('/.//evil.com'), '/chat')
  assert.equal(safeNextPath('/..//evil.com'), '/chat')
  assert.equal(safeNextPath('/chat/..//evil.com'), '/chat')
})

test('safeNextPath rejects control characters browsers strip before parsing', () => {
  assert.equal(safeNextPath('/\t/evil.com'), '/chat')
  assert.equal(safeNextPath('/\n/evil.com'), '/chat')
})

test('safeNextPath refuses /login however it is spelled once resolved', () => {
  for (const next of [
    '/./login',
    '/chat/../login',
    '/LOGIN',
    '/Login/x',
    '/%6Cogin',
    '/%2e/login',
    '/chat/%2e%2e/login',
    '/login%2Fx',
    '/login#x',
    '/login?next=/login',
  ]) {
    assert.equal(safeNextPath(next), '/chat', next)
  }
})

test('safeNextPath returns the resolved path, query and hash', () => {
  assert.equal(safeNextPath('/chat/../admin?x=1#y'), '/admin?x=1#y')
  assert.equal(safeNextPath('/chat/a b'), '/chat/a%20b')
})

test('safeNextPath falls back on undecodable escapes', () => {
  assert.equal(safeNextPath('/chat/%E0%A4%A'), '/chat')
})

test('safeNextPath falls back for empty, null and undefined', () => {
  assert.equal(safeNextPath(''), '/chat')
  assert.equal(safeNextPath(null), '/chat')
  assert.equal(safeNextPath(undefined), '/chat')
})

test('safeNextPath never sends the user back to the login page', () => {
  assert.equal(safeNextPath('/login'), '/chat')
  assert.equal(safeNextPath('/login?next=%2Fchat'), '/chat')
  assert.equal(safeNextPath('/login/'), '/chat')
  assert.equal(safeNextPath('/loginx'), '/loginx')
})

test('loginRedirect encodes the full path and query into next', () => {
  assert.equal(loginRedirect('/chat', ''), '/login?next=%2Fchat')
  assert.equal(loginRedirect('/admin/knowledge', '?q=a b'), '/login?next=%2Fadmin%2Fknowledge%3Fq%3Da%20b')
})

test('parseRetryAfter reads delta-seconds only', () => {
  assert.equal(parseRetryAfter('120'), 120)
  assert.equal(parseRetryAfter(' 5 '), 5)
  assert.equal(parseRetryAfter('Wed, 21 Oct 2026 07:28:00 GMT'), null)
  assert.equal(parseRetryAfter('-3'), null)
  assert.equal(parseRetryAfter(''), null)
  assert.equal(parseRetryAfter(null), null)
})

test('loginErrorMessage gives one message for bad credentials', () => {
  assert.equal(loginErrorMessage(401), 'Incorrect email or password.')
})

test('loginErrorMessage on 429 names the wait when Retry-After is known', () => {
  assert.equal(loginErrorMessage(429, 30), 'Too many attempts. Try again in 30 seconds.')
  assert.equal(loginErrorMessage(429, 1), 'Too many attempts. Try again in 1 second.')
  assert.equal(loginErrorMessage(429, 60), 'Too many attempts. Try again in 1 minute.')
  assert.equal(loginErrorMessage(429, 61), 'Too many attempts. Try again in 2 minutes.')
  assert.equal(loginErrorMessage(429, null), 'Too many attempts. Try again later.')
  assert.equal(loginErrorMessage(429, 0), 'Too many attempts. Try again later.')
})

test('loginErrorMessage covers network failure and unexpected statuses', () => {
  assert.match(loginErrorMessage(undefined), /reach the server/)
  assert.match(loginErrorMessage(403), /Reload/)
  assert.match(loginErrorMessage(500), /Sign-in failed/)
})

test('passwordProblem enforces 12..128 at the boundaries', () => {
  const ok = 'a'.repeat(12)
  assert.equal(passwordProblem('old', ok, ok), null)
  assert.equal(passwordProblem('old', 'a'.repeat(128), 'a'.repeat(128)), null)
  assert.match(passwordProblem('old', 'a'.repeat(11), 'a'.repeat(11)) ?? '', /at least 12/)
  assert.match(passwordProblem('old', 'a'.repeat(129), 'a'.repeat(129)) ?? '', /at most 128/)
})

test('passwordProblem counts code points, not UTF-16 units', () => {
  const emoji = '😀'.repeat(6)
  assert.equal(emoji.length, 12)
  assert.match(passwordProblem('old', emoji, emoji) ?? '', /at least 12/)
  const enough = '😀'.repeat(12)
  assert.equal(passwordProblem('old', enough, enough), null)
})

test('passwordProblem NFC-normalises like the backend before counting and comparing', () => {
  const composed = 'mậtkhẩumới1'
  const decomposed = composed.normalize('NFD')
  assert.equal([...composed].length, 11)
  assert.ok([...decomposed].length > 12)
  // Without normalisation the decomposed form would sneak past the 12 minimum.
  assert.match(passwordProblem('old', decomposed, decomposed) ?? '', /at least 12/)
  const twelve = 'mậtkhẩumới12'
  assert.equal(passwordProblem('old', twelve.normalize('NFD'), twelve.normalize('NFC')), null)
  assert.match(passwordProblem(twelve.normalize('NFC'), twelve.normalize('NFD'), twelve.normalize('NFD')) ?? '', /different/)
})

test('passwordProblem requires the current password, a matching confirmation and a change', () => {
  const pw = 'correct horse battery'
  assert.match(passwordProblem('', pw, pw) ?? '', /current password/i)
  assert.match(passwordProblem('old', pw, pw + 'x') ?? '', /do not match/)
  assert.match(passwordProblem(pw, pw, pw) ?? '', /different/)
})

test('changePasswordErrorMessage maps 401 and 422 and does not leak raw JSON', () => {
  assert.equal(changePasswordErrorMessage(400, 'Current password is incorrect'), 'Current password is incorrect.')
  assert.equal(changePasswordErrorMessage(422, 'Password must differ from email'), 'Password must differ from email')
  assert.match(changePasswordErrorMessage(422, '[{"loc":["body"]}]'), /does not meet/)
  assert.match(changePasswordErrorMessage(undefined, ''), /reach the server/)
  assert.equal(changePasswordErrorMessage(500, 'boom'), 'boom')
})

test('changePasswordErrorMessage on 429 names the wait like the login one', () => {
  assert.equal(changePasswordErrorMessage(429, 'Too many attempts, try again later', 30), 'Too many attempts. Try again in 30 seconds.')
  assert.equal(changePasswordErrorMessage(429, 'x', 61), 'Too many attempts. Try again in 2 minutes.')
  assert.equal(changePasswordErrorMessage(429, 'Too many attempts, try again later', null), 'Too many attempts. Try again later.')
})

test('parseResponseBody returns undefined for 204/205 even when labelled JSON', () => {
  assert.equal(parseResponseBody(204, 'application/json', ''), undefined)
  assert.equal(parseResponseBody(205, 'application/json', ''), undefined)
  assert.equal(parseResponseBody(204, 'application/json', '{}'), undefined)
})

test('parseResponseBody treats an empty body as undefined instead of throwing', () => {
  assert.equal(parseResponseBody(200, 'application/json', ''), undefined)
  assert.equal(parseResponseBody(200, 'text/plain', ''), undefined)
})

test('parseResponseBody parses JSON, passes other bodies through, and still throws on bad JSON', () => {
  assert.deepEqual(parseResponseBody(200, 'application/json; charset=utf-8', '{"a":1}'), { a: 1 })
  assert.equal(parseResponseBody(200, 'text/csv', 'a,b'), 'a,b')
  assert.throws(() => parseResponseBody(200, 'application/json', '{bad'))
})
