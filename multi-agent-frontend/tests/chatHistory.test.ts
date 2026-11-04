import assert from 'node:assert/strict'
import { test } from 'node:test'
import { canMoveFocus, createGeneration, dropKnownTurns, scrollTopAfterPrepend } from '../src/lib/chatHistory.ts'

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
