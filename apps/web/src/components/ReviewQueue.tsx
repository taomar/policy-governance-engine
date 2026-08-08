import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  App,
  Button,
  Card,
  Checkbox,
  Col,
  DatePicker,
  Empty,
  Form,
  Input,
  InputNumber,
  Pagination,
  Progress,
  Row,
  Segmented,
  Select,
  Space,
  Statistic,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import {
  BulbOutlined,
  ClusterOutlined,
  EditOutlined,
  ExclamationCircleOutlined,
  PlusOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
  SendOutlined,
  ThunderboltOutlined,
  UserOutlined,
} from "@ant-design/icons";
import dayjs from "dayjs";
import {
  aiApi,
  api,
  PolicyPlatformApiError,
  type ApprovedPolicyVersion,
  type CandidateRule,
  type CanonicalRule,
  type PolicySet,
  type ReviewFacets,
  type PolicyScope,
  type QualityFinding,
} from "../api";
import { RuleCard } from "./RuleCard";
import { RewriteModal } from "./RewriteModal";
import { EditRuleModal } from "./EditRuleModal";
import { ManagerActionModal } from "./ManagerActionModal";
import { AskAboutRuleModal } from "./AskAboutRuleModal";
import { AiRuleComposer } from "./AiRuleComposer";
import { ImmutableFieldsNotice } from "./ImmutableFieldsNotice";
import { NotesPanel } from "./NotesPanel";
import { ExportMenu } from "./ExportMenu";
import { ScopeFieldsEditor } from "./ScopeEditor";
import { EMPTY_SCOPE, normalizeScope } from "../scopeUtils";
import { candidateEditability } from "../candidateEditability";
import { buildVariationClusters, clusterColor, clusterIdentity } from "../ruleDisplay";
import { computeBandGeometry } from "../bandGeometry";
import { familyGaps, familyMembers, idsCoveringFamilies, type FamilyGap } from "../ruleFamilyReview";
import { FamilyReviewConfirm } from "./FamilyReviewConfirm";
import {
  buildCondition,
  conditionToRows,
  isVacuousCondition,
  CONDITION_OPERATORS,
  type ConditionRow,
} from "../conditionRows";
import { useActor } from "../ActorContext";
import { RULE_TYPES } from "../ruleTypes";
import { CandidateRow } from "./CandidateRow";
import { ReviewFilterBar, DELTA_META } from "./ReviewFilterBar";
import { ReviewStatusTabs } from "./ReviewStatusTabs";
import { RuleChangeExplainer } from "./RuleChangeExplainer";

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

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
  const scoped = Boolean(policySetKey);
  const { actor, setActor } = useActor();
  const { message } = App.useApp();
  const [policySets, setPolicySets] = useState<PolicySet[]>([]);
  const [selectedKey, setSelectedKey] = useState<string>(policySetKey ?? "");
  const [candidates, setCandidates] = useState<CandidateRule[]>([]);
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
  const [contentKind, setContentKind] = useState<"policies" | "definitions">("policies");
  const [searchText, setSearchText] = useState("");
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

  // Candidate list rendering — each row starts collapsed (RuleCard's own
  // detail body, its per-evidence resolution effect, and the discussion
  // NotesPanel all only mount for rows the reviewer actually opens), plus
  // client-side pagination so at most PAGE_SIZE rows exist in the DOM at
  // once. Without this, a queue the size of a real extracted document (300+
  // pending candidates) rendered every row fully expanded on load — a
  // confirmed live scalability bug (346 candidates × full detail + a
  // separate notes fetch each, all mounted simultaneously).
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [page, setPage] = useState(1);
  const PAGE_SIZE = 20;

  // Readiness/quality findings — lazy-loaded on demand (triggers a real AI call),
  // grouped client-side by affected rule_id so each candidate can show a small badge.
  const [qualityFindings, setQualityFindings] = useState<Map<string, QualityFinding[]> | null>(null);
  const [qualityLoading, setQualityLoading] = useState(false);
  const [qualityError, setQualityError] = useState<string | null>(null);

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
      .catch((e) => setError(e instanceof PolicyPlatformApiError ? e.detail : String(e)));
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
  // Binding both fields to the actor removes that class of bug instead of adding
  // a third sync to paper over it: identity is entered once, anywhere, applies
  // everywhere, and persists across reloads. `actor.role` still carries the
  // reviewer-vs-manager distinction, which is the part that genuinely differs.
  const identity = actor.name;
  const setIdentity = (name: string) => setActor({ ...actor, name });

  const loadCandidates = async () => {
    if (!selectedKey) return;
    setError(null);
    setLoading(true);
    try {
      const status = statusFilter === "all" ? undefined : statusFilter;
      const list = await api.listCandidateRules(selectedKey, status, {
        document_id: documentFilter || undefined,
        extraction_run_id: runFilter || undefined,
        delta_status: deltaFilter === "all" ? undefined : deltaFilter,
        // Opening a historical run means asking for rules a later run retired,
        // so those rows have to be included or the run would look empty.
        include_superseded: Boolean(runFilter),
      });
      setCandidates(list);
    } catch (e) {
      setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
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

  useEffect(() => {
    void loadCandidates();
    setQualityFindings(null); // stale once the policy set/filter changes — re-run on demand
    setExpandedIds(new Set());
    setPage(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedKey, statusFilter, documentFilter, runFilter, deltaFilter]);

  useEffect(() => {
    void loadFacets();
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
    } catch (e) {
      setQualityError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
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
      const detail = e instanceof PolicyPlatformApiError ? e.detail : String(e);
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

  const toggleExpanded = (candidateId: string) =>
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(candidateId)) next.delete(candidateId);
      else next.add(candidateId);
      return next;
    });

  // Definitions/glossary entries (rule_type "definition" — both the AI's
  // "definition" and "classification" canonical types map here in
  // formulation_mapping.py) describe terms, not obligations: they have no
  // real condition/effect to evaluate and read very differently from
  // operative rules. Reviewing them interleaved with obligations/
  // prohibitions/eligibility rules buried both — a glossary entry's "Approve"
  // looks identical to a real policy's, so a reviewer scanning for
  // enforceable rules had to mentally filter dozens of "X is defined as Y"
  // rows out of the list. Splitting by content kind lets a reviewer clear
  // the glossary in one pass, then focus entirely on rules that actually
  // constrain behavior.
  const isDefinitionKind = (ruleType: string) => ruleType === "definition";

  const contentKindCounts = useMemo(() => {
    let definitions = 0;
    for (const c of candidates) if (isDefinitionKind(c.rule_type)) definitions += 1;
    return { definitions, policies: candidates.length - definitions };
  }, [candidates]);

  const filteredCandidates = useMemo(() => {
    const q = searchText.trim().toLowerCase();
    return candidates.filter((c) => {
      if (isDefinitionKind(c.rule_type) !== (contentKind === "definitions")) return false;
      if (!q) return true;
      const r = c.rule;
      return (
        r.title.toLowerCase().includes(q) ||
        r.description.toLowerCase().includes(q) ||
        r.rule_id.toLowerCase().includes(q) ||
        r.effect.action.toLowerCase().includes(q) ||
        (r.category ?? "").toLowerCase().includes(q) ||
        (r.tags ?? []).some((t) => t.toLowerCase().includes(q)) ||
        (r.group_label ?? "").toLowerCase().includes(q)
      );
    });
  }, [candidates, searchText, contentKind]);

  // Reset to page 1 whenever the search or content-kind tab narrows/widens
  // the filtered set, so the reviewer never lands on a now-empty trailing page.
  useEffect(() => {
    setPage(1);
  }, [searchText, contentKind]);

  const pagedCandidates = useMemo(
    () => filteredCandidates.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE),
    [filteredCandidates, page]
  );

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

  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const c of candidates) counts[c.review_status] = (counts[c.review_status] ?? 0) + 1;
    return counts;
  }, [candidates]);

  const selectableIds = filteredCandidates
    .filter((c) => candidateEditability(c.review_status).canReview)
    .map((c) => c.id);

  const toggleSelectAllVisible = () =>
    setSelectedIds((prev) => (prev.size === selectableIds.length ? new Set() : new Set(selectableIds)));

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

  const handlePublish = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setPublishResult(null);
    try {
      const version = await api.publishCandidates(selectedKey, {
        approved_by: identity,
        effective_from: effectiveFrom,
        is_active: true,
      });
      setPublishResult(version);
      await loadCandidates();
    } catch (e) {
      setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
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
          // Only override the generated condition once the user has actually
          // entered one; an untouched form must not silently replace extracted
          // logic with an empty conjunction.
          condition:
            filledRows.length > 0
              ? buildCondition(filledRows)
              : (aiGeneratedRule?.condition ?? buildCondition([])),
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
      setDraftError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    }
  };

  const addConditionRow = () => setConditionRows((rows) => [...rows, { fact: "", operator: "greaterThan", value: "" }]);
  const updateConditionRow = (i: number, patch: Partial<ConditionRow>) =>
    setConditionRows((rows) => rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
  const removeConditionRow = (i: number) => setConditionRows((rows) => rows.filter((_, idx) => idx !== i));

  const approvedUnpublished = candidates.filter((c) => c.review_status === "approved");
  const totalCandidates = candidates.length;

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

  return (
    <>
      <div className="page-header-row">
        <Title level={3} style={{ margin: 0 }}>
          Review Queue
        </Title>
        {!scoped && (
          <Select
            value={selectedKey}
            onChange={setSelectedKey}
            style={{ minWidth: 220 }}
            options={policySets.map((ps) => ({ value: ps.key, label: ps.name }))}
          />
        )}
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

      {selectedKey && totalCandidates > 0 && (
        <Card size="small" className="progress-stats-bar" style={{ marginBottom: 16 }}>
          <Row gutter={24} align="middle">
            <Col flex="220px">
              <Statistic title="Total rules" value={totalCandidates} />
            </Col>
            <Col flex="auto">
              <Progress
                percent={publishedPct}
                success={{ percent: publishedPct }}
                format={() => `${statusCounts.published ?? 0} published`}
              />
            </Col>
            <Col>
              <Space size={[6, 6]} wrap>
                {STATUS_FILTERS.filter((s) => s !== "all").map((s) => (
                  <Tag key={s} color={STATUS_COLOR[s]} style={{ margin: 0 }}>
                    {STATUS_LABEL[s]}: {statusCounts[s] ?? 0}
                  </Tag>
                ))}
              </Space>
            </Col>
          </Row>
        </Card>
      )}

      {selectedKey && (
        <>
          <Card
            title="Candidate Rules"
            className="modern-card"
            extra={
              <Button
                type={showDraftForm ? "default" : "primary"}
                icon={!showDraftForm && <PlusOutlined />}
                onClick={() => setShowDraftForm((v) => !v)}
              >
                {showDraftForm ? "Cancel" : "Draft Candidate Rule"}
              </Button>
            }
          >
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

            <Segmented
              value={contentKind}
              onChange={(v) => setContentKind(v as typeof contentKind)}
              style={{ marginBottom: 16, marginTop: 16 }}
              options={[
                { label: `Policies & Rules (${contentKindCounts.policies})`, value: "policies" },
                { label: `Definitions & Glossary (${contentKindCounts.definitions})`, value: "definitions" },
              ]}
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
              <Space>
                <Text>Reviewing as</Text>
                <Tooltip title="This is your identity across the whole app — the same name shown in the header and used when publishing a version. Set it once here or there.">
                  <Input
                    value={identity}
                    onChange={(e) => setIdentity(e.target.value)}
                    placeholder="your name"
                    prefix={<UserOutlined />}
                    status={identity.trim() ? undefined : "warning"}
                    style={{ width: 180 }}
                  />
                </Tooltip>
              </Space>
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
              {bandedFamilyCount > 0 && (
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
                    </>
                  }
                >
                  <Tag icon={<ClusterOutlined />} color="blue" style={{ cursor: "help", marginInlineEnd: 0 }}>
                    {bandedFamilyCount} banded {bandedFamilyCount === 1 ? "family" : "families"}
                  </Tag>
                </Tooltip>
              )}
            </Space>

            {qualityError && <Alert type="warning" showIcon message={qualityError} style={{ marginBottom: 16 }} closable onClose={() => setQualityError(null)} />}

            {selectableIds.length > 0 && (
              <Card size="small" className="bulk-bar" style={{ marginBottom: 16 }}>
                <Space size={16} wrap style={{ width: "100%", justifyContent: "space-between" }}>
                  <Checkbox
                    checked={selectedIds.size === selectableIds.length && selectableIds.length > 0}
                    onChange={toggleSelectAllVisible}
                  >
                    {selectedIds.size > 0 ? `${selectedIds.size} selected` : `Select all ${selectableIds.length} in this filter`}
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
              </Card>
            )}

            {loading ? (
              <Text type="secondary">Loading…</Text>
            ) : (
              <>
                <Space direction="vertical" style={{ width: "100%" }} size={8} className="candidate-list">
                  {pagedCandidates.map((c) => {
                    const findings = qualityFindings?.get(c.rule.rule_id) ?? [];
                    const editability = candidateEditability(c.review_status);
                    const isReviewable = editability.canReview;
                    const cluster = clusterMap.get(c.rule.rule_id);
                    const isExpanded = expandedIds.has(c.id);
                    return (
                      <div key={c.id} className="candidate-item">
                        <CandidateRow
                          candidate={c}
                          expanded={isExpanded}
                          selected={selectedIds.has(c.id)}
                          selectable={isReviewable}
                          cluster={cluster}
                          clusterColor={cluster ? clusterColor(cluster) : undefined}
                          band={bandInfo.get(c.rule.rule_id)}
                          findingsCount={findings.length}
                          statusColor={STATUS_COLOR[c.review_status] ?? "default"}
                          statusLabel={STATUS_LABEL[c.review_status] ?? c.review_status}
                          onToggleExpand={() => toggleExpanded(c.id)}
                          onToggleSelect={() => toggleSelected(c.id)}
                          onSelectFamily={cluster && editability.canReview ? () => selectFamily(c.rule.rule_id) : undefined}
                          onApprove={isReviewable ? () => handleReview(c.id, "approve") : undefined}
                          onReject={isReviewable ? () => handleReview(c.id, "reject") : undefined}
                        />
                        {isExpanded && (
                          <div className="candidate-item-detail">
                            <RuleCard rule={c.rule} defaultExpanded hideNotes />
                            {c.baseline_candidate_id && (
                              <div className="candidate-change-slot">
                                <RuleChangeExplainer candidateId={c.id} />
                              </div>
                            )}
                            {findings.length > 0 && (
                              <div className="readiness-badges">
                                {findings.map((f, fi) => (
                                  <Tooltip key={fi} title={f.recommendation}>
                                    <Tag
                                      icon={<ExclamationCircleOutlined />}
                                      color={f.severity === "high" ? "red" : f.severity === "medium" ? "gold" : "default"}
                                    >
                                      {f.category}: {f.finding}
                                    </Tag>
                                  </Tooltip>
                                ))}
                              </div>
                            )}
                            <div className="candidate-item-footer">
                              <Space size={10} wrap>
                                <Text type="secondary" className="entity-id-row" copyable={{ text: c.id }}>
                                  {c.id}
                                </Text>
                                {c.reviewed_by && <Text type="secondary">reviewed by {c.reviewed_by}</Text>}
                                {c.review_notes && <Text type="secondary">— {c.review_notes}</Text>}
                              </Space>
                              <Space size={8} wrap>
                                <Button size="small" icon={<BulbOutlined />} onClick={() => setAskTarget(c)}>
                                  Ask AI about this rule
                                </Button>
                                <Tooltip title={editability.editBlockedReason ?? "Change this rule's wording, conditions or effect"}>
                                  <Button
                                    size="small"
                                    icon={<EditOutlined />}
                                    disabled={!editability.canEdit}
                                    onClick={() => setEditTarget(c)}
                                  >
                                    Edit
                                  </Button>
                                </Tooltip>
                                {isReviewable && (
                                  <>
                                    <Button size="small" icon={<ThunderboltOutlined />} onClick={() => setRewriteTarget(c)}>
                                      Suggest Rewrite
                                    </Button>
                                    <Button size="small" type="primary" onClick={() => handleReview(c.id, "approve")}>
                                      Approve
                                    </Button>
                                    <Button size="small" danger onClick={() => handleReview(c.id, "reject")}>
                                      Reject
                                    </Button>
                                  </>
                                )}
                                {c.review_status === "approved" && (
                                  <>
                                    <Tooltip title={isManager ? "Send back to the composer for rework" : "Manager role required"}>
                                      <Button
                                        size="small"
                                        icon={<SendOutlined />}
                                        disabled={!isManager}
                                        onClick={() => setManagerAction({ candidate: c, mode: "request-changes" })}
                                      >
                                        Send back for changes
                                      </Button>
                                    </Tooltip>
                                    <Tooltip title={isManager ? "Override this decision to Rejected" : "Manager role required"}>
                                      <Button
                                        size="small"
                                        danger
                                        disabled={!isManager}
                                        onClick={() => setManagerAction({ candidate: c, mode: "override-reject" })}
                                      >
                                        Override & Reject
                                      </Button>
                                    </Tooltip>
                                  </>
                                )}
                                {c.review_status === "rejected" && isManager && (
                                  <Tooltip title="Override this decision to Approved">
                                    <Button
                                      size="small"
                                      onClick={() => setManagerAction({ candidate: c, mode: "override-approve" })}
                                    >
                                      Override & Approve
                                    </Button>
                                  </Tooltip>
                                )}
                              </Space>
                            </div>
                            <NotesPanel entityType="candidate_rule" entityId={c.id} title="Review discussion" compact />
                          </div>
                        )}
                      </div>
                    );
                  })}
                  {filteredCandidates.length === 0 && (
                    <div className="review-empty-state">
                      {emptyState.status === "success" ? (
                        <Alert
                          type="success"
                          showIcon
                          message={emptyState.title}
                          description={emptyState.detail}
                        />
                      ) : (
                        <Empty description={emptyState.title}>
                          {emptyState.detail && <Text type="secondary">{emptyState.detail}</Text>}
                        </Empty>
                      )}
                    </div>
                  )}
                </Space>
                {filteredCandidates.length > PAGE_SIZE && (
                  <div className="candidate-pagination">
                    <Pagination
                      current={page}
                      pageSize={PAGE_SIZE}
                      total={filteredCandidates.length}
                      onChange={setPage}
                      showSizeChanger={false}
                      showTotal={(total, range) => `${range[0]}–${range[1]} of ${total} candidates`}
                    />
                  </div>
                )}
              </>
            )}
          </Card>

          <Card title="Publish Approved Candidates" className="modern-card publish-card">
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
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item
                    label="Approved by"
                    required
                    extra="Your identity across the app — the same name you review under."
                  >
                    <Input
                      value={identity}
                      onChange={(e) => setIdentity(e.target.value)}
                      placeholder="your name"
                      prefix={<UserOutlined />}
                    />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="Effective from" required>
                    <DatePicker
                      style={{ width: "100%" }}
                      value={dayjs(effectiveFrom)}
                      onChange={(d) => setEffectiveFrom(d ? d.format("YYYY-MM-DD") : "")}
                    />
                  </Form.Item>
                </Col>
              </Row>
              <Button type="primary" htmlType="submit" disabled={approvedUnpublished.length === 0}>
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
          </Card>
        </>
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
