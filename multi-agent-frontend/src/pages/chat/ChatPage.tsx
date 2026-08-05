import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../../api/client'
import type { ChatResponse, Citation, PipelineStep } from '../../api/types'
import { AgentPipelinePanel } from '../../components/chat/AgentPipelinePanel'
import { ChatMessageBody } from '../../components/chat/ChatMessageBody'
import { MaterialIcon } from '../../components/ui/MaterialIcon'
import { formatAgentName, truncate } from '../../lib/format'
import { parseCitationsFromResponse } from '../../lib/citations'
import { upsertChatSession } from '../../lib/storage'

type ChatMessage =
  | { id: string; role: 'user'; content: string; imagePreview?: string; imageName?: string }
  | {
      id: string
      role: 'assistant'
      content: string
      traceId: string
      agent?: string
      topologyMode?: string | null
      pipeline: PipelineStep[]
      citations: Citation[]
      rating?: number
    }

function agentIcon(agent?: string): string {
  if (!agent) return 'smart_toy'
  if (agent.includes('legal')) return 'gavel'
  if (agent.includes('research')) return 'travel_explore'
  if (agent.includes('db')) return 'database'
  return 'support_agent'
}

const MAX_IMAGE_BYTES = 4 * 1024 * 1024
const IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/webp', 'image/gif']

async function fileToAttachment(file: File) {
  if (!IMAGE_TYPES.includes(file.type)) {
    throw new Error('Only PNG, JPEG, WebP, or GIF images are supported')
  }
  if (file.size > MAX_IMAGE_BYTES) {
    throw new Error('Image must be 4MB or smaller')
  }
  const dataUrl = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(new Error('Could not read file'))
    reader.readAsDataURL(file)
  })
  const base64 = dataUrl.includes(',') ? dataUrl.split(',')[1] : dataUrl
  return {
    attachment: { filename: file.name, mime_type: file.type, data: base64 },
    preview: dataUrl,
  }
}

function turnsToMessages(turns: Array<{
  trace_id: string
  user_message: string
  response: string
  rating?: number | null
}>): ChatMessage[] {
  const restored: ChatMessage[] = []
  for (const turn of turns) {
    restored.push({ id: `${turn.trace_id}-user`, role: 'user', content: turn.user_message })
    const { body, citations } = parseCitationsFromResponse(turn.response)
    restored.push({
      id: turn.trace_id,
      role: 'assistant',
      content: body,
      traceId: turn.trace_id,
      citations,
      pipeline: [],
      rating: turn.rating ?? undefined,
    })
  }
  return restored
}

export function ChatPage() {
  const navigate = useNavigate()
  const { sessionId: routeSessionId } = useParams()
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [expandedCitations, setExpandedCitations] = useState<string | null>(null)
  const [livePipeline, setLivePipeline] = useState<PipelineStep[]>([])
  const [pendingImage, setPendingImage] = useState<{
    preview: string
    name: string
    attachment: { filename: string; mime_type: string; data: string }
  } | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const scrollToBottomOnUpdate = useRef(false)
  const historyLoadedForSession = useRef<string | null>(null)

  const activeSessionId = routeSessionId

  useEffect(() => {
    if (!routeSessionId) {
      setMessages([])
      return
    }

    let cancelled = false
    setLoadingHistory(true)
    setError(null)
    setMessages([])
    historyLoadedForSession.current = null

    api
      .chatHistory(routeSessionId)
      .then((data) => {
        if (cancelled) return
        const restored = turnsToMessages(data.turns)
        setMessages(restored)
        scrollToBottomOnUpdate.current = false
        historyLoadedForSession.current = routeSessionId

        if (data.turns.length > 0) {
          const first = data.turns[0]
          upsertChatSession({
            id: routeSessionId,
            title: truncate(first.user_message, 40),
            updatedAt: data.turns[data.turns.length - 1]?.created_at ?? new Date().toISOString(),
          })
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Could not load chat history')
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingHistory(false)
      })

    return () => {
      cancelled = true
    }
  }, [routeSessionId])

  useEffect(() => {
    if (loadingHistory) return

    if (scrollToBottomOnUpdate.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'auto' })
      scrollToBottomOnUpdate.current = false
      return
    }

    if (historyLoadedForSession.current === routeSessionId && messages.length > 0) {
      bottomRef.current?.scrollIntoView({ behavior: 'auto' })
      historyLoadedForSession.current = null
    }
  }, [messages, loading, loadingHistory, routeSessionId])

  const handleSend = useCallback(async () => {
    const text = message.trim()
    if ((!text && !pendingImage) || loading) return

    const attachment = pendingImage?.attachment
    const displayText = text || (attachment ? 'Read information from the attached image' : '')
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: displayText,
      imagePreview: pendingImage?.preview,
      imageName: pendingImage?.name,
    }
    scrollToBottomOnUpdate.current = true
    setMessages((prev) => [...prev, userMsg])
    setMessage('')
    setPendingImage(null)
    if (fileRef.current) fileRef.current.value = ''
    setLoading(true)
    setError(null)
    setLivePipeline([])

    const appendStep = (step: PipelineStep) => {
      setLivePipeline((prev) => [...prev, step])
      scrollToBottomOnUpdate.current = true
    }

    try {
      const stream = api.chatStream(
        {
          message: text || displayText,
          session_id: activeSessionId ?? null,
          user_id: 'frontend-user',
          attachments: attachment ? [attachment] : undefined,
        },
        appendStep,
      )

      let res: ChatResponse | undefined
      for await (const chunk of stream) {
        res = chunk
      }

      if (!res) {
        throw new Error('No response received from server')
      }

      if (!routeSessionId) {
        navigate(`/chat/${res.session_id}`, { replace: true })
      }

      upsertChatSession({
        id: res.session_id,
        title: truncate(displayText, 40),
        updatedAt: new Date().toISOString(),
      })

      const primaryAgent = res.worker_results[0]?.agent
      scrollToBottomOnUpdate.current = true
      setMessages((prev) => [
        ...prev,
        {
          id: res.trace_id,
          role: 'assistant',
          content: res.response,
          traceId: res.trace_id,
          agent: primaryAgent,
          topologyMode: res.topology_mode,
          pipeline: res.pipeline,
          citations: res.citations,
        },
      ])
      setLivePipeline([])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not send message')
      setLivePipeline([])
    } finally {
      setLoading(false)
    }
  }, [activeSessionId, loading, message, navigate, pendingImage, routeSessionId])

  const handlePickImage = () => {
    if (!loading && !loadingHistory) fileRef.current?.click()
  }

  const handleImageSelected = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    void fileToAttachment(file)
      .then(({ attachment, preview }) => {
        setPendingImage({ preview, name: file.name, attachment })
        setError(null)
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : 'Could not read image')
        e.target.value = ''
      })
  }

  const canSend = (message.trim().length > 0 || !!pendingImage) && !loading && !loadingHistory

  const handleRate = async (traceId: string, rating: number) => {
    try {
      await api.submitFeedback({ trace_id: traceId, rating })
      setMessages((prev) =>
        prev.map((m) => (m.role === 'assistant' && m.traceId === traceId ? { ...m, rating } : m)),
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not submit rating')
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void handleSend()
    }
  }

  const hasMessages = messages.length > 0

  return (
    <div className="relative flex h-full min-h-0 flex-1 flex-col overflow-hidden bg-background">
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
        <div className="mx-auto flex w-full max-w-container-max-chat flex-col gap-8 px-4 py-8 pb-40 sm:px-6">
          {loadingHistory && (
            <div className="flex flex-col items-center justify-center py-24 text-body-md text-on-surface-variant">
              <MaterialIcon name="progress_activity" size={24} className="mb-3 animate-spin" />
              Loading conversation history…
            </div>
          )}

          {!loadingHistory && !hasMessages && !loading && !routeSessionId && (
            <div className="flex flex-col items-center justify-center py-24 text-center">
              <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-secondary-container text-on-secondary-container">
                <MaterialIcon name="smart_toy" size={28} />
              </div>
              <h2 className="mb-2 text-headline-sm text-primary">Agent Workspace</h2>
              <p className="max-w-md text-body-md text-on-surface-variant">
                Ask anything — general questions, data lookup, internal documents, research…
              </p>
            </div>
          )}

          {!loadingHistory && !hasMessages && routeSessionId && !error && (
            <div className="flex flex-col items-center justify-center py-24 text-center">
              <p className="text-body-md text-on-surface-variant">No messages in this conversation yet.</p>
            </div>
          )}

          {!loadingHistory &&
            messages.map((msg) =>
              msg.role === 'user' ? (
                <div key={msg.id} className="flex w-full justify-end">
                  <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-surface-container-high px-5 py-3.5 text-body-lg text-on-surface">
                    {msg.imagePreview ? (
                      <div className="mb-2 overflow-hidden rounded-lg border border-border-subtle">
                        <img src={msg.imagePreview} alt={msg.imageName ?? 'Attachment'} className="max-h-48 w-auto object-contain" />
                      </div>
                    ) : null}
                    {msg.content}
                  </div>
                </div>
              ) : (
                <div key={msg.id} className="flex w-full flex-col gap-3">
                  <div className="mb-1 flex items-center gap-2">
                    <div className="flex h-8 w-8 items-center justify-center rounded-full bg-secondary-container text-on-secondary-container">
                      <MaterialIcon name="smart_toy" size={18} />
                    </div>
                    <span className="font-label-md font-semibold text-on-surface">Agent Workspace</span>
                    {msg.agent && (
                      <div className="ml-2 flex items-center gap-1.5 rounded-md border border-slate-200 bg-slate-100 px-2 py-0.5">
                        <MaterialIcon name={agentIcon(msg.agent)} size={14} className="text-blue-800" />
                        <span className="text-label-sm font-medium text-blue-900">{formatAgentName(msg.agent)}</span>
                      </div>
                    )}
                    {msg.topologyMode ? (
                      <span className="rounded-md border border-border-subtle px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-on-surface-variant">
                        {msg.topologyMode}
                      </span>
                    ) : null}
                  </div>

                  {msg.pipeline.length > 0 ? (
                    <div className="pl-10">
                      <AgentPipelinePanel steps={msg.pipeline} defaultExpanded={false} />
                    </div>
                  ) : null}

                  <div className="pl-10">
                    <ChatMessageBody content={msg.content} citations={msg.citations} />
                  </div>

                  <div className="mt-3 flex items-center justify-between pl-10">
                    {msg.citations.length > 0 ? (
                      <button
                        type="button"
                        onClick={() => setExpandedCitations(expandedCitations === msg.id ? null : msg.id)}
                        className="flex items-center gap-1.5 rounded border border-border-subtle px-2 py-1 text-label-sm text-on-surface-variant hover:bg-surface-container-low hover:text-on-surface"
                      >
                        <MaterialIcon name="menu_book" size={16} />
                        {msg.citations.length} Citations
                        <MaterialIcon name={expandedCitations === msg.id ? 'expand_less' : 'expand_more'} size={16} />
                      </button>
                    ) : (
                      <span />
                    )}
                    <div className="flex items-center gap-1">
                      {Array.from({ length: 5 }, (_, i) => (
                        <button
                          key={i}
                          type="button"
                          onClick={() => void handleRate(msg.traceId, i + 1)}
                          className={`p-1 transition-colors hover:text-status-warning ${
                            msg.rating && i < msg.rating ? 'text-status-warning' : 'text-outline-variant'
                          }`}
                        >
                          <MaterialIcon name="star" size={20} filled={!!msg.rating && i < msg.rating} />
                        </button>
                      ))}
                    </div>
                  </div>

                  {expandedCitations === msg.id && msg.citations.length > 0 && (
                    <div className="ml-10 space-y-2 rounded-lg border border-border-subtle bg-surface-container-low p-4">
                      {msg.citations.map((c) => (
                        <div key={c.ref_id} className="text-body-md">
                          <span
                            className={`mr-2 inline-flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-bold ${
                              c.ref_id.startsWith('W')
                                ? 'bg-orange-100 text-citation-web'
                                : 'bg-blue-100 text-citation-knowledge'
                            }`}
                          >
                            {c.ref_id}
                          </span>
                          {c.url ? (
                            <a
                              href={c.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="font-medium text-primary underline hover:opacity-80"
                            >
                              {c.title}
                            </a>
                          ) : (
                            <span className="font-medium text-primary">{c.title}</span>
                          )}
                          {c.excerpt ? <p className="mt-1 text-on-surface-variant">{c.excerpt}</p> : null}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ),
            )}

          {loading && (
            <div className="flex w-full flex-col gap-3 pl-10">
              <div className="flex items-center gap-2 text-body-md text-on-surface-variant">
                <MaterialIcon name="progress_activity" size={20} className="animate-spin text-primary" />
                Agent Workspace is processing…
              </div>
              {livePipeline.length > 0 ? (
                <AgentPipelinePanel steps={livePipeline} live defaultExpanded />
              ) : null}
            </div>
          )}

          {error && (
            <div className="rounded-lg border border-error/30 bg-error-container/30 px-4 py-3 text-body-md text-on-error-container">
              {error}
            </div>
          )}

          <div ref={bottomRef} />
        </div>
      </div>

      <div className="absolute bottom-0 left-0 z-10 flex w-full justify-center bg-gradient-to-t from-background via-background to-transparent px-4 pt-6 pb-6 sm:px-8">
        <div className="relative w-full max-w-container-max-chat rounded-xl border border-border-subtle bg-surface-container-lowest shadow-[0_2px_12px_rgba(0,0,0,0.06)] transition-all focus-within:border-secondary focus-within:ring-1 focus-within:ring-secondary">
          <input
            ref={fileRef}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            className="hidden"
            onChange={handleImageSelected}
          />
          {pendingImage ? (
            <div className="flex items-center gap-3 border-b border-border-subtle px-4 py-2">
              <img src={pendingImage.preview} alt="" className="h-14 w-14 rounded-md object-cover" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-label-sm text-on-surface">{pendingImage.name}</p>
                <p className="text-label-sm text-on-surface-variant">Image will be sent for OCR/text extraction</p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setPendingImage(null)
                  if (fileRef.current) fileRef.current.value = ''
                }}
                className="rounded-md p-1 text-on-surface-variant hover:bg-surface-container-low"
                title="Remove image"
              >
                <MaterialIcon name="close" size={18} />
              </button>
            </div>
          ) : null}
          <textarea
            rows={1}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a message to discuss..."
            disabled={loading || loadingHistory}
            className="min-h-[60px] max-h-[200px] w-full resize-none border-none bg-transparent px-4 py-4 text-body-md text-on-surface focus:ring-0 focus:outline-none disabled:opacity-60"
          />
          <div className="flex items-center justify-between px-3 pb-3">
            <button
              type="button"
              onClick={handlePickImage}
              disabled={loading || loadingHistory}
              className="rounded-md p-1.5 text-on-surface-variant hover:bg-surface-container-low disabled:opacity-50"
              title="Attach image (OCR)"
            >
              <MaterialIcon name="attach_file" size={20} />
            </button>
            <div className="flex items-center gap-3">
              <span className="text-label-sm text-outline">{message.length}/8000</span>
              <button
                type="button"
                disabled={!canSend}
                onClick={() => void handleSend()}
                className="flex items-center justify-center gap-2 rounded-lg bg-primary px-4 py-1.5 text-label-md text-on-primary transition-colors hover:bg-inverse-surface disabled:opacity-50"
              >
                <MaterialIcon name="send" filled size={18} />
                Send
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
