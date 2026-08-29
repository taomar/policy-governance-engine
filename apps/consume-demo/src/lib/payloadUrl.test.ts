import { describe, expect, it } from 'vitest'
import { resolvePayloadUrl } from './payloadUrl'

/**
 * The regression suite for a defect found in a live browser.
 *
 * The server returns `payload_url` as a relative path, correctly: production
 * reaches the API through the web tier's `/api` proxy, so an absolute URL built
 * server-side would name a host the caller never used.
 *
 * A browser resolves a relative `href` against the *document's* origin. This
 * page is served from 5179 and calls an API elsewhere, so rendering the value
 * raw sent every "View payload" link to `http://localhost:5179/api/policy-
 * payload/…` — the playground's own origin, which serves nothing of the sort.
 * It looked like a working link and 404ed on the wrong server.
 */

const BASE = 'http://localhost:8010'

describe('a relative payload_url resolves against the API base', () => {
  it('prefixes the configured base', () => {
    expect(resolvePayloadUrl('/api/policy-payload/SUP-3.2', BASE)).toBe(
      'http://localhost:8010/api/policy-payload/SUP-3.2',
    )
  })

  it('resolves against the base the page is calling, not the page it is served from', () => {
    // The defect, stated as the thing that must not happen.
    const resolved = resolvePayloadUrl('/api/policy-payload/SUP-3.2', 'http://localhost:8050')
    expect(resolved).toBe('http://localhost:8050/api/policy-payload/SUP-3.2')
    expect(resolved).not.toContain('5179')
  })

  it('tolerates a base with a trailing slash', () => {
    expect(resolvePayloadUrl('/api/policy-payload/X', 'http://localhost:8010/')).toBe(
      'http://localhost:8010/api/policy-payload/X',
    )
  })

  it('tolerates a path that does not start with a slash', () => {
    expect(resolvePayloadUrl('api/policy-payload/X', BASE)).toBe(
      'http://localhost:8010/api/policy-payload/X',
    )
  })

  it('trims surrounding whitespace before deciding anything', () => {
    expect(resolvePayloadUrl('  /api/policy-payload/X  ', BASE)).toBe(
      'http://localhost:8010/api/policy-payload/X',
    )
  })

  it('handles a base that carries a path prefix', () => {
    expect(resolvePayloadUrl('/api/policy-payload/X', 'https://gateway.example.com/policy')).toBe(
      'https://gateway.example.com/policy/api/policy-payload/X',
    )
  })
})

describe('an absolute payload_url is left exactly as it came', () => {
  it.each([
    'https://policy.example.com/api/policy-payload/SUP-3.2',
    'http://policy.example.com/api/policy-payload/SUP-3.2',
    // Protocol-relative. Already absolute to the browser, and rewriting it
    // would point a reader at a different server while looking like a fix.
    '//policy.example.com/api/policy-payload/SUP-3.2',
  ])('%s', (url) => {
    expect(resolvePayloadUrl(url, BASE)).toBe(url)
  })

  it('does not rewrite an absolute URL even when the base disagrees with it', () => {
    // A receipt read back from storage carries whatever was written when the
    // decision was made. That is the record, and it is not this page's to edit.
    const stored = 'https://policy.example.com/api/policy-payload/SUP-3.2'
    expect(resolvePayloadUrl(stored, 'http://localhost:8010')).toBe(stored)
  })
})

describe('there is nothing to link to', () => {
  it.each([null, undefined, '', '   '])('%s yields null', (value) => {
    expect(resolvePayloadUrl(value as string | null | undefined, BASE)).toBeNull()
  })

  it('returns the relative value unchanged when no base is configured yet', () => {
    // Half a URL would be worse than the server's own answer: at least the
    // latter is what the receipt actually says.
    expect(resolvePayloadUrl('/api/policy-payload/X', '')).toBe('/api/policy-payload/X')
    expect(resolvePayloadUrl('/api/policy-payload/X', '   ')).toBe('/api/policy-payload/X')
  })
})
