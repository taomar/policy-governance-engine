/**
 * Where a citation sits in its source document.
 *
 * Evidence carries a `section` per citation, and it is `null` on a good number
 * of them. The interface used to render it as ` · {section}` and nothing at
 * all when it was absent, which collapses two different facts into one blank:
 * a passage that sits under a heading nobody recorded looked exactly like a
 * passage the reader had already been told everything about.
 *
 * That distinction is the whole point of this module. A reviewer judging
 * "In the case of absences on that day, there will be action taken according
 * to the administration procedures." cannot tell what "that day" is. The
 * heading is part of what would tell them, and being told it was not captured
 * is itself worth knowing, because it says the passage may lean on surrounding
 * text they have not been shown.
 *
 * The words live here rather than in the server for the same reason the
 * condition-route wording does: the server states facts, the interface states
 * them in a language a reviewer reads. Nothing here paraphrases a heading —
 * when one exists it is quoted exactly, like every other piece of source text.
 */

export interface HeadingContext {
  /** True when the document supplied a heading for this citation. */
  known: boolean;
  /** The heading, exactly as the document had it. Empty when not known. */
  heading: string;
  /** What to show when there is no heading to quote. */
  absence: string;
}

/** Shown against every citation, in both states, so the field never vanishes. */
export const HEADING_CONTEXT_LABEL = "Heading in the source";

/**
 * Said when no heading was captured.
 *
 * States what is and is not known, and points at the control sitting beside it.
 * It does not describe the citation as deficient — an unrecorded heading is a
 * fact about how the document was read, not about the policy.
 */
export const HEADING_NOT_RECORDED =
  "Not recorded for this citation. Open the document to see what it sits under.";

/**
 * Read the heading context off one citation's `section`.
 *
 * Whitespace-only is treated as absent: a heading made of spaces would render
 * as an empty quotation, which reads as a heading that says nothing rather
 * than as one nobody captured.
 */
export function headingContext(section: string | null | undefined): HeadingContext {
  const heading = (section ?? "").trim();
  return {
    known: heading.length > 0,
    heading,
    absence: HEADING_NOT_RECORDED,
  };
}
