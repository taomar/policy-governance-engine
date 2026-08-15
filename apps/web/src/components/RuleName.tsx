import { useEffect, useSyncExternalStore, type JSX } from "react";
import { aiApi, type RuleName as StoredRuleName } from "../api";
import { DirectionalText } from "./DirectionalText";

/**
 * A short generated handle for what one rule is for.
 *
 * WHY IT EXISTS
 *
 * Rules under one heading are decomposed from the same few sentences, so a
 * reviewer scanning a card meets four statements that open with the same six
 * words and an identifier that is a hash. Telling them apart means reading all
 * four in full, every time the card is drawn. This gives each one a handle: a
 * line or two saying what it is *for*, so the eye can land on the right rule
 * and then read it properly. It is a finding aid and never a reading — anyone
 * deciding anything about a rule reads the rule.
 *
 * WHY IT IS NOT PART OF THE RULE
 *
 * A rule's record is evidence about a document. These words are ours. If they
 * were a field of the record they would leave in an export, in a published
 * version, in the JSON a reviewer opens to check what was extracted — and a
 * reader downstream would find text in a policy record that no document ever
 * stated. So the name is fetched separately, keyed by the rule it describes,
 * and it is not reachable from any rule object. The component takes an id and
 * goes and gets it; nothing hands it in.
 *
 * WHY IT FETCHES ITSELF, AND WHY THAT IS NOT ONE REQUEST PER RULE
 *
 * Dropping this in beside a rule should cost the caller nothing and require no
 * plumbing above it, so it sources its own data. Every rule drawn in the same
 * tick is collected into one request by the store below, so a queue of seventy
 * rules asks once, not seventy times. Answers are kept for the life of the
 * page: the same rule scrolled past twice is fetched once.
 *
 * FOUR OUTCOMES, KEPT APART
 *
 * Nobody has generated one; the answer is on its way; there is a name; and the
 * model was asked and produced nothing usable. A fifth, the request itself not
 * completing, is kept apart again — it says nothing about the rule. Only the
 * third renders. The rest render nothing at all, which is the point: a card
 * with no names is exactly the card that existed before this component, and no
 * reviewer is ever shown a hole where a name would have been.
 *
 * HOW IT SAYS IT IS OURS
 *
 * The `✦` and the "by this app" wording, both taken from the generated subject
 * label on the same card, so a reader who has learned what that mark means
 * meets it meaning the same thing here. Nothing about it borrows the quotation
 * styling, which is reserved for the document's own characters.
 */

/** Where one rule's name has got to. Absent, waiting, named and declined are
 *  four different facts about the world and the store keeps them four. */
export type RuleNameState =
  | { status: "absent" }
  | { status: "loading" }
  | { status: "named"; text: string }
  | { status: "declined"; code: string }
  | { status: "unreachable" };

const ABSENT: RuleNameState = { status: "absent" };
const LOADING: RuleNameState = { status: "loading" };
const UNREACHABLE: RuleNameState = { status: "unreachable" };

/**
 * How many ids one request may carry.
 *
 * A page draws far fewer than this. The cap is here so that a caller who maps
 * this over an unbounded list produces several ordinary requests instead of one
 * enormous one, not because any measured page needed it.
 */
const MAX_IDS_PER_REQUEST = 200;

const states = new Map<string, RuleNameState>();
const listeners = new Set<() => void>();
const pending = new Set<string>();
let flushScheduled = false;

function notify(): void {
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function stateOf(candidateId: string): RuleNameState {
  return states.get(candidateId) ?? ABSENT;
}

function asState(record: StoredRuleName | undefined): RuleNameState {
  // No entry: the server holds nothing for this rule. Nobody has run naming
  // over it, which is not the same as having run it and got nothing back.
  if (!record) return ABSENT;
  if (record.text) return { status: "named", text: record.text };
  // Asked, and the outcome was recorded. The code is kept even though nothing
  // renders, so a future surface can say which outcome it was without asking
  // again.
  return { status: "declined", code: record.unavailable_code ?? "unrecorded" };
}

async function flush(): Promise<void> {
  while (pending.size > 0) {
    const batch = [...pending].slice(0, MAX_IDS_PER_REQUEST);
    for (const id of batch) pending.delete(id);
    try {
      const result = await aiApi.ruleNames(batch);
      for (const id of batch) states.set(id, asState(result.names?.[id]));
    } catch {
      // The request did not land. That is a fact about the network and not
      // about these rules, so it is recorded as its own state rather than as
      // "there is no name" — a distinction a retry would need.
      for (const id of batch) states.set(id, UNREACHABLE);
    }
    notify();
  }
}

function scheduleFlush(): void {
  if (flushScheduled) return;
  flushScheduled = true;
  // A microtask, so every rule mounted in one render lands in one request.
  queueMicrotask(() => {
    flushScheduled = false;
    void flush();
  });
}

/** Ask for one rule's name, once. A rule already known — in any of its four
 *  states — is not asked about again for the life of the page. */
function askFor(candidateId: string): void {
  if (!candidateId || states.has(candidateId)) return;
  states.set(candidateId, LOADING);
  pending.add(candidateId);
  scheduleFlush();
}

/**
 * Drop everything this page has learned about rule names.
 *
 * For tests, and for a caller that has just generated names and wants the page
 * to go and look again. It does not delete anything on the server.
 */
export function forgetRuleNames(): void {
  states.clear();
  pending.clear();
  notify();
}

/** One rule's name state, subscribing the caller to changes in it. */
export function useRuleName(candidateId: string): RuleNameState {
  const state = useSyncExternalStore(
    subscribe,
    () => stateOf(candidateId),
    () => ABSENT,
  );
  useEffect(() => {
    askFor(candidateId);
  }, [candidateId]);
  return state;
}

export function RuleName({
  candidateId,
  variant = "inline",
}: {
  /** The rule to name. The name is looked up by this and never passed in, so
   *  that no rule object anywhere can be carrying one. */
  candidateId: string;
  /** `inline` sits on the rule's own line; `block` stands above it. Both say
   *  the same words and both are marked as ours. */
  variant?: "inline" | "block";
}): JSX.Element | null {
  const state = useRuleName(candidateId);
  // Everything that is not a name renders nothing. A consumer can therefore
  // drop this in unconditionally and the surrounding layout never has to know
  // whether naming has been run.
  if (state.status !== "named") return null;
  return (
    <span
      className={`rule-name rule-name--${variant}`}
      data-generated="true"
      data-testid="rule-name"
    >
      <span className="rule-name__mark" aria-hidden>
        ✦
      </span>{" "}
      <span className="rule-name__caption">What this is for, named by this app:</span>{" "}
      <span className="rule-name__text">
        <DirectionalText>{state.text}</DirectionalText>
      </span>
    </span>
  );
}
