/**
 * Every user-facing sentence on this page, in one place.
 *
 * Copy on a policy surface is not decoration: the difference between "no rule
 * bears on this case" and "the policies say no" is the difference between an
 * honest client and a misleading one. Several of these strings are lifted
 * verbatim from the product's own case runner so the in-product surface and
 * this external one cannot drift into describing the same server event with
 * different words.
 *
 * Nothing here is assembled from fragments at the call site. A sentence that is
 * concatenated somewhere else is a sentence nobody can review.
 */

export const HEADER = {
  title: 'Policy API Playground',
  eyebrow: 'External client demonstration',
  purpose:
    'Test how an agent, Copilot integration, workflow or business process calls one governed project.',
  demoNote:
    'Demonstration client. It talks to the policy API over HTTP only, holds your subscription key in memory for this tab, and stores nothing.',
} as const

export const DOCKET = {
  heading: 'Request docket',
  connection: 'Connection',
  request: 'Request',
  guidance: 'Caller guidance — editable',
  trace: 'Trace',
  apiBaseLabel: 'API base URL',
  projectKeyLabel: 'Project key',
  projectKeyHelper: 'Stable key used in API paths—not display name or UUID',
  subscriptionKeyLabel: 'API subscription key',
  subscriptionKeyCaption:
    'Sent as X-Policy-Subscription-Key. Held in memory only: never written to storage, the URL, or a log.',
  subscriptionKeyLocalWarning:
    'Local demonstration only. This field is shown in clear and is copied into the Raw HTTP tab, so use a key your operator generated for local use. A production browser client must never hold a shared subscription key: anything prefixed VITE_ is compiled into the bundle and served to every visitor.',
  subscriptionKeyPrefilled:
    'Prefilled from VITE_POLICY_SUBSCRIPTION_KEY in this machine’s local .env.local. That file is git-ignored and is a local-demonstration convenience only.',
  resolvedFrom: 'Resolved from the API',
  resolving: 'Resolving project identity…',
  scenarioLabel: 'Scenario',
  scenarioPlaceholder:
    'e.g. A supplier in a sanctioned jurisdiction asks whether we may proceed with a 90-day payment term.',
  reasoningLabel: 'Reasoning effort',
  callingSystemLabel: 'Calling system',
  callingSystemDefault: 'playground-demo',
  callingSystemCaption: 'Recorded on the decision so the receipt shows who called.',
  idempotencyLabel: 'Idempotency key (optional)',
  idempotencyCaption:
    'Send the same key to make a repeated submit return the original decision instead of creating a second one.',
  idempotencyConflict: 'Request changed; sending with this key may return 409',
  generate: 'Generate',
  guidanceLabel: 'Additional instructions (optional)',
  guidanceHelper:
    'Shapes explanation focus or format. It cannot override published policy, retrieval, decision status, or citation requirements.',
  guidanceExamplesCaption:
    'Examples. Guidance shapes how the answer is explained, never what the policies decide.',
  correlationLabel: 'Correlation ID',
  correlationCaption:
    'Generated here before the request so you can see the value you are about to send.',
  regenerate: 'Regenerate',
  submit: 'Send case to policy API',
  submitting: 'Sending…',
  submitCaption: 'This sends one request. Nothing is saved on this page. Ctrl or ⌘ + Enter also sends.',
  memoryOnly:
    'This page holds your subscription key in memory only. It is cleared when you close or reload the tab.',
} as const

/** The closed, hardcoded example set. Never a prompt library, never a preset store. */
export const GUIDANCE_EXAMPLES = [
  'Explain the approval path first',
  'Use concise language for a service agent',
] as const

export const INSPECTOR = {
  title: 'Request Inspector',
  subtitle: 'This is the exact request this page will send. It updates as you type.',
  tabJson: 'Request JSON',
  tabGuidance: 'Caller guidance',
  tabHttp: 'Raw HTTP',
  jsonCaption: 'Correlation and idempotency travel as headers, not in the body. See Raw HTTP.',
  hashLabel: 'Request hash (client preview)',
  hashCaption:
    "Computed here from the same fields the server hashes. The server's value on the receipt is authoritative.",
  changedChip: 'Request changed',
  editableHeading: 'Caller guidance — editable',
  editablePill: 'Editable',
  guidanceEmpty: 'No additional instructions. The field will be omitted from the request.',
  /**
   * The same constraint sentence the docket field carries, repeated verbatim
   * inside the inspector. Repeated rather than cross-referenced because the
   * inspector is the surface an audience reads, and a constraint that lives
   * only beside the input is a constraint the audience never sees.
   */
  guidanceHelperEcho:
    'Shapes explanation focus or format. It cannot override published policy, retrieval, decision status, or citation requirements.',
  edit: 'Edit',
  serverHeading: 'Server instruction profile — read only',
  serverPill: 'Read only',
  serverDisclosure:
    'The server composes its own system instructions for this decision. They are not exposed here and cannot be sent, replaced, or disabled by a caller. The server enforces policy grounding — which published policies are read, which citations are required, and which decision statuses may carry a verdict — regardless of anything in caller guidance.',
  serverProfileNote:
    'The identifier above names the version of that server-side instruction profile, so a receipt can be traced to the instructions that produced it.',
  precedence:
    'Server instructions and published policy take precedence. Caller guidance is applied only where it does not conflict.',
  profileUnknownBeforeFirst: 'Reported on the receipt after the first decision.',
  profileUnknown: 'Not reported on this receipt.',
  subscriptionKeyCaption:
    'Shown as it will be sent, so you can compare it against a failing call. Copy and Download emit it too — this is a local demonstration, not a pattern for a production browser client.',
  previewUpdated: 'Request preview updated.',
} as const

export const WAIT = {
  line1: 'Searching published policies and evaluating',
  elapsedSuffix: 'elapsed',
  line2:
    "The server narrows this project's published policies to the ones that bear on your scenario, then evaluates only those.",
  long: 'Still working. Long scenarios and large published sets take longer.',
} as const

/**
 * Decision-status copy. The first five are lifted verbatim from the product's
 * `ProjectCaseRunner`; `failed` and `not_evaluated` belong to the receipt layer
 * and are written to the same standard -- each says what did *not* happen.
 */
export const DECISION_STATUS_COPY = {
  answered: {
    label: 'Answered',
    tone: 'allow',
    title: 'The evaluated rules settle this case',
    description: 'The verdict below is the decision returned from the evaluated published policies.',
  },
  missing_required_facts: {
    label: 'Needs facts',
    tone: 'action',
    title: 'The evaluated rules need more facts',
    description: 'The policy can answer this only if the case supplies the missing facts listed below.',
  },
  not_settled_by_rules: {
    label: 'Not settled by rules',
    tone: 'note',
    title: 'The evaluated rules bear on this case but do not settle it',
    description:
      'This is not a verdict. The answer below explains what the evaluated rules say and what they do not decide.',
  },
  no_rule_bears: {
    label: 'No evaluated rule bears',
    tone: 'neutral',
    title: 'No evaluated rule bears on this case',
    description:
      'The policies listed below were read, but none contains a rule that speaks to this scenario.',
  },
  declined: {
    label: 'No answer composed',
    tone: 'action',
    title: 'No decision answer was composed',
    description:
      'The request reached the evaluated rules, but no usable decision answer was returned.',
  },
  failed: {
    label: 'Failed',
    tone: 'deny',
    title: 'The decision failed before an answer was produced.',
    description: 'No verdict was reached and nothing here should be used as evidence.',
  },
  not_evaluated: {
    label: 'Not evaluated',
    tone: 'neutral',
    title: 'Nothing was evaluated for this case.',
    description:
      'The project may have published nothing, the index may be missing, or no published policy may bear on the question. This is not the same as the policies being read and saying nothing.',
  },
} as const

/**
 * Retrieval copy, verbatim from `ProjectCaseRunner`'s `RETRIEVAL_COPY`, so the
 * two surfaces describe one server event with one set of words.
 */
export const RETRIEVAL_COPY: Record<string, { tone: string; message: string; description: string }> = {
  narrowed: {
    tone: 'allow',
    message: 'Search narrowed the published policies before evaluation',
    description:
      'The project was not evaluated as one undifferentiated set. Search kept the highest matching published policies and discarded the rest before the answer was composed.',
  },
  not_narrowed: {
    tone: 'note',
    message: 'All published policies were evaluated',
    description:
      'This project has few enough published policies that search did not need to select between them. Every published policy went to evaluation, and none was discarded.',
  },
  bypassed: {
    tone: 'note',
    message: 'Retrieval was bypassed for the policy you chose',
    description:
      'You selected one published policy, so the case was put to that policy directly instead of searching across the project.',
  },
  no_published_version: {
    tone: 'note',
    message: 'This project has no published policies yet',
    description:
      'There is no published project scope to test. Publish policies first, or choose a project that already has a published version.',
  },
  no_match: {
    tone: 'note',
    message: 'Published policies were searched; none matched this case',
    description:
      'The project has published policies, but retrieval found none that bear on this question. Nothing was evaluated.',
  },
  index_not_built: {
    tone: 'action',
    message: 'The policy search index has not been built for this project',
    description:
      'The app will not fall back to evaluating every published policy. Build or refresh the index, or choose one policy directly.',
  },
  index_stale: {
    tone: 'action',
    message: 'The policy search index is stale for the active published version',
    description:
      'The app will not trust an index for another version. Refresh the index, or choose one policy directly.',
  },
  index_empty: {
    tone: 'action',
    message: 'The published policies are not searchable in the index',
    description:
      'Retrieval cannot be relied on for this project, so the app did not evaluate every policy as a fallback.',
  },
  unavailable: {
    tone: 'action',
    message: 'Policy search is not available on this server',
    description:
      'Project-wide testing depends on search to narrow the scope. Choose one policy directly, or run this where search is configured.',
  },
  failed: {
    tone: 'deny',
    message: 'Policy search failed before evaluation',
    description:
      'The app did not evaluate every published policy after the search failure. Try again, or choose one policy directly.',
  },
  empty: {
    tone: 'note',
    message: 'The active published version has no policy rules to test',
    description: 'A version exists, but it contains no live rules that can answer a case.',
  },
}

/**
 * The heading used whenever narrowing actually discarded something. Kept apart
 * from `RETRIEVAL_COPY.not_narrowed` so the over-claiming sentence can only
 * appear when the predicate permits it.
 */
export const RETRIEVAL_NARROWED_HEADING = 'Policies considered by narrowing'

export const RECEIPT = {
  heading: 'Decision receipt',
  requestAsSent: 'Request as sent',
  scenario: 'Scenario',
  guidance: 'Additional instructions (caller guidance)',
  copyBoth: 'Copy both',
  downloadRequest: 'Download request',
  guidanceAbsent: 'No additional instructions were sent with this request.',
  guidanceEmpty: 'An empty instruction value was recorded.',
  guidanceEmptyChip: 'Empty, not absent',
  guidanceNotEchoed: 'The receipt does not carry the caller guidance that was sent.',
  guidanceNotEchoedBody:
    'The decision is shown as returned. Treat the request record as incomplete and report the decision id.',
  requestHashCaption:
    'Covers the question and the caller guidance. An idempotency key is bound to this value.',
  matchesPreview: 'Matches preview',
  differsFromPreview: 'Differs from preview',
  previewChipCaption:
    "The server's value is authoritative. A difference means the request changed after the preview was taken.",
  profileCaption:
    'The version of the server-side instruction profile that produced this decision.',
  callerCaption:
    'The declared label is supplied by the caller; the principal is what the credential proves.',
  hashCaption: 'Compare this to the stored hash to prove the result was not altered.',
  usedInPaths: 'Use this in API paths',
  traceIdentity: 'Trace identity',
  contractVersion: 'Contract version',
  serverAssigned: 'Server-assigned',
  staleChip: 'Previous decision, not refreshed',
  showRaw: 'Show raw response',
} as const

export const VERIFY = {
  button: 'Verify stored receipt',
  caption:
    'Fetch this decision from the API by id and compare the stored hash to the one you received.',
  verifying: 'Verifying…',
  match: 'Stored receipt matches.',
  mismatch: 'Stored receipt does not match what you received.',
  mismatchBody:
    'Do not treat this decision as evidence. Report the decision id to the platform owner.',
  guidanceMismatch:
    'The stored caller guidance is not the guidance you sent. Do not treat this decision as evidence of what was asked.',
  unavailable: 'The stored receipt could not be read, so this decision is unverified.',
  unavailableBody: 'An unverified decision is not evidence.',
  forbidden:
    'This receipt may be read by the caller who made the decision, or by a policy author or administrator.',
  forbiddenBody:
    'Your credential made the call but may not read the stored receipt, so this decision is unverified.',
  pending: 'The decision is still being written. It cannot be verified yet.',
  pendingRetry: 'Try verifying again',
  failed: 'The stored receipt failed and has no verdict to serve.',
  failedBody: 'A failed receipt is not a decision. Nothing here should be used as evidence.',
  returned: 'Returned',
  stored: 'Stored',
  absent: 'absent',
} as const

export const PERSISTENCE_FAILURE = 'The decision was not stored, so it is not usable. Nothing is shown.'

export const STALE_CAPTION = 'Previous decision, not refreshed'
