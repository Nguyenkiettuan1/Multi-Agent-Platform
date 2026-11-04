import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import type { Citation } from '../../api/types'

type Props = {
  citation: Citation
}

// The raw citation tokens fail 4.5:1 on their own tint (web 3.07, knowledge 4.37), so the chip uses the
// darkened text / tint tokens from index.css. Contrast: knowledge 6.68 / 6.31 (rest / hover), web 4.99 / 4.75.
const TONE = {
  web: 'bg-citation-web-tint text-citation-web-text hover:bg-citation-web-tint-hover',
  knowledge: 'bg-citation-knowledge-tint text-citation-knowledge-text hover:bg-citation-knowledge-tint-hover',
}

// Same size and shape as the badge but not interactive: used when the answer cites a ref we have no
// citation for (e.g. restored history carries no citations). on-surface-variant on surface-container is 8.05:1.
export function UnknownCitationChip({ refId }: { refId: string }) {
  return (
    <span className="ml-0.5 inline-flex min-w-[1.375rem] items-center justify-center whitespace-nowrap rounded bg-surface-container px-1.5 align-baseline text-label-sm text-on-surface-variant">
      {refId}
    </span>
  )
}

const VIEWPORT_MARGIN = 8

type TooltipPos = { top: number; left: number; below: boolean }

export function CitationBadge({ citation }: Props) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState<TooltipPos | null>(null)
  const tooltipId = useId()
  const buttonRef = useRef<HTMLButtonElement>(null)
  const tooltipRef = useRef<HTMLSpanElement>(null)
  const isWeb = citation.ref_id.startsWith('W')

  const handleClick = () => {
    if (citation.url) {
      window.open(citation.url, '_blank', 'noopener,noreferrer')
    }
  }

  // The tooltip is position:fixed so a scrolling ancestor (the table wrapper's overflow-x:auto clips y too)
  // cannot cut it off. It is placed above the badge, flipped below when there is no room, and clamped to the viewport.
  useLayoutEffect(() => {
    const button = buttonRef.current
    const tooltip = tooltipRef.current
    if (!open || !button || !tooltip) return
    const anchor = button.getBoundingClientRect()
    const { offsetWidth: width, offsetHeight: height } = tooltip
    const below = anchor.top - height < VIEWPORT_MARGIN
    const maxLeft = Math.max(VIEWPORT_MARGIN, window.innerWidth - width - VIEWPORT_MARGIN)
    setPos({
      top: below ? anchor.bottom : anchor.top - height,
      left: Math.min(Math.max(anchor.left + anchor.width / 2 - width / 2, VIEWPORT_MARGIN), maxLeft),
      below,
    })
  }, [open])

  // Fixed coordinates go stale as soon as the page moves, so close instead of tracking.
  useEffect(() => {
    if (!open) return
    const close = () => setOpen(false)
    window.addEventListener('scroll', close, true)
    window.addEventListener('resize', close)
    return () => {
      window.removeEventListener('scroll', close, true)
      window.removeEventListener('resize', close)
    }
  }, [open])

  return (
    <span
      className="ml-0.5 inline-block align-baseline"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      onKeyDown={(e) => {
        if (e.key === 'Escape') setOpen(false)
      }}
    >
      <button
        ref={buttonRef}
        type="button"
        onClick={handleClick}
        aria-label={`Source ${citation.ref_id}`}
        aria-describedby={tooltipId}
        className={`inline-flex min-w-[1.375rem] cursor-pointer items-center justify-center whitespace-nowrap rounded px-1.5 text-label-sm transition-colors ${
          isWeb ? TONE.web : TONE.knowledge
        }`}
      >
        {citation.ref_id}
      </button>

      {/* Always mounted (just hidden) so aria-describedby never points at a missing node; the padding on the
          badge side bridges the gap, and as a DOM child of the hover region it keeps the tooltip open while
          the pointer moves onto it. */}
      <span
        ref={tooltipRef}
        id={tooltipId}
        role="tooltip"
        style={pos ? { top: pos.top, left: pos.left } : undefined}
        className={`${open ? 'block' : 'hidden'} fixed z-30 w-72 max-w-[calc(100vw-1rem)] ${pos?.below ? 'pt-2' : 'pb-2'}`}
      >
        <span className="block rounded-lg border border-border-subtle bg-surface-container-lowest p-3 text-left shadow-lg">
          <span className="block text-label-sm font-semibold text-on-surface">{citation.title}</span>
          {citation.excerpt ? (
            <span className="mt-1 block line-clamp-3 text-label-sm text-on-surface-variant">{citation.excerpt}</span>
          ) : null}
          {citation.url ? (
            <span className="mt-2 block truncate text-label-sm text-primary underline">{citation.url}</span>
          ) : null}
        </span>
      </span>
    </span>
  )
}
