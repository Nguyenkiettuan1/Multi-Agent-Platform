import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { PipelineStep } from '../src/api/types.ts'
import { dedupeSteps } from '../src/lib/pipeline.ts'

function step(status: PipelineStep['status'], over: Partial<PipelineStep> = {}): PipelineStep {
  return { id: `s-${status}`, phase: 'worker', agent: 'research', status, title: 'Research', ...over }
}

test('running then done resolves to done', () => {
  const out = dedupeSteps([step('running'), step('done')])
  assert.deepEqual(out.map((s) => s.status), ['done'])
})

test('a late running after done stays done', () => {
  const out = dedupeSteps([step('running'), step('done'), step('running')])
  assert.deepEqual(out.map((s) => s.status), ['done'])
})

test('skipped then running resolves to running', () => {
  const out = dedupeSteps([step('skipped'), step('running')])
  assert.deepEqual(out.map((s) => s.status), ['running'])
})

test('running beats a later skipped', () => {
  const out = dedupeSteps([step('running'), step('skipped')])
  assert.deepEqual(out.map((s) => s.status), ['running'])
})

test('running then failed resolves to failed', () => {
  const out = dedupeSteps([step('running'), step('failed')])
  assert.deepEqual(out.map((s) => s.status), ['failed'])
})

test('same status: the later step replaces the earlier one', () => {
  const out = dedupeSteps([step('done', { detail: 'a' }), step('done', { detail: 'b' })])
  assert.deepEqual(out.map((s) => s.detail), ['b'])
})

test('two agents in the same phase stay separate', () => {
  const out = dedupeSteps([
    step('running', { agent: 'research' }),
    step('running', { agent: 'db' }),
    step('done', { agent: 'research' }),
  ])
  assert.deepEqual(out.map((s) => [s.agent, s.status]), [
    ['research', 'done'],
    ['db', 'running'],
  ])
})

test('steps without an agent are keyed by title', () => {
  const out = dedupeSteps([
    step('done', { agent: null, title: 'Triage' }),
    step('done', { agent: null, title: 'Plan' }),
  ])
  assert.deepEqual(out.map((s) => s.title), ['Triage', 'Plan'])
})

// The cases below mirror workflows/runner.py: the "next phase" announcement has no
// agent, while the terminal step from pipeline_trace.py names one (or a new title).
test('agentless planner placeholder resolves to the planner step', () => {
  const out = dedupeSteps([
    step('running', { phase: 'plan', agent: null, title: 'Plan agents' }),
    step('done', { phase: 'plan', agent: 'meta-planner', title: 'Plan agents' }),
  ])
  assert.deepEqual(out.map((s) => [s.agent, s.status]), [['meta-planner', 'done']])
})

test('agentless reviewer placeholder resolves to the skipped step', () => {
  const out = dedupeSteps([
    step('running', { phase: 'review', agent: null, title: 'Reviewer check' }),
    step('skipped', { phase: 'review', agent: null, title: 'Reviewer' }),
  ])
  assert.deepEqual(out.map((s) => [s.title, s.status]), [['Reviewer', 'skipped']])
})

test('agentless worker placeholder is replaced by the worker agent steps', () => {
  const out = dedupeSteps([
    step('running', { phase: 'worker', agent: null, title: 'Run agents' }),
    step('running', { phase: 'worker', agent: 'research-worker', title: 'Research' }),
    step('done', { phase: 'worker', agent: 'research-worker', title: 'Research' }),
  ])
  assert.deepEqual(out.map((s) => [s.agent, s.status]), [['research-worker', 'done']])
})

test('placeholder does not remove sibling agents already running in its phase', () => {
  const out = dedupeSteps([
    step('running', { phase: 'worker', agent: null, title: 'Run agents' }),
    step('running', { phase: 'worker', agent: 'research-worker' }),
    step('running', { phase: 'worker', agent: 'db-worker' }),
  ])
  assert.deepEqual(out.map((s) => s.agent), ['research-worker', 'db-worker'])
})

test('full runner sequence leaves no running step and keeps phase order', () => {
  const out = dedupeSteps([
    step('running', { phase: 'triage', agent: 'triage', title: 'Triage' }),
    step('done', { phase: 'triage', agent: 'triage', title: 'Triage' }),
    step('running', { phase: 'plan', agent: null, title: 'Plan agents' }),
    step('done', { phase: 'plan', agent: 'meta-planner', title: 'Plan agents' }),
    step('running', { phase: 'worker', agent: null, title: 'Run agents' }),
    step('running', { phase: 'worker', agent: 'research-worker', title: 'Research' }),
    step('done', { phase: 'worker', agent: 'research-worker', title: 'Research' }),
    step('running', { phase: 'review', agent: null, title: 'Reviewer check' }),
    step('skipped', { phase: 'review', agent: null, title: 'Reviewer' }),
    step('running', { phase: 'synthesize', agent: null, title: 'Synthesize response' }),
    step('done', { phase: 'synthesize', agent: 'synthesizer', title: 'Synthesize response' }),
  ])
  assert.deepEqual(out.map((s) => [s.phase, s.status]), [
    ['triage', 'done'],
    ['plan', 'done'],
    ['worker', 'done'],
    ['review', 'skipped'],
    ['synthesize', 'done'],
  ])
})

test('first-seen order is preserved when a slot is replaced', () => {
  const out = dedupeSteps([
    step('running', { phase: 'triage', agent: 'triage', title: 'Triage' }),
    step('running', { phase: 'worker', agent: 'research' }),
    step('done', { phase: 'triage', agent: 'triage', title: 'Triage' }),
  ])
  assert.deepEqual(out.map((s) => [s.phase, s.status]), [
    ['triage', 'done'],
    ['worker', 'running'],
  ])
})

test('a skipped step with the same title as its placeholder replaces it', () => {
  const out = dedupeSteps([
    step('running', { phase: 'review', agent: null, title: 'Reviewer' }),
    step('skipped', { phase: 'review', agent: null, title: 'Reviewer' }),
  ])
  assert.deepEqual(out.map((s) => [s.title, s.status]), [['Reviewer', 'skipped']])
})

// A placeholder only announces a phase that has not produced a step yet; arriving after the real
// step (out of order) it is stale, so it is dropped instead of showing a second, forever-running row.
test('a late placeholder is dropped when its phase already has a real step', () => {
  const out = dedupeSteps([
    step('done', { phase: 'plan', agent: 'meta-planner', title: 'Plan agents' }),
    step('running', { phase: 'plan', agent: null, title: 'Plan agents' }),
  ])
  assert.deepEqual(out.map((s) => [s.agent, s.status]), [['meta-planner', 'done']])
})

test('a late placeholder does not replace a real agentless step with the same title', () => {
  const out = dedupeSteps([
    step('skipped', { phase: 'review', agent: null, title: 'Reviewer' }),
    step('running', { phase: 'review', agent: null, title: 'Reviewer' }),
  ])
  assert.deepEqual(out.map((s) => [s.title, s.status]), [['Reviewer', 'skipped']])
})
