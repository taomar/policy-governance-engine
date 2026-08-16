import { Alert, Tag, Typography } from "antd";
import {
  AMBIGUITY_UNNAMED,
  ambiguityNote,
  isKnownAmbiguityStatus,
} from "../ambiguityNote";

const { Text, Paragraph } = Typography;

/**
 * What the source's wording admits, shown on the record where it is decided.
 *
 * Two placements, deliberately:
 *
 * - `variant="banner"` sits in the inspector header beside Approve and Reject.
 *   It renders only for a status worth interrupting a reviewer about, because a
 *   banner on every record is a banner nobody reads — 230 of 273 records in a
 *   document under review read one way, and drowning the other 43 in identical
 *   notices would lose exactly the ones this exists for.
 * - `variant="section"` sits on the Parties & routes tab and renders for
 *   EVERY status including `none`. The field is never invisible there: a
 *   reviewer who wants to know what the system holds about this record can
 *   always find it, rather than inferring from the absence of a banner.
 *
 * The banner is text, not a hover. The status already had a hover-only
 * treatment — a warning glyph with a `title` — and hover does not exist for a
 * keyboard user, so a reviewer could reach Approve having never been shown it.
 */
export function AmbiguityNoteView({
  status,
  variant,
}: {
  status: string | null | undefined;
  variant: "banner" | "section";
}) {
  const note = ambiguityNote(status);
  const known = isKnownAmbiguityStatus(status);

  // The banner exists to interrupt. A record whose wording reads one way has
  // nothing to interrupt for, so it stays on the tab only.
  if (variant === "banner" && !note.prominent) return null;

  const body = (
    <>
      <Paragraph type="secondary" className="ambiguity-note-reason">
        {note.reason}
      </Paragraph>
      {/* Shown for every status, known or not: the record stores a status and
          no field saying which words are open, and implying otherwise would
          claim precision the record does not carry. */}
      <Text type="secondary" className="ambiguity-note-unnamed">
        {AMBIGUITY_UNNAMED}
      </Text>
      {/* Only for a status this build cannot read. Rendering the stored value
          is the point — it is the one thing that lets a reviewer report what
          they saw — but it is labelled as a stored identifier so it is never
          mistaken for a description written for them. */}
      {!known && (
        <div className="ambiguity-note-raw">
          <Text type="secondary">Stored value: </Text>
          <Text code>{status ? String(status) : "(nothing recorded)"}</Text>
        </div>
      )}
    </>
  );

  if (variant === "section") {
    return (
      <div className="decision-readiness-section ambiguity-note">
        <Text strong>How the source's wording reads</Text>
        <div className="ambiguity-note-tag">
          <Tag color={known ? undefined : "default"}>{note.label}</Tag>
        </div>
        {body}
      </div>
    );
  }

  return (
    <Alert
      className="ambiguity-note ambiguity-note--banner"
      type={note.severity}
      showIcon
      message={note.label}
      description={body}
    />
  );
}
