/**
 * Grouping the project register by the document each project governs.
 *
 * WHY THIS EXISTS
 *
 * A project ought to be a document under governance, with runs inside it. The
 * product has no run-within-a-project, so re-extracting a document meant
 * creating another project, and the register became a run log wearing a
 * register's clothes. The fix at the data level is a schema change; this is the
 * display half, and it is worth doing on its own because the grouping is
 * derivable from what is already stored.
 *
 * WHY THE CONTENT HASH AND NOT THE TITLE
 *
 * Titles carry the run's annotation -- one file appears as "AIS Employee
 * Handbook", "AIS Handbook v3", "AIS Employee Handbook pin a7296ff". Grouping
 * on them would leave the rows exactly as scattered as they are now. The
 * content hash is the file's own bytes: two projects holding the same bytes
 * hold the same document, whatever anybody called them. It needs no list of
 * known documents, no parsing of names, and it behaves the same at a hundred
 * projects as at nine.
 *
 * WHAT IS AND IS NOT CLAIMED
 *
 * The group is labelled with the shortest title among its members. Annotations
 * lengthen a name rather than shorten it, so the shortest is the least
 * annotated -- but the point is that every title in the group is genuinely a
 * title this document was given, so choosing one presents a reviewer with the
 * document's own words rather than a name composed here. Each project keeps its
 * own name beneath the group, so nothing is hidden by the choice.
 */

export interface GroupableProject {
  key: string;
  document_content_hash: string | null;
  document_title: string | null;
  run_count: number | null;
}

export interface DocumentGroup<T extends GroupableProject> {
  /** The content hash, or null for projects holding no document at all. */
  documentHash: string | null;
  /** What to call this document on screen. */
  label: string;
  projects: T[];
  /** Extraction runs across every project in the group. */
  runCount: number;
}

/** A project that holds no document has nothing to be grouped under. */
export const NO_DOCUMENT_LABEL = "No document loaded";

/**
 * Collapse projects onto the documents they govern.
 *
 * Order is by group size descending then label, so the documents carrying the
 * most work sit at the top. Projects within a group keep the order they
 * arrived in, which is the caller's sort.
 */
export function groupProjectsByDocument<T extends GroupableProject>(
  projects: readonly T[],
): DocumentGroup<T>[] {
  const byHash = new Map<string, T[]>();
  const withoutDocument: T[] = [];

  for (const project of projects) {
    const hash = project.document_content_hash;
    if (!hash) {
      withoutDocument.push(project);
      continue;
    }
    const existing = byHash.get(hash);
    if (existing) existing.push(project);
    else byHash.set(hash, [project]);
  }

  const groups: DocumentGroup<T>[] = [];
  for (const [hash, members] of byHash) {
    groups.push({
      documentHash: hash,
      label: documentLabel(members),
      projects: members,
      runCount: members.reduce((total, p) => total + (p.run_count ?? 0), 0),
    });
  }

  groups.sort((a, b) => b.projects.length - a.projects.length || a.label.localeCompare(b.label));

  if (withoutDocument.length > 0) {
    // Last, and named for what it is. A project with no document is not a
    // document with no name, and folding it in with the rest would say it was.
    groups.push({
      documentHash: null,
      label: NO_DOCUMENT_LABEL,
      projects: withoutDocument,
      runCount: withoutDocument.reduce((total, p) => total + (p.run_count ?? 0), 0),
    });
  }

  return groups;
}

function documentLabel(members: readonly GroupableProject[]): string {
  const titles = members
    .map((m) => m.document_title)
    .filter((t): t is string => typeof t === "string" && t.trim().length > 0)
    .map((t) => t.trim());
  if (titles.length === 0) return "Untitled document";
  return titles.reduce((shortest, candidate) =>
    candidate.length < shortest.length ||
    (candidate.length === shortest.length && candidate < shortest)
      ? candidate
      : shortest,
  );
}

/**
 * What to say about a document that several projects govern.
 *
 * This states the shape a reviewer is looking at without judging it. Repeated
 * extraction of one document is how the work has actually been done; the
 * register describing it accurately is the fix, not a complaint about it.
 */
export function groupSubtitle(group: DocumentGroup<GroupableProject>): string {
  const parts: string[] = [];
  const projectCount = group.projects.length;
  parts.push(projectCount === 1 ? "1 project" : `${projectCount} projects`);
  if (group.runCount > 0) {
    parts.push(group.runCount === 1 ? "1 extraction run" : `${group.runCount} extraction runs`);
  }
  return parts.join(" · ");
}
