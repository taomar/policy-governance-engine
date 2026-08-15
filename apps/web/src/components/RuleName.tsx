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

/**
 * Which rule a handle is being asked about.
 *
 * Two ways of saying it, because two surfaces hold different records of the
 * same rule. The review queue holds the draft row naming ran over and asks by
 * its id. A published version holds no draft row — there, the rule *is* the
 * record — so it asks by the rule's own identifier, within the set that gives
 * that identifier its meaning. Neither is the primary; they are two doors to
 * one stored handle.
 */
export type RuleNameSubject =
  | { candidateId: string; policySetKey?: undefined; ruleId?: undefined }
  | { candidateId?: undefined; policySetKey: string; ruleId: string };

/**
 * The key this page files a handle under.
 *
 * Namespaced so the two doors can never collide in the store: a draft row id
 * and a canonical rule id are both strings, and a shared map keyed on the bare
 * value would let one answer the other's question. The set is part of the key
 * for the same reason it is part of the query — the same canonical id in two
 * documents is two different rules.
 */
function subjectKey(subject: RuleNameSubject): string {
  if (subject.candidateId) return `candidate:${subject.candidateId}`;
  if (!subject.policySetKey || !subject.ruleId) return "";
  return `rule:${subject.policySetKey}\u0000${subject.ruleId}`;
}

/** The reply is keyed by whichever identifier was asked with, so the answer is
 *  filed back under the key that asked for it. */
function replyKey(subject: RuleNameSubject): string {
  return subject.candidateId ?? subject.ruleId ?? "";
}

const states = new Map<string, RuleNameState>();
const listeners = new Set<() => void>();
const pending = new Map<string, RuleNameSubject>();
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

function stateOf(key: string): RuleNameState {
  return states.get(key) ?? ABSENT;
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

/**
 * Ask for every rule now waiting, in as few requests as the doors allow.
 *
 * One request per door, and one per set within the identifier door, because a
 * canonical identifier means nothing without a set. Each reply is applied only
 * to the rules that request asked about — never merged into one map first. Two
 * sets can state the same identifier about unrelated rules, so a merged map
 * would hand one set's handle to the other's rule, and it would look entirely
 * ordinary on screen.
 */
async function flush(): Promise<void> {
  while (pending.size > 0) {
    const batch = [...pending.entries()].slice(0, MAX_IDS_PER_REQUEST);
    for (const [key] of batch) pending.delete(key);

    type Ask = {
      /** The waiting rules this request is for, and nobody else's. */
      members: [string, RuleNameSubject][];
      reply: Promise<Record<string, StoredRuleName | undefined>>;
    };

    const byDraftRow: [string, RuleNameSubject][] = [];
    const bySet = new Map<string, [string, RuleNameSubject][]>();
    for (const entry of batch) {
      const subject = entry[1];
      if (subject.candidateId) {
        byDraftRow.push(entry);
      } else if (subject.policySetKey && subject.ruleId) {
        const held = bySet.get(subject.policySetKey);
        if (held) held.push(entry);
        else bySet.set(subject.policySetKey, [entry]);
      }
    }

    const asks: Ask[] = [];
    if (byDraftRow.length > 0) {
      asks.push({
        members: byDraftRow,
        reply: aiApi
          .ruleNames(byDraftRow.map(([, subject]) => subject.candidateId as string))
          .then((result) => result.names ?? {}),
      });
    }
    // A list of requests rather than a pair, so a page drawing three sets asks
    // three times rather than silently answering two of them from the third.
    for (const [policySetKey, members] of bySet) {
      asks.push({
        members,
        reply: aiApi
          .ruleNames([], {
            policySetKey,
            ruleIds: members.map(([, subject]) => subject.ruleId as string),
          })
          .then((result) => result.names_by_rule_id ?? {}),
      });
    }

    try {
      const replies = await Promise.all(asks.map((ask) => ask.reply));
      replies.forEach((reply, index) => {
        for (const [key, subject] of asks[index].members) {
          states.set(key, asState(reply[replyKey(subject)]));
        }
      });
    } catch {
      // The request did not land. That is a fact about the network and not
      // about these rules, so it is recorded as its own state rather than as
      // "there is no name" — a distinction a retry would need.
      for (const [key] of batch) states.set(key, UNREACHABLE);
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

/** Ask about one rule, once. A rule already known — in any of its four states
 *  — is not asked about again for the life of the page. */
function askFor(subject: RuleNameSubject): void {
  const key = subjectKey(subject);
  if (!key || states.has(key)) return;
  states.set(key, LOADING);
  pending.set(key, subject);
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
export function useRuleName(subject: RuleNameSubject): RuleNameState {
  const key = subjectKey(subject);
  const state = useSyncExternalStore(
    subscribe,
    () => stateOf(key),
    () => ABSENT,
  );
  const { candidateId, policySetKey, ruleId } = subject;
  useEffect(() => {
    // Rebuilt from the three primitives rather than closing over `subject`, so
    // a caller passing a fresh object literal every render does not re-ask.
    askFor(
      candidateId
        ? { candidateId }
        : policySetKey && ruleId
          ? { policySetKey, ruleId }
          : { candidateId: "" },
    );
  }, [candidateId, policySetKey, ruleId]);
  return state;
}

export function RuleName({
  candidateId,
  policySetKey,
  ruleId,
  variant = "inline",
}: RuleNameSubject & {
  /** `inline` sits on the rule's own line; `block` stands above it. Both say
   *  the same words and both are marked as ours. */
  variant?: "inline" | "block";
}): JSX.Element | null {
  const state = useRuleName(
    (candidateId ? { candidateId } : { policySetKey, ruleId }) as RuleNameSubject,
  );
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
