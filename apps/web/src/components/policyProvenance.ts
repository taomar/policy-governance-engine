/**
 * The chain from a document to a policy record.
 *
 * WHY THIS EXISTS
 *
 * The Overview tab restated three facts the card header had already stated —
 * page, passages, rules — as three grey pills, and said nothing else. A
 * reviewer's actual complaint was that they could not trace the policy, and
 * tracing is precisely what the tab omitted and the data supports. Every link
 * in the chain below was already loaded on both surfaces; none of it was on
 * screen.
 *
 * WHAT IT REFUSES TO DO
 *
 * *Absent is not empty.* Every field here is optional and every consumer must
 * be able to say "this app does not know" differently from "there is none".
 * The distinction is not pedantry: a policy that has never been published and a
 * policy whose publication history has not been fetched look identical if both
 * render as a blank, and only one of them is a fact.
 *
 * *No link is invented.* A run id that resolves to no known run yields the id
 * and nothing else, rather than a plausible document title borrowed from a
 * neighbouring rule. The point of a provenance chain is that a reader can
 * follow it; a guessed link is worse than a missing one because it cannot be
 * told apart from a real one.
 *
 * *Every derivation is here, not in a pane.* Both surfaces render the same
 * chain from the same function, which is what stops the published Overview
 * becoming a second, slowly diverging opinion about where a policy came from.
 */
import type { ReviewFacetRun } from "../api";
import type { PolicyRecordView, PolicySightingView } from "./policyTabPanes";

/** One extraction run that produced rules of this policy. */
export interface PolicyRunLink {
  /** The run's id, always known — it is what the rule carries. */
  id: string;
  /** `RUN-3F9A2B1C`, when the run itself could be found. Null when it could not. */
  reference: string | null;
  status: string | null;
  startedAt: string | null;
  /** How many of the policy's rules this run produced. */
  rules: number;
}

/** The document version the policy was read out of. */
export interface PolicyDocumentLink {
  documentId: string | null;
  title: string | null;
  versionId: string | null;
  versionLabel: string | null;
  contentHash: string | null;
}

/** Where in its document the policy sits. */
export interface PolicyPlacement {
  /** Governing headings, outermost first, excluding the policy's own. */
  trail: string[];
  /** First and last page any of its passages was quoted from. Equal when the
   *  policy sits on one page; null when no passage recorded a page. */
  pages: { first: number; last: number } | null;
  /** The verbatim source element attribution, which is what a reader would
   *  quote back when asking where something came from. */
  sourceElements: string | null;
  /** Whether the boundary is the one the pipeline recorded, or one inferred at
   *  read time from the headings its rules cite. */
  boundaryRecorded: boolean;
}

/** Where the policy has been published, when this app has looked. */
export type PolicyPublication =
  | { known: false }
  | { known: true; versions: PolicyPublishedIn[] };

/** One published version this policy's key appears in. */
export interface PolicyPublishedIn {
  versionId: string;
  versionNumber: number | null;
  /** Whether this is the version that applies now. This — not the presence of
   *  an end date — is what says a version is the one in force: a superseded
   *  version can carry no end date at all, having stopped applying because a
   *  later one replaced it. */
  isActive: boolean;
  approvedAt: string | null;
  /** When the version starts and stops applying, where the record says so.
   *  Approval and application are different moments and are not interchangeable
   *  answers to "does this bind me". */
  effectiveFrom: string | null;
  effectiveTo: string | null;
}

export interface PolicyProvenance {
  /** The policy's identity across versions, and the handle a reviewer follows. */
  provisionKey: string;
  /** The provision row this cut of the policy is, where one was persisted. */
  provisionId: string | null;
  document: PolicyDocumentLink;
  /** Every run that produced a rule of this policy, most rules first.
   *
   *  A list rather than one: after a re-extraction a policy's rules can come
   *  from more than one run, and that is a finding about the record rather than
   *  a detail to average away. */
  runs: PolicyRunLink[];
  placement: PolicyPlacement;
  publication: PolicyPublication;
}

function pageRange(record: PolicyRecordView): { first: number; last: number } | null {
  const pages = record.policy.passages
    .map((passage) => passage.page)
    .filter((page): page is number => page != null);
  // The policy's own page is the fallback rather than the primary: it is one
  // page, and a policy that runs across a break occupies more than one.
  if (pages.length === 0) {
    return record.policy.page == null ? null : { first: record.policy.page, last: record.policy.page };
  }
  return { first: Math.min(...pages), last: Math.max(...pages) };
}

/**
 * Resolve the chain for one policy.
 *
 * `runs` is the policy set's extraction runs, which each carry their document
 * and document version — so one already-loaded list resolves the whole chain
 * from rule to file. Passing `null` means this app has not loaded them, and
 * every link that depends on them then reports its id and nothing more.
 */
export function policyProvenance(
  record: PolicyRecordView,
  sources: {
    runs?: readonly ReviewFacetRun[] | null;
    sightings?: readonly PolicySightingView[] | null;
  } = {},
): PolicyProvenance {
  const knownRuns = new Map((sources.runs ?? []).map((run) => [run.id, run]));

  const rulesPerRun = new Map<string, number>();
  for (const entry of record.rules) {
    const runId = entry.rule.lineage?.extraction_run_id;
    if (!runId) continue;
    rulesPerRun.set(runId, (rulesPerRun.get(runId) ?? 0) + 1);
  }

  const runs: PolicyRunLink[] = [...rulesPerRun.entries()]
    .map(([id, rules]) => {
      const known = knownRuns.get(id);
      return {
        id,
        reference: known?.reference ?? null,
        status: known?.status ?? null,
        startedAt: known?.started_at ?? null,
        rules,
      };
    })
    .sort((a, b) => b.rules - a.rules || a.id.localeCompare(b.id));

  // The document is taken from the policy's own version id where the runs can
  // identify it, and from the runs that produced its rules otherwise. Not the
  // other way round: the policy states which document version it belongs to,
  // and a run only implies it.
  const versionId = record.policy.document_version_id;
  const matchingRun =
    (versionId ? (sources.runs ?? []).find((run) => run.document_version_id === versionId) : undefined) ??
    (runs.length > 0 ? knownRuns.get(runs[0].id) : undefined);

  const document: PolicyDocumentLink = {
    documentId: matchingRun?.document_id ?? null,
    title: matchingRun?.document_title ?? null,
    versionId: versionId ?? matchingRun?.document_version_id ?? null,
    versionLabel: matchingRun?.version_label ?? null,
    contentHash: matchingRun?.content_hash ?? null,
  };

  const publication: PolicyPublication =
    sources.sightings == null
      ? { known: false }
      : {
          known: true,
          versions: sources.sightings.map((sighting) => ({
            versionId: sighting.version_id,
            versionNumber: sighting.version_number,
            isActive: sighting.is_active,
            approvedAt: sighting.approved_at,
            effectiveFrom: sighting.effective_from ?? null,
            effectiveTo: sighting.effective_to ?? null,
          })),
        };

  return {
    provisionKey: record.policy.key,
    provisionId: record.policy.provision_id ?? null,
    document,
    runs,
    placement: {
      trail: record.policy.heading_path.slice(0, -1),
      pages: pageRange(record),
      sourceElements: record.policy.source_elements || null,
      boundaryRecorded: record.policy.persisted,
    },
    publication,
  };
}

/**
 * A calendar day, written the way the reader's own system writes days.
 *
 * Not `toLocaleString`, which appends a time to a value that has none: these
 * are dates, and a policy that applies "from 15/08/2026, 00:00:00" invites a
 * reader to wonder what happens at 23:59. Not `new Date(value)` either — that
 * reads a bare `YYYY-MM-DD` as UTC midnight, so a reader west of Greenwich is
 * shown the day before the one the record holds. The parts are read straight
 * off the string and rebuilt as a local day, which cannot shift.
 *
 * Anything that is not a plain day is returned untouched rather than rendered
 * as an invalid date.
 */
export function formatDay(value: string): string {
  const parts = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!parts) return value;
  const day = new Date(Number(parts[1]), Number(parts[2]) - 1, Number(parts[3]));
  return Number.isNaN(day.getTime()) ? value : day.toLocaleDateString();
}

/** Today as a plain day, for comparing against the days a record holds. */
export function today(): string {
  const now = new Date();
  const month = `${now.getMonth() + 1}`.padStart(2, "0");
  const day = `${now.getDate()}`.padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

/**
 * Whether a published version applies, and from and until when.
 *
 * The question a business reader arrives with is not when a version was
 * approved but whether it binds them, and those are different moments: a
 * version approved in one month can be written to apply from the next.
 *
 * THE CLAIM THIS REFUSES TO MAKE
 *
 * A superseded version can carry no end date at all — it stopped applying
 * because a later version replaced it, and that is recorded as the later
 * version being the active one, not as a date on this one. So an absent end
 * date is never reported as an open one. A version that no longer applies is
 * spoken about in the past tense and its end is simply not mentioned, which is
 * the difference between "we do not know when this stopped" and the false
 * "this never stopped".
 *
 * Returns null where the record holds no start date, so that a caller renders
 * nothing rather than a sentence with a hole in it. `now` is a parameter so a
 * test can pin the day rather than pass on a date that goes stale.
 */
export function whenItApplies(
  version: Pick<PolicyPublishedIn, "isActive" | "effectiveFrom" | "effectiveTo">,
  now: string = today(),
): string | null {
  const from = version.effectiveFrom;
  if (!from) return null;
  const until = version.effectiveTo ? ` until ${formatDay(version.effectiveTo)}` : "";

  if (!version.isActive) {
    return `applied from ${formatDay(from)}${until}`;
  }
  return from > now
    ? `takes effect ${formatDay(from)}${until}`
    : `in force since ${formatDay(from)}${until}`;
}
