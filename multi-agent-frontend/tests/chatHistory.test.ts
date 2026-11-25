import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  appendSessionPage,
  canMoveFocus,
  createGeneration,
  dropKnownTurns,
  scrollTopAfterPrepend,
  sessionIdFromErrorPayload,
  turnOutcome,
} from '../src/lib/chatHistory.ts'

const t = (id: string) => ({ trace_id: id })
const ids = (turns: Array<{ trace_id: string }>) => turns.map((x) => x.trace_id)

test('dropKnownTurns removes only the turns whose id is known', () => {
  const kept = dropKnownTurns([t('1'), t('2'), t('3')], new Set(['2']))
  assert.deepEqual(ids(kept), ['1', '3'])
})

test('dropKnownTurns with an empty set keeps everything but dedupes within the page', () => {
  assert.deepEqual(ids(dropKnownTurns([t('1'), t('1')], new Set())), ['1'])
})

test('scrollTopAfterPrepend adds the height the prepend created', () => {
  assert.equal(scrollTopAfterPrepend(0, 1000, 1800), 800)
  assert.equal(scrollTopAfterPrepend(120, 1000, 1800), 920)
})

test('scrollTopAfterPrepend never goes negative when content shrank', () => {
  assert.equal(scrollTopAfterPrepend(10, 1000, 900), 0)
})

test('scrollTopAfterPrepend is a no-op when height did not change', () => {
  assert.equal(scrollTopAfterPrepend(250, 1000, 1000), 250)
})

test('dropKnownTurns does not mutate its inputs', () => {
  const turns = [t('1'), t('2')]
  const known = new Set(['1'])
  const kept = dropKnownTurns(turns, known)
  assert.deepEqual(turns, [t('1'), t('2')])
  assert.deepEqual([...known], ['1'])
  assert.notEqual(kept, turns)
})

test('generation: a ticket is current until the next one is issued', () => {
  const gen = createGeneration()
  const first = gen.next()
  assert.equal(gen.isCurrent(first), true)
  const second = gen.next()
  assert.equal(gen.isCurrent(first), false)
  assert.equal(gen.isCurrent(second), true)
})

test('generation: A to B to A leaves the first A request stale', () => {
  const gen = createGeneration()
  gen.next() // session A mounts
  const requestOnA = gen.next() // older-page request started on A
  gen.next() // switch to B
  gen.next() // switch back to A
  assert.equal(gen.isCurrent(requestOnA), false)
})

test('generation: tickets are strictly increasing and unique', () => {
  const gen = createGeneration()
  assert.deepEqual([gen.next(), gen.next(), gen.next()], [1, 2, 3])
})

test('canMoveFocus: still on the load button that started the load', () => {
  assert.equal(canMoveFocus({ wasOnButton: true, active: 'btn', button: 'btn', body: 'body' }), true)
})

test('canMoveFocus: focus fell to the body (button unmounted)', () => {
  assert.equal(canMoveFocus({ wasOnButton: true, active: 'body', button: null, body: 'body' }), true)
  assert.equal(canMoveFocus({ wasOnButton: false, active: 'body', button: 'btn', body: 'body' }), true)
  assert.equal(canMoveFocus({ wasOnButton: false, active: null, button: 'btn', body: 'body' }), true)
})

test('canMoveFocus: user moved to another control, such as the textarea', () => {
  assert.equal(canMoveFocus({ wasOnButton: true, active: 'textarea', button: 'btn', body: 'body' }), false)
  assert.equal(canMoveFocus({ wasOnButton: false, active: 'textarea', button: 'btn', body: 'body' }), false)
})

test('canMoveFocus: button focused now but it was not when the load started', () => {
  assert.equal(canMoveFocus({ wasOnButton: false, active: 'btn', button: 'btn', body: 'body' }), false)
})

test('turnOutcome: completed and a missing status both render the answer', () => {
  assert.deepEqual(turnOutcome('completed'), { kind: 'answer' })
  assert.deepEqual(turnOutcome(undefined), { kind: 'answer' })
  assert.deepEqual(turnOutcome(null), { kind: 'answer' })
})

test('turnOutcome: failed shows a fixed note, never server text', () => {
  assert.deepEqual(turnOutcome('failed'), { kind: 'note', text: 'No answer — the request failed' })
})

test('turnOutcome: incomplete says the request did not finish', () => {
  assert.deepEqual(turnOutcome('incomplete'), { kind: 'note', text: 'No answer — the request did not finish' })
})

test('turnOutcome: an unknown future status degrades to the answer, not a crash', () => {
  assert.deepEqual(turnOutcome('archived'), { kind: 'answer' })
})

const s = (id: string) => ({ session_id: id })

test('appendSessionPage appends the next page after the current list', () => {
  const merged = appendSessionPage([s('a'), s('b')], [s('c')])
  assert.deepEqual(merged.map((x) => x.session_id), ['a', 'b', 'c'])
})

test('appendSessionPage drops sessions already listed (a new chat shifted the page)', () => {
  const merged = appendSessionPage([s('a'), s('b')], [s('b'), s('c'), s('c')])
  assert.deepEqual(merged.map((x) => x.session_id), ['a', 'b', 'c'])
})

test('appendSessionPage with an empty page returns an equal list without mutating', () => {
  const current = [s('a')]
  const merged = appendSessionPage(current, [])
  assert.deepEqual(merged, [s('a')])
  assert.deepEqual(current, [s('a')])
})

test('appendSessionPage: a session that moved from the tail to the top keeps its new position', () => {
  const merged = appendSessionPage([s('a'), s('b'), s('c'), s('x'), s('d')], [s('x'), s('a'), s('b')])
  assert.deepEqual(merged.map((i) => i.session_id), ['a', 'b', 'c', 'x', 'd'])
  // fresh page 1 first, previously loaded list after it
  const refreshed = appendSessionPage([s('x'), s('a'), s('b')], [s('a'), s('b'), s('c'), s('x'), s('d')])
  assert.deepEqual(refreshed.map((i) => i.session_id), ['x', 'a', 'b', 'c', 'd'])
})

test('sessionIdFromErrorPayload reads a top-level session_id (SSE error event)', () => {
  assert.equal(sessionIdFromErrorPayload({ message: 'boom', session_id: 'abc123' }), 'abc123')
})

test('sessionIdFromErrorPayload reads session_id inside an object detail (POST /chat body)', () => {
  assert.equal(sessionIdFromErrorPayload({ detail: { message: 'boom', session_id: 'abc123' } }), 'abc123')
})

test('sessionIdFromErrorPayload returns null for anything else', () => {
  assert.equal(sessionIdFromErrorPayload({ detail: 'Session not found' }), null)
  assert.equal(sessionIdFromErrorPayload({ session_id: '' }), null)
  assert.equal(sessionIdFromErrorPayload({ session_id: 42 }), null)
  assert.equal(sessionIdFromErrorPayload(null), null)
  assert.equal(sessionIdFromErrorPayload('text'), null)
  assert.equal(sessionIdFromErrorPayload(undefined), null)
})
