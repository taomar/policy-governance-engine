import { useCallback, useEffect, useState } from "react";
import { Alert, Space, Spin, Tag, Tooltip, Typography } from "antd";
import { DatabaseOutlined, InboxOutlined, QuestionCircleOutlined } from "@ant-design/icons";
import { api, PolicyPlatformApiError, type ApprovedPolicyVersion } from "../api";

const { Text } = Typography;

/**
 * Several pages (Quality, Tests, Aggregate Limits) run an action against a subject
 * they never actually named: "Run Quality Evaluation" and "Propose tests with AI"
 * both described *what they do* while leaving *what they do it to* invisible. A
 * reviewer could not tell whether a run would cover 7 rules or 190, nor why a
 * button failed when the policy set had never been published.
 *
 * That was one cross-cutting defect rather than three page-level ones, so the fix
 * lives here once. `useEvaluationTarget` resolves the two real subjects in the
 * system — the active published version and the unpublished candidate pool — and
 * `EvaluationTargetBanner` states the resolved subject before the user commits to
 * an action, including when the subject is empty.
 *
 * Counts are deliberately fetched here rather than passed in: a caller that has to
 * remember to supply them is a caller that can forget, which is how the original
 * defect appeared on three pages at once.
 */

export type TargetScope = "published" | "candidates";

export interface EvaluationTargetState {
  version: ApprovedPolicyVersion | null;
  /** Rules the candidate-scoped actions would actually read: candidate + approved, never rejected. */
  candidateCount: number | null;
  loading: boolean;
  /** Set only when the lookup itself failed — "no published version" is a valid state, not an error. */
  error: string | null;
  reload: () => void;
}

export function useEvaluationTarget(policySetKey: string): EvaluationTargetState {
  const [version, setVersion] = useState<ApprovedPolicyVersion | null>(null);
  const [candidateCount, setCandidateCount] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!policySetKey) return;
    setLoading(true);
    setError(null);
    // A policy set with no active version is the normal state before the first
    // publish, so a 404 here is information, not a failure. Only unexpected
    // errors are surfaced, otherwise the banner would cry wolf on every new
    // project and reviewers would learn to ignore it.
    const [versionResult, facetsResult] = await Promise.allSettled([
      api.getActiveVersion(policySetKey),
      api.reviewFacets(policySetKey),
    ]);

    if (versionResult.status === "fulfilled") {
      setVersion(versionResult.value);
    } else {
      const reason = versionResult.reason;
      setVersion(null);
      if (reason instanceof PolicyPlatformApiError && reason.status !== 404) {
        setError(reason.detail);
      }
    }

    if (facetsResult.status === "fulfilled") {
      const totals = facetsResult.value.status_totals ?? {};
      setCandidateCount((totals.candidate ?? 0) + (totals.approved ?? 0));
    } else {
      setCandidateCount(null);
    }

    setLoading(false);
  }, [policySetKey]);

  useEffect(() => {
    void load();
  }, [load]);

  return { version, candidateCount, loading, error, reload: () => void load() };
}

/**
 * Names the concrete subject an action will run against. `scope` picks which
 * subject; `actionLabel` is the verb the caller's button uses, so the warning can
 * say exactly which button will not work and why.
 */
export function EvaluationTargetBanner({
  scope,
  target,
  actionLabel,
  emptyHint,
}: {
  scope: TargetScope;
  target: EvaluationTargetState;
  actionLabel: string;
  /** What the user should do instead when the subject is empty. */
  emptyHint?: string;
}) {
  const { version, candidateCount, loading, error } = target;

  if (loading && !version && candidateCount === null) {
    return (
      <div className="eval-target eval-target-loading">
        <Spin size="small" />
        <Text type="secondary">Resolving what this will run against…</Text>
      </div>
    );
  }

  if (error) {
    return <Alert type="error" showIcon message={`Could not determine what ${actionLabel} would run against: ${error}`} />;
  }

  if (scope === "published") {
    if (!version) {
      return (
        <Alert
          type="warning"
          showIcon
          message="No published version yet"
          description={
            emptyHint ??
            `${actionLabel} runs against the active published version, and this policy set does not have one. Approve rules in Review, then publish a version first.`
          }
        />
      );
    }
    return (
      <div className="eval-target">
        <span className="eval-target-icon eval-target-icon-published">
          <DatabaseOutlined />
        </span>
        <div className="eval-target-body">
          <div className="eval-target-line">
            <Text type="secondary" className="eval-target-label">
              Runs against
            </Text>
            <Text strong>Published version {version.version_number}</Text>
            <Tag className="eval-target-count">{version.rule_count} rules</Tag>
            <Tag color="green" className="eval-target-state">
              active
            </Tag>
            <Tooltip title="The version currently in force. Publishing a newer version changes what this runs against.">
              <QuestionCircleOutlined className="eval-target-help" />
            </Tooltip>
          </div>
          <Text type="secondary" className="eval-target-sub">
            Effective from {version.effective_from} · approved by {version.approved_by || "—"}
          </Text>
        </div>
      </div>
    );
  }

  if (candidateCount === 0) {
    return (
      <Alert
        type="warning"
        showIcon
        message="No unpublished rules to check"
        description={
          emptyHint ??
          `${actionLabel} reads rules that are still in review. Extract a document or draft a rule first.`
        }
      />
    );
  }

  return (
    <div className="eval-target">
      <span className="eval-target-icon eval-target-icon-candidates">
        <InboxOutlined />
      </span>
      <div className="eval-target-body">
        <div className="eval-target-line">
          <Text type="secondary" className="eval-target-label">
            Runs against
          </Text>
          <Text strong>Unpublished rules in review</Text>
          {candidateCount !== null && <Tag className="eval-target-count">{candidateCount} rules</Tag>}
          <Tooltip title="Rules awaiting review plus rules you have approved but not yet published. Rejected rules are excluded.">
            <QuestionCircleOutlined className="eval-target-help" />
          </Tooltip>
        </div>
        <Text type="secondary" className="eval-target-sub">
          Lets you catch problems before publishing, not after.
        </Text>
      </div>
    </div>
  );
}

/** Compact inline form for headers where a full banner would dominate the page. */
export function EvaluationTargetInline({ target }: { target: EvaluationTargetState }) {
  const { version, loading } = target;
  if (loading) return <Text type="secondary">Resolving target…</Text>;
  if (!version) {
    return (
      <Space size={6}>
        <Text type="secondary">Target:</Text>
        <Tag color="orange">no published version</Tag>
      </Space>
    );
  }
  return (
    <Space size={6}>
      <Text type="secondary">Target:</Text>
      <Text strong>v{version.version_number}</Text>
      <Tag>{version.rule_count} rules</Tag>
    </Space>
  );
}
