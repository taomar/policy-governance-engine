import { describe, expect, it } from "vitest";
import {
  groupProjectsByDocument,
  groupSubtitle,
  NO_DOCUMENT_LABEL,
  type GroupableProject,
} from "./projectRegisterGroups";

/**
 * That the register collapses runs onto the document they ran against.
 *
 * The witness for this was nine projects covering two documents, but nothing
 * here refers to those projects, their names or their counts. The fixtures are
 * built to the SHAPE of the defect -- several projects holding identical
 * document bytes under differing titles -- so the guard holds at a hundred
 * projects as well as at nine.
 *
 * Controls are included deliberately. A guard containing only offenders cannot
 * tell you when it has begun over-reaching, which is a lesson this session
 * paid for: a title-deduplication fix removed a repetition the source document
 * genuinely contained, and only an unrelated test caught it. So: projects that
 * legitimately stand alone must survive grouping untouched.
 */

function project(over: Partial<GroupableProject> & { key: string }): GroupableProject {
  return {
    document_content_hash: null,
    document_title: null,
    run_count: 1,
    ...over,
  };
}

describe("groupProjectsByDocument", () => {
  it("collapses projects that hold the same document bytes", () => {
    const groups = groupProjectsByDocument([
      project({ key: "first-load", document_content_hash: "aaa", document_title: "Handbook" }),
      project({ key: "re-run", document_content_hash: "aaa", document_title: "Handbook v2" }),
      project({ key: "pinned", document_content_hash: "aaa", document_title: "Handbook pin 1234" }),
    ]);

    expect(groups).toHaveLength(1);
    expect(groups[0].projects.map((p) => p.key)).toEqual(["first-load", "re-run", "pinned"]);
  });

  it("groups on bytes, not on titles that differ", () => {
    // The defect the register had: titles carry the run's annotation, so
    // grouping on them leaves the rows exactly as scattered as before.
    const groups = groupProjectsByDocument([
      project({ key: "a", document_content_hash: "same", document_title: "Staff Handbook 2024-25" }),
      project({ key: "b", document_content_hash: "same", document_title: "final: Segment + refusal" }),
    ]);
    expect(groups).toHaveLength(1);
  });

  it("keeps different documents apart even when their titles match", () => {
    // The mirror of the above, and the reason a title cannot be the key: two
    // genuinely different files may be given one name.
    const groups = groupProjectsByDocument([
      project({ key: "a", document_content_hash: "one", document_title: "Handbook" }),
      project({ key: "b", document_content_hash: "two", document_title: "Handbook" }),
    ]);
    expect(groups).toHaveLength(2);
  });

  it("labels a group with the least annotated title it was given", () => {
    const groups = groupProjectsByDocument([
      project({ key: "c", document_content_hash: "x", document_title: "Employee Handbook pin a7296ff" }),
      project({ key: "a", document_content_hash: "x", document_title: "Employee Handbook" }),
      project({ key: "b", document_content_hash: "x", document_title: "Employee Handbook (v2 comparison)" }),
    ]);
    expect(groups[0].label).toBe("Employee Handbook");
  });

  it("sums extraction runs across the group", () => {
    const groups = groupProjectsByDocument([
      project({ key: "a", document_content_hash: "x", document_title: "D", run_count: 4 }),
      project({ key: "b", document_content_hash: "x", document_title: "D", run_count: 1 }),
    ]);
    expect(groups[0].runCount).toBe(5);
  });

  it("puts a project holding no document last and names it for what it is", () => {
    const groups = groupProjectsByDocument([
      project({ key: "empty", run_count: 0 }),
      project({ key: "loaded", document_content_hash: "x", document_title: "D" }),
    ]);
    expect(groups[groups.length - 1].label).toBe(NO_DOCUMENT_LABEL);
    expect(groups[groups.length - 1].projects.map((p) => p.key)).toEqual(["empty"]);
  });

  it("orders documents by how much work sits on them", () => {
    const groups = groupProjectsByDocument([
      project({ key: "solo", document_content_hash: "b", document_title: "Bravo" }),
      project({ key: "x1", document_content_hash: "a", document_title: "Alpha" }),
      project({ key: "x2", document_content_hash: "a", document_title: "Alpha" }),
    ]);
    expect(groups.map((g) => g.label)).toEqual(["Alpha", "Bravo"]);
  });

  // ---------------------------------------------------------------- CONTROLS

  it("CONTROL: leaves genuinely separate projects as separate rows", () => {
    // Grouping must not be so eager that a register of distinct documents
    // collapses. This is the over-reach direction, and it is the one an
    // offender-only guard would miss.
    const inputs = ["a", "b", "c", "d"].map((h) =>
      project({ key: `p-${h}`, document_content_hash: h, document_title: `Doc ${h}` }),
    );
    const groups = groupProjectsByDocument(inputs);
    expect(groups).toHaveLength(4);
    expect(groups.every((g) => g.projects.length === 1)).toBe(true);
  });

  it("CONTROL: a single project is still a group, not a special case", () => {
    const groups = groupProjectsByDocument([
      project({ key: "only", document_content_hash: "x", document_title: "Only Doc" }),
    ]);
    expect(groups).toHaveLength(1);
    expect(groups[0].label).toBe("Only Doc");
  });

  it("CONTROL: an empty register produces no groups rather than throwing", () => {
    expect(groupProjectsByDocument([])).toEqual([]);
  });

  it("CONTROL: loses no project on the way through", () => {
    // The failure that would be worst here is a row silently disappearing --
    // the same family as the superseded-record mixing defect. Asserted as a
    // conservation law rather than by inspecting any particular grouping.
    const inputs = [
      project({ key: "a", document_content_hash: "x", document_title: "X" }),
      project({ key: "b", document_content_hash: "x", document_title: "X" }),
      project({ key: "c", document_content_hash: "y", document_title: "Y" }),
      project({ key: "d" }),
    ];
    const groups = groupProjectsByDocument(inputs);
    const emitted = groups.flatMap((g) => g.projects.map((p) => p.key)).sort();
    expect(emitted).toEqual(["a", "b", "c", "d"]);
  });

  it("scales without special-casing: many documents, many runs each", () => {
    // Designed for a hundred, not for the nine that were the witness.
    const many = Array.from({ length: 100 }, (_, i) =>
      Array.from({ length: 3 }, (_, r) =>
        project({
          key: `doc${i}-run${r}`,
          document_content_hash: `hash-${i}`,
          document_title: r === 0 ? `Document ${i}` : `Document ${i} rerun ${r}`,
        }),
      ),
    ).flat();

    const groups = groupProjectsByDocument(many);
    expect(groups).toHaveLength(100);
    expect(groups.every((g) => g.projects.length === 3)).toBe(true);
    expect(groups.every((g) => !g.label.includes("rerun"))).toBe(true);
  });
});

describe("groupSubtitle", () => {
  it("counts projects and runs without grading either", () => {
    const [group] = groupProjectsByDocument([
      project({ key: "a", document_content_hash: "x", document_title: "D", run_count: 4 }),
      project({ key: "b", document_content_hash: "x", document_title: "D", run_count: 1 }),
    ]);
    expect(groupSubtitle(group)).toBe("2 projects · 5 extraction runs");
  });

  it("says nothing about runs when none have happened", () => {
    const [group] = groupProjectsByDocument([
      project({ key: "a", document_content_hash: "x", document_title: "D", run_count: 0 }),
    ]);
    expect(groupSubtitle(group)).toBe("1 project");
  });

  it("never describes repeated extraction as a problem", () => {
    // Re-running a document is how the work has been done. The register
    // describing that shape accurately is the fix; editorialising about it
    // would be a different defect wearing the fix's clothes.
    const forbidden = /duplicate|redundant|unnecessary|too many|should|clutter|excess/i;
    const [group] = groupProjectsByDocument(
      Array.from({ length: 9 }, (_, i) =>
        project({ key: `k${i}`, document_content_hash: "x", document_title: "D" }),
      ),
    );
    expect(groupSubtitle(group)).not.toMatch(forbidden);
  });
});
