import type { ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import type { Citation } from '../../api/types'
import { citationMap, parseCitationsFromResponse, splitCitationRefs, stripReferencesBlock } from '../../lib/citations'
import { CitationBadge } from './CitationBadge'

type Props = {
  content: string
  citations?: Citation[]
}

const markdownComponents = {
  p: ({ children }: { children?: ReactNode }) => (
    <p className="mb-3 last:mb-0 leading-relaxed">{children}</p>
  ),
  ul: ({ children }: { children?: ReactNode }) => (
    <ul className="mb-3 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>
  ),
  ol: ({ children }: { children?: ReactNode }) => (
    <ol className="mb-3 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>
  ),
  li: ({ children }: { children?: ReactNode }) => <li className="leading-relaxed">{children}</li>,
  strong: ({ children }: { children?: ReactNode }) => (
    <strong className="font-semibold text-on-surface">{children}</strong>
  ),
  h2: ({ children }: { children?: ReactNode }) => (
    <h2 className="mb-2 mt-4 text-title-md font-semibold text-on-surface first:mt-0">{children}</h2>
  ),
  h3: ({ children }: { children?: ReactNode }) => (
    <h3 className="mb-2 mt-3 text-title-sm font-semibold text-on-surface first:mt-0">{children}</h3>
  ),
  a: ({ href, children }: { href?: string; children?: ReactNode }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary underline hover:opacity-80">
      {children}
    </a>
  ),
}

function renderMarkdownChunk(text: string, key: string) {
  const trimmed = text.trim()
  if (!trimmed) return null
  return (
    <ReactMarkdown key={key} components={markdownComponents}>
      {trimmed}
    </ReactMarkdown>
  )
}

export function ChatMessageBody({ content, citations = [] }: Props) {
  const parsed = citations.length > 0
    ? { body: stripReferencesBlock(content), citations }
    : parseCitationsFromResponse(content)

  const refs = citationMap(parsed.citations)
  const parts = splitCitationRefs(parsed.body)

  return (
    <div className="text-body-lg text-on-surface">
      {parts.map((part, i) => {
        if (part.type === 'ref') {
          const cite = refs.get(part.refId)
          if (cite) {
            return <CitationBadge key={`${part.refId}-${i}`} citation={cite} />
          }
          return (
            <span
              key={`${part.refId}-${i}`}
              className="mx-0.5 inline-flex h-[18px] min-w-[18px] items-center justify-center rounded bg-slate-100 px-1 text-[10px] font-bold text-slate-600"
            >
              {part.refId}
            </span>
          )
        }
        return renderMarkdownChunk(part.value, `md-${i}`)
      })}
    </div>
  )
}
