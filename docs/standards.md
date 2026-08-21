# Standards

PolicyVerbAItim implements three published standards. Each is named here with what it governs, where it is applied, and — where it matters most — what the platform deliberately does *not* claim from it.

Depth and the full survey of what was evaluated and rejected is in [Standards research](policy-standards-research.md). This page is the short, binding answer: **which standard governs which decision**.

## The three

| Standard | Body | Governs |
|---|---|---|
| **OASIS XACML 3.0** | OASIS | Decisions, effects, obligations, target matching, attribute naming |
| **OMG DMN 1.5 / FEEL** | OMG | Decision tables, condition expressions, hit policies |
| **OMG SBVR 1.5** (concepts) | OMG | The deontic vocabulary the canonical rule types express |

One rule governs all of them: **a standard is adopted or it is not.** Where a concept is borrowed without conformance, this page says so explicitly, because a half-claimed standard is worse than none — it invites a reader to assume guarantees the code does not provide.

## XACML 3.0 — the decision vocabulary

XACML is the platform's adopted authorization standard. It is used, not merely referenced:

| XACML concept | Where |
|---|---|
| Decision (`Permit` / `Deny` / `NotApplicable` / `Indeterminate`) | `contracts/evaluation.py`, `evaluator/engine.py` |
| Target matching on Subject / Resource / Action / Environment | `PolicyScope` — jurisdictions, organizational units, personas, processes |
| Obligation vs Advice (§7.18) | `EffectType.REQUIRE_ACTION` vs the `advice` field on a rule |
| Rule-combining algorithms | `evaluator/precedence.py` |
| Attribute naming | `apps/web/src/xacml.ts` |

### Obligation is not Advice

XACML §7.18 draws a line the platform must keep: a PEP **must** discharge an Obligation, and **may** ignore Advice. `REQUIRE_ACTION` is the first; `INFORMATIONAL` is the second. Collapsing them turns guidance into a duty, so they never share an encoding.

### Attribute naming

Short forms of the standard identifiers, used in the display of stated logic:

| Short form | XACML identifier |
|---|---|
| `subject.subject-id` | `urn:oasis:names:tc:xacml:1.0:subject:subject-id` |
| `action.action-id` | `urn:oasis:names:tc:xacml:1.0:action:action-id` |
| `resource.resource-id` | `urn:oasis:names:tc:xacml:1.0:resource:resource-id` |

`subject:subject-id` is used rather than the narrower `subject:role`. Both are standard, but asserting `role` requires knowing the subject *names a role* — "The ED/CEO" is a role, "A device" is not, and both arrive as the grammatical subject of a sentence. The generic identifier makes no claim the extraction cannot support.

A rule that only classifies constrains `resource.resource-id`, not a subject: calling "Security incidents" a subject would claim the document assigned conduct to a category.

### What XACML does not govern

The platform is not an XACML PDP and does not consume XACML XML policies. It implements the model — decisions, targets, obligations, combining — over its own canonical rule format.

## DMN 1.5 / FEEL — the executable projection

The formulator projects each canonical policy to a DMN-shaped decision, and `derive_condition()` compiles a table row into the condition AST the evaluator executes.

Every projection carries a status, and only one of them compiles:

| `dmn_mapping_status` | Meaning |
|---|---|
| `executable` | Every fact path, type and value came from source or trusted configuration. Compiles. |
| `enrichment_required` | Conditions found, but no fact model binds them. |
| `ambiguous` | The wording admits more than one reading. |
| `not_directly_mappable` | Stated as a responsibility, not a decision. |
| `not_applicable` | Carries no decision at all. |

**`executable` is the agent's assertion that nothing was invented.** Without it, `derive_condition()` returns nothing and the rule is `machine_executable=False`. It never guesses a fact path to fill the gap — see [Relationships and linking](relationships.md) for the same principle applied to links.

The JSON is a **DMN-compatible IR**, not a normative DMN document. It carries `representation: "DMN-compatible JSON IR"` precisely so no consumer mistakes it for one.

## SBVR 1.5 — deontic categories

`CanonicalRuleType` is the deontic vocabulary: `obligation`, `prohibition`, `permission`, `entitlement`, `eligibility`, `ineligibility`, `recommendation`, `classification`, `definition`, `conditional_outcome`, `calculation`, `ambiguous`, `non_normative`.

The distinction that matters is **deontic vs alethic**: an obligation says what *ought* to be, a classification says what *is true by definition*. Conflating them turns a definition into a duty, which is why `classification` and `definition` map to `INFORMATIONAL` rather than `ALLOW` — most visibly when the source is phrased negatively and a forced `ALLOW` would assert the literal inverse of the rule's own text.

Concepts are used; SBVR's structured English and MOF metamodel are not implemented.

## RFC 9457 — not adopted

API errors are FastAPI's default `{"detail": "..."}`, **not** `application/problem+json`. RFC 9457 is a natural fit and adopting it would be a small change, but until it is made the platform does not claim it.

## Deliberately not claimed

| Standard | Status |
|---|---|
| RFC 9457 (Problem Details) | Not implemented; errors are FastAPI's default shape |
| ISO/IEC 38507, ISO 31000 | Practices informed the governance model; no certification is claimed |
| Open Policy Agent / Rego | Decision-log *shape* is comparable; the engine is not OPA and Rego is not supported |
| W3C ODRL | Evaluated; not adopted |
| LegalRuleML | Evaluated; not adopted |

## Where these are enforced

Standards live in code, not only in prose:

| Claim | Enforced by |
|---|---|
| Effects map to the correct XACML decision | `apps/web/src/xacml.ts`, `_RULE_TYPE_MAP` |
| A definition never asserts ALLOW | `tests/unit/test_document_guidance.py`, `ai_quality._definition_effect_findings` |
| An empty condition never matches everything | `evaluator/engine.py::_is_vacuous`, `tests/unit/test_engine.py` |
| Only `executable` projections compile | `formulation_mapping.derive_condition` |
| Only confirmed relationships enter `related_rule_ids` | `infrastructure/extraction/ai_extraction.py`, `tests/unit/test_relationship_discovery.py` |
