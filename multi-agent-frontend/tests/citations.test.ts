import assert from 'node:assert/strict'
import { test } from 'node:test'
import { linkCitationRefs } from '../src/lib/citations.ts'

test('links a mid-sentence ref', () => {
  assert.equal(linkCitationRefs('Theo quy định [D1] thì đúng.'), 'Theo quy định [D1](#cite-D1) thì đúng.')
})

test('links a ref right before a period without detaching it', () => {
  assert.equal(linkCitationRefs('Kết luận là đúng [W1].'), 'Kết luận là đúng [W1](#cite-W1).')
})

test('leaves refs inside inline code untouched', () => {
  assert.equal(linkCitationRefs('Gõ `[D1]` rồi xem [D2]'), 'Gõ `[D1]` rồi xem [D2](#cite-D2)')
})

test('leaves refs inside a fenced code block untouched', () => {
  const body = 'Trước [D1]\n```md\nví dụ [D1]\n```\nSau [W1]'
  assert.equal(linkCitationRefs(body), 'Trước [D1](#cite-D1)\n```md\nví dụ [D1]\n```\nSau [W1](#cite-W1)')
})

test('leaves refs inside a tilde fence untouched', () => {
  assert.equal(linkCitationRefs('~~~\n[D1]\n~~~'), '~~~\n[D1]\n~~~')
})

test('links every ref regardless of whether a citation exists (the UI decides how to render it)', () => {
  assert.equal(linkCitationRefs('Không có nguồn [D9].'), 'Không có nguồn [D9](#cite-D9).')
})

test('does not re-link a ref that is already a link', () => {
  assert.equal(linkCitationRefs('Xem [D1](https://example.com) nhé'), 'Xem [D1](https://example.com) nhé')
})

test('handles Vietnamese diacritics around the ref', () => {
  assert.equal(
    linkCitationRefs('Thời hạn bảo hành là 12 tháng[D1], đồng thời “được gia hạn”[W1].'),
    'Thời hạn bảo hành là 12 tháng[D1](#cite-D1), đồng thời “được gia hạn”[W1](#cite-W1).',
  )
})

test('returns an empty string unchanged', () => {
  assert.equal(linkCitationRefs(''), '')
})

test('links adjacent refs separately', () => {
  assert.equal(linkCitationRefs('Đúng [D1][W1]'), 'Đúng [D1](#cite-D1)[W1](#cite-W1)')
})

test('links a ref inside a blockquote line', () => {
  assert.equal(linkCitationRefs('> Trích dẫn quan trọng [D1]\n> dòng hai'), '> Trích dẫn quan trọng [D1](#cite-D1)\n> dòng hai')
})

test('escapes a bang before a ref so it is not parsed as an image', () => {
  assert.equal(linkCitationRefs('Hạn chót là ngày mai![D1] Đúng vậy.'), 'Hạn chót là ngày mai\\![D1](#cite-D1) Đúng vậy.')
})

test('does not double-escape a bang that is already escaped', () => {
  assert.equal(linkCitationRefs('Thật \\![D1] nhé'), 'Thật \\![D1](#cite-D1) nhé')
})

test('escapes a bang that follows an escaped backslash', () => {
  assert.equal(linkCitationRefs('Thật \\\\![D1] nhé'), 'Thật \\\\\\![D1](#cite-D1) nhé')
})

test('leaves an escaped bracket ref untouched so it renders as literal text', () => {
  assert.equal(linkCitationRefs('Gõ \\[D1] để xem'), 'Gõ \\[D1] để xem')
})

test('links a ref after an escaped backslash', () => {
  assert.equal(linkCitationRefs('Gõ \\\\[D1] nhé'), 'Gõ \\\\[D1](#cite-D1) nhé')
})

test('preserves CRLF, linking outside a fence and not inside it', () => {
  const body = 'A [D1]\r\n```\r\n[D1]\r\n```\r\nB [W1]'
  assert.equal(linkCitationRefs(body), 'A [D1](#cite-D1)\r\n```\r\n[D1]\r\n```\r\nB [W1](#cite-W1)')
})

test('an unclosed fence protects the rest of the text', () => {
  assert.equal(linkCitationRefs('A [D1]\n```\n[D1]\n[W1]'), 'A [D1](#cite-D1)\n```\n[D1]\n[W1]')
})
