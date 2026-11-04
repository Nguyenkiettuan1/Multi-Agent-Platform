import { getApiKey } from '../lib/storage'
import type {
  AdminOverview,
  ChatHistoryResponse,
  ChatRequest,
  ChatResponse,
  ChatSessionsResponse,
  FeedbackRequest,
  HealthResponse,
  KnowledgeDeleteResult,
  KnowledgeDocumentDetail,
  KnowledgeDocumentList,
  KnowledgeUploadResult,
  ListResponse,
  ModelsResponse,
  PipelineStep,
  AuditRecord,
  FeedbackRecord,
} from './types'

class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function parseError(res: Response): Promise<string> {
  const text = await res.text()
  if (!text) return res.statusText || `HTTP ${res.status}`
  try {
    const json = JSON.parse(text) as { detail?: unknown }
    if (typeof json.detail === 'string') return json.detail
    if (json.detail) return JSON.stringify(json.detail)
  } catch {
    /* plain text */
  }
  return text
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  const apiKey = getApiKey()
  if (apiKey) headers.set('X-API-Key', apiKey)

  const body = options.body
  if (body && !(body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const res = await fetch(path, { ...options, headers })
  if (!res.ok) {
    throw new ApiError(await parseError(res), res.status)
  }

  const contentType = res.headers.get('content-type') ?? ''
  if (contentType.includes('application/json')) {
    return res.json() as Promise<T>
  }
  return res.text() as Promise<T>
}

export const api = {
  health: () => request<HealthResponse>('/health'),

  chat: (body: ChatRequest) =>
    request<ChatResponse>('/api/v1/chat', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  chatStream: async function* (
    body: ChatRequest,
    onStep?: (step: PipelineStep) => void,
  ): AsyncGenerator<ChatResponse, void, unknown> {
    const headers = new Headers({ 'Content-Type': 'application/json' })
    const apiKey = getApiKey()
    if (apiKey) headers.set('X-API-Key', apiKey)

    const res = await fetch('/api/v1/chat/stream', {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    })

    if (!res.ok) {
      throw new ApiError(await parseError(res), res.status)
    }

    const reader = res.body?.getReader()
    if (!reader) {
      throw new ApiError('Stream unavailable', 500)
    }

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split('\n\n')
      buffer = parts.pop() ?? ''

      for (const part of parts) {
        const lines = part.split('\n')
        let event = 'message'
        let data = ''
        for (const line of lines) {
          if (line.startsWith('event:')) event = line.slice(6).trim()
          if (line.startsWith('data:')) data += line.slice(5).trim()
        }
        if (!data) continue

        const payload = JSON.parse(data) as Record<string, unknown>
        if (event === 'step') {
          onStep?.(payload as PipelineStep)
        } else if (event === 'complete') {
          yield payload as ChatResponse
        } else if (event === 'error') {
          throw new ApiError(String(payload.message ?? 'Stream error'), 500)
        }
      }
    }
  },

  chatHistory: (sessionId: string, opts: { limit?: number; before?: string } = {}) => {
    const params = new URLSearchParams({ session_id: sessionId, limit: String(opts.limit ?? 50) })
    if (opts.before) params.set('before', opts.before)
    return request<ChatHistoryResponse>(`/api/v1/chat/history?${params}`)
  },

  chatSessions: (limit = 30) =>
    request<ChatSessionsResponse>(`/api/v1/chat/sessions?limit=${limit}`),

  submitFeedback: (body: FeedbackRequest) =>
    request<{ status: string; trace_id: string }>('/api/v1/feedback', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  adminOverview: () => request<AdminOverview>('/api/v1/admin/overview'),

  adminKnowledgeDocuments: (params?: { limit?: number; offset?: number; domain?: string }) => {
    const search = new URLSearchParams()
    if (params?.limit) search.set('limit', String(params.limit))
    if (params?.offset) search.set('offset', String(params.offset))
    if (params?.domain) search.set('domain', params.domain)
    const qs = search.toString()
    return request<KnowledgeDocumentList>(`/api/v1/admin/knowledge/documents${qs ? `?${qs}` : ''}`)
  },

  adminKnowledgeDocument: (docId: string) =>
    request<KnowledgeDocumentDetail>(`/api/v1/admin/knowledge/documents/${encodeURIComponent(docId)}`),

  deleteKnowledgeDocument: (docId: string) =>
    request<KnowledgeDeleteResult>(`/api/v1/admin/knowledge/documents/${encodeURIComponent(docId)}`, {
      method: 'DELETE',
    }),

  adminFeedback: (params?: { limit?: number; min_rating?: number }) => {
    const search = new URLSearchParams()
    if (params?.limit) search.set('limit', String(params.limit))
    if (params?.min_rating != null) search.set('min_rating', String(params.min_rating))
    const qs = search.toString()
    return request<ListResponse<FeedbackRecord>>(`/api/v1/admin/feedback${qs ? `?${qs}` : ''}`)
  },

  adminAudit: (params?: { limit?: number; trace_id?: string }) => {
    const search = new URLSearchParams()
    if (params?.limit) search.set('limit', String(params.limit))
    if (params?.trace_id) search.set('trace_id', params.trace_id)
    const qs = search.toString()
    return request<ListResponse<AuditRecord>>(`/api/v1/admin/audit${qs ? `?${qs}` : ''}`)
  },

  models: () => request<ModelsResponse>('/api/v1/models'),

  exportFeedback: async (params?: { min_rating?: number; format?: string }) => {
    const search = new URLSearchParams()
    if (params?.min_rating != null) search.set('min_rating', String(params.min_rating))
    if (params?.format) search.set('format', params.format)
    const qs = search.toString()
    const headers = new Headers()
    const apiKey = getApiKey()
    if (apiKey) headers.set('X-API-Key', apiKey)
    const res = await fetch(`/api/v1/admin/feedback/export${qs ? `?${qs}` : ''}`, { headers })
    if (!res.ok) throw new ApiError(await parseError(res), res.status)
    return res.blob()
  },

  uploadKnowledge: (file: File, options?: { domain?: string; preview_only?: boolean }) => {
    const form = new FormData()
    form.append('file', file)
    if (options?.domain) form.append('domain', options.domain)
    if (options?.preview_only) form.append('preview_only', 'true')
    return request<KnowledgeUploadResult>('/api/v1/admin/knowledge/upload', {
      method: 'POST',
      body: form,
    })
  },
}

export { ApiError }
