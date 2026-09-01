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
  revealKey: 'Reveal',
  hideKey: 'Hide',
  subscriptionKeyCaption:
    'Sent as X-Policy-Subscription-Key. Held in memory only: never written to storage, the URL, or a log.',
  subscriptionKeyLocalWarning:
    'Local demonstration only. Use a key your operator generated for local use: the Raw HTTP tab masks it, but this field itself is in clear so you can check it. A production browser client must never hold a shared subscription key: anything prefixed VITE_ is compiled into the bundle and served to every visitor.',
  subscriptionKeyPrefilled:
    'Prefilled from VITE_POLICY_SUBSCRIPTION_KEY in this machine’s local .env.local. That file is git-ignored and is a local-demonstration convenience only.',
  resolvedFrom: 'Resolved from the API',
  resolving: 'Resolving project identity…',
  scenarioLabel: 'Scenario',
  scenarioPlaceholder:
    'e.g. A supplier in a sanctioned jurisdiction asks whether we may proceed with a 90-day payment term.',
  responseModeLabel: 'Choose the API response',
  decisionModeLabel: 'Decision JSON',
  decisionModeDescription:
    'Runs retrieval and the current reasoning path, then returns the verdict, explanation, evidence, and stored receipt.',
  decisionLightModeLabel: 'Decision Light',
  decisionLightModeDescription:
    'Runs and stores the same decision, then returns only essential structured outcomes, ids, policies, and citations.',
  policiesModeLabel: 'Policy JSON',
  policiesModeDescription:
    'Uses semantic precision ranking and returns only the selected published policy records.',
  policiesModeNote: 'No reasoning effort is needed: this mode stops before the reasoning path.',
  policiesMetadataNote:
    'Only the scenario and correlation ID are sent. There is no caller guidance, idempotency key, verdict, or stored receipt.',
  reasoningLabel: 'Reasoning effort',
  callingSystemLabel: 'Calling system',
  callingSystemDefault: 'playground-demo',
  callingSystemCaption: 'Recorded on the decision so the receipt shows who called.',
  idempotencyLabel: 'One-call idempotency key (optional)',
  idempotencyCaption:
    'Used for this request and rotated after success. After a failure it stays in place so retrying is safe.',
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
  submitLight: 'Run Decision Light',
  submitPolicies: 'Retrieve filtered policy JSON',
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
  policiesSubtitle:
    'This request stops after filtering. The response contains selected policy records, not a decision receipt.',
  lightSubtitle:
    'This runs and stores the same governed decision, then returns its compact fixed-schema projection.',
  tabJson: 'Request JSON',
  tabResponse: 'Response JSON',
  tabGuidance: 'Caller guidance',
  tabHttp: 'Raw HTTP',
  responseEmpty: 'No response yet. Send the request to inspect the full decision envelope here.',
  policiesResponseEmpty: 'No response yet. Retrieve policies to inspect the filtered JSON here.',
  jsonCaption: 'Correlation and idempotency travel as headers, not in the body. See Raw HTTP.',
  policiesJsonCaption:
    'Correlation travels as a header. Policy JSON mode has no idempotency key because it stores no receipt.',
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
    'Masked by default. Reveal it to check it against a failing call — most first-integration 401s are a typo here. Copy and Download always emit $POLICY_SUBSCRIPTION_KEY instead of the value, whatever the reveal is set to.',
  revealKey: 'Reveal key',
  hideKey: 'Hide key',
  keyRevealed: 'Subscription key revealed.',
  keyHidden: 'Subscription key hidden.',
  previewUpdated: 'Request preview updated.',
} as const

export const INTEGRATION = {
  button: 'Integration guide',
  title: 'Use the Policy API in another system',
  intro:
    'Choose whether your system needs a governed decision receipt or the filtered policy JSON for its own agent to reason over.',
  decisionHeading: 'Decision JSON',
  decisionBody:
    'Use the case endpoint when the platform should retrieve, reason, explain, cite, and persist an auditable receipt.',
  decisionLightHeading: 'Decision Light',
  decisionLightBody:
    'Use the light case endpoint for the same stored decision with a compact fixed schema containing essential outcomes, ids, policies, and citations.',
  policiesHeading: 'Policy JSON',
  policiesBody:
    'Use the policies endpoint when your agent should receive a small precision-ranked set of approved policy records. No verdict or receipt is produced.',
  agentHeading: 'Agentic systems and Copilot',
  agentBody:
    'Register each POST operation as a separate tool from the OpenAPI schema. Describe the decision tool as authoritative for verdicts and the policy tool as retrieval-only. Keep the subscription key in the server-side tool connection, never in a browser prompt.',
  close: 'Close integration guide',
} as const

export const WAIT = {
  line1: 'Searching published policies and evaluating',
  policiesLine1: 'Filtering published policies',
  elapsedSuffix: 'elapsed',
  line2:
    "The server narrows this project's published policies to the ones that bear on your scenario, then evaluates only those.",
  policiesLine2:
    'The server precision-ranks policy records, slices selected large policies by rule, and returns them without running a verdict.',
  long: 'Still working. Long scenarios and large published sets take longer.',
} as const

export const RUN_METER = {
  label: 'API execution metrics',
  eyebrow: 'Last API execution',
  ready: 'Ready',
  running: 'Running',
  complete: 'Complete',
  failed: 'Failed',
  time: 'Time taken',
  tokens: 'Model tokens',
  pending: 'Pending',
  notReported: 'Not reported',
  noCall: 'No call completed',
  tokenCaption: 'Service-reported after a completed call',
  modes: {
    decision: 'Decision JSON',
    'decision-light': 'Decision Light',
    policies: 'Policy JSON',
  },
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
 * Per-track outcome copy for `case_decision_v2`.
 *
 * v1 had one status; v2 has two outcomes, and the vocabulary they share is not
 * the same claim on each track. `no_rule_bears` on the information track means
 * "no retained rule states anything on this subject"; on the verdict track it
 * means "no retained rule decides this case". Written apart so neither has to
 * be phrased vaguely enough to cover both.
 *
 * Every entry names what did *not* happen as plainly as what did. A caller who
 * cannot tell "the policies say no" from "no policy speaks to this" has been
 * given a worse answer than none.
 */
export const INFORMATION_OUTCOME_COPY = {
  answered: {
    label: 'Answered',
    tone: 'allow',
    title: 'The retained policies state something on this subject',
    description: 'What they state is below, with the rules it rests on.',
  },
  no_rule_bears: {
    label: 'No rule bears',
    tone: 'neutral',
    title: 'No retained rule states anything on this subject',
    description:
      'The policies below were read and none of them speaks to what was asked. This is a real answer, and it is not the same as nothing having been read.',
  },
  declined: {
    label: 'No answer composed',
    tone: 'action',
    title: 'No informational answer was composed',
    description:
      'The retained policies were reached, but no usable statement of what they say was returned.',
  },
  failed: {
    label: 'Failed',
    tone: 'deny',
    title: 'The information track failed before an answer was produced',
    description: 'Nothing here should be used as evidence of what the policies state.',
  },
  not_requested: {
    label: 'Not asked for',
    tone: 'neutral',
    title: 'This question did not ask what the policies state',
    description:
      'The classifier read the question as asking for a determination only, so the information track was never run. Nothing was suppressed.',
  },
  not_evaluated: {
    label: 'Not evaluated',
    tone: 'neutral',
    title: 'Nothing was evaluated, so nothing was stated',
    description:
      'Retrieval produced no record to answer from. The project may have published nothing, the index may be missing, or no published policy may bear on the question.',
  },
} as const

export const VERDICT_OUTCOME_COPY = {
  answered: {
    label: 'Verdict reached',
    tone: 'allow',
    title: 'The evaluated rules settle this case',
    description: 'The determination below is what the evaluated published policies returned.',
  },
  missing_required_facts: {
    label: 'Needs facts',
    tone: 'action',
    title: 'The evaluated rules need facts this case did not supply',
    description:
      'An empty verdict here is not a refusal — the case was never decided. Supply the facts below and send it again.',
  },
  not_settled_by_rules: {
    label: 'Not settled by rules',
    tone: 'note',
    title: 'The evaluated rules bear on this case but do not settle it',
    description:
      'This is not a verdict. The explanation below says what the rules cover and what they leave open.',
  },
  no_rule_bears: {
    label: 'No rule bears',
    tone: 'neutral',
    title: 'No evaluated rule decides this case',
    description:
      'The policies below were read, and none contains a rule that determines this scenario.',
  },
  declined: {
    label: 'No verdict composed',
    tone: 'action',
    title: 'No verdict was composed',
    description: 'The evaluated rules were reached, but no usable determination was returned.',
  },
  failed: {
    label: 'Failed',
    tone: 'deny',
    title: 'The verdict track failed before a determination was produced',
    description: 'No verdict was reached and nothing here should be used as evidence.',
  },
  not_requested: {
    label: 'Not asked for',
    tone: 'neutral',
    title: 'This question did not ask for a determination',
    description:
      'The classifier read the question as asking what the policies state, not whether a case complies. No verdict was withheld, because none was sought.',
  },
  not_evaluated: {
    label: 'Not evaluated',
    tone: 'neutral',
    title: 'Nothing was evaluated, so nothing was decided',
    description:
      'Retrieval produced no record to decide from. This is not the same as the policies being read and settling nothing.',
  },
} as const

/** The language boundary, and what it did and did not touch. */
export const LANGUAGE = {
  heading: 'Language',
  absent: 'This receipt predates the language boundary, so it records no language information.',
  absentCaption:
    'That is not the same as a boundary that ran and reported nothing. Nothing here should be read as a claim about which language the decision was made in.',

  adjudicatedIn: 'Adjudicated in',
  askedIn: 'Question observed as',
  answeredIn: 'This receipt is written in',
  undTag: 'not well-formed',
  undCaption:
    'The tag the rendering observed was not well-formed. The decision is unaffected: every stage reasons in the processing language whatever the question was written in.',

  boundaryLabel: 'Question boundary',
  boundaryRendered: 'The question was carried into the processing language before anything read it.',
  boundaryIdentity: 'The rendering call reported the question was already in the processing language.',

  outputLabel: 'Answer rendering',
  outputRendered: 'The prose in this receipt was carried back into the language the question was asked in.',
  outputTargetUnknown:
    'No usable target tag was observed, so the prose is returned exactly as it was reasoned, in the processing language.',
  outputNotRequired:
    'No rendering was made because none was needed — either the answer was owed in the processing language, or the evaluation composed no prose at all.',

  guidanceLabel: 'Caller guidance',
  guidanceRendered: 'Your guidance was carried into the processing language and applied.',
  guidanceNotRequired: 'No rendering of your guidance was needed.',
  guidanceDropped:
    'Your guidance could not be carried into the processing language, so it was dropped rather than applied un-rendered. The decision itself is unaffected.',

  processingHeading: 'The question as it was read',
  processingSame: 'Identical to the question you sent.',
  processingDiffers:
    'This is the text retrieval, classification and both gathers actually ran against. It is not what you sent, and comparing the two is the only way to catch a rendering that changed the question.',
  processingHashLabel: 'Processing scenario hash',
  processingHashCaption:
    'Sealed by the decision hash, so the text that was actually adjudicated cannot be altered on a stored receipt without breaking it.',
  yourBytesUnchanged:
    'Your own bytes are untouched beside it: the scenario, its hash and the idempotency binding are all still over exactly what you sent.',

  /**
   * The claim this page must make loudly, because it is the one a reader is most
   * likely to assume the other way round after seeing a rendered answer.
   */
  citationsUntranslated: 'Cited source text is never translated.',
  citationsUntranslatedBody:
    'Every quotation under Rule evidence is the published document’s own words, in the language it was published in. A rendering is applied to the prose this service composes, never to the authority it rests on — a translated quotation would be a paraphrase wearing quotation marks.',

  profilesLabel: 'Translation profiles',
  profilesCaption:
    'Versioned contracts. Two contracts can reduce one question to two different texts, so the one used is named and the inbound profile is sealed.',
  projectionLabel: 'Corpus projection',
  projectionCaption:
    'The projection the retrieval index was built under. A query and the text it is scored against must be in one language, and this is what says whether they were.',
  projectionAbsent: 'The index carries no projection identifier yet.',
} as const

/** Rule-level retrieval, M2. */
export const RULE_INDEX = {
  stateLabel: 'Rule index',
  matched: 'Queried, and its ranking was fused with the others.',
  degraded:
    'Rule documents exist under the expected projection and the query against them failed recoverably. The selection ran without that ranking, so rules reachable only through the rule index may not have been placed.',
  unavailable: 'Not consulted for this question.',
  hitsZeroMatched:
    'The rule index was asked and placed none of this policy’s rules. That is an answer, not an outage.',
  elevated: (n: number) =>
    n === 1
      ? '1 policy was ranked higher because one of its own rules surfaced'
      : `${n} policies were ranked higher because one of their own rules surfaced`,
  elevatedCaption:
    'Including policies the policy-level search did not return at all. A rule beyond what its policy’s own document could carry is reachable only this way.',
  elevatedNone:
    'No policy’s ranking was changed by a rule surfacing, so rule-level retrieval altered nothing on this question.',

  candidatesLabel: 'Candidate pool',
  quantityCaption:
    'A quantity rank places rules whose stated quantity admits one the question states. It decides whether a rule is worth reading, never what the rule decides.',
  diversityQuota: (n: number) =>
    `${n} of the budget’s slots were reserved so distinct source passages are covered before a passage’s second rule competes.`,
  withoutProjection: (n: number) =>
    n === 1
      ? '1 rule could not be scored by relevance: the index returned no English projection for it.'
      : `${n} rules could not be scored by relevance: the index returned no English projection for them.`,
  withoutProjectionCaption:
    'They score zero rather than being scored against the document’s own language — one language on both sides of a match, always — and can still be placed by the rule index or the quantity rank.',

  projectionReady: 'The index reported a complete corpus projection under the expected contract.',
  projectionNotReady:
    'The index did not report a complete projection under the expected contract. Treat every ranking below as made over a corpus that may not be comparable to the question.',
} as const

/** The two-track result surface. */
export const V2 = {
  askedHeading: 'What this question asked for',
  askedBoth: 'Information and a verdict',
  askedInformation: 'Information only',
  askedVerdict: 'A verdict only',
  askedNeither: 'Nothing was classified',
  askedNeitherCaption:
    'Retrieval produced no record to evaluate, so the classifier never ran. Both tracks report not evaluated.',
  askedCaption:
    'Read by the classifier from the question itself. There is no request field that sets it: a caller who could declare the shape of their own answer could choose it.',
  informationTrack: 'Information',
  verdictTrack: 'Verdict',
  classifierReasoning: 'Why the question was read that way',
  classifierReasoningCaption:
    'Prose from the classifier explaining the routing. Deliberately outside the decision hash: it explains how the question was routed, not what was decided.',

  splitHeading: 'The two halves of this answer came out differently',
  splitAnsweredBlocked:
    'The policies were able to state what they say. They were not able to decide the case, because facts it needs were not supplied. Neither result qualifies the other: what the policies state is settled, and the determination is still open.',
  splitBlockedCaption: 'The empty verdict below is not a refusal.',

  informationHeading: 'What the policies state',
  verdictHeading: 'Verdict',
  explanationLabel: 'Explanation',
  noteLabel: 'Caveat from the answer',
  missingHeading: 'Facts this case must supply',
  missingLead:
    'No verdict can be reached until these are in the scenario. Each one names the rules waiting on it.',
  missingWhyNeeded: 'Why it is needed',
  missingRequiredBy: 'Required by',
  missingNoReason:
    'No reason was composed for this fact. It is listed as the policy record names it, and nothing has been invented here.',
  missingCopy: 'Copy the checklist',
  missingAction: 'Add these to the scenario above and send the case again.',
  verificationHeading: 'Checks before acting',
  verificationLead:
    'The verdict above stands on the rules as read. These conditions were not decided by it and must be confirmed against your own records before the verdict is acted on.',
  verificationWhyNeeded: 'What to confirm',
  verificationRequiredBy: 'Imposed by',
  verificationNoReason:
    'No explanation was composed for this check. It is listed as the policy record names it, and nothing has been invented here.',
  verificationCopy: 'Copy the checks',
  verificationAction: 'These qualify the verdict. They do not withdraw it.',
  verdictNotReached: 'No verdict was reached.',
  informationNotAnswered: 'No statement of what the policies say was composed.',
  unrecognisedHeading: 'This receipt is in an envelope this page does not recognise',
  unrecognisedBody:
    'It is shown below exactly as it was returned, and nothing has been interpreted. Read the raw response, and treat no part of it as a verdict.',
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

/**
 * The heading for the case `RETRIEVAL_COPY` has no entry for: search kept every
 * published policy, and one of them was still read as a slice of its rules.
 *
 * `retrieval.status` is `not_narrowed` there, and taking the status entry at
 * face value would print "All published policies were evaluated" over a receipt
 * where sixty-six of a policy's seventy-four rules were never read. The status
 * is not wrong — search narrowed nothing — it simply does not describe the
 * second narrowing, so this sentence does.
 */
export const RETRIEVAL_SLICED_HEADING =
  'Every published policy was searched; at least one was read as a slice of its rules'

export const RETRIEVAL_SLICED_DESCRIPTION =
  'Search did not need to select between the published policies. A policy holding more rules than one case can read was still narrowed to the rules that bear on the question, so a retained policy here is not necessarily a policy read whole.'

/**
 * Two things that look alike in a count and are not the same claim.
 *
 * A **collapsed duplicate** is proven identical: same condition, effect, type,
 * mode, required facts, authority, scope, effective window, carve-outs and
 * relationship targets. Its record was not read and its terms were — in the
 * policy it names. It is the only discard whose content still reached the
 * gather, and reporting it as an ordinary discard would tell a reader that
 * terms went unweighed when they did not.
 *
 * A **diversity-deferred** policy is not proven identical to anything. It
 * ranked inside the budget and was offered after it because a policy requiring
 * the same thing was offered first. Calling it a duplicate would assert an
 * equivalence the system never established, so the word never appears here.
 *
 * The same care applies one level down, to rules. `represented_rule_ids` names
 * rules that were *not read* — their content was covered by an identical rule
 * that was. The copy must not let "represented" be read as "also read".
 */
export const DUPLICATES = {
  collapsedHeading: 'Collapsed as exact duplicates',
  collapsedLead:
    'These policies govern identically to one that was retrieved, so only one copy took a slot. Their records were not read; their terms were, in the policy each names below.',
  collapsedInto: 'Terms read in',
  collapsedChip: 'Exact duplicate',
  collapsedCount: (n: number) =>
    n === 1
      ? '1 policy was collapsed into an identical one'
      : `${n} policies were collapsed into identical ones`,

  deferredHeading: 'Deferred for coverage, not as duplicates',
  deferredBody:
    'These ranked inside the retention budget and were offered after it because a policy requiring the same thing was offered first. They are not proven identical to anything and are not duplicates: each keeps its own rank and score, and each was discarded for being outside the budget.',
  deferredCount: (n: number) =>
    n === 1
      ? '1 policy was deferred so a differently-governing policy could be offered first'
      : `${n} policies were deferred so differently-governing policies could be offered first`,

  selectionOrderLabel: 'Selection order',
  selectionOrderCaption:
    'Relevance first, then normative-content diversity: among candidates requiring the same thing, the highest-ranked is offered before any second member of that group. This is what puts a highly-ranked policy outside the budget.',

  ruleCollapsedCount: (n: number) =>
    n === 1
      ? '1 further rule was not a candidate: an earlier rule of this policy governs identically.'
      : `${n} further rules were not candidates: an earlier rule of this policy governs identically.`,
  representedHeading: 'Exact copies of rules that were read',
  representedCaption:
    'None of these was put in front of the model. Each is an exact copy of a rule that was read, so its content was covered — but the rule itself was not read, and this is not a second reading of it.',
} as const

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
