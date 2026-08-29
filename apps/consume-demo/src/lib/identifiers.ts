/**
 * Client-side identifiers: the correlation id the caller chooses, and the
 * optional idempotency key.
 *
 * Both are generated *before* the request and displayed, so the value on screen
 * is the value that will be sent rather than something the user is told about
 * afterwards. A correlation id whose whole purpose is that both sides can name
 * the same event is worth very little if the caller first sees it in the reply.
 */

/**
 * A v4 UUID.
 *
 * `crypto.randomUUID` is used when it exists. It does not exist on an insecure
 * origin in some browsers, and a demonstration served over plain HTTP is a
 * realistic way to run this page, so there is a `getRandomValues` fallback that
 * produces a correctly-shaped v4 from the same CSPRNG. There is deliberately no
 * `Math.random` path: a correlation id that silently stopped being unique would
 * be worse than one the page refused to generate.
 */
export function newUuid(): string {
  const cryptoObj: Crypto | undefined = globalThis.crypto
  if (cryptoObj && typeof cryptoObj.randomUUID === 'function') {
    return cryptoObj.randomUUID()
  }

  if (!cryptoObj || typeof cryptoObj.getRandomValues !== 'function') {
    throw new Error('This browser exposes no cryptographic random source, so no correlation id can be generated.')
  }

  const bytes = cryptoObj.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80

  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

export function isUuidV4(value: string): boolean {
  return UUID_V4.test(value.trim())
}
