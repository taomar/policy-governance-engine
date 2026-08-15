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

import { Alert, Button, Empty, Popconfirm, Space, Table, Tag, Tooltip, Typography } from "antd";
import type { AssembledPolicy, CanonicalRule, PolicyTestListItem, ReviewFacetRun } from "../api";
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
import { NotesPanel } from "./NotesPanel";
import { policyProvenance } from "./policyProvenance";
import type { PolicyTesting } from "./policyTesting";
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
  /**
   * How far through review the policy is — totals only, never per-rule status.
   *
   * Deliberately arrives already aggregated. A pane holding per-rule statuses
   * could enable a control for rule X on the strength of rule X's state, which
   * is the branch this type exists to make impossible; a pane holding two
   * numbers physically cannot. That the counts are a *fact about the record*
   * rather than a permission is what makes them admissible here at all.
   *
   * `null` where the question does not apply — on a sealed record there is
   * nothing open, and rendering "0 open" would invite a reader to wonder what
   * happened to a decision that was never pending.
   */
  progress?: { decided: number; open: number } | null;
}

/** A queue card as a policy record. */
export function candidatePolicyRecord(card: PolicyCard): PolicyRecordView {
  return {
    policy: card.policy,
    passageCount: card.passages.length,
    rules: card.rules.map((entry) => ({ rule_id: entry.rule_id, rule: entry.rule })),
    progress: {
      decided: card.allIds.length - card.reviewableIds.length,
      open: card.reviewableIds.length,
    },
  };
}

/** A published card as a policy record. */
export function publishedPolicyRecord(card: PublishedPolicyCard): PolicyRecordView {
  return {
    policy: card.policy,
    passageCount: card.passages.length,
    rules: card.rules.map((entry) => ({ rule_id: entry.rule_id, rule: entry.rule })),
    // A published record is sealed. There is no decision outstanding on it, so
    // there is no progress through one to report.
    progress: null,
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

/**
 * A handle a reviewer can copy and go and look something up with.
 *
 * Rendered as an identifier — monospaced, selectable, whole — rather than
 * folded into a sentence. A traceable chain is only traceable if the reader can
 * take the link away with them, and an id truncated to fit a line is an id that
 * cannot be pasted anywhere.
 */
function Identifier({ label, value }: { label: string; value: string }) {
  return (
    <div className="policy-pane__identifier">
      <Text type="secondary" style={{ fontSize: 12 }}>
        {label}
      </Text>
      <Typography.Paragraph copyable={{ text: value }} style={{ marginBottom: 4 }}>
        <Text code>{value}</Text>
      </Typography.Paragraph>
    </div>
  );
}

/**
 * A moment, in the reader's own locale.
 *
 * Not formatted to a pattern of this app's choosing: a date written the way the
 * reader's system writes dates is one they cannot misread, and a fixed pattern
 * is a decision made on behalf of every locale at once. Unparseable input is
 * returned untouched rather than rendered as an invalid date.
 */
function formatMoment(value: string): string {
  const at = new Date(value);
  return Number.isNaN(at.getTime()) ? value : at.toLocaleString();
}

/* ------------------------------------------------------------------ Overview */

/**
 * The chain from a document to this record.
 *
 * WHAT CHANGED AND WHY
 *
 * This tab used to render three grey pills — page, passages, rules — directly
 * beneath a card header that had just stated the same three facts. A reviewer
 * read the same line twice and learned nothing the second time, and said so:
 * they could not trace the policy.
 *
 * So the rule for this pane is that **nothing the header states may be
 * restated here**. What the header cannot say is where the record came from,
 * and every link of that was already loaded and none of it was on screen. It
 * now reads top to bottom as a chain a reviewer can follow: this file, at this
 * version → these extraction runs → this policy, at this key → here in the
 * document → published in these versions → this far through review.
 *
 * Each link renders its identifier as an identifier, because the point of a
 * traceable chain is that a reader can copy a handle and go and find the thing.
 *
 * Absent is never blank. A link this app has not loaded says so, and says it
 * differently from a link that is genuinely empty — a policy that has never
 * been published and a policy whose publication history was never fetched are
 * different facts and must not render alike.
 */
export function PolicyOverviewPane({
  record,
  runs,
  sightings,
  sightingsLoading,
  onRequestSightings,
}: {
  record: PolicyRecordView;
  /** The policy set's extraction runs, which carry their document and version.
   *  `null` when this app has not loaded them. */
  runs?: readonly ReviewFacetRun[] | null;
  /** This key's published sightings, when they have been fetched. */
  sightings?: readonly PolicySightingView[] | null;
  sightingsLoading?: boolean;
  /** Ask for them. Supplied where the surface can afford the request only on
   *  demand — a page holding many cards would otherwise spend one per card to
   *  fill a section most readers never scroll to. Without it the section states
   *  the absence and stops there, which is honest but is a dead end, so every
   *  surface that can offer the way out should. */
  onRequestSightings?: () => void;
}) {
  const rules = recordRules(record);
  const composition = policyCompositionSentence(rules);
  const authorities = policyAuthorities(rules);
  const chain = policyProvenance(record, { runs, sightings });

  return (
    <div className="policy-pane">
      <section className="policy-pane__section">
        <Text type="secondary" className="policy-pane__label">
          The document it was read from
        </Text>
        {chain.document.title ? (
          <Paragraph className="policy-pane__chain">
            <DirectionalText>{chain.document.title}</DirectionalText>
            {chain.document.versionLabel && (
              <Text type="secondary"> · version {chain.document.versionLabel}</Text>
            )}
          </Paragraph>
        ) : (
          <Paragraph type="secondary">
            This app has not loaded the documents of this policy set, so it cannot name the file
            this policy was read from.
          </Paragraph>
        )}
        {chain.document.versionId && (
          <Identifier label="Document version" value={chain.document.versionId} />
        )}
        {chain.document.contentHash && (
          <Identifier label="Content hash" value={chain.document.contentHash} />
        )}
      </section>

      <section className="policy-pane__section">
        <Text type="secondary" className="policy-pane__label">
          {chain.runs.length > 1 ? "The extractions that produced its rules" : "The extraction that produced its rules"}
        </Text>
        {chain.runs.length === 0 ? (
          <Paragraph type="secondary">
            No rule of this policy records which extraction produced it.
          </Paragraph>
        ) : (
          <>
            {chain.runs.length > 1 && (
              <Paragraph type="secondary">
                Its rules come from more than one extraction, which happens when a document is read
                again and only part of a policy changes.
              </Paragraph>
            )}
            <ul className="policy-pane__list">
              {chain.runs.map((run) => (
                <li key={run.id}>
                  <Text strong>
                    <span data-testid={`run-reference-${run.id}`}>{run.reference ?? run.id}</span>
                  </Text>
                  {run.startedAt && <Text type="secondary"> · started {formatMoment(run.startedAt)}</Text>}
                  {run.status && <Text type="secondary"> · {run.status.replace(/_/g, " ")}</Text>}
                  <Text type="secondary"> · {share(run.rules, rules.length)}</Text>
                </li>
              ))}
            </ul>
          </>
        )}
      </section>

      <section className="policy-pane__section">
        <Text type="secondary" className="policy-pane__label">
          What identifies this policy
        </Text>
        <Paragraph type="secondary">
          This key is what the policy is known by across every version of the document. It is the
          handle to follow when tracing the policy through its history.
        </Paragraph>
        <Identifier label="Policy key" value={chain.provisionKey} />
        {chain.provisionId && <Identifier label="This cut of it" value={chain.provisionId} />}
        <Paragraph type="secondary" style={{ marginTop: 8 }}>
          {chain.placement.boundaryRecorded
            ? "The document itself marked out where this policy begins and ends."
            : "Where this policy begins and ends was worked out when it was read, from the headings its rules cite."}
        </Paragraph>
      </section>

      <section className="policy-pane__section">
        <Text type="secondary" className="policy-pane__label">
          Where it sits in the document
        </Text>
        {chain.placement.trail.length > 0 ? (
          <Paragraph className="policy-pane__trail">
            <DirectionalText>{chain.placement.trail.join(" › ")}</DirectionalText>
          </Paragraph>
        ) : (
          <Paragraph type="secondary">
            The document places this policy at its top level, under no heading above it.
          </Paragraph>
        )}
        <Paragraph type="secondary">
          {chain.placement.pages == null
            ? "No passage of this policy recorded which page it was on."
            : chain.placement.pages.first === chain.placement.pages.last
              ? `All of it is on page ${chain.placement.pages.first}.`
              : `It runs from page ${chain.placement.pages.first} to page ${chain.placement.pages.last}.`}
        </Paragraph>
        {chain.placement.sourceElements && (
          <Identifier label="Source elements" value={chain.placement.sourceElements} />
        )}
      </section>

      <section className="policy-pane__section">
        <Text type="secondary" className="policy-pane__label">
          Where it has been published
        </Text>
        {!chain.publication.known ? (
          <>
            <Paragraph type="secondary">
              {sightingsLoading
                ? "Looking for published versions carrying this key…"
                : "This app has not looked for published versions carrying this key."}
            </Paragraph>
            {onRequestSightings && !sightingsLoading && (
              <Button size="small" onClick={onRequestSightings} data-testid="overview-request-sightings">
                Look
              </Button>
            )}
          </>
        ) : chain.publication.versions.length === 0 ? (
          <Paragraph type="secondary">
            No published version carries this key. Nothing under it has been sealed.
          </Paragraph>
        ) : (
          <ul className="policy-pane__list">
            {chain.publication.versions.map((version) => (
              <li key={version.versionId}>
                <Text strong>
                  {version.versionNumber == null ? "A version" : `Version ${version.versionNumber}`}
                </Text>
                {version.isActive && <Tag color="green" style={{ marginInlineStart: 8 }}>Active</Tag>}
                {version.approvedAt && (
                  <Text type="secondary"> · approved {formatMoment(version.approvedAt)}</Text>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {record.progress && (
        <section className="policy-pane__section">
          <Text type="secondary" className="policy-pane__label">
            How far through review it is
          </Text>
          <Paragraph>
            {record.progress.open === 0
              ? "Every rule of this policy has been decided."
              : record.progress.decided === 0
                ? "No rule of this policy has been decided yet."
                : `${record.progress.decided} of its ${record.progress.decided + record.progress.open} rules have been decided; ${record.progress.open} are still open.`}
          </Paragraph>
        </section>
      )}

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
 *
 * The captions here state how a rule works, never what it does not have, and
 * that distinction survived two attempts at the reassuring form. Writing "it
 * names no facts, and is not missing any" reads as generous and does the
 * opposite: it supplies the frame it then withdraws, and a reader skimming
 * keeps the noun and drops the negation. There is no shortage to deny. The
 * words of the source are the test, which is a complete account of the rule
 * and needs nothing subtracted from it.
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
            Every rule of this policy is decided by reading what its source says: the words
            are the test, and a reader applies them to the case in front of them.
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
              Counted against the rules that state a comparison, which is where a named fact
              comes from. A rule its source states in words is decided by reading it: the words
              are the test, and a reader applies them.
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
  /** The tests covering this rule, so a row can run its own without the pane
   *  having to re-derive which ones they were. */
  testIds: string[];
  /** How many of them this app proposed and nobody has accepted yet.
   *
   *  Kept separate from `state` rather than folded into it. A proposed test is
   *  not a fifth outcome of running — it has not run — it is a statement about
   *  where the test came from, and a reviewer deciding whether to trust a green
   *  row needs to know that the question it answers was written by this app. */
  awaitingReview: number;
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
      testIds: covering.map((item) => item.test.id),
      awaitingReview: covering.filter((item) => item.test.review_status === "pending_review").length,
    };
  });
}

/**
 * What this pane can ask for. Absent means asking is not available here, and
 * the pane then says so rather than rendering a control that does nothing.
 */
export type PolicyTestingVerbs = Pick<
  PolicyTesting,
  "generate" | "run" | "busy" | "working" | "error" | "dismissError"
>;

export function PolicyTestsPane({
  record,
  tests,
  loading,
  testing,
}: {
  record: PolicyRecordView;
  tests: readonly PolicyTestListItem[] | null;
  loading?: boolean;
  testing?: PolicyTestingVerbs;
}) {
  const rows = policyTestRows(record, tests ?? []);
  const covered = rows.filter((row) => row.state !== "untested").length;
  const untestedRuleIds = rows.filter((row) => row.state === "untested").map((row) => row.ruleId);
  const everyTestId = rows.flatMap((row) => row.testIds);
  const awaitingReview = rows.reduce((total, row) => total + row.awaitingReview, 0);

  return (
    <div className="policy-pane">
      <Paragraph type="secondary">
        {tests == null && !loading
          ? "The tests for this policy set have not been loaded."
          : covered === 0
            ? "No test targets any rule of this policy. Nothing here has been checked — which is different from having been checked and passed."
            : `${share(covered, rows.length)} of this policy are covered by a test.`}
      </Paragraph>

      {testing && rows.length > 0 ? (
        <Space wrap size="small" style={{ marginBottom: 12 }} data-testid="policy-test-actions">
          <Popconfirm
            title="Write scenarios for these rules?"
            description={
              <div style={{ maxWidth: 320 }}>
                This asks a model to read each rule and propose a scenario for it, which takes time
                and costs model usage. What comes back is a proposal from this app, held for your
                review, and it is not run until you run it.
              </div>
            }
            okText="Write them"
            cancelText="Not now"
            onConfirm={() => {
              void testing.generate(untestedRuleIds.length > 0 ? untestedRuleIds : rows.map((r) => r.ruleId));
            }}
            disabled={testing.working}
          >
            <Button size="small" type="primary" loading={testing.working} data-testid="policy-generate-tests">
              {untestedRuleIds.length > 0
                ? `Write scenarios for ${share(untestedRuleIds.length, rows.length)} with no test`
                : "Write more scenarios"}
            </Button>
          </Popconfirm>
          <Popconfirm
            title="Run every test of this policy?"
            description={
              <div style={{ maxWidth: 320 }}>
                Each test is evaluated against the version on screen. This takes time and costs
                model usage.
              </div>
            }
            okText="Run them"
            cancelText="Not now"
            onConfirm={() => {
              void testing.run(everyTestId);
            }}
            disabled={testing.working || everyTestId.length === 0}
          >
            <Button
              size="small"
              disabled={everyTestId.length === 0 || testing.working}
              loading={testing.working}
              data-testid="policy-run-tests"
            >
              Run {everyTestId.length === 0 ? "tests" : `all ${everyTestId.length}`}
            </Button>
          </Popconfirm>
          {awaitingReview > 0 ? (
            <Text type="secondary" data-testid="policy-tests-awaiting-review">
              {awaitingReview} written by this app, waiting for you to accept or reject
            </Text>
          ) : null}
        </Space>
      ) : null}

      {testing?.error ? (
        <Alert
          type="error"
          showIcon
          closable
          onClose={testing.dismissError}
          message="That did not complete"
          description={<DirectionalText>{testing.error}</DirectionalText>}
          style={{ marginBottom: 12 }}
          data-testid="policy-test-error"
        />
      ) : null}

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
            render: (title: string, row: RuleTestRow) => (
              <Space direction="vertical" size={0}>
                <DirectionalText>{title}</DirectionalText>
                {row.awaitingReview > 0 ? (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    ✦ {row.awaitingReview === row.tests ? "Written by this app" : `${row.awaitingReview} written by this app`}, awaiting review
                  </Text>
                ) : null}
              </Space>
            ),
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
          ...(testing
            ? [
                {
                  title: "",
                  key: "act",
                  width: 96,
                  render: (_: unknown, row: RuleTestRow) =>
                    row.testIds.length > 0 ? (
                      <Button
                        size="small"
                        type="link"
                        loading={row.testIds.some((id) => testing.busy.has(id))}
                        disabled={testing.working}
                        onClick={() => {
                          void testing.run(row.testIds);
                        }}
                        data-testid={`run-rule-tests-${row.ruleId}`}
                      >
                        Run
                      </Button>
                    ) : (
                      <Button
                        size="small"
                        type="link"
                        loading={testing.busy.has(row.ruleId)}
                        disabled={testing.working}
                        onClick={() => {
                          void testing.generate([row.ruleId]);
                        }}
                        data-testid={`generate-rule-test-${row.ruleId}`}
                      >
                        Write one
                      </Button>
                    ),
                } as const,
              ]
            : []),
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

/* --------------------------------------------------------------------- Notes */

/**
 * What people have said about this policy.
 *
 * WHY THIS IS NOT THE RULE'S NOTES PANEL WITH A LOOP AROUND IT
 *
 * Notes already attach to a rule, and a policy holds rules, so the cheap move
 * would have been to show every note on every rule of the policy under one
 * heading. That would put a remark about one sentence of the document under a
 * title claiming it is about the whole section, and — worse — there would be no
 * way to write the other kind. "These two rules contradict each other" is a
 * statement about the policy; filed against one of the two rules it reads as a
 * complaint about that rule alone, and the reader of the other one never sees
 * it.
 *
 * So a policy's notes are the policy's own, attached to the policy.
 *
 * WHAT IT IS KEYED ON, AND WHY THAT IS THE WHOLE DESIGN
 *
 * `provision_key`, not the `document_provisions` row id. The row is per document
 * version: re-extract the document and every row is replaced, so a note keyed to
 * one would stop appearing without anything having deleted it — the worst
 * failure available here, because a reviewer would have no way to know a remark
 * had ever been made. The key is the policy's identity across versions, which is
 * what History groups by and what the published grouping relies on. The rule
 * notes already made exactly this choice for exactly this reason.
 *
 * WHY IT IS NOT GATED ON EDITABILITY
 *
 * A note is not a change to the record. A sealed version can be discussed —
 * indeed a published policy is the one most likely to attract "this is being
 * read wrongly in practice" — and nothing a note says alters what was published.
 * The pane therefore behaves identically on both surfaces, and this file, as
 * ever, is told nothing about which one it is on.
 */
export function PolicyNotesPane({ record }: { record: PolicyRecordView }) {
  const provisionKey = record.policy.key?.trim() ?? "";

  // A grouping the system has not recorded has no key that will still resolve
  // after the next run, so a note written against it would be addressed to
  // nothing. Said out loud rather than by presenting a composer that silently
  // loses what is typed into it.
  if (!record.policy.persisted || !provisionKey) {
    return (
      <div className="policy-pane" data-testid="policy-notes-pane">
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={
            <Text type="secondary">
              This policy is assembled for display and has not been recorded as a policy in its own
              right, so there is nothing for a note to stay attached to. Notes on its individual
              rules are on those rules.
            </Text>
          }
        />
      </div>
    );
  }

  return (
    <div className="policy-pane" data-testid="policy-notes-pane">
      <Paragraph type="secondary" className="policy-pane__note">
        On the policy as a whole. A remark about one rule belongs on that rule, where the person
        reading that rule will find it.
      </Paragraph>
      <NotesPanel entityType="provision" entityId={provisionKey} compact />
    </div>
  );
}

