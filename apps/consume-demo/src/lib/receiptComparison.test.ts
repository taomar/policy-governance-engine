import { describe, expect, it } from 'vitest'
import {
  allPublishedPoliciesWereEvaluated,
  compareReceipts,
  guidanceEchoState,
} from './receiptComparison'
import { makeEnvelope } from './testFixtures'

describe('compareReceipts', () => {
  it('matches when all five fields are identical', () => {
    const result = compareReceipts(makeEnvelope(), makeEnvelope())
    expect(result.matches).toBe(true)
    expect(result.rows.map((row) => row.id)).toEqual([
      'decision-hash',
      'policy-version',
      'timestamp',
      'guidance',
      'profile',
    ])
  })

  it('fails on an altered decision hash', () => {
    const result = compareReceipts(
      makeEnvelope(),
      makeEnvelope({ decision_hash: 'd'.repeat(64) }),
    )
    expect(result.matches).toBe(false)
    expect(result.rows.find((r) => r.id === 'decision-hash')?.verdict).toBe('mismatch')
  })

  it('fails on altered caller guidance and flags it specifically', () => {
    const stored = makeEnvelope()
    stored.request = { ...stored.request, additional_instructions: 'SOMETHING ELSE' }
    const result = compareReceipts(makeEnvelope(), stored)
    expect(result.matches).toBe(false)
    expect(result.guidanceMismatch).toBe(true)
  })

  it('treats absent versus empty-string guidance as a MISMATCH, not a match', () => {
    // The quiet failure this whole module exists for: both are falsy, both
    // render as nothing, and a naive comparison calls them equal.
    const returned = makeEnvelope()
    returned.request = { ...returned.request, additional_instructions: undefined }
    const stored = makeEnvelope()
    stored.request = { ...stored.request, additional_instructions: '' }

    const result = compareReceipts(returned, stored)
    expect(result.matches).toBe(false)
    expect(result.guidanceMismatch).toBe(true)

    const row = result.rows.find((r) => r.id === 'guidance')
    expect(row?.presenceDiffers).toBe(true)
    expect(row?.returned).toBeNull()
    expect(row?.stored).toBe('')
  })

  it('matches when both sides are absent', () => {
    const returned = makeEnvelope()
    returned.request = { ...returned.request, additional_instructions: undefined }
    const stored = makeEnvelope()
    stored.request = { ...stored.request, additional_instructions: undefined }
    const result = compareReceipts(returned, stored)
    expect(result.rows.find((r) => r.id === 'guidance')?.verdict).toBe('match')
  })

  it('fails on a changed instruction profile', () => {
    const stored = makeEnvelope()
    stored.trace = { ...stored.trace, prompt_version: 'ai-case-intent-v3' }
    expect(compareReceipts(makeEnvelope(), stored).matches).toBe(false)
  })

  it('fails on a changed timestamp or policy version', () => {
    expect(
      compareReceipts(makeEnvelope(), makeEnvelope({ decided_at: '2020-01-01T00:00:00Z' })).matches,
    ).toBe(false)
    expect(
      compareReceipts(
        makeEnvelope(),
        makeEnvelope({ active_version: { version_id: 'other', version_number: 8 } }),
      ).matches,
    ).toBe(false)
  })
})

describe('allPublishedPoliciesWereEvaluated — the over-claim guard', () => {
  it('is true only for not_narrowed, or narrowed with nothing discarded', () => {
    expect(
      allPublishedPoliciesWereEvaluated(
        makeEnvelope({ retrieval: { status: 'not_narrowed' } }),
      ),
    ).toBe(true)
    expect(
      allPublishedPoliciesWereEvaluated(
        makeEnvelope({ retrieval: { status: 'narrowed', policies_discarded: 0 }, considered: [] }),
      ),
    ).toBe(true)
  })

  it('is false whenever narrowing discarded anything', () => {
    expect(allPublishedPoliciesWereEvaluated(makeEnvelope())).toBe(false)
    expect(
      allPublishedPoliciesWereEvaluated(
        makeEnvelope({ retrieval: { status: 'narrowed', policies_discarded: 1 } }),
      ),
    ).toBe(false)
  })

  it('falls back to counting discarded policies when the count is absent', () => {
    expect(
      allPublishedPoliciesWereEvaluated(
        makeEnvelope({
          retrieval: { status: 'narrowed' },
          considered: [{ provision_key: 'a', retained: false }],
        }),
      ),
    ).toBe(false)
  })

  it('is false for every retrieval status that did not evaluate everything', () => {
    for (const status of ['no_match', 'index_not_built', 'failed', 'bypassed', 'empty']) {
      expect(allPublishedPoliciesWereEvaluated(makeEnvelope({ retrieval: { status } }))).toBe(false)
    }
  })
})

describe('guidanceEchoState', () => {
  it('reports echoed when the server returned the guidance', () => {
    expect(guidanceEchoState(makeEnvelope(), 'Explain the approval path first')).toBe('echoed')
  })

  it('reports absent when none was sent and none was returned', () => {
    const envelope = makeEnvelope()
    envelope.request = { ...envelope.request, additional_instructions: undefined }
    expect(guidanceEchoState(envelope, undefined)).toBe('absent')
  })

  it('reports empty when the server recorded an empty string', () => {
    const envelope = makeEnvelope()
    envelope.request = { ...envelope.request, additional_instructions: '' }
    expect(guidanceEchoState(envelope, undefined)).toBe('empty')
  })

  it('reports not-echoed when guidance was sent and the key came back missing', () => {
    const envelope = makeEnvelope()
    envelope.request = { ...envelope.request, additional_instructions: undefined }
    expect(guidanceEchoState(envelope, 'Explain the approval path first')).toBe('not-echoed')
  })

  it('reports not-echoed when guidance was sent and an empty string came back', () => {
    const envelope = makeEnvelope()
    envelope.request = { ...envelope.request, additional_instructions: '' }
    expect(guidanceEchoState(envelope, 'Explain the approval path first')).toBe('not-echoed')
  })
})
