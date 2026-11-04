export type ChatTurn = {
  trace_id: string
  session_id?: string | null
  user_message: string
  response: string
  rating?: number | null
  eval_score?: number | null
  created_at?: string | null
  /** Absent before the backend records it; treat missing as 'completed'. */
  status?: 'completed' | 'failed' | 'incomplete'
}

export type ChatSessionSummary = {
  session_id: string
  title: string
  updated_at?: string | null
}

export type ChatSessionsResponse = {
  items: ChatSessionSummary[]
  count: number
}

export type ChatHistoryResponse = {
  session_id: string
  turns: ChatTurn[]
  count: number
  has_more: boolean
  next_before: string | null
}

export type ChatAttachment = {
  filename: string
  mime_type: string
  data: string
}

export type ChatRequest = {
  message: string
  session_id?: string | null
  user_id?: string
  attachments?: ChatAttachment[]
}

export type PipelineStep = {
  id: string
  phase: string
  agent?: string | null
  status: 'running' | 'done' | 'skipped' | 'failed'
  title: string
  detail?: string
  tools?: string[]
}

export type ChatResponse = {
  trace_id: string
  session_id: string
  triage: Record<string, unknown> | null
  topology_mode: string | null
  plan: Record<string, unknown> | null
  worker_results: WorkerResult[]
  review_status: string | null
  eval: Record<string, unknown> | null
  response: string
  redacted_types: string[]
  citations: Citation[]
  pipeline: PipelineStep[]
  model_usage: Record<string, unknown>[]
}

export type WorkerResult = {
  task_id: string
  agent: string
  summary: string
  success: boolean
  sources: string[]
  citations: Citation[]
  tools_called: string[]
}

export type Citation = {
  ref_id: string
  title: string
  excerpt: string
  source_type: string
  backend: string
  url?: string | null
  doc_id?: string | null
  score?: number | null
}

export type FeedbackRequest = {
  trace_id: string
  rating: number
  comment?: string
}

export type AdminOverview = {
  service: string
  version: string
  capabilities: {
    llm: boolean
    embeddings: boolean
    azure_search: boolean
    web_search: boolean
    tracing: boolean
    rrf_fusion: boolean
  }
  counts: Record<string, number>
  recent_feedback: FeedbackRecord[]
  recent_audit: AuditRecord[]
}

export type FeedbackRecord = {
  trace_id: string
  session_id?: string | null
  user_message: string
  response: string
  rating: number | null
  comment?: string | null
  eval_score: number | null
  created_at?: string | null
}

export type AuditRecord = {
  id?: number
  trace_id: string
  session_id?: string | null
  user_id?: string | null
  agent_name?: string | null
  action: string
  payload?: Record<string, unknown> | null
  sql_executed?: string | null
  created_at?: string | null
}

export type KnowledgeDocumentSummary = {
  doc_id: string
  title: string
  domain: string
  source: string
  chunk_count: number
  embedded_count: number
  content_length: number
  azure_indexed: boolean | null
  created_at?: string | null
  updated_at?: string | null
}

export type KnowledgeDocumentList = {
  items: KnowledgeDocumentSummary[]
  total: number
  azure_enabled: boolean
}

export type KnowledgeChunk = {
  doc_id: string
  chunk_index: number | null
  char_count: number
  has_embedding: boolean
  content: string
}

export type KnowledgeDocumentDetail = {
  doc_id: string
  title: string
  domain: string
  source: string
  chunk_count: number
  embedded_count: number
  azure_enabled: boolean
  azure_indexed: boolean | null
  content: string
  chunks: KnowledgeChunk[]
}

export type KnowledgeDeleteResult = {
  doc_id: string
  deleted_rows: number
  azure: { enabled: boolean; deleted: number; error: string | null }
}

export type KnowledgeUploadResult = {
  status?: string
  parent_doc_id?: string | null
  doc_id?: string | null
  chunks_stored: number
  embedded_count?: number
  has_embeddings?: boolean
  azure?: { enabled: boolean; indexed: number; total: number; error: string | null }
}

export type ModelsResponse = {
  catalog: ModelCatalogItem[]
  agents: Record<string, AgentModelConfig>
  pipeline: Record<string, PipelineModelConfig>
  llm_enabled: boolean
}

export type ModelCatalogItem = {
  ref: string
  provider: string
  model_id: string
  tags: string[]
  description?: string
}

export type AgentModelConfig = {
  model: string
  source: string
  fallback_chain: string[]
}

export type PipelineModelConfig = {
  model: string
  source: string
}

export type HealthResponse = {
  status: string
  service: string
  version: string
  graph_ready: boolean
}

export type ListResponse<T> = {
  items: T[]
  count: number
}
