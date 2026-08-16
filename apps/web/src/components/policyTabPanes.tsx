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

import { useState } from "react";
import { Alert, Button, Empty, Modal, Popconfirm, Space, Table, Tag, Tooltip, Typography } from "antd";
import { aiApi } from "../api";
import type {
  AssembledPolicy,
  CanonicalRule,
  PolicyExplanation,
  PolicyTestListItem,
  ReviewFacetRun,
} from "../api";
import { describeApiFailure } from "../loadState";
import type { PolicyCard } from "../policyCards";
import { passageQuotations } from "../policyCards";
import { policyRouteLabel } from "../policyGrouping";
import {
  policyAuthorities,
  policyCompositionSentence,
  policyRequiredFacts,
  policyRoutes,
  policyScope,
  type PolicyScopeDimension,
} from "../policyRecordFacts";
import { DirectionalText } from "./DirectionalText";
import { NotesPanel } from "./NotesPanel";
import { policyProvenance, whenItApplies } from "./policyProvenance";
import { RuleName } from "./RuleName";
import { RuleScenarioTester } from "./RuleScenarioTester";
import { PolicyCaseRunner } from "./PolicyCaseRunner";
import { engineDecidesRule } from "../ruleExecutability";
import { testingDoor, type PolicyTesting, type TestingDoor } from "./policyTesting";
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
  rules: {
    rule_id: string;
    rule: CanonicalRule;
    /** The draft row this rule was read from, where the surface has one. Not a
     *  status and nothing branches on it: it is the address a generated name is
     *  looked up by. Absent on a sealed record, which has no such row. */
    candidateId?: string | null;
    /** This rule's own route, from the assembly. Never summarised away and
     *  never ranked: both routes are ways a document states a test. */
    route?: string | null;
  }[];
  /**
   * The document's own words, one entry per passage, in document order.
   *
   * The lead of the Overview, because it is what a reader arriving at a policy
   * came to read. Optional because a surface may build this view without them;
   * an entry whose `quotations` is empty is a passage whose source text was not
   * stored, which is a different fact from a policy with no passages and is
   * said differently.
   */
  source?: readonly PolicyRecordSource[];
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

/** One passage of the source document, quoted. */
export interface PolicyRecordSource {
  key: string;
  page: number | null;
  /** One entry per distinct statement, never joined: two texts the document
   *  states apart are two texts. Empty where none was stored. */
  quotations: string[];
}

/**
 * A card as a policy record.
 *
 * One function for both surfaces. There were two — one that always reported
 * review progress and one that never did — and each caller picked by knowing
 * which page it was on. That is a surface deciding a question about a record,
 * which is the branch this whole type exists to prevent: the same card handed
 * to the two of them described itself differently.
 *
 * WHERE THE ANSWER COMES FROM INSTEAD
 *
 * Review progress is progress through deciding draft rows, so it exists exactly
 * where the card holds draft rows. A published version supplies none — the
 * builder reads that absence as published rather than filling it in — so a
 * sealed policy reports no progress without this function being told anything
 * about publishing. A candidate whose rules have all been settled still holds
 * its rows, and "every rule decided" is both true and worth reading there.
 *
 * The failure this avoids is specific: `allIds` is populated on a published
 * card too (a record with no draft row is known by its rule id), so counting
 * `allIds − reviewableIds` on one reports every rule of a sealed policy as
 * freshly decided — a claim about a review that never took place.
 */
export function policyRecord(card: PolicyCard): PolicyRecordView {
  const underReview = card.rules.some((entry) => entry.candidate !== undefined);
  return {
    policy: card.policy,
    passageCount: card.passages.length,
    rules: card.rules.map((entry) => ({
      rule_id: entry.rule_id,
      rule: entry.rule,
      candidateId: entry.candidate?.id ?? null,
      route: entry.evaluation_mode,
    })),
    source: card.passages.map((block) => ({
      key: block.passage.key,
      page: block.passage.page ?? null,
      quotations: passageQuotations(block.rules.map((entry) => entry.rule)),
    })),
    progress: underReview
      ? {
          decided: card.allIds.length - card.reviewableIds.length,
          open: card.reviewableIds.length,
        }
      : null,
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
 * The same count, said as a count.
 *
 * `share` reads well mid-sentence — "named by every rule that compares" — and
 * badly as a standalone fact, where a reviewer met the bare words "every rule"
 * with no verb attached and read a field value rather than an answer. This
 * spells the number out both ways round.
 */
function sharedRuleCount(named: number, total: number): string {
  if (total === 1) return named === 1 ? "its one rule" : `${named} of its 1 rule`;
  return named === total ? `all ${total} of its rules` : `${named} of its ${total} rules`;
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
 * What this policy says, what it holds, and where it came from.
 *
 * WHAT CHANGED AND WHY
 *
 * This tab used to render three grey pills — page, passages, rules — beneath a
 * card header that had just stated the same three facts. It was rewritten into
 * a provenance chain, which put the facts a reviewer needs on screen and read
 * as a wall of identifiers: five handles stacked as chips, explanatory prose
 * wedged between them, and a sentence describing where the policy sat in the
 * document's outline. A reviewer's verdict was that no business reader could
 * use it, and they were right — it was a debugging panel wearing a business
 * label.
 *
 * THE ORDER IT READS IN NOW, AND WHO EACH PART IS FOR
 *
 * 1. *The document's own words.* The compliance officer opening a policy came
 *    to read the policy. This is the only thing on the tab that is the source
 *    rather than a fact about the record, and it leads because everything below
 *    it is checked against it.
 * 2. *In plain words* — the reading this app can write of its own extraction,
 *    fetched when asked for. It says out loud that it describes the extraction
 *    and not the document, because a fluent paragraph about a decomposition
 *    reads exactly like a fluent paragraph about a source.
 * 3. *The rules it holds.* One line per rule: the name generated for it, what
 *    it states, the route it takes and the id it is known by. This is the thing
 *    a reviewer most wants to scan and the tab named not one rule before.
 * 4. *How to trace it.* One handle promoted — the policy key, which is what
 *    follows the policy across every version of the document — and the rest of
 *    the identifiers kept, behind a disclosure, as the reference material they
 *    are. Deleting them was never an option: "cannot trace the policy" was the
 *    original complaint.
 *
 * WHAT IS DELIBERATELY NOT HERE
 *
 * *Nothing the header states.* The header carries the counts, the page and the
 * status. A reader who reads the same line twice learns nothing the second
 * time, and that is what made this tab uninformative the first time.
 *
 * *Where the policy sits in the document's outline.* "The document places this
 * policy at its top level, under no heading above it" is a fact about the
 * document's layout and no reader of this screen has ever needed it. The
 * governing headings are still shown where the document records any, because a
 * heading is what a reader cites; the sentence that fired when there were none
 * is gone.
 *
 * *Raw internal values as prose.* `ai_drafted` and `policy-formulator` are
 * field values, not words. They are said in words here and kept verbatim on the
 * JSON tab, which is what that tab is for.
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
  const spansPages =
    chain.placement.pages !== null &&
    chain.placement.pages.first !== chain.placement.pages.last;

  return (
    <div className="policy-pane">
      <PolicySourcePane source={record.source} spansPages={spansPages} />

      <PolicyPlainWords
        provisionId={record.policy.provision_id ?? null}
        policyKey={chain.provisionKey}
      />

      <PolicyRuleRoster record={record} />

      <section className="policy-pane__section">
        <Text type="secondary" className="policy-pane__label">
          How to trace it
        </Text>
        <div className="policy-pane__handle">
          <Text type="secondary" style={{ fontSize: 12 }}>
            Policy key
          </Text>
          <Typography.Paragraph
            copyable={{ text: chain.provisionKey }}
            className="policy-pane__handle-value"
          >
            <Text code>{chain.provisionKey}</Text>
          </Typography.Paragraph>
          <Text type="secondary" style={{ fontSize: 12 }}>
            Quote this to find the same policy in any version of the document.
          </Text>
        </div>

        <dl className="policy-pane__facts">
          <div className="policy-pane__fact">
            <dt>Read from</dt>
            <dd>
              {chain.document.title ? (
                <>
                  <DirectionalText>{chain.document.title}</DirectionalText>
                  {chain.document.versionLabel && (
                    <Text type="secondary"> · version {chain.document.versionLabel}</Text>
                  )}
                </>
              ) : (
                <Text type="secondary">
                  This app has not loaded the documents of this policy set, so it cannot name the
                  file this policy was read from.
                </Text>
              )}
            </dd>
          </div>

          {chain.placement.trail.length > 0 && (
            <div className="policy-pane__fact">
              <dt>Filed under</dt>
              <dd className="policy-pane__trail">
                <DirectionalText>{chain.placement.trail.join(" › ")}</DirectionalText>
              </dd>
            </div>
          )}

          {spansPages && chain.placement.pages && (
            <div className="policy-pane__fact">
              <dt>Runs</dt>
              <dd>
                from page {chain.placement.pages.first} to page {chain.placement.pages.last}
              </dd>
            </div>
          )}

          <div className="policy-pane__fact">
            <dt>{chain.runs.length > 1 ? "Read on" : "Read on"}</dt>
            <dd>
              {chain.runs.length === 0 ? (
                <Text type="secondary">
                  No rule of this policy records which extraction produced it.
                </Text>
              ) : (
                <>
                  <ul className="policy-pane__list">
                    {chain.runs.map((run) => (
                      <li key={run.id}>
                        <span data-testid={`run-reference-${run.id}`}>
                          {run.reference ?? run.id}
                        </span>
                        {run.startedAt && (
                          <Text type="secondary"> · {formatMoment(run.startedAt)}</Text>
                        )}
                        {run.status && (
                          <Text type="secondary"> · {run.status.replace(/_/g, " ")}</Text>
                        )}
                        <Text type="secondary">
                          {" "}
                          · produced {sharedRuleCount(run.rules, rules.length)}
                        </Text>
                      </li>
                    ))}
                  </ul>
                  {chain.runs.length > 1 && (
                    <Text type="secondary">
                      Its rules come from more than one extraction, which happens when a document
                      is read again and only part of a policy changes.
                    </Text>
                  )}
                </>
              )}
            </dd>
          </div>

          <div className="policy-pane__fact">
            <dt>Put here by</dt>
            <dd>
              {authorities.length === 0 ? (
                <Text type="secondary">No rule of this policy records who put it here.</Text>
              ) : (
                <ul className="policy-pane__list">
                  {authorities.map((entry) => (
                    <li key={`${entry.owner}\u0000${entry.level}`}>
                      {authorityWords(entry.owner, entry.level)}
                      <Text type="secondary">
                        {" "}
                        · {sharedRuleCount(entry.ruleIds.length, rules.length)}
                      </Text>
                    </li>
                  ))}
                </ul>
              )}
            </dd>
          </div>

          <div className="policy-pane__fact">
            <dt>Made of</dt>
            <dd>{composition}</dd>
          </div>
        </dl>

        {/* Reference material, not headlines. Every one of these was a chip in
            the reader's way; every one of them is what somebody tracing a
            record actually pastes into a query, so none is deleted. */}
        <details className="policy-pane__references" data-testid="overview-references">
          <summary>The identifiers this record is addressed by</summary>
          <div className="policy-pane__references-body">
            {chain.provisionId && (
              <Identifier label="This cut of the policy" value={chain.provisionId} />
            )}
            {chain.document.versionId && (
              <Identifier label="Document version" value={chain.document.versionId} />
            )}
            {chain.document.contentHash && (
              <Identifier label="Content hash" value={chain.document.contentHash} />
            )}
            {chain.placement.sourceElements && (
              <Identifier label="Source elements" value={chain.placement.sourceElements} />
            )}
          </div>
        </details>
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
            {chain.publication.versions.map((version) => {
              const applies = whenItApplies(version);
              return (
                <li key={version.versionId}>
                  <Text strong>
                    {version.versionNumber == null ? "A version" : `Version ${version.versionNumber}`}
                  </Text>
                  {version.isActive && <Tag color="green" style={{ marginInlineStart: 8 }}>Active</Tag>}
                  {applies && (
                    <Text type="secondary" data-testid={`published-in-${version.versionId}`}>
                      {" "}
                      · {applies}
                    </Text>
                  )}
                  {version.approvedAt && (
                    <Text type="secondary"> · approved {formatMoment(version.approvedAt)}</Text>
                  )}
                </li>
              );
            })}
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
    </div>
  );
}

/**
 * What the document says, at the top of the policy.
 *
 * A reviewer asked for the source text to sit under the title of the policy,
 * where a reader lands. It sat inside the Reading tab, above the rules, which
 * is one click and one scroll away from where somebody opening a policy starts.
 *
 * It is a lead here and evidence there, and both are worth having: this is the
 * passage read whole, before any rule has been drawn over it; the Reading tab
 * puts each passage immediately above the rules formulated from it, which is
 * how a reviewer checks one against the other. Neither is a copy of the other's
 * job.
 *
 * The page is named per passage only where the policy runs across more than one
 * — on a policy that sits on one page the header has already said which, and
 * saying it again per passage is the repetition this tab was rewritten to stop.
 *
 * WHY THE REST IS BEHIND A DISCLOSURE, AND WHY THAT IS NOT A TRUNCATION
 *
 * A policy of eleven passages printed whole is a wall, and a wall at the top of
 * the tab pushes the rules and the trace facts below the fold — which is the
 * complaint this rewrite exists to answer, reintroduced by the fix for it. So
 * the passage the policy opens with is printed, and the remainder is offered
 * with its count said exactly.
 *
 * No quotation is shortened to achieve that: a reader who opens the disclosure
 * gets every later passage in full, in document order, and the Reading tab
 * carries all of them unconditionally either way. What is deferred is a whole
 * passage, named and counted, never a part of one.
 */
function PolicySourcePane({
  source,
  spansPages,
}: {
  source: readonly PolicyRecordSource[] | undefined;
  spansPages: boolean;
}) {
  // A surface that did not supply the passages has not said they are empty, so
  // nothing is claimed about them.
  if (!source) return null;
  const [opening, ...rest] = source;
  return (
    <section className="policy-pane__section" data-testid="overview-source">
      <Text type="secondary" className="policy-pane__label">
        What the document says
      </Text>
      {source.length === 0 ? (
        <Paragraph type="secondary">
          No passage of the source document is attached to this policy.
        </Paragraph>
      ) : (
        <>
          <SourcePassage passage={opening} spansPages={spansPages} />
          {rest.length > 0 && (
            <details className="policy-pane__more" data-testid="overview-source-rest">
              <summary>
                {rest.length === 1
                  ? "The other passage this policy is stated in"
                  : `The other ${rest.length} passages this policy is stated in`}
              </summary>
              <div className="policy-pane__more-body">
                {rest.map((passage) => (
                  <SourcePassage key={passage.key} passage={passage} spansPages={spansPages} />
                ))}
              </div>
            </details>
          )}
        </>
      )}
    </section>
  );
}

/** One passage of the document, quoted whole. */
function SourcePassage({
  passage,
  spansPages,
}: {
  passage: PolicyRecordSource;
  spansPages: boolean;
}) {
  return (
    <div className="policy-pane__passage">
      {spansPages && passage.page !== null && (
        <Text type="secondary" style={{ fontSize: 12 }}>
          Page {passage.page}
        </Text>
      )}
      {passage.quotations.length === 0 ? (
        <Text type="secondary">
          The source text for this passage was not stored with its rules.
        </Text>
      ) : (
        passage.quotations.map((quotation, index) => (
          <p
            key={`${index}-${quotation.slice(0, 32)}`}
            className="policy-card__passage"
            data-verbatim="true"
            data-testid="overview-quotation"
          >
            <DirectionalText align>{quotation}</DirectionalText>
          </p>
        ))
      )}
    </div>
  );
}

/**
 * Every rule the policy holds, named, on one screen.
 *
 * The thing a reviewer most wants to scan, and the thing this tab named not one
 * of. Four parts per rule and none of them merged: the name this app generated
 * for it, the rule's own words, the route it takes, and the id it is known by.
 *
 * ON THE ROUTE CHIP
 *
 * Both routes are first-class ways of settling a case and the chip says so in
 * the same voice for each. Deterministic is computed; AI Ready is read by a
 * judge that returns a verdict with its confidence. A document states some of
 * its tests as comparisons and some in words, and which it did is a property of
 * the document rather than a grade on the extraction — so neither chip is
 * coloured, ranked, ordered ahead of the other, or given a caveat the other
 * does not get.
 */
function PolicyRuleRoster({ record }: { record: PolicyRecordView }) {
  if (record.rules.length === 0) return null;
  return (
    <section className="policy-pane__section" data-testid="overview-roster">
      <Text type="secondary" className="policy-pane__label">
        The rules it holds
      </Text>
      <ol className="policy-pane__roster">
        {record.rules.map((entry, index) => (
          <li key={entry.rule_id} className="policy-pane__rule" data-testid="overview-rule">
            <span className="policy-card__rule-ordinal" aria-hidden>
              {index + 1}
            </span>
            <div className="policy-pane__rule-body">
              {/* Renders nothing until a name has been generated, so a policy
                  nobody has named reads as its rules' own words and no line is
                  held open for something that may never arrive. The door is
                  the draft row; a sealed record has none, and asks nothing. */}
              {entry.candidateId && <RuleName candidateId={entry.candidateId} variant="block" />}
              <p className="policy-pane__rule-title" data-verbatim="true">
                <DirectionalText align>{entry.rule.title}</DirectionalText>
              </p>
              <div className="policy-pane__rule-facts">
                {entry.route && (
                  <Tooltip title={routeExplanation(entry.route)}>
                    <Tag variant="filled" data-testid="overview-rule-route">
                      {policyRouteLabel(entry.route)}
                    </Tag>
                  </Tooltip>
                )}
                <Typography.Text
                  copyable={{ text: entry.rule_id }}
                  className="policy-pane__rule-id"
                >
                  <Text code>{entry.rule_id}</Text>
                </Typography.Text>
              </div>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

/**
 * How a rule of each route is settled, said the same way for both.
 *
 * Mutation-tested: neither sentence may describe its route as pending,
 * unfinished, weaker or a fallback. They are two things a document does, and
 * this app follows the document.
 */
function routeExplanation(route: string): string {
  if (route === "deterministic") {
    return "The source states this test as a comparison between named quantities, so the engine settles a case by computing it.";
  }
  if (route === "ai_ready") {
    return "The source states this test in words, so a language model reads the case against it and returns a verdict with its confidence.";
  }
  return "This is the route recorded on the rule. This view has no words of its own for it and prints the record's.";
}

/**
 * Who put a rule here, in words rather than in field values.
 *
 * `policy-formulator` and `ai_drafted` are what the record stores and what the
 * JSON tab shows. They are not sentences, and a reviewer reading them on this
 * tab was reading our schema rather than our answer.
 */
function authorityWords(owner: string, level: string): string {
  if (level === "ai_drafted") return "Drafted by this app, not yet reviewed by a person";
  if (level === "human_reviewed") return "Reviewed by a person";
  if (!level) return owner;
  return `${owner} · ${level.replace(/_/g, " ")}`;
}

/**
 * A plain-words reading of the policy's record, when a reader asks for one.
 *
 * The reading itself is written by the server, from the same endpoint the
 * Explain dialog uses, so there is one generator and not two accounts of one
 * record that drift apart. What is different here is only where it lands: in
 * the tab a reader opens first, rather than behind a button that opens a modal
 * over it.
 *
 * Asked for rather than fetched on sight, for the reason the publication
 * section gives: a page holding many cards mounts many of these, and a reading
 * nobody asked for costs a model call per policy on the page.
 */
function PolicyPlainWords({
  provisionId,
  policyKey,
}: {
  provisionId: string | null;
  policyKey: string;
}) {
  const [state, setState] = useState<"idle" | "loading" | "failed" | "ready">("idle");
  const [result, setResult] = useState<PolicyExplanation | null>(null);
  const [failure, setFailure] = useState("");

  // A policy that was never persisted as a provision has no address to ask
  // about. Saying nothing is right: there is no reading to offer and no action
  // a reader could take to get one.
  if (!provisionId) return null;

  async function ask(regenerate = false) {
    if (!provisionId) return;
    setState("loading");
    setFailure("");
    try {
      setResult(await aiApi.explainPolicy(provisionId, regenerate));
      setState("ready");
    } catch (error) {
      setFailure(describeApiFailure(error));
      setState("failed");
    }
  }

  return (
    <section
      className="policy-pane__section"
      data-testid="overview-plain-words"
      aria-label={`A plain-words reading of policy ${policyKey}`}
    >
      <Text type="secondary" className="policy-pane__label">
        In plain words
      </Text>

      {state === "idle" && (
        <>
          <Paragraph type="secondary" style={{ marginBottom: 8 }}>
            This app can read its own extraction of this policy back in plain words. It describes
            what was extracted, not what the document says — the document's words are above, to
            read it against.
          </Paragraph>
          <Button
            size="small"
            onClick={() => void ask()}
            data-testid="overview-request-plain-words"
          >
            Read it in plain words
          </Button>
        </>
      )}

      {state === "loading" && <Paragraph type="secondary">Reading the record…</Paragraph>}

      {state === "failed" && (
        <Alert
          type="warning"
          showIcon
          data-testid="overview-plain-words-failed"
          message="The request did not complete"
          description={
            <>
              <p>{failure}</p>
              <Button size="small" onClick={() => void ask()}>
                Try again
              </Button>
            </>
          }
        />
      )}

      {state === "ready" && result && (
        <>
          {result.explanation ? (
            <div
              className="policy-pane__reading"
              data-generated="true"
              data-testid="overview-plain-words-text"
            >
              {/* Said before the reading rather than after it. A caveat under a
                  paragraph is read by someone who has already believed the
                  paragraph. */}
              <Text type="secondary" style={{ fontSize: 12 }}>
                <span aria-hidden>✦</span> In plain words, by this app. It describes what was
                extracted, not what the document says — the document's own words are above, to
                read it against.
              </Text>
              {/* Unquoted: quotation marks would present these as somebody's
                  exact words, and they are nobody's. */}
              <div className="policy-pane__reading-text">
                <DirectionalText>{result.explanation}</DirectionalText>
              </div>
              <Text type="secondary" style={{ fontSize: 12 }}>
                Written by {result.model_deployment ?? "a language model"}
                {result.generated_at ? ` on ${formatMoment(result.generated_at)}` : ""}
                {result.generated_earlier ? ", from this record as it stands now." : "."}
                {!result.covers_every_rule &&
                  ` It covers the first ${result.rules.length} of this policy's ${result.rule_count} rules; the rest are listed below and are unaffected.`}
              </Text>
              <Button size="small" onClick={() => void ask(true)}>
                Write it again
              </Button>
            </div>
          ) : (
            <Paragraph type="secondary" data-testid="overview-plain-words-none">
              {result.unavailable_code
                ? "A reading was asked for and none was written. The Explain dialog on this policy says which of the reasons applied; the document's words are above and the rules are below, which is where the answer is either way."
                : "No language model is configured on this server, so no reading was asked for. Nothing else on this tab is affected by that — it is all from the record itself."}
            </Paragraph>
          )}
        </>
      )}
    </section>
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
            Every rule of this policy takes the AI Ready route: the words of its source
            are the test, and a judge applies them to the case in front of them.
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
              comes from. A rule its source states in words takes the AI Ready route: the words
              are the test, and a judge applies them.
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
  /** Whether the engine that computes comparisons evaluates this rule.
   *
   *  Scenario generation is a blind validation batch, and a blind validation
   *  batch is run by that engine. A rule whose test is stated in words takes the
   *  AI Ready route, so the engine is not the
   *  instrument that checks it and the server says so when asked.
   *
   *  This is read off the rule rather than passed in, and it selects which
   *  rules the control offers to write for. Offering it on every rule and
   *  letting the server refuse would teach a reviewer, through the refusal,
   *  that one of two routes is the lesser — which is the same claim the copy
   *  guards exist to keep out of the words, arriving through the interaction
   *  instead. */
  engineEvaluates: boolean;
  /** Which door this rule can actually be tested through, here and now.
   *
   *  `engineEvaluates` answers what the rule is; this answers what can be asked
   *  of it, which is the same question plus whether a published version exists
   *  for the engine to compute against. Both are derived from the record — see
   *  `testingDoor`. */
  door: TestingDoor;
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
  publishedVersionId?: string | null,
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
      engineEvaluates: engineDecidesRule(entry.rule),
      door: testingDoor(entry.rule, publishedVersionId),
    };
  });
}

/**
 * What this pane can ask for. Absent means asking is not available here, and
 * the pane then says so rather than rendering a control that does nothing.
 */
export type PolicyTestingVerbs = Pick<
  PolicyTesting,
  "generate" | "run" | "publishedVersionId" | "busy" | "working" | "error" | "dismissError"
>;

export function PolicyTestsPane({
  record,
  tests,
  loading,
  testing,
  policySetKey,
}: {
  record: PolicyRecordView;
  tests: readonly PolicyTestListItem[] | null;
  loading?: boolean;
  testing?: PolicyTestingVerbs;
  /**
   * The set this policy is read within. The engine's own scenario runner
   * addresses a rule through its set, so it wants this; the judge reads the
   * record it is handed, so the case box opens on that route with whatever the
   * caller supplies.
   */
  policySetKey?: string;
}) {
  const rows = policyTestRows(record, tests ?? [], testing?.publishedVersionId ?? null);
  const covered = rows.filter((row) => row.state !== "untested").length;
  const writableRows = rows.filter((row) => row.door === "engine-scenario");
  const untestedRuleIds = writableRows
    .filter((row) => row.state === "untested")
    .map((row) => row.ruleId);
  const everyTestId = rows.flatMap((row) => row.testIds);
  const awaitingReview = rows.reduce((total, row) => total + row.awaitingReview, 0);
  const readDecided = rows.filter((row) => row.door === "judge-case").length;
  const awaitingPublication = rows.filter((row) => row.door === "engine-awaits-publication").length;
  const [caseRuleId, setCaseRuleId] = useState<string | null>(null);
  const [policyCaseOpen, setPolicyCaseOpen] = useState(false);
  const caseRule = caseRuleId
    ? (record.rules.find((entry) => entry.rule_id === caseRuleId)?.rule ?? null)
    : null;

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
          {testing.generate && writableRows.length > 0 && (
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
                void testing.generate?.(
                  untestedRuleIds.length > 0 ? untestedRuleIds : writableRows.map((r) => r.ruleId),
                );
              }}
              disabled={testing.working}
            >
              <Button size="small" type="primary" loading={testing.working} data-testid="policy-generate-tests">
                {untestedRuleIds.length > 0
                  ? `Write scenarios for ${share(untestedRuleIds.length, rows.length)} with no test`
                  : "Write more scenarios"}
              </Button>
            </Popconfirm>
          )}
          <Button
            size="small"
            type={testing.generate ? "default" : "primary"}
            onClick={() => setPolicyCaseOpen(true)}
            data-testid="policy-put-case"
          >
            Put a case to this policy
          </Button>
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

      {testing && readDecided > 0 ? (
        <Paragraph type="secondary" data-testid="policy-tests-instrument">
          A rule stating a comparison is checked by writing a scenario the engine computes, and the
          result is kept. A rule stating its test in words is checked by putting a case to the judge
          that reads it — from its row, or to the whole policy at once — and what comes back is an
          answer to look at rather than a record to keep.
        </Paragraph>
      ) : null}

      {testing && awaitingPublication > 0 ? (
        <Paragraph type="secondary" data-testid="policy-tests-awaits-publication">
          {awaitingPublication === 1
            ? "One rule of this policy states its test as a comparison between named quantities."
            : `${awaitingPublication} rules of this policy state their test as a comparison between named quantities.`}{" "}
          The engine computes those against a published version, and this policy has not been
          published yet — so writing scenarios for them is offered once it is. Every rule stating
          its test in words can be put to a case now.
        </Paragraph>
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
                    ) : row.door === "engine-scenario" && testing.generate ? (
                      <Button
                        size="small"
                        type="link"
                        loading={testing.busy.has(row.ruleId)}
                        disabled={testing.working}
                        onClick={() => {
                          void testing.generate?.([row.ruleId]);
                        }}
                        data-testid={`generate-rule-test-${row.ruleId}`}
                      >
                        Write one
                      </Button>
                    ) : row.door === "judge-case" ? (
                      <Button
                        size="small"
                        type="link"
                        onClick={() => setCaseRuleId(row.ruleId)}
                        data-testid={`put-case-${row.ruleId}`}
                      >
                        Put a case
                      </Button>
                    ) : (
                      <Tooltip title="The engine computes this rule's comparison against a published version. Once this policy is published, writing a scenario for it is offered here.">
                        <Text type="secondary" data-testid={`awaits-publication-${row.ruleId}`}>
                          Once published
                        </Text>
                      </Tooltip>
                    ),
                } as const,
              ]
            : []),
        ]}
      />

      {policyCaseOpen ? (
        <Modal
          open
          width={860}
          onCancel={() => setPolicyCaseOpen(false)}
          footer={null}
          title="Put a case to this policy"
          destroyOnHidden
        >
          <PolicyCaseRunner
            policySetKey={policySetKey}
            publishedVersionId={testing?.publishedVersionId ?? null}
            rules={record.rules.map((entry) => entry.rule)}
          />
        </Modal>
      ) : null}

      {caseRule ? (
        <Modal
          open
          width={720}
          onCancel={() => setCaseRuleId(null)}
          footer={null}
          title="Put a case to this rule"
          destroyOnHidden
        >
          <div data-testid="policy-case-box">
            <Paragraph type="secondary" style={{ marginBottom: 12 }}>
              <DirectionalText>{caseRule.title}</DirectionalText>
            </Paragraph>
            <Paragraph type="secondary" style={{ marginBottom: 12, fontSize: 12 }}>
              An answer read here is yours to look at. It is not saved to this policy's tests and
              does not change what the table reports, which describes the scenarios stored against
              the rule.
            </Paragraph>
            <RuleScenarioTester policySetKey={policySetKey ?? ""} rule={caseRule} />
          </div>
        </Modal>
      ) : null}
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
  /** From and until when the version this policy was sealed into applies.
   *  Absent where the record holds no date. An absent end is not an open end —
   *  see `is_active`, which is what says whether a version applies at all. */
  effective_from?: string | null;
  effective_to?: string | null;
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

