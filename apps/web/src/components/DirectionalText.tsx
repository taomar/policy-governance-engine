/**
 * Renders text that may mix directions, with each run laid out in its own right.
 *
 * The element used is `<bdi>`, which is the HTML element for exactly this: it
 * isolates its contents from the surrounding text so that neither can reorder
 * the other. That is semantic isolation, not a styling trick — `<bdi>` carries
 * `unicode-bidi: isolate` in the user-agent stylesheet, so it works whether or
 * not this app's CSS loads, and it survives being copied, printed or read by a
 * screen reader.
 *
 * Nothing here alters a single character. The runs are the input text, split
 * and reassembled in order, and the tests assert that concatenating what is
 * rendered reproduces the input exactly. That is also what makes copy and paste
 * safe: the DOM text nodes are the stored logical Unicode, so a reviewer who
 * selects a rule and copies it gets the document's words, not what the screen
 * happened to show.
 *
 * A run whose scripts are interleaved — shredded together character by
 * character upstream, in a way that no writing produces — is marked rather than
 * laid out as if it were prose. Rendering damaged text tidily is the one
 * outcome worth less than rendering it untidily, because a reviewer who cannot
 * read the script has no other way to tell the difference.
 */
import type { CSSProperties, ElementType, ReactNode } from "react";

import { baseDirection, splitDirectionalRuns } from "../directionalText";

interface DirectionalTextProps {
  /** The stored, logical-order text. Rendered as-is. */
  children: ReactNode;
  /** Element to wrap the runs in. Defaults to a `<span>` so it can sit inline. */
  as?: ElementType;
  className?: string;
  style?: CSSProperties;
  /**
   * Align the block to the side its base direction starts from. Off by default
   * because most callers are inline fragments inside a line that is already
   * aligned; on for paragraphs, table cells and anything that owns its width.
   */
  align?: boolean;
}

/** Text that cannot be split — anything that is not a string is passed through
 *  untouched rather than coerced, so `null`, numbers and nested nodes behave as
 *  they did before this component existed. */
function isSplittable(children: ReactNode): children is string {
  return typeof children === "string" && children.length > 0;
}

export function DirectionalText({
  children,
  as: Wrapper = "span",
  className,
  style,
  align = false,
}: DirectionalTextProps) {
  if (!isSplittable(children)) {
    return (
      <Wrapper className={className} style={style}>
        {children}
      </Wrapper>
    );
  }

  const base = baseDirection(children);
  const runs = splitDirectionalRuns(children);

  // A single run in the reading direction of the interface needs no wrapping at
  // all. Emitting the bare string keeps the DOM of an English-only product
  // identical to what it was, so this change is invisible where it has nothing
  // to say.
  const untouched = runs.length === 1 && runs[0].direction === "ltr" && !runs[0].interleaved;

  return (
    <Wrapper
      className={
        align ? [className, "directional-text--block"].filter(Boolean).join(" ") : className
      }
      style={style}
      // The wrapper's direction orders the runs relative to each other. Each run
      // is isolated, so this decides their sequence on the line and nothing
      // inside them.
      dir={untouched ? undefined : base}
    >
      {untouched
        ? children
        : runs.map((run, index) => (
            <bdi
              // Runs are positional and the text is static for a given record,
              // so the index is the identity here.
              key={index}
              dir={run.direction}
              lang={run.lang}
              className={run.interleaved ? "directional-text__interleaved" : undefined}
              title={
                run.interleaved
                  ? "This text has two scripts interleaved character by character, which no writing produces. It was damaged before it reached this screen and is shown as stored rather than tidied up."
                  : undefined
              }
              data-interleaved={run.interleaved ? "true" : undefined}
            >
              {run.text}
            </bdi>
          ))}
    </Wrapper>
  );
}
