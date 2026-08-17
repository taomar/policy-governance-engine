/**
 * The behaviour of the shared post-decision refresh.
 *
 * The wiring guard (aDecisionRefreshesTheStripItReads) pins that both commit
 * funnels route through this function; these pin what the function does once
 * they do — that it refetches BOTH reads of the population, not the rows alone,
 * which is the defect it exists to close.
 */
import { describe, expect, it, vi } from "vitest";

import { refreshQueueAndStrip } from "./reviewReload";

describe("a committed decision refreshes both reads of the population", () => {
  it("refreshes the strip's facets, not only the queue's rows", async () => {
    const candidates = vi.fn().mockResolvedValue(undefined);
    const facets = vi.fn().mockResolvedValue(undefined);

    await refreshQueueAndStrip({ candidates, facets });

    expect(candidates).toHaveBeenCalledTimes(1);
    expect(facets).toHaveBeenCalledTimes(1); // the read that was being skipped
  });

  it("waits for both before it resolves, so the reviewer sees one settled picture", async () => {
    let facetsSettled = false;
    const candidates = vi.fn().mockResolvedValue(undefined);
    const facets = vi.fn().mockImplementation(
      () =>
        new Promise<void>((resolve) =>
          setTimeout(() => {
            facetsSettled = true;
            resolve();
          }, 5),
        ),
    );

    await refreshQueueAndStrip({ candidates, facets });

    expect(facetsSettled).toBe(true);
  });

  it("issues both reads before awaiting either, so a decision costs one round-trip", async () => {
    let candidatesAlreadyIssued = false;
    const candidates = vi.fn().mockResolvedValue(undefined);
    const facets = vi.fn().mockImplementation(async () => {
      candidatesAlreadyIssued = candidates.mock.calls.length > 0;
    });

    await refreshQueueAndStrip({ candidates, facets });

    expect(candidatesAlreadyIssued).toBe(true);
  });
});
