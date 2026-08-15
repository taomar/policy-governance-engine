/**
 * Asking a question about one rule or one whole policy, in the language the
 * reader chose.
 *
 * WHY THIS IS NOT IN `api.ts`
 *
 * It should be. `aiApi.ask` already posts this endpoint, and this module posts
 * it again with one more field in the body. The duplication is deliberate and
 * temporary: `api.ts` is being edited by someone else as this is written, and
 * threading a parameter through a shared client while another change is in
 * flight is how two correct edits become one broken file. The intended end
 * state is a `answerLanguage` parameter on `aiApi.ask` and this module deleted;
 * the request shape here is exactly that call plus the field, so collapsing it
 * is a move rather than a rewrite.
 *
 * WHAT IT SENDS, AND WHAT IT DOES NOT DO ON THE WAY BACK
 *
 * It sends a BCP-47 tag and asks the model to write its own words in that
 * language. It does not translate anything. Nothing in this file inspects,
 * rewrites or re-orders a single character of the response — the answer is
 * handed to the caller exactly as the server sent it, because the response
 * carries quoted source material and a translated quotation is a false
 * quotation.
 */
import { API_UNREACHABLE_STATUS, PolicyPlatformApiError, type AskResponse, type ChatTurn } from "./api";

/**
 * Same expression as `api.ts`'s own, and it has to be: this module talks to the
 * same server. It is duplicated rather than imported because `api.ts` keeps the
 * constant private, and exporting it would be an edit to a file another change
 * is sitting in. It disappears with this module.
 */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8010";

export interface AskInLanguageRequest {
  question: string;
  policySetId?: string;
  history?: ChatTurn[];
  focusCandidateRuleId?: string;
  /** The rules to ground on, by their own `AI-…` ids, in document order.
   *  Used when the question is about a whole policy rather than one rule. */
  focusRuleIds?: readonly string[];
  /** IETF BCP-47 tag for the language this app's own words should come back in. */
  answerLanguage: string;
}

/**
 * How much of the asked-about set the answer actually rests on.
 *
 * Reported rather than inferred. A policy can hold more rules than one request
 * can carry, and the difference between "grounded in all of it" and "grounded
 * in the first part of it" is the difference between an answer a reviewer can
 * rely on and one they cannot. Silently sending a subset would make those two
 * look identical on screen.
 */
export interface AskGrounding {
  /** How many rules the subject holds. */
  rule_count: number;
  /** How many of them the model was shown. */
  covered_rule_count: number;
  /** Whether those two are the same number. */
  covers_every_rule: boolean;
}

/** An answer, plus how much of the subject it was grounded in.
 *
 *  Declared here rather than in `api.ts` for the reason in this file's header:
 *  that file is in someone else's hands today. It extends the shared shape so
 *  the extension is additive and collapses cleanly when this module is folded
 *  back in. */
export interface AskInLanguageResponse extends AskResponse {
  grounding?: AskGrounding | null;
}

/** Asks about one rule. */
export async function askAboutRuleInLanguage(
  request: AskInLanguageRequest,
): Promise<AskInLanguageResponse> {
  return postAsk(request);
}

/** Asks about a whole policy, grounding on the rules it names.
 *
 *  Separate from the rule call so each surface reads as what it is, though both
 *  reach the same endpoint — there is one ask path, and a second one would be a
 *  second place for the no-translation rule to be forgotten. */
export async function askAboutPolicyInLanguage(
  request: AskInLanguageRequest,
): Promise<AskInLanguageResponse> {
  return postAsk(request);
}

async function postAsk({
  question,
  policySetId,
  history = [],
  focusCandidateRuleId,
  focusRuleIds,
  answerLanguage,
}: AskInLanguageRequest): Promise<AskInLanguageResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/ai/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        policy_set_key: policySetId ?? null,
        history,
        focus_candidate_rule_id: focusCandidateRuleId ?? null,
        focus_rule_ids: focusRuleIds ? [...focusRuleIds] : null,
        answer_language: answerLanguage,
      }),
    });
  } catch (cause) {
    // The request never reached a server. Distinct from a server refusing it,
    // and the two lead to different sentences on screen.
    throw new PolicyPlatformApiError(
      API_UNREACHABLE_STATUS,
      "Cannot reach the policy platform server. It may be restarting, or the connection was interrupted.",
      { cause },
    );
  }

  if (!response.ok) {
    throw new PolicyPlatformApiError(response.status, await failureDetail(response));
  }
  return (await response.json()) as AskInLanguageResponse;
}

/** The server's own words for a refusal, when it sent any. */
async function failureDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string" && body.detail.trim()) return body.detail;
  } catch {
    // A refusal with no JSON body is still a refusal; fall through to the
    // status, which is the only thing that was actually said.
  }
  return `The server refused the request (${response.status}).`;
}
