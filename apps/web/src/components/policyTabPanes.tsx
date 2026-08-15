/**
 * What a policy is, told in the same tabs a rule is told in.
 *
 * A rule opened in the inspector gets a full information surface. A policy —
 * which is the thing a reviewer actually approves, rejects and publishes — got
 * two tabs. This module supplies the missing panes.
 *
 * They are not the rule's panes with a loop around them. A rule answers each
 * question once; a policy answers it several times and the answers can differ,
 * and *that difference is the finding*. So every pane here is written to say
 * where the policy's rules agree, where they do not, and which rules are on
 * each side — never to merge a disagreement into a single tidy answer the
 * reviewer would have no way to question.
 *
 * Two things are deliberately absent, and their absence is the design:
 *
 *  - Nothing here prints a zero for a route. A policy whose rules are all read
 *    rather than computed is not missing anything; it took a route. A pane that
 *    renders "0 computed" beside a populated list manufactures a shortfall out
 *    of a routing decision.
 *  - Nothing here takes an "is this editable" flag. Every pane is a statement
 *    about the record and reads the same on a candidate and on a published
 *    policy. What changes between the two is which *actions* are offered, and
 *    that is decided from the record's own status elsewhere.
 */

import { Empty, Table, Tag, Tooltip, Typography } from "antd";
import type { AssembledPolicy, CanonicalRule, PolicyTestListItem } from "../api";
import type { PolicyCard } from "../policyCards";
import {
  policyAuthorities,
  policyCompositionSentence,
  policyRequiredFacts,
  policyRoutes,
  policyScope,
  type PolicyScopeDimension,
} from "../policyRecordFacts";
import type { PublishedPolicyCard } from "../publishedPolicyCards";
import { DirectionalText } from "./DirectionalText";
import "./policyTabPanes.css";

const { Text, Paragraph } = Typography;

/**
 * A policy as these panes need it, with nothing in it about who may act on it.
 *
 * The review queue and the published version hold a policy in two different
 * shapes, for a real reason: one carries a candidate that may still be edited,
 * the other carries a sealed record. Neither difference is visible in anything
 * these panes say. So the panes read this, and each surface supplies it — which
 * is what keeps there being one set of panes rather than a published copy that
 * drifts from the review one within weeks.
 *
 * There is deliberately no status, no editability and no permission on this
 * type. A pane that could see them could branch on them.
 */
export interface PolicyRecordView {
  policy: AssembledPolicy;
  /** How many passages of its source document the policy quotes. */
  passageCount: number;
  /** Every rule the policy holds, in document order, with the id it is known by. */
  rules: { rule_id: string; rule: CanonicalRule }[];
}

/** A queue card as a policy record. */
export function candidatePolicyRecord(card: PolicyCard): PolicyRecordView {
  return {
    policy: card.policy,
    passageCount: card.passages.length,
    rules: card.rules.map((entry) => ({ rule_id: entry.rule_id, rule: entry.candidate.rule })),
  };
}

/** A published card as a policy record. */
export function publishedPolicyRecord(card: PublishedPolicyCard): PolicyRecordView {
  return {
    policy: card.policy,
    passageCount: card.passages.length,
    rules: card.rules.map((entry) => ({ rule_id: entry.rule_id, rule: entry.rule })),
  };
}

/** The rules of a record, as the canonical records the panes reason about. */
export function recordRules(record: PolicyRecordView): CanonicalRule[] {
  return record.rules.map((entry) => entry.rule);
}

/** How many rules named this, of how many — the shape every pane counts in. */
function share(named: number, total: number): string {
  return named === total ? "every rule" : `${named} of ${total} rules`;
}

/* ------------------------------------------------------------------ Overview */

/**
 * What this policy is, before any question is asked about it.
 *
 * Ordered as a reader meets it: the document's own heading and the trail that
 * locates it, then how much of the document it occupies, then what it is made
 * of. The generated subject label is rendered by the panel's header rather than
 * here, so that this app's words never sit above the document's without being
 * marked as this app's.
 */
export function PolicyOverviewPane({ record }: { record: PolicyRecordView }) {
  const rules = recordRules(record);
  const composition = policyCompositionSentence(rules);
  const authorities = policyAuthorities(rules);
  const passages = record.passageCount;

  return (
    <div className="policy-pane">
      <section className="policy-pane__section">
        <Text type="secondary" className="policy-pane__label">
          Where this policy sits
        </Text>
        {record.policy.heading_path.length > 1 ? (
          <Paragraph className="policy-pane__trail">
            <DirectionalText>{record.policy.heading_path.slice(0, -1).join(" › ")}</DirectionalText>
          </Paragraph>
        ) : (
          <Paragraph type="secondary">
            The document places this policy at its top level, under no heading above it.
          </Paragraph>
        )}
        {record.policy.page != null && <Tag>Page {record.policy.page}</Tag>}
        <Tag>
          {passages === 1 ? "1 passage" : `${passages} passages`}
        </Tag>
        <Tag>
          {rules.length === 1 ? "1 rule" : `${rules.length} rules`}
        </Tag>
      </section>

      <section className="policy-pane__section">
        <Text type="secondary" className="policy-pane__label">
          What it is made of
        </Text>
        <Paragraph>{composition}</Paragraph>
      </section>

      <section className="policy-pane__section">
        <Text type="secondary" className="policy-pane__label">
          Where its rules came from
        </Text>
        {authorities.length === 0 ? (
          <Paragraph type="secondary">
            No rule of this policy records who put it here.
          </Paragraph>
        ) : (
          <ul className="policy-pane__list">
            {authorities.map((entry) => (
              <li key={`${entry.owner}\u0000${entry.level}`}>
                <Text strong>{entry.owner}</Text>
                {entry.level && <Text type="secondary"> · {entry.level}</Text>}
                <Text type="secondary"> · {share(entry.ruleIds.length, rules.length)}</Text>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

/* --------------------------------------------------- Parties and the routes */

/**
 * The one place this tab is named.
 *
 * It was three: the review panel, the published card and the rule inspector
 * each held their own string, and the third had drifted to a word the other
 * two had deliberately dropped. A label is an interface a reader learns, so
 * two names for one tab teaches them there are two tabs.
 */
export const PARTIES_AND_ROUTES_TAB_LABEL = "Parties & routes";

/**
 * Who the policy binds, and how each of its rules reaches a decision.
 *
 * Named "Parties & routes" rather than "readiness". A route is how a rule is
 * decided — by computing a comparison, or by reading what the source says — and
 * both are decisions the policy reaches. Calling the second one a readiness
 * level invites the reader to score it against the first, and there is nothing
 * to score: the source wrote it in words, so it is read.
 *
 * The facts table is the same trap in numeric form. Facts are named by the
 * rules that state a computable test, and only by those. A rule the source
 * states in words names none — so listing it with an empty cell puts it in a
 * column measuring something it was never going to have, and the empty cell
 * reads as an omission. Those rules are therefore not in the table at all;
 * what the reviewer is told about them is which route they take, above.
 */
export function PolicyPartiesAndRoutesPane({ record }: { record: PolicyRecordView }) {
  const rules = recordRules(record);
  const routes = policyRoutes(rules);
  const facts = policyRequiredFacts(rules);
  const ruleIdsNamingFacts = new Set(facts.flatMap((entry) => entry.ruleIds));

  return (
    <div className="policy-pane">
      <section className="policy-pane__section">
        <Text type="secondary" className="policy-pane__label">
          How its rules are decided
        </Text>
        {routes.length === 0 ? (
          <Paragraph type="secondary">This policy states no rules to decide.</Paragraph>
        ) : (
          <>
            <ul className="policy-pane__list">
              {routes.map((route) => (
                <li key={route.route}>
                  <Tag>{route.label}</Tag>
                  <Text type="secondary">{share(route.count, rules.length)}</Text>
                </li>
              ))}
            </ul>
            {routes.length > 1 && (
              <Paragraph type="secondary">
                This policy's rules are decided in more than one way. Both reach a decision;
                they differ in what does the deciding.
              </Paragraph>
            )}
          </>
        )}
      </section>

      <section className="policy-pane__section">
        <Text type="secondary" className="policy-pane__label">
          Facts its rules compare
        </Text>
        {facts.length === 0 ? (
          <Paragraph type="secondary">
            No rule of this policy states a comparison, so none of them waits on a supplied
            value. They are decided from what the source says.
          </Paragraph>
        ) : (
          <>
            <ul className="policy-pane__list">
              {facts.map((entry) => (
                <li key={entry.fact.name}>
                  <Text code>{entry.fact.name}</Text>
                  <Text type="secondary">
                    {" "}
                    · named by {share(entry.ruleIds.length, ruleIdsNamingFacts.size)} that compare
                  </Text>
                </li>
              ))}
            </ul>
            <Paragraph type="secondary">
              Counted against the rules that state a comparison, not against the policy. A rule
              its source states in words is decided by reading it, so it names no facts and
              waits on nothing.
            </Paragraph>
          </>
        )}
      </section>
    </div>
  );
}

/* -------------------------------------------------------------------- Scope */

/**
 * Who the policy applies to, with its rules' disagreements left standing.
 *
 * The union is not the answer on its own, and the reason is easy to miss: an
 * empty list on a rule does not mean "nobody", it means "everybody". Union the
 * scopes of a rule bound to one persona and a rule bound to all of them and you
 * get that one persona — a policy stated as narrower than it is, with the
 * broadest rule in it silently gone.
 *
 * So each dimension reports both, and a dimension whose rules do not agree is
 * marked. Two rules of one policy scoped differently means the policy binds
 * different people depending which of its rules is being applied. That is a
 * finding for the reviewer, not a rendering inconvenience to be smoothed over.
 */
export function PolicyScopePane({ record }: { record: PolicyRecordView }) {
  const rules = recordRules(record);
  const dimensions = policyScope(rules);
  const stated = dimensions.filter(
    (d) => d.values.length > 0 || d.agreement === "mixed",
  );

  if (rules.length === 0) {
    return <Empty description="This policy states no rules, so it binds no one yet." />;
  }

  if (stated.length === 0) {
    return (
      <div className="policy-pane">
        <Paragraph>
          No rule of this policy narrows who it applies to. Every rule applies to everyone the
          document covers.
        </Paragraph>
      </div>
    );
  }

  return (
    <div className="policy-pane">
      {stated.map((dimension: PolicyScopeDimension) => (
        <section key={dimension.key} className="policy-pane__section">
          <Text type="secondary" className="policy-pane__label">
            {dimension.label}
          </Text>
          {dimension.agreement === "mixed" && (
            <Tooltip title="The rules of this policy do not name the same thing here. Which people it binds depends on which of its rules is applied.">
              <Tag color="gold">Its rules differ here</Tag>
            </Tooltip>
          )}
          {dimension.values.length > 0 ? (
            <div className="policy-pane__chips">
              {dimension.values.map((value) => (
                <Tag key={value}>
                  <DirectionalText>{value}</DirectionalText>
                </Tag>
              ))}
            </div>
          ) : (
            <Paragraph type="secondary">No rule names anything here.</Paragraph>
          )}
          {dimension.unrestrictedRuleIds.length > 0 && dimension.values.length > 0 && (
            <Paragraph type="secondary">
              {share(dimension.unrestrictedRuleIds.length, rules.length)} name nothing here, and
              so apply to everyone — the names above do not narrow them.
            </Paragraph>
          )}
        </section>
      ))}
    </div>
  );
}

/* -------------------------------------------------------------------- Tests */

/** What is known about one rule's testing, kept as four separate answers. */
export type RuleTestState = "passing" | "failing" | "unverified" | "untested";

export interface RuleTestRow {
  ruleId: string;
  title: string;
  state: RuleTestState;
  tests: number;
}

const TEST_STATE: Record<RuleTestState, { label: string; color?: string; why: string }> = {
  passing: { label: "Passing", color: "green", why: "Every test covering this rule passed on its last run." },
  failing: { label: "Failing", color: "red", why: "A test covering this rule failed on its last run." },
  unverified: {
    label: "Not yet run",
    color: "gold",
    why: "A test covers this rule but has not been run, so nothing is known about it yet.",
  },
  untested: {
    label: "No test",
    why: "No test targets this rule. That is a fact about the coverage, not a passing result.",
  },
};

/**
 * The tests covering this policy's rules.
 *
 * A policy owns rules and a test targets a rule, so a policy's tests are the
 * ones aimed at rules it holds. That is done here rather than asked of the
 * server, because a policy-scope endpoint would have to re-derive which rules
 * are in a policy — a second opinion on grouping, free to disagree with the
 * first one and with no way for a reader to tell which they were looking at.
 *
 * Four states, and none of them collapse. `untested` is not `failing`, because
 * nothing has been claimed and failed. It is emphatically not `passing` either:
 * an absent test that renders as a green tick is a false assurance, and the one
 * outcome this pane exists to make impossible.
 */
export function policyTestRows(
  record: PolicyRecordView,
  tests: readonly PolicyTestListItem[],
): RuleTestRow[] {
  const byRule = new Map<string, PolicyTestListItem[]>();
  for (const item of tests) {
    const target = item.test.expected_rule_id;
    if (!target) continue;
    const existing = byRule.get(target);
    if (existing) existing.push(item);
    else byRule.set(target, [item]);
  }

  return record.rules.map((entry) => {
    const covering = byRule.get(entry.rule_id) ?? [];
    const runs = covering
      .map((item) => item.latest_run)
      .filter((run): run is NonNullable<typeof run> => run != null);
    let state: RuleTestState = "untested";
    if (covering.length === 0) state = "untested";
    else if (runs.length === 0) state = "unverified";
    // `error` is not `fail`: a test that could not run has claimed nothing, so
    // it is unverified. Folding it into failing would report a defect in the
    // policy where the defect is in the run.
    else if (runs.some((run) => run.status === "fail")) state = "failing";
    else if (runs.every((run) => run.status === "pass")) state = "passing";
    else state = "unverified";

    return {
      ruleId: entry.rule_id,
      title: entry.rule.title,
      state,
      tests: covering.length,
    };
  });
}

export function PolicyTestsPane({
  record,
  tests,
  loading,
}: {
  record: PolicyRecordView;
  tests: readonly PolicyTestListItem[] | null;
  loading?: boolean;
}) {
  const rows = policyTestRows(record, tests ?? []);
  const covered = rows.filter((row) => row.state !== "untested").length;

  return (
    <div className="policy-pane">
      <Paragraph type="secondary">
        {tests == null && !loading
          ? "The tests for this policy set have not been loaded."
          : covered === 0
            ? "No test targets any rule of this policy. Nothing here has been checked — which is different from having been checked and passed."
            : `${share(covered, rows.length)} of this policy are covered by a test.`}
      </Paragraph>
      <Table<RuleTestRow>
        size="small"
        rowKey="ruleId"
        loading={loading}
        dataSource={rows}
        pagination={false}
        locale={{ emptyText: <Empty description="This policy states no rules to test." /> }}
        columns={[
          {
            title: "Rule",
            dataIndex: "title",
            render: (title: string) => <DirectionalText>{title}</DirectionalText>,
          },
          {
            title: "Tests",
            dataIndex: "tests",
            width: 90,
            render: (count: number) => (count === 0 ? <Text type="secondary">—</Text> : count),
          },
          {
            title: "Last run",
            dataIndex: "state",
            width: 150,
            render: (state: RuleTestState) => (
              <Tooltip title={TEST_STATE[state].why}>
                <Tag color={TEST_STATE[state].color}>{TEST_STATE[state].label}</Tag>
              </Tooltip>
            ),
          },
        ]}
      />
    </div>
  );
}

/* ------------------------------------------------------------------ History */

/**
 * One sighting of this policy, in one published version.
 *
 * The field names are the server's, from `PolicySighting` in
 * `infrastructure/assembly/provision_history.py`, and are not renamed on the
 * way in. A view type that renames them reads plausibly and then hands the
 * table `undefined` for anything it guessed wrong — which is exactly what
 * happened here: this interface first said `rules_changed` and `rule_count`,
 * the server says `rules_reworded` and sends `rules`, and the tab crashed on
 * the first real payload while every test passed against the invented shape.
 */
export interface PolicyRuleSightingView {
  rule_id: string;
  title: string;
  fingerprint: string;
}

export interface PolicySightingView {
  version_id: string;
  version_number: number | null;
  is_active: boolean;
  approved_by: string | null;
  approved_at: string | null;
  heading_path: string[];
  change: string;
  rules: PolicyRuleSightingView[];
  rules_added: string[];
  rules_removed: string[];
  rules_reworded: string[];
}

/**
 * The policy across the versions it was published in.
 *
 * A policy is not a row. `document_provisions.id` belongs to one document
 * version and cannot follow a policy that survives a re-extraction, so the
 * thing that persists is the provision key — the policy is a key, seen at a
 * version. This pane reads those sightings in order.
 *
 * What it says about each is deliberately narrow. The first sighting is
 * `first seen`, not `added`: this app was not watching before it, so it cannot
 * report that the policy did not exist. And change is judged by comparing
 * consecutive sightings of the same key on what a reader would call the rule,
 * not on a revision counter, which moves when nothing a reader can see has.
 *
 * The two empty states are separated for the same reason. `null` means this app
 * never asked, and `[]` means it asked and the key has no published sighting;
 * one sentence for both told a published policy, on the published page, that it
 * "has not been published yet". Neither sentence now claims anything about the
 * record's own status, which this pane is not given and must not infer.
 */
export function PolicyHistoryPane({
  sightings,
  loading,
}: {
  sightings: readonly PolicySightingView[] | null;
  loading?: boolean;
}) {
  if (!loading && sightings == null) {
    return <Empty description="This policy's other versions have not been loaded." />;
  }
  if (!loading && sightings != null && sightings.length === 0) {
    return <Empty description="No published version of this policy was found to compare." />;
  }

  return (
    <div className="policy-pane">
      <Table<PolicySightingView>
        size="small"
        rowKey="version_id"
        loading={loading}
        dataSource={[...(sightings ?? [])]}
        pagination={false}
        columns={[
          {
            title: "Version",
            dataIndex: "version_number",
            width: 110,
            render: (n: number | null, row) => (
              <>
                {n == null ? <Text type="secondary">—</Text> : `v${n}`}
                {row.is_active && <Tag className="policy-pane__active-tag">active</Tag>}
              </>
            ),
          },
          {
            title: "Approved",
            dataIndex: "approved_at",
            width: 190,
            render: (at: string | null, row) => (
              <>
                {at ? at.slice(0, 10) : <Text type="secondary">not recorded</Text>}
                {row.approved_by && <Text type="secondary"> · {row.approved_by}</Text>}
              </>
            ),
          },
          {
            title: "Rules",
            dataIndex: "rules",
            width: 80,
            render: (rules: PolicyRuleSightingView[]) => rules.length,
          },
          {
            title: "Against the version before it",
            dataIndex: "change",
            render: (change: string, row) => (
              <>
                <Tag>{change.replace(/_/g, " ")}</Tag>
                {row.rules_added.length > 0 && (
                  <Text type="secondary"> {row.rules_added.length} new</Text>
                )}
                {row.rules_removed.length > 0 && (
                  <Text type="secondary"> · {row.rules_removed.length} gone</Text>
                )}
                {row.rules_reworded.length > 0 && (
                  <Text type="secondary"> · {row.rules_reworded.length} reworded</Text>
                )}
              </>
            ),
          },
        ]}
      />
    </div>
  );
}
