import type { KnowledgeUploadResult } from '../api/types.ts'

export type EmbeddingState = 'all' | 'partial' | 'none'
export type AzureState = 'indexed' | 'failed' | 'not_configured' | 'not_synced'

// A document with zero chunks has nothing embedded, so it must never read as "all".
export function embeddingState(embedded: number, chunks: number): EmbeddingState {
  if (chunks <= 0 || embedded <= 0) return 'none'
  return embedded >= chunks ? 'all' : 'partial'
}

// azure_indexed is null both when Azure is off and when a document was never synced;
// azure_enabled tells the two apart.
export function azureState(enabled: boolean, indexed: boolean | null | undefined): AzureState {
  if (!enabled) return 'not_configured'
  if (indexed === true) return 'indexed'
  if (indexed === false) return 'failed'
  return 'not_synced'
}

export function azureLabel(state: AzureState): string {
  switch (state) {
    case 'indexed':
      return 'Indexed'
    case 'failed':
      return 'Failed'
    case 'not_configured':
      return 'Not configured'
    case 'not_synced':
      return 'Not synced'
  }
}

export type UploadSummary = { tone: 'success' | 'warning'; message: string }

export function summarizeUpload(result: KnowledgeUploadResult): UploadSummary {
  const stored = result.chunks_stored
  // Older backends only send has_embeddings; treat it as all-or-nothing.
  const embedded = result.embedded_count ?? (result.has_embeddings ? stored : 0)
  const parts: string[] = []
  let warning = false

  if (stored === 0) {
    warning = true
    parts.push('No chunks were stored, so the file produced no searchable content')
  } else if (embedded >= stored && stored > 0) {
    parts.push(`${embedded}/${stored} chunks embedded`)
  } else {
    warning = true
    parts.push(
      embedded === 0
        ? `${embedded}/${stored} chunks embedded, so search cannot find this document yet`
        : `Only ${embedded}/${stored} chunks embedded, so search will miss the rest`,
    )
  }

  const azure = result.azure
  if (azure?.enabled) {
    if (azure.error) {
      warning = true
      parts.push(`Azure Search indexing failed: ${azure.error}`)
    } else if (azure.indexed < azure.total) {
      warning = true
      parts.push(`only ${azure.indexed}/${azure.total} chunks indexed in Azure`)
    } else {
      parts.push('indexed in Azure')
    }
  } else if (azure) {
    parts.push('Azure Search not configured')
  }

  return { tone: warning ? 'warning' : 'success', message: parts.join(' · ') }
}

export function uploadedDocId(result: { parent_doc_id?: string | null; doc_id?: string | null }): string | null {
  return result.parent_doc_id ?? result.doc_id ?? null
}

export type PageInfo = {
  from: number
  to: number
  page: number
  pages: number
  hasPrev: boolean
  hasNext: boolean
}

// Start offset of the last page that has rows (0 when empty).
export function lastValidOffset(total: number, limit: number): number {
  return Math.max(0, Math.ceil(total / limit) - 1) * limit
}

export function pageInfo(requestedOffset: number, limit: number, total: number): PageInfo {
  // A delete can leave the requested offset past the end; describe the last real page instead.
  const offset = Math.min(requestedOffset, lastValidOffset(total, limit))
  const pages = Math.max(1, Math.ceil(total / limit))
  return {
    from: total === 0 ? 0 : offset + 1,
    to: Math.min(total, offset + limit),
    page: Math.floor(offset / limit) + 1,
    pages,
    hasPrev: offset > 0,
    hasNext: offset + limit < total,
  }
}

export function removalScope(azureEnabled: boolean): string {
  return azureEnabled ? 'the database and Azure Search' : 'the database'
}

export function deleteSuccessMessage(title: string, azureEnabled: boolean): string {
  return `Deleted "${title}" from ${removalScope(azureEnabled)}.`
}

export function deleteFailureMessage(
  status: number | undefined,
  detail: string,
  context: 'list' | 'detail',
): { text: string; refresh: boolean } {
  if (status === 502) {
    return {
      text: `Azure Search could not remove this document. Nothing was deleted, so you can try again. (${detail})`,
      refresh: false,
    }
  }
  if (status === 404) {
    return {
      text: `This document was already deleted.${context === 'list' ? ' The list has been refreshed.' : ''}`,
      refresh: true,
    }
  }
  return { text: `Delete failed: ${detail}`, refresh: false }
}
