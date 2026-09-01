# How we work

This page is for contributors. It records the engineering agreements this codebase is held to. They are here because most of them were learned by getting something wrong first, and the reasoning matters more than the rule.

## The one principle

> **Never assert more than the evidence supports.**

Everything below is an application of it. A policy platform's failure mode is not being unhelpful — it is being *confidently wrong about what a document said*, because that answer looks exactly like a correct one.

## What must never be invented

| Never | Because |
|---|---|
| A fact path in `rule.condition` | The evaluator, exports and DMN compilation all read it as a real binding |
| A relationship from wording or layout | Consumers read `related_rule_ids` as established fact |
| A placeholder condition to fill an empty tree | A synthesised always-false node is a constraint the document never stated |
| A summary of a family of rules | A summary of a policy is a new claim about the policy |
| An alignment between conditions and cases | Emission order is not a stated mapping |

When something cannot be derived, **say so and route it to a human**. An honest gap is a decision a reviewer can make; a plausible fabrication is one they cannot even see.

### Display is not the executable contract

Showing `subject.subject-id = "The ED/CEO"` is legitimate — it describes what the source states. Writing that into `rule.condition` is not. The two live in different modules for exactly this reason, and the boundary is load-bearing.

## Distinguish absence from failure

An empty condition tree has two causes that demand opposite responses:

| Cause | Encoding | Response |
|---|---|---|
| The rule is genuinely unconditional | `all: []`, honest | Human review — is it truly open, or was scope missed? |
| Conditions existed and were not projected | `all: []`, a defect | Human supplies the missing mapping |

They must stay distinct in **data and in UI**, with different reasons and different messages. Reading the second as the first turns a narrow permission into an open one.

The same rule applies everywhere: when a screen shows nothing, say *why* it shows nothing. A flat unbanded list cannot otherwise distinguish "grouping is off", "grouping is broken", and "no relationship was derived".

## Measure, do not assume

Before and after every behavioural change, **query the live system and count**.

This is not a preference. Relationship discovery was wired in, reported success, and contributed **exactly zero** edges — a field read from the wrong place yielded an empty anchor, the detector silently never fired, and nothing failed. Only counting the result caught it.

Corollary: **prove a test can fail.** Reintroduce the bug, confirm the test catches it, restore, confirm the diff is empty. A test that cannot fail documents nothing.

## Safety that a human has to arm is off

**A guard whose trigger is a hand-maintained value is disabled by default, and reads as enabled.** Derive the value, or accept that the guard is decoration.

This is a design rule, not an incident report, because the incident was the mildest possible version of it and the shape is general.

The quality history refuses to draw a trend across two runs whose methodology differs, and says why in its own source: a change to what can be discovered establishes a new baseline rather than masquerading as improvement or regression. That mechanism was correct, and it was reviewed as correct. What armed it was a version constant somebody had to remember to change, and nobody did — so every run recorded carried the same value, every pair compared equal, and the refusal never fired once. The page drew deltas straight across a change to the instrument while containing, a few lines away, the argument for why it must not.

Note the failure mode carefully, because it is what makes this worth a rule. The guard did not error. It did not warn. It reported the healthy answer — no methodology difference — which is indistinguishable from the answer it gives when it is working and there genuinely is none. **An unarmed guard and a satisfied guard produce the same output.**

The fix was to stop asking a human: `derive_methodology_version` (`infrastructure/quality/methodology.py`) computes the value from the detectors themselves, so adding or changing one moves it whether or not anyone thought about comparability.

Applies to anything with the same shape — a schema version, a cache key, a prompt revision, a feature flag defaulting to the permissive branch. If the correctness of a check depends on somebody updating a literal, the check is already wrong; it is only a question of when someone notices.

## Comments explain why

Code says what it does. Comments exist for what a reader cannot recover:

- the defect a guard closes, and how it presented
- the alternative that was tried and rejected, and on what evidence
- the standard or spec section that constrains the choice
- the blast radius of getting it wrong

Do not narrate the code. `// increment the counter` is noise; "assigned rather than accumulated: the pass runs over every rule each time, so its result is a total, and adding it would multiply the count by the number of batches" is the comment worth writing.

## Scope discipline

- Fix the reported defect. Fix bugs *caused by or tightly coupled to* the change. Leave unrelated ones.
- Prefer the smallest correction that addresses the proven root cause. Escalate to a structural fix only when the same cause affects multiple paths, or the responsibility sits in the wrong layer.
- When a full correction does not fit, **contain** the failure at the right boundary, label the temporary behaviour, and record the debt. A containment workaround is never described as a resolution.

## One standard, cascaded

Check [Standards](standards.md) before introducing a vocabulary. XACML 3.0 is already adopted. A second vocabulary for the same concept means a reviewer reads one screen in one set of terms and the next in another, with nothing saying the two describe the same rule.

## What stays on the workstation

The repository is public. Several kinds of file are deliberately kept out of it, and `.gitignore` enforces each — they are absent by decision, not by oversight, so do not add them back as tracked files. Everything in the second group below lives together under `docs/internal/`, so filing a document in the right directory is what keeps it local, rather than anyone remembering to add a rule for it.

| Kept local | Why |
|---|---|
| **Environment files** — `.env`, `.env.local`, `infra/parameters/*.env` | They hold real endpoints, logins and keys. Only the `*.example` templates are published, carrying placeholders. `.env` alone did not cover the variants, which is how a real Azure endpoint reached a published example file once. |
| **Decision records** — `docs/internal/adr/` | Reasoning about a choice, written for whoever is making it. The decision's *outcome* belongs in the code comment and the commit message, where it cannot drift from what shipped. |
| **Task lists** — `docs/internal/planning/`, `TODO.md` | A list of intentions dates immediately and describes work rather than the product. Open work belongs in the tracker; a defect worth remembering belongs in a test that fails. |
| **Audits and failure analyses** — `docs/internal/audits/` | Records of how the product went wrong, including drift reports and UI audits. Valuable to whoever is fixing it, misleading to whoever is trying to learn what it does now. |
| **Unfinished designs** — `docs/internal/planning/repair-passes.md` | Decided and not built. A published page describing behaviour that does not exist is worse than no page. |
| **The security roadmap** — `docs/internal/planning/security-roadmap.md` | The itemised list of authentication and authorization gaps still open. That access control ships off by default, and must be configured before exposing the build beyond a trusted environment, *is* published in the README and [Known limitations](known-limitations.md), because a user must know it. The item-by-item checklist is not, because a specific list of unclosed gaps on a public repository is an invitation rather than a disclosure. |
| **The running path** — `docs/internal/handover/running-path.md` | A step-by-step account of what this build actually executes, including which designed stages are unreachable. Internal working knowledge, not product documentation. |
| **Session records** — `docs/internal/handover/HANDOVER.md` | Session history, verbatim instructions and failure analyses, written for whoever picks the work up next. |

The general rule: **publish what the product is, keep what the work was.** A reader of this repository should be able to understand the system without reading anyone's notes about building it. What the product does *not* do is still published, in [Known limitations](known-limitations.md) — a boundary a user must know is part of the product, not part of the work.

Two consequences worth knowing:

- **Nothing published may link to a local-only page.** A link to a file a reader cannot fetch is worse than no link. When a page moves out, its inbound links go with it.
- **A guard that reads a local-only page must skip when the page is absent, not fail.** `test_the_running_path_is_the_documented_path.py` does this: it runs in full wherever the page is kept and skips visibly, with its reason, where it is not. Absence is a policy; breakage is a failure; the two must never look alike.

Verify a path before relying on it — `git check-ignore -v <path>` names the rule that matched, and says nothing if the file would be published.

## Commits

- Commit to the working branch; **state the branch name** in the work.
- The message explains the defect and the reasoning, not the diff — the diff is already in the commit.
- Include what was measured, and what was tried and rejected.
- Do not commit secrets, generated bundles, or virtual environments.
- **Stage by explicit pathspec.** `git add` then `git commit` is not atomic, and the index is shared mutable state: anything another writer stages between the two commands is swept into your commit. Name the paths on the commit itself (`git commit --only <path> ...`) so the set of files is decided once, by you. This is not hypothetical — a commit here collected four files belonging to someone else that way.

## Checks before committing

```powershell
# Backend — the full unit suite; no database or network required
.\.venv-graph\Scripts\python.exe -m pytest tests/unit -q

# Frontend
cd apps\web
npx tsc --noEmit
npm run build
```

### One check that is triggered, not routine

If your change **puts a new module on the production path** — anything reachable from document upload or from the AI extraction endpoint — run this as well:

```powershell
.\.venv-graph\Scripts\python.exe scripts/running_path_closure.py
```

It computes the call closure from the two entry points and reports modules on it that the running-path page (`docs/internal/handover/running-path.md`, kept on the workstation) does not name. Read what it names and decide; roughly four findings in five are worth acting on, which is why it is a script and not a build-failing guard.

The trigger is the point. A step added to the running system and left off that page is how a documented pipeline and a running one diverged before, and the person best placed to catch it is the one adding the module — who is also the person least likely to know the page exists. That is why the instruction lives here, next to the checks everyone runs, rather than only on the page it serves.

**This check is itself subject to [the rule two sections up](#safety-that-a-human-has-to-arm-is-off):** it needs a human to decide to run it, so by default it is off. That is a known and accepted weakness, chosen over a guard at this precision because an alarm that misfires gets disabled and takes the honest limitation down with it. Recorded plainly rather than dressed up.

The suite runs under `.[dev]` alone: tests that need Docling carry a `skipif` guard and skip themselves rather than failing at collection. The `graph` extra is what makes them execute. The torch footprint is a constraint on the runtime image, not on a development machine.

`pyproject.toml` sets `pythonpath = ["src"]`, so the suite runs without an editable install, and pins the approved Microsoft package feed proxy as the default index — resolving directly to `files.pythonhosted.org` fails the TLS handshake on managed networks and surfaces as an opaque retry error.

## Environment traps

Each of these cost real time and none of them fail loudly.

| Symptom | Cause |
|---|---|
| Azure returns `401` with a valid key | Ambient `AZURE_OPENAI_*` outranks `.env` in pydantic-settings, pairing one resource's endpoint with another's key. Use `scripts/run_api.ps1`, which clears them. |
| Every test module fails at import | Venv without the package installed and no `pythonpath` |
| `curl` succeeds, the browser fails | `--host ::` binds IPv6-only on Windows; browsers resolve `localhost` to `::1` first while `curl` prefers IPv4. Bind `0.0.0.0`, point the UI at `127.0.0.1`. |
| `InvalidCxxCompiler: cl not found` | Windows PDF conversion without `TORCHDYNAMO_DISABLE=1` |
| Package resolution retries then dies | Not using the approved feed proxy |
| Console `ReferenceError` for something you just wrote | Possibly a stale hot-reload artefact from a concurrent edit, not your defect. The dev server can serve a module from a moment that no longer exists. **Check the error against a clean build before believing it** — `npx tsc --noEmit` and `npm run build`. A scare reported from a stale bundle costs more than the check does. |

## Where to look

| Question | Page |
|---|---|
| Which standard governs this? | [Standards](standards.md) |
| How are rules linked? | [Relationships](relationships.md) |
| How does a document become elements? | [Docling](docling.md) |
| What does the AI actually decide? | [AI assistance](ai-assistance.md) |
| What is the system shaped like? | [Architecture](architecture.md) |
| What does the suite defend? | [Testing](testing.md) |
