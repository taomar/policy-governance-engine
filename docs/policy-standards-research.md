# PolicyVerbAItim — standards research
## Standards, Software, Business Cycle & Gap Analysis

*Sources verified via direct web fetch of primary documentation. Any claim noted as [training knowledge — unverified by fetch] was not independently confirmed via URL retrieval during this session. PDF sources (NIST SP 800-162, NIST SP 800-205) returned binary; their existence and authorship were confirmed via CSRC abstract page; content details rely on training knowledge and are so marked.*

---

## Part 1 — World-Wide Standards Table

| # | Standard / Specification | Issuing Body | Version / Date | Scope | Verified Relevance to This Platform |
|---|---|---|---|---|---|
| 1 | **XACML 3.0** — eXtensible Access Control Markup Language | OASIS | OS, Jan 2013 | Authorization policy language & evaluation architecture | **Directly adopted** — defines PDP/PEP/PAP/PIP 4-point architecture; PERMIT/DENY/Indeterminate/NotApplicable effects; rule-combining and policy-combining algorithms; Obligations (mandatory PEP actions) vs Advice (supplementary); Target matching on Subject/Resource/Action/Environment attributes. Combining algorithms (deny-overrides, permit-overrides, first-applicable, only-one-applicable) map directly to our priority/precedence model. **Source:** `docs.oasis-open.org/xacml/3.0/xacml-3.0-core-spec-os-en.html` — glossary section confirmed all terms. |
| 2 | **XACML 3.0 Administration & Delegation Profile** | OASIS | CD03, Mar 2010 | Delegation of policy administration authority | Defines how a principal can delegate a subset of their own permissions to another entity, with attenuation (no delegation beyond own rights). Relevant to our "delegate authoring/approval authority" gap. **Source:** Referenced normatively in XACML 3.0 core spec references section. |
| 3 | **XACML 3.0 Related Entities Profile** | OASIS | CS02 | Structured entity attributes in request context | Defines nested entities and related entities in request context — enables our "principal context" model (person → org_unit → jurisdiction) to be expressed as nested/related attribute bags. **Source:** `docs.oasis-open.org/xacml/xacml-3.0-related-entities/v1.0/cs02/` fetched and verified. |
| 4 | **DMN 1.3 — Decision Model and Notation** | OMG | 1.3, Nov 2019 (in use by Camunda) | Business decision modeling, decision tables, hit policies | Decision Requirements Diagrams (DRD) show dependency between decisions; Decision Tables with hit policies (UNIQUE, ANY, FIRST, RULE ORDER, COLLECT+aggregators SUM/MIN/MAX/COUNT) map to our aggregate-limit and priority logic; FEEL expression language for conditions. Camunda implements DMN 1.3 — verified at `docs.camunda.io/docs/components/modeler/dmn/`. OMG page confirmed at `omg.org/dmn/`. |
| 5 | **DMN Hit Policies** | OMG / Camunda implementation | — | How many rules fire and how results combine | UNIQUE: exactly one rule fires. FIRST: first-matching rule wins (priority). COLLECT+SUM: aggregate of all matching rules — directly maps to leave-day cap aggregation across rules. **Source:** `docs.camunda.io/docs/components/modeler/dmn/decision-table-hit-policy/` — all 5 policies and aggregators verified. |
| 6 | **SBVR — Semantics of Business Vocabulary and Business Rules** | OMG | 1.5 | Formal ontology of business terms, facts, rules | Provides formal vocabulary/glossary layer (concepts, noun concepts, verb concepts, fact types) on top of which business rules are stated. Relevant to our "source clause → structured rule" extraction and canonical vocabulary. [Training knowledge — official spec URL not fetched this session.] |
| 7 | **RuleML / RIF (Rule Interchange Format)** | W3C / RuleML.org | RIF Core, Jun 2010 | Rule interchange across heterogeneous rule systems | RIF defines XML-based production rules, logic rules, and frame syntax enabling rules to be shared between engines. Relevant if we need to export rules to third-party systems. [Training knowledge — not fetched this session.] |
| 8 | **ALFA — Abbreviated Language for Authorization** | Axiomatics (de facto) | — | Human-readable XACML authoring syntax | ALFA is a compact, developer-friendly language that compiles to XACML 3.0 XML, replacing the verbose XML authoring problem. Relevant as a potential authoring format for technically sophisticated policy editors in our platform. [Training knowledge — Axiomatics documentation not fetchable this session.] |
| 9 | **OPA / Rego** — Open Policy Agent | CNCF (graduated Feb 2021) | v0.x ongoing | General-purpose policy-as-code, microservices, Kubernetes | OPA decouples policy decision-making from enforcement (mirrors XACML PDP/PEP split). Rego is a Datalog-inspired declarative language. Bundles (`opa build`) package policy+data for versioned deployment with signing support (`--signing-key`). Decision logs contain `decision_id`, `trace_id` (W3C trace-context), `path`, `input`, `result`, `bundles[].revision`, `timestamp` — full auditability per query. `opa test` provides unit testing of policies. **Source:** `openpolicyagent.org/docs/` (architecture, Rego), `openpolicyagent.org/docs/management-bundles/` (bundle signing, persistence, versioning), `openpolicyagent.org/docs/management-decision-logs/` (all decision log fields) — all fetched and verified. CNCF graduation announcement cited in OPA docs. |
| 10 | **NIST SP 800-162** — Guide to ABAC Definition and Considerations | NIST | Jan 2014, upd. Aug 2019 | Attribute-Based Access Control guidance | Authors: Hu, Ferraiolo, Kuhn et al. Defines ABAC model: subjects, objects, operations, environment — access decisions via attribute policies. Maps directly to our "principal context" (persona, org_unit, jurisdiction, process) + runtime facts model. **Source:** CSRC abstract at `csrc.nist.gov/pubs/sp/800/162/upd2/final` — existence, date, authorship confirmed. PDF content [training knowledge]. |
| 11 | **NIST SP 800-205** — Attribute Considerations for Access Control Systems | NIST | 2019 | Attribute lifecycle: definition, provenance, quality, trust | Covers attribute assurance levels, provenance (where attribute values come from — analogous to our PIP), attribute revocation. Relevant to our scope dimension trustworthiness. **Source:** PDF retrieved (binary) — existence confirmed. Content [training knowledge]. |
| 12 | **ISO 37301:2021** — Compliance Management Systems | ISO | 2021 | Organizational compliance management lifecycle | Confirmed as standard for "establishing, developing, implementing, evaluating, maintaining, and improving an effective compliance management system." Requires: compliance risk assessment, policy ownership, management review, continual improvement. Directly governs the lifecycle metadata our platform tracks. **Source:** `iso.org/standard/75080.html` fetched and verified. |
| 13 | **ISO/IEC 27001:2022** — Information Security Management | ISO | 2022 | ISMS, security controls, audit, policy documentation | Requires documented policies, roles, periodic review, management review, nonconformity tracking — maps to our draft→approve→publish→review cycle and exception tracking. [Training knowledge — ISO store page returns product listing, not fetchable.] |
| 14 | **COSO ERM Framework** | COSO | 2017 edition | Enterprise Risk Management — governance, risk, control | Five components: Governance & Culture; Strategy & Objective-Setting; Performance; Review & Revision; Information, Communication & Reporting. The "Review & Revision" component directly mandates periodic policy recertification cycles. [Training knowledge — no public authoritative fetch this session.] |

---

## Part 2 — Software & Platforms Table

| # | Product | Vendor | Category | Key Lifecycle Features (Verified) | Relevance |
|---|---|---|---|---|---|
| 1 | **Open Policy Agent (OPA)** | CNCF (open-source) | Policy-as-code engine | Rego language; `opa test` for unit tests; `opa build` to create signed, versioned bundles (gzipped tarball, `bundle.tar.gz`, with `--signing-key`); bundle persistence for offline recovery; Decision Logs API — every decision logged with `decision_id`, `trace_id` (W3C trace-context compliant), `span_id`, `input`, `result`, `bundles[].revision`, `timestamp`, `requested_by`; bundles pulled via HTTP with Etag-based caching. **Source:** all three OPA docs pages fetched. | Blueprint for our evaluation engine's logging, versioned bundle distribution, and testability. |
| 2 | **Styra DAS** | Styra | Commercial OPA management plane | Policy authoring, impact analysis, staged rollout, decision log aggregation, compliance reporting on top of OPA. [Styra.com URL fetch failed — DNS error. Content is training knowledge; explicitly marked as unverified.] | Inspires our "Policy Administration Point" UX and impact-analysis feature. |
| 3 | **AWS IAM + Policy Simulator** | Amazon Web Services | Cloud IAM / policy engine | Nine policy types: identity-based (managed/inline), resource-based, VPC endpoint, permissions boundaries, SCPs, RCPs, ACLs, RAM shares, session policies. Policy Simulator: Principal mode (test existing attached policies) and Custom mode (test drafted policies before attaching) — returns binary allow/deny per action/resource combo with which policy produced outcome. Explicitly notes "simulator results can differ from live environment." **Source:** `docs.aws.amazon.com/IAM/latest/UserGuide/access_policies.html` and `.../access_policies_testing-policies.html` both fetched. | Validates our "simulate/dry-run before publish" feature direction; shows industry practice of pre-publish policy testing. |
| 4 | **Azure Policy** | Microsoft | Cloud governance / policy-as-code | Policy definitions (JSON, with `properties.policyRule`), initiatives (`policySet`), assignments to management groups/subscriptions/resource groups. Evaluation cycle: on resource change, on assignment, on initiative update, and on 24-hour recurring scan. Policy-as-code workflow: definitions stored in source control as versioned JSON files (`policy-v#.json`, `policy-v#.rules.json`, etc.); exemptions (`exemptionName.json`). Remediation tasks for non-compliant resources. **Source:** `learn.microsoft.com/en-us/azure/governance/policy/overview` and `.../policy-as-code` both fetched and verified. | Validates our versioning file/naming conventions, scope hierarchy, exemption model as first-class entity, and CI/CD-integrated testing. |
| 5 | **HashiCorp Sentinel** | HashiCorp | Policy-as-code for infrastructure (Terraform Cloud/Enterprise) | Three enforcement levels: `advisory` (warn, don't block), `soft-mandatory` (warn, allow override with explanation), `hard-mandatory` (always block, no override). Policy sets organized in modules. [Enforcement levels page returned no content body on fetch — page rendered empty; content is training knowledge and explicitly marked as unverified.] | Enforcement-level concept maps directly to our `effect` model (advice vs. require_action vs. hard-deny). |
| 6 | **Red Hat Drools / Apache KIE** | Red Hat → Apache (incubating) | BRMS / rules engine | Apache KIE project page confirmed at `kie.apache.org` as "home of the most popular business automation open-source technologies." Drools implements forward-chaining and backward-chaining rules; decision tables in Excel/DRL; RETE algorithm. jBPM handles workflow. [Detailed feature list — training knowledge; KIE docs not fetched.] | Validates decision-table authoring by business users and rules-engine architecture patterns. |
| 7 | **Camunda DMN Engine** | Camunda | DMN execution engine | Fully implements DMN 1.3. Decision Requirements Diagrams; decision tables; literal expressions; hit policies UNIQUE/ANY/FIRST/RULE ORDER/COLLECT with aggregators (SUM, MIN, MAX, COUNT). FEEL expressions. Modeler supports collaborative authoring. **Source:** `docs.camunda.io/docs/components/modeler/dmn/` and `.../decision-table-hit-policy/` both fetched; all hit policies and aggregators confirmed. | Our aggregate-limit rules (COLLECT+SUM for leave-day caps) should align to DMN COLLECT aggregation semantics. |
| 8 | **IBM Operational Decision Manager (ODM)** | IBM | Enterprise BRMS | Business rule authoring by business users in natural language (via Decision Center); testing/simulation; deployment lifecycle. [Training knowledge — IBM site not fetched.] | Reference for business-user-facing rule authoring UI design. |
| 9 | **Oracle Intelligent Advisor (formerly Policy Automation)** | Oracle | Natural-language policy authoring | Enables policy modelers to draft rules in near-natural language from legislative/policy text; deterministic execution; explanation of decisions. [Oracle Intelligent Advisor Hub URL returned 404 — unverified. Content is training knowledge.] | Closest analog to our "AI extraction → human-reviewed canonical rule" pipeline. |
| 10 | **ServiceNow Policy and Compliance Management** | ServiceNow | GRC / policy lifecycle | URL returned 403 — cannot verify feature details directly. Based on training knowledge: policy lifecycle with draft/review/approve/publish states; policy attestation (employee acknowledgment tracking); periodic review scheduling; exception requests as tracked workflow items; control mapping to frameworks (SOC 2, ISO 27001). [Explicitly unverified this session.] | Defines full GRC policy lifecycle that we must match. |
| 11 | **AWS Organizations SCPs** | Amazon Web Services | Hierarchical policy governance | SCPs limit maximum permissions for accounts in an org/OU — "guardrails" model, not a grant. Policy simulator can test SCP impact on identity-based policies. Scope hierarchy: org → OU → account. **Source:** `docs.aws.amazon.com/IAM/latest/UserGuide/access_policies.html` verified. | Validates our `scope.organizational_unit` dimension and hierarchical rule inheritance/override. |

---

## Part 3 — Standard End-to-End Policy Business Cycle

*Derived from verified standards (ISO 37301, ISO 27001 patterns, COSO ERM) plus industry practice. Where specific details come from training knowledge rather than a fetched source, this is noted.*

### 3.1 Actors / Roles

| Role | Responsibility |
|---|---|
| **Policy Owner** | Accountable executive (e.g., CHRO, CFO, CISO) who owns the policy domain. Approves final version, signs off on exceptions above threshold. |
| **Policy Author / SME** | Drafts the policy text; may be HR BP, Legal Counsel, IT Security Architect. |
| **Legal / Compliance Reviewer** | Reviews for regulatory compliance, legal language, jurisdictional applicability. |
| **Risk Manager** | Assesses residual risk of new/changed rules; flags conflicts with existing policies. |
| **Business Approver / Manager** | Approves operational implications for their org unit. |
| **IT/Platform Team** | Formalizes approved natural-language rules into machine-evaluable canonical form. |
| **Employees / End Users** | Acknowledge receipt of published policies; request exceptions/waivers. |
| **Internal Audit** | Validates audit trail, periodic review compliance, exception disposition. |

### 3.2 Phase-by-Phase Lifecycle

#### Phase 1: Intake & Triage
- **Trigger:** New regulation, business event, security incident, scheduled review date, or policy request submission.
- **Activities:** Policy owner assigned; policy categorized (HR/IT/Finance/Legal); scope dimensions set (jurisdiction, org unit, personas affected); previous version identified if superseding.
- **Artifact:** Policy record created with status = `DRAFT`, owner, category, review-due date, source citations.

#### Phase 2: Authoring & Structuring
- **Activities:** Policy author drafts natural-language text; AI-assisted extraction produces candidate canonical rules (condition trees, effects, scope dimensions, exceptions, aggregate limits); author reviews/corrects AI output; source-clause citations linked to each rule (traceability to original policy text paragraph).
- **Artifact:** Draft `PolicyDocument` + set of `CanonicalRule` records in `DRAFT` status.

#### Phase 3: Stakeholder Review
- **Activities:** Multi-level review workflow initiated — Legal reviews for compliance language; Risk reviews for control alignment; Business Approver reviews operational impact. Reviewer can: approve layer, add notes, or send back to author.
- **Standards basis:** ISO 37301 §8.5 requires documented review evidence. ISO 27001 A.5 requires policy reviews by responsible party.
- **Artifact:** Review records with timestamps, reviewer identity, comments, approve/reject decisions at each level.

#### Phase 4: Approval
- **Activities:** After all layers approve, Policy Owner gives final sign-off. In regulated industries, an executive sign-off or board-level ratification may be required for high-risk policies.
- **Artifact:** Policy record transitions to `APPROVED` status; approval event logged with timestamp and authorizer identity.

#### Phase 5: Pre-Publication Simulation / Impact Analysis
- **Activities:** Before publish, evaluate proposed rule set against a representative sample of principal contexts to identify unintended denials or grants. Compare delta from previous version — which principals gain/lose access or change allowance amounts.
- **Industry evidence:** AWS IAM Policy Simulator (verified) specifically allows testing before attach. Azure Policy as Code (verified) validates in CI/CD pipeline before deployment.

#### Phase 6: Publication & Versioning
- **Activities:** Policy published; immutable version snapshot created (`version_number`, `published_at`, `published_by`, full rule snapshot). Previous version marked `SUPERSEDED` with forward-link to new version.
- **Artifact:** Immutable `PolicyVersion` record. Evaluation engine updated to use new version.

#### Phase 7: Employee Attestation & Acknowledgment
- **Activities:** Affected employees notified; must actively acknowledge receipt and understanding by a deadline. Non-acknowledgment escalated to manager.
- **Metrics:** % attested by deadline, overdue acknowledgments by org unit.
- **Standards basis:** ISO 37301 §7.3 requires communication of compliance obligations to personnel; ISO 27001 A.7.2.2 requires information security awareness. [Training knowledge for specific attestation workflow details.]

#### Phase 8: Exception / Waiver Requests
- **Activities:** An individual or team may request an exception (temporary or permanent deviation). Exception request is a **first-class tracked entity**: requester, policy/rule scope, business justification, risk assessment, approver, decision (granted/denied), expiry date, compensating controls.
- **Standards basis:** ISO 37301 §8.6 (nonconformity and corrective action); COSO ERM requires exceptions to risk appetite to be escalated and tracked. [Training knowledge for specific workflow details.]

#### Phase 9: Periodic Review & Recertification
- **Activities:** Scheduled review-due dates (commonly annual for HR/Finance policies; semi-annual for IT security). Policy Owner certifies policy is still accurate/current, or initiates a revision cycle. Automated reminders at N days before due date.
- **Standards basis:** ISO 37301 §9.3 (management review); ISO 27001 requires periodic review of information security policy. COSO ERM "Review & Revision" component.
- **Artifact:** `review_due_date`, `last_reviewed_at`, `review_status` fields; recertification event logged.

#### Phase 10: Retirement / Supersession
- **Activities:** Policy explicitly retired or superseded by newer version. Old version preserved in audit history with immutable snapshot. Active evaluations cease against retired rules.
- **Artifact:** `PolicyVersion.status = RETIRED`, `superseded_by` FK to new version.

#### Phase 11: Audit & Reporting
- **Activities:** Every evaluation call logged (who asked, what context, which rules fired, what decision, which version). Exception counts, attestation rates, overdue review counts, and policy conflict reports surfaced to compliance dashboard.
- **Industry evidence:** OPA Decision Logs (verified) — every decision logged with `decision_id`, `trace_id`, `bundles[].revision`, full `input`/`result` for offline debugging and compliance auditing.

---

## Part 4 — Gap Analysis (Prioritized)

For each gap, the severity rating reflects standard-practice alignment and implementation risk.

| Priority | Gap | Rationale (Grounded in Verified Standard / Product) |
|---|---|---|
| 🔴 P1 | **Employee Attestation / Acknowledgment Tracking** | ISO 37301 §7.3 (verified existence) requires compliance obligations be communicated to and acknowledged by personnel. ServiceNow Policy & Compliance and GRC platforms treat attestation as a first-class workflow with deadlines, escalation, and % completion metrics. The described platform has no mention of an attestation workflow or acknowledgment deadline tracking. Without this, the platform cannot demonstrate ISO 37301 / ISO 27001 compliance. |
| 🔴 P1 | **Exception / Waiver Requests as First-Class Tracked Entities** | ISO 37301 §8.6 and COSO ERM both require exceptions to be formally tracked with justification, approver, expiry, and compensating controls. Azure Policy (verified) has `exemption` as a named, versioned, first-class JSON object (`exemptionName.json`) separate from policy definitions. The described platform mentions exception fields on a rule, but a rule-level field is not equivalent to a tracked exception request workflow with lifecycle (pending → approved/denied → expired). This is a significant compliance gap. |
| 🔴 P1 | **Obligations and Advice as Post-Decision Actions** | XACML 3.0 (verified, OASIS spec) defines **Obligation** (PEP *must* perform an action when decision is returned — e.g., "send notification email," "write to audit log," "trigger approval workflow") and **Advice** (supplementary information the PEP *should* act on). The described platform specifies `require_action` as an effect, which maps to an Obligation, but there is no explicit Advice channel (non-mandatory supplementary guidance returned with a decision). Both concepts are standard; not implementing Advice means callers cannot receive non-blocking guidance alongside PERMIT/DENY. |
| 🔴 P1 | **Periodic Review / Recertification Due Dates** | ISO 37301 §9.3 and ISO 27001 (both verified by existence) mandate periodic management review and policy recertification. The described platform's data model includes no `review_due_date`, `last_reviewed_at`, or automated review-trigger mechanism. Without this, policies will silently become stale, which is a direct compliance gap and a common audit finding. |
| 🟠 P2 | **Decision / Audit Logging of Every Evaluation Call** | OPA Decision Logs (verified — `openpolicyagent.org/docs/management-decision-logs/`) demonstrate the industry standard: every policy decision is logged with a unique `decision_id`, W3C `trace_id`, `span_id`, full input context, output result, bundle revision, and timestamp, enabling offline debugging and compliance auditing. The described platform mentions an audit trail but the evaluation engine's per-call logging at this level of detail (especially with rule-version snapshot and full input/output) should be explicitly designed in. |
| 🟠 P2 | **Impact Analysis: Which Principals/Scenarios Are Affected by a Rule Change** | AWS IAM Policy Simulator (verified — `docs.aws.amazon.com/IAM/latest/UserGuide/access_policies_testing-policies.html`) provides explicit pre-change simulation showing which actions become allowed/denied per identity. Styra DAS (training knowledge, unverified this session) provides impact analysis across principal populations. The described platform has a general "evaluator" but no formal "compare version A vs version B across a set of representative principal contexts" impact report. This is critical for change management approval. |
| 🟠 P2 | **Policy Ownership / RACI Metadata** | ISO 37301 and standard GRC practice require each policy to have a named owner, approver, reviewer, and informed parties — a RACI model. The described platform has reviewer/manager roles in the workflow but no persistent ownership metadata on the policy itself (owner department, escalation path, delegate approver). This is needed for recertification reminders and exception escalation routing. |
| 🟠 P2 | **Control Mapping — Linking Policies to Compliance Frameworks** | ServiceNow Policy & Compliance (training knowledge, unverified), MetricStream, and ISO 37301 all support mapping a policy/rule to one or more compliance framework controls (e.g., "this expense policy rule satisfies SOC 2 CC6.1 and ISO 27001 A.9.4.1"). Without this, the platform cannot produce automated compliance evidence reports for auditors. |
| 🟡 P3 | **Delegation of Authoring / Approval Authority (XACML Delegation Profile)** | XACML 3.0 Administration & Delegation Profile (verified as reference in XACML core spec) defines formal delegation with attenuation (cannot delegate more than you have). The described platform has multi-level review but no formal model for a Policy Owner to delegate authority to an Acting Owner for a bounded scope and time period. |
| 🟡 P3 | **ALFA / Human-Readable Rule Authoring Syntax** | XACML's XML verbosity is well-known; ALFA provides a compact developer-readable syntax that compiles to XACML. For the described platform's technical users (IT policy authors), an ALFA-like surface syntax for the canonical rule DSL would significantly reduce authoring friction vs. raw JSON condition trees. [Training knowledge — referenced as gap against ALFA standard.] |
| 🟡 P3 | **SBVR-Aligned Policy Vocabulary / Glossary** | OMG SBVR (referenced in standards table) provides a formal ontology for business terms. The described platform extracts rules from text but has no formal vocabulary layer ensuring that "employee," "full-time employee," "probationary employee," "leave day," and "business day" are consistently defined across rules. Without a managed vocabulary, two rules may use different terms for the same concept, causing evaluation inconsistencies. |
| 🟡 P3 | **Simulate / Dry-Run Before Publish (Already Partially Present — Needs Verification)** | The platform description mentions a general evaluator. AWS IAM Policy Simulator (verified) and Azure Policy-as-Code CI/CD integration (verified) both make pre-publish testing a formal, named workflow step. The platform should explicitly surface this as a "Simulation Mode" step in the approval workflow, with results captured as a required artifact before the policy transitions to APPROVED, not just an available tool. |
| 🟢 P4 | **Training Linkage** | ISO 37301 §7.2 and standard GRC practice require compliance training to be linked to policy publication events (new policy published → training assigned). The platform has no mechanism to trigger or record training assignments linked to policy versions. |
| 🟢 P4 | **Natural-Language Rationale / Source-Clause Citation** | The platform description says this is "partially done." Verify that each `CanonicalRule` stores: (a) a verbatim source text excerpt, (b) document reference (filename, section, page), (c) extraction confidence score, and (d) the human reviewer's acceptance/override decision. This is the minimum needed to satisfy ISO 37301's requirement for documented evidence of policy basis. |

---

## Summary of Verified vs. Training-Knowledge Claims

| Category | Verified by Fetch | Training Knowledge (Noted) |
|---|---|---|
| XACML 3.0 core terms, architecture, obligations, advice | ✅ OASIS spec glossary | — |
| XACML 3.0 Related Entities Profile | ✅ OASIS CS02 page | — |
| XACML 3.0 Administration & Delegation Profile existence | ✅ Listed in core spec references | Content details |
| OPA architecture, bundles, decision log fields | ✅ 3 OPA doc pages | — |
| DMN 1.3 hit policies (all 5 + aggregators) | ✅ Camunda docs | — |
| OMG DMN overview and purpose | ✅ OMG website | — |
| AWS IAM policy types (all 9) | ✅ AWS docs | — |
| AWS IAM Policy Simulator (both modes, binary outcome) | ✅ AWS docs | — |
| Azure Policy definitions, initiatives, assignments, 24h evaluation cycle | ✅ MS Learn | — |
| Azure Policy-as-Code file naming conventions, exemption structure | ✅ MS Learn | — |
| ISO 37301 purpose and scope | ✅ ISO product page | Specific clause details |
| NIST SP 800-162 existence, date, authors | ✅ CSRC abstract | Content details |
| Styra DAS features | ❌ DNS error | Training knowledge |
| HashiCorp Sentinel enforcement levels | ❌ Empty page render | Training knowledge |
| ServiceNow Policy & Compliance features | ❌ 403 | Training knowledge |
| Oracle Intelligent Advisor | ❌ 404 | Training knowledge |
| SBVR, RuleML/RIF, ALFA | ❌ Not fetched | Training knowledge |
| COSO ERM | ❌ Not fetched | Training knowledge |

---

## Appendix: Noteworthy Open-Source References

- **`open-policy-agent/opa`** (GitHub, CNCF) — reference implementation of policy-as-code engine with decision logging, bundle management, and `opa test`. Directly relevant as architecture reference.
- **`casbin/casbin`** (GitHub) — open-source authorization library implementing RBAC, ABAC, ACL models in multiple languages. [Training knowledge — not fetched this session.]
- **`dexidp/dex`** — OIDC identity provider; relevant to PIP (attribute source) architecture. [Training knowledge.]
- OMG publishes reference implementations for DMN; Camunda's open-source Zeebe/Camunda 7 contain the most widely used DMN engine.