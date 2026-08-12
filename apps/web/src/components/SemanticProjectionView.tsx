import { Tag, Tree, Typography } from "antd";
import type { CanonicalPolicyRule, CanonicalRule, PolicyFact } from "../api";
import { effectMeta } from "../ruleDisplay";

const { Text } = Typography;

/**
 * The logic a policy states, in the policy's own terms.
 *
 * This panel used to render every rule as a XACML request: `subject.subject-id
 * = "board-of-trustees"`, `action.action-id = "limit"`, `resource.resource-id =
 * "for specific cases that the university deems necessary"`, under headings
 * reading `REQUIRES · XACML PERMIT` and `OBLIGATION`, with a footnote citing
 * OASIS XACML 3.0.
 *
 * Three things were wrong with that, and only the third is cosmetic.
 *
 * It put clauses in identifier slots. A resource identifier is a name a request
 * is matched against; "for specific cases that the university deems necessary"
 * is a sentence. Slugging it produced
 * `for-specific-cases-that-the-university-deems-necessary`, an eighty-character
 * identifier that identifies nothing — the same defect that once put a whole
 * clause in the action slot, reappearing one slot over.
 *
 * It classified by grammar. In "Increase due to inflation … subject to the
 * judgment and approval of the Board of Trustees", the Board was shown as the
 * subject because a party was found there, while the increase — what the rule
 * is actually about — was filed under `unclassified` along with the 5% bound.
 *
 * And it spoke a vocabulary nothing here uses. These records are read by a
 * search API and by a judge, and a policy is either decided by comparison or by
 * reading. Neither consumer takes a XACML request, so the notation added a
 * translation step between the reader and the document without adding a fact.
 *
 * What replaces it is the canonical decomposition, which is verbatim source
 * text throughout, laid out as: what the rule governs, what narrows it, what
 * follows, and what a case must supply. Where the fact model names one of those
 * phrases the name is shown beside it, because that is the identifier a
 * consumer binds a value to — but the phrase leads, since that is what a reader
 * checks against the document.
 */

interface TreeDatum {
  key: string;
  title: React.ReactNode;
  children?: TreeDatum[];
}

/** Canonical fields that narrow when a rule applies. */
const SCOPE_FIELDS = [
  "condition",
  "prerequisite",
  "trigger",
  "temporal_constraint",
  "constraint",
] as const;

/** Canonical fields naming the class of people or places a rule covers. */
const AUDIENCE_FIELDS = ["beneficiary", "recipient", "candidate", "location"] as const;

/** Canonical fields carrying what follows. */
const OUTCOME_FIELDS = ["object", "threshold", "calculation", "frequency", "deadline"] as const;

/** Canonical fields naming who acts, decides, or is carved out. */
const PARTY_FIELDS = ["assigner", "actor", "exception"] as const;

type CanonicalField = keyof CanonicalPolicyRule;

/** Plain labels, in the vocabulary of policy rather than of a request format. */
const FIELD_LABEL: Partial<Record<CanonicalField, string>> = {
  condition: "only when",
  prerequisite: "only after",
  trigger: "on",
  temporal_constraint: "timing",
  constraint: "limited by",
  beneficiary: "for",
  recipient: "paid to",
  candidate: "for",
  location: "at",
  object: "what",
  threshold: "limit",
  calculation: "worked out as",
  frequency: "how often",
  deadline: "by",
  assigner: "decided by",
  actor: "carried out by",
  exception: "except",
};

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

/** One row: the document's phrase, labelled by the part it plays. */
function phraseRow(key: string, label: string, phrase: string, fact?: PolicyFact): TreeDatum {
  return {
    key,
    title: (
      <span className="cond-leaf">
        <Text type="secondary" className="semantic-projection-slot">
          {label}
        </Text>
        <Text>{phrase}</Text>
        {fact && (
          <Text code className="cond-fact">
            {fact.name}
            {fact.data_type ? `: ${fact.data_type}` : ""}
          </Text>
        )}
      </span>
    ),
  };
}

function groupNode(key: string, label: string, children: TreeDatum[]): TreeDatum {
  return {
    key,
    title: (
      <Text strong className="cond-group-label">
        {label}
      </Text>
    ),
    children,
  };
}

/** The published fact whose source phrase is this one, if there is one. */
function factFor(facts: PolicyFact[], phrase: string): PolicyFact | undefined {
  const needle = phrase.toLowerCase();
  return facts.find((fact) => fact.source_phrase.trim().toLowerCase() === needle);
}

function rowsFor(
  core: CanonicalPolicyRule,
  fields: readonly string[],
  facts: PolicyFact[],
  keyPrefix: string,
  skip: Set<string>
): TreeDatum[] {
  const rows: TreeDatum[] = [];
  for (const field of fields) {
    const phrase = text((core as unknown as Record<string, unknown>)[field]);
    if (!phrase || skip.has(phrase.toLowerCase())) continue;
    skip.add(phrase.toLowerCase());
    rows.push(
      phraseRow(
        `${keyPrefix}-${field}`,
        FIELD_LABEL[field as CanonicalField] ?? field,
        phrase,
        factFor(facts, phrase)
      )
    );
  }
  return rows;
}

export function SemanticProjectionView({ rule }: { rule: CanonicalRule }) {
  const core = rule.formulation?.canonical?.rule;
  if (!core) return null;

  const facts = rule.fact_model ?? [];
  const subject = text(core.subject);

  // One phrase routinely fills several canonical fields. Showing it once, under
  // the first part it plays, keeps the panel a description of the sentence
  // rather than of the schema — repeating an amount as both `object` and
  // `threshold` reads as two limits.
  const shown = new Set<string>();

  // GOVERNS — the thing the rule is about, then the class it covers.
  const governs: TreeDatum[] = [];
  if (subject) {
    shown.add(subject.toLowerCase());
    governs.push(phraseRow("gov-subject", "this", subject, factFor(facts, subject)));
  }
  governs.push(...rowsFor(core, AUDIENCE_FIELDS, facts, "gov", shown));

  // WHEN — every field that narrows the rule. Absence is stated rather than
  // filled in: a rule that narrows nothing applies whenever its subject matter
  // arises, and saying so is different from having failed to look.
  const when = rowsFor(core, SCOPE_FIELDS, facts, "when", shown);

  // THEN — what follows, as the sentence writes it. The modality stays attached
  // to the predicate: "shall not exceed 10%" and "exceed 10%" are opposite
  // instructions, and the second is what a reader saw when only the verb was
  // shown.
  const then: TreeDatum[] = [];
  const predicate = text(core.predicate);
  if (predicate) {
    const modality = text(core.modality);
    then.push(phraseRow("then-does", "does", [modality, predicate].filter(Boolean).join(" ")));
  }
  then.push(...rowsFor(core, OUTCOME_FIELDS, facts, "then", shown));
  then.push(...rowsFor(core, PARTY_FIELDS, facts, "then-party", shown));

  const effect = effectMeta(rule.effect?.type ?? "");

  const contextTree: TreeDatum[] = [
    groupNode(
      "governs",
      "GOVERNS",
      governs.length > 0
        ? governs
        : [{ key: "gov-none", title: <Text type="secondary">not stated</Text> }]
    ),
    groupNode(
      "when",
      "WHEN",
      when.length > 0
        ? when
        : [
            {
              key: "when-none",
              title: <Text type="secondary">the source states no condition</Text>,
            },
          ]
    ),
  ];

  const outcomeTree: TreeDatum[] = [
    groupNode(
      "then",
      effect.label.toUpperCase(),
      then.length > 0
        ? then
        : [{ key: "then-none", title: <Text type="secondary">no outcome stated</Text> }]
    ),
  ];

  return (
    <div className="semantic-projection">
      <Tree
        treeData={contextTree}
        defaultExpandAll
        selectable={false}
        showLine={{ showLeafIcon: false }}
        className="cond-tree"
      />

      <div className="semantic-projection-effect">
        <Text type="secondary" className="semantic-projection-label">
          Outcome
        </Text>
        <Tree
          treeData={outcomeTree}
          defaultExpandAll
          selectable={false}
          showLine={{ showLeafIcon: false }}
          className="cond-tree"
        />
      </div>

      {facts.length > 0 && (
        <div className="semantic-projection-facts">
          <Text type="secondary" className="semantic-projection-label">
            A case must supply
          </Text>
          <div className="semantic-projection-fact-list">
            {facts.map((fact) => (
              <Tag key={fact.name} className="semantic-projection-fact">
                {fact.name}
                {fact.data_type ? ` · ${fact.data_type}` : ""}
              </Tag>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/** Whether a rule carries a canonical decomposition worth showing. */
export function hasSemanticProjection(rule: CanonicalRule): boolean {
  const core = rule.formulation?.canonical?.rule;
  if (!core) return false;
  return Boolean(text(core.subject) || text(core.predicate) || text(core.object));
}
