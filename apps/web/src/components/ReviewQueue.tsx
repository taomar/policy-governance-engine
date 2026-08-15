import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  App,
  Button,
  Checkbox,
  Col,
  DatePicker,
  Drawer,
  Empty,
  Form,
  Grid,
  Input,
  InputNumber,
  Modal,
  Pagination,
  Progress,
  Row,
  Segmented,
  Select,
  Space,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import {
  BulbOutlined,
  ClusterOutlined,
  EditOutlined,
  ExclamationCircleOutlined,
  FileSearchOutlined,
  HistoryOutlined,
  LayoutOutlined,
  LeftOutlined,
  PlusOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
  SendOutlined,
  ThunderboltOutlined,
  UnorderedListOutlined,
} from "@ant-design/icons";
import dayjs from "dayjs";
import {
  aiApi,
  api,
  type ApprovedPolicyVersion,
  type AssembledPolicy,
  type CandidateRule,
  type CanonicalRule,
  type PolicySet,
  type PolicyTestListItem,
  policyTestApi,
  type ReviewFacets,
  type PolicyScope,
  type QualityFinding,
} from "../api";
import { RewriteModal } from "./RewriteModal";
import { EditRuleModal } from "./EditRuleModal";
import { ManagerActionModal } from "./ManagerActionModal";
import { AskAboutRuleModal } from "./AskAboutRuleModal";
import { AiRuleComposer } from "./AiRuleComposer";
import { ImmutableFieldsNotice } from "./ImmutableFieldsNotice";
import { ExportMenu } from "./ExportMenu";
import { ScopeFieldsEditor } from "./ScopeEditor";
import { EMPTY_SCOPE, normalizeScope } from "../scopeUtils";
import { candidateEditability } from "../candidateEditability";
import { buildVariationClusters, clusterColor, clusterIdentity } from "../ruleDisplay";
import { computeBandGeometry } from "../bandGeometry";
import { buildPolicyCards, policyTitle, unplacedRules, type PolicyCard } from "../policyCards";
import { recordScaleLabel } from "../policyRecordFacts";
import { type LoadState, describeApiFailure } from "../loadState";
import { qualityScanSummary } from "../qualityScanSummary";
import { familyGaps, familyMembers, idsCoveringFamilies, type FamilyGap } from "../ruleFamilyReview";
import { FamilyReviewConfirm } from "./FamilyReviewConfirm";
import {
  buildCondition,
  conditionToRows,
  isVacuousCondition,
  CONDITION_OPERATORS,
  type ConditionRow,
} from "../conditionRows";
import { machineExecutableFor } from "../ruleExecutability";
import { reviewQueueIsEmpty } from "../reviewQueueEmptiness";
import {
  candidateAnswersSearch,
  cardsAnsweringSearch,
  matchedCandidateIds,
  placeableCandidates,
} from "../queueCardSelection";
import {
  candidateAnswersRuleFilters,
  candidateIdsAnsweringRuleFilters,
  cardsAnsweringRuleFilters,
  filterIsOff,
  policySelectionNote,
} from "../queueCardFilters";
import { useActor } from "../ActorContext";
import { usePolicyTesting } from "./policyTesting";
import { RULE_TYPES } from "../ruleTypes";
import { CandidateRow } from "./CandidateRow";
import { FamilyCompositeHeader } from "./FamilyCompositeHeader";
import { PolicyReviewCard } from "./PolicyReviewCard";
import { PolicyDetailPanel } from "./PolicyDetailPanel";
import { listProvisionHistory } from "../publishedPolicyCards";
import type { PolicySightingView } from "./policyTabPanes";
import type { RecordActionHandlers } from "./RecordActionsMenu";
import { ReviewFilterBar, DELTA_META } from "./ReviewFilterBar";
import { ReviewStatusTabs, REVIEW_STATUS_TABS } from "./ReviewStatusTabs";
import { RuleChangeExplainer } from "./RuleChangeExplainer";
import { PolicyInspector } from "./PolicyInspector";
import { RuleDetailInline } from "./RuleDetailInline";

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;
type ReviewWorkspaceMode = "list" | "split" | "detail";

const STATUS_FILTERS = ["all", "candidate", "changes_requested", "approved", "rejected", "published"] as const;

const STATUS_COLOR: Record<string, string> = {
  candidate: "blue",
  changes_requested: "orange",
  approved: "green",
  rejected: "red",
  published: "purple",
};

const STATUS_LABEL: Record<string, string> = {
  all: "All",
  candidate: "Candidate",
  changes_requested: "Changes requested",
  approved: "Approved",
  rejected: "Rejected",
  published: "Published",
};

const OPERATORS = CONDITION_OPERATORS;

export function ReviewQueue({ policySetKey }: { policySetKey?: string } = {}) {
  const screens = Grid.useBreakpoint();
  const isDesktop = !!screens.lg;
  const scoped = Boolean(policySetKey);
  const { actor } = useActor();
  const { message } = App.useApp();
  const [policySets, setPolicySets] = useState<PolicySet[]>([]);
  const [selectedKey, setSelectedKey] = useState<string>(policySetKey ?? "");
  const [candidates, setCandidates] = useState<CandidateRule[]>([]);
  /** The same rules arranged under the passage that stated them. Fetched
   *  alongside the flat list and joined to it by rule id. */
  const [policies, setPolicies] = useState<AssembledPolicy[]>([]);
  /** Whether we have the passage grouping at all. A failed fetch used to be
   *  caught into an empty array, which the queue then rendered as "this policy
   *  set has no passages" — a claim about the document made out of a network
   *  failure. */
  const [policiesState, setPoliciesState] = useState<LoadState>("loading");
  const [policiesError, setPoliciesError] = useState<string | null>(null);
  const [previousUnderReview, setPreviousUnderReview] = useState<CandidateRule | null>(null);
  const [previousTab, setPreviousTab] = useState("overview");
  const [statusFilter, setStatusFilter] = useState<(typeof STATUS_FILTERS)[number]>("all");
  /** Filters that narrow the queue to what a reviewer is actually working on:
   *  one document, one extraction run, or one kind of change. Held server-side
   *  rather than filtering the loaded array, because the queue can run to
   *  hundreds of rules and the point of a delta is to not ship them all. */
  const [documentFilter, setDocumentFilter] = useState<string>("");
  const [runFilter, setRunFilter] = useState<string>("");
  const [deltaFilter, setDeltaFilter] = useState<string>("all");
  const [facets, setFacets] = useState<ReviewFacets | null>(null);
  const [showRemoved, setShowRemoved] = useState(false);
  const [searchText, setSearchText] = useState("");
  /**
   * Every test in this policy set, loaded once for the page.
   *
   * Kept at page scope rather than per policy for the reason the Tests tab
   * exists to respect: a policy's tests are those aimed at rules it holds, and
   * that question is answered from the card already on screen. Asking a server
   * for one policy's tests would make it re-derive the grouping, and a second
   * opinion on grouping is free to disagree with the one the reviewer is
   * looking at.
   *
   * `null` until something is known, so "not loaded" and "this set has no
   * tests" stay different answers.
   */
  const [policySetTests, setPolicySetTests] = useState<PolicyTestListItem[] | null>(null);
  const [policySetTestsLoading, setPolicySetTestsLoading] = useState(false);
  /** One policy's published sightings, by provision key, fetched when its
   *  History tab is opened. A policy under review may already have published
   *  versions under the same key, and this is where the reviewer sees them. */
  const [policyHistory, setPolicyHistory] = useState<Record<string, PolicySightingView[]>>({});
  const [policyHistoryLoading, setPolicyHistoryLoading] = useState<ReadonlySet<string>>(new Set());
  const [effectiveFrom, setEffectiveFrom] = useState(() => new Date().toISOString().slice(0, 10));
  const [publishResult, setPublishResult] = useState<ApprovedPolicyVersion | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showDraftForm, setShowDraftForm] = useState(false);
  const [advancedMode, setAdvancedMode] = useState(false);
  const [rewriteTarget, setRewriteTarget] = useState<CandidateRule | null>(null);
  const [editTarget, setEditTarget] = useState<CandidateRule | null>(null);
  const [managerAction, setManagerAction] = useState<{ candidate: CandidateRule; mode: "request-changes" | "override-approve" | "override-reject" } | null>(null);
  const [askTarget, setAskTarget] = useState<CandidateRule | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  /** A review the user asked for that would leave part of a rule family behind,
   *  held until they say how to resolve the split. */
  const [familyPrompt, setFamilyPrompt] = useState<{
    ids: string[];
    decision: "approve" | "reject";
    gaps: FamilyGap[];
  } | null>(null);

  // The queue and inspector are peers, matching the published Policies
  // workspace. Only one candidate detail mounts at a time, so source resolution
  // and discussion fetches stay constant even when the queue has hundreds of rows.
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);
  /** The passage open in the detail panel. The panel shows the policy; setting
   *  `selectedCandidateId` as well drills into one of its rules in place. */
  const [openPolicyKey, setOpenPolicyKey] = useState<string | null>(null);
  const [workspaceMode, setWorkspaceMode] = useState<ReviewWorkspaceMode>("split");
  const [inspectorTab, setInspectorTab] = useState("overview");
  const [inspectorFullscreen, setInspectorFullscreen] = useState(false);
  const [mobileInspectorOpen, setMobileInspectorOpen] = useState(false);
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 20;

  // Readiness/quality findings — lazy-loaded on demand (triggers a real AI call),
  // grouped client-side by affected rule_id so each candidate can show a small badge.
  const [qualityFindings, setQualityFindings] = useState<Map<string, QualityFinding[]> | null>(null);
  const [qualityLoading, setQualityLoading] = useState(false);
  const [qualityError, setQualityError] = useState<string | null>(null);
  /**
   * That the last scan failed, held apart from the message saying so.
   *
   * The message is shown in an Alert the reviewer can close, and closing it
   * clears `qualityError`. When the summary strip read the error directly, a
   * dismissed Alert took the failure with it and the strip went back to
   * claiming no scan had ever been run — the reviewer had asked for one,
   * watched it fail, closed the notice, and was then told it never happened.
   * Dismissing a message may silence the message; it may not rewrite what
   * took place.
   */
  const [qualityFailed, setQualityFailed] = useState(false);

  // Active-version rules — fetched to compute a pre-publish diff summary
  // (net-new / superseding / carried-forward-unchanged) before the manager commits.
  const [activeVersionRules, setActiveVersionRules] = useState<CanonicalRule[] | null>(null);

  // structured draft form state
  const [ruleId, setRuleId] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [ruleType, setRuleType] = useState("approval_requirement");
  const [effectType, setEffectType] = useState<"allow" | "deny" | "require_action" | "informational">("require_action");
  const [effectAction, setEffectAction] = useState("");
  const [authorityOwner, setAuthorityOwner] = useState("");
  const [authorityLevel, setAuthorityLevel] = useState("corporate");
  const [authorityRank, setAuthorityRank] = useState(10);
  const [priority, setPriority] = useState(0);
  const [draftEffectiveFrom, setDraftEffectiveFrom] = useState(() => new Date().toISOString().slice(0, 10));
  const [conditionRows, setConditionRows] = useState<ConditionRow[]>([{ fact: "", operator: "greaterThan", value: "" }]);
  const [draftScope, setDraftScope] = useState<PolicyScope>(EMPTY_SCOPE);
  const [draftIsExplicitOverride, setDraftIsExplicitOverride] = useState(false);
  const [draftSupersedesRuleIds, setDraftSupersedesRuleIds] = useState<string[]>([]);
  const [draftGroupLabel, setDraftGroupLabel] = useState("");
  const [draftRelatedRuleIds, setDraftRelatedRuleIds] = useState<string[]>([]);
  const [advancedJson, setAdvancedJson] = useState("{}");
  const [draftError, setDraftError] = useState<string | null>(null);
  // The rule the composer produced, kept whole. `handleDraft` submits the form
  // fields *over* this object rather than rebuilding from scratch, so the
  // agent's formulation record, lineage and ambiguity status survive the round
  // trip instead of being silently dropped by the form.
  const [aiGeneratedRule, setAiGeneratedRule] = useState<CanonicalRule | null>(null);
  const [loadedAiRuleId, setLoadedAiRuleId] = useState<string | null>(null);

  useEffect(() => {
    if (scoped) return; // scope is fixed by the embedding project; no picker/list needed
    api
      .listPolicySets()
      .then((sets) => {
        setPolicySets(sets);
        if (sets.length > 0) setSelectedKey(sets[0].key);
      })
      .catch((e) => setError(describeApiFailure(e)));
  }, [scoped]);

  // "Who is doing this" has exactly one home: the actor identity in the header.
  //
  // It used to have three — `actor.name`, a local `reviewer` field, and a local
  // `publishedBy` field — kept in step by a one-way, fill-the-blanks effect that
  // only ran when the actor already had a name. So a user who typed their name
  // into the visible, red-asterisked "Approved by" box at the bottom of the page
  // had, as far as the rest of the app was concerned, still not said who they
  // were: approving a rule failed with "Enter a reviewer name" while their name
  // sat on screen a few hundred pixels below the button.
  //
  // Removing both local fields eliminates that class of bug instead of adding
  // another sync: identity is entered once in the header, applies everywhere,
  // and persists across reloads. `actor.role` still carries the
  // reviewer-vs-manager distinction, which is the part that genuinely differs.
  const identity = actor.name;

  const loadCandidates = async () => {
    if (!selectedKey) return;
    setError(null);
    setLoading(true);
    try {
      // Review status and delta status are NOT sent to the server.
      //
      // They are properties of a rule, and asking the server for "the pending
      // rules" returns rules, not policies — so every card assembled from the
      // answer holds only the part of its policy that matched, while still
      // offering one `Approve policy` over it. The queue's unit is the policy,
      // so the population it loads has to be whole policies too.
      //
      // Document and run stay server-side: they are scope, not a filter within
      // a policy. A policy belongs to one document, so scoping to a document
      // never splits one — and the assembly call below is given the same scope,
      // so the two answers describe the same population.
      const scope = {
        document_id: documentFilter || undefined,
        extraction_run_id: runFilter || undefined,
      };
      // The flat list is what a reviewer edits; the assembly says which rules
      // came from the same passage. One population, two arrangements, fetched
      // together so the rule ids in the second index into the first.
      //
      // The assembly is what the queue is arranged by, so losing it is not
      // nothing — but it is also not an empty document set. The failure is
      // carried as its own state and said out loud, and the rows still render
      // ungrouped underneath it.
      setPoliciesState("loading");
      setPoliciesError(null);
      const [list, assembled] = await Promise.all([
        api.listCandidateRules(selectedKey, undefined, {
          ...scope,
          // Opening a historical run means asking for rules a later run retired,
          // so those rows have to be included or the run would look empty.
          include_superseded: Boolean(runFilter),
        }),
        api
          .listPolicies(selectedKey, scope)
          .then((result) => ({ ok: true as const, result }))
          .catch((e) => ({ ok: false as const, detail: describeApiFailure(e) })),
      ]);
      setCandidates(list);
      if (assembled.ok) {
        setPolicies(assembled.result);
        setPoliciesState("ready");
      } else {
        setPolicies([]);
        setPoliciesState("unavailable");
        setPoliciesError(assembled.detail);
      }
    } catch (e) {
      setError(describeApiFailure(e));
    } finally {
      setLoading(false);
    }
  };

  const loadFacets = async () => {
    if (!selectedKey) return;
    try {
      setFacets(await api.reviewFacets(selectedKey));
    } catch {
      setFacets(null); // filters degrade to "no options", the queue itself still works
    }
  };

  // Only the filters that change which records are fetched trigger a reload.
  // Status and delta now narrow the assembled cards in place, so refetching on
  // them would spend a round-trip to receive the same payload — and clear the
  // reviewer's selection and page while doing it.
  useEffect(() => {
    void loadCandidates();
    setQualityFindings(null); // stale once the policy set/filter changes — re-run on demand
    setQualityFailed(false); // a failure belonged to the set that was scanned, not to this one
    setQualityError(null);
    setSelectedCandidateId(null);
    setInspectorFullscreen(false);
    setPage(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedKey, documentFilter, runFilter]);

  // Narrowing by status or delta changes which cards are shown but not which
  // are loaded, so it only has to return to the first page. The selection is
  // kept: a reviewer who has a rule open and then narrows the queue has not
  // asked to stop looking at it.
  useEffect(() => {
    setPage(1);
  }, [statusFilter, deltaFilter]);

  const requestPolicyHistory = useCallback(
    (provisionKey: string) => {
      if (!selectedKey || !provisionKey) return;
      setPolicyHistoryLoading((current) => {
        if (current.has(provisionKey)) return current;
        const next = new Set(current);
        next.add(provisionKey);
        return next;
      });
      listProvisionHistory(selectedKey, provisionKey)
        .then((sightings) => {
          setPolicyHistory((current) => ({ ...current, [provisionKey]: sightings }));
        })
        .catch(() => {
          // Absent, not empty. The pane draws a different sentence for each and
          // a failed request has established neither.
        })
        .finally(() => {
          setPolicyHistoryLoading((current) => {
            if (!current.has(provisionKey)) return current;
            const next = new Set(current);
            next.delete(provisionKey);
            return next;
          });
        });
    },
    [selectedKey],
  );

  /**
   * Re-read the set's tests.
   *
   * A failure leaves them unknown rather than empty: an empty list would tell
   * the reviewer this set has no tests, which is a claim about coverage rather
   * than an admission that the answer did not arrive.
   *
   * Separate from the set-switch effect so writing or running a test can
   * re-read them without also resetting the reviewer's filters.
   */
  const reloadPolicySetTests = useCallback(async () => {
    setPolicySetTestsLoading(true);
    try {
      setPolicySetTests(await policyTestApi.list(selectedKey));
    } catch {
      setPolicySetTests(null);
    } finally {
      setPolicySetTestsLoading(false);
    }
  }, [selectedKey]);

  /**
   * The Tests tab's verbs, on a candidate.
   *
   * Not gated on the policy being editable. Writing a test does not change the
   * policy; it writes a question *about* it. The same verbs are offered on the
   * published surface for the same reason, so there is no branch here to keep
   * in step with one over there.
   */
  const policyTesting = usePolicyTesting({
    policySetKey: selectedKey,
    policyVersionId: null,
    actor: actor.name,
    onChanged: useCallback(() => {
      void reloadPolicySetTests();
    }, [reloadPolicySetTests]),
  });

  useEffect(() => {
    void loadFacets();
    void reloadPolicySetTests();
    // Filters are scoped to the policy set; carrying a document or run selection
    // across a switch would silently filter the new set to nothing.
    setDocumentFilter("");
    setRunFilter("");
    setDeltaFilter("all");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedKey]);

  // Load the current active version's rules once per policy set, purely to compute the
  // pre-publish diff summary below — a plain deterministic DB read, safe to fetch eagerly
  // (unlike the AI-backed quality check, which stays behind a manual trigger).
  useEffect(() => {
    setActiveVersionRules(null);
    if (!selectedKey) return;
    let cancelled = false;
    api
      .getActiveVersion(selectedKey)
      .then((version) => api.getVersionRules(selectedKey, version.id))
      .then((rules) => {
        if (!cancelled) setActiveVersionRules(rules);
      })
      .catch(() => {
        if (!cancelled) setActiveVersionRules([]); // no active version yet (first publish) — treat as empty baseline
      });
    return () => {
      cancelled = true;
    };
  }, [selectedKey]);

  const runQualityCheck = async () => {
    if (!selectedKey) return;
    setQualityError(null);
    setQualityFailed(false);
    setQualityLoading(true);
    try {
      const report = await aiApi.getCandidateQuality(selectedKey);
      const byRule = new Map<string, QualityFinding[]>();
      for (const finding of report.findings) {
        for (const ruleId of finding.affected_rule_ids) {
          const list = byRule.get(ruleId) ?? [];
          list.push(finding);
          byRule.set(ruleId, list);
        }
      }
      setQualityFindings(byRule);
      setQualityFailed(false);
    } catch (e) {
      setQualityError(describeApiFailure(e));
      setQualityFailed(true);
    } finally {
      setQualityLoading(false);
    }
  };

  /** Perform the review. Accepts one or many ids so the single-row buttons, the
   *  bulk bar, and the family-confirmation dialog all commit through one path
   *  and therefore cannot drift in what they send or how they report it. */
  const runReview = async (ids: string[], decision: "approve" | "reject") => {
    if (ids.length === 0) return;
    setError(null);
    setFamilyPrompt(null);
    setBulkBusy(true);
    try {
      if (ids.length === 1) {
        await api.reviewCandidateRule(selectedKey, ids[0], { decision, reviewer: identity });
        message.success(decision === "approve" ? "Rule approved" : "Rule rejected");
      } else {
        const result = await api.bulkReviewCandidateRules(selectedKey, {
          candidate_ids: ids,
          decision,
          reviewer: identity,
          notes: "bulk review",
        });
        if (result.skipped.length > 0) {
          // A partial result is not an error: the reviewed rules were reviewed.
          // Reporting it as one made reviewers re-run the action.
          message.warning(
            `${result.reviewed} reviewed; ${result.skipped.length} skipped (already reviewed or published).`
          );
        } else {
          message.success(`${result.reviewed} rule${result.reviewed === 1 ? "" : "s"} ${decision}d`);
        }
      }
      setSelectedIds(new Set());
      await loadCandidates();
    } catch (e) {
      const detail = describeApiFailure(e);
      setError(detail);
      message.error(detail);
    } finally {
      setBulkBusy(false);
    }
  };

  /** Gate every review through the same two checks: attributable author, and
   *  no silently-split rule family. */
  const requestReview = (ids: string[], decision: "approve" | "reject") => {
    setError(null);
    // An approval with no attributable author is not an audit trail. Reported
    // through `message` rather than the page-top Alert: the buttons are in a
    // long scrolling list, and an error rendered off-screen is indistinguishable
    // from the button not working — which is exactly how this was reported.
    if (!identity.trim()) {
      message.warning("Set your name in the header before approving or rejecting.");
      return;
    }
    if (ids.length === 0) {
      message.warning("Select at least one candidate rule first.");
      return;
    }
    const gaps = familyGaps(new Set(ids), clusterMap, candidates);
    if (gaps.length > 0) {
      setFamilyPrompt({ ids, decision, gaps });
      return;
    }
    void runReview(ids, decision);
  };

  const handleReview = (candidateId: string, decision: "approve" | "reject") =>
    requestReview([candidateId], decision);

  const toggleSelected = (candidateId: string) =>
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(candidateId)) next.delete(candidateId);
      else next.add(candidateId);
      return next;
    });

  // WHY THERE IS NO CONTENT-KIND LANE HERE ANY MORE
  //
  // The distinction was real. A glossary entry describes a term and has no
  // condition or effect to weigh, yet its Approve button is identical to the
  // one on a rule that constrains what people may do — and in a flat list the
  // enforceable rules were buried among "X means Y" rows, so a reviewer had to
  // filter dozens of them out by eye before finding anything to decide.
  //
  // What was wrong was the level, not the observation. A lane splits the queue
  // above the policy, and a policy is the unit a reviewer approves: a policy
  // that states a term and then constrains its use has rules on both sides of
  // that line, so the lane cut it in half and showed each half as though it
  // were whole. Measured across four extraction runs, at most one policy per
  // run is purely definitional, so the definitions lane would hold a single
  // card while quietly making every mixed policy a fragment on the other side.
  //
  // The burying is answered inside the card instead, by ordering: a card puts
  // what it decides before what it defines, so a reviewer reaches the operative
  // rules first without any record being taken off the screen to do it.

  /** True when this candidate's own text answers the search. */
  const matchesSearch = useMemo(
    () => (c: CandidateRule) => candidateAnswersSearch(c, searchText),
    [searchText],
  );

  /**
   * The filters that are properties of a rule rather than of a policy.
   *
   * Held together because they are applied together and at the same level: they
   * choose which policies appear, never what a policy contains.
   */
  const ruleFilters = useMemo(
    () => ({ status: statusFilter, delta: deltaFilter }),
    [statusFilter, deltaFilter],
  );

  /**
   * Every candidate a policy can be built from, whatever the search says.
   *
   * A search narrows which policies are worth looking at. It is not a statement
   * about what a policy contains, so it must not decide that either: a card
   * built from the matches alone would show three rules of a policy that has
   * nine and offer one Approve over the three, which decides all nine. The
   * search picks the cards; the policy supplies their contents.
   */
  const placeable = useMemo(() => placeableCandidates(candidates), [candidates]);

  /**
   * The ungrouped fallback's rows, filtered at rule level — which is correct
   * *here* and nowhere else on this screen.
   *
   * This list is used only when the assembly is unavailable, and then its rows
   * are rules, not policies: there is no card to fragment and no policy-level
   * Approve to mislead anyone. A rule list narrowed by a rule's own status is
   * exactly what it appears to be. The grouped queue above is the one that had
   * to move to policy level, because there the unit on screen is the policy.
   */
  const filteredCandidates = useMemo(
    () =>
      placeable.filter(
        (c) => matchesSearch(c) && candidateAnswersRuleFilters(c, ruleFilters),
      ),
    [placeable, matchesSearch, ruleFilters],
  );

  /** The reading this one replaced, when it is still in the payload. */
  const previousOf = useMemo(() => {
    const byId = new Map(candidates.map((c) => [c.id, c]));
    return (candidate: CandidateRule) =>
      candidate.baseline_candidate_id ? byId.get(candidate.baseline_candidate_id) ?? null : null;
  }, [candidates]);

  // Reset to page 1 whenever the search narrows/widens what is shown, so the
  // reviewer never lands on a now-empty trailing page.
  useEffect(() => {
    setPage(1);
  }, [searchText]);

  // The queue's rows are policies, not rules. The server decided which rules a
  // passage states; this pairs that answer with every record that could be
  // placed. Nothing here re-decides membership or order.
  //
  // Cards are built before the search is applied, so a card always holds the
  // whole policy. The search then chooses which of those whole cards to show.
  const allPolicyCards = useMemo(
    () => buildPolicyCards(policies, placeable),
    [policies, placeable]
  );

  const matchedIds = useMemo(
    () => matchedCandidateIds(placeable, searchText),
    [placeable, searchText],
  );

  /**
   * The records answering the rule-level filters, used only to choose cards.
   *
   * The queue is a list of policies, so status and delta select policies here
   * rather than rules. A policy is offered when any of its rules answers, and
   * comes back whole — see `queueCardFilters` for why a card that shows the
   * matching part of a policy while offering one policy-level Approve is the
   * defect this replaces.
   */
  const filterMatchedIds = useMemo(
    () => candidateIdsAnsweringRuleFilters(placeable, ruleFilters),
    [placeable, ruleFilters],
  );

  const policyCards = useMemo(
    () =>
      cardsAnsweringRuleFilters(
        cardsAnsweringSearch(allPolicyCards, searchText, matchedIds),
        ruleFilters,
        filterMatchedIds,
      ),
    [allPolicyCards, searchText, matchedIds, ruleFilters, filterMatchedIds]
  );

  /**
   * What the document a policy was read out of is called.
   *
   * Read off the run facets, which already carry a title for every document
   * version this queue can show, and keyed by version so a policy is attributed
   * to the document it actually came from rather than to whichever one happens
   * to be selected. Empty when the facets did not load — and then a card asks
   * the narrower question about its label, which is the answer it had before
   * this existed.
   */
  const documentNameByVersion = useMemo(() => {
    const byVersion = new Map<string, string>();
    for (const run of facets?.runs ?? []) {
      const title = run.document_title?.trim();
      if (title && !byVersion.has(run.document_version_id)) {
        byVersion.set(run.document_version_id, title);
      }
    }
    return byVersion;
  }, [facets]);

  const documentNameOf = useCallback(
    (versionId: string | null | undefined) =>
      (versionId && documentNameByVersion.get(versionId)) || null,
    [documentNameByVersion],
  );

  const unplaced = useMemo(
    () => unplacedRules(policies, filteredCandidates),
    [policies, filteredCandidates]
  );

  // Paginated over policies, so a passage is never cut in half by a page
  // boundary — which is the failure the old per-rule pagination could produce
  // and then had to describe with a "continues below" band.
  const pagedPolicyCards = useMemo(
    () => policyCards.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [policyCards, page]
  );

  // The ungrouped fallback, used only when the assembly is unavailable: the
  // reviewer still gets the rules, and is told the arrangement is missing
  // rather than shown an empty queue.
  const pagedCandidates = useMemo(
    () => filteredCandidates.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [filteredCandidates, page]
  );

  const grouped = policiesState === "ready";
  const listTotal = grouped ? policyCards.length : filteredCandidates.length;

  /**
   * What the current rule-level filters are called, in the words the controls
   * themselves use. Read from the tab strip's own table rather than restated,
   * so the note can never name a filter differently from the button that set
   * it — and so a filter added there needs no second edit here.
   */
  const activeFilterLabels = useMemo(() => {
    const labels: string[] = [];
    if (!filterIsOff(statusFilter)) {
      labels.push(
        REVIEW_STATUS_TABS.find((t) => t.value === statusFilter)?.label ?? statusFilter,
      );
    }
    if (!filterIsOff(deltaFilter)) {
      labels.push(DELTA_META[deltaFilter]?.label ?? deltaFilter);
    }
    return labels;
  }, [statusFilter, deltaFilter]);

  // Only meaningful for the grouped queue: the ungrouped fallback lists rules,
  // so its count and the strip's count are already the same unit.
  const selectionNote = grouped
    ? policySelectionNote(listTotal, activeFilterLabels)
    : null;

  // Family banding, by the same criterion the Policies view uses: a curated
  // `group_label`, else rules of one type testing the same fact. Clustering runs
  // over *all* loaded candidates rather than the current filter, so a family's
  // identity and colour don't shift when a reviewer searches or changes tabs.
  const clusterMap = useMemo(
    () => buildVariationClusters(candidates.map((c) => c.rule)),
    [candidates]
  );

  // Geometry is computed over the whole filtered list, not just the visible
  // page: a family split across a page boundary must still say "continues
  // below" rather than silently presenting a fragment as the complete set.
  const bandInfo = useMemo(
    () =>
      computeBandGeometry(
        filteredCandidates.map((c) => ({ kind: "rule" as const, ruleId: c.rule.rule_id })),
        clusterMap
      ),
    [filteredCandidates, clusterMap]
  );

  const bandedFamilyCount = useMemo(() => {
    const ids = new Set<string>();
    for (const c of filteredCandidates) {
      const cluster = clusterMap.get(c.rule.rule_id);
      if (cluster) ids.add(clusterIdentity(cluster));
    }
    return ids.size;
  }, [filteredCandidates, clusterMap]);

  // How many rows carry no family at all. A reviewer looking at a flat,
  // unbanded list cannot otherwise tell whether grouping is switched off,
  // broken, or correctly reporting that no relationship was derived — and the
  // three call for completely different responses. Counted rather than
  // inferred from `bandedFamilyCount`, which counts families, not rows.
  const unfamiliedCount = useMemo(
    () => filteredCandidates.filter((c) => !clusterMap.get(c.rule.rule_id)).length,
    [filteredCandidates, clusterMap]
  );

  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const c of candidates) counts[c.review_status] = (counts[c.review_status] ?? 0) + 1;
    return counts;
  }, [candidates]);

  const selectedCandidate = useMemo(
    () => placeable.find((candidate) => candidate.id === selectedCandidateId) ?? null,
    [placeable, selectedCandidateId],
  );

  /** The passage in the detail panel. */
  const openPolicyCard = useMemo(
    () => policyCards.find((card) => card.policy.key === openPolicyKey) ?? null,
    [policyCards, openPolicyKey],
  );

  useEffect(() => {
    // Grouped: the panel opens on a policy, and stays on a policy until the
    // reviewer drills into one of its rules. Selecting a rule up front would
    // reintroduce exactly the rule-at-a-time reading the card exists to end.
    if (grouped) {
      if (policyCards.length === 0) {
        setOpenPolicyKey(null);
        setSelectedCandidateId(null);
        setMobileInspectorOpen(false);
        return;
      }
      if (!openPolicyCard) {
        setOpenPolicyKey(policyCards[0].policy.key);
        setSelectedCandidateId(null);
      }
      return;
    }
    if (filteredCandidates.length === 0) {
      setSelectedCandidateId(null);
      setMobileInspectorOpen(false);
      return;
    }
    if (!selectedCandidate) setSelectedCandidateId(filteredCandidates[0].id);
  }, [grouped, policyCards, openPolicyCard, filteredCandidates, selectedCandidate]);

  const openCandidate = (candidate: CandidateRule) => {
    setSelectedCandidateId(candidate.id);
    if (isDesktop) {
      if (workspaceMode === "list") setWorkspaceMode("split");
    } else {
      setMobileInspectorOpen(true);
    }
  };

  /** Open a passage in the detail panel, at the policy rather than a rule. */
  const openPolicy = (card: PolicyCard) => {
    setOpenPolicyKey(card.policy.key);
    setSelectedCandidateId(null);
    setInspectorTab("overview");
    if (isDesktop) {
      if (workspaceMode === "list") setWorkspaceMode("split");
    } else {
      setMobileInspectorOpen(true);
    }
  };

  /** Drill from the open policy into one of its rules, in the same panel.
   *
   *  Looked up among everything placeable, not among the search matches: a card
   *  shows the whole policy, so a rule the search did not match is on screen and
   *  must open like any other. */
  const openRuleWithinPolicy = (ruleId: string) => {
    const candidate = placeable.find((item) => item.rule.rule_id === ruleId);
    if (!candidate) return;
    setSelectedCandidateId(candidate.id);
    setInspectorTab("overview");
  };

  /** What this queue can do to one rule, beyond deciding it.
   *
   *  Handed to the overflow menu as handlers rather than as flags. Two rules
   *  are kept here deliberately:
   *
   *  - Whether the *record* admits an action is not decided here. The menu
   *    reads that from the review status through the same `candidateEditability`
   *    the server mirrors, so a candidate that cannot be edited shows no Edit
   *    entry wherever it is drawn.
   *  - Whether the *person* may act is decided here, because a role is a fact
   *    about the reader and not about the record. A reviewer who is not a
   *    manager is given no override handler at all, so the entry is absent
   *    rather than present and refused. */
  const ruleActionHandlers = (
    candidate: CandidateRule,
    openFullRecord: () => void,
  ): RecordActionHandlers => ({
    "open-record": openFullRecord,
    "view-history": () => {
      openFullRecord();
      setInspectorTab("history");
    },
    "ask-ai": () => setAskTarget(candidate),
    edit: () => setEditTarget(candidate),
    "suggest-rewrite": () => setRewriteTarget(candidate),
    ...(isManager
      ? {
          "request-changes": () => setManagerAction({ candidate, mode: "request-changes" }),
          "override-reject": () => setManagerAction({ candidate, mode: "override-reject" }),
          "override-approve": () => setManagerAction({ candidate, mode: "override-approve" }),
        }
      : {}),
  });

  // Opens a record in the panel. Takes the record itself rather than the rule it
  // holds, because `rule_id` is a hash of the rule's content: two rules a
  // passage states in identical words share one, so resolving a click through it
  // can open a rule the reviewer did not point at. The card rows hand back their
  // own identity for exactly this reason.
  const selectCandidateRecord = (candidate: (typeof placeable)[number]) => {
    if (grouped) {
      const card = policyCards.find((c) => c.rules.some((r) => r.recordId === candidate.id));
      if (card) {
        const index = policyCards.indexOf(card);
        if (index >= 0) setPage(Math.floor(index / PAGE_SIZE) + 1);
        setOpenPolicyKey(card.policy.key);
      }
      setSelectedCandidateId(candidate.id);
      if (isDesktop) {
        if (workspaceMode === "list") setWorkspaceMode("split");
      } else {
        setMobileInspectorOpen(true);
      }
      return;
    }
    const index = filteredCandidates.findIndex((item) => item.id === candidate.id);
    if (index >= 0) setPage(Math.floor(index / PAGE_SIZE) + 1);
    openCandidate(candidate);
  };

  const selectCandidateRuleById = (recordId: string) => {
    const candidate = placeable.find((item) => item.id === recordId);
    if (candidate) selectCandidateRecord(candidate);
  };

  const selectCandidateRule = (rule: CanonicalRule) => {
    const candidate = placeable.find((item) => item.rule.rule_id === rule.rule_id);
    if (candidate) selectCandidateRecord(candidate);
  };

  const changeWorkspaceMode = (mode: ReviewWorkspaceMode) => {
    setInspectorFullscreen(false);
    setWorkspaceMode(mode);
  };

  const hideInspector = () => {
    setInspectorFullscreen(false);
    setWorkspaceMode("list");
  };

  /** Every reviewable record currently on screen.
   *
   *  In grouped mode a card shows the whole policy, including rules the search
   *  did not match, so "select all" has to reach them too: a bulk decision must
   *  cover what the reviewer can see, or narrowing the view would quietly
   *  change what the action decides. */
  const selectableIds = (
    grouped
      ? // A card can now hold a record with no draft row behind it, which the
        // review surface never has. Filtered rather than asserted, so a
        // published record could never be swept into a bulk decision.
        policyCards.flatMap((card) =>
          card.rules.flatMap((entry) => (entry.candidate ? [entry.candidate] : [])),
        )
      : filteredCandidates
  )
    .filter((c) => candidateEditability(c.review_status).canReview)
    .map((c) => c.id);

  const toggleSelectAllVisible = () =>
    setSelectedIds((prev) => (prev.size === selectableIds.length ? new Set() : new Set(selectableIds)));

  /** Put a whole passage into the bulk selection, or take it out again.
   *
   * The card's checkbox stands for the policy, so it moves every rule of the
   * passage that is still open for review — one act, matching the one decision
   * the card offers. */
  const togglePolicySelected = (card: PolicyCard) =>
    setSelectedIds((prev) => {
      const next = new Set(prev);
      const allSelected = card.reviewableIds.every((id) => next.has(id));
      for (const id of card.reviewableIds) {
        if (allSelected) next.delete(id);
        else next.add(id);
      }
      return next;
    });

  /** Add every open member of a rule's family to the bulk selection.
   *
   * Reviewing a family is the common case once you notice one — the members say
   * the same thing at different thresholds, so they are read together and
   * decided together. Selecting them one checkbox at a time invites exactly the
   * partial approval the confirmation dialog then has to warn about. */
  const selectFamily = (ruleId: string) => {
    const members = familyMembers(ruleId, clusterMap, candidates);
    if (members.length === 0) return;
    setSelectedIds((prev) => {
      const next = new Set(prev);
      // Already all selected → treat the chip as a toggle and clear them.
      const allSelected = members.every((m) => next.has(m.id));
      for (const m of members) {
        if (allSelected) next.delete(m.id);
        else next.add(m.id);
      }
      return next;
    });
  };

  const handleBulkReview = (decision: "approve" | "reject") =>
    requestReview(Array.from(selectedIds), decision);

  /** How many passages the bulk selection touches — the unit the reviewer is
   *  working in, alongside the rule count the server will actually write to. */
  const selectedPolicyCount = policyCards.filter((card) =>
    card.reviewableIds.some((id) => selectedIds.has(id))
  ).length;

  const handlePublish = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setPublishResult(null);
    if (!identity.trim()) {
      message.warning("Set your name in the application header before publishing.");
      return;
    }
    try {
      const version = await api.publishCandidates(selectedKey, {
        approved_by: identity,
        effective_from: effectiveFrom,
        is_active: true,
      });
      setPublishResult(version);
      await loadCandidates();
    } catch (e) {
      setError(describeApiFailure(e));
    }
  };

  /** Copy a composer-generated rule into the form so the human can adjust it.
   *
   * The whole rule is retained separately (`aiGeneratedRule`) because the form
   * only surfaces the fields a person edits; the formulation record, lineage
   * and executability flags the agent produced have no widgets and would be
   * lost if the payload were rebuilt from the visible fields alone. */
  const applyGeneratedRule = (rule: CanonicalRule) => {
    setAiGeneratedRule(rule);
    setLoadedAiRuleId(rule.rule_id);
    setDraftError(null);
    setRuleId(rule.rule_id);
    setTitle(rule.title);
    setDescription(rule.description);
    setRuleType(rule.rule_type);
    setEffectType(rule.effect.type);
    setEffectAction(rule.effect.action);
    setPriority(rule.priority);
    setAuthorityOwner(rule.authority.owner);
    setAuthorityLevel(rule.authority.level);
    setAuthorityRank(rule.authority.rank);
    setDraftEffectiveFrom(rule.effective_from.slice(0, 10));
    setDraftScope(normalizeScope(rule.scope));
    setDraftIsExplicitOverride(rule.is_explicit_override ?? false);
    setDraftSupersedesRuleIds(rule.supersedes_rule_ids ?? []);
    setDraftGroupLabel(rule.group_label ?? "");
    setDraftRelatedRuleIds(rule.related_rule_ids ?? []);
    setAdvancedJson(JSON.stringify(rule, null, 2));

    const rows = conditionToRows(rule.condition);
    if (isVacuousCondition(rule.condition)) {
      // Nothing machine-checkable was extracted. Show an empty row so the user
      // is invited to add logic, rather than dropping them into raw JSON.
      setConditionRows([{ fact: "", operator: "greaterThan", value: "" }]);
      setAdvancedMode(false);
    } else if (rows && rows.length > 0) {
      setConditionRows(rows);
      setAdvancedMode(false);
    } else {
      // Richer logic than the row editor can express — show it honestly as JSON
      // instead of flattening it into something that means something else.
      setAdvancedMode(true);
    }
  };

  const resetDraftForm = () => {
    setRuleId("");
    setTitle("");
    setDescription("");
    setEffectAction("");
    setAuthorityOwner("");
    setConditionRows([{ fact: "", operator: "greaterThan", value: "" }]);
    setDraftScope(EMPTY_SCOPE);
    setDraftIsExplicitOverride(false);
    setDraftSupersedesRuleIds([]);
    setDraftGroupLabel("");
    setDraftRelatedRuleIds([]);
    setAdvancedJson("{}");
    setAiGeneratedRule(null);
    setLoadedAiRuleId(null);
  };

  const handleDraft = async (e: React.FormEvent) => {
    e.preventDefault();
    setDraftError(null);
    try {
      let rule: Record<string, unknown>;
      if (advancedMode) {
        rule = JSON.parse(advancedJson);
      } else {
        const filledRows = conditionRows.filter((r) => r.fact.trim() !== "");
        // Only override the generated condition once the user has actually
        // entered one; an untouched form must not silently replace extracted
        // logic with an empty conjunction.
        const draftCondition =
          filledRows.length > 0
            ? buildCondition(filledRows)
            : (aiGeneratedRule?.condition ?? buildCondition([]));
        rule = {
          // Start from the generated rule (when there is one) so agent-authored
          // fields without a widget — formulation, lineage, ambiguity status —
          // are carried through instead of being dropped on submit.
          ...(aiGeneratedRule ?? {}),
          policy_set_id: "placeholder",
          policy_version_id: "placeholder",
          rule_id: ruleId,
          rule_revision: 1,
          title,
          description,
          rule_type: ruleType,
          authority: { level: authorityLevel, owner: authorityOwner, rank: authorityRank },
          scope: draftScope,
          is_explicit_override: draftIsExplicitOverride,
          supersedes_rule_ids: draftSupersedesRuleIds,
          group_label: draftGroupLabel,
          related_rule_ids: draftRelatedRuleIds,
          condition: draftCondition,
          // Derived from the condition, in both directions. Neither source was
          // right before: with no AI rule the field was absent, so the server
          // default (True) paired with an empty conjunction and claimed a rule
          // with nothing to test was executable; with an AI rule the spread
          // carried its `false` over a condition the user had just built by
          // hand, so the engine short-circuited before ever reading it.
          machine_executable: machineExecutableFor(draftCondition),
          effect: { type: effectType, action: effectAction },
          required_facts:
            filledRows.length > 0
              ? filledRows.map((r) => ({
                  name: r.fact,
                  data_type: isNaN(Number(r.value)) ? "string" : "number",
                  required: true,
                }))
              : (aiGeneratedRule?.required_facts ?? []),
          priority,
          effective_from: draftEffectiveFrom,
        };
      }
      await api.draftCandidateRule(selectedKey, { rule });
      setShowDraftForm(false);
      resetDraftForm();
      await loadCandidates();
    } catch (e) {
      setDraftError(describeApiFailure(e));
    }
  };

  const addConditionRow = () => setConditionRows((rows) => [...rows, { fact: "", operator: "greaterThan", value: "" }]);
  const updateConditionRow = (i: number, patch: Partial<ConditionRow>) =>
    setConditionRows((rows) => rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  const removeConditionRow = (i: number) => setConditionRows((rows) => rows.filter((_, idx) => idx !== i));

  const approvedUnpublished = candidates.filter((c) => c.review_status === "approved");
  const totalCandidates = candidates.length;

  /**
   * True when this project holds no candidate rules at all -- not "none matched
   * the current filter", which is a different situation with a different
   * remedy.
   *
   * The distinction decides how much apparatus the page is entitled to, and the
   * reasoning behind it is in reviewQueueEmptiness.ts, where it is tested
   * directly. The component renders the consequence.
   */
  const queueIsEmpty = reviewQueueIsEmpty(
    totalCandidates,
    {
      status: statusFilter,
      document: documentFilter,
      run: runFilter,
      delta: deltaFilter,
      showRemoved,
      search: searchText,
    },
    loading,
  );

  /**
   * An empty queue is ambiguous: it can mean "nothing matched" (a dead end)
   * or "this run changed nothing" (a successful no-op). Re-extracting an
   * unchanged document is the second case, and reading it as failure would
   * push the reviewer to re-run the extraction pointlessly. Distinguish them.
   */
  const emptyState = useMemo(() => {
    // Filters disagree on how "off" is spelled: document/run use "", delta uses
    // "all". Normalise once here rather than testing truthiness per branch —
    // treating "all" as an active filter is exactly the bug this avoids.
    const activeDelta = deltaFilter && deltaFilter !== "all" ? deltaFilter : "";
    if (searchText.trim()) {
      return { status: "info" as const, title: "No rules match your search.", detail: null };
    }
    const run = runFilter ? facets?.runs.find((r) => r.id === runFilter) : null;
    if (run && !activeDelta && statusFilter === "all") {
      const changed = run.delta.new + run.delta.changed;
      if (changed === 0 && run.total > 0) {
        return {
          status: "success" as const,
          title: `No changes in ${run.reference ?? "this run"}.`,
          detail: `All ${run.total} rule(s) extracted from ${run.document_title} were identical to the previous run, so nothing new needs review. The run is kept in history as evidence the document was re-checked.`,
        };
      }
      if (run.total === 0) {
        return {
          status: "warning" as const,
          title: `${run.reference ?? "This run"} produced no rules.`,
          detail: "The extraction completed but found nothing to formalize in this document.",
        };
      }
    }
    if (activeDelta) {
      return {
        status: "info" as const,
        title: `Nothing classified as “${DELTA_META[activeDelta]?.label ?? activeDelta}” under the current filters.`,
        detail: "Clear the change filter to see the rest of the queue.",
      };
    }
    if (statusFilter !== "all") {
      return {
        status: "info" as const,
        title: `Nothing is currently ${STATUS_LABEL[statusFilter]?.toLowerCase() ?? statusFilter}.`,
        detail: null,
      };
    }
    return { status: "info" as const, title: "No candidate rules found for this filter.", detail: null };
  }, [searchText, runFilter, deltaFilter, statusFilter, facets]);

  const publishedPct = totalCandidates ? Math.round(((statusCounts.published ?? 0) / totalCandidates) * 100) : 0;
  const isManager = actor.role === "policy_manager";

  const publishDiff = useMemo(() => {
    if (activeVersionRules === null) return null;
    const activeIds = new Set(activeVersionRules.map((r) => r.rule_id));
    const approvedIds = new Set(approvedUnpublished.map((c) => c.rule.rule_id));
    const netNew = approvedUnpublished.filter((c) => !activeIds.has(c.rule.rule_id));
    const superseding = approvedUnpublished.filter((c) => activeIds.has(c.rule.rule_id));
    const unchangedCount = activeVersionRules.filter((r) => !approvedIds.has(r.rule_id)).length;
    return { netNew, superseding, unchangedCount };
  }, [activeVersionRules, approvedUnpublished]);

  const qualityFindingCount = qualityFindings
    ? Array.from(qualityFindings.values()).reduce((total, findings) => total + findings.length, 0)
    : null;
  const qualityScan = qualityScanSummary({
    loading: qualityLoading,
    failed: qualityFailed,
    count: qualityFindingCount,
  });
  const reviewedCount =
    (statusCounts.approved ?? 0) + (statusCounts.rejected ?? 0) + (statusCounts.published ?? 0);
  const decisionProgress = totalCandidates ? Math.round((reviewedCount / totalCandidates) * 100) : 0;
  const selectedFindings = selectedCandidate
    ? (qualityFindings?.get(selectedCandidate.rule.rule_id) ?? [])
    : [];
  const selectedEditability = selectedCandidate
    ? candidateEditability(selectedCandidate.review_status)
    : null;
  const candidateRules = candidates.map((candidate) => candidate.rule);

  const ruleInspector = (
    <PolicyInspector
      rule={selectedCandidate?.rule ?? null}
      allRules={candidateRules}
      activeTabKey={inspectorTab}
      onTabChange={setInspectorTab}
      onSelectRule={selectCandidateRule}
      onClose={!isDesktop ? () => setMobileInspectorOpen(false) : undefined}
      onHide={isDesktop ? hideInspector : undefined}
      onToggleFullscreen={isDesktop ? () => setInspectorFullscreen((value) => !value) : undefined}
      isFullscreen={inspectorFullscreen}
      recordKind="candidate"
      recordLabel="candidate"
      contextMeta={
        selectedCandidate ? (
          <>
            <Tag color={STATUS_COLOR[selectedCandidate.review_status] ?? "default"}>
              {STATUS_LABEL[selectedCandidate.review_status] ?? selectedCandidate.review_status}
            </Tag>
            {selectedCandidate.delta_status && selectedCandidate.delta_status !== "baseline" && (
              <Tag color={DELTA_META[selectedCandidate.delta_status]?.color}>
                {DELTA_META[selectedCandidate.delta_status]?.label}
              </Tag>
            )}
          </>
        ) : undefined
      }
      additionalActions={
        selectedCandidate && selectedEditability ? (
          <>
            <Button size="small" icon={<BulbOutlined />} onClick={() => setAskTarget(selectedCandidate)}>
              Ask AI
            </Button>
            <Tooltip title={selectedEditability.editBlockedReason ?? "Change this candidate's wording, logic or effect"}>
              <Button
                size="small"
                icon={<EditOutlined />}
                disabled={!selectedEditability.canEdit}
                onClick={() => setEditTarget(selectedCandidate)}
              >
                Edit
              </Button>
            </Tooltip>
            {selectedEditability.canReview && (
              <>
                <Button size="small" icon={<ThunderboltOutlined />} onClick={() => setRewriteTarget(selectedCandidate)}>
                  Suggest rewrite
                </Button>
                <Button size="small" type="primary" onClick={() => handleReview(selectedCandidate.id, "approve")}>
                  Approve
                </Button>
                <Button size="small" danger onClick={() => handleReview(selectedCandidate.id, "reject")}>
                  Reject
                </Button>
              </>
            )}
            {selectedCandidate.review_status === "approved" && (
              <>
                <Button
                  size="small"
                  icon={<SendOutlined />}
                  disabled={!isManager}
                  onClick={() => setManagerAction({ candidate: selectedCandidate, mode: "request-changes" })}
                >
                  Send back
                </Button>
                <Button
                  size="small"
                  danger
                  disabled={!isManager}
                  onClick={() => setManagerAction({ candidate: selectedCandidate, mode: "override-reject" })}
                >
                  Override & reject
                </Button>
              </>
            )}
            {selectedCandidate.review_status === "rejected" && isManager && (
              <Button
                size="small"
                onClick={() => setManagerAction({ candidate: selectedCandidate, mode: "override-approve" })}
              >
                Override & approve
              </Button>
            )}
          </>
        ) : undefined
      }
      overviewSupplement={
        selectedCandidate ? (
          <div className="review-inspector-record">
            <div className="review-record-grid">
              <div>
                <span>Candidate record ID</span>
                <Text code copyable={{ text: selectedCandidate.id }}>
                  {selectedCandidate.id}
                </Text>
              </div>
              <div>
                <span>Extraction run ID</span>
                <Text code copyable={{ text: selectedCandidate.extraction_run_id }}>
                  {selectedCandidate.extraction_run_id}
                </Text>
              </div>
              <div>
                <span>Review state</span>
                <Text>{STATUS_LABEL[selectedCandidate.review_status] ?? selectedCandidate.review_status}</Text>
              </div>
              <div>
                <span>Last decision</span>
                <Text>{selectedCandidate.reviewed_by ? `By ${selectedCandidate.reviewed_by}` : "Not reviewed"}</Text>
              </div>
            </div>
            {(() => {
              const previous = previousOf(selectedCandidate);
              if (!previous) return null;
              return (
                <div className="candidate-previous-version">
                  <Text type="secondary">
                    <HistoryOutlined /> Previous version
                  </Text>
                  <div className="candidate-previous-version-body">
                    <Text code>{previous.rule.rule_id}</Text>
                    <Text type="secondary">
                      {previous.published_version_id ? "published" : previous.review_status} ·{" "}
                      {new Date(previous.created_at).toLocaleDateString()}
                    </Text>
                    <Button
                      size="small"
                      onClick={() => setPreviousUnderReview(previous)}
                    >
                      View
                    </Button>
                  </div>
                </div>
              );
            })()}
            {selectedCandidate.baseline_candidate_id && (
              <RuleChangeExplainer candidateId={selectedCandidate.id} />
            )}
            {selectedFindings.length > 0 && (
              <div className="readiness-badges">
                {selectedFindings.map((finding, index) => (
                  <Tooltip key={index} title={finding.recommendation}>
                    <Tag
                      icon={<ExclamationCircleOutlined />}
                      color={finding.severity === "high" ? "red" : finding.severity === "medium" ? "gold" : "default"}
                    >
                      {finding.category}: {finding.finding}
                    </Tag>
                  </Tooltip>
                ))}
              </div>
            )}
          </div>
        ) : undefined
      }
      notesTarget={
        selectedCandidate
          ? { entityType: "candidate_rule", entityId: selectedCandidate.id, title: "Review discussion" }
          : undefined
      }
    />
  );

  // One panel, two depths. The passage is what the reviewer decides, so that is
  // what the panel shows; a rule of it can be examined in place, behind an
  // explicit "Back to" that returns to the policy. Opening a rule has never
  // meant opening a second panel — three rules of a passage must never put
  // three documents in front of somebody deciding one thing.
  const candidateInspector =
    grouped && openPolicyCard && !selectedCandidate ? (
      <PolicyDetailPanel
        card={openPolicyCard}
        documentName={documentNameOf(openPolicyCard.policy.document_version_id)}
        statusColor={(status) => STATUS_COLOR[status] ?? "default"}
        statusLabel={(status) => STATUS_LABEL[status] ?? status}
        ruleDetail={(ruleId) => {
          const entry = openPolicyCard.rules.find((r) => r.rule_id === ruleId);
          if (!entry?.candidate) return null;
          return (
            <RuleDetailInline
              candidate={entry.candidate}
              // The card above already quotes this rule's statement, verbatim,
              // in the passage it came from. Repeating it inside the expansion
              // is the one thing an expansion can do that is worse than showing
              // nothing: it charges a click for words already read.
              statementVisibleAbove
              allRules={openPolicyCard.rules.map((r) => r.rule)}
              onOpenFullRecord={() => openRuleWithinPolicy(ruleId)}
            />
          );
        }}
        onApprove={
          openPolicyCard.reviewableIds.length > 0
            ? () => requestReview(openPolicyCard.reviewableIds, "approve")
            : undefined
        }
        onReject={
          openPolicyCard.reviewableIds.length > 0
            ? () => requestReview(openPolicyCard.reviewableIds, "reject")
            : undefined
        }
        policySetKey={selectedKey}
        tests={policySetTests}
        testsLoading={policySetTestsLoading}
        testing={policyTesting}
        extractionRuns={facets?.runs ?? null}
        history={policyHistory[openPolicyCard.policy.key] ?? null}
        historyLoading={policyHistoryLoading.has(openPolicyCard.policy.key)}
        onRequestHistory={requestPolicyHistory}
        ruleActions={(ruleId) => {
          const entry = openPolicyCard.rules.find((r) => r.rule_id === ruleId);
          if (!entry?.candidate) return {};
          return ruleActionHandlers(entry.candidate, () => openRuleWithinPolicy(ruleId));
        }}
        /* What the queue can genuinely service for a whole policy, and no more.
         *
         * Only `open-record` is wired, because only it already exists: a policy
         * is opened at the first rule the reviewer has not yet settled, or at
         * its first rule when they are all settled, which is the same
         * destination the rule rows use.
         *
         * Left unwired on purpose, and absent rather than dead in the menu:
         *  - `view-history` would have to open one rule's history under a
         *    policy's name. The policy-scope history the API exposes has no
         *    client in this app, and api.ts is not this change's to edit.
         *  - `ask-ai` is already a button in this header. A second way to reach
         *    one thing is the drift this work exists to undo.
         *  - `revise`, `compare-versions` and `export` mean nothing for a
         *    candidate; they are declared for the Policies page to service. */
        policyActions={{
          "open-record": () => {
            const unsettled = openPolicyCard.rules.find((r) =>
              openPolicyCard.reviewableIds.includes(r.recordId),
            );
            const target = unsettled ?? openPolicyCard.rules[0];
            if (target) openRuleWithinPolicy(target.rule_id);
          },
        }}
        actions={
          <>
            {isDesktop && (
              <Button size="small" onClick={() => setInspectorFullscreen((value) => !value)}>
                {inspectorFullscreen ? "Restore" : "Expand"}
              </Button>
            )}
            {isDesktop ? (
              <Button size="small" onClick={hideInspector}>
                Hide
              </Button>
            ) : (
              <Button size="small" onClick={() => setMobileInspectorOpen(false)}>
                Close
              </Button>
            )}
          </>
        }
      />
    ) : (
      <>
        {grouped && openPolicyCard && selectedCandidate && (
          <div className="policy-detail-panel__breadcrumb">
            <Button size="small" icon={<LeftOutlined />} onClick={() => setSelectedCandidateId(null)}>
              Back to the policy
            </Button>
            <Text type="secondary">
              {/* Named by its title rather than by its key: a policy of fifty
                  passages has fifty element ids and one name, and a persisted
                  provision's key is a digest. `6e4461b7c9deb997…` names nothing
                  a reviewer is holding in mind while reading rule 3 of 10. */}
              Rule {openPolicyCard.rules.findIndex((r) => r.recordId === selectedCandidate.id) + 1} of{" "}
              {openPolicyCard.rules.length} in{" "}
              {policyTitle(openPolicyCard.policy, openPolicyCard.passages).text ||
                openPolicyCard.policy.key}
            </Text>
          </div>
        )}
        {ruleInspector}
      </>
    );

  return (
    <>
      <div className="page-header-row review-page-header">
        <div>
          <Title level={3}>Review queue</Title>
          <Text type="secondary">Decide candidate records from their source, condition, outcome, and exceptions.</Text>
        </div>
        <Space wrap className="review-page-actions">
          {isDesktop && selectedKey && (
            <Segmented
              className="policies-view-switcher"
              value={workspaceMode}
              onChange={(value) => changeWorkspaceMode(value as ReviewWorkspaceMode)}
              aria-label="Review workspace layout"
              options={[
                {
                  value: "list",
                  label: (
                    <span className="policies-view-option">
                      <UnorderedListOutlined /> List
                    </span>
                  ),
                },
                {
                  value: "split",
                  label: (
                    <span className="policies-view-option">
                      <LayoutOutlined /> Split
                    </span>
                  ),
                },
                {
                  value: "detail",
                  label: (
                    <span className="policies-view-option">
                      <FileSearchOutlined /> Detail
                    </span>
                  ),
                },
              ]}
            />
          )}
          {!scoped && (
            <Select
              value={selectedKey}
              onChange={setSelectedKey}
              style={{ minWidth: 220 }}
              options={policySets.map((ps) => ({ value: ps.key, label: ps.name }))}
            />
          )}
        </Space>
      </div>

      {error && <Alert type="error" showIcon message={error} closable onClose={() => setError(null)} />}
      {!scoped && policySets.length === 0 && (
        <Text type="secondary">Create a policy set first (Policy Sets page).</Text>
      )}

      {/* Approving records a decision; it does not change the live policy. With a
          long queue the publish form sits hundreds of rows down, so approvals
          could pile up with no visible consequence and the Policies tab stayed
          empty. Surface the pending state where the approving happens. */}
      {selectedKey && approvedUnpublished.length > 0 && (
        <Alert
          type="success"
          showIcon
          style={{ marginBottom: 16 }}
          message={`${approvedUnpublished.length} approved rule${
            approvedUnpublished.length === 1 ? "" : "s"
          } ready to publish`}
          description={
            <Text type="secondary">
              Approved rules are not live yet. Publishing creates an immutable, numbered version — that is what the{" "}
              <strong>Policies</strong> tab shows.
            </Text>
          }
          action={
            <Button
              size="small"
              type="primary"
              onClick={() =>
                document
                  .querySelector(".publish-card")
                  ?.scrollIntoView({ behavior: "smooth", block: "center" })
              }
            >
              Publish now →
            </Button>
          }
        />
      )}

      {/* The six status counts that used to sit here as read-only tags are
          already rendered directly below by ReviewStatusTabs — where they are
          also clickable filters. Duplicating them cost 170px above the fold and
          gave the reviewer a second, dumber copy of the same numbers. Only the
          publish progress was unique to this band, so that is all that remains,
          as a single slim line. */}
      {selectedKey && totalCandidates > 0 && (
        <div className="review-progress-line">
          <Text className="review-progress-line__total">
            {/* Policies lead, because a policy is what gets decided. The rule
                count follows rather than disappearing: it is what a policy is
                made of. Null while the assembly is not ready, so the line says
                the one number it actually has instead of reporting no policies
                over a queue that plainly holds some. */}
            <strong>
              {recordScaleLabel(
                policiesState === "ready" ? allPolicyCards.length : null,
                totalCandidates,
              )}
            </strong>
          </Text>
          <Progress
            percent={publishedPct}
            size="small"
            showInfo={false}
            strokeColor="#16a34a"
            className="review-progress-line__bar"
          />
          <Text type="secondary" className="review-progress-line__label">
            {statusCounts.published ?? 0} published · {publishedPct}%
          </Text>
        </div>
      )}

      {selectedKey && (
        <>
          <section className="review-queue-panel">
            <div className="review-queue-panel__header">
              <div>
                <Title level={4}>Candidate rules</Title>
                <Text type="secondary">Select a decision record to verify its logic, source, formulation, and review history.</Text>
              </div>
              <Button
                type={showDraftForm ? "default" : "primary"}
                icon={!showDraftForm && <PlusOutlined />}
                onClick={() => setShowDraftForm((v) => !v)}
              >
                {showDraftForm ? "Cancel" : "Draft Candidate Rule"}
              </Button>
            </div>
            <div className="review-queue-panel__body">
            {showDraftForm && (
              <Row gutter={20} style={{ marginBottom: 8 }}>
                <Col xs={24} xl={9} style={{ marginBottom: 16 }}>
                  <AiRuleComposer
                    policySetKey={selectedKey}
                    onLoadRule={applyGeneratedRule}
                    loadedRuleId={loadedAiRuleId}
                  />
                </Col>
                <Col xs={24} xl={15}>
              <Form layout="vertical" onSubmitCapture={handleDraft}>
                {draftError && <Alert type="error" showIcon message={draftError} style={{ marginBottom: 16 }} />}
                {loadedAiRuleId && (
                  <Alert
                    type="success"
                    showIcon
                    style={{ marginBottom: 16 }}
                    message="Filled in from your description"
                    description="Every field below is yours to change. Nothing is saved until you submit it for review."
                    closable
                    onClose={() => setLoadedAiRuleId(null)}
                  />
                )}
                <ImmutableFieldsNotice ruleId={advancedMode ? undefined : ruleId} />
                <Checkbox checked={advancedMode} onChange={(e) => setAdvancedMode(e.target.checked)} style={{ marginBottom: 16 }}>
                  Advanced (raw JSON) mode
                </Checkbox>

                {advancedMode ? (
                  <Form.Item label="Candidate rule (canonical rule JSON)">
                    <TextArea rows={14} value={advancedJson} onChange={(e) => setAdvancedJson(e.target.value)} spellCheck={false} />
                  </Form.Item>
                ) : (
                  <>
                    <Row gutter={16}>
                      <Col span={8}>
                        <Form.Item label="Rule ID" required>
                          <Input value={ruleId} onChange={(e) => setRuleId(e.target.value)} placeholder="RULE-DRAFT-001" />
                        </Form.Item>
                      </Col>
                      <Col span={16}>
                        <Form.Item label="Title" required>
                          <Input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Require manager approval" />
                        </Form.Item>
                      </Col>
                      <Col span={24}>
                        <Form.Item label="Description">
                          <Input value={description} onChange={(e) => setDescription(e.target.value)} />
                        </Form.Item>
                      </Col>
                      <Col span={8}>
                        <Form.Item label="Rule type">
                          <Select
                            value={ruleType}
                            onChange={setRuleType}
                            options={RULE_TYPES.map((t) => ({ value: t, label: t }))}
                          />
                        </Form.Item>
                      </Col>
                      <Col span={8}>
                        <Form.Item label="Effect">
                          <Select
                            value={effectType}
                            onChange={(v) => setEffectType(v as typeof effectType)}
                            options={[
                              { value: "allow", label: "allow" },
                              { value: "deny", label: "deny" },
                              { value: "require_action", label: "require_action" },
                              { value: "informational", label: "informational" },
                            ]}
                          />
                        </Form.Item>
                      </Col>
                      <Col span={8}>
                        <Form.Item label="Effect action" required>
                          <Input value={effectAction} onChange={(e) => setEffectAction(e.target.value)} placeholder="manager_approval" />
                        </Form.Item>
                      </Col>
                      <Col span={6}>
                        <Form.Item label="Priority">
                          <InputNumber style={{ width: "100%" }} value={priority} onChange={(v) => setPriority(Number(v ?? 0))} />
                        </Form.Item>
                      </Col>
                      <Col span={6}>
                        <Form.Item label="Authority owner" required>
                          <Input value={authorityOwner} onChange={(e) => setAuthorityOwner(e.target.value)} placeholder="finance-controls" />
                        </Form.Item>
                      </Col>
                      <Col span={6}>
                        <Form.Item label="Authority level">
                          <Input value={authorityLevel} onChange={(e) => setAuthorityLevel(e.target.value)} placeholder="corporate" />
                        </Form.Item>
                      </Col>
                      <Col span={6}>
                        <Form.Item label="Authority rank">
                          <InputNumber
                            style={{ width: "100%" }}
                            value={authorityRank}
                            onChange={(v) => setAuthorityRank(Number(v ?? 0))}
                          />
                        </Form.Item>
                      </Col>
                      <Col span={8}>
                        <Form.Item label="Effective from" required>
                          <DatePicker
                            style={{ width: "100%" }}
                            value={dayjs(draftEffectiveFrom)}
                            onChange={(d) => setDraftEffectiveFrom(d ? d.format("YYYY-MM-DD") : "")}
                          />
                        </Form.Item>
                      </Col>
                    </Row>

                    <ScopeFieldsEditor
                      scope={draftScope}
                      onScopeChange={setDraftScope}
                      isExplicitOverride={draftIsExplicitOverride}
                      onIsExplicitOverrideChange={setDraftIsExplicitOverride}
                      supersedesRuleIds={draftSupersedesRuleIds}
                      onSupersedesRuleIdsChange={setDraftSupersedesRuleIds}
                      supersedeCandidates={(activeVersionRules ?? []).map((r) => ({ rule_id: r.rule_id, title: r.title }))}
                      groupLabel={draftGroupLabel}
                      onGroupLabelChange={setDraftGroupLabel}
                      existingGroupLabels={(activeVersionRules ?? []).map((r) => r.group_label).filter(Boolean)}
                      relatedRuleIds={draftRelatedRuleIds}
                      onRelatedRuleIdsChange={setDraftRelatedRuleIds}
                    />

                    <Form.Item label="Condition (AND of comparisons — use Advanced mode for OR/NOT/nested logic)">
                      <Space direction="vertical" style={{ width: "100%" }} size={8}>
                        {conditionRows.map((row, i) => (
                          <Space.Compact key={i} style={{ width: "100%" }}>
                            <Input
                              placeholder="fact name"
                              value={row.fact}
                              onChange={(e) => updateConditionRow(i, { fact: e.target.value })}
                              style={{ width: "30%" }}
                            />
                            <Select
                              value={row.operator}
                              onChange={(v) => updateConditionRow(i, { operator: v })}
                              style={{ width: "30%" }}
                              options={OPERATORS.map((op) => ({ value: op, label: op }))}
                            />
                            <Input
                              placeholder="value"
                              value={row.value}
                              onChange={(e) => updateConditionRow(i, { value: e.target.value })}
                              style={{ width: "30%" }}
                            />
                            {conditionRows.length > 1 && (
                              <Button onClick={() => removeConditionRow(i)}>✕</Button>
                            )}
                          </Space.Compact>
                        ))}
                        <Button icon={<PlusOutlined />} onClick={addConditionRow}>
                          Add condition
                        </Button>
                      </Space>
                    </Form.Item>
                  </>
                )}

                <Button type="primary" htmlType="submit">
                  Submit for Review
                </Button>
              </Form>
                </Col>
              </Row>
            )}

            {queueIsEmpty ? (
              <div className="review-queue-empty">
                <Text strong>No candidate rules yet</Text>
                <Text type="secondary">
                  Rules appear here once a document has been added to this
                  project and an extraction run has finished. You can also write
                  one by hand with “Draft Candidate Rule” above.
                </Text>
              </div>
            ) : (
              <>
            <ReviewStatusTabs
              value={statusFilter}
              onChange={(v) => setStatusFilter(v as typeof statusFilter)}
              counts={facets?.status_totals ?? statusCounts}
              total={
                facets
                  ? Object.values(facets.status_totals).reduce((a, b) => a + b, 0)
                  : totalCandidates
              }
            />

            <dl className="review-operations-strip" aria-label="Review operations summary">
              <div>
                <dt>Decision progress</dt>
                <dd>{decisionProgress}%</dd>
                <small>{reviewedCount} of {totalCandidates} decided</small>
              </div>
              <div className={approvedUnpublished.length > 0 ? "review-operation-attention" : undefined}>
                <dt>Ready to publish</dt>
                <dd>{approvedUnpublished.length}</dd>
                <small>Approved, not live</small>
              </div>
              <div>
                <dt>Related families</dt>
                <dd>{bandedFamilyCount}</dd>
                <small>
                  {unfamiliedCount > 0
                    ? `${unfamiliedCount} of ${totalCandidates} stand alone`
                    : "In the current view"}
                </small>
              </div>
              <div>
                <dt>Quality findings</dt>
                <dd>{qualityScan.display}</dd>
                <small>{qualityScan.caption}</small>
              </div>
            </dl>

            <ReviewFilterBar
              facets={facets}
              documentFilter={documentFilter}
              runFilter={runFilter}
              deltaFilter={deltaFilter}
              showRemoved={showRemoved}
              onDocument={setDocumentFilter}
              onRun={setRunFilter}
              onDelta={setDeltaFilter}
              onToggleRemoved={() => setShowRemoved((v) => !v)}
              onRefresh={() => {
                void loadCandidates();
                void loadFacets();
              }}
            />

            <Space size={16} wrap className="review-controls-bar" style={{ marginBottom: 16 }}>
              <Input
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                placeholder="Search title, description, action, rule ID, tag…"
                prefix={<SearchOutlined />}
                allowClear
                style={{ width: 300 }}
              />
              <Tooltip title="Run an AI + deterministic quality scan over unpublished candidates (findings appear as badges below)">
                <Button icon={<SafetyCertificateOutlined />} onClick={runQualityCheck} loading={qualityLoading}>
                  {qualityFindings ? "Re-run quality check" : "Run quality check"}
                </Button>
              </Tooltip>
              <ExportMenu
                label="Export this filter"
                size="middle"
                onExport={(format) =>
                  api.exportCandidateRules(selectedKey, format, statusFilter === "all" ? undefined : statusFilter)
                }
              />
              {(bandedFamilyCount > 0 || unfamiliedCount > 0) && (
                <Tooltip
                  title={
                    <>
                      <div>
                        Rules that are variations of one decision share a coloured spine on the left edge, using
                        the same criterion as the Policies view:
                      </div>
                      <div style={{ marginTop: 6 }}>
                        1. a curated <b>variation group</b> on the rule, when set; otherwise
                      </div>
                      <div>2. same rule type testing the same fact with differing values.</div>
                      {unfamiliedCount > 0 && (
                        <div style={{ marginTop: 8 }}>
                          {unfamiliedCount} rule{unfamiliedCount === 1 ? "" : "s"} here match neither, so
                          {unfamiliedCount === 1 ? " it is" : " they are"} shown standing alone. A variation
                          group is only set when one DMN decision covers two or more rules, and the fact
                          test needs a projected condition — so rules extracted without a fact model have
                          nothing to group on. That is reported rather than guessed at: relating them on
                          wording or position would assert a link the document never made.
                        </div>
                      )}
                    </>
                  }
                >
                  <Tag
                    icon={<ClusterOutlined />}
                    color={bandedFamilyCount > 0 ? "blue" : "default"}
                    style={{ cursor: "help", marginInlineEnd: 0 }}
                  >
                    {bandedFamilyCount > 0
                      ? `${bandedFamilyCount} banded ${bandedFamilyCount === 1 ? "family" : "families"}`
                      : "No families derived"}
                  </Tag>
                </Tooltip>
              )}
            </Space>

            {qualityError && <Alert type="warning" showIcon message={qualityError} style={{ marginBottom: 16 }} closable onClose={() => setQualityError(null)} />}

            {selectionNote && (
              <Text
                type="secondary"
                data-testid="policy-selection-note"
                style={{ display: "block", marginBottom: 12 }}
              >
                {selectionNote}
              </Text>
            )}

            {selectableIds.length > 0 && (
              <div className="bulk-bar">
                <Space size={16} wrap style={{ width: "100%", justifyContent: "space-between" }}>
                  <Checkbox
                    checked={selectedIds.size === selectableIds.length && selectableIds.length > 0}
                    onChange={toggleSelectAllVisible}
                  >
                    {selectedIds.size > 0
                      ? grouped
                        ? `${selectedPolicyCount} ${selectedPolicyCount === 1 ? "policy" : "policies"} selected · ${selectedIds.size} ${selectedIds.size === 1 ? "rule" : "rules"}`
                        : `${selectedIds.size} selected`
                      : grouped
                        ? `Select all ${policyCards.length} ${policyCards.length === 1 ? "policy" : "policies"} in this filter`
                        : `Select all ${selectableIds.length} in this filter`}
                  </Checkbox>
                  <Space>
                    <Button
                      type="primary"
                      disabled={selectedIds.size === 0 || bulkBusy}
                      loading={bulkBusy}
                      onClick={() => handleBulkReview("approve")}
                    >
                      Approve selected ({selectedIds.size})
                    </Button>
                    <Button danger disabled={selectedIds.size === 0 || bulkBusy} onClick={() => handleBulkReview("reject")}>
                      Reject selected
                    </Button>
                  </Space>
                </Space>
              </div>
            )}

            {loading ? (
              <Text type="secondary">Loading…</Text>
            ) : (
              <div
                className={`review-workspace review-workspace--${isDesktop ? "desktop" : "narrow"}${
                  isDesktop ? ` review-workspace--${workspaceMode}` : ""
                }`}
              >
                {(!isDesktop || workspaceMode !== "detail") && (
                  <div className="review-workspace-list">
                    {policiesState === "unavailable" && (
                      <Alert
                        type="warning"
                        showIcon
                        style={{ marginBottom: 12 }}
                        message="The passage grouping could not be loaded, so these rules are listed one at a time."
                        description={
                          <>
                            {policiesError}{" "}
                            Every rule below is still here and still reviewable — what is missing is which
                            of them the source stated together, so a decision made here covers one rule
                            rather than one policy.
                          </>
                        }
                      />
                    )}
                    <div
                      className="candidate-list"
                      role="listbox"
                      aria-label={grouped ? "Policies" : "Candidate rules"}
                    >
                      {grouped &&
                        pagedPolicyCards.map((card) => {
                          const selectedCount = card.reviewableIds.filter((id) => selectedIds.has(id)).length;
                          return (
                            <PolicyReviewCard
                              key={card.policy.key}
                              card={card}
                              selected={
                                card.reviewableIds.length > 0 && selectedCount === card.reviewableIds.length
                              }
                              indeterminate={selectedCount > 0 && selectedCount < card.reviewableIds.length}
                              open={openPolicyKey === card.policy.key}
                              statusColor={(status) => STATUS_COLOR[status] ?? "default"}
                              statusLabel={(status) => STATUS_LABEL[status] ?? status}
                              findingsFor={(ruleId) => (qualityFindings?.get(ruleId) ?? []).length}
                              onToggleSelect={() => togglePolicySelected(card)}
                              onOpen={() => openPolicy(card)}
                              onApprove={
                                card.reviewableIds.length > 0
                                  ? () => requestReview(card.reviewableIds, "approve")
                                  : undefined
                              }
                              onReject={
                                card.reviewableIds.length > 0
                                  ? () => requestReview(card.reviewableIds, "reject")
                                  : undefined
                              }
                              onSelectRule={selectCandidateRuleById}
                              selectedRuleId={selectedCandidateId}
                              documentName={documentNameOf(card.policy.document_version_id)}
                            />
                          );
                        })}
                      {grouped && page === 1 && unplaced.length > 0 && (
                        <div className="review-unplaced">
                          <Text type="secondary">
                            {unplaced.length === 1
                              ? "1 rule below was not placed in a passage by the assembly"
                              : `${unplaced.length} rules below were not placed in a passage by the assembly`}
                            {runFilter
                              ? " — a historical run is open, and rules a later run retired are not assembled into passages."
                              : "."}{" "}
                            They are shown one at a time so nothing is dropped from the queue.
                          </Text>
                        </div>
                      )}
                      {(!grouped ? pagedCandidates : page === 1 ? unplaced : []).map((candidate) => {
                        const findings = qualityFindings?.get(candidate.rule.rule_id) ?? [];
                        const editability = candidateEditability(candidate.review_status);
                        const cluster = clusterMap.get(candidate.rule.rule_id);
                        const band = bandInfo.get(candidate.rule.rule_id);
                        return (
                          <div key={candidate.id} className="candidate-item">
                            {cluster && band?.isStart && (
                              <FamilyCompositeHeader
                                cluster={cluster}
                                members={cluster.members}
                                accent={clusterColor(cluster)}
                                memberCountInView={band.total}
                              />
                            )}
                            <CandidateRow
                              candidate={candidate}
                              active={selectedCandidateId === candidate.id}
                              selected={selectedIds.has(candidate.id)}
                              selectable={editability.canReview}
                              cluster={cluster}
                              clusterColor={cluster ? clusterColor(cluster) : undefined}
                              band={band}
                              findingsCount={findings.length}
                              statusColor={STATUS_COLOR[candidate.review_status] ?? "default"}
                              statusLabel={STATUS_LABEL[candidate.review_status] ?? candidate.review_status}
                              renderDetail={() => (
                                <RuleDetailInline
                                  candidate={candidate}
                                  onOpenFullRecord={() => openCandidate(candidate)}
                                />
                              )}
                              onOpenFullRecord={() => openCandidate(candidate)}
                              recordActions={ruleActionHandlers(candidate, () => openCandidate(candidate))}
                              onToggleSelect={() => toggleSelected(candidate.id)}
                              onSelectFamily={
                                cluster && editability.canReview ? () => selectFamily(candidate.rule.rule_id) : undefined
                              }
                              onApprove={
                                editability.canReview ? () => handleReview(candidate.id, "approve") : undefined
                              }
                              onReject={
                                editability.canReview ? () => handleReview(candidate.id, "reject") : undefined
                              }
                            />
                          </div>
                        );
                      })}
                      {filteredCandidates.length === 0 && (
                        <div className="review-empty-state">
                          {emptyState.status === "success" ? (
                            <Alert type="success" showIcon message={emptyState.title} description={emptyState.detail} />
                          ) : (
                            <Empty description={emptyState.title}>
                              {emptyState.detail && <Text type="secondary">{emptyState.detail}</Text>}
                            </Empty>
                          )}
                        </div>
                      )}
                    </div>
                    {listTotal > PAGE_SIZE && (
                      <div className="candidate-pagination">
                        <Pagination
                          current={page}
                          pageSize={PAGE_SIZE}
                          total={listTotal}
                          onChange={setPage}
                          showSizeChanger={false}
                          showTotal={(total, range) =>
                            grouped
                              ? `${range[0]}–${range[1]} of ${total} policies`
                              : `${range[0]}–${range[1]} of ${total} candidates`
                          }
                        />
                      </div>
                    )}
                  </div>
                )}
                {isDesktop && workspaceMode !== "list" && (
                  <>
                    {inspectorFullscreen && (
                      <button
                        type="button"
                        className="policy-inspector-backdrop"
                        onClick={() => setInspectorFullscreen(false)}
                        aria-label="Restore review workspace"
                      />
                    )}
                    <div
                      className={`review-workspace-inspector${
                        inspectorFullscreen ? " review-workspace-inspector--fullscreen" : ""
                      }`}
                    >
                      {candidateInspector}
                    </div>
                  </>
                )}
              </div>
            )}
              </>
            )}
            </div>
          </section>

          {!queueIsEmpty && (
          <section className="project-overview-panel publish-card">
            <div className="project-overview-panel__header">
              <div>
                <Text strong>Publish approved candidates</Text>
                <Text type="secondary">Create the next immutable policy version</Text>
              </div>
              <Tag color={approvedUnpublished.length > 0 ? "gold" : "default"}>
                {approvedUnpublished.length} ready
              </Tag>
            </div>
            <div className="project-overview-panel__body">
            <Paragraph type="secondary">
              {approvedUnpublished.length} approved candidate(s) ready to publish into a new version, carrying forward
              all rules from the current active version.
            </Paragraph>
            {publishDiff && approvedUnpublished.length > 0 && (
              <Space wrap style={{ marginBottom: 16 }}>
                <Tag color="green">{publishDiff.netNew.length} net-new rule(s)</Tag>
                <Tag color="gold">{publishDiff.superseding.length} superseding existing rule(s)</Tag>
                <Tag>{publishDiff.unchangedCount} unchanged carried forward</Tag>
              </Space>
            )}
            <Form layout="vertical" onSubmitCapture={handlePublish}>
              {!identity.trim() && (
                <Alert
                  type="warning"
                  showIcon
                  message="Set your name in the application header before publishing."
                  className="publish-identity-warning"
                />
              )}
              <Form.Item label="Effective from" required className="publish-effective-field">
                <DatePicker
                  value={dayjs(effectiveFrom)}
                  onChange={(d) => setEffectiveFrom(d ? d.format("YYYY-MM-DD") : "")}
                />
              </Form.Item>
              <Button
                type="primary"
                htmlType="submit"
                disabled={approvedUnpublished.length === 0 || !identity.trim()}
              >
                Publish New Version
              </Button>
            </Form>
            {publishResult && (
              <Alert
                type="success"
                showIcon
                style={{ marginTop: 16 }}
                message={`Published: version ${publishResult.version_number}, ${publishResult.rule_count} rule(s)`}
              />
            )}
            </div>
          </section>
          )}
        </>
      )}

      {!isDesktop && (
        <Drawer
          open={mobileInspectorOpen && !!selectedCandidate}
          onClose={() => setMobileInspectorOpen(false)}
          placement="right"
          size="100%"
          closable={false}
          styles={{ body: { padding: 0 } }}
          className="policy-inspector-drawer"
        >
          {candidateInspector}
        </Drawer>
      )}

      {rewriteTarget && (
        <RewriteModal candidate={rewriteTarget} onClose={() => setRewriteTarget(null)} onApplied={() => void loadCandidates()} />
      )}
      {editTarget && (
        <EditRuleModal
          policySetKey={selectedKey}
          candidate={editTarget}
          allRules={activeVersionRules ?? []}
          onClose={() => setEditTarget(null)}
          onApplied={() => void loadCandidates()}
        />
      )}
      {managerAction && (
        <ManagerActionModal
          policySetKey={selectedKey}
          candidate={managerAction.candidate}
          mode={managerAction.mode}
          onClose={() => setManagerAction(null)}
          onApplied={() => void loadCandidates()}
        />
      )}
      {askTarget && <AskAboutRuleModal candidate={askTarget} onClose={() => setAskTarget(null)} />}
      {previousUnderReview && (
        <Modal
          open
          width={960}
          title={`Previous version — ${previousUnderReview.rule.rule_id}`}
          footer={null}
          onCancel={() => setPreviousUnderReview(null)}
        >
          {/* Read-only. This record was replaced; it is here so a reviewer can
              see what the earlier run made of the same sentence, not so it can
              be acted on. */}
          <PolicyInspector
            rule={previousUnderReview.rule}
            recordKind="candidate"
            activeTabKey={previousTab}
            onTabChange={setPreviousTab}
          />
        </Modal>
      )}
      <FamilyReviewConfirm
        open={familyPrompt !== null}
        gaps={familyPrompt?.gaps ?? []}
        decision={familyPrompt?.decision ?? "approve"}
        busy={bulkBusy}
        onCancel={() => setFamilyPrompt(null)}
        onProceedPartial={() => familyPrompt && void runReview(familyPrompt.ids, familyPrompt.decision)}
        onProceedWholeFamily={() => {
          if (!familyPrompt) return;
          const whole = new Set([...familyPrompt.ids, ...idsCoveringFamilies(familyPrompt.gaps)]);
          void runReview(Array.from(whole), familyPrompt.decision);
        }}
      />
    </>
  );
}
