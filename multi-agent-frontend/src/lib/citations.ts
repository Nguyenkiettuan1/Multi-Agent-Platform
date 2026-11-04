import type { Citation } from '../api/types'

const REFS_MARKER = '## References'
const LEGACY_REFS_MARKER = '## Nguồn tham khảo'
const FENCE_RE = /^ {0,3}(`{3,}|~{3,})/
// Code spans come first in the alternation so a ref inside backticks is consumed as code, not as a ref.
const CODE_OR_REF_RE = /(`+)(.+?)\1(?!`)|(!?)\[([DW]\d+)\](?!\()/g
const REF_LINE_RE = /-\s*\*\*\[([DW]\d+)\]\*\*\s*(.+?)\s*—\s*(https?:\/\/\S+)/g

export function stripReferencesBlock(text: string): string {
  for (const marker of [REFS_MARKER, LEGACY_REFS_MARKER]) {
    const idx = text.indexOf(marker)
    if (idx >= 0) {
      return text.slice(0, idx).trimEnd()
    }
  }
  return text
}

/** Remove legacy fallback that dumped raw [W1] title — url blocks into the body. */
export function stripRawSourceDump(text: string): string {
  const lines = text.split('\n')
  const out: string[] = []
  let skipping = false

  for (const line of lines) {
    if (/^(?:Found \d+ sources|Đã tìm thấy \d+ nguồn)/i.test(line.trim())) {
      skipping = true
      continue
    }
    if (/^\[[DW]\d+\]\s/.test(line.trim())) {
      skipping = true
      continue
    }
    if (skipping && line.trim() === '') {
      continue
    }
    skipping = false
    out.push(line)
  }

  return out.join('\n').trimEnd()
}

/** Parse legacy responses that embedded sources in the body. */
export function parseCitationsFromResponse(content: string): { body: string; citations: Citation[] } {
  const markerIdx = [REFS_MARKER, LEGACY_REFS_MARKER]
    .map((marker) => content.indexOf(marker))
    .find((idx) => idx >= 0)

  if (markerIdx === undefined) {
    return { body: stripRawSourceDump(stripReferencesBlock(content)), citations: [] }
  }

  const body = stripRawSourceDump(content.slice(0, markerIdx).trimEnd())
  const refsSection = content.slice(markerIdx)
  const citations: Citation[] = []

  for (const match of refsSection.matchAll(REF_LINE_RE)) {
    const [, refId, title, url] = match
    citations.push({
      ref_id: refId,
      title: title.trim(),
      excerpt: '',
      source_type: refId.startsWith('W') ? 'web' : 'knowledge',
      backend: refId.startsWith('W') ? 'web_search' : 'knowledge',
      url,
    })
  }

  return { body, citations }
}

// A character is already escaped when an odd number of backslashes precedes it (`\\` is an escaped backslash).
function isEscaped(line: string, index: number): boolean {
  let backslashes = 0
  while (line[index - 1 - backslashes] === '\\') backslashes++
  return backslashes % 2 === 1
}

/**
 * Rewrite `[D1]` refs into markdown links (`[D1](#cite-D1)`) so the whole answer can go through a single
 * markdown parse; splitting the text first would break paragraphs, lists and blockquotes. Every ref is
 * linked, known or not: the renderer decides what to show for a ref without a citation (restored chats
 * have none). A `!` right before a ref is escaped, otherwise `![D1](...)` would parse as an image.
 *
 * Line-based scanner; known limits (not handled): fences inside blockquotes or 4-space list items,
 * indented code blocks, code spans that cross lines, `[D1]: url` definitions, and a bare URL glued to a ref.
 */
export function linkCitationRefs(body: string): string {
  let fence: { char: string; length: number } | null = null

  return body
    .split('\n')
    .map((line) => {
      const open = FENCE_RE.exec(line)
      if (fence) {
        if (open && open[1][0] === fence.char && open[1].length >= fence.length && line.trim() === open[1]) fence = null
        return line
      }
      if (open) {
        fence = { char: open[1][0], length: open[1].length }
        return line
      }
      return line.replace(
        CODE_OR_REF_RE,
        (match, _ticks, _code, bang: string | undefined, refId: string | undefined, offset: number) => {
          if (!refId) return match
          // `\[D1]` is literal text the author escaped on purpose; linking it would print the link syntax.
          if (!bang && isEscaped(line, offset)) return match
          const prefix = bang ? (isEscaped(line, offset) ? '!' : '\\!') : ''
          return `${prefix}[${refId}](#cite-${refId})`
        },
      )
    })
    .join('\n')
}

export function citationMap(citations: Citation[]): Map<string, Citation> {
  return new Map(citations.map((c) => [c.ref_id, c]))
}
