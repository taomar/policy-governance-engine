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
 * WHY THIS PAGE MASKS IT BY DEFAULT, AND STILL LETS YOU SEE IT
 *
 * The history here matters, because it has now gone both ways. An early version
 * masked the credential everywhere and emitted the mask from Copy and Download.
 * That was reverted, for a good reason: this is a local demonstration whose one
 * job is to show the exact request an integrator must reproduce, and a raw HTTP
 * example with sixteen asterisks where the credential goes cannot be pasted,
 * cannot be compared against a failing call, and cannot be checked for a typo —
 * which is the single most common reason a first integration returns 401.
 *
 * Showing it unconditionally solved that and created a smaller problem of its
 * own: the Raw HTTP tab is the one an integrator screen-shares, screenshots and
 * pastes into a ticket, and it rendered a live credential whether or not anyone
 * needed to read it at that moment.
 *
 * So the position is now masked **by default**, with an explicit reveal. The
 * typo can still be found — that affordance is one click away and the tests
 * hold it there — and the credential is no longer on screen for every reader of
 * every other tab. Neither of the two earlier positions had both properties.
 *
 * What has never changed, through all three versions:
 *
 *   * *Exported* snippets never carry a literal. Copy and Download read
 *     `$POLICY_SUBSCRIPTION_KEY`, because a snippet that leaves this page is
 *     pasted into somebody else's service and a reader would ship the value.
 *   * The key is never *persisted*. It lives in React state for the life of the
 *     tab and reaches no `localStorage`, `sessionStorage`, cookie, URL or
 *     console. A value on screen is gone when the tab is; a value in storage is
 *     not.
 *
 * `docs/external-consumption.md` states the production position in full: a
 * browser client must not hold a shared subscription key at all, because a
 * credential shipped to a browser is a credential shipped to everyone who
 * loads the page. Masking it on screen does not soften that.
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
 * What a masked key renders as.
 *
 * A fixed width rather than one asterisk per character: the length of a
 * credential is itself a small disclosure, and a reader who can count the dots
 * learns something they should not need. It is also visibly a mask rather than
 * a value, so nobody pastes it into a terminal expecting it to work.
 */
export const SUBSCRIPTION_KEY_MASK = '••••••••••••'

/**
 * The `X-Policy-Subscription-Key` line as the Raw HTTP tab renders it.
 *
 * An empty field renders the placeholder rather than an empty header, because
 * `X-Policy-Subscription-Key:` with nothing after it is a valid-looking line
 * that would send a reader looking for a server fault. That is true whether or
 * not the value is revealed — an absent key is not a secret and masking it
 * would hide the actual problem.
 */
export function subscriptionKeyHeaderLine(key: string, revealed = false): string {
  const value = key.trim()
  if (value.length === 0) {
    return `${SUBSCRIPTION_KEY_HEADER}: ${SUBSCRIPTION_KEY_PLACEHOLDER}`
  }
  return `${SUBSCRIPTION_KEY_HEADER}: ${revealed ? value : SUBSCRIPTION_KEY_MASK}`
}

/** The same line for an exported snippet, which reads its value from the shell. */
export function subscriptionKeyHeaderLineForExport(): string {
  return `${SUBSCRIPTION_KEY_HEADER}: $${SUBSCRIPTION_KEY_ENV}`
}

/**
 * The same request, with the credential line rewritten for export.
 *
 * Takes the lines that are on screen and replaces only the credential one, so
 * there is a single list of headers rather than two that can drift. Whatever
 * the screen is showing — masked or revealed — what leaves this page reads
 * `$POLICY_SUBSCRIPTION_KEY`, because a snippet is pasted into somebody else's
 * service and a literal in it is a credential they would ship.
 *
 * Lives here rather than inline in the inspector so the rule is stated once,
 * beside the other rules about this credential, and can be tested without
 * rendering anything.
 */
export function linesForExport(lines: string[]): string[] {
  return lines.map((line) =>
    line.startsWith(`${SUBSCRIPTION_KEY_HEADER}:`)
      ? subscriptionKeyHeaderLineForExport()
      : line,
  )
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
