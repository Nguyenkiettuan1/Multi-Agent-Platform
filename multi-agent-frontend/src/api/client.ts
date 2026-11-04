import { sessionIdFromErrorPayload } from '../lib/chatHistory'
import { AUTH_UNAUTHORIZED_EVENT, parseResponseBody, parseRetryAfter } from '../lib/auth'
import type {
  AdminOverview,
  AdminUser,
  AdminUsersResponse,
  AuthMe,
  ChatHistoryResponse,
  ChatRequest,
  ChatResponse,
  ChatSessionsResponse,
  CreateUserRequest,
  FeedbackRequest,
  HealthResponse,
  KnowledgeDeleteResult,
  KnowledgeDocumentDetail,
  KnowledgeDocumentList,
  KnowledgeUploadResult,
  ListResponse,
  ModelsResponse,
  PipelineStep,
  User,
  AuditRecord,
  FeedbackRecord,
} from './types'

class ApiError extends Error {
  status: number
  /** Seconds from the Retry-After header (429), when the server sent one. */
  retryAfter: number | null
  /** Set when a chat call failed after the server had already created the session (see sessionIdFromErrorPayload). */
  sessionId: string | null

  constructor(message: string, status: number, retryAfter: number | null = null, sessionId: string | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.retryAfter = retryAfter
    this.sessionId = sessionId
  }
}

// Cookie auth needs this header on every call: the server demands it on unsafe methods (CSRF, D7), and a
// custom header cannot be sent cross-site without a CORS preflight. Sent on GETs too so no call is forgotten.
const CSRF_HEADERS = { 'X-Requested-With': 'XMLHttpRequest' }

type FailureOptions = {
  /** The login call: 401 there means "wrong credentials", not "session expired". */
  credentials401?: boolean
}

async function toApiError(res: Response, opts: FailureOptions = {}): Promise<ApiError> {
  const text = await res.text()
  const error = new ApiError(
    parseError(res, text),
    res.status,
    parseRetryAfter(res.headers.get('Retry-After')),
    sessionIdFromErrorPayload(parseJson(text)),
  )
  if (res.status === 401 && !opts.credentials401) {
    window.dispatchEvent(new Event(AUTH_UNAUTHORIZED_EVENT))
  }
  return error
}

function parseJson(text: string): unknown {
  try {
    return JSON.parse(text)
  } catch {
    return undefined
  }
}

function parseError(res: Response, text: string): string {
  if (!text) return res.statusText || `HTTP ${res.status}`
  const json = parseJson(text) as { detail?: unknown } | undefined
  if (json && typeof json === 'object') {
    if (typeof json.detail === 'string') return json.detail
    if (json.detail) return JSON.stringify(json.detail)
  }
  return text
}

async function request<T>(path: string, options: RequestInit = {}, failure: FailureOptions = {}): Promise<T> {
  const headers = new Headers(options.headers)
  for (const [name, value] of Object.entries(CSRF_HEADERS)) headers.set(name, value)

  const body = options.body
  if (body && !(body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const res = await fetch(path, { ...options, headers })
  if (!res.ok) {
    throw await toApiError(res, failure)
  }

  return parseResponseBody(res.status, res.headers.get('content-type') ?? '', await res.text()) as T
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
    const headers = new Headers({ 'Content-Type': 'application/json', ...CSRF_HEADERS })

    const res = await fetch('/api/v1/chat/stream', {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    })

    if (!res.ok) {
      throw await toApiError(res)
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
          throw new ApiError(String(payload.message ?? 'Stream error'), 500, null, sessionIdFromErrorPayload(payload))
        }
      }
    }
  },

  chatHistory: (sessionId: string, opts: { limit?: number; before?: string } = {}) => {
    const params = new URLSearchParams({ session_id: sessionId, limit: String(opts.limit ?? 50) })
    if (opts.before) params.set('before', opts.before)
    return request<ChatHistoryResponse>(`/api/v1/chat/history?${params}`)
  },

  chatSessions: ({ limit = 30, before }: { limit?: number; before?: string } = {}) => {
    const params = new URLSearchParams({ limit: String(limit) })
    if (before) params.set('before', before)
    return request<ChatSessionsResponse>(`/api/v1/chat/sessions?${params}`)
  },

  login: (email: string, password: string) =>
    request<{ user: User }>(
      '/api/v1/auth/login',
      { method: 'POST', body: JSON.stringify({ email, password }) },
      { credentials401: true },
    ),

  logout: () => request<void>('/api/v1/auth/logout', { method: 'POST' }),

  me: () => request<AuthMe>('/api/v1/auth/me'),

  changePassword: (currentPassword: string, newPassword: string) =>
    request<void>('/api/v1/auth/password', {
      method: 'POST',
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    }),

  adminUsers: (params?: { limit?: number; offset?: number }) => {
    const search = new URLSearchParams()
    if (params?.limit) search.set('limit', String(params.limit))
    if (params?.offset) search.set('offset', String(params.offset))
    const qs = search.toString()
    return request<AdminUsersResponse>(`/api/v1/admin/users${qs ? `?${qs}` : ''}`)
  },

  createUser: (body: CreateUserRequest) =>
    request<User>('/api/v1/admin/users', { method: 'POST', body: JSON.stringify(body) }),

  setUserActive: (userId: string, isActive: boolean) =>
    request<AdminUser>(`/api/v1/admin/users/${encodeURIComponent(userId)}`, {
      method: 'PATCH',
      body: JSON.stringify({ is_active: isActive }),
    }),

  resetUserPassword: (userId: string, password: string) =>
    request<void>(`/api/v1/admin/users/${encodeURIComponent(userId)}/password`, {
      method: 'POST',
      body: JSON.stringify({ password }),
    }),

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
    const res = await fetch(`/api/v1/admin/feedback/export${qs ? `?${qs}` : ''}`, { headers: CSRF_HEADERS })
    if (!res.ok) throw await toApiError(res)
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
