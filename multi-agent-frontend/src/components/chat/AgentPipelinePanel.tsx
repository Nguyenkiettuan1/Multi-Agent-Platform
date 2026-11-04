import type { PipelineStep } from '../../api/types'
import { MaterialIcon } from '../ui/MaterialIcon'
import { formatAgentName } from '../../lib/format'
import { dedupeSteps } from '../../lib/pipeline'

type Props = {
  steps: PipelineStep[]
  live?: boolean
  defaultExpanded?: boolean
}

// The status icon is aria-hidden, so screen readers get the status from this text instead.
const STATUS_LABEL: Record<PipelineStep['status'], string> = {
  running: 'Running',
  done: 'Done',
  failed: 'Failed',
  skipped: 'Skipped',
}

function stepIcon(status: PipelineStep['status']): string {
  if (status === 'running') return 'progress_activity'
  if (status === 'done') return 'check_circle'
  if (status === 'failed') return 'error'
  return 'remove_circle_outline'
}

function stepIconClass(status: PipelineStep['status']): string {
  if (status === 'running') return 'animate-spin text-primary'
  if (status === 'done') return 'text-status-success'
  if (status === 'failed') return 'text-error'
  return 'text-outline-variant'
}

function agentIcon(agent?: string | null): string {
  if (!agent) return 'settings'
  if (agent.includes('research')) return 'travel_explore'
  if (agent.includes('legal')) return 'gavel'
  if (agent.includes('db')) return 'database'
  if (agent.includes('triage') || agent.includes('planner') || agent.includes('reviewer')) return 'hub'
  return 'smart_toy'
}

export function AgentPipelinePanel({ steps, live = false, defaultExpanded = true }: Props) {
  if (steps.length === 0) return null

  const deduped = dedupeSteps(steps)
  const running = deduped.find((s) => s.status === 'running')

  return (
    <details
      open={defaultExpanded || live}
      className="rounded-lg border border-border-subtle bg-surface-container-low/80"
    >
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-label-md font-medium text-on-surface [&::-webkit-details-marker]:hidden">
        <MaterialIcon name="account_tree" size={18} className="text-primary" />
        {live ? 'Processing' : 'Agent pipeline'}
        {running ? (
          <span className="ml-1 truncate text-label-sm font-normal text-primary">
            — {running.title}
          </span>
        ) : null}
        <MaterialIcon name="expand_more" size={18} className="ml-auto text-on-surface-variant" />
      </summary>

      <ol className="space-y-0 border-t border-border-subtle px-3 py-2">
        {deduped.map((step, index) => (
          <li
            key={`${step.id}-${index}`}
            className="relative flex gap-3 pb-3 last:pb-1"
          >
            {index < deduped.length - 1 ? (
              <span className="absolute left-[9px] top-5 h-[calc(100%-8px)] w-px bg-border-subtle" />
            ) : null}

            <span className="relative z-10 mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-surface-container-lowest">
              <MaterialIcon name={stepIcon(step.status)} size={16} className={stepIconClass(step.status)} />
            </span>

            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={`text-label-md font-medium ${
                    step.status === 'running' ? 'text-primary' : 'text-on-surface'
                  }`}
                >
                  <span className="sr-only">{STATUS_LABEL[step.status]}: </span>
                  {step.title}
                </span>
                {step.agent ? (
                  <span className="inline-flex items-center gap-1 rounded-md border border-border-subtle bg-surface-container-lowest px-1.5 py-0.5 text-[10px] font-medium text-on-surface-variant">
                    <MaterialIcon name={agentIcon(step.agent)} size={12} />
                    {formatAgentName(step.agent)}
                  </span>
                ) : null}
              </div>
              {step.detail ? (
                <p className="mt-0.5 text-label-sm leading-snug text-on-surface-variant">{step.detail}</p>
              ) : null}
            </div>
          </li>
        ))}
      </ol>
    </details>
  )
}
