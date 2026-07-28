import { useRef, useState } from 'react'
import { api } from '../../api/client'
import type { KnowledgeDocument } from '../../api/types'
import { MaterialIcon } from '../../components/ui/MaterialIcon'
import { useAsync } from '../../hooks/useAsync'
import { formatCount, formatDateTime } from '../../lib/format'

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

function parentDocs(items: KnowledgeDocument[]): KnowledgeDocument[] {
  const seen = new Set<string>()
  return items.filter((doc) => {
    const key = doc.parent_doc_id ?? doc.doc_id
    if (seen.has(key)) return false
    seen.add(key)
    return doc.chunk_index == null || doc.chunk_index === 0
  })
}

export function KnowledgePage() {
  const [domain, setDomain] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)

  const { data, loading, error, reload } = useAsync(
    () => api.adminKnowledge({ limit: 100, domain: domain || undefined }),
    [domain],
  )

  const docs = data ? parentDocs(data.items) : []
  const total = data?.count ?? 0
  const withEmbedding = data?.items.filter((d) => d.has_embedding).length ?? 0
  const embeddingPct = total > 0 ? Math.round((withEmbedding / total) * 1000) / 10 : 0
  const domains = [...new Set((data?.items ?? []).map((d) => d.domain))].sort()

  const handleUpload = async (file: File) => {
    setUploading(true)
    setUploadError(null)
    try {
      await api.uploadKnowledge(file, { domain: domain || 'general' })
      reload()
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Upload thất bại')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="mx-auto max-w-[1200px] p-margin-page">
      <div className="mb-8 flex items-end justify-between">
        <div>
          <h1 className="text-display-lg text-primary">Quản trị Tri thức</h1>
          <p className="mt-2 text-body-md text-on-surface-variant">
            Quản lý và cập nhật nguồn dữ liệu cho các Agent nội bộ.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative">
            <select
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              className="appearance-none rounded-lg border border-border-subtle bg-surface px-4 py-2 pr-10 text-label-md text-on-surface focus:border-secondary focus:ring-1 focus:ring-secondary focus:outline-none"
            >
              <option value="">Tất cả Lĩnh vực</option>
              {domains.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
            <MaterialIcon
              name="arrow_drop_down"
              className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-on-surface-variant"
              size={20}
            />
          </div>
          <button
            type="button"
            onClick={reload}
            disabled={loading}
            className="flex items-center gap-2 rounded-lg border border-border-subtle bg-surface px-4 py-2 text-label-md text-primary hover:bg-surface-container-low disabled:opacity-50"
          >
            <MaterialIcon name="refresh" size={18} className={loading ? 'animate-spin' : ''} />
            Làm mới
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx,.doc,.txt,.md"
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
            <MaterialIcon name="upload" size={18} />
            {uploading ? 'Đang tải lên…' : 'Tải lên tài liệu'}
          </button>
        </div>
      </div>

      {(error || uploadError) && (
        <div className="mb-6 rounded-lg border border-error/30 bg-error-container/30 px-4 py-3 text-body-md text-on-error-container">
          {error ?? uploadError}
        </div>
      )}

      <div className="mb-8 grid grid-cols-1 gap-6 md:grid-cols-3">
        <div className="flex flex-col justify-between rounded-xl border border-border-subtle bg-surface p-6">
          <div className="mb-4 flex items-start justify-between">
            <span className="text-label-md text-on-surface-variant">Tổng tài liệu</span>
            <span className="rounded-lg bg-surface-container-low p-2 text-secondary">
              <MaterialIcon name="description" />
            </span>
          </div>
          <div>
            <div className="mb-1 text-display-lg text-primary">{loading ? '…' : formatCount(total)}</div>
            <div className="text-label-sm text-on-surface-variant">Từ API knowledge</div>
          </div>
        </div>
        <div className="flex flex-col justify-between rounded-xl border border-border-subtle bg-surface p-6">
          <div className="mb-4 flex items-start justify-between">
            <span className="text-label-md text-on-surface-variant">Trạng thái Embedding</span>
            <span className="rounded-lg border border-border-subtle bg-surface-container-lowest p-2 text-status-success">
              <MaterialIcon name="check_circle" />
            </span>
          </div>
          <div>
            <div className="mb-1 text-display-lg text-primary">{loading ? '…' : `${embeddingPct}%`}</div>
            <div className="text-label-sm text-on-surface-variant">
              {withEmbedding}/{total} có embedding
            </div>
          </div>
        </div>
        <div className="flex flex-col justify-between rounded-xl bg-secondary-container p-6 text-on-secondary-container">
          <div className="mb-4 flex items-start justify-between">
            <span className="text-label-md opacity-90">Chunks</span>
            <MaterialIcon name="cut" />
          </div>
          <div>
            <div className="mb-1 text-display-lg">{loading ? '…' : formatCount(total - docs.length)}</div>
            <div className="text-label-sm opacity-90">Tài liệu con (chunk)</div>
          </div>
        </div>
      </div>

      <div className="overflow-hidden rounded-xl border border-border-subtle bg-surface">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left">
            <thead>
              <tr className="border-b border-border-subtle bg-surface-container-low">
                <th className="px-6 py-4 text-label-sm uppercase tracking-wider text-on-surface-variant">Tiêu đề</th>
                <th className="px-6 py-4 text-label-sm uppercase tracking-wider text-on-surface-variant">Lĩnh vực</th>
                <th className="px-6 py-4 text-label-sm uppercase tracking-wider text-on-surface-variant">Nguồn</th>
                <th className="px-6 py-4 text-label-sm uppercase tracking-wider text-on-surface-variant">Trạng thái Embedding</th>
                <th className="px-6 py-4 text-label-sm uppercase tracking-wider text-on-surface-variant">Ngày cập nhật</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border-subtle">
              {loading ? (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-on-surface-variant">
                    Đang tải…
                  </td>
                </tr>
              ) : docs.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-on-surface-variant">
                    Chưa có tài liệu — hãy tải lên tài liệu đầu tiên.
                  </td>
                </tr>
              ) : (
                docs.map((doc) => {
                  const { icon, color } = docIcon(doc.title)
                  const domainKey = doc.domain.toLowerCase()
                  return (
                    <tr key={doc.doc_id} className="group transition-colors hover:bg-surface-container-low">
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <MaterialIcon name={icon} className={color} />
                          <span className="line-clamp-1 font-medium text-primary">{doc.title}</span>
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
                        <div
                          className={`flex w-max items-center gap-1.5 rounded-md border border-border-subtle bg-surface-container-lowest px-2 py-1 text-xs ${
                            doc.has_embedding ? 'text-status-success' : 'text-status-warning'
                          }`}
                        >
                          <MaterialIcon name={doc.has_embedding ? 'check_circle' : 'sync'} size={16} />
                          {doc.has_embedding ? 'Hoàn tất' : 'Chưa embed'}
                        </div>
                      </td>
                      <td className="px-6 py-4 text-on-surface-variant">{formatDateTime(doc.updated_at)}</td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
        <div className="flex items-center justify-between border-t border-border-subtle bg-surface-container-lowest px-6 py-4">
          <span className="text-label-sm text-on-surface-variant">
            Hiển thị {docs.length} trên {total} bản ghi
          </span>
        </div>
      </div>
    </div>
  )
}
