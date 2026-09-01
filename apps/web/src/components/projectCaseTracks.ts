/**
 * Reading a project case answer as the two independent tracks it now is.
 *
 * WHY THIS IS NOT ONE STATUS
 *
 * A case put to a project can ask two things, and they are not the same
 * question: what the published policies *state*, and how the case *comes out*.
 * A reviewer can ask for either, or for both in one sentence — "what does the
 * policy say about overtime, and was my Tuesday shift within it?" — and both
 * are owed an answer. The two are gathered independently over the one
 * retrieval, so a case can be answered on information while the verdict still
 * needs facts. That is a whole, correct, useful reply, and the one thing this
 * module exists to stop is it being collapsed into a single scalar status,
 * where it can only be rendered as a failure or as an answer it is not.
 *
 * So the reading is two tracks side by side. Each carries its own outcome from
 * its own closed vocabulary, and two outcomes belong to neither gather:
 *
 *   - `not_requested` — the classifier did not read the question as asking for
 *     this track, so it never ran. The caller's own silence, not the corpus's.
 *   - `not_evaluated` — retrieval produced nothing to answer from, so neither
 *     track ran. A legitimate reply, and never "the policies said nothing".
 *
 * WHY THE OLD SHAPE STILL READS
 *
 * The endpoint used to return one branch chosen by an exclusive `intent`, and
 * before that a flat `status`/`verdict`/`answer` on the evaluation itself. Both
 * still arrive — from a server that has not moved, and from an answer captured
 * before the redesign — and both are read here rather than in the component, so
 * the interface has one shape to render and exactly one place decides what an
 * older reply meant. Nothing is invented while doing it: when the two booleans
 * are absent they are inferred from the branch that is actually present, which
 * is all the older reply ever claimed.
 */
import type {
  ProjectCaseAnswer,
  ProjectCaseCitation,
  ProjectCaseCitationServes,
  ProjectCaseEvaluation,
  ProjectCaseJudgement,
  ProjectCasePolicyCandidate,
  ProjectCaseRuleSelection,
} from "../api";

/** The two halves of a case, named the way the receipt names them. */
export type CaseTrack = "information" | "verdict";

/** No track ran, because nothing was retrieved to run one over. */
export const NOT_EVALUATED = "not_evaluated";

/** This track was not asked for. Kept apart from every gather outcome so a
 *  reader can never mistake their own silence for the policies'. */
export const NOT_REQUESTED = "not_requested";

/** The track was asked for and the reply carried no section for it. Not a
 *  gather state: it is this client saying the answer is short of what the
 *  contract promises, rather than picking a gather outcome to stand in. */
export const NO_SECTION = "no_section";

/** What an information track may report, from its own gather. */
export const INFORMATION_STATUSES = ["answered", "no_rule_bears", "declined", "failed"] as const;

/** What a verdict track may report. Two more than information, because only a
 *  verdict can be blocked on facts or left unsettled by rules that do bear. */
export const VERDICT_STATUSES = [
  "answered",
  "missing_required_facts",
  "not_settled_by_rules",
  "no_rule_bears",
  "declined",
  "failed",
] as const;

/** The one status that carries an answer, on either track. */
export const STATUS_WITH_ANSWER = "answered";

export interface CaseTrackReading {
  track: CaseTrack;
  /** The classifier read the question as asking for this track. */
  requested: boolean;
  /** A gather ran and returned a section. */
  ran: boolean;
  /** This track's outcome: a member of its closed set, `not_requested`,
   *  `not_evaluated`, `no_section`, or whatever unknown string the server sent. */
  outcome: string;
  /** The outcome is one this client knows how to describe. */
  known: boolean;
  /** True exactly when the outcome is `answered`: the information track stated
   *  an answer, or the verdict track reached a determination. */
  answered: boolean;
  section: ProjectCaseJudgement | null;
}

/** One rule the answer rested on, and which track or tracks cited it. */
export interface MergedCaseCitation extends ProjectCaseCitation {
  serves: ProjectCaseCitationServes[];
}

export interface CaseAskedReading {
  information: boolean;
  verdict: boolean;
  /** The server stated the two booleans itself. False when they were inferred
   *  from an older reply's single branch, which is worth saying out loud rather
   *  than presenting a guess as the classifier's reading. */
  declared: boolean;
  reasoning: string;
  classifierVersion: string | null;
}

export interface CaseTracksReading {
  /** Something was retrieved and at least one gather could run. */
  evaluated: boolean;
  asked: CaseAskedReading;
  information: CaseTrackReading;
  verdict: CaseTrackReading;
  /** Every cited rule, once, carrying the track or tracks that cited it. */
  citations: MergedCaseCitation[];
  /** Every rule id the answer names, cited or waited on. */
  ruleIds: string[];
}

/** One large policy that was read rule by rule, with its own selection. */
export interface SlicedPolicyReading {
  policy: ProjectCasePolicyCandidate;
  selection: ProjectCaseRuleSelection;
}

/** One policy whose terms were read through an identical policy's record.
 *
 *  Proven identical governance, not a near-copy: the collapsed policy's record
 *  was never put in front of the gather, and it did not need to be, because the
 *  representative says the same thing. `representative` is where those terms
 *  were actually read.
 */
export interface DuplicatePolicyReading {
  policy: ProjectCasePolicyCandidate;
  representative: string;
}

/** The narrowings that happened after search, disclosed in their own right.
 *
 *  Search discards by relevance and the interface already reports that. These
 *  are the ones that happen to policies search *kept*, and they are four
 *  different things that must not be told as one:
 *
 *    - a policy holding more rules than the threshold is read rule by rule;
 *    - a whole record that would overflow one grounded pass is set aside;
 *    - a policy proven to govern identically to one already retrieved is
 *      collapsed into it, and its terms *are* read, through that record;
 *    - a policy that ranked inside the budget is offered after it because a
 *      policy requiring the same thing was offered first — which is **not** a
 *      duplicate finding, and whose terms were **not** read.
 *
 *  The last two are the pair a reader is most likely to be handed as one
 *  number, and conflating them would either claim a distinct policy was read
 *  when it was not, or claim the corpus held one policy where it held two
 *  copies of one. They are counted apart here and worded apart above.
 */
export interface RuleSlicingReading {
  slicedCount: number;
  threshold: number | null;
  ruleBudget: number | null;
  overPayloadBudget: number;
  payloadBudgetChars: number | null;
  policies: SlicedPolicyReading[];
  /** Exact policy copies, collapsed into a representative that was read. */
  duplicateCollapsed: number;
  duplicatePolicies: DuplicatePolicyReading[];
  /** Distinct policies deferred behind one requiring the same thing. Never a
   *  duplicate count, and never added to one. */
  diversityDeferred: number;
  /** How the retained set was ordered, in the server's own vocabulary. */
  selectionOrder: string | null;
  /** Exact rule copies inside sliced policies that were represented by a rule
   *  that was read, and were not themselves read. */
  duplicateRulesCollapsed: number;
  /** What the search actually matched, and under which corpus projection.
   *
   *  Null when the reply said nothing about any of it — an older server, or a
   *  scope that consulted no index. Never a row of zeroes standing in for
   *  silence: "the rule index placed none" and "there was no rule index in this
   *  answer" are different facts. */
  discovery: DiscoveryReading | null;
}

/** What the discovery search matched, and whether it could be matched at all. */
export interface DiscoveryReading {
  policyDocuments: number | null;
  ruleDocuments: number | null;
  ruleScan: number | null;
  /** Policies whose ranking was raised by one of their own rules surfacing.
   *  The count that says whether rule-level retrieval did anything here: a rule
   *  beyond what its policy's own document could carry is reachable only so. */
  elevatedByRule: number | null;
  ruleIndexState: string | null;
  projectionProfile: string | null;
  /** Only ever true on a served answer — a project whose projection is absent,
   *  superseded or half-written is refused rather than answered. */
  projectionReady: boolean | null;
}

function judgementFromFlat(evaluation: ProjectCaseEvaluation): ProjectCaseJudgement | null {
  if (!evaluation.status) return null;
  return {
    status: evaluation.status,
    verdict: evaluation.verdict,
    answer: evaluation.answer,
    missing_required_facts: evaluation.missing_required_facts,
    citations: evaluation.citations,
    note: evaluation.note,
    grounding: evaluation.grounding,
  };
}

function sectionFor(track: CaseTrack, evaluation: ProjectCaseEvaluation): ProjectCaseJudgement | null {
  if (track === "information") return evaluation.informational ?? null;
  // The oldest replies carried the determination as `judgement`, or flattened
  // onto the evaluation itself. Both are the verdict track under another name —
  // but only on a reply that was read as a determination. Reading a flattened
  // informational answer as a verdict would manufacture one out of a reply that
  // never claimed to have reached anything.
  if (evaluation.decision) return evaluation.decision;
  if (evaluation.judgement) return evaluation.judgement;
  if (evaluation.intent === "decision" || evaluation.verdict_requested === true) {
    return judgementFromFlat(evaluation);
  }
  return null;
}

function trackReading(
  track: CaseTrack,
  {
    requested,
    section,
    evaluated,
  }: { requested: boolean; section: ProjectCaseJudgement | null; evaluated: boolean },
): CaseTrackReading {
  const closed: readonly string[] = track === "information" ? INFORMATION_STATUSES : VERDICT_STATUSES;
  if (!evaluated) {
    return { track, requested: false, ran: false, outcome: NOT_EVALUATED, known: true, answered: false, section: null };
  }
  if (section) {
    const outcome = section.status?.trim() || NO_SECTION;
    return {
      track,
      requested: true,
      ran: true,
      outcome,
      known: closed.includes(outcome),
      answered: outcome === STATUS_WITH_ANSWER,
      section,
    };
  }
  if (requested) {
    // Asked for, and nothing came back for it. Reported as its own state: the
    // alternative is choosing a gather outcome on the server's behalf, which
    // would put words in the policies' mouths.
    return { track, requested: true, ran: false, outcome: NO_SECTION, known: false, answered: false, section: null };
  }
  return { track, requested: false, ran: false, outcome: NOT_REQUESTED, known: true, answered: false, section: null };
}

function mergeCitations(sections: readonly (ProjectCaseJudgement | null)[]): MergedCaseCitation[] {
  const merged = new Map<string, MergedCaseCitation>();
  const order: CaseTrack[] = ["information", "verdict"];
  sections.forEach((section, index) => {
    const track = order[index];
    for (const citation of section?.citations ?? []) {
      if (!citation?.rule_id) continue;
      // A citation that already carries its own tags — a merged list from a
      // receipt rather than a per-track one — is believed rather than retagged.
      const serves = citation.serves?.length ? citation.serves : [track];
      const existing = merged.get(citation.rule_id);
      if (!existing) {
        merged.set(citation.rule_id, { ...citation, serves: [...serves] });
        continue;
      }
      for (const tag of serves) {
        if (!existing.serves.includes(tag)) existing.serves.push(tag);
      }
      // The first sighting keeps its source; a second is the same rule, and the
      // verbatim sentence a rule rests on does not change with who cited it.
      if (!existing.source?.text && citation.source?.text) existing.source = citation.source;
      if (!existing.policy && citation.policy) existing.policy = citation.policy;
    }
  });
  return [...merged.values()];
}

/**
 * Read one project case answer as its two tracks.
 *
 * `evaluated` is false exactly when the reply carried no evaluation at all,
 * which is what retrieval producing nothing looks like from here. Both tracks
 * then report `not_evaluated`, and nothing in the reading claims a gather ran.
 */
export function readCaseTracks(answer: ProjectCaseAnswer): CaseTracksReading {
  const evaluation = answer.evaluation;
  const evaluated = Boolean(evaluation);
  const informationSection = evaluation ? sectionFor("information", evaluation) : null;
  const verdictSection = evaluation ? sectionFor("verdict", evaluation) : null;

  const declared =
    typeof evaluation?.information_requested === "boolean" ||
    typeof evaluation?.verdict_requested === "boolean";

  // A section that exists was gathered, so the track was asked for whatever the
  // booleans say. Where they are absent, the older exclusive `intent` is the
  // only reading available and is used as exactly that — one track, not two.
  const informationRequested =
    Boolean(informationSection) ||
    (declared
      ? evaluation?.information_requested === true
      : evaluated && evaluation?.intent !== "decision");
  const verdictRequested =
    Boolean(verdictSection) ||
    (declared ? evaluation?.verdict_requested === true : evaluated && evaluation?.intent === "decision");

  const information = trackReading("information", {
    requested: informationRequested,
    section: informationSection,
    evaluated,
  });
  const verdict = trackReading("verdict", {
    requested: verdictRequested,
    section: verdictSection,
    evaluated,
  });

  const citations = mergeCitations([informationSection, verdictSection]);
  const waitedOn = (verdictSection?.missing_information ?? []).flatMap(
    (item) => item.required_by_rule_ids ?? [],
  );
  // A rule that imposes a check before acting bore on the case as surely as one
  // that blocked it, so it belongs in the evidence set a reviewer can open.
  const qualifiedBy = verificationRequirementItems(verdictSection).flatMap(
    (item) => item.requiredByRuleIds,
  );

  return {
    evaluated,
    asked: {
      information: information.requested,
      verdict: verdict.requested,
      declared,
      reasoning: evaluation?.classification_reasoning?.trim() ?? "",
      classifierVersion: evaluation?.classifier_version ?? null,
    },
    information,
    verdict,
    citations,
    ruleIds: [...new Set([...citations.map((citation) => citation.rule_id), ...waitedOn, ...qualifiedBy].filter(Boolean))],
  };
}

/** The prose a track composed, whichever field carried it.
 *
 *  An answered information track puts its substance in `answer`; one that stood
 *  back explains itself in `explanation` and leaves `answer` empty, so a client
 *  cannot render a non-answer as an answer. The verdict track's reasoning has
 *  always arrived as `answer` on this endpoint and as `explanation` on the
 *  receipt; both are read, and neither is duplicated. */
export function trackProse(section: ProjectCaseJudgement | null): string {
  if (!section) return "";
  const answer = section.answer?.trim() ?? "";
  if (answer) return answer;
  return section.explanation?.trim() ?? "";
}

/** The facts a verdict is waiting on, structured when the gather structured
 *  them and reconstructed from the flat labels when it did not.
 *
 *  The flat list is never dropped in favour of the structured one: an older
 *  reply carries only the flat list, and a reviewer owed "which facts" must not
 *  be shown an empty panel because the richer field was absent. */
export function missingInformationItems(section: ProjectCaseJudgement | null) {
  if (!section) return [];
  const structured = section.missing_information ?? [];
  if (structured.length > 0) {
    return structured.map((item) => ({
      fact: item.fact,
      label: (item.label ?? "").trim() || item.fact,
      whyNeeded: (item.why_needed ?? "").trim(),
      requiredByRuleIds: item.required_by_rule_ids ?? [],
    }));
  }
  return (section.missing_required_facts ?? [])
    .filter(Boolean)
    .map((fact) => ({ fact, label: fact, whyNeeded: "", requiredByRuleIds: [] as string[] }));
}

/** The conditions to confirm before acting on a verdict that was reached.
 *
 *  Read exactly as the missing facts are read, with two deliberate differences.
 *  There is no flat-list fallback, because there is no older flat field to fall
 *  back to. And nothing is returned unless the verdict was actually reached: a
 *  condition on *acting* on a determination is meaningless where there is none,
 *  so a reply that carried one on a blocked section is ignored rather than
 *  rendered beside the facts that block it. */
export function verificationRequirementItems(section: ProjectCaseJudgement | null) {
  if (!section) return [];
  if ((section.status ?? "").trim().toLowerCase() !== "answered") return [];
  return (section.verification_requirements ?? [])
    .filter((item) => Boolean((item.fact ?? "").trim() || (item.label ?? "").trim()))
    .map((item) => ({
      fact: item.fact,
      label: (item.label ?? "").trim() || item.fact,
      whyNeeded: (item.why_needed ?? "").trim(),
      requiredByRuleIds: item.required_by_rule_ids ?? [],
    }));
}

/** The discard reason a policy carries when an identical policy was read in its
 *  place. The only discard whose terms still reached the gather. */
export const DISCARD_DUPLICATE_POLICY_CONTENT = "duplicate_policy_content";

/**
 * The narrowing that happened to the policies search kept.
 *
 * Returns `null` when there is nothing to disclose, so the interface adds a
 * paragraph only when it has something to say. Every count is trusted from the
 * retrieval block when it is there and derived from the per-policy entries when
 * it is not, because the two must never disagree and the per-policy entries are
 * the evidence. A reply from a server that reports none of these fields — an
 * older v2, or a v1 replay — produces the same `null` it always did.
 */
export function readRuleSlicing(answer: ProjectCaseAnswer): RuleSlicingReading | null {
  const candidates =
    answer.scope === "single" && answer.provision ? [answer.provision] : (answer.considered ?? []);
  const policies: SlicedPolicyReading[] = candidates.flatMap((policy) => {
    const selection = policy.rule_selection;
    if (!selection) return [];
    const sliced =
      selection.sliced === true ||
      (typeof selection.selected_rules === "number" &&
        typeof selection.total_rules === "number" &&
        selection.selected_rules < selection.total_rules);
    return sliced ? [{ policy, selection }] : [];
  });

  // Only a policy that names its representative is reported as a collapsed
  // copy. The claim being made is "its terms were read, over there", and a
  // claim with nowhere to point is one a reader cannot check.
  const duplicatePolicies: DuplicatePolicyReading[] = candidates.flatMap((policy) => {
    const representative = policy.duplicate_of_provision_key;
    if (!representative) return [];
    if (policy.discard_reason && policy.discard_reason !== DISCARD_DUPLICATE_POLICY_CONTENT) return [];
    return [{ policy, representative }];
  });

  const retrieval = answer.retrieval;
  const slicedCount =
    typeof retrieval.policies_rule_sliced === "number" ? retrieval.policies_rule_sliced : policies.length;
  const overPayloadBudget =
    typeof retrieval.policies_over_payload_budget === "number"
      ? retrieval.policies_over_payload_budget
      : candidates.filter((policy) => policy.discard_reason === "outside_payload_budget").length;
  const duplicateCollapsed =
    typeof retrieval.policies_duplicate_collapsed === "number"
      ? retrieval.policies_duplicate_collapsed
      : duplicatePolicies.length;
  // Never derived from anything: a deferred policy carries the ordinary
  // `outside_budget` reason and is indistinguishable from a relevance discard
  // in the candidate list. Inferring it would mean inventing the finding.
  const diversityDeferred =
    typeof retrieval.policies_diversity_deferred === "number" ? retrieval.policies_diversity_deferred : 0;
  const duplicateRulesCollapsed = policies.reduce(
    (total, entry) => total + (entry.selection.duplicate_rules_collapsed ?? 0),
    0,
  );
  const discovery = readDiscovery(retrieval);

  const nothingToDisclose =
    slicedCount === 0 &&
    policies.length === 0 &&
    overPayloadBudget === 0 &&
    duplicateCollapsed === 0 &&
    duplicatePolicies.length === 0 &&
    diversityDeferred === 0 &&
    discovery === null;
  if (nothingToDisclose) return null;

  return {
    slicedCount,
    threshold: retrieval.large_policy_rule_threshold ?? null,
    ruleBudget: retrieval.selected_rule_budget ?? null,
    overPayloadBudget,
    payloadBudgetChars: retrieval.payload_budget_chars ?? null,
    policies,
    duplicateCollapsed,
    duplicatePolicies,
    diversityDeferred,
    selectionOrder: retrieval.policy_selection_order ?? null,
    duplicateRulesCollapsed,
    discovery,
  };
}

/** What the discovery search matched, or `null` when the reply said nothing.
 *
 *  Read apart from the counts above because it answers a different question:
 *  not "how was the retained set narrowed" but "what was searched, and could it
 *  be searched at all". A reply that carries none of these fields — an older
 *  server, or the single-policy scope that consults no index — produces `null`
 *  rather than zeroes, because a zero here is a claim about a search that ran.
 */
export function readDiscovery(retrieval: ProjectCaseAnswer["retrieval"]): DiscoveryReading | null {
  const numeric = (value: unknown): number | null => (typeof value === "number" ? value : null);
  const reading: DiscoveryReading = {
    policyDocuments: numeric(retrieval.policy_documents_matched),
    ruleDocuments: numeric(retrieval.rule_documents_matched),
    ruleScan: numeric(retrieval.rule_scan),
    elevatedByRule: numeric(retrieval.policies_elevated_by_rule),
    ruleIndexState: retrieval.rule_index_state ?? null,
    projectionProfile: retrieval.projection_profile ?? null,
    projectionReady: typeof retrieval.projection_ready === "boolean" ? retrieval.projection_ready : null,
  };
  const said =
    reading.policyDocuments !== null ||
    reading.ruleDocuments !== null ||
    reading.ruleScan !== null ||
    reading.elevatedByRule !== null ||
    reading.ruleIndexState !== null ||
    reading.projectionProfile !== null ||
    reading.projectionReady !== null;
  return said ? reading : null;
}

/** The exact rule copies one policy's selection stood in for, if any.
 *
 *  Separated from the selection itself because the sentence a reader needs is
 *  not "66 rules were not read" but "of those, these N say exactly what a rule
 *  that was read says". Neither number may be presented as the other, and
 *  neither may be presented as a rule having been read. */
export function representedRuleIds(selection: ProjectCaseRuleSelection | null | undefined): string[] {
  return selection?.represented_rule_ids ?? [];
}

/** How a large policy's rules were chosen, as a family rather than a version.
 *
 *  The contract is explicit that the version suffix on a selection method moves
 *  when the algorithm changes, so a stored receipt names the algorithm that
 *  produced it. A client that pinned the literal it was written against would
 *  therefore go quietly wrong on the next change — not by crashing, but by
 *  falling through to a raw-identifier label, which is the failure that reads
 *  as working. So the version is stripped and the family is matched.
 *
 *  Only a `_v<digits>` suffix is stripped, and only the three known families
 *  are returned. A method this client has never heard of comes back `null` and
 *  is shown as itself: inventing a family for it would be guessing at what an
 *  unknown algorithm did, which is worse than saying its name. */
export function ruleSelectionMethodFamily(method: string | null | undefined): string | null {
  const named = (method ?? "").trim();
  if (!named) return null;
  const family = named.replace(/_v\d+$/, "");
  return RULE_SELECTION_METHOD_FAMILIES.includes(family) ? family : null;
}

/** The selection methods this client can describe, without their versions.
 *
 *  `hybrid_rule` is the rule index taking part: a rule's own search rank, a
 *  relevance rank over the English projection, and a quantity-compatibility
 *  rank fused together. `scenario_relevance` is the same selection run without
 *  the index's ranking — either because the index was never consulted, or
 *  because it was and the query against it failed recoverably. Told apart
 *  because "the index placed these rules" and "the index was not able to" are
 *  different accounts of the same list. */
export const RULE_SELECTION_METHOD_FAMILIES: readonly string[] = [
  "whole_policy",
  "hybrid_rule",
  "scenario_relevance",
  "document_order",
];

/** Whether the rule index took part in a selection, per policy or per retrieval.
 *
 *  `matched` — queried, and its ranking fused with the others.
 *  `degraded` — rule documents exist, and the query against them failed
 *  recoverably, so the selection ran without that ranking.
 *  `unavailable` — it was not consulted at all.
 *
 *  Zero hits under `matched` is a real answer: the index was asked and placed
 *  none of this policy's rules. It is not `unavailable`, where it was never
 *  asked, and a surface that showed both as "0" would be reporting a question
 *  that was never put as one that came back empty. */
export const RULE_INDEX_STATES: readonly string[] = ["matched", "degraded", "unavailable"];

/** How the rule index and the ranks beside it placed one policy's rules.
 *
 *  Null when the server said nothing about any of it — an older reply, or a
 *  selection that predates rule-level retrieval. Zero is never substituted for
 *  silence: `0 hits` is a claim, and absence is not.
 */
export interface RuleIndexReading {
  state: string | null;
  known: boolean;
  hits: number | null;
  lexical: number | null;
  quantity: number | null;
  fused: number | null;
  evidenceQuota: number | null;
  withoutProjection: number | null;
}

export function readRuleIndex(
  selection: ProjectCaseRuleSelection | null | undefined,
): RuleIndexReading | null {
  if (!selection) return null;
  const state = selection.rule_index_state ?? null;
  const numbers = [
    selection.rule_index_hits,
    selection.lexical_candidates,
    selection.quantity_candidates,
    selection.fused_candidates,
    selection.evidence_diversity_quota,
    selection.rules_without_projection,
  ];
  if (state === null && numbers.every((value) => typeof value !== "number")) return null;
  return {
    state,
    known: state !== null && RULE_INDEX_STATES.includes(state),
    hits: typeof selection.rule_index_hits === "number" ? selection.rule_index_hits : null,
    lexical: typeof selection.lexical_candidates === "number" ? selection.lexical_candidates : null,
    quantity: typeof selection.quantity_candidates === "number" ? selection.quantity_candidates : null,
    fused: typeof selection.fused_candidates === "number" ? selection.fused_candidates : null,
    evidenceQuota:
      typeof selection.evidence_diversity_quota === "number" ? selection.evidence_diversity_quota : null,
    withoutProjection:
      typeof selection.rules_without_projection === "number" ? selection.rules_without_projection : null,
  };
}

/** What the language boundary did to one case, if it reported anything.
 *
 *  `rendered` is the state that matters to a reader: the question they typed is
 *  not the text that was adjudicated, and the two are worth comparing. Every
 *  other state means the words on screen are the words that were read.
 *
 *  Nothing here touches the evidence. A document's own sentence is never
 *  translated, in any state, so a citation's `source.text` is the document's
 *  and the interface says so wherever a rendering happened.
 */
export interface LanguageReading {
  reported: boolean;
  /** The question was carried into the processing language before it was read. */
  questionRendered: boolean;
  /** The answer's prose was carried back to the caller's language. */
  answerRendered: boolean;
  /** The caller's guidance could not be carried across and was dropped. */
  guidanceDropped: boolean;
  sourceLanguage: string | null;
  processingLanguage: string | null;
  responseLanguage: string | null;
  /** The text every stage of the decision actually read. Only worth showing
   *  when it is not what the reader typed. */
  processingScenario: string | null;
  inputProfile: string | null;
  outputProfile: string | null;
  projectionProfile: string | null;
}

export function readLanguage(answer: ProjectCaseAnswer): LanguageReading | null {
  const language = answer.language;
  if (!language) return null;
  return {
    reported: true,
    questionRendered: language.boundary_state === "rendered",
    answerRendered: language.output_rendering_state === "rendered",
    guidanceDropped: language.guidance_rendering_state === "unrendered_dropped",
    sourceLanguage: language.source_language ?? null,
    processingLanguage: language.processing_language ?? null,
    responseLanguage: language.response_language ?? null,
    processingScenario: language.processing_scenario?.trim() || null,
    inputProfile: language.input_translation_profile ?? null,
    outputProfile: language.output_translation_profile ?? null,
    projectionProfile: language.projection_profile ?? null,
  };
}
