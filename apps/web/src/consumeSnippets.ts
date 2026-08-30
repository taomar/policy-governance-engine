/** Worked examples for calling a project's published policies from elsewhere.
 *
 * Pure builders. Nothing here reads the session, the DOM, `sessionStorage`,
 * `localStorage`, or `import.meta.env`; every value a snippet contains is
 * either a literal declared in this file or an argument handed in. That is the
 * point rather than a tidiness preference: these strings are put on a
 * clipboard and pasted into somebody else's service, so the one thing that must
 * be impossible is a signed-in credential travelling with them. A builder that
 * cannot reach a credential cannot leak one, and a unit test can prove it
 * without rendering anything.
 *
 * The credential in every example is the environment variable
 * `POLICY_SUBSCRIPTION_KEY`, sent in `X-Policy-Subscription-Key`. There is no
 * toggle to substitute a real one, and this drawer never displays the key the
 * operator configured — the product has no reason to know it, and a page that
 * showed it would be a page that has to be careful about screenshots.
 *
 * The examples call the external endpoints — `POST /api/policy-decisions/
 * {project_key}/case` and `GET /api/policy-decisions/{decision_id}` — and
 * address the project by its **key**. The project's UUID is trace identity and
 * is never a path segment, so no builder here accepts one.
 */

import {
  EXTERNAL_CORRELATION_ID_HEADER,
  EXTERNAL_IDEMPOTENCY_KEY_HEADER,
  type ExternalCaseDecisionRequest,
} from "./api";

/** The environment variable every example reads its subscription key from.
 *
 * The same name the server setting uses, so there is one word for one thing
 * across the product. Examples never carry a literal credential: a snippet on
 * a clipboard ends up in somebody else''s service, and a value pasted with it
 * is a value they will ship. */
export const POLICY_SUBSCRIPTION_KEY_ENV = "POLICY_SUBSCRIPTION_KEY";

/** The header the key travels in. Not `Authorization`: it is not a token. */
export const SUBSCRIPTION_KEY_HEADER = "X-Policy-Subscription-Key";

/** The envelope every decision made now is answered as.
 *
 *  Named rather than spelled inline so the example, its caption and its guard
 *  cannot drift into disagreeing about which contract is being taught. */
export const RECEIPT_SCHEMA_V2 = "case_decision_v2";

/** The envelope a receipt written before the two-track redesign is replayed as.
 *
 *  Nothing writes it any more. It appears in the worked example only because a
 *  stored decision is served as what it was written as — a receipt whose content
 *  changed after the fact is not evidence of anything — so an integrator holding
 *  keys from then meets it and is owed the branch. */
export const RECEIPT_SCHEMA_V1 = "case_decision_v1";

/** The example request, in one place so all four snippets agree.
 *
 * Typed as the server's request contract, so a field the API does not accept
 * cannot be taught by an example that still renders. */
export const EXAMPLE_CASE_REQUEST: Required<
  Pick<
    ExternalCaseDecisionRequest,
    "scenario" | "reasoning_effort" | "calling_system_identity" | "additional_instructions"
  >
> = {
  scenario: "Describe the situation you want decided.",
  reasoning_effort: "medium",
  calling_system_identity: "my-service",
  additional_instructions: "Explain the approval path first.",
};

/** Fixed ids in the raw-HTTP examples.
 *
 * Literal rather than generated: a raw request is shown byte for byte, and a
 * value that changed on every render would make two readings of the same
 * example disagree. The comment above each says to send your own. */
export const EXAMPLE_CORRELATION_ID = "6f1c9d2e-1b7a-4a55-9a4c-2d3f5b8e1c04";
export const EXAMPLE_IDEMPOTENCY_KEY = "2b90f4c1-77aa-4a1e-9a0f-1c4d8e2b7f30";
export const EXAMPLE_DECISION_ID = "0f1a3c5e-7b9d-4f21-8a63-5c4e2b7d9f08";

/** Where the snippets point and who they ask about. */
export interface ConsumeTarget {
  /** The API base as the reader typed it. Shown as written. */
  apiBase: string;
  /** The project's stable public key. The only project identifier in a path. */
  projectKey: string;
}

/** The base with surrounding whitespace and trailing slashes removed.
 *
 * Only trailing slashes: nothing else is repaired. A base that is not a URL is
 * still rendered exactly as typed, because a reader pasting a placeholder host
 * is telling us what their environment looks like, and withholding the example
 * until they type something parseable would be the drawer refusing to do its
 * one job. */
export function normaliseApiBase(base: string): string {
  return base.trim().replace(/\/+$/, "");
}

/** Whether the base parses as an absolute http(s) URL.
 *
 * Used to caption an unparseable value and to disable links that would
 * otherwise resolve against this app's own origin — a documentation link that
 * silently points at the wrong server is worse than one that says it cannot. */
export function isUsableApiBase(base: string): boolean {
  const normalised = normaliseApiBase(base);
  if (normalised.length === 0) return false;
  try {
    const url = new URL(normalised);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

/** The `Host:` line of the raw HTTP example.
 *
 * Falls back to the base with any scheme and path stripped, so an unparseable
 * value still produces a readable example rather than the word "undefined". */
export function apiBaseHost(base: string): string {
  const normalised = normaliseApiBase(base);
  try {
    return new URL(normalised).host;
  } catch {
    return normalised.replace(/^[a-z][a-z0-9+.-]*:\/\//i, "").split("/")[0];
  }
}

/** The external case endpoint's path for a project, keyed by its stable key. */
export function caseEndpointPath(projectKey: string): string {
  return `/api/policy-decisions/${encodeURIComponent(projectKey)}/case`;
}

/** The same path, absolute against the base being shown. */
export function caseEndpointUrl({ apiBase, projectKey }: ConsumeTarget): string {
  return `${normaliseApiBase(apiBase)}${caseEndpointPath(projectKey)}`;
}

/** The read-back path for one stored decision, by decision id. */
export function receiptEndpointPath(decisionId: string): string {
  return `/api/policy-decisions/${encodeURIComponent(decisionId)}`;
}

/** The example body, serialised the way the raw HTTP example sends it. */
export function exampleCaseBodyJson(): string {
  return JSON.stringify(EXAMPLE_CASE_REQUEST);
}

/** cURL: the shortest thing a reader can paste into a terminal and run. */
export function buildCurlSnippet(target: ConsumeTarget): string {
  const url = caseEndpointUrl(target);
  return [
    `# Put a case to the published policies of project ${target.projectKey}.`,
    "# The subscription key comes from your environment, never from this page:",
    `#   export ${POLICY_SUBSCRIPTION_KEY_ENV}="<the key your operator issued>"`,
    `curl -sS -X POST "${url}" \\`,
    `  -H "${SUBSCRIPTION_KEY_HEADER}: $${POLICY_SUBSCRIPTION_KEY_ENV}" \\`,
    '  -H "Content-Type: application/json" \\',
    `  -H "${EXTERNAL_CORRELATION_ID_HEADER}: $(uuidgen)" \\`,
    `  -H "${EXTERNAL_IDEMPOTENCY_KEY_HEADER}: $(uuidgen)" \\`,
    "  -d '{",
    `    "scenario": "${EXAMPLE_CASE_REQUEST.scenario}",`,
    `    "reasoning_effort": "${EXAMPLE_CASE_REQUEST.reasoning_effort}",`,
    `    "calling_system_identity": "${EXAMPLE_CASE_REQUEST.calling_system_identity}",`,
    `    "additional_instructions": "${EXAMPLE_CASE_REQUEST.additional_instructions}"`,
    "  }'",
    "",
    "# additional_instructions is optional: drop the line, and the comma above it,",
    "# when you have no guidance to give. It shapes how the answer is explained and",
    "# cannot change what the published policies decide.",
  ].join("\n");
}

/** Python: the same call, read the way a receipt must be read.
 *
 * The status branches are not decoration. A case asks for up to two things —
 * what the published policies *state*, and how the case *comes out* — and each
 * requested track is answered on its own. `outcome` carries one status per
 * track and is read first, because both sections are `null` when their track
 * did not run: an example that reached straight into `receipt["verdict"]` would
 * raise a `TypeError` on the very ordinary case of a question that asked only
 * what the policies say. And `verdict["decision"]` is populated only when the
 * verdict was reached, so an example that printed it unconditionally would
 * teach the exact mistake the envelope exists to prevent — a caller reading an
 * empty string as "allowed". Both branches are mandatory here, and unit tests
 * hold them in that order.
 *
 * The `schema_version` branch is there for one honest reason: nothing writes
 * `case_decision_v1` any more, but an `Idempotency-Key` issued before the
 * two-track redesign still replays the receipt it named, in the shape that
 * receipt was written in. A caller starting today only ever meets v2. */
export function buildPythonSnippet(target: ConsumeTarget): string {
  return [
    "import os",
    "import uuid",
    "",
    "import requests",
    "",
    `BASE = "${normaliseApiBase(target.apiBase)}"`,
    `PROJECT_KEY = "${target.projectKey}"`,
    "",
    "body = {",
    `    "scenario": "${EXAMPLE_CASE_REQUEST.scenario}",`,
    `    "reasoning_effort": "${EXAMPLE_CASE_REQUEST.reasoning_effort}",`,
    `    "calling_system_identity": "${EXAMPLE_CASE_REQUEST.calling_system_identity}",`,
    "}",
    "",
    "# Optional. Shapes how the answer is explained; it cannot change which",
    "# policies were read, what your question is read as asking for, or what the",
    "# policies decide. Leave it out entirely when you have no guidance — an",
    "# absent key and an empty string are not the same.",
    `body["additional_instructions"] = "${EXAMPLE_CASE_REQUEST.additional_instructions}"`,
    "",
    "response = requests.post(",
    '    f"{BASE}/api/policy-decisions/{PROJECT_KEY}/case",',
    "    headers={",
    `        "${SUBSCRIPTION_KEY_HEADER}": os.environ["${POLICY_SUBSCRIPTION_KEY_ENV}"],`,
    '        "Content-Type": "application/json",',
    // Correlation and idempotency are headers, not body keys: one names the
    // call, the other names its delivery. Neither is part of the question.
    `        "${EXTERNAL_CORRELATION_ID_HEADER}": str(uuid.uuid4()),`,
    `        "${EXTERNAL_IDEMPOTENCY_KEY_HEADER}": str(uuid.uuid4()),`,
    "    },",
    "    json=body,",
    "    timeout=120,",
    ")",
    "response.raise_for_status()",
    "receipt = response.json()",
    "",
    'print("decision_id:", receipt["decision_id"])',
    "",
    `# Every decision made now is ${RECEIPT_SCHEMA_V2}. A receipt written before the`,
    "# two-track redesign is replayed in the shape it was written in, so branch on",
    "# the version only if you still hold Idempotency-Keys from then.",
    `if receipt["schema_version"] == "${RECEIPT_SCHEMA_V1}":`,
    "    # One status, one verdict, and no separate information track.",
    '    if receipt["decision_status"] == "answered":',
    '        print("verdict:", receipt["decision"]["verdict"])',
    "    else:",
    '        print("no verdict:", receipt["decision_status"])',
    '    print("explanation:", receipt["decision"]["explanation"])',
    "else:",
    "    # Read outcome before either section. Your question is read as asking",
    "    # for what the policies state, for a verdict, or for both, and each",
    "    # requested track is answered on its own — one can answer while the",
    "    # other cannot.",
    '    outcome = receipt["outcome"]',
    '    print("asked for information:", receipt["asked"]["information_requested"])',
    '    print("asked for a verdict:", receipt["asked"]["verdict_requested"])',
    "",
    "    # Both sections are null when their track did not run, so neither is",
    '    # subscripted before its own outcome has been read. "not_requested"',
    '    # means you did not ask; "not_evaluated" means nothing was evaluated',
    "    # at all. Neither is the policies refusing you an answer.",
    '    if outcome["information"] == "answered":',
    '        print("information:", receipt["information"]["answer"])',
    "    else:",
    '        print("no information:", outcome["information"])',
    "",
    '    if outcome["verdict"] == "answered":',
    '        print("verdict:", receipt["verdict"]["decision"])',
    '        print("explanation:", receipt["verdict"]["explanation"])',
    '    elif outcome["verdict"] == "missing_required_facts":',
    "        # The case cannot be decided until these are supplied. This is not",
    "        # a refusal, and it is not a verdict.",
    '        for fact in receipt["verdict"]["missing_information"]:',
    '            print("needs:", fact["label"], "-", fact["why_needed"])',
    "    else:",
    '        print("no verdict:", outcome["verdict"])',
    "",
    "    # One entry per rule, whichever track cited it; a rule both tracks cited",
    '    # appears once and carries both tags in "serves".',
    '    for citation in receipt["citations"]:',
    '        print("citation:", citation["rule_id"], citation["serves"], citation["source"].get("text"))',
    "",
    'print("receipt_url:", receipt["receipt_url"])',
  ].join("\n");
}

/** Raw HTTP: the request on the wire, for a reader working in another language. */
export function buildRawHttpRequestSnippet(target: ConsumeTarget): string {
  return [
    `POST ${caseEndpointPath(target.projectKey)} HTTP/1.1`,
    `Host: ${apiBaseHost(target.apiBase)}`,
    `${SUBSCRIPTION_KEY_HEADER}: $${POLICY_SUBSCRIPTION_KEY_ENV}`,
    "Content-Type: application/json",
    `${EXTERNAL_CORRELATION_ID_HEADER}: ${EXAMPLE_CORRELATION_ID}`,
    `${EXTERNAL_IDEMPOTENCY_KEY_HEADER}: ${EXAMPLE_IDEMPOTENCY_KEY}`,
    "",
    exampleCaseBodyJson(),
  ].join("\n");
}

/** Raw HTTP: reading the stored receipt back by decision id. */
export function buildRawHttpReceiptSnippet(target: ConsumeTarget): string {
  return [
    `GET ${receiptEndpointPath(EXAMPLE_DECISION_ID)} HTTP/1.1`,
    `Host: ${apiBaseHost(target.apiBase)}`,
    `${SUBSCRIPTION_KEY_HEADER}: $${POLICY_SUBSCRIPTION_KEY_ENV}`,
  ].join("\n");
}

/** One row of the API-docs register. */
export interface ApiDocsLink {
  /** Stable id, used for the row's test hook. */
  id: "swagger" | "redoc" | "openapi";
  title: string;
  /** What the link is, in one line. */
  caption: string;
  href: string;
}

/** The three documentation surfaces the API serves about itself.
 *
 * Derived from the base rather than hardcoded, so they always describe the
 * server the snippets above call. Nothing probes them: a HEAD request from a
 * drawer would be a side effect for a documentation link. */
export function buildApiDocsLinks(apiBase: string): ApiDocsLink[] {
  const base = normaliseApiBase(apiBase);
  return [
    {
      id: "swagger",
      title: "Interactive API docs (Swagger UI)",
      caption: "Try the endpoint in the browser against this server.",
      href: `${base}/docs`,
    },
    {
      id: "redoc",
      title: "Reference docs (ReDoc)",
      caption: "The same contract, laid out for reading.",
      href: `${base}/redoc`,
    },
    {
      id: "openapi",
      title: "OpenAPI schema (JSON)",
      caption: "The machine-readable contract, for generating a client.",
      href: `${base}/openapi.json`,
    },
  ];
}
