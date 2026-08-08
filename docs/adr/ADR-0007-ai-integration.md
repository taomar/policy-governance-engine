# ADR-0007: Azure OpenAI + Azure AI Search integration (extraction, quality, rewrite, compare, ask)

## Status
Accepted and verified end-to-end against live Azure resources (this is not a
paper design — every feature below has been exercised against real API
responses, see the verification log at the bottom).

## Context
ADR-0004 deferred all AI/MAF integration because no Azure OpenAI resource,
API keys, or SDK packages were available in the local session at the time.
The user later supplied real credentials for a live Azure OpenAI resource
(`scopeaifoundry`) and a live Azure AI Search resource
(`myfoundryiqforscop`), plus two chat deployments (`gpt-5.6-sol` for
reasoning-heavy work, `gpt-5.4-mini` for latency-sensitive interactive chat)
and an embedding deployment (`text-embedding-3-large`, 3072 dims). This
unblocked the Phase 2–4 work that ADR-0004 had deferred, but the original
constraint from Section 33 ("do not fabricate Azure SDK APIs") still applied
— so every wire format below was verified against the live resource rather
than assumed from documentation.

## Decision

### 1. Thin `httpx` REST clients, not the `openai`/`azure-search-documents` SDKs
`infrastructure/ai/openai_client.py` and `infrastructure/search/search_client.py`
call the Azure OpenAI and Azure AI Search REST APIs directly over `httpx`
rather than depending on the official Python SDKs. This was a deliberate
choice, not an oversight:
- It keeps the dependency surface small (no SDK version pinning/compat
  churn) for a project whose core trust boundary (the deterministic
  evaluator) must never depend on AI availability.
- Every endpoint path/payload shape was hit live against the real resources
  during setup and confirmed working (200 OK) before being relied upon —
  satisfying the "don't fabricate SDK APIs" constraint by testing against
  reality instead of trusting either the SDK's abstraction or documentation
  from training data.
- `AzureOpenAIClient.enabled` / `AzureSearchClient.enabled` gate every call
  on the presence of configuration; when unset, `ai_status()` reports
  `enabled: false` and all AI endpoints return a clear 4xx rather than
  crashing — the platform is fully usable with AI switched off.

### 2. Two chat deployments, chosen per call site
- `gpt-5.6-sol` (`AZURE_OPENAI_DEPLOYMENT`) — a **reasoning model** — is used
  for extraction, rewrite suggestions, quality review, and compare
  summaries, where correctness matters more than latency. Reasoning models
  spend part of their token budget on a hidden reasoning pass before
  producing visible content, so calls to this deployment use a generous
  `max_tokens` (8000) and long timeouts (180s); a too-small budget can
  silently consume the whole budget on reasoning and return an empty
  `content` with `finish_reason="length"` (confirmed live, documented in
  `openai_client.py`).
- `gpt-5.4-mini` (`AZURE_OPENAI_FAST_DEPLOYMENT`) — used only for the
  interactive **Ask AI** chat drawer, where response latency matters more
  than maximum reasoning depth.

### 3. Extraction produces *candidates*, never auto-published rules
`ai_extraction.py` turns a source document version into `CandidateRule` rows
in `review_status="candidate"` — identical to the manual-drafting path
already in place. AI-extracted candidates are never auto-approved or
auto-published; they go through the exact same human review/approve/reject/
publish pipeline as manually-drafted candidates (`candidate_rules.py`).
This was a hard requirement carried over from the project's core trust
model (Section 35: "No LLM participates in the final runtime rule
calculation") — AI participates in *drafting*, never in *deciding*.

### 4. Quality evaluation needed a pre-publish path, not just a published-version path
The original `evaluate_policy_set_quality()` only evaluated an already
*published* active version. This left a real gap: a policy administrator
who has just extracted 400+ candidates from a document has no way to ask
"are these any good?" before committing to publish. `ai_quality.py` was
refactored to extract a shared `_run_ai_review()` helper, and a new
`evaluate_candidate_quality()` function was added that runs the identical
deterministic-check + AI-review pipeline directly over `CandidateRule.
payload_json` rows (parsed into `CanonicalRule`, with schema-validation
failures reported as findings rather than crashing). Both paths share one
`QualityReport` shape, distinguished by a new `scope: "published" |
"candidates"` field. This is now the recommended way to triage a large
extraction batch before spending review effort on it.

### 5. Bulk review, because one-by-one review doesn't scale to AI extraction volume
A single AI extraction run against a real ~30-page policy document produced
419 candidates. Reviewing 419 rows one at a time via the existing
single-candidate review endpoint is not a workflow a human would tolerate.
`POST /policy-sets/{key}/candidate-rules/bulk-review` was added: it accepts
an explicit list of candidate IDs, or an empty list meaning "all currently
pending candidates," applies approve/reject to each, and returns
`{reviewed, skipped}` (skipping anything already reviewed/published so a
client can safely re-submit). The frontend Review Queue gained matching
checkbox multi-select, a "select all N in this filter" toggle, and bulk
approve/reject buttons.

### 6. Governance discipline: don't blindly bulk-approve everything
When exercising the new bulk-review capability against real data (HR Guide
policy, 419 AI-extracted candidates from a document that is literally titled
"...Template.pdf"), the AI's own quality review correctly flagged that the
source contains placeholder/alternative clauses that should not be treated
as operative policy. Rather than bulk-approving all 419 candidates to prove
the feature works, only the 73 candidates with `ambiguity_status == "none"`
AND `machine_executable == true` were bulk-approved and published as v1 —
demonstrating the full cycle honestly while leaving the remaining 346
explicitly flagged for real human/legal review. This is the intended usage
pattern for the feature, not a one-off shortcut.

### 7. Azure AI Search: scoped to pre-existing shared indexes, read/write only
`myfoundryiqforscop` is a shared resource with pre-existing indexes
(`policy-authoring`, `policy-evidence`) used by other systems. The search
client never creates or alters index schemas — it only reads/writes
documents into the existing schema, and `infrastructure/search/indexing.py`
applies an explicit scoping/tagging strategy so this project's writes never
collide with or pollute the resource's unrelated pre-existing data.

## Alternatives considered
- **Official `openai` / `azure-ai-search` SDKs** — rejected for this phase to
  keep the dependency surface minimal and because every call site's exact
  wire behavior (especially the reasoning-model token-budget gotcha) needed
  to be verified directly against the live resource anyway; a thin `httpx`
  wrapper makes that verification and the resulting constraints (timeouts,
  `max_tokens` sizing) explicit in one place instead of hidden behind SDK
  defaults.
- **Auto-publishing AI extractions** — rejected outright; violates the
  project's core "no LLM in the final runtime decision" trust model and the
  explicit finding (from live testing) that AI-extracted candidates from a
  template document can include non-operative placeholder text.
- **A single "quality" endpoint with a query param instead of two routes** —
  considered, but two distinct routes (`/quality` vs.
  `/candidates/quality`) keep the "published" semantics unambiguous
  (no optional param defaulting behavior to reason about) and match how the
  frontend already models these as two different toggle states.

## Consequences
- **Positive**: all six AI capabilities (status, ask, extract, rewrite/apply,
  compare, quality — including the new candidates-quality and bulk-review
  additions) are real, tested against live Azure resources, and gated
  cleanly on/off via `.env` configuration.
- **Negative**: the `httpx`-based clients duplicate some request/response
  shaping that an official SDK would provide for free (retries, pagination
  helpers); acceptable trade-off given the small number of call sites.
- **Migration/compatibility**: swapping to official SDKs later is possible
  without changing any router/schema code, since callers only see
  `AzureOpenAIClient`/`AzureSearchClient`'s narrow method surface.
- **Operational**: reasoning-model calls (extraction, rewrite, quality,
  compare) can take up to ~180s each; evaluating a large candidate batch
  (e.g. 346 candidates) via `/candidates/quality` is a single long-running
  request — the frontend shows a disabled "Evaluating…" button state and
  the backend has no separate progress-streaming mechanism yet (documented
  as a known limitation).

## Validation
Verified live, end-to-end, against the real Azure resources and real policy
documents (HR Guide PDF, Workplace Hardware Provisioning DOCX v3.2/v3.3):
- `GET /api/ai/status` → `enabled: true`, correct chat/fast deployment names.
- `POST .../extract` → 419 real candidates extracted from the HR Guide PDF
  with correct page/paragraph source citations.
- `GET .../candidates/quality` → 346 candidates evaluated, 622 findings
  (33 high / 589 medium), correctly distinct from the published-scope report.
- Bulk-review → 73 clean candidates approved and published as
  `hr-guide-policy` v1; published-scope `/quality` on v1 showed 15 findings,
  confirming the pre-filter meaningfully improved rule-set quality.
- `POST .../rewrite` + `.../rewrite/apply` → live rewrite suggestion applied
  to a real candidate (revision 1 → 2).
- `GET .../compare?from=1&to=3` (hardware-provisioning-policy) → 171 added /
  0 removed / 1 changed (contractor threshold 20→10 days) + coherent AI
  narrative.
- Ask AI drawer (frontend, manual browser verification) → asked "What is the
  contractor engagement day threshold for hardware provisioning?" scoped to
  `hardware-provisioning-policy`; got the correct answer (10 working days)
  with accurate source citations to both the amendment history and the
  original 20-day clause.
- All new frontend UI (Quality page published/candidates toggle, Review
  Queue bulk-select) visually verified in a live browser session with no
  runtime errors.

## Addendum: PDF header/footer boilerplate fix (post-launch data-quality bug)

After the Ask-AI feature was reworked to quote source facts verbatim
(never paraphrased), live testing surfaced that some "facts" returned for
vague/broad questions were meaningless fragments like `"Policies and
Procedures Template - Page 16"`. Root cause: `document_extraction.py`'s
PDF path used `pdfplumber.page.extract_text()`, which inlines running
header/footer text with real body content (no separate "page furniture"
region), and the paragraph-chunking logic had no step to detect/strip
repeated header/footer lines before persisting `Clause` rows. This let
boilerplate get embedded and indexed into Azure Search, where it could
outrank genuinely relevant content for vague queries (all scores cluster
near the noise floor when there's no strong lexical/semantic signal).
DOCX extraction was confirmed unaffected (python-docx's body-only block
iteration never includes header/footer XML parts).

**Fix** (`_extract_pdf`, `_detect_boilerplate_lines`, `_normalize_line`):
a general, non-hardcoded two-pass detector — normalize each line (digits
→ `#` placeholder so e.g. "Page 7" and "Page 51" match the same pattern),
then treat a normalized line as boilerplate only when it appears as the
literal first-or-last line of a page on ≥30% of pages (min 3 pages).
Restricting candidates to the exact page edges (not any repeated line
anywhere in the page) was a deliberate second iteration: an initial
"any line repeating across pages" heuristic also stripped a recurring
*structural subheading* ("Policy and Procedure Statement", printed after
almost every policy's title in this HR template) — real content that
happens to repeat, but never at a fixed top/bottom margin position the
way a true running header/footer does. The narrower, positional
definition avoids that false positive while still reliably catching the
true footer. Also switched `extract_text()` to `x_tolerance=1`, fixing a
separate but related fidelity bug where missing inter-word spaces
produced artifacts like `"thispolicy"`.

**Remediation**: a one-off script (`scripts/reextract_document.py`)
deleted the already-persisted polluted `Clause` rows for the HR Guide PDF,
re-ran extraction with the fix, and replaced the corresponding stale Azure
Search index entries (added `AzureSearchClient.find_ids_by_filter` /
`.delete_documents` for this purge step, since re-extraction regenerates
clause UUIDs and the index's document key includes the clause UUID).
Verified via direct `/api/ai/ask` calls (before/after) and via
`tests/unit/test_document_extraction.py`; full existing suite (51 tests)
still passes. This was a genuine root-cause data-extraction fix, not a
prompt/UI patch — the Ask-AI verbatim-quoting contract from earlier in
this ADR's lineage is only trustworthy when the underlying `Clause` text
it quotes from is itself clean.
