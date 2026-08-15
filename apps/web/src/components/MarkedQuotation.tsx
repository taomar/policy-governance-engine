/**
 * The source, quoted whole, with the runs that became rules marked in it.
 *
 * WHY MARK RATHER THAN REPEAT
 *
 * The reviewer is asking whether the extraction is faithful *and* complete. A
 * mark answers the second half directly: these words became rule ②, and the
 * words beside them became nothing. Two blocks of similar prose, one above the
 * other, make that a comparison exercise instead of a glance.
 *
 * NOT ONE CHARACTER IS ALTERED
 *
 * A mark is a pair of offsets into the stored string. The text is sliced at
 * those offsets and the slices are rendered in order, so what the DOM holds is
 * the passage exactly as stored — a reviewer selecting the quotation and
 * copying it gets the document's words, with no ordinal, bracket or ellipsis
 * mixed in. The rule number is drawn by the stylesheet from `data-rule`, which
 * is why it is not in the text.
 *
 * DIRECTION SURVIVES THE SPLIT
 *
 * One document is bilingual. Splitting a right-to-left sentence into three
 * fragments and letting them fall in DOM order would lay it out backwards, so
 * the quotation's own base direction is set on the wrapper: the fragments are
 * then ordered by it, and each fragment is isolated by `DirectionalText` so a
 * Latin run inside an Arabic sentence keeps its own direction. `<mark>` is
 * inline and carries no direction of its own, so it does not disturb this.
 *
 * A MARK IS NOT A VERDICT
 *
 * Marked and unmarked words are both ordinary. The mark says where a rule came
 * from; it does not say that the unmarked remainder is a miss, and it is drawn
 * in the interface's own neutral tint rather than in a colour that means
 * "attention" — a highlighter yellow would turn every quotation into a page of
 * warnings.
 */
import type { ReactNode } from "react";

import { baseDirection } from "../directionalText";
import type { QuotationMark } from "../policyReading";
import { DirectionalText } from "./DirectionalText";

export function MarkedQuotation({
  text,
  marks,
  className,
  testId,
}: {
  text: string;
  marks: readonly QuotationMark[];
  className?: string;
  testId?: string;
}) {
  const pieces: ReactNode[] = [];
  let cursor = 0;
  marks.forEach((mark, index) => {
    if (mark.start > cursor) {
      pieces.push(<DirectionalText key={`gap-${index}`}>{text.slice(cursor, mark.start)}</DirectionalText>);
    }
    pieces.push(
      <mark
        key={`mark-${index}`}
        className="policy-quote__taken"
        data-rule={mark.ordinal}
        title={`These words are rule ${mark.ordinal} below, as the document states them.`}
      >
        <DirectionalText>{text.slice(mark.start, mark.end)}</DirectionalText>
      </mark>,
    );
    cursor = mark.end;
  });
  if (cursor < text.length) {
    pieces.push(<DirectionalText key="tail">{text.slice(cursor)}</DirectionalText>);
  }
  if (pieces.length === 0) pieces.push(<DirectionalText key="whole">{text}</DirectionalText>);

  return (
    <p
      className={[className, "directional-text--block"].filter(Boolean).join(" ")}
      dir={baseDirection(text)}
      data-testid={testId}
    >
      {pieces}
    </p>
  );
}
