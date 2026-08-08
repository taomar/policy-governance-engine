# Extraction quality and fresh-intake session — handoff

**Recorded:** 2026-08-08

**Status:** authoritative successor handoff

**Supersedes for current state:** `backend-data-integrity-handoff.md`

This handoff preserves the session's current code, data, architectural decisions,
validation evidence, user constraints, and exact resumption steps. The chronological
decision record is `AGENT_PROGRESS.md`, especially Milestones 43–46.

---

## 1. User objective and non-negotiable constraints

The platform must remain domain-neutral: it must work for statutes, internal company
policy, HR mandates, IT support rules, procurement standards, and similarly structured
documents. Do not solve Saudi-law examples with legal-only architecture.

Standing user instructions:

1. Run locally.
2. PostgreSQL uses the non-standard host port **5433**.
3. Frontend must be served on **5789**. This supersedes the earlier 5178
   instruction; port 5178 is now intentionally free.
4. Use the local `.env` for runtime connections, but never commit or reproduce its
   secrets. `.env` is intentionally ignored by git.
5. Approved dependency feeds:
   - PyPI: `packagefeedproxy.microsoft.io/pypi/simple`
   - NuGet: `packagefeedproxy.microsoft.io/nuget/v3/index.json`
6. Keep only a clean, fresh intake project for validation. The database currently
   contains exactly one policy set: `saudi-labor-law`.
7. Extract **only the first 50 clauses** for quality evaluation until the user
   explicitly authorizes a larger run.
8. Do not approve, publish, or bulk-promote candidate rules without explicit user
   confirmation.
9. Do not commit or push without explicit user instruction.
10. Generalize defects to the correct architectural boundary; do not patch one phrase
    while equivalent paths remain wrong.

---

## 2. Current repository and runtime state

### Git

- Branch: `master`
- Extraction-quality implementation commit: `91cf192`
- Fresh first-50 extraction record commit: `2c3e051`
- The implementation and Milestone 47 record are committed.
- Do not reset, stash, discard, or overwrite these commits.

Files included in the extraction-quality implementation commit:

```text
AGENT_PROGRESS.md
apps/web/src/App.css
apps/web/src/components/PolicyInspector.tsx
apps/web/src/components/ReviewQueue.tsx
apps/web/src/components/RuleCard.tsx
src/policy_platform/api/routers/ai.py
src/policy_platform/infrastructure/ai_extraction.py
src/policy_platform/infrastructure/ai_quality.py
src/policy_platform/infrastructure/formulation_mapping.py
src/policy_platform/infrastructure/passage_extractor.py
src/policy_platform/infrastructure/prompts/policy_formulator_v1.md
tests/unit/test_ai_quality.py
tests/unit/test_policy_formulator.py
docs/handoff/backend-data-integrity-handoff.md
docs/handoff/extraction-quality-handoff-2026-08-08.md
```

The large `AGENT_PROGRESS.md` diff is intentional: it records Milestones 43–46 in
architecture/root-cause/impact/validation form.

### Processes and ports

State measured after the Milestone 47 refresh:

- PostgreSQL container `policy-postgres`: healthy, host port **5433**
- Frontend: responding on `http://127.0.0.1:5789`, title `Policy Platform`
- API on `http://127.0.0.1:8010`: healthy
- Port **5178**: free

Start the API from repo root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn policy_platform.api.app:app --host 127.0.0.1 --port 8010 --app-dir src
```

Start the frontend explicitly on the user-required port:

```powershell
cd apps\web
npm run dev -- --host 127.0.0.1 --port 5789
```

The ignored local `.env` now sets `WEB_DEV_SERVER_PORT=5789` so the backend CORS
allowlist includes the browser origin. `apps/web/vite.config.ts` does not read that
variable, so still start Vite with the explicit `--port 5789` argument. If the
frontend port changes again, update the local setting and restart the API; middleware
origins are constructed at process startup.

The backend runs without `--reload`. Prompt and Python changes require a process
restart. `load_formulator_prompt()` is additionally cached with
`@lru_cache(maxsize=1)`.

---

## 3. Current database state

Only one project remains:

| Field | Value |
|---|---|
| policy set key | `saudi-labor-law` |
| policy set id | `58b28fd6-898a-476c-83c5-3afc50dcbeb4` |
| document version id | `0fbf7f9c-a386-41ab-87f4-8b0ac64f8c1a` |
| final clean extraction run | `61e7b4e1-7748-4ffa-a586-efe4b6d663fb` |
| extraction scope | first 50 clauses |
| candidate rules | 44 |
| review status | all `candidate` |
| approved/published | none performed |
| document versions | 1 |

Effect distribution in the 44 candidates:

| Effect | Count |
|---|---:|
| `informational` | 29 |
| `allow` | 8 |
| `require_action` | 4 |
| `deny` | 3 |

Useful query:

```powershell
docker exec policy-postgres psql -U policy_admin -d policy_platform -c "SELECT payload_json#>>'{effect,type}', COUNT(*) FROM candidate_rules WHERE policy_set_id='58b28fd6-898a-476c-83c5-3afc50dcbeb4' GROUP BY 1 ORDER BY 1;"
```

`candidate_rules` stores rule content in `payload_json`; it does not have standalone
`description` or `effect` columns.

---

## 4. Architecture model and durable learnings

### Two-stage extraction

```text
source document
  -> Stage 1 passage extraction
  -> Stage 2 policy formulation
  -> deterministic formulation mapping
  -> candidate_rules.payload_json
  -> human review
  -> deterministic evaluator (only when executable)
```

Stage 1 must preserve source wording. Stage 2 may resolve anaphora in structured fields
(`subject`, predicates, etc.) while leaving `source_text` verbatim.

### Content ambiguity and technical executability are different

`ambiguity_status` answers whether the source meaning needs human interpretation.
`machine_executable` answers whether trusted fact/output/temporal configuration exists.
A clear rule can be non-executable without being ambiguous. Milestone 44 separated
these concerns; do not recombine them.

### Effect semantics are executable behavior, not display metadata

The evaluator reads `effect.type` and `effect.action` together. A satisfied `deny`
rule places its action directly into `denied_actions`; the winning action becomes the
decision `outcome`. Polarity mistakes therefore invert real decisions.

`EffectType.INFORMATIONAL` is the neutral effect for definitions/classifications.
It already exists in `contracts/policy.py`; `_RULE_TYPE_MAP` routes
`DEFINITION`/`CLASSIFICATION` to it; `_apply_combining_algorithm` excludes it from the
allow/deny axis. The old handoff and stale todo saying a neutral effect was still
needed are obsolete.

### Evidence must be rule-scoped

One Stage-2 batch may contain multiple articles/topics. Applying a flat batch evidence
list to every output rule caused false citations. `formulation_to_candidate_rules()`
now matches each `CanonicalPolicy.source_text` back to Stage-1 passages using normalized
bidirectional substring containment, with coarse batch evidence only as fallback.

### Definitions/glossary are separate review content

The Review Queue has a segmented `Policies & Rules` / `Definitions & Glossary` control.
Definitions remain reviewable and traceable but must not be treated as authorizations.

### Source context must accompany raw extraction JSON

The raw `AI EXTRACTION RECORD` deliberately preserves phrases such as “this Law” or
“this policy.” `PolicyInspector.tsx` and `RuleCard.tsx` now render an
`Extracted from: {document} ({version}) · {section}, p.{page} · clause {ref}` banner
above the raw formulation JSON so the referenced instrument is visible without
rewriting source text.

### Mapping is write-time, not read-time

`_effect_action()`, `_RULE_TYPE_MAP`, ambiguity mapping, and evidence mapping run during
extraction. Their values are baked into `candidate_rules.payload_json`. Restarting the
backend is not enough to update existing rows; verification of mapper changes requires
re-extraction or a deliberate backfill.

---

## 5. Defects fixed and verified in this session

### A. Non-policy intake noise

Lifecycle/document-meta text (“this policy shall be published,” entry-into-force
boilerplate, headings, narrative) was being emitted as enforceable rules because both
prompts listed `non_normative` but did not explain it. Stage 1 and Stage 2 now contain
domain-neutral guidance and counterexamples. Real scope/exemption clauses that mention
“this Law” or “this policy” must not be discarded.

### B. Definitions carrying false authorization effects

Definitions/classifications formerly mapped to `ALLOW`, which inverted negatively
phrased definitions. They now map to `INFORMATIONAL`, and informational results do not
compete in evaluator allow/deny resolution. A deterministic quality check remains as a
legacy-row/regression guard.

### C. Ambiguity over-reporting

All rules were previously marked as requiring human judgment because content ambiguity
was conflated with non-executability. `_ambiguity_for()` now keeps those concerns
separate. Clear thresholds such as “shall not exceed 90 days” are not ambiguous merely
because trusted fact/temporal configuration is missing.

### D. Degenerate definition predicates and dangling pronouns

Prompt guidance now tells Stage 2 to synthesize meaningful definition copulas instead
of punctuation-only predicates, and to resolve structured pronoun subjects from nearby
context while preserving source text verbatim. A deterministic
`degenerate_predicate` quality guard remains.

### E. Per-rule evidence citation leakage

Rules from a multi-topic batch no longer inherit every batch citation. Live validation
showed the “null and void” rules cite Article 8 only, not Articles 6/7/8 collectively.

### F. Exemption polarity inversion

Six exemption rules were classified as `ineligibility -> deny`, causing evaluator
semantics equivalent to “denied: be exempted.” Root cause was an incorrect worked
example in the Stage-2 prompt. Sections 14/15 now use a generalized GAIN/LOSS model,
and Section 15.1 defines:

- grant-shaped negation: exempt, excused, immune, not subject to -> gain ->
  `eligibility` / `allow`
- loss-shaped negation: not eligible for, excluded from receiving, disqualified from
  -> loss -> `ineligibility` / `deny`

`_eligibility_polarity_findings()` is the permanent deterministic guard.

Live fresh-extraction proof: all exemption-derived rows are `eligibility + allow`;
zero are `deny`.

### G. Silent `effect.action` truncation

`_effect_action()` silently sliced evaluator-facing actions at 200 characters with no
ellipsis. The cap was removed entirely after a caller audit confirmed no downstream
consumer requires a bounded action. The final dataset contains a complete 1,383-character
action, proving the fix on real data.

---

## 6. Quality-report triage

The final fresh quality report contained 17 findings.

### Fixed pipeline defects

- exemption polarity inversion
- `effect.action` data-integrity truncation

Neither category appears in the fresh report after re-extraction.

### Deterministic checks working as designed

- In the prior Milestone 46 47-rule report, `ambiguity` classified 45 rules as
  `non_blocking` and only 2 as requiring real human judgment. Milestone 47 replaced
  those rows with 44 fresh candidates; rerun the quality endpoint before quoting
  current ambiguity counts.
- `not_machine_executable`: expected until trusted configuration supplies source-term
  fact/output/temporal mappings; this is not extraction failure

### Genuine human-review content, not code defects

- redundancy (two findings)
- unclear wording
- missing context
- incomplete rule
- calculation risk
- exception loss
- applicability conflict
- coverage gap
- unclear applicability
- control design
- missing exception criteria
- rights-waiver risk

Several arise because this is intentionally only the first 50 of 743 clauses. Do not
“fix” source-policy ambiguity or missing later-document context by inventing policy.
Use the Review Queue.

### Open architectural decisions — deliberately not implemented

#### Applicability classification

Six binding “this Law/policy applies to X” clauses become
`definition + informational` because the closed `CanonicalRuleType` vocabulary has no
`applicability`/`scope` member. They therefore do not make an evaluator decision.

Options:

1. Map applicability grants to existing `eligibility + allow` (smaller, reuses
   GAIN/LOSS semantics).
2. Add a dedicated `APPLICABILITY` canonical type (larger contract/prompt/mapping/DMN
   change).

Do not choose without confirming desired cross-domain behavior.

#### Scope population

Every mapped rule currently receives `PolicyScope()` with empty jurisdiction,
organizational-unit, persona, and process dimensions. Empty dimensions match
permissively in the evaluator. This is a completeness/under-restriction risk, not a
polarity inversion.

Options:

1. Policy-set-level default scope inherited by rules (lower risk, domain-neutral).
2. Per-rule LLM-extracted scope (new canonical fields, prompt guidance, mapper changes,
   and uncertain extraction reliability).

---

## 7. Validation standing

Latest backend validation:

```text
328 passed, 11 skipped
```

Targeted suites:

- `tests/unit/test_ai_quality.py`: 24 passed
- `tests/unit/test_policy_formulator.py`: 69 passed

Milestone 45 frontend validation completed before handoff:

- TypeScript check clean
- `npm run lint` clean
- `npm run build` clean
- live browser verification completed for evidence scoping, source banner, and
  Policies/Definitions segmented filtering

The final real-data validation loop was:

1. restart backend (prompt and mapper changes are process-loaded/cached)
2. delete stale candidate rows for the test policy set
3. re-run the same 50-clause extraction
4. inspect raw database payloads
5. re-pull `/api/ai/policy-sets/saudi-labor-law/candidates/quality`
6. confirm exemption polarity and truncation findings are absent

Milestone 47 then reran the latest committed pipeline over source clauses 0–49:

- extraction run `61e7b4e1-7748-4ffa-a586-efe4b6d663fb`
- 47 prior unreviewed candidates superseded
- 44 fresh candidates created, 0 batches skipped
- all 44 remain unreviewed and unpublished
- all 178 evidence links resolve to clause sequences 0–49
- exemption-derived output: 6 `allow`, 0 `deny`
- longest action: 1,383 characters; no action is exactly 200 characters

---

## 8. Structured pending work

The session todo database was reconciled at handoff. The stale
`effecttype-neutral-member` todo was marked done because
`EffectType.INFORMATIONAL` already resolves it.

Pending:

1. `applicability-rule-classification` — product/schema decision described above
2. `policy-scope-population` — product/schema decision described above
3. `impact-analysis-pre-publish` — add candidate impact analysis before approval,
   reusing the post-publish ADR-0010 engine
4. `control-mapping-compliance` — map rules/policies to external framework controls
5. `mhrsd-extraction-review` — human review of source-content conflicts; never bulk
   approve known defects

---

## 9. Exact next-session sequence

1. Read this file and Milestones 43–46 in `AGENT_PROGRESS.md`.
2. Run `git status --short`; preserve every existing modification.
3. Verify the API on 8010 and frontend on 5789; both were healthy at final handoff,
   but verify it rather than assuming.
4. Do **not** re-extract or delete data merely to “check” current state; the clean
   44-rule dataset is already validated.
5. Present the two open architecture decisions (applicability classification and scope
   population) to the user before implementing either.
6. Continue only the first-50-clause workflow until the user explicitly authorizes
   broader extraction.
7. Never approve/publish candidate rules or commit/push code without explicit user
   instruction.

---

## 10. Environment and safety notes

- Python command: `.\.venv\Scripts\python.exe`
- PostgreSQL:
  `docker exec policy-postgres psql -U policy_admin -d policy_platform -c "..."`
- API health endpoint: `/health`
- Candidate quality endpoint:
  `/api/ai/policy-sets/saudi-labor-law/candidates/quality`
- Extraction endpoint:
  `/api/ai/policy-sets/saudi-labor-law/documents/0fbf7f9c-a386-41ab-87f4-8b0ac64f8c1a/extract`
  with `{"max_clauses": 50}`
- Long extraction requests exceed browser-evaluate tool timeouts; use PowerShell
  `Invoke-RestMethod` with a generous timeout.
- `.env` contains real local/Azure credentials. It is ignored; never quote it into
  handoffs, logs, commits, or responses.
- The repository may be shared with other sessions. Never use `git add -A`, destructive
  reset/checkout, or broad process termination.
