import type { Citation } from '../api/types'

const REFS_MARKER = '## References'
const LEGACY_REFS_MARKER = '## Nguồn tham khảo'
const CITATION_REF_RE = /\[([DW]\d+)\]/g
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

export function splitCitationRefs(text: string): Array<{ type: 'text'; value: string } | { type: 'ref'; refId: string }> {
  const parts: Array<{ type: 'text'; value: string } | { type: 'ref'; refId: string }> = []
  let lastIndex = 0

  for (const match of text.matchAll(CITATION_REF_RE)) {
    const index = match.index ?? 0
    if (index > lastIndex) {
      parts.push({ type: 'text', value: text.slice(lastIndex, index) })
    }
    parts.push({ type: 'ref', refId: match[1] })
    lastIndex = index + match[0].length
  }

  if (lastIndex < text.length) {
    parts.push({ type: 'text', value: text.slice(lastIndex) })
  }

  return parts
}

export function citationMap(citations: Citation[]): Map<string, Citation> {
  return new Map(citations.map((c) => [c.ref_id, c]))
}
