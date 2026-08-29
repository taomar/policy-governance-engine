import { joinUrl } from './requestBody'

/**
 * Resolve a receipt's `payload_url` against the API this page is calling.
 *
 * THE DEFECT THIS EXISTS TO FIX
 *
 * The server returns `payload_url` as a **relative** path — `/api/policy-payload/
 * <id>` — and it is right to. Production reaches the API through the web tier's
 * `/api` proxy, so an absolute URL built server-side would name a host the
 * caller never used.
 *
 * A browser resolves a relative `href` against the *document's* origin, not
 * against whatever base the page happens to be calling. This playground is
 * served from its own origin (5179) and calls an API somewhere else, so
 * rendering the value directly produced `http://localhost:5179/api/policy-
 * payload/…` — the playground's own origin, where nothing of the sort is
 * served. Every "View payload" link on the page was wrong, and wrong in the way
 * that is hardest to notice: it looked like a link, and it 404ed somewhere else.
 *
 * WHY IT IS RESOLVED HERE AND NOT AT THE COMPONENT
 *
 * Two components render these links, over three collections (citation
 * evidence, retained policies, discarded policies). Resolving in each would be
 * three chances to forget one. The base is passed in explicitly rather than
 * read from a module global or `import.meta.env`, because this app's whole
 * claim is that it holds no ambient state — a resolver that reached for a
 * global would be the first thing in it that did.
 *
 * ALREADY-ABSOLUTE URLS ARE LEFT ALONE
 *
 * A deployment may serve absolute payload URLs, and a receipt read back from
 * storage carries whatever was written when the decision was made. Rewriting
 * one would point a reader at the wrong server while looking like a fix.
 */
export function resolvePayloadUrl(
  payloadUrl: string | null | undefined,
  baseUrl: string,
): string | null {
  const url = (payloadUrl ?? '').trim()
  if (url.length === 0) return null

  // Any scheme, and protocol-relative `//host/path`, is already absolute and is
  // returned untouched. Matched on the shape rather than by parsing, because
  // `new URL` would also happily "succeed" on things this must not rewrite.
  if (/^[a-z][a-z0-9+.-]*:/i.test(url) || url.startsWith('//')) return url

  const base = baseUrl.trim().replace(/\/+$/, '')
  // With no base to resolve against, the relative value is returned as it came.
  // Returning a half-built URL would be worse than returning the server's own
  // answer: at least the latter is what the receipt actually says.
  if (base.length === 0) return url

  return joinUrl(base, url)
}
