/**
 * What the source's own wording admits, in words a reviewer can read.
 *
 * `ambiguity_status` is a statement about the DOCUMENT, not about this record
 * and not about the route it travels. It says whether the sentence the record
 * was read from can be read more than one way. A document that says something
 * two ways is a fact about that document; the record quoting it faithfully is
 * doing its job. Nothing here is missing, unfinished or awaiting work.
 *
 * It is stored on every record and, before this file, reached the screen only
 * as a bare warning glyph in the inspector header whose hover text read
 * "Ambiguity: Human judgment required". A reviewer who never hovered — or who
 * reached the record by keyboard, where no hover exists — approved it for
 * publication without being told. On a document under review 43 of 273 records
 * carried a non-`none` status and none of them said so in text.
 *
 * The server emits the enum and this file owns the words, the same split
 * `conditionRoute.ts` uses for `condition_provenance` and `AggregateLimitsPage`
 * uses for `not_machine_executable`. Wording changed here needs no migration
 * and reaches records published years ago.
 *
 * IMPORTANT: the record carries a status and nothing else. There is no field
 * naming WHICH words are open to more than one reading, so nothing here may
 * imply the record knows. `AMBIGUITY_UNNAMED` is the honest statement of that
 * limit and is shown wherever a status is shown.
 */
export interface AmbiguityNote {
  /** Short label for a tag. */
  label: string;
  /** What the source did, and what follows from it. One or two sentences. */
  reason: string;
  /** antd severity for the surrounding Alert. */
  severity: "success" | "info" | "warning";
  /** Whether this is worth interrupting a reviewer about next to Approve. */
  prominent: boolean;
}

/**
 * Wording per status. Keys are the members of `AmbiguityStatus` in
 * `contracts/policy.py`, and `tests/unit/test_ambiguity_note_wording.py`
 * fails if that enum gains a member this object has not.
 *
 * Read these as descriptions of the source text. None of them says the record
 * lacks anything, and none of them says work remains to be done on it.
 */
export const AMBIGUITY_NOTE: Record<string, AmbiguityNote> = {
  none: {
    label: "Reads one way",
    reason:
      "The wording this record was read from carries one reading. Nothing in the sentence was found to point two ways.",
    severity: "success",
    prominent: false,
  },
  non_blocking: {
    label: "Reads more than one way, same outcome",
    reason:
      "The wording this record was read from can be read more than one way, and the readings meet at the same outcome. The difference is in how the sentence is read, not in what results.",
    severity: "info",
    prominent: true,
  },
  human_judgment_required: {
    label: "Reads more than one way",
    reason:
      "The wording this record was read from can be read more than one way, and the source does not itself say which reading is meant. The record carries the source's words as they stand.",
    severity: "warning",
    prominent: true,
  },
  blocking: {
    label: "Reads more than one way, outcomes differ",
    reason:
      "The wording this record was read from can be read more than one way, and the readings lead to different outcomes. The record carries the source's words as they stand.",
    severity: "warning",
    prominent: true,
  },
};

/**
 * Shown for a status this build has no wording for — a record written by a
 * newer server, or an older one whose status has since been retired. It names
 * the situation and shows the stored value as an identifier, clearly labelled
 * as one. It never renders the raw value as if it were English, and it never
 * renders nothing: a reviewer must be able to tell that the record carries a
 * status this screen cannot read, which is itself worth knowing before
 * approving it.
 */
export const UNKNOWN_AMBIGUITY_NOTE: AmbiguityNote = {
  label: "Recorded, not readable here",
  reason:
    "This record carries a wording status that this screen has no description for. The stored value is shown below as it was written; open the source to read the sentence yourself.",
  severity: "warning",
  prominent: true,
};

/**
 * The record stores a status and no field naming which words are open. Saying
 * so is better than a description implying the system knows more than it does.
 */
export const AMBIGUITY_UNNAMED =
  "The record stores this as a status only — it does not record which words read more than one way. The source text is quoted under Overview.";

/** Wording for a stored `ambiguity_status`, never throwing on an unknown one. */
export function ambiguityNote(status: string | null | undefined): AmbiguityNote {
  if (!status) return UNKNOWN_AMBIGUITY_NOTE;
  return AMBIGUITY_NOTE[status] ?? UNKNOWN_AMBIGUITY_NOTE;
}

/** Whether this build recognises the stored status. */
export function isKnownAmbiguityStatus(status: string | null | undefined): boolean {
  return Boolean(status) && Object.hasOwn(AMBIGUITY_NOTE, status as string);
}
