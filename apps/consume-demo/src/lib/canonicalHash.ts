/**
 * SHA-256 and the server's canonical-JSON rule, in the browser.
 *
 * WHY A HAND-WRITTEN SHA-256
 *
 * The obvious implementation is `crypto.subtle.digest`, and it is the wrong one
 * here for two reasons. It is asynchronous, and the request hash is recomputed
 * on every keystroke in the inspector -- an async hash means the displayed
 * value trails the displayed request body, which is precisely the kind of small
 * lie this page exists not to tell. And `crypto.subtle` is unavailable on an
 * insecure origin, so a demo served over plain HTTP on a colleague's machine
 * would lose its preview with no honest way to explain why.
 *
 * WHY IT MUST MATCH THE SERVER
 *
 * `contracts/canonical.py` hashes `json.dumps(data, sort_keys=True,
 * separators=(",", ":"), ensure_ascii=False)`. `canonicalJson` below reproduces
 * that: keys sorted at every level, no insignificant whitespace, non-ASCII kept
 * as itself. That agreement is what lets the page compare its own preview
 * against `request.scenario_hash` and `request.additional_instructions_hash` on
 * the receipt and say something true about whether they match, rather than
 * showing a number nobody can check.
 */

type Json = string | number | boolean | null | Json[] | { [key: string]: Json }

const K: readonly number[] = [
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]

function rotr(value: number, bits: number): number {
  return (value >>> bits) | (value << (32 - bits))
}

/** SHA-256 over UTF-8 bytes, returned as lowercase hex. */
export function sha256Hex(input: string): string {
  const bytes = new TextEncoder().encode(input)

  // Padding: a single 0x80 byte, zeroes, then the bit length as a big-endian
  // 64-bit integer.
  const bitLength = bytes.length * 8
  const paddedLength = (((bytes.length + 9) >> 6) + 1) << 6
  const padded = new Uint8Array(paddedLength)
  padded.set(bytes)
  padded[bytes.length] = 0x80
  const view = new DataView(padded.buffer)
  // The high word is written too, so a >512MB input would still be sealed
  // correctly rather than silently truncated.
  view.setUint32(paddedLength - 8, Math.floor(bitLength / 0x100000000), false)
  view.setUint32(paddedLength - 4, bitLength >>> 0, false)

  const h = [
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
  ]

  const w = new Uint32Array(64)

  for (let offset = 0; offset < paddedLength; offset += 64) {
    for (let i = 0; i < 16; i += 1) {
      w[i] = view.getUint32(offset + i * 4, false)
    }
    for (let i = 16; i < 64; i += 1) {
      const s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >>> 3)
      const s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >>> 10)
      w[i] = (w[i - 16] + s0 + w[i - 7] + s1) >>> 0
    }

    let [a, b, c, d, e, f, g, hh] = h

    for (let i = 0; i < 64; i += 1) {
      const S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)
      const ch = (e & f) ^ (~e & g)
      const temp1 = (hh + S1 + ch + K[i] + w[i]) >>> 0
      const S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)
      const maj = (a & b) ^ (a & c) ^ (b & c)
      const temp2 = (S0 + maj) >>> 0

      hh = g
      g = f
      f = e
      e = (d + temp1) >>> 0
      d = c
      c = b
      b = a
      a = (temp1 + temp2) >>> 0
    }

    h[0] = (h[0] + a) >>> 0
    h[1] = (h[1] + b) >>> 0
    h[2] = (h[2] + c) >>> 0
    h[3] = (h[3] + d) >>> 0
    h[4] = (h[4] + e) >>> 0
    h[5] = (h[5] + f) >>> 0
    h[6] = (h[6] + g) >>> 0
    h[7] = (h[7] + hh) >>> 0
  }

  return h.map((word) => word.toString(16).padStart(8, '0')).join('')
}

/**
 * The server's canonical JSON: keys sorted at every level, no insignificant
 * whitespace, non-ASCII characters kept as themselves.
 *
 * `JSON.stringify` already agrees with Python's `json.dumps` on escaping --
 * both emit `\n`, `\t`, `\r`, `\b`, `\f`, `\"` and `\\` in short form and
 * `\u00xx` for the remaining control characters, and neither escapes `/`. The
 * only thing that has to be added here is the key ordering.
 */
export function canonicalJson(value: Json): string {
  if (value === null || typeof value !== 'object') {
    return JSON.stringify(value)
  }
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(',')}]`
  }
  const keys = Object.keys(value).sort()
  const body = keys.map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',')
  return `{${body}}`
}

/** A stable SHA-256 hex digest over the canonical JSON of `value`. */
export function canonicalHash(value: Json): string {
  return sha256Hex(canonicalJson(value))
}

/**
 * The digest of the question alone, as `case_decision.scenario_hash` computes
 * it. Taken over the scenario exactly as sent -- the server does not normalise
 * it, so neither does this.
 */
export function scenarioHash(scenario: string): string {
  return canonicalHash({ scenario })
}

/**
 * The digest of the normalised guidance, as
 * `case_decision.additional_instructions_hash` computes it. An empty string
 * hashes to a stable value rather than to null: "no guidance was given" is a
 * fact worth sealing.
 */
export function additionalInstructionsHash(value: string): string {
  return canonicalHash({ additional_instructions: value })
}

/**
 * The canonical hash of the request an idempotency key is bound to, as
 * `case_decision.request_hash` computes it.
 *
 * The correlation id is deliberately excluded -- a caller retrying under a new
 * correlation id is retrying the same request. The guidance is deliberately
 * included -- it changes the answer the caller receives, so replaying an
 * earlier receipt against changed guidance would be a silent substitution.
 */
export function requestHash(input: {
  policySetKey: string
  scenario: string
  provisionId?: string | null
  reasoningEffort: string
  additionalInstructions: string
}): string {
  return canonicalHash({
    policy_set_key: input.policySetKey,
    scenario: input.scenario,
    provision_id: input.provisionId || null,
    reasoning_effort: input.reasoningEffort,
    additional_instructions: input.additionalInstructions,
  })
}

/**
 * The server's whitespace normalisation for caller guidance, reproduced from
 * `normalise_additional_instructions`.
 *
 * It is reproduced rather than skipped because the character limit is applied
 * to the normalised form: a client that counted raw characters would let a
 * caller submit something the server refuses, and would refuse something the
 * server would have accepted. Line endings unify, runs of blank lines collapse
 * to one, spaces and tabs inside a line collapse to a single space, each line
 * is stripped, and the whole is stripped. Line structure survives.
 */
export function normaliseAdditionalInstructions(value: string | null | undefined): string {
  if (!value) return ''

  const text = String(value).replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  const lines = text.split('\n').map((line) => line.split(/\s+/).filter(Boolean).join(' '))

  const collapsed: string[] = []
  for (const line of lines) {
    if (!line && (collapsed.length === 0 || !collapsed[collapsed.length - 1])) continue
    collapsed.push(line)
  }

  return collapsed.join('\n').trim()
}
