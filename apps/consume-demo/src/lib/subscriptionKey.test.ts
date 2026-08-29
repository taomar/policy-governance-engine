import { describe, expect, it } from 'vitest'
import {
  SUBSCRIPTION_KEY_ENV,
  SUBSCRIPTION_KEY_HEADER,
  SUBSCRIPTION_KEY_PLACEHOLDER,
  SUBSCRIPTION_KEY_VITE_VAR,
  containsKeyFragment,
  subscriptionKeyHeaderLine,
  subscriptionKeyHeaderLineForExport,
} from './subscriptionKey'

/**
 * The credential vocabulary, pinned.
 *
 * These are strings the server, the docs, the snippets and this page all have
 * to agree on. A header spelled two ways is a 401 nobody can explain, and an
 * environment variable spelled two ways is a paragraph of documentation that
 * silently stops matching the thing it describes.
 */

describe('the names', () => {
  it('uses a dedicated header rather than Authorization', () => {
    expect(SUBSCRIPTION_KEY_HEADER).toBe('X-Policy-Subscription-Key')
    // A subscription key has no issuer, no expiry and no claims. Sharing the
    // Authorization header with bearer tokens would mean every proxy rule and
    // every reader has to guess which of two credential formats a request
    // carries.
    expect(SUBSCRIPTION_KEY_HEADER.toLowerCase()).not.toContain('authorization')
  })

  it('names the same environment variable the server setting uses', () => {
    expect(SUBSCRIPTION_KEY_ENV).toBe('POLICY_SUBSCRIPTION_KEY')
    expect(SUBSCRIPTION_KEY_VITE_VAR).toBe(`VITE_${SUBSCRIPTION_KEY_ENV}`)
  })
})

describe('the raw HTTP header line', () => {
  it('shows the key as it will be sent', () => {
    // Deliberate, and the reversal of an earlier masking decision: this is a
    // local demonstration of an operator-generated key, and an example with
    // asterisks where the credential goes cannot be compared against the 401
    // it is meant to explain.
    expect(subscriptionKeyHeaderLine('abc123')).toBe('X-Policy-Subscription-Key: abc123')
  })

  it('trims what the field carries, so a pasted newline is not shown as one', () => {
    expect(subscriptionKeyHeaderLine('  abc123\n')).toBe('X-Policy-Subscription-Key: abc123')
  })

  it('renders a placeholder rather than an empty header', () => {
    // `X-Policy-Subscription-Key:` with nothing after it is a valid-looking
    // line. A reader comparing it against a failing call would go looking for
    // a server fault instead of for the field they have not filled in.
    expect(subscriptionKeyHeaderLine('')).toBe(
      `X-Policy-Subscription-Key: ${SUBSCRIPTION_KEY_PLACEHOLDER}`,
    )
    expect(subscriptionKeyHeaderLine('   ')).toBe(
      `X-Policy-Subscription-Key: ${SUBSCRIPTION_KEY_PLACEHOLDER}`,
    )
  })

  it('reads from the environment in a line meant to leave this page', () => {
    // An exported snippet is pasted into somebody else's service. A literal
    // credential in it is a credential they will ship.
    const line = subscriptionKeyHeaderLineForExport()
    expect(line).toBe('X-Policy-Subscription-Key: $POLICY_SUBSCRIPTION_KEY')
    expect(line).toContain(`$${SUBSCRIPTION_KEY_ENV}`)
  })
})

describe('containsKeyFragment', () => {
  it('finds any run of the key, not just the whole value', () => {
    const key = 'abcdefghijklmnopqr'
    expect(containsKeyFragment(`X-Policy-Subscription-Key: ${key}`, key)).toBe(true)
    expect(containsKeyFragment('prefix ijklmnopqr suffix', key)).toBe(true)
    expect(containsKeyFragment('nothing of the sort', key)).toBe(false)
  })

  it('says nothing about very short values', () => {
    // At three characters a "substring of the key" is indistinguishable from
    // ordinary English, and the check would fire on the word `scenario`.
    expect(containsKeyFragment('the scenario field', 'nar')).toBe(false)
  })

  it('reports the export line as carrying no fragment of a real key', () => {
    const key = 'a-real-looking-key-0123456789'
    expect(containsKeyFragment(subscriptionKeyHeaderLineForExport(), key)).toBe(false)
  })
})
