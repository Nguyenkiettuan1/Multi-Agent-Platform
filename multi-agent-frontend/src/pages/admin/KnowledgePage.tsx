import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import type { KnowledgeDocumentSummary } from '../../api/types'
import { MaterialIcon } from '../../components/ui/MaterialIcon'
import { useAsync } from '../../hooks/useAsync'
import { formatCount, formatDateTime } from '../../lib/format'
import {
  deleteSuccessMessage,
  lastValidOffset,
  pageInfo,
  summarizeUpload,
  uploadedDocId,
  type UploadSummary,
} from '../../lib/knowledge'
import { AzureBadge, DeleteDocumentDialog, EmbeddingBadge } from './KnowledgeDocumentPage'

const domainStyles: Record<string, string> = {
  hr: 'bg-[#ecfdf5] text-[#065f46] border-[#a7f3d0]',
  it: 'bg-[#eff6ff] text-[#1e40af] border-[#bfdbfe]',
  legal: 'bg-[#fef2f2] text-[#991b1b] border-[#fecaca]',
  general: 'bg-surface-container-high text-on-surface border-outline-variant',
}

function docIcon(title: string): { icon: string; color: string } {
  const lower = title.toLowerCase()
  if (lower.endsWith('.pdf')) return { icon: 'picture_as_pdf', color: 'text-status-error' }
  if (lower.endsWith('.docx') || lower.endsWith('.doc')) return { icon: 'description', color: 'text-secondary' }
  return { icon: 'text_snippet', color: 'text-on-surface-variant' }
}

const PAGE_SIZE = 25

const headCell = 'px-6 py-4 text-label-sm uppercase tracking-wider text-on-surface-variant'

export function KnowledgePage() {
  const location = useLocation()
  const navigate = useNavigate()
  const [domain, setDomain] = useState('')
  const [offset, setOffset] = useState(0)
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploadSummary, setUploadSummary] = useState<UploadSummary | null>(null)
  const [highlightId, setHighlightId] = useState<string | null>(null)
  const [deleting, setDeleting] = useState<KnowledgeDocumentSummary | null>(null)
  // Message for the role="status" region; set after a delete here or on the detail page.
  const [notice, setNotice] = useState<string | null>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const focusHeadingAfterDelete = useRef(false)
  // Domains seen so far, so the filter keeps listing them after one is selected.
  const [knownDomains, setKnownDomains] = useState<string[]>([])

  const { data, loading, error, reload } = useAsync(
    () => api.adminKnowledgeDocuments({ limit: PAGE_SIZE, offset, domain: domain || undefined }),
    [domain, offset],
  )

  // The detail page hands over its delete message through router state. Read it once, then clear
  // it so a reload does not replay it and the status region announces it as a change.
  useEffect(() => {
    const carried = (location.state as { notice?: string } | null)?.notice
    if (!carried) return
    setNotice(carried)
    headingRef.current?.focus()
    navigate(location.pathname, { replace: true, state: null })
  }, [location.state, location.pathname, navigate])

  // A delete can empty the last page; step back to the last page that still has rows.
  useEffect(() => {
    if (data && offset > 0 && offset >= data.total) setOffset(lastValidOffset(data.total, PAGE_SIZE))
  }, [data, offset])

  // The deleted row (the dialog's opener) is gone, so focus would fall to <body>.
  useEffect(() => {
    if (!deleting && focusHeadingAfterDelete.current) {
      focusHeadingAfterDelete.current = false
      headingRef.current?.focus()
    }
  }, [deleting])

  useEffect(() => {
    if (!data) return
    setKnownDomains((prev) => [...new Set([...prev, ...data.items.map((d) => d.domain)])].sort())
  }, [data])

  const docs = data?.items ?? []
  const total = data?.total ?? 0
  const azureEnabled = data?.azure_enabled ?? false
  const pageDocsEmbedded = docs.filter((d) => d.chunk_count > 0 && d.embedded_count >= d.chunk_count).length
  const pageChunks = docs.reduce((sum, d) => sum + d.chunk_count, 0)
  const pageChunksEmbedded = docs.reduce((sum, d) => sum + d.embedded_count, 0)
  const page = pageInfo(offset, PAGE_SIZE, total)
  const firstLoad = loading && !data

  const handleUpload = async (file: File) => {
    setUploading(true)
    setUploadError(null)
    setUploadSummary(null)
    setNotice(null)
    try {
      const result = await api.uploadKnowledge(file, { domain: domain || 'general' })
      setUploadSummary(summarizeUpload(result))
      setHighlightId(uploadedDocId(result))
      // Newest first: page 1 is where the highlighted row will be.
      setOffset(0)
      reload()
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const handleDeleted = (doc: KnowledgeDocumentSummary) => {
    focusHeadingAfterDelete.current = true
    setDeleting(null)
    setNotice(deleteSuccessMessage(doc.title, azureEnabled))
    setUploadSummary(null)
    reload()
  }

  return (
    <div className="mx-auto max-w-[1200px] p-margin-page">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 ref={headingRef} tabIndex={-1} className="text-display-lg text-primary focus:outline-none">
            Knowledge Management
          </h1>
          <p className="mt-2 text-body-md text-on-surface-variant">
            Manage and update data sources for internal agents.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative">
            <select
              aria-label="Filter by domain"
              value={domain}
              onChange={(e) => {
                setDomain(e.target.value)
                setOffset(0)
              }}
              className="appearance-none rounded-lg border border-border-subtle bg-surface px-4 py-2 pr-10 text-label-md text-on-surface focus:border-secondary focus:ring-1 focus:ring-secondary focus:outline-none"
            >
              <option value="">All Domains</option>
              {knownDomains.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
            <span aria-hidden="true">
              <MaterialIcon
                name="arrow_drop_down"
                className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-on-surface-variant"
                size={20}
              />
            </span>
          </div>
          <button
            type="button"
            onClick={reload}
            disabled={loading}
            className="flex items-center gap-2 rounded-lg border border-border-subtle bg-surface px-4 py-2 text-label-md text-primary hover:bg-surface-container-low disabled:opacity-50"
          >
            <span aria-hidden="true">
              <MaterialIcon name="refresh" size={18} className={loading ? 'animate-spin' : ''} />
            </span>
            Refresh
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx,.doc,.txt,.md"
            aria-label="Choose a document to upload"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) void handleUpload(file)
              e.target.value = ''
            }}
          />
          <button
            type="button"
            disabled={uploading}
            onClick={() => fileRef.current?.click()}
            className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-label-md text-on-primary hover:opacity-90 disabled:opacity-50"
          >
            <span aria-hidden="true">
              <MaterialIcon name="upload" size={18} />
            </span>
            {uploading ? 'Uploading…' : 'Upload document'}
          </button>
        </div>
      </div>

      {(error || uploadError) && (
        <div
          role="alert"
          className="mb-6 rounded-lg border border-error/30 bg-error-container/30 px-4 py-3 text-body-md text-on-error-container"
        >
          {error ?? uploadError}
        </div>
      )}

      {/* Always mounted so screen readers announce the text changes. */}
      <div role="status" className={uploadSummary || notice ? 'mb-6' : undefined}>
        {uploadSummary && (
          <p
            className={`rounded-lg border px-4 py-3 text-body-md ${
              uploadSummary.tone === 'success'
                ? 'border-[#a7f3d0] bg-[#ecfdf5] text-[#065f46]'
                : 'border-[#fde68a] bg-[#fffbeb] text-[#92400e]'
            }`}
          >
            {uploadSummary.tone === 'success' ? 'Upload complete: ' : 'Uploaded with problems: '}
            {uploadSummary.message}
          </p>
        )}
        {notice && (
          <p className="rounded-lg border border-[#a7f3d0] bg-[#ecfdf5] px-4 py-3 text-body-md text-[#065f46]">
            {notice}
          </p>
        )}
      </div>

      <div className="mb-8 grid grid-cols-1 gap-6 md:grid-cols-3">
        <div className="flex flex-col justify-between rounded-xl border border-border-subtle bg-surface p-6">
          <div className="mb-4 flex items-start justify-between">
            <span className="text-label-md text-on-surface-variant">Total documents</span>
            <span aria-hidden="true" className="rounded-lg bg-surface-container-low p-2 text-secondary">
              <MaterialIcon name="description" />
            </span>
          </div>
          <div>
            <div className="mb-1 text-display-lg text-primary">{firstLoad ? '…' : formatCount(total)}</div>
            <div className="text-label-sm text-on-surface-variant">
              {domain ? `In domain "${domain}"` : 'Across all domains'}
            </div>
          </div>
        </div>
        <div className="flex flex-col justify-between rounded-xl border border-border-subtle bg-surface p-6">
          <div className="mb-4 flex items-start justify-between">
            <span className="text-label-md text-on-surface-variant">Fully embedded</span>
            <span
              aria-hidden="true"
              className="rounded-lg border border-border-subtle bg-surface-container-lowest p-2 text-status-success"
            >
              <MaterialIcon name="check_circle" />
            </span>
          </div>
          <div>
            <div className="mb-1 text-display-lg text-primary">
              {firstLoad ? '…' : `${pageDocsEmbedded}/${docs.length}`}
            </div>
            <div className="text-label-sm text-on-surface-variant">Documents on this page</div>
          </div>
        </div>
        <div className="flex flex-col justify-between rounded-xl bg-secondary-container p-6 text-on-secondary-container">
          <div className="mb-4 flex items-start justify-between">
            <span className="text-label-md opacity-90">Chunks embedded</span>
            <span aria-hidden="true">
              <MaterialIcon name="cut" />
            </span>
          </div>
          <div>
            <div className="mb-1 text-display-lg">
              {firstLoad ? '…' : `${formatCount(pageChunksEmbedded)}/${formatCount(pageChunks)}`}
            </div>
            <div className="text-label-sm opacity-90">Chunks on this page</div>
          </div>
        </div>
      </div>

      <div className="overflow-hidden rounded-xl border border-border-subtle bg-surface">
        <div className="relative overflow-x-auto">
          <table className="w-full border-collapse text-left">
            <caption className="sr-only">Knowledge documents</caption>
            <thead>
              <tr className="border-b border-border-subtle bg-surface-container-low">
                <th scope="col" className={headCell}>Title</th>
                <th scope="col" className={headCell}>Domain</th>
                <th scope="col" className={headCell}>Source</th>
                <th scope="col" className={headCell}>Embedding</th>
                <th scope="col" className={headCell}>Azure Search</th>
                <th scope="col" className={headCell}>Updated</th>
                <th scope="col" className={headCell}>
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {firstLoad ? (
                <tr>
                  <td colSpan={7} className="px-6 py-8 text-center text-on-surface-variant">
                    Loading…
                  </td>
                </tr>
              ) : docs.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-6 py-8 text-center text-on-surface-variant">
                    {domain
                      ? `No documents in domain "${domain}".`
                      : 'No documents yet — upload your first document.'}
                  </td>
                </tr>
              ) : (
                docs.map((doc) => {
                  const { icon, color } = docIcon(doc.title)
                  const domainKey = doc.domain.toLowerCase()
                  const isNew = doc.doc_id === highlightId
                  return (
                    <tr
                      key={doc.doc_id}
                      className={`group transition-colors hover:bg-surface-container-low ${
                        isNew ? 'bg-secondary-fixed/40' : ''
                      }`}
                    >
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <span aria-hidden="true">
                            <MaterialIcon name={icon} className={color} />
                          </span>
                          <Link
                            to={`/admin/knowledge/${encodeURIComponent(doc.doc_id)}`}
                            className="line-clamp-1 font-medium text-primary hover:text-secondary hover:underline"
                          >
                            {doc.title}
                          </Link>
                          {isNew && (
                            <span className="rounded-full bg-secondary px-2 py-0.5 text-xs font-medium text-on-secondary">
                              New
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <span
                          className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${
                            domainStyles[domainKey] ?? domainStyles.general
                          }`}
                        >
                          {doc.domain}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-on-surface-variant">{doc.source}</td>
                      <td className="px-6 py-4">
                        <EmbeddingBadge embedded={doc.embedded_count} chunks={doc.chunk_count} />
                      </td>
                      <td className="px-6 py-4">
                        <AzureBadge enabled={azureEnabled} indexed={doc.azure_indexed} />
                      </td>
                      <td className="px-6 py-4 text-on-surface-variant">{formatDateTime(doc.updated_at)}</td>
                      <td className="px-6 py-4">
                        <button
                          type="button"
                          aria-label={`Delete ${doc.title}`}
                          onClick={() => setDeleting(doc)}
                          className="rounded-lg p-2 text-on-surface-variant hover:bg-error-container/30 hover:text-error"
                        >
                          <span aria-hidden="true">
                            <MaterialIcon name="delete" size={20} />
                          </span>
                        </button>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border-subtle bg-surface-container-lowest px-6 py-4">
          <span className="text-label-sm text-on-surface-variant">
            Showing {page.from}–{page.to} of {total} documents
          </span>
          <div className="flex items-center gap-3">
            <span className="text-label-sm text-on-surface-variant">
              Page {page.page} of {page.pages}
            </span>
            <button
              type="button"
              disabled={!page.hasPrev || loading}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              className="rounded-lg border border-border-subtle bg-surface px-3 py-1.5 text-label-md text-primary hover:bg-surface-container-low disabled:opacity-50"
            >
              Previous
            </button>
            <button
              type="button"
              disabled={!page.hasNext || loading}
              onClick={() => setOffset(offset + PAGE_SIZE)}
              className="rounded-lg border border-border-subtle bg-surface px-3 py-1.5 text-label-md text-primary hover:bg-surface-container-low disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </div>
      </div>

      {deleting && (
        <DeleteDocumentDialog
          key={deleting.doc_id}
          doc={{ doc_id: deleting.doc_id, title: deleting.title, chunk_count: deleting.chunk_count }}
          azureEnabled={azureEnabled}
          context="list"
          onClose={() => setDeleting(null)}
          onDeleted={() => handleDeleted(deleting)}
          onStale={() => {
            focusHeadingAfterDelete.current = true
            reload()
          }}
        />
      )}
    </div>
  )
}
