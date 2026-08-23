/** What a surface shows while a long request is open.
 *
 * WHY THIS IS SHARED
 *
 * Five surfaces in this app make a request that can run for a minute or more,
 * and they were split two against three. Document upload and the project case
 * runner each announced the wait properly: a live region, a running clock, what
 * the server is doing, and how long it usually takes. Quality, the validation
 * lab and the rule scenario tester showed a spinning button and nothing else.
 *
 * Those three are the slowest of the five — an AI quality evaluation over a
 * published version, a sealed-scenario generation, a judged scenario read — so
 * the surfaces most in need of the pattern were the ones without it. A reader
 * who cannot tell a working request from a hung one reloads the page, and on
 * these surfaces reloading loses the run.
 *
 * The clock, not a percentage: these calls return one reply at the end. A
 * progress bar would have to invent its own position, and a bar that advances
 * on a guess is worse than a number that is true. This is the reasoning the
 * case runner already carried, kept here so it is stated once.
 *
 * `role="status"` with `aria-live="polite"` so the wait is announced without
 * interrupting, which is the only way a screen-reader user learns the request
 * is still open at all.
 */
import { Space, Typography } from "antd";
import { formatElapsed } from "../uploadFeedback";

const { Text } = Typography;

export interface LongRunWaitProps {
  /** What the server is doing, in the reader's terms. No trailing clock — this
   *  component appends it, so every surface phrases the elapsed time alike. */
  headline: string;
  /** Why it takes as long as it does. One or two sentences. */
  detail: string;
  /** The honest range, e.g. "30–120 seconds". Omitted when there is no measured
   *  range to state: a made-up estimate is worse than none. */
  expected?: string;
  /** Milliseconds since the request opened. */
  elapsedMs: number;
  className?: string;
}

export function LongRunWait({ headline, detail, expected, elapsedMs, className }: LongRunWaitProps) {
  return (
    <div className={className ?? "long-run-wait"} role="status" aria-live="polite">
      <Space orientation="vertical" size={4}>
        <Text strong>
          {headline} · {formatElapsed(elapsedMs)} elapsed
        </Text>
        <Text type="secondary">{detail}</Text>
        {expected ? (
          <Text type="secondary">
            This usually takes {expected}. There is one reply at the end, so the live signal here is the
            running clock rather than a guessed percentage.
          </Text>
        ) : null}
      </Space>
    </div>
  );
}
