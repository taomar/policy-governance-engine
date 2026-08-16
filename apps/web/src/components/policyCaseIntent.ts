/**
 * Asking the server what a case put to a policy *is*, before the client decides
 * how to answer it.
 *
 * WHY THIS IS A SEPARATE SEAM
 *
 * A reviewer's question to a policy is either a request for what the policy
 * provides ("how many hours may a part-timer work?") or a description of a
 * situation awaiting a determination ("someone works thirty hours; are they
 * within the cap?"). Those are different questions, and answering the first as
 * the second reports the rule that *states* the answer as unsettled, because as
 * a determination it needs the very quantity being asked about. So the case is
 * classified first — by the model, reading the question alone, never a phrase
 * list, which would classify one language and be blind to the other in a
 * bilingual corpus — and only an informational request is gathered into a single
 * stated answer. A determination is left untouched for the per-rule deciders the
 * client already runs.
 *
 * WHY IT REUSES THE API'S ERROR, NOT ITS CLIENT
 *
 * `api.ts` keeps its `request` helper and base URL private. Rather than widen
 * that module's surface for one caller, this seam repeats the one idiom it needs
 * — turn a `fetch` that never reached a server into the same unreachable error
 * every other call raises — and imports the error type and the unreachable
 * status so a caller cannot tell this request apart from any other by how it
 * fails. When it cannot reach the server, or the server refuses, the caller
 * fails closed to the per-rule determination path: a classification that did not
 * arrive must never masquerade as one that did.
 */
import { API_UNREACHABLE_STATUS, PolicyPlatformApiError, type CanonicalRule } from "../api";

/**
 * Kept in step with `VITE_API_BASE_URL` in `api.ts`. Repeated rather than
 * exported-and-imported because it is a build-time constant, not shared state:
 * two reads of the same env var cannot drift, and nothing here should be able to
 * change where the rest of the app points.
 */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8010";

/** Which of the two kinds a case was read as. */
export type CaseIntent = "informational" | "decision";

/**
 * Where an informational answer stands. Four, and kept apart on purpose: a
 * policy that holds nothing on the subject, a policy that holds something and it
 * was gathered, a model that would not compose an answer, and a request that did
 * not complete are four different replies, and collapsing any pair reports one
 * as another. `failed` is only ever reached when the intent is *known* to be
 * informational and the gather did not complete — a failure before the intent is
 * known cannot arrive here, because it fails the whole request instead.
 */
export type InformationalStatus = "answered" | "no_rule_bears" | "declined" | "failed";

/**
 * One rule the stated answer drew on: the app's finding aid for it (`title`, and
 * a generated name resolved separately by `RuleName`) plus the document's own
 * sentence, `quote`, carried verbatim from the record and never rewritten,
 * translated or trimmed.
 */
export interface InformationalCitation {
  rule_id: string;
  title: string;
  quote: string;
}

/**
 * The gathered answer to an informational request. `answer` is the app's own
 * wording — the caller marks it as the app's — and is empty in every state but
 * `answered`. `citations` name the rules the answer rests on and carry their
 * verbatim source. `note` is an optional caveat from the gather.
 */
export interface InformationalAnswer {
  status: InformationalStatus;
  answer: string;
  citations: InformationalCitation[];
  note: string;
}

/**
 * The server's reply to a case put to a whole policy. `informational` is present
 * only when the intent is informational; for a determination it is `null` and
 * the caller runs the per-rule deciders it already has, unchanged.
 */
export interface PolicyCaseAnswer {
  intent: CaseIntent;
  classification_reasoning: string;
  informational: InformationalAnswer | null;
  reasoning_effort: string;
}

/**
 * Classify a case put to a policy, and gather the answer when it is
 * informational.
 *
 * The rules are sent as the reviewer sees them — the same canonical rules the
 * rest of the surface holds — so the server quotes their stored source, not a
 * shape reassembled here. Throws `PolicyPlatformApiError` when the server refuses
 * or cannot be reached, which the caller treats as a signal to fall back to the
 * per-rule determination path rather than as an answer.
 */
export async function answerPolicyCase(
  rules: readonly CanonicalRule[],
  options: { scenario: string; reasoningEffort: string },
): Promise<PolicyCaseAnswer> {
  const { scenario, reasoningEffort } = options;
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/api/ai/policy-case/answer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rules, scenario, reasoning_effort: reasoningEffort }),
    });
  } catch (cause) {
    // Never reached a server. Raised as the same unreachable error every other
    // call uses, so "we could not ask" is told apart from "the answer was no".
    throw new PolicyPlatformApiError(
      API_UNREACHABLE_STATUS,
      "Cannot reach the policy platform server. It may be restarting, or the connection was interrupted.",
      { cause },
    );
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body);
    } catch {
      // No JSON body; the status text is the most this refusal will say.
    }
    throw new PolicyPlatformApiError(res.status, detail);
  }
  return (await res.json()) as PolicyCaseAnswer;
}
