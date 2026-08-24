import { describe, expect, it } from "vitest";
import { qualitySummary } from "./Dashboard";
import { portfolioQualitySummary } from "./ProjectsPage";

describe("quality summary copy", () => {
  it("does not turn a never-run dashboard quality check into zero findings", () => {
    const summary = qualitySummary(0, 0, 2);

    expect(summary.value).toBe("Not evaluated");
    expect(summary.detail).toMatch(/establish a baseline/i);
  });

  it("reserves None for projects that have actually been checked", () => {
    const summary = qualitySummary(0, 2, 2);

    expect(summary.value).toBe("None");
    expect(summary.detail).toBe("latest quality checks");
  });

  it("keeps the project register portfolio total honest before any run", () => {
    const summary = portfolioQualitySummary(0, 0, 3);

    expect(summary.value).toBe("Not evaluated");
    expect(summary.detail).toMatch(/establish a baseline/i);
    expect(summary.risky).toBe(false);
  });
});
