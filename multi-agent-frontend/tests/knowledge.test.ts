import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  azureLabel,
  azureState,
  deleteFailureMessage,
  deleteSuccessMessage,
  embeddingState,
  lastValidOffset,
  pageInfo,
  removalScope,
  summarizeUpload,
  uploadedDocId,
} from '../src/lib/knowledge.ts'

describe('embeddingState', () => {
  it('is all when every chunk is embedded', () => {
    assert.equal(embeddingState(12, 12), 'all')
  })
  it('is partial when some chunks are embedded', () => {
    assert.equal(embeddingState(3, 12), 'partial')
  })
  it('is none when no chunk is embedded', () => {
    assert.equal(embeddingState(0, 12), 'none')
  })
  it('treats a document without chunks as none, never all', () => {
    assert.equal(embeddingState(0, 0), 'none')
  })
})

describe('azureState / azureLabel', () => {
  it('is not_configured whenever Azure is disabled', () => {
    assert.equal(azureState(false, null), 'not_configured')
    assert.equal(azureState(false, true), 'not_configured')
  })
  it('maps enabled + true/false/null', () => {
    assert.equal(azureState(true, true), 'indexed')
    assert.equal(azureState(true, false), 'failed')
    assert.equal(azureState(true, null), 'not_synced')
  })
  it('has human labels', () => {
    assert.equal(azureLabel('indexed'), 'Indexed')
    assert.equal(azureLabel('failed'), 'Failed')
    assert.equal(azureLabel('not_configured'), 'Not configured')
    assert.equal(azureLabel('not_synced'), 'Not synced')
  })
})

describe('summarizeUpload', () => {
  const ok = { chunks_stored: 12, embedded_count: 12, azure: { enabled: true, indexed: 12, total: 12, error: null } }

  it('reports full success', () => {
    const s = summarizeUpload(ok)
    assert.equal(s.tone, 'success')
    assert.equal(s.message, '12/12 chunks embedded · indexed in Azure')
  })
  it('does not mention Azure when it is not configured', () => {
    const s = summarizeUpload({ ...ok, azure: { enabled: false, indexed: 0, total: 0, error: null } })
    assert.equal(s.tone, 'success')
    assert.equal(s.message, '12/12 chunks embedded · Azure Search not configured')
  })
  it('warns on partial embedding', () => {
    const s = summarizeUpload({ ...ok, embedded_count: 5 })
    assert.equal(s.tone, 'warning')
    assert.match(s.message, /^Only 5\/12 chunks embedded/)
  })
  it('warns when nothing is embedded', () => {
    const s = summarizeUpload({ ...ok, embedded_count: 0 })
    assert.equal(s.tone, 'warning')
    assert.match(s.message, /^0\/12 chunks embedded/)
  })
  it('warns on Azure failure and includes the error', () => {
    const s = summarizeUpload({ ...ok, azure: { enabled: true, indexed: 0, total: 12, error: 'quota' } })
    assert.equal(s.tone, 'warning')
    assert.match(s.message, /Azure Search indexing failed: quota/)
    assert.match(s.message, /^12\/12 chunks embedded/)
  })
  it('warns when Azure indexed fewer chunks than stored without an error', () => {
    const s = summarizeUpload({ ...ok, azure: { enabled: true, indexed: 4, total: 12, error: null } })
    assert.equal(s.tone, 'warning')
    assert.match(s.message, /4\/12 chunks indexed in Azure/)
  })
  it('falls back to has_embeddings for an old backend response', () => {
    assert.equal(summarizeUpload({ chunks_stored: 3, has_embeddings: true }).tone, 'success')
    const s = summarizeUpload({ chunks_stored: 3, has_embeddings: false })
    assert.equal(s.tone, 'warning')
    assert.match(s.message, /^0\/3 chunks embedded/)
  })
  it('warns when the file produced no chunks', () => {
    const s = summarizeUpload({ chunks_stored: 0, embedded_count: 0 })
    assert.equal(s.tone, 'warning')
    assert.match(s.message, /No chunks were stored/)
  })
})

describe('uploadedDocId', () => {
  it('prefers parent_doc_id then doc_id', () => {
    assert.equal(uploadedDocId({ parent_doc_id: 'p', doc_id: 'd' }), 'p')
    assert.equal(uploadedDocId({ doc_id: 'd' }), 'd')
    assert.equal(uploadedDocId({}), null)
  })
})

describe('pageInfo', () => {
  it('handles an empty list', () => {
    assert.deepEqual(pageInfo(0, 25, 0), { from: 0, to: 0, page: 1, pages: 1, hasPrev: false, hasNext: false })
  })
  it('computes a middle page', () => {
    assert.deepEqual(pageInfo(25, 25, 60), { from: 26, to: 50, page: 2, pages: 3, hasPrev: true, hasNext: true })
  })
  it('clamps the last page to total', () => {
    assert.deepEqual(pageInfo(50, 25, 60), { from: 51, to: 60, page: 3, pages: 3, hasPrev: true, hasNext: false })
  })
  it('clamps an offset past the end (page emptied by a delete)', () => {
    assert.deepEqual(pageInfo(25, 25, 25), { from: 1, to: 25, page: 1, pages: 1, hasPrev: false, hasNext: false })
  })
  it('an exact multiple has no extra page', () => {
    assert.equal(pageInfo(0, 25, 50).pages, 2)
  })
})

describe('lastValidOffset', () => {
  it('returns 0 for empty and single page', () => {
    assert.equal(lastValidOffset(0, 25), 0)
    assert.equal(lastValidOffset(25, 25), 0)
  })
  it('returns the start of the last page', () => {
    assert.equal(lastValidOffset(26, 25), 25)
    assert.equal(lastValidOffset(60, 25), 50)
  })
})

describe('removalScope / deleteSuccessMessage', () => {
  it('mentions Azure Search only when enabled', () => {
    assert.equal(removalScope(true), 'the database and Azure Search')
    assert.equal(removalScope(false), 'the database')
    assert.equal(deleteSuccessMessage('a.pdf', true), 'Deleted "a.pdf" from the database and Azure Search.')
    assert.equal(deleteSuccessMessage('a.pdf', false), 'Deleted "a.pdf" from the database.')
  })
})

describe('deleteFailureMessage', () => {
  it('502 says nothing was deleted and can be retried', () => {
    const m = deleteFailureMessage(502, 'azure down', 'list')
    assert.match(m.text, /Nothing was deleted/)
    assert.match(m.text, /try again/i)
    assert.match(m.text, /azure down/)
    assert.equal(m.refresh, false)
  })
  it('404 says already gone and asks for a refresh', () => {
    const m = deleteFailureMessage(404, 'not found', 'list')
    assert.match(m.text, /already deleted/i)
    assert.match(m.text, /list has been refreshed/)
    assert.equal(m.refresh, true)
  })
  it('404 on the detail page does not mention the list', () => {
    const m = deleteFailureMessage(404, 'not found', 'detail')
    assert.match(m.text, /already deleted/i)
    assert.doesNotMatch(m.text, /list/)
  })
  it('other errors pass the detail through', () => {
    const m = deleteFailureMessage(500, 'boom', 'list')
    assert.match(m.text, /boom/)
    assert.equal(m.refresh, false)
  })
})
