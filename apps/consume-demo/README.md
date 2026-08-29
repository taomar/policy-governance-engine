# Policy API Playground

An **external client demonstration**. It shows how an agent, a Copilot
integration, a workflow or a business process calls one governed project's
published policies over HTTP, and then renders the full audited receipt it is
answered with.

It is not a second admin UI. It cannot author, edit, approve, publish, compare
or score a policy, and it has no project register and no review queue. It sends
one request and reads one receipt.

## Why it is a separate application

The claim this page makes is that the REST contract is sufficient — that an
outside system needs a base URL, a project key and a credential, and nothing else.
That claim is only worth anything if it is true of the demo itself, so:

- it imports nothing from `apps/web`, nothing from `policy_platform`, and
  nothing above its own directory;
- it declares its own `package.json`, its own lockfile and its own
  `tsconfig`, and it is not a member of any workspace;
- it has no database client and no path to data other than `fetch`;
- it declares no TypeScript or Vite path alias, because an alias is the usual
  way a "separate" app quietly starts sharing source.

`tests/unit/test_the_consume_demo_only_speaks_rest.py` asserts all of the above,
so the boundary is checked rather than merely intended.

## Running it

```bash
cd apps/consume-demo
npm install
cp .env.example .env.local   # point VITE_POLICY_API_BASE_URL at your API
npm run dev             # http://localhost:5179
```

The port is fixed at 5179 with `strictPort`, because 5179 sits inside the API's
default development CORS range (`CORS_DEV_PORT_RANGE`, 5173–5180). Letting Vite
wander to the next free port produces a browser-side CORS block, which looks
like a broken backend rather than like a port collision.

```bash
npm run build   # tsc -b && vite build
npm test        # vitest
```

## The credential

The demo authenticates with an **API subscription key**, sent in
`X-Policy-Subscription-Key`. It does not use a bearer token and sends no
`Authorization` header. The server side is `POLICY_SUBSCRIPTION_KEY` — see
[Configuration](../../docs/configuration.md#calling-the-decision-api-from-another-system).

The key is typed into a **plain text field and is visible**, and it appears in
the Raw HTTP tab exactly as it will be sent, including in what Copy and Download
emit. That is deliberate, and it is a decision about *this local demonstration*
against a key an operator generated for local use: the page exists to show the
exact request an integrator must reproduce, and an example with asterisks where
the credential goes cannot be pasted, compared against a failing call, or
checked for the typo that causes most first-integration 401s.

**Do not read that as a pattern.** A shipped browser client must not hold a
shared subscription key at all — see
[External consumption](../../docs/external-consumption.md#where-the-credential-may-live).
Put your own server in front of the API and let it hold the credential.

What has not relaxed is persistence. The key lives in React state for the life
of the tab and is never written to `localStorage`, `sessionStorage`, a cookie,
the URL or the console. `tests/unit/test_the_consume_demo_only_speaks_rest.py`
asserts that, and `src/App.test.tsx` asserts it against the rendered page.

### Prefilling it locally

`.env.example` declares `VITE_POLICY_SUBSCRIPTION_KEY` and leaves it **empty**.
Set it in your own `.env.local` — which is git-ignored — if you would rather not
retype the key on every reload.

Two things follow from Vite inlining `VITE_`-prefixed values at build time, and
both matter:

- a value committed to `.env.example` would be a value in every clone, so the
  committed default is empty and a guard test fails if it is not;
- `npm run build` on a machine with `.env.local` set produces a `dist/` bundle
  containing that key. `dist/` is git-ignored. Do not publish a build made on a
  machine that has a real key configured.

The test suite pins the variable empty (`define` in `vitest.config.ts`), so the
tests exercise the committed default rather than whatever the machine running
them happens to have.
## The two rules the page is built around

**Status is read before verdict, always.** The verdict node is not rendered at
all unless `decision_status` is `answered`. Six of the seven statuses mean
something other than "the policies decided", and "no published rule bears on
this case" is not "the policies say no".

**A receipt that was not stored is not a usable success.** A `500` carrying
`decision_receipt_failed` renders the error and no verdict, no result grid and
no hash — regardless of any decision payload in the body.

## What is on screen

| Region | What it is for |
|---|---|
| Request docket | Connection, the subscription key, the case, caller guidance, and the correlation id you are about to send |
| Request Inspector | The exact request, live, before it is sent: the JSON body, the caller/server guidance split, and the raw HTTP including the credential header |
| Status band | The decision status first; the verdict only when the status carries one |
| Decision receipt | Identity, the request as the *server* recorded it, and the hashes |
| Result | Status, verdict-or-why-not, route, explanation, missing facts, decision hash |
| Rule evidence | Every cited rule with its provision, page/section and verbatim quotation |
| Retrieval | What was considered, retained and discarded, and why |
| Raw JSON | The `case_decision_v1` envelope, unmodified |

## What the caller may steer, and what it may not

`Additional instructions` shapes how the explanation is presented and nothing
else. It cannot change which policies were retrieved, what a rule means, the
decision status, the verdict, or the requirement to cite. The server's own
system instructions are not exposed, not editable and not returned; the receipt
identifies them by `trace.prompt_version` and `trace.instruction_profile`
instead. The Inspector renders those as two visually separate registers, and the
read-only one contains no control of any kind — not even a disabled one, because
a disabled field implies a lock and a lock implies a key.

## API surface used

| Call | Purpose |
|---|---|
| `POST /api/policy-decisions/{project_key}/case` | Put the case; returns the `case_decision_v1` envelope |
| `GET /api/policy-decisions/{decision_id}` | Read the stored receipt back, for verification |
| `GET /api/policy-sets/{key}` | Resolve the project's identity from its key |
| `GET /api/policy-sets/{key}/active-version` | Resolve the version a case would be decided against |

`X-Correlation-Id` and `Idempotency-Key` are headers, never body keys: they
describe the delivery of the request rather than the question being asked, and
putting the idempotency key in the body would make it part of the hash it is
compared against.