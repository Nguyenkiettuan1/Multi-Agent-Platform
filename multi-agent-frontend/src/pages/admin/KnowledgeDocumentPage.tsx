import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, ApiError } from '../../api/client'
import type { KnowledgeDocumentDetail } from '../../api/types'
import { MaterialIcon } from '../../components/ui/MaterialIcon'
import {
  azureLabel,
  azureState,
  deleteFailureMessage,
  deleteSuccessMessage,
  embeddingState,
  removalScope,
  type AzureState,
  type EmbeddingState,
} from '../../lib/knowledge'

const toneClass = {
  good: 'bg-[#ecfdf5] text-[#065f46] border-[#a7f3d0]',
  warn: 'bg-[#fffbeb] text-[#92400e] border-[#fde68a]',
  bad: 'bg-[#fef2f2] text-[#991b1b] border-[#fecaca]',
  muted: 'bg-surface-container-high text-on-surface border-outline-variant',
}

const embeddingTone: Record<EmbeddingState, keyof typeof toneClass> = {
  all: 'good',
  partial: 'warn',
  none: 'bad',
}
const embeddingWord: Record<EmbeddingState, string> = { all: 'All embedded', partial: 'Partial', none: 'None' }
const azureTone: Record<AzureState, keyof typeof toneClass> = {
  indexed: 'good',
  failed: 'bad',
  not_configured: 'muted',
  not_synced: 'warn',
}

function Badge({ tone, children }: { tone: keyof typeof toneClass; children: React.ReactNode }) {
  return (
    <span
      className={`inline-flex w-max items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${toneClass[tone]}`}
    >
      {children}
    </span>
  )
}

export function EmbeddingBadge({ embedded, chunks }: { embedded: number; chunks: number }) {
  const state = embeddingState(embedded, chunks)
  return (
    <div className="flex flex-col gap-1">
      <span className="tabular-nums text-on-surface">
        {embedded}/{chunks} chunks
      </span>
      <Badge tone={embeddingTone[state]}>{embeddingWord[state]}</Badge>
    </div>
  )
}

export function AzureBadge({ enabled, indexed }: { enabled: boolean; indexed: boolean | null }) {
  const state = azureState(enabled, indexed)
  return <Badge tone={azureTone[state]}>{azureLabel(state)}</Badge>
}

type DeleteTarget = { doc_id: string; title: string; chunk_count: number }

/**
 * In-page confirmation. Uses native <dialog>.showModal() so focus is trapped, Esc closes it and
 * focus returns to the opener; window.confirm would block browser automation.
 */
export function DeleteDocumentDialog({
  doc,
  azureEnabled,
  context,
  onClose,
  onDeleted,
  onStale,
}: {
  doc: DeleteTarget
  azureEnabled: boolean
  context: 'list' | 'detail'
  /** Called only from the native close event, after the browser has restored focus to the opener. */
  onClose: () => void
  onDeleted: () => void
  /** The document no longer exists (404): the caller should refresh its view. */
  onStale: () => void
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const [stale, setStale] = useState(false)
  // The close handler must read the live value, not a stale render's closure.
  const busyRef = useRef(false)

  useEffect(() => {
    const dialog = ref.current
    if (dialog && !dialog.open) dialog.showModal()
  }, [])

  const confirm = async () => {
    if (busyRef.current) return
    busyRef.current = true
    setBusy(true)
    setFailure(null)
    try {
      await api.deleteKnowledgeDocument(doc.doc_id)
      onDeleted()
    } catch (err) {
      const status = err instanceof ApiError ? err.status : undefined
      const detail = err instanceof Error ? err.message : 'Unknown error'
      const result = deleteFailureMessage(status, detail, context)
      setFailure(result.text)
      if (result.refresh) {
        setStale(true)
        onStale()
      }
      busyRef.current = false
      setBusy(false)
    }
  }

  return (
    <dialog
      ref={ref}
      aria-labelledby="delete-doc-title"
      aria-describedby="delete-doc-body"
      // Esc must not dismiss the dialog while a delete is in flight.
      onCancel={(e) => {
        if (busyRef.current) e.preventDefault()
      }}
      // Chrome can still close on a repeated Esc despite preventDefault: reopen so the in-flight
      // delete keeps its dialog. Otherwise the native close (which restores focus) tells the parent.
      onClose={() => {
        if (busyRef.current) {
          if (!ref.current?.open) ref.current?.showModal()
        } else {
          onClose()
        }
      }}
      className="m-auto w-[min(32rem,calc(100vw-2rem))] rounded-xl border border-border-subtle bg-surface p-0 text-on-surface shadow-xl backdrop:bg-black/40"
    >
      <div className="p-6">
        <h2 id="delete-doc-title" className="text-title-md font-semibold text-primary">
          Delete this document?
        </h2>
        <div id="delete-doc-body" className="mt-3 space-y-2 text-body-md text-on-surface-variant">
          <p>
            <strong className="break-words font-semibold text-primary">{doc.title}</strong> and its{' '}
            {doc.chunk_count} {doc.chunk_count === 1 ? 'chunk' : 'chunks'} will be removed from{' '}
            {azureEnabled ? 'both ' : ''}
            {removalScope(azureEnabled)}.
          </p>
          <p>This cannot be undone.</p>
        </div>
        {failure && (
          <p
            role="alert"
            className="mt-4 rounded-lg border border-error/30 bg-error-container/30 px-4 py-3 text-body-md text-on-error-container"
          >
            {failure}
          </p>
        )}
        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            autoFocus
            disabled={busy}
            onClick={() => ref.current?.close()}
            className="rounded-lg border border-border-subtle bg-surface px-4 py-2 text-label-md text-primary hover:bg-surface-container-low disabled:opacity-50"
          >
            {stale ? 'Close' : 'Cancel'}
          </button>
          {!stale && (
            <button
              type="button"
              aria-disabled={busy}
              onClick={() => void confirm()}
              className="flex items-center gap-2 rounded-lg bg-error px-4 py-2 text-label-md text-on-error hover:opacity-90 aria-disabled:cursor-wait aria-disabled:opacity-60"
            >
              {busy && (
                <span aria-hidden="true">
                  <MaterialIcon name="progress_activity" size={18} className="animate-spin" />
                </span>
              )}
              {busy ? 'Deleting…' : failure ? 'Try again' : 'Delete document'}
            </button>
          )}
        </div>
      </div>
    </dialog>
  )
}

type LoadState =
  | { kind: 'loading' }
  | { kind: 'ready'; doc: KnowledgeDocumentDetail }
  | { kind: 'not_found' }
  | { kind: 'error'; message: string }

export function KnowledgeDocumentPage() {
  const { docId = '' } = useParams()
  const navigate = useNavigate()
  const [state, setState] = useState<LoadState>({ kind: 'loading' })
  const [confirming, setConfirming] = useState(false)
  // Set when the dialog got a 404; the page switches to "not found" once the dialog is closed.
  const goneRef = useRef(false)
  const notFoundHeadingRef = useRef<HTMLHeadingElement>(null)

  // Switching to "not found" unmounts the Delete opener; move focus to the new heading.
  useEffect(() => {
    if (state.kind === 'not_found' && goneRef.current) notFoundHeadingRef.current?.focus()
  }, [state])

  const load = useCallback(() => {
    let cancelled = false
    setState({ kind: 'loading' })
    api
      .adminKnowledgeDocument(docId)
      .then((doc) => {
        if (!cancelled) setState({ kind: 'ready', doc })
      })
      .catch((err: unknown) => {
        if (cancelled) return
        if (err instanceof ApiError && err.status === 404) setState({ kind: 'not_found' })
        else setState({ kind: 'error', message: err instanceof Error ? err.message : 'Could not load document' })
      })
    return () => {
      cancelled = true
    }
  }, [docId])

  useEffect(() => load(), [load])

  const backLink = (
    <Link to="/admin/knowledge" className="inline-flex items-center gap-1 text-label-md text-secondary hover:underline">
      <span aria-hidden="true">
        <MaterialIcon name="arrow_back" size={18} />
      </span>
      Back to knowledge
    </Link>
  )

  if (state.kind === 'loading') {
    return (
      <div className="mx-auto max-w-[1200px] p-margin-page">
        {backLink}
        <p role="status" className="mt-8 text-on-surface-variant">
          Loading document…
        </p>
      </div>
    )
  }

  if (state.kind === 'not_found' || state.kind === 'error') {
    return (
      <div className="mx-auto max-w-[1200px] p-margin-page">
        {backLink}
        <div className="mt-8 rounded-xl border border-border-subtle bg-surface p-8">
          <h1 ref={notFoundHeadingRef} tabIndex={-1} className="text-title-md font-semibold text-primary focus:outline-none">
            {state.kind === 'not_found' ? 'Document not found' : 'Could not load document'}
          </h1>
          <p className="mt-2 text-body-md text-on-surface-variant">
            {state.kind === 'not_found'
              ? `No document with id "${docId}" exists. It may have been deleted.`
              : state.message}
          </p>
          {state.kind === 'error' && (
            <button
              type="button"
              onClick={load}
              className="mt-4 rounded-lg border border-border-subtle bg-surface px-4 py-2 text-label-md text-primary hover:bg-surface-container-low"
            >
              Retry
            </button>
          )}
        </div>
      </div>
    )
  }

  const { doc } = state

  const closeDialog = () => {
    setConfirming(false)
    if (goneRef.current) setState({ kind: 'not_found' })
  }

  return (
    <div className="mx-auto max-w-[1200px] p-margin-page">
      {backLink}
      <div className="mb-8 mt-4 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="break-words text-display-lg text-primary">{doc.title}</h1>
          <dl className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-2 text-body-md text-on-surface-variant">
            <div className="flex items-center gap-2">
              <dt>Domain</dt>
              <dd className="font-medium text-on-surface">{doc.domain}</dd>
            </div>
            <div className="flex items-center gap-2">
              <dt>Source</dt>
              <dd className="font-medium text-on-surface">{doc.source}</dd>
            </div>
            <div className="flex items-center gap-2">
              <dt>Embedding</dt>
              <dd>
                <EmbeddingBadge embedded={doc.embedded_count} chunks={doc.chunk_count} />
              </dd>
            </div>
            <div className="flex items-center gap-2">
              <dt>Azure Search</dt>
              <dd>
                <AzureBadge enabled={doc.azure_enabled} indexed={doc.azure_indexed} />
              </dd>
            </div>
          </dl>
        </div>
        <button
          type="button"
          onClick={() => setConfirming(true)}
          className="flex items-center gap-2 rounded-lg border border-error/40 bg-surface px-4 py-2 text-label-md text-error hover:bg-error-container/30"
        >
          <span aria-hidden="true">
            <MaterialIcon name="delete" size={18} />
          </span>
          Delete document
        </button>
      </div>

      <section aria-labelledby="doc-content" className="mb-8">
        <h2 id="doc-content" className="text-title-sm font-semibold text-primary">
          Extracted content
        </h2>
        <p className="mt-1 text-label-sm text-on-surface-variant">
          Adjacent chunks overlap, so some passages can appear twice in this joined text.
        </p>
        <pre className="mt-3 max-h-[28rem] overflow-auto whitespace-pre-wrap break-words rounded-xl border border-border-subtle bg-surface-container-lowest p-6 font-sans text-body-md text-on-surface">
          {doc.content || 'No content extracted.'}
        </pre>
      </section>

      <section aria-labelledby="doc-chunks">
        <h2 id="doc-chunks" className="text-title-sm font-semibold text-primary">
          Chunks ({doc.chunks.length})
        </h2>
        <ul className="mt-3 divide-y divide-border-subtle overflow-hidden rounded-xl border border-border-subtle bg-surface">
          {doc.chunks.map((chunk) => (
            <li key={chunk.doc_id}>
              <details>
                <summary className="flex cursor-pointer flex-wrap items-center gap-x-6 gap-y-1 px-6 py-3 text-body-md hover:bg-surface-container-low">
                  <span className="font-medium tabular-nums text-primary">Chunk {(chunk.chunk_index ?? 0) + 1}</span>
                  <span className="tabular-nums text-on-surface-variant">{chunk.char_count} chars</span>
                  <Badge tone={chunk.has_embedding ? 'good' : 'bad'}>
                    {chunk.has_embedding ? 'Embedded: yes' : 'Embedded: no'}
                  </Badge>
                </summary>
                <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words border-t border-border-subtle bg-surface-container-lowest px-6 py-4 font-sans text-body-md text-on-surface">
                  {chunk.content}
                </pre>
              </details>
            </li>
          ))}
        </ul>
      </section>

      {confirming && (
        <DeleteDocumentDialog
          doc={{ doc_id: doc.doc_id, title: doc.title, chunk_count: doc.chunk_count }}
          azureEnabled={doc.azure_enabled}
          context="detail"
          onClose={closeDialog}
          onDeleted={() =>
            navigate('/admin/knowledge', {
              state: { notice: deleteSuccessMessage(doc.title, doc.azure_enabled) },
            })
          }
          onStale={() => {
            goneRef.current = true
          }}
        />
      )}
    </div>
  )
}
