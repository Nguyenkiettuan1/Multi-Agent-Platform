import type { PipelineStep } from '../api/types'

// A `running` that arrives before its `done` must not block it. Skipped is terminal
// too but ranks below running, so a later "skipped" never hides a live step.
const RANK: Record<PipelineStep['status'], number> = {
  skipped: 0,
  running: 1,
  done: 2,
  failed: 2,
}

function slotKey(step: PipelineStep): string {
  return `${step.phase}:${step.agent ?? step.title}`
}

// The backend's "next phase" announcement: agentless and still running.
function isPlaceholder(step: PipelineStep): boolean {
  return !step.agent && step.status === 'running'
}

/**
 * One step per phase+agent slot, in first-seen order; a step never downgrades its slot's status.
 *
 * The backend announces the next phase with an agentless `running` placeholder, but the
 * terminal step names an agent or uses another title, so the keys never match. A real
 * step therefore replaces a stale placeholder of its phase and takes over its position.
 * A placeholder never overrides or duplicates a phase that already has a real step: if it arrives
 * late (out of order) it is dropped.
 */
export function dedupeSteps(steps: PipelineStep[]): PipelineStep[] {
  const slots: Array<{ key: string; step: PipelineStep }> = []
  for (const step of steps) {
    const key = slotKey(step)
    const same = slots.findIndex((s) => s.key === key)
    if (same >= 0) {
      const prev = slots[same].step
      // A placeholder never replaces a real step, whatever its rank.
      if (isPlaceholder(step) && !isPlaceholder(prev)) continue
      // A placeholder is only an announcement, so any later step wins; this also covers a terminal
      // step that shares its placeholder's title but ranks lower (skipped).
      if (RANK[step.status] >= RANK[prev.status] || isPlaceholder(prev)) {
        slots[same].step = step
      }
      continue
    }
    const inPhasePlaceholder = (s: { key: string; step: PipelineStep }) =>
      s.step.phase === step.phase && isPlaceholder(s.step)
    const first = slots.findIndex(inPhasePlaceholder)
    if (first < 0) {
      // No placeholder to replace, so every slot of this phase is a real step: a late placeholder is stale.
      if (isPlaceholder(step) && slots.some((s) => s.step.phase === step.phase)) continue
      slots.push({ key, step })
      continue
    }
    slots[first] = { key, step }
    for (let i = slots.length - 1; i > first; i--) {
      if (inPhasePlaceholder(slots[i])) slots.splice(i, 1)
    }
  }
  return slots.map((s) => s.step)
}
