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
import { API_UNREACHABLE_STATUS, PolicyPlatformApiError } from "../api";

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
 * Which state a citation's source sentence is in. Four, kept apart for the same
 * reason the answer's statuses are: an empty quote must never stand in for the
 * document's words, and the reader is told which case it is (constraint 5).
 *
 *   - `quoted`      — the rule's verbatim sentence was resolved and is carried.
 *   - `no_citation` — the rule points at no clause at all.
 *   - `unresolved`  — it points at a clause, but no span carried the sentence.
 *   - `not_stored`  — a span is present but its text was never stored (empty),
 *     the app's "source text was not stored with its rules" case.
 */
export type InformationalCitationSourceState =
  | "quoted"
  | "no_citation"
  | "unresolved"
  | "not_stored";

/**
 * The document's own words a citation rests on, resolved by the server.
 *
 * The verbatim sentence is followed from the rule's `evidence_refs` into the
 * payload's `spans` on the server — over the closed payload it was grounded on —
 * rather than re-joined in the browser (§4.2). `text` is present only in the
 * `quoted` state and is the document's sentence exactly: uncut, untranslated,
 * unwrapped (constraint 4). `page` and `section` ride along when the span
 * recorded them, so a reader can find the sentence in the document. No generated
 * name is ever carried here; the display name is still the client's to resolve
 * from the id (constraint 8).
 */
export interface InformationalCitationSource {
  state: InformationalCitationSourceState;
  text?: string;
  page?: number;
  section?: string;
}

/**
 * One rule the stated answer drew on, named by its id, with the document's own
 * verbatim source sentence resolved onto it by the server.
 *
 * The id is the checkable part: it is the identity the server validated against
 * the closed set of rules it was shown — a citation naming an id not in that set
 * is a fabrication the server refuses — so the id is the one token that carries a
 * checkable claim. `source` carries the document's own words the rule rests on,
 * resolved server-side by following `evidence_refs` into `spans`, so the browser
 * no longer re-implements that join (§4.2); it is optional only so a reply from
 * an older server still types. The rule's generated *name* is the app's, not the
 * document's, and still must never cross the wire (constraint 8); the client
 * resolves it from the id at render time.
 */
export interface InformationalCitation {
  rule_id: string;
  source?: InformationalCitationSource;
}

/**
 * What the gather grounded on, reported rather than merely performed. The rules
 * shown to the model are the closed set an answer may draw on; this records how
 * large that set was, how many citations the model asked for, how many named a
 * rule actually in it, and — the check with teeth — which named none and were
 * refused as fabrications. `oversize` is true when the policy's records were too
 * large to read in one pass and no answer was composed.
 *
 * It is surfaced to the reader, not kept in code, so a refused citation is
 * something a reviewer can see the check reject rather than a claim it never had
 * to make good on.
 */
export interface InformationalGrounding {
  prompt_version: string;
  rules_available: number;
  citations_requested: number;
  rules_cited: number;
  fabricated_citations: string[];
  oversize: boolean;
}

/**
 * The gathered answer to an informational request. `answer` is the app's own
 * wording — the caller marks it as the app's — and is empty in every state but
 * `answered`. `citations` name the rules the answer rests on and carry their
 * verbatim source. `note` is an optional caveat from the gather. `grounding`
 * reports the closed set the answer was drawn from and any citation refused as a
 * fabrication; it is optional only so a reply from an older server still types.
 */
export interface InformationalAnswer {
  status: InformationalStatus;
  answer: string;
  citations: InformationalCitation[];
  note: string;
  grounding?: InformationalGrounding;
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
 * The policy is named by its provision id, not sent as rules from here. The
 * server builds the lean record it grounds on from that id — the one canonical
 * projection, never a shape reassembled by a caller — so the closed set the
 * answer may draw on is the server's to define and to validate citations
 * against. Throws `PolicyPlatformApiError` when the server refuses or cannot be
 * reached, which the caller treats as a signal to fall back to the per-rule
 * determination path rather than as an answer.
 */
export async function answerPolicyCase(
  provisionId: string,
  options: { scenario: string; reasoningEffort: string },
): Promise<PolicyCaseAnswer> {
  const { scenario, reasoningEffort } = options;
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/api/ai/policy-case/answer`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provision_id: provisionId, scenario, reasoning_effort: reasoningEffort }),
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
