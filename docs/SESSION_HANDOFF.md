# Session handoff — hard-won knowledge

Things that cost real time to discover. Most of these fail *silently*, which is
why they are written down: the code looks right, nothing throws, and the result
is quietly wrong.

Read this before changing extraction config, the approval flow, or the UI shell.

---

## Running the stack

| Piece | Value |
|---|---|
| API entry point | `policy_platform.api.app:app` — there is **no** `api/main.py` |
| API port | 8010 |
| Frontend | 5789 (`npm run dev` in `apps/web`) |
| Postgres | host port **5433**, container `policy-postgres`, user `policy_admin`, db `policy_platform` |
| psql | `docker exec policy-postgres psql -U policy_admin -d policy_platform -c "..."` |

Run the API **without `--reload`**. The reloader's file watcher fights the
extraction worker and produces confusing mid-run restarts.

---

## Extraction config: `trusted_config`

**Key on the source term exactly as it appears in the policy text, with the FEEL
target nested inside.** Keying by the FEEL path instead looks entirely
reasonable and fails **silently** — no error, no warning, the term simply never
resolves and the rule lands as `enrichment_required`.

```jsonc
// right — keyed by what the document says
{ "Basic Salary": { "feel_expression": "employee.basic_salary" } }

// wrong — silently ignored
{ "employee.basic_salary": { "source_term": "Basic Salary" } }
```

Shape requirements, also enforced silently:

- `fact_model` entries need `feel_expression`
- `output_model` entries need `feel_name`
- `temporal_model` is **not** a valid Section 83 key — it is dropped without complaint

If coverage is mysteriously low, check these three before suspecting the model.

---

## Approval and publish API

- There is **no `/approve` endpoint**. Use
  `POST /{key}/candidate-rules/bulk-review`.
- It takes **UUIDs**, not the `AI-` display ids. Passing `AI-` ids fails to match
  anything and reports success against zero rows.
- An **empty list means "all pending"** — convenient, and dangerous if you meant
  to pass a filtered set that happened to come back empty.

### Schema quirks

- `candidate_rules` has **no** `rule_id` / `machine_executable` columns — both
  live inside `payload_json`.
- `approved_rules` **does** have them as real columns.

So a query that works against one table silently returns nothing useful against
the other.

---

## Current data state

- 68 candidates sit at `enrichment_required`.
- Only 9 of 190 rules are executable.

The mechanism is proven end to end; **coverage is not**. Do not read a working
pipeline as a complete one.

---

## UI: the token architecture

There are **two `:root` blocks**, and only one of them is authoritative.

- **`index.css` is canonical.** It owns the brand and slate ramps, semantic
  colours, `--bg-*`, `--border-*`, `--text-*`, shadows, radii, fonts, and now the
  spacing scale (`--sp-1..6`) and type scale (`--fs-xs..--fs-display`).
- **`App.css` may only alias.** It loads after index.css, so redefining a token
  there silently changes every existing use of it.

This is not hypothetical — a `--border-strong` redefinition in App.css changed
two existing call sites with no visible error. If a colour looks subtly off,
check for a duplicate definition before anything else.

**Set the type scale at the antd token in `main.tsx`, not in CSS.** antd derives
heading sizes, control heights and line-heights from its tokens. Overriding
`font-size` downstream gives you small text inside unchanged 40px controls,
which reads as "wrong" without being obviously broken.

---

## UI: rc-tabs constraints

These were each discovered by breaking something.

- **`.ant-tabs-nav-wrap` must stay `flex: 0 1 auto`.** Pinning it to `0 0 auto`
  breaks antd's overflow calculation — it compares wrap width against list
  width. Tabs then get **silently clipped and become unreachable** instead of
  moving into the "more" menu.
- **rc-tabs refuses to wrap.** Forcing `flex-wrap` produces seven stacked rows.
  Do not retry this.
- A tab's `label` renders **inside** the tab button, so anything you put there is
  enclosed by the active pill. Use `data-node-key` on `.ant-tabs-tab` as the seam
  for group dividers.
- **Tabs nest their panels under the nav.** If `<Tabs>` sits inside a styled bar,
  every panel is trapped in that bar. Fix: give items no `children` and render
  `TAB_CONTENT[activeTab]` as a sibling, hiding the empty holder. Only the active
  panel ever mounts either way.

In `ProjectWorkspace.tsx`, `TAB_CONTENT` must stay immediately before
`return (` — declaring it earlier causes a TDZ `ReferenceError`.

---

## Diagnosing layout complaints

The lesson from a long and repetitive round of "it looks too big": **measure
before theorising.** I twice had a confident hypothesis that measurement
disproved.

- "Fonts are too large" → queried the DOM: **zero inline font sizes** on the page
  in question. The real cause was content volume, not type.
- The Tests tab was 3589px tall with zero tests, of which ~2700px was
  explanatory prose. That is a **content** problem wearing a CSS costume.

Useful technique: query for the tallest cards and the largest
`margin/padding/gap` values, sorted, rather than reading screenshots.

Watch for **duplicated information** presenting as a spacing problem — the Review
tab had a stats banner rendering the same six counts as the interactive filter
chips directly beneath it. Merging beat shrinking.

### Shared browser canvas traps

- The canvas viewport is only **614px** wide at `dpr 1.5`, which distorts what
  the user actually sees. Simulate with
  `document.documentElement.style.zoom='0.42'` (≈1462px effective), divide
  measurements by the factor, and **always revert** — the browser is shared with
  the user.
- It can serve a **stale HMR-injected `<style>`** that survives reload *and*
  cache-bust. Cross-check with
  `fetch('/src/App.css?direct',{cache:'no-store'})`, or grep the built
  `dist/assets/*.css`. Note the minifier rewrites values
  (`rgba(255,255,255,0.46)` → `#ffffff75`, `flex: 0 1 auto` → `flex: 0 auto`), so
  match loosely.
- Long `await sleep()` chains inside one `evaluate_javascript` call time out —
  split them.
- `chrome-devtools` MCP tools are unusable here (profile already in use).

---

## Repository etiquette

- **Never `git add -A`.** A concurrent session shares this working tree. Stage
  explicit paths only.
- **There is no git remote.** `git remote -v` is empty and `master` has no
  upstream, so *push is not possible*. This was not an oversight — the repo
  contains HR and policy data, so creating a remote is a decision for the owner,
  not something to do unprompted.
- PowerShell here has no heredocs — use `@'...'@`. Multi-line commit messages via
  `.git\CMTMSG` + `git commit -F`. `&&` only chains native commands; use `;`.
- `AGENT_PROGRESS.md` (~339KB) is a shared running log. **Check the last
  milestone number before appending** — the concurrent session writes to it too.

---

## Known debt, deliberately not fixed

- Commit `89dc40e`'s message claims `PolicyTestsPage` gained "search and
  filtering". It has kind filtering and status grouping but **no free-text search
  and no pagination**. Not rebased: rewriting shared history under a concurrent
  session is worse than the inaccurate wording.
- **219 inline spacing values** remain across components. The `--sp-*` and
  `--fs-*` tokens now exist but those call sites have not been migrated. This is
  the reason local styling fixes kept failing to hold — there was nothing to be
  consistent *with*. Migrate opportunistically.
