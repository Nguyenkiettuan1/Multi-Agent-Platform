import { createContext, useContext, useMemo } from 'react'
import type { ComponentProps } from 'react'
import type { Components } from 'react-markdown'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Citation } from '../../api/types'
import { citationMap, linkCitationRefs, parseCitationsFromResponse, stripReferencesBlock } from '../../lib/citations'
import { CitationBadge, UnknownCitationChip } from './CitationBadge'

type Props = {
  content: string
  citations?: Citation[]
}

// Only this exact shape is a citation; any other `#cite-…` (even an empty one) is not ours to turn into a chip.
const CITE_HREF_RE = /^#cite-([DW]\d+)$/

// Everything handed to ReactMarkdown below is module-level on purpose: a new component function per render
// changes the element type, so React remounts the whole markdown subtree on every parent re-render
// (composer keystroke, pipeline event) and loses text selection, badge focus and open tooltips.
const CitationRefsContext = createContext<ReadonlyMap<string, Citation>>(new Map())

const remarkPlugins = [remarkGfm]

function MarkdownLink({ href, children }: ComponentProps<'a'>) {
  const refs = useContext(CitationRefsContext)
  const refId = href ? CITE_HREF_RE.exec(href)?.[1] : undefined
  if (refId) {
    const cite = refs.get(refId)
    return cite ? <CitationBadge citation={cite} /> : <UnknownCitationChip refId={refId} />
  }
  if (href?.startsWith('#cite-')) return <>{children}</>
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary underline hover:opacity-80">
      {children}
    </a>
  )
}

const markdownComponents: Components = {
  p: ({ children }) => <p className="mb-3 last:mb-0 leading-relaxed">{children}</p>,
  ul: ({ children }) => <ul className="mb-3 list-disc space-y-1 pl-5 last:mb-0">{children}</ul>,
  ol: ({ children }) => <ol className="mb-3 list-decimal space-y-1 pl-5 last:mb-0">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-on-surface">{children}</strong>,
  h2: ({ children }) => <h2 className="mb-2 mt-4 text-title-md font-semibold text-on-surface first:mt-0">{children}</h2>,
  h3: ({ children }) => <h3 className="mb-2 mt-3 text-title-sm font-semibold text-on-surface first:mt-0">{children}</h3>,
  blockquote: ({ children }) => (
    <blockquote className="mb-3 rounded-r-md border-l border-border-subtle bg-surface-container-low px-4 py-2 text-on-surface-variant last:mb-0">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-4 border-border-subtle" />,
  // Block code is styled on <pre>; its inner <code> resets the inline styling below.
  pre: ({ children }) => (
    <pre className="mb-3 overflow-x-auto rounded-lg border border-border-subtle bg-surface-container-low p-3 text-body-code font-body-code text-on-surface last:mb-0 [&_code]:rounded-none [&_code]:bg-transparent [&_code]:p-0">
      {children}
    </pre>
  ),
  code: ({ children, className }) => (
    <code className={`rounded bg-surface-container px-1 py-0.5 text-body-code font-body-code ${className ?? ''}`}>
      {children}
    </code>
  ),
  table: ({ children }) => (
    <div className="mb-3 overflow-x-auto last:mb-0">
      <table className="w-full border-collapse text-left text-body-md tabular-nums">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-surface-container-low">{children}</thead>,
  th: ({ children }) => (
    <th className="border border-border-subtle px-3 py-2 text-label-md font-semibold text-on-surface">{children}</th>
  ),
  td: ({ children }) => <td className="border border-border-subtle px-3 py-2 align-top">{children}</td>,
  a: MarkdownLink,
}

export function ChatMessageBody({ content, citations }: Props) {
  const { body, refs } = useMemo(() => {
    const parsed = citations && citations.length > 0
      ? { body: stripReferencesBlock(content), citations }
      : parseCitationsFromResponse(content)
    return { body: linkCitationRefs(parsed.body), refs: citationMap(parsed.citations) }
  }, [content, citations])

  return (
    <div className="text-body-lg text-on-surface">
      <CitationRefsContext value={refs}>
        <ReactMarkdown remarkPlugins={remarkPlugins} components={markdownComponents}>
          {body}
        </ReactMarkdown>
      </CitationRefsContext>
    </div>
  )
}
