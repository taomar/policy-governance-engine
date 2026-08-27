# User guide

This guide is for the person who owns a policy and has to stand behind it — a compliance owner, a policy author, a risk or audit reader — and for the engineer wiring a system to the decisions that come out.

It follows one document all the way through: upload, extraction, review, publication, and then the four things you do with a published register that make the work worth doing — **put a real case to it**, **prove its behaviour**, **compare it against the next edition**, and **serve it to other systems**.

Everything shown here is the running product. Where a capability has a limit, the limit is stated next to it.

**Related pages:** [Workflows](workflows.md) for the short operational sequence · [From document to policy](from-document-to-policy.md) for what happens inside extraction · [API](api.md) for the integration surface · [Known limitations](known-limitations.md) for what this build does not do.

---

## The shape of the work

| Stage | You do | The platform does | Result |
|---|---|---|---|
| **Load** | Upload a PDF or DOCX | Preserves the source, segments it into clauses, reports what it could not read | A controlled document version |
| **Extract** | Start a run | Finds policy passages, verifies each one word-for-word, drafts candidate rules | Candidates, each carrying its source sentence |
| **Review** | Approve, reject, or ask for a rewrite | Shows the source beside the drafted logic, flags what it doubts | Decided candidates |
| **Assure** | Run a quality evaluation | Inspects source and logic faithfulness, grades findings | Evidence for a publication decision |
| **Publish** | Approve a version | Freezes it, numbers it, records who approved it | An immutable published version |
| **Use** | Ask, test, evaluate, compare | Answers with the rule, the version and the sentence | Decisions you can defend |

Two rules hold across all of it:

- **Nothing decides anything until a person approves it.** Extraction produces candidates, never live policy.
- **A published version never changes.** Corrections become a new version; the old one stays readable.

---

## 1. Sign in

Sign in with a local account or an identity provider, depending on how the instance is configured. Your role decides which surfaces you see.

| Role | Can |
|---|---|
| **Viewer** | Evaluate cases and read the register. Cannot upload, author or approve. |
| **Policy author** | Everything a viewer can, plus upload, review, approve and publish. |
| **Admin** | Everything, plus project lifecycle including deletion. |

The header shows who you are and which role is in effect. If an action is missing, the role is usually why.

> **Before you rely on this build:** authorization ships present but **off by default** (`RBAC_ENABLED`). Until an operator enables it and configures sign-in, roles are workflow attribution rather than a security boundary. See [Known limitations](known-limitations.md).

---

## 2. The dashboard

![The dashboard: review queue, decision routes, and the portfolio register](images/user-guide/01-dashboard.png)

The dashboard answers one question — *what needs a person?*

- **Review queue** — how many policies and rules are waiting for a decision, across every project.
- **High findings** — the count from the latest quality checks, scoped so you can tell a published finding from a candidate one.
- **Decision routes** — how the live rules split between Deterministic and AI Ready. Not a score; see [§8](#8-two-routes-one-register).
- **Regression guards** — how many saved scenarios protect the published versions.

Below, the **portfolio register** lists each project with what it actually holds: policies, rules, what is in review, the route split, and the published version. Counts always name their unit — *policies* and *rules* are different things, and a policy contains rules.

---

## 3. Open a project

![The project workspace: governance status and the working tabs](images/user-guide/02-project-overview.png)

A project is one policy set — a handbook, a procurement policy, a leave scheme. Opening one gives you its governance status and the tabs you will work through: **Documents**, **Review**, **Policies**, **Compare**, **Quality**, **Validation** and **Decision Log**.

The header carries the project key, its owner, and the actions that apply to the whole set: **Edit**, **Record periodic review**, and **Test a Case**.

Each tab badge is a real count — documents held, rules awaiting a decision, published policies, versions available to compare. If a tab has no badge, it has nothing waiting for you.

---

## 4. Load a document

Go to **Documents**.

![The Documents tab: source control and ingestion diagnostics](images/user-guide/03-documents.png)

Upload a PDF or DOCX. The platform stores the source first, converts it to canonical text, and segments it into numbered clauses that keep their page, section and character offsets.

**Read the ingestion diagnostics before extracting.** They are how the load stage tells you it fell short:

| Diagnostic | Means |
|---|---|
| `low_coverage` | Much of the source text did not reach a logical element — content may be trapped in an unparsed region. |
| `fragment_offsets_unresolvable` | Some clause text cannot be located back in the page it came from. |
| `element_text_not_rebuilt_from_fragments` | An element's stored text is not its recorded fragments joined as declared. |
| `rtl_script_detected` | Right-to-left content was found; reading order was recovered where possible. |

A scanned PDF with no text layer will produce very few clauses. That is visible here, before you spend an extraction run on it.

Uploading a document with the **same title into the same project** creates a **new version** of that document rather than a second document — which is what makes version comparison possible later.

---

## 5. Extract candidate rules

Start extraction from the project. The run reads the clauses, finds the passages that state policy, verifies each passage back against the source, and drafts candidate rules from them.

Extraction is server-side and takes minutes on a real handbook. When it finishes you get candidates, each carrying:

- the **source passage**, word-for-word;
- **where it came from** — document version, page, section, clause;
- a drafted **subject, condition and outcome**;
- a **route** (see [§8](#8-two-routes-one-register));
- any **findings** the platform already doubts.

**Coverage is reported, not implied.** A run that finished and a run that read everything are different things, and the record says which. See [Extraction run coverage](extraction-run-coverage.md).

Re-running extraction on the same document supersedes *unreviewed* drafts only. **Approvals and rejections you have already made are never overwritten.**

---

## 6. Review against the source

![The review queue: candidates with source evidence and the inspector](images/user-guide/04-review-queue.png)

This is where the work happens, and the queue is built so you can decide without leaving it.

**Narrow first.** Filter by document, by extraction run, by route, by finding severity, or search titles, actions, rule ids and tags. The banded family view groups rules that came from the same provision, so you can decide a topic as a unit rather than meeting the same clause six times as six unrelated cards.

**Then inspect.** Selecting a candidate opens it beside the queue with tabs:

| Tab | Shows |
|---|---|
| **Overview** | What the document says, and what was drafted from it, side by side |
| **Reading** | The passage in its surrounding context |
| **Logic** | The rule as *applies* and *outcome* attributes — subject, condition, effect |
| **Parties & routes** | Who it binds, who decides, and which route it takes |
| **Scope** | What it applies to, and what it excludes |
| **Tests** | Scenarios attached to this rule |
| **History** | Every prior sighting of this provision across runs |
| **Notes** | Reviewer commentary |
| **JSON** | The canonical record exactly as the evaluator reads it |

![The Logic tab: a rule as applies and outcome attributes, with its source below](images/user-guide/10-rule-logic.png)

**Decide.** Approve, reject, or request a rewrite. The assistant can propose a rewording; it never changes a record on its own, and the proposal is shown against the source for you to accept or discard.

**Decided together.** Where several rules come from one provision, the inspector says so — approving one alone can leave a topic half-decided.

---

## 7. Run a quality evaluation before publishing

![The Quality tab: scope, history, findings and recommended decisions](images/user-guide/06-quality.png)

Quality answers one question: **what prevents this exact policy version from being relied on?**

**Choose the scope.** The published version, or the rules still in review. The two are different questions and the screen keeps them apart — a finding about published v1 says nothing about a candidate you have not decided yet.

**The evaluation is read-only.** Running it never changes a rule, an approval or a published version. It records the result, so the history below can compare this run against the one before it.

**Findings are graded and explained.** Each row gives the risk level, what the evaluation found, the affected rules, a recommended decision, and a link to the evidence. Two families run:

- **Source faithfulness** — does the rule still say what the document said? Negation preserved, quantities preserved, conditions represented, source conditions reached the record, the action is not a sentence fragment, the passage is the document's own words.
- **Logic faithfulness** — does the compiled logic hold up? Attributes and parties quoted from source, authority is a real delegation, discretion names who exercises it, malformed decomposition reported, polarity survives projection.

**Checks that did not apply are held apart from findings.** A route-specific check has nothing to say about records on the other route, and the screen reports that as what it is rather than as a check that ran and came back clean.

> Findings are evidence for a reviewer, not a gate. The platform does not approve, reject or publish anything on their basis.

---

## 8. Two routes, one register

Every rule is classed by **how its source is written**, not by how good the extraction was.

| Route | The source states | Decided by |
|---|---|---|
| **Deterministic** | A test you can compute — *"…a nominal value of less than 50.00 SAR."* | A FEEL evaluator running a compiled condition. Same input, same answer, every time. |
| **AI Ready** | A judgement in words — *"…dress in professional business attire."* | A judge reading the rule against the case, answering with the sentence it relied on. |

Neither is a grade, and neither is a fallback. Most real policy prose takes the AI Ready route because that is how humans write policy. Forcing a judgement into a computed threshold would invent a number the document never set.

---

## 9. Publish an immutable version

Publishing takes the approved rules and freezes them into a numbered version with an effective date and a named approver.

From that moment the version cannot be edited. A correction is a **new version**; the previous one stays readable, and anything that cited it still resolves.

Publishing also rebuilds the search index for the version and re-runs any active regression guards ([§12](#12-prove-behaviour-with-blind-tests)).

---

## 10. The published register

![Published policies: the register, with the inspector open](images/user-guide/05-published-policies.png)

The **Policies** tab is the published register — read-only decision records, arranged under the provisions that stated them.

- The version strip names the version, its state, and how many policies and rules it holds.
- Search and filters narrow the register; related families group provisions that belong together.
- Selecting a policy opens the same inspector tabs as review, now against published content.
- **Export** the filtered set or the whole register as JSONL.

---

## 11. Put a real case to it

This is the shortest route to understanding what the platform is for. Use **Test a Case** from the project header.

![Test a Case: describing a real situation in plain English](images/user-guide/11-test-a-case.png)

Describe a situation in plain English and put it either to one published policy or to the whole project. Choose a reasoning effort if the case is subtle.

![The result: narrowing, quality-finding link, verdict, and the rules it rests on](images/user-guide/12-case-result.png)

The result is the point. Read it top to bottom:

1. **Narrowing** — how many published policies were considered, how many were retained, how many were discarded, and *why* each one was discarded. The project is not evaluated as one undifferentiated blob, and the screen shows you the shortlist.
2. **Known quality findings** — if any rule in the answer is covered by an open finding, it is named here with its severity. A reviewer sees *"a known finding covers these rules"* rather than an unexplained answer.
3. **Which route answered** — the AI Ready judge or the FEEL evaluator. You always know what decided.
4. **The verdict** — the decision returned by the evaluated published policies.
5. **The explanation** — composed by the app, clearly labelled as such, citing rule ids.
6. **The rules it rests on** — each cited rule with its id, section, page, and the **exact sentence** from the document.

That last item is the whole proposition. The answer is not a summary of the handbook; it is a decision with the sentences that produced it, which a person can check against the source.

---

## 12. Prove behaviour with blind tests

![Validation: sealed scenarios, blind runs, and regression guards](images/user-guide/08-validation.png)

**Validation** proves a policy behaves as written, and keeps the proofs you trust as guards that re-run on every future published version.

The four-step method exists to stop a test being written to match whatever the engine already does:

1. **Select policies** — choose exactly which published policies are under test.
2. **Generate & seal** — scenarios are generated and the expected answer is **committed and hidden before execution**.
3. **Run blind** — the sealed scenarios go through the deterministic engine, which cannot see the expectation.
4. **Reveal & preserve** — the comparison is revealed, and the scenarios that pass can be kept as **regression guards**.

Guards then re-run automatically on every publish. The panel at the top shows how many are active, passing, failing, erroring, never run, or retired — and states plainly when **no guard protects the policy set yet**.

You can generate combinations across the selected policies, or supply your own scenario statement. Grounding is either the full policy JSON or JSON plus hybrid search, and the screen says which the model saw. Every generated batch, grounding set, commitment and engine run is retained in the validation history.

> Definitions carry no test to run, and are excluded from the batch rather than counted as passing.

---

## 13. Compare against the next edition

![Compare Versions: the AI summary and the rule-by-rule difference](images/user-guide/07-compare-versions.png)

When the policy is revised, upload the new edition **under the same title** and extract it. It becomes the next document version, and its candidates are compared against the current baseline.

The **Compare** tab diffs two published versions rule by rule, with an AI-written summary of what the update does in practice, then the added, removed, changed and unchanged rules.

**One distinction worth understanding.** Re-reading a document does not reproduce byte-identical records — the same sentence can be read slightly differently on a later run. So a naive diff reports every re-reading as a change, and the handful of real revisions hide among them. The candidate delta separates:

- **changed in source** — the document's own words moved. This is what a reviewer must read.
- **re-extracted** — the same sentence, read differently. Reported separately so it cannot bury the above.

> The published-version compare shown above has a related limitation, stated on the screen itself: AI-drafted rules receive a fresh id on each extraction, so re-extracting a document and publishing it will show its rules as *added* rather than *changed* against a prior AI extraction. That is a property of matching drafted rules across independent runs, not a fault in the diff.

---

## 14. Serve decisions to other systems

![Evaluate: the decision path a calling system invokes](images/user-guide/13-evaluate.png)

**Evaluate** is the evaluation API's own surface — the decision path a calling system invokes, run by hand so you can preview exactly what that system would receive.

Supply the facts of a case. The required facts are generated from the selected version's rules, so you can see what the register actually needs to decide. Optionally supply principal context — persona, organisational unit, jurisdiction — which is used only to check scope-restricted rules; the facts still drive whether a condition is satisfied.

Choose the active version or pin a specific one. Pinning gives a reproducible answer; following the active version means the caller inherits revisions when you publish them.

The response carries the determination for each rule, and those requests are what the evaluation audit trail records.

For the endpoint groups, request shapes and common sequences, see the [API guide](api.md).

---

## 15. Ask the policy in plain words

![Ask AI, scoped to the selected project](images/user-guide/14-ask-ai.png)

**Ask AI** answers questions about a policy set from its approved rules, grouping verbatim source facts by topic and keeping the AI's own synthesis separate and labelled.

Use it for *"what does this say about…"*. Use **Test a Case** ([§11](#11-put-a-real-case-to-it)) when you want a decision on a specific situation — that is a reviewer's tool and it writes to the audit trail.

---

## 16. Audit and periodic review

![The Decision Log](images/user-guide/09-decision-log.png)

The **Decision Log** retains what was asked, what answered, and which version decided. Every mutation is audited, and evaluations are retained as evidence.

**Record periodic review** — on the project header — attests that a policy set has been reviewed, in the shape [ISO 37301](standards.md) §9.3 expects. It records the attestation and sets the next review date; the register shows when a project is overdue.

---

## 17. The document inbox

![The Document Inbox](images/user-guide/15-document-inbox.png)

The inbox holds documents that have arrived but are not yet assigned to a project. Use it to triage sources before deciding which policy set they belong to.

---

## Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| Extraction produced very few rules | The source has little readable text, or is a scan | Check the ingestion diagnostics on **Documents** before re-running |
| AI routes return `503` | Azure AI settings are blank or unreachable | Validate the settings; deterministic features keep working meanwhile |
| `clauses_search_indexed` is `0` | Search indexing was unavailable | The clauses are stored — this reports the search index only, and upload still succeeded |
| Quality shows no findings on a candidate set | The run was scoped to the published version | Switch the scope to rules still in review |
| Compare says it needs two versions | Only one version is published | Publish a second version before comparing |
| A version comparison looks noisy | Re-extraction produced different records for unchanged sentences | Read the *changed in source* group first — see [§13](#13-compare-against-the-next-edition) |

---

## Safe operating rules

1. **Read the ingestion diagnostics before extracting.** They tell you whether the document was readable at all.
2. **Decide a provision as a unit.** Approving one rule of a family can leave the topic half-decided.
3. **Check the quality scope before quoting a number.** Published and in-review are different questions.
4. **Publish deliberately.** The version is immutable, and downstream systems may pin it.
5. **Keep guards after they pass.** A scenario you verified is worth more re-running on every future publish than it was the day you wrote it.
6. **Treat a citation as the evidence.** If the sentence does not support the rule, the rule is wrong regardless of how confident the record reads.
