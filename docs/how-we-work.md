# How we work

The engineering agreements this codebase is held to. They are here because most
of them were learned by getting something wrong first, and the reasoning matters
more than the rule.

## The one principle

> **Never assert more than the evidence supports.**

Everything below is an application of it. A policy platform's failure mode is
not being unhelpful — it is being *confidently wrong about what a document
said*, because that answer looks exactly like a correct one.

## What must never be invented

| Never | Because |
|---|---|
| A fact path in `rule.condition` | The evaluator, exports and DMN compilation all read it as a real binding |
| A relationship from wording or layout | Consumers read `related_rule_ids` as established fact |
| A placeholder condition to fill an empty tree | A synthesised always-false node is a constraint the document never stated |
| A summary of a family of rules | A summary of a policy is a new claim about the policy |
| An alignment between conditions and cases | Emission order is not a stated mapping |

When something cannot be derived, **say so and route it to a human**. An honest
gap is a decision a reviewer can make; a plausible fabrication is one they
cannot even see.

### Display is not the executable contract

Showing `subject.subject-id = "The ED/CEO"` is legitimate — it describes what the
source states. Writing that into `rule.condition` is not. The two live in
different modules for exactly this reason, and the boundary is load-bearing.

## Distinguish absence from failure

An empty condition tree has two causes that demand opposite responses:

| Cause | Encoding | Response |
|---|---|---|
| The rule is genuinely unconditional | `all: []`, honest | Human review — is it truly open, or was scope missed? |
| Conditions existed and were not projected | `all: []`, a defect | Human supplies the missing mapping |

They must stay distinct in **data and in UI**, with different reasons and
different messages. Reading the second as the first turns a narrow permission
into an open one.

The same rule applies everywhere: when a screen shows nothing, say *why* it
shows nothing. A flat unbanded list cannot otherwise distinguish "grouping is
off", "grouping is broken", and "no relationship was derived".

## Measure, do not assume

Before and after every behavioural change, **query the live system and count**.

This is not a preference. Relationship discovery was wired in, reported success,
and contributed **exactly zero** edges — a field read from the wrong place
yielded an empty anchor, the detector silently never fired, and nothing failed.
Only counting the result caught it.

Corollary: **prove a test can fail.** Reintroduce the bug, confirm the test
catches it, restore, confirm the diff is empty. A test that cannot fail
documents nothing.

## Comments explain why

Code says what it does. Comments exist for what a reader cannot recover:

- the defect a guard closes, and how it presented
- the alternative that was tried and rejected, and on what evidence
- the standard or spec section that constrains the choice
- the blast radius of getting it wrong

Do not narrate the code. `// increment the counter` is noise; "assigned rather
than accumulated: the pass runs over every rule each time, so its result is a
total, and adding it would multiply the count by the number of batches" is the
comment worth writing.

## Scope discipline

- Fix the reported defect. Fix bugs *caused by or tightly coupled to* the change.
  Leave unrelated ones.
- Prefer the smallest correction that addresses the proven root cause. Escalate
  to a structural fix only when the same cause affects multiple paths, or the
  responsibility sits in the wrong layer.
- When a full correction does not fit, **contain** the failure at the right
  boundary, label the temporary behaviour, and record the debt. A containment
  workaround is never described as a resolution.

## One standard, cascaded

Check [Standards](standards.md) before introducing a vocabulary. XACML 3.0 is
already adopted. A second vocabulary for the same concept means a reviewer reads
one screen in one set of terms and the next in another, with nothing saying the
two describe the same rule.

## Commits

- Commit to the working branch; **state the branch name** in the work.
- The message explains the defect and the reasoning, not the diff — the diff is
  already in the commit.
- Include what was measured, and what was tried and rejected.
- Do not commit secrets, generated bundles, or virtual environments.

## Checks before committing

```powershell
# Backend — 1026 unit tests; no database or network required
.\.venv-graph\Scripts\python.exe -m pytest tests/unit -q

# Frontend
cd apps\web
npx tsc --noEmit
npm run build
```

The suite needs the `graph` extra: 13 modules import Docling directly and fail
at collection in a `.venv` built from `.[dev]` alone. The torch footprint is a
constraint on the runtime image, not on a development machine.

`pyproject.toml` sets `pythonpath = ["src"]`, so the suite runs without an
editable install, and pins the approved Microsoft package feed proxy as the
default index — resolving directly to `files.pythonhosted.org` fails the TLS
handshake on managed networks and surfaces as an opaque retry error.

## Environment traps

Each of these cost real time and none of them fail loudly.

| Symptom | Cause |
|---|---|
| Azure returns `401` with a valid key | Ambient `AZURE_OPENAI_*` outranks `.env` in pydantic-settings, pairing one resource's endpoint with another's key. Use `scripts/run_api.ps1`, which clears them. |
| Every test module fails at import | Venv without the package installed and no `pythonpath` |
| `curl` succeeds, the browser fails | `--host ::` binds IPv6-only on Windows; browsers resolve `localhost` to `::1` first while `curl` prefers IPv4. Bind `0.0.0.0`, point the UI at `127.0.0.1`. |
| `InvalidCxxCompiler: cl not found` | Windows PDF conversion without `TORCHDYNAMO_DISABLE=1` |
| Package resolution retries then dies | Not using the approved feed proxy |

## Where to look

| Question | Page |
|---|---|
| Which standard governs this? | [Standards](standards.md) |
| How are rules linked? | [Relationships](relationships.md) |
| How does a document become elements? | [Docling](docling.md) |
| What does the AI actually decide? | [AI assistance](ai-assistance.md) |
| What is the system shaped like? | [Architecture](architecture.md) |
| What does the suite defend? | [Testing](testing.md) |
