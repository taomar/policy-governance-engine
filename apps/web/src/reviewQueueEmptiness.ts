/**
 * When the review queue is entitled to its apparatus, and when it is not.
 *
 * The review surface carries six status tabs, four operation counters, a
 * document/run/change filter bar, a content-kind switch, a search box, an
 * export menu and a two-pane workspace held open at
 * `clamp(560px, 100vh - 150px, 1400px)`. That is the right furniture for a
 * queue with records in it. For a project holding none it measured 1,117px of
 * controls filtering nothing and a pane inspecting nothing, which made a
 * project with no work in it look exactly like a project with all of it.
 *
 * The distinction that decides this is not "the list on screen is empty". A
 * queue filtered down to nothing must keep every control, because the control
 * is how the reviewer gets back out. Only a queue that is empty *with every
 * filter still at its default* is genuinely empty, and only then is the
 * apparatus suppressed.
 *
 * This lives outside the component so the rule can be tested directly. The
 * component renders the consequence; the consequence is not the thing that can
 * quietly go wrong.
 */

/** The state of the review filters, as the queue holds them. */
export interface ReviewFilterState {
  /** Status tab. `"all"` is the default. */
  status: string;
  /** Document id, or `""` for no document filter. */
  document: string;
  /** Extraction run id, or `""` for no run filter. */
  run: string;
  /** Change classification. `"all"` is the default, not `""`. */
  delta: string;
  /** Whether rules a later run retired are being shown. */
  showRemoved: boolean;
  /** Free-text search. */
  search: string;
}

/**
 * True when nothing is narrowing the queue.
 *
 * The two "off" spellings are deliberate and not interchangeable: document and
 * run are off at `""`, delta is off at `"all"`. Treating `"all"` as an active
 * filter -- or `""` as an inactive delta -- is the mistake this centralises.
 */
export function filtersAreDefault(filters: ReviewFilterState): boolean {
  return (
    filters.status === "all" &&
    filters.document === "" &&
    filters.run === "" &&
    filters.delta === "all" &&
    !filters.showRemoved &&
    filters.search.trim() === ""
  );
}

/**
 * True when this project holds no candidate rules at all, as opposed to none
 * that match what is being asked for.
 *
 * `loadedCount` is the length of the queue as fetched. With every filter at its
 * default `loadCandidates` sends no status, scope or delta argument and paging
 * is done client-side, so the fetched queue is the whole queue and a count of
 * zero means the project is empty.
 *
 * While a fetch is in flight the count is not evidence of anything, so
 * `loading` suppresses the verdict rather than letting the surface collapse and
 * re-expand as results arrive.
 *
 * The project-wide `review-facets` totals would be a more direct signal and
 * were tried first. They are not usable: the endpoint returns
 * `status_totals: {}` alongside empty `documents` and `runs` for a project
 * holding 58 candidate rules, so a test built on it collapsed a full queue as
 * though it were empty. That is a server-side defect, reported rather than
 * worked around, and nothing here depends on it.
 */
export function reviewQueueIsEmpty(
  loadedCount: number,
  filters: ReviewFilterState,
  loading: boolean,
): boolean {
  return !loading && loadedCount === 0 && filtersAreDefault(filters);
}
