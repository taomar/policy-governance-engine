import { useId } from "react";

import type { RecordStance, StanceFocus } from "../recordStance";
import { stanceTallyPhrase } from "../recordStance";

/**
 * Chips that narrow which of one policy's rules are on screen.
 *
 * ## Why this is not the filter that was just deleted
 *
 * A filter across the queue made a card a fragment: it showed three of a
 * policy's eighteen rules while its Approve still called itself policy-level,
 * and a reviewer read "3 of 18" and had to ask what it meant. They were right
 * to. That control changed what an action decided without saying so.
 *
 * This one narrows one policy the reviewer already opened, and changes nothing
 * about what any action decides. The difference is invisible unless it is
 * stated, so it is stated: while a focus is in force this component prints what
 * is shown, that the rest are still here, and that approving decides all of
 * them. That sentence is not decoration and is not optional — it is the reason
 * this control is allowed to exist, and it is rendered here rather than left to
 * the caller precisely so that a caller cannot forget it.
 *
 * ## Why the chips are whatever the policy holds
 *
 * There is no fixed set of buttons. The chips are the stances present in this
 * policy, so a policy holding only obligations offers nothing to choose and
 * renders no control at all, and no chip ever reads zero. A fixed taxonomy
 * would have to name kinds a given policy does not hold, and a zero beside a
 * name reads as a shortfall against a target that does not exist.
 *
 * It also rules out a subtler fault. The three words a reader might expect —
 * decision, definition, informational — are not three groups in the records:
 * `informational` and `definition` are very nearly the same set, so offering
 * both would count most of those records twice and imply a distinction the
 * documents do not carry.
 *
 * ## Nothing here ranks anything
 *
 * The chips are in reading order, not in order of importance, and the wording
 * is the wording of the summary line above them. A rule that supplies a meaning
 * is not a lesser rule; a wrong definition is a real defect and needs the same
 * review as a wrong prohibition.
 */
export interface PolicyCompositionChipsProps<T> {
  /** The one derivation of counts, labels and shown records. */
  composition: StanceFocus<T>;
  /** View state only. Never read by anything that decides, exports or publishes. */
  onFocus: (next: RecordStance | null) => void;
  /**
   * What the reviewer is looking at, named for the announcement. Defaults to
   * the neutral "rules" — a caller with a better word may pass one, but nothing
   * here supplies domain vocabulary.
   */
  noun?: string;
}

export function PolicyCompositionChips<T>({
  composition,
  onFocus,
  noun = "rules",
}: PolicyCompositionChipsProps<T>) {
  const groupId = useId();
  const { tally, focus, shown, total, choosable } = composition;

  // A control that can only be in the state it is already in is not a choice,
  // and a reviewer who clicks it learns nothing. A policy of one kind shows the
  // rules and no buttons.
  if (!choosable) return null;

  return (
    <div className="composition-focus">
      <div
        className="composition-focus__chips"
        role="group"
        aria-labelledby={`${groupId}-label`}
      >
        <span className="composition-focus__label" id={`${groupId}-label`}>
          Show
        </span>
        <button
          type="button"
          className="composition-focus__chip"
          aria-pressed={focus === null}
          onClick={() => onFocus(null)}
        >
          All {total} {total === 1 ? noun.replace(/s$/, "") : noun}
        </button>
        {tally.map((entry) => (
          <button
            key={entry.stance}
            type="button"
            className="composition-focus__chip"
            aria-pressed={focus === entry.stance}
            onClick={() => onFocus(focus === entry.stance ? null : entry.stance)}
          >
            {stanceTallyPhrase(entry)}
          </button>
        ))}
      </div>
      {/*
        Live rather than silent: a reviewer working by keyboard presses a chip
        and the list below them changes with no other signal. Polite rather than
        assertive because nothing here is urgent — it is a reading aid.

        Rendered as a region that is always in the tree, with its text emptied
        when nothing is narrowed, so a screen reader announces the change rather
        than the arrival of a new node.
      */}
      <p className="composition-focus__consequence" role="status" aria-live="polite">
        {focus === null
          ? ""
          : `Showing ${shown.length} of ${total} ${noun} — the rest are still on this policy. ` +
            `Approving this policy decides all ${total}.`}
      </p>
    </div>
  );
}
