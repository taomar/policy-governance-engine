# Working agreements for agents in this repository

## The rule that matters most: never assert a dead end you have not checked

The expensive mistakes in this repository are not wrong edits. They are **wrong
conclusions stated as facts** — and specifically *negative* ones:

> "that file is missing" · "that's environmental" · "that's pre-existing" ·
> "that's unfixable" · "that's not in scope"

A wrong positive claim gets caught by the next test run. A wrong negative claim
**closes the investigation**, and nothing later reopens it. It survives into the
summary, the commit message and the handover, and the next person inherits it as
established fact. Every one of these has already happened here and each cost real
time:

| Asserted | Actually |
|---|---|
| "the source PDF is lost, unfixable" | sitting on the user's Desktop |
| "these CORS failures are environmental" | a test reading the ambient `.env`; a genuine defect |
| "`docs/internal/` is not gitignored" | ignored at `.gitignore:93-95` |

**So: a negative claim is a finding that needs evidence, exactly like a positive
one.** Before writing "missing", "unfixable", "pre-existing" or "environmental",
run the check that would disprove it. If you cannot run that check, say what you
do not know instead of rounding it down to a dead end.

State confidence honestly. "I have not verified this" is cheap. "This is
unfixable" when it is not costs an hour.

## Verification recipes for the traps this repository actually sets

**Before calling a file missing** — search for it before concluding it is gone.
Missing from an expected path and missing from the machine are different facts:

```powershell
Get-ChildItem -Path $HOME -Recurse -Filter "*<name>*" -File -Force -EA SilentlyContinue
```

**Before calling a test failure environmental** — check whether the test reads
ambient configuration. `Settings` reads `.env` for any field a caller does not
pass, so a test that constructs it inherits the developer's machine. A test that
passes in CI and fails locally on identical code is a **defective test**, not an
environment problem. Fix it by pinning the inputs in the shared helper, the way
`tests/unit/test_cors_settings.py::_settings` and `TestApplicationWiring` do.

**`git check-ignore` does not answer "is this ignored" for a path that does not
exist.** A directory rule such as `docs/internal/` will not match a directory
that is absent, and the command reports no match — which reads exactly like "not
ignored". Grep `.gitignore` instead when the path is absent.

**Before calling a failure pre-existing** — "I did not touch that file" is an
argument, not evidence. Prove it: check whether the offending line is in the
diff, or whether the cause is an artifact that was never present. Baseline
failures are suspects, not scenery — this repository's baseline contained a real
defect that had been miscategorised as background noise.

## Local-only artifacts that are absent by design

These are deliberately outside the repository. Their absence is normal and is
**not** a reason to fail, skip, or invent a workaround — but confirm which case
you are in before claiming either way:

| Path | Status |
|---|---|
| `.env`, `apps/consume-demo/.env.local` | gitignored; hold real credentials. Never commit, never echo a value. |
| `data/documents/` | gitignored upload directory. Runtime data; restoring a file here is environment repair, not a repository change. |
| `docs/internal/`, `docs/adr/`, `docs/handover/`, `docs/todo/` | gitignored by design (`.gitignore:31-34, 93-95, 107-108, 135-139, 153-154`). Published documents may legitimately reference them; `_EXPECTED_ABSENT` in `tests/unit/test_documented_paths_exist.py` is the sanctioned way to record that. |

## Tests are evidence, so treat them as evidence

* Tests here are written to **refuse to skip quietly** — see `tests/corpus.py`,
  which fails rather than skips when an upload is absent, because *"a silent skip
  reads exactly like a pass"*. Do not convert such a failure into a skip.
* A guard that never refuses anything is a validator that could not fail. When
  adding one, add the test that watches it refuse — and a control proving it is
  not simply refusing everything.
* `vitest` worker-startup timeouts (`Timeout waiting for worker to respond`,
  `transform 0ms`, "no tests") are **resource contention**, not assertion
  failures. Do not run the backend suite and both frontend suites concurrently;
  re-run serially before reporting a frontend failure.

## Scope discipline

* Nothing may be shaped around a particular corpus, project key, index or
  domain. `tests/unit/test_no_m2_code_is_shaped_around_a_corpus.py` enforces
  this; run it after any change to the retrieval, projection or decision path.
* Do not commit, push, reset, stash or revert unless explicitly asked.
* Do not change a recorded architectural decision to match the code, or the code
  to match a recorded decision, without being asked. Record the mismatch.
* No caching, memoisation or "same answer as last time" shortcut anywhere in the
  decision path. This is a standing user decision.
