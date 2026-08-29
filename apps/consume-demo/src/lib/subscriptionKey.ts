/**
 * The API subscription key: the header it travels in, and how it is shown.
 *
 * WHAT THIS CREDENTIAL IS
 *
 * One pre-shared value an operator configures on the server as
 * `POLICY_SUBSCRIPTION_KEY`. A caller presenting it in
 * `X-Policy-Subscription-Key` is a proved identity — the single system identity
 * the operator configured, holding the role they configured. It is not a bearer
 * token: no issuer, no expiry, no claims, no per-caller attribution.
 *
 * WHY THIS PAGE SHOWS IT RATHER THAN MASKING IT
 *
 * An earlier version of this playground masked the credential everywhere and
 * emitted the mask from Copy and Download. That is the right behaviour for a
 * personal bearer token, which identifies a human being and is theirs alone.
 * It is the wrong behaviour here, and hiding it made the page worse at its one
 * job: this is a local demonstration whose whole purpose is to show the exact
 * request an integrator must reproduce, and a raw HTTP example with sixteen
 * asterisks where the credential goes cannot be pasted, cannot be compared
 * against a failing call, and cannot be checked for a typo — which is the
 * single most common reason a first integration returns 401.
 *
 * So the value is visible, copied and downloaded as itself. That is a decision
 * about **this local demo and a key the operator generated for it**, and it is
 * not a pattern to carry anywhere else. The rule that still holds without
 * exception is the one about persistence: the key lives in React state for the
 * life of the tab, and is never written to `localStorage`, `sessionStorage`, a
 * cookie, the URL or the console. A value on screen is gone when the tab is;
 * a value in storage is not.
 *
 * `docs/external-consumption.md` states the production position in full: a
 * browser client must not hold a shared subscription key at all, because a
 * credential shipped to a browser is a credential shipped to everyone who
 * loads the page.
 */

/** The header the key travels in. Not `Authorization`: this is not a token. */
export const SUBSCRIPTION_KEY_HEADER = 'X-Policy-Subscription-Key'

/**
 * The environment variable every *exported* example reads the key from.
 *
 * Snippets that leave this page are pasted into somebody else's service, so
 * they must never carry a literal credential — the reader would ship it. They
 * read `$POLICY_SUBSCRIPTION_KEY` instead, which is also the name the server
 * setting uses, so there is one word for one thing across the whole product.
 */
export const SUBSCRIPTION_KEY_ENV = 'POLICY_SUBSCRIPTION_KEY'

/**
 * The Vite variable this demo may be prefilled from locally.
 *
 * Named here so the warning beside the field, the README and the isolation
 * guard all refer to the same string. Vite inlines any `VITE_`-prefixed value
 * into the built bundle, which is exactly why the committed `.env.example`
 * leaves it blank and why this is documented as a local-demonstration
 * convenience rather than a way to configure a client.
 */
export const SUBSCRIPTION_KEY_VITE_VAR = 'VITE_POLICY_SUBSCRIPTION_KEY'

/** What a raw-HTTP or header example shows when no key has been entered yet. */
export const SUBSCRIPTION_KEY_PLACEHOLDER = '<your subscription key>'

/**
 * The `X-Policy-Subscription-Key` line as the Raw HTTP tab renders it.
 *
 * An empty field renders the placeholder rather than an empty header, because
 * `X-Policy-Subscription-Key:` with nothing after it is a valid-looking line
 * that would send a reader looking for a server fault.
 */
export function subscriptionKeyHeaderLine(key: string): string {
  const value = key.trim()
  return `${SUBSCRIPTION_KEY_HEADER}: ${value.length > 0 ? value : SUBSCRIPTION_KEY_PLACEHOLDER}`
}

/** The same line for an exported snippet, which reads its value from the shell. */
export function subscriptionKeyHeaderLineForExport(): string {
  return `${SUBSCRIPTION_KEY_HEADER}: $${SUBSCRIPTION_KEY_ENV}`
}

/**
 * Whether a run of the key appears in some text.
 *
 * Retained from the masking version because the property it guards did not go
 * away: the key may be *displayed*, and may still never be *persisted*. The
 * tests use this to assert that nothing reached `localStorage`,
 * `sessionStorage`, a cookie or the URL, and that an exported snippet carries
 * the environment-variable name instead of a value.
 *
 * Short keys are not checked below eight characters, because at that length a
 * "substring of the key" is indistinguishable from ordinary English and the
 * check would fire on the word `scenario`.
 */
export function containsKeyFragment(text: string, key: string, minimumRun = 8): boolean {
  const candidate = key.trim()
  if (candidate.length < minimumRun) return false
  for (let start = 0; start + minimumRun <= candidate.length; start += 1) {
    if (text.includes(candidate.slice(start, start + minimumRun))) return true
  }
  return false
}
