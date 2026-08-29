import { describe, expect, it } from 'vitest'
import {
  additionalInstructionsHash,
  canonicalJson,
  normaliseAdditionalInstructions,
  requestHash,
  scenarioHash,
  sha256Hex,
} from './canonicalHash'

/**
 * The client's hash must be the server's hash.
 *
 * The expected digests below were produced by the server's own
 * `contracts/canonical.canonical_hash` over the same inputs. If a future change
 * to `canonicalJson` -- key ordering, escaping, whitespace -- diverges from
 * `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`, these
 * fail, and they fail loudly rather than by the page quietly showing a preview
 * hash that no server value will ever match.
 */
describe('sha256Hex', () => {
  it('matches the published digests for the standard vectors', () => {
    expect(sha256Hex('')).toBe(
      'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    )
    expect(sha256Hex('abc')).toBe(
      'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad',
    )
  })

  it('hashes multi-byte characters as UTF-8, not as UTF-16 code units', () => {
    // "£" is one code unit but two UTF-8 bytes. A digest taken over code units
    // would diverge from the server here and nowhere else, which is the worst
    // place for a hash to diverge.
    expect(sha256Hex('£')).toBe(
      'b4fe151e413445357b1c0935e7cf04a429492ebd23dc62bfadb2f898c431c1fd',
    )
  })

  it('handles inputs that cross the 64-byte block boundary', () => {
    const long = 'a'.repeat(1000)
    expect(sha256Hex(long)).toBe(
      '41edece42d63e8d9bf515a9ba6932e1c20cbc9f5a5d134645adb5db1b9737ea3',
    )
  })
})

describe('canonicalJson', () => {
  it('sorts keys at every level and emits no insignificant whitespace', () => {
    expect(canonicalJson({ b: 1, a: { d: 2, c: 3 } })).toBe('{"a":{"c":3,"d":2},"b":1}')
  })

  it('keeps null distinct from an absent key', () => {
    expect(canonicalJson({ provision_id: null })).toBe('{"provision_id":null}')
  })

  it('preserves array order, which is content rather than layout', () => {
    expect(canonicalJson({ xs: [3, 1, 2] })).toBe('{"xs":[3,1,2]}')
  })
})

describe('the hashes the receipt can be checked against', () => {
  it('computes the scenario hash the server computes', () => {
    // canonical_hash({"scenario": "A supplier asks about payment terms."})
    expect(scenarioHash('A supplier asks about payment terms.')).toBe(
      '0dcc8729feb2df19550a042031b7180ad1f9a3e78fefa4c008583b5007d568f3',
    )
  })

  it('gives empty guidance a stable digest rather than treating it as null', () => {
    expect(additionalInstructionsHash('')).toBe(sha256Hex('{"additional_instructions":""}'))
    expect(additionalInstructionsHash('')).not.toBe(additionalInstructionsHash(' '))
  })

  it('binds the request hash to guidance, so changing guidance rotates it', () => {
    const common = {
      policySetKey: 'demo-project',
      scenario: 'A supplier asks about payment terms.',
      provisionId: null,
      reasoningEffort: 'medium',
    }
    const without = requestHash({ ...common, additionalInstructions: '' })
    const withGuidance = requestHash({
      ...common,
      additionalInstructions: 'Explain the approval path first',
    })

    expect(withGuidance).not.toBe(without)
    // And returning to the original guidance returns the original hash: the
    // preview is a function of the request, not of the edit history.
    expect(requestHash({ ...common, additionalInstructions: '' })).toBe(without)
  })

  it('excludes the correlation id, so a retry under a new id is the same request', () => {
    // There is no correlation parameter to pass; this asserts the preimage
    // shape directly so the omission cannot be undone without failing here.
    const hash = requestHash({
      policySetKey: 'k',
      scenario: 's',
      provisionId: null,
      reasoningEffort: 'low',
      additionalInstructions: '',
    })
    expect(hash).toBe(
      sha256Hex(
        '{"additional_instructions":"","policy_set_key":"k","provision_id":null,"reasoning_effort":"low","scenario":"s"}',
      ),
    )
  })
})

describe('normaliseAdditionalInstructions', () => {
  it('unifies line endings so a Windows client is not told its body changed', () => {
    expect(normaliseAdditionalInstructions('a\r\nb')).toBe('a\nb')
    expect(normaliseAdditionalInstructions('a\rb')).toBe('a\nb')
  })

  it('collapses runs of blank lines to one and inner whitespace to a space', () => {
    expect(normaliseAdditionalInstructions('a\n\n\n\nb')).toBe('a\n\nb')
    expect(normaliseAdditionalInstructions('a   \t  b')).toBe('a b')
  })

  it('keeps line structure, because a short list of preferences means the list', () => {
    expect(normaliseAdditionalInstructions('one\ntwo\nthree')).toBe('one\ntwo\nthree')
  })

  it('returns an empty string for nothing at all', () => {
    expect(normaliseAdditionalInstructions('')).toBe('')
    expect(normaliseAdditionalInstructions('   \n  \n ')).toBe('')
    expect(normaliseAdditionalInstructions(null)).toBe('')
    expect(normaliseAdditionalInstructions(undefined)).toBe('')
  })
})
