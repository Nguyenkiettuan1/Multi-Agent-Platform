import { useState } from 'react'
import type { Citation } from '../../api/types'

type Props = {
  citation: Citation
}

export function CitationBadge({ citation }: Props) {
  const [open, setOpen] = useState(false)
  const isWeb = citation.ref_id.startsWith('W')

  const handleClick = () => {
    if (citation.url) {
      window.open(citation.url, '_blank', 'noopener,noreferrer')
    }
  }

  return (
    <span
      className="relative mx-0.5 inline-block align-super"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        onClick={handleClick}
        title={citation.title}
        className={`inline-flex h-[18px] min-w-[18px] cursor-pointer items-center justify-center rounded px-1 text-[10px] font-bold leading-none transition-colors ${
          isWeb
            ? 'bg-orange-100 text-citation-web hover:bg-orange-200'
            : 'bg-blue-100 text-citation-knowledge hover:bg-blue-200'
        }`}
      >
        {citation.ref_id}
      </button>

      {open && (
        <span
          role="tooltip"
          className="absolute bottom-full left-1/2 z-30 mb-2 w-72 -translate-x-1/2 rounded-lg border border-border-subtle bg-surface-container-lowest p-3 text-left shadow-lg"
        >
          <span className="block text-label-sm font-semibold text-on-surface">{citation.title}</span>
          {citation.excerpt ? (
            <span className="mt-1 block line-clamp-3 text-label-sm text-on-surface-variant">{citation.excerpt}</span>
          ) : null}
          {citation.url ? (
            <span className="mt-2 block truncate text-label-sm text-primary underline">{citation.url}</span>
          ) : null}
        </span>
      )}
    </span>
  )
}
