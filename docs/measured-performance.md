# Measured performance

Numbers observed against a live deployment, with the method that produced them.

Everything here is an **observation from one corpus on one afternoon**, not a
service level objective, not a benchmark, and not an accuracy claim. No latency
guarantee is offered anywhere in this product. The reason to publish it is that
an integrator sizing a timeout, or an operator choosing a deployment, is
otherwise guessing — and the shape of these numbers is more useful than their
exact values.

## How the measurements were made

| | |
|---|---|
| Client | A local developer machine, calling over the public internet |
| Azure OpenAI region | **Sweden Central**, confirmed from the service's own `x-ms-region` response header rather than assumed |
| Azure AI Search | The same resource used by the running application |
| Route exercised | `POST /api/policy-decisions/{project_key}/case/light`, followed by `GET /api/policy-decisions/{decision_id}` to read the full receipt back |
| Corpus | Two published projects — an employee handbook and a hardware provisioning policy |
| Matrix | 20 scenarios × 2 repetitions = 40 decisions per configuration |
| Reasoning effort | `medium` unless a row says otherwise |

**The client is not in the same region as the service.** Every wall-clock figure
below therefore includes public-internet round trips that a deployment
co-located with its models would not pay. Read them as an upper bound on that
axis, not as what the platform costs in a datacentre.

**Decision Light was the route called, and that does not make these numbers
smaller than a full decision's.** Light runs the identical adjudication and
stores the identical receipt; only the response body is smaller. Nothing about
the timings below would improve by calling `/case` instead.

## What a decision costs

Over 40 decisions per configuration, on the `medium` default:

| | p50 | p95 | slowest | median tokens |
|---|---:|---:|---:|---:|
| Wall clock, client-observed | 20.8–22.9 s | 33.5–46.2 s | 38.8–216.2 s | ~14,300 |

Ranges span the three deployments compared below. The slowest column is wide
because one of them has an unbounded tail; that is a property of the model, not
of the platform, and it is the subject of the comparison.

Token composition is stable and lopsided: roughly **13,200 prompt tokens**
against **600–900 completion**, of which **150–400 are reasoning**. Reasoning is
a breakdown *inside* completion, not a third bucket beside it — `prompt +
completion == total` on **40 of 40** rows in every arm, so adding reasoning on
top would double-count it. The corpus dominates what is *sent*; the reasoning
dominates what it *costs in time*.

That asymmetry is the single most useful thing on this page. A decision's
duration tracks how much the model reasons, not how much policy text was
retrieved. Shortening a question or narrowing the corpus reduces tokens and
money without reliably reducing wall-clock time.

### Where the time goes

The timing keys nest, so they decompose cleanly as long as each level is read
separately. Figures are per-row medians on `gpt-5.6-terra` — each stage measured
against *its own* request, then medianed, rather than one percentile divided by
another.

**The request, outermost level:**

| Stage | Median | Share of wall |
|---|---:|---:|
| Reservation write (`reservation`) | 8 ms | 0.0% |
| Inbound language boundary (`language_in`) | 2.5 s | 12.5% |
| The decision itself (`decider_wall`) | 18.2 s | 87.3% |
| Outbound language boundary (`language_out`) | 0 ms | 0.0% |
| Policy link lookup (`policy_link_lookup`) | 4 ms | 0.0% |
| **Total to envelope (`to_envelope`)** | **20.9 s** | **99.8%** |

Those five account for `to_envelope` with a **2 ms** median residual — the outer
level is fully attributed. `language_out` reads 0 ms because this corpus is
already in the processing language; a corpus that needed rendering back would
not.

**Inside `decider_wall`:**

| Stage | Median | Share of wall |
|---|---:|---:|
| Project scope load (`scope_load`) | 0.8 s | 3.2% |
| Intent classifier (`classifier`) | 4.4 s | 20.0% |
| Retrieval preflight — index ∥ readiness ∥ embedding (`retrieval_preflight_wall`) | 2.4 s | 12.3% |
| Policy and rule queries (`retrieval_discovery_wall`) | 2.4 s | 12.7% |
| Adjudication gathers (`gather_wall`) | 6.2 s | 29.2% |

Those five account for `decider_wall` with a **27 ms** median residual. Three
further stages sit inside it — `policy_selection`, `retained_rule_ranking` and
`rule_slice_and_fit` — and each medians **0 ms**, which is why they are not
given rows; `retained_rule_ranking` does reach 1.8 s at its worst, and that
worst case is what the 27 ms residual's own maximum reflects. The gap between
the server finishing its envelope and this client seeing the response medians
**37 ms**, and never exceeded 63 ms.

**Both residuals are per-row medians, not differences of the medians in the
tables.** Subtracting one published median from another is a different and
invalid statistic — the medians above do not add, and reading them as though
they do is the specific error that produced this project's earlier phantom
"unattributed" time. Each residual here was computed on each request
individually and then medianed.

So a request is attributed end to end. There is no unexplained bulk left in it —
which is what the telemetry work was for, and is a stronger statement than any
timing figure on this page.

**Do not add a stage from one level to a stage from the other**, and do not sum
within a level except as shown. `gather_wall` is 6.2 s while `gather_total` is
11.2 s, and both are correct — but the gap is **not** concurrency. `gather_total`
spans the classification and gather phase together, so it already contains the
classifier: measured per row, `gather_total − (classifier + gather_wall)` has a
median of **1 ms**. Treating the difference as "gather work" and adding it to
the classifier row would count the classifier twice. The field-level reference
for every key, and which ones nest, is in
[API → timing and token telemetry](api.md#timing-and-token-telemetry).

Two stages are worth separate attention. The **classifier** is ~4.4 s and
strictly serial ahead of everything it gates; at the time of measurement it ran
on the retired `gpt-5.4-mini` deployment, and it now runs on the primary
reasoning deployment at medium reasoning, which is expected to cost more time
rather than less. **Finalisation is not a latency problem** — policy link lookup
medians 4 ms and the reservation write 8 ms, tens of milliseconds against a
~21 s request.

## Choosing a deployment

Three chat deployments were compared as the **deep** role. At the time of that
comparison a separate `gpt-5.4-mini` deployment ran the classifier and the
language boundary, and it was held constant across every arm, so any difference
is attributable to the deep model and not to two changes made at once. That
`gpt-5.4-mini` slot has since been retired — see
[why there is no `temperature=0` deployment any more](#why-there-is-no-temperature0-deployment-any-more)
— so the absolute figures below predate the current configuration. The
comparison between the three deep deployments is unaffected, because the change
applied equally to all of them.

### Method, and why the first attempt was thrown away

The comparison was run twice.

**Sequentially first** — each model as its own matrix, one after another, over
about two hours. That reading said `gpt-5.6-terra` was **33% slower** than
`gpt-5.6-sol` (25,660 ms vs 19,251 ms at p50).

That number was wrong, and the runs themselves show why. Three stages in every
request **cannot be moved by changing the deep model**: the intent classifier and
the inbound language boundary both run on the *fast* deployment, held constant
across every matrix, and the retrieval preflight is search and embedding with no
chat model in it at all. They are controls. Between the two sequential runs they
nevertheless moved:

| Control stage | Sequential | Interleaved |
|---|---:|---:|
| `language_in` | 13.0% | **0.2%** |
| `retrieval_preflight_wall` | 23.4% | **0.1%** |
| `classifier` | 5.2% | 7.8% |

A 23% shift in a stage the change cannot reach is the same order as the 33%
effect being claimed. Whatever produced it was also acting on the stages that
*were* being compared.

**Interleaved second** — three backends, one per deep model, all live at once,
with the same scenario put to every arm within the same minute and the arm order
rotated per scenario so no arm is permanently first. Each recorded row carries
the deployment named by its *own receipt*; the sequential runs did not record
that field at all, so their attribution rested on knowing which backend was up.

Interleaved, `gpt-5.6-terra` is **6% faster**, not 33% slower — the sign
reverses. Two of the three controls collapse to under half a percent. The
classifier does not tighten, and that is worth stating rather than smoothing
over: interleaving removed the drift on two controls and not on the third, so
the classifier's 5.2% sequential spread was never distinguishable from its 7.8%
interleaved one. Two observations do not establish a noise floor, and this page
does not claim one — [API → reasoning effort](api.md#what-low-measured-on-one-corpus)
records a separate run in which the classifier's p50 moved **+15%** with no
cause that could reach it, which is well outside anything seen here.

The lesson generalises beyond this repository: **a sequential A/B against a
shared cloud service measures the service's mood as much as the change.** If you
repeat this work, interleave, and keep a control stage the change cannot reach —
without one, there is no way to tell the two apart.

### Results

40 paired calls per model, `medium` reasoning, same minute, rotated order.
Percentiles are **nearest-rank** — every figure below is an observation that
actually occurred, not an interpolation between two of them:

| | `gpt-5.6-sol` | `gpt-5.6-terra` | `gpt-5.6-luna` |
|---|---:|---:|---:|
| Scenario gate | 17/20 | 17/20 | **18/20** |
| Hash, Full≡Light, citation integrity | 40/40 | 40/40 | 40/40 |
| Wall p50 | 22,092 ms | **20,822 ms** | 22,930 ms |
| Wall p95 | 46,219 ms | **33,491 ms** | 39,738 ms † |
| Slowest single call | 83.1 s | **38.8 s** | **216.2 s** |
| Calls over 120 s | 0 | 0 | **2** |
| Verdict gather p50 † | 9,657 ms | **6,888 ms** | 10,008 ms |
| Median reasoning tokens | 283 | **157** | 369 |
| Median prompt tokens | 13,185 | 13,185 | 13,244 |

**† The verdict gather row is over a subset, not all 40.** `verdict_gather` is
recorded only when the caller's question actually asked for a verdict, which was
35, 34 and 35 of the 40 calls respectively. Read beside `gather_wall` over all
40 calls it looks impossible — 6,888 ms inside a 6,214 ms container — but on the
same subset `gather_wall` medians 6,906 ms, and no single call has
`verdict_gather` exceeding its own `gather_wall`. The subsets are close in size
but not identical, so the cross-model comparison below is indicative rather than
strictly paired.

**† Do not read Luna's p95 as a better tail than Sol's.** It is lower only
because its two worst calls — 202.6 s and 216.2 s — sit *above* the 95th rank of
40 samples and are therefore excluded by construction. Luna's three slowest
calls are 39.7 s, 202.6 s and 216.2 s; Sol's are 46.2 s, 48.2 s and 83.1 s. Under
linear interpolation instead of nearest-rank the same data puts Luna's p95 at
47.9 s, above Sol's. A single percentile cannot describe a bimodal tail, which is
why "slowest call" and "calls over 120 s" are reported beside it.

**`gpt-5.6-terra` is the recommended deep deployment.** It reached the same
verdicts as `gpt-5.6-sol` — the same three scenarios failing on the same three
checks — while spending about 45% fewer reasoning tokens, running 29% faster on
the verdict gather that dominates the clock, and holding a far tighter tail.
There is no axis in this data on which Sol beats it.

**`gpt-5.6-luna` is not recommended, despite scoring higher on the gate.** It
passed one scenario the other two fail, which is a real and interesting result.
But it reasons about 30% more than Sol and more than twice as much as Terra, and
that extra reasoning is unbounded: two of its forty calls ran past 200 seconds,
and both would have failed a caller following this API's own
[120 s timeout guidance](external-consumption.md#timeouts-and-recovery).
One additional correct answer does not pay for a 5% timeout rate.

Counting every fault class rather than only the gate. The two tail rows are made
disjoint on purpose — a call over 120 s is also a call over 60 s, and adding
both rows would count Luna's two slow calls twice:

| | Sol | Terra | Luna |
|---|---:|---:|---:|
| Scenarios failing the gate | 3 | 3 | 2 |
| Calls between 60 s and 120 s | 1 | 0 | 0 |
| Calls over 120 s | 0 | 0 | 2 |
| Integrity failures of any kind | 0 | 0 | 0 |
| **Total** | 4 | **3** | 4 |

On that count Luna ties Sol rather than trailing it, and the case against Luna
does not rest on the total: it rests on *which* faults they are. Sol's single
slow call was 83.1 s and would have returned inside the documented timeout;
Luna's two were 202.6 s and 216.2 s and would not.

### Why there is no `temperature=0` deployment any more

Until this change the intent classifier and the language boundary ran on
`gpt-5.4-mini` at `temperature=0`, on the stated reasoning that this was "the one
determinism control that deployment honours". Both stages now run on the
**primary** reasoning deployment at `medium` reasoning, with no sampling control
at all, and the `gpt-5.4-mini` deployment is no longer used anywhere.

They were briefly moved to `gpt-5.6-sol` instead, which agreed with itself more
often in the offline comparison below. That did not survive contact with the
live decision route: the classifier stage reached **261,761 ms** on a call that
spent 125 reasoning tokens — throttling and client retry rather than compute —
and produced a 306 s request against this API's own 120 s timeout guidance. The
decision and decision-light routes are single-model for that reason, and
`gpt-5.6-sol` is used only on the document-loading path.

**The reason is that the determinism was not real.** Asked eight scenarios three
times each through the real classifier prompt, the `temperature=0` deployment
contradicted itself:

| Scenario | `gpt-5.4-mini` at `temperature=0` | `gpt-5.6-sol` | `gpt-5.6-terra` |
|---|---|---|---|
| `hw-contractor-15-days` | informational, informational, **decision** | decision ×3 | decision ×3 |
| `hw-stolen-trip` | informational ×3 | decision ×3 | decision, decision, informational |

The parameter was not buying the stability it was there for. It is also the case
that `hw-contractor-15-days` is one of the three scenarios that persistently fail
their gate, and that the retired deployment classified it differently from both
reasoning models.

`seed` is accepted by every deployment on this resource and was separately
measured to change nothing — six identical quality reviews varied as much seeded
as unseeded — and the service returns a null `system_fingerprint`. So no sampling
control on offer delivers run-to-run determinism, and **the product no longer
claims one anywhere**.

Note what this comparison is not. Twenty-four classifications is a small sample,
`gpt-5.6-sol` agreeing with itself on 8 of 8 scenarios against Terra's 7 of 8 is
not a significant difference, and neither was compared on extraction at all.

The reasoning deployments do still reject the parameter outright:

```
400 Unsupported value: 'temperature' does not support 0.0 with this model.
    Only the default (1) value is supported.
```

Probed live: `gpt-5.6-sol`, `gpt-5.6-terra` and `gpt-5.6-luna` all reject
`temperature=0` and `top_p=0`, and all accept `seed`. So sending a temperature to
either configured deployment is not a degraded call, it is a failed one.

## Reasoning effort

`reasoning_effort` is the one request field that materially moves a decision's
duration. Measured by running the same matrix at `low` and at `medium` an hour
apart and comparing **paired by scenario**, nearest-rank as above:

| | p50 | p75 | p95 |
|---|---:|---:|---:|
| Reasoning tokens | −44% | −67% | −51% |
| Verdict gather | −23% | **−55%** | −35% |

End-to-end p95 fell 22%. **p50 did not move.** That is the mechanism rather than
a contradiction: the median request in that matrix reasoned only ~220 tokens, so
there was almost nothing to cut, while the slow quartile reasoned ~840 and its
gather more than halved.

So `low` is a **tail** lever. Reach for it when a timeout or a p95 is the
problem; it will not help a median that is already fast. Verdicts were unchanged
across all 20 scenarios, which is evidence that this matrix did not detect a
cost — not evidence that adjudication depth is free.

The caller-facing version of this, with the caveats an integrator needs, is in
[API → what `low` measured](api.md#what-low-measured-on-one-corpus).

## What these numbers do not establish

- **Accuracy.** The scenario gate is a regression check against expectations
  recorded for one corpus. 17/20 is not an accuracy score, and the three
  persistent failures are documented as
  [known limitations](known-limitations.md) rather than as noise.
- **Model quality in general.** Terra matched Sol on 20 scenarios of two
  policy corpora. It has not been compared on anything harder, and a 45%
  reduction in reasoning is a cost result, not proof of equal judgement.
- **Anything about a co-located deployment.** Every figure includes
  public-internet latency from a developer machine to Sweden Central.
- **Repeatability of Luna's extra pass.** One scenario, one observation. It may
  be capability or it may be variance, and it has not been re-run in isolation.
