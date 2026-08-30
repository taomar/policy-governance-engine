/** THE EXAMPLE IS A PROMISE, AND IT IS MADE WITHOUT A CREDENTIAL.
 *
 * These builders produce text a person copies into another company's service.
 * Two things therefore have to be true of them, and neither can be established
 * by looking at a screenshot:
 *
 *  1. No signed-in credential can travel with the text. Proved here by seeding
 *     a real session in `sessionStorage` — the shape `auth.ts` stores — and
 *     asserting no snippet contains any part of it. The builders import nothing
 *     that can read a session, so this is a floor rather than a coincidence,
 *     and the test states it so a future refactor that reaches for one fails.
 *
 *  2. The example teaches the right reading order. A case asks for up to two
 *     things — what the published policies state, and how the case comes out —
 *     and each track is answered on its own. Both sections are `null` when
 *     their track did not run, and a verdict is carried only when one was
 *     reached, so an example that reached into either section before reading
 *     `outcome` would teach a caller to raise a `TypeError` on an ordinary
 *     reply, or to read "not settled by rules" as a silent allow. The branches
 *     are asserted to come first, by index, not merely to exist.
 *
 *     The `case_decision_v1` arm is asserted too, and asserted to stay small:
 *     nothing writes v1 any more, but a receipt written before the redesign is
 *     replayed as what it was written as, and an integrator holding old
 *     idempotency keys is owed the branch rather than a surprise.
 *
 * The project is addressed by its **key** everywhere. The UUID is trace
 * identity and never a path segment, so a snippet containing one is a defect
 * even if the request would still work.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type {
  ExternalCaseDecisionReceiptFields,
  ExternalCaseDecisionReceiptV1Fields,
} from "./api";
import {
  apiBaseHost,
  buildApiDocsLinks,
  buildCurlSnippet,
  buildPythonSnippet,
  buildRawHttpReceiptSnippet,
  buildRawHttpRequestSnippet,
  caseEndpointPath,
  caseEndpointUrl,
  isUsableApiBase,
  normaliseApiBase,
  POLICY_SUBSCRIPTION_KEY_ENV,
  RECEIPT_SCHEMA_V1,
  RECEIPT_SCHEMA_V2,
  SUBSCRIPTION_KEY_HEADER,
  type ConsumeTarget,
} from "./consumeSnippets";

const TARGET: ConsumeTarget = { apiBase: "https://policy.example.com", projectKey: "ACME-HR-2024" };
const PROJECT_UUID = "7c9e6679-7425-40de-944b-e07fc1f90ae7";
const SESSION_TOKEN = "eyJhbGciOiJIUzI1NiJ9.a-real-looking-session-token.signature";

/** Every snippet the drawer can put on a clipboard. */
function allSnippets(target: ConsumeTarget = TARGET): Record<string, string> {
  return {
    curl: buildCurlSnippet(target),
    python: buildPythonSnippet(target),
    http: buildRawHttpRequestSnippet(target),
    receipt: buildRawHttpReceiptSnippet(target),
  };
}

describe("no snippet can carry the signed-in session", () => {
  beforeEach(() => {
    sessionStorage.setItem(
      "policy-platform.session",
      JSON.stringify({
        accessToken: SESSION_TOKEN,
        expiresAt: new Date(Date.now() + 3_600_000).toISOString(),
        role: "policy_author",
        name: "an author",
      }),
    );
  });

  afterEach(() => {
    sessionStorage.clear();
  });

  it.each(Object.entries(allSnippets()))("%s contains no part of the stored token", (_name, snippet) => {
    expect(snippet).not.toContain(SESSION_TOKEN);
    // The signature segment alone would be just as much of a leak.
    expect(snippet).not.toContain("a-real-looking-session-token");
  });

  it.each(Object.entries(allSnippets()))("%s never names a client credential store", (_name, snippet) => {
    expect(snippet).not.toContain("sessionStorage");
    expect(snippet).not.toContain("localStorage");
    expect(snippet).not.toContain("accessToken");
    expect(snippet).not.toContain("policy-platform.session");
  });

  it.each(Object.entries(allSnippets()))("%s takes its subscription key from the environment instead", (_name, snippet) => {
    expect(snippet).toContain(POLICY_SUBSCRIPTION_KEY_ENV);
  });

  it.each(Object.entries(allSnippets()))(
    "%s sends the key in X-Policy-Subscription-Key and never as a bearer token",
    (_name, snippet) => {
      expect(snippet).toContain(SUBSCRIPTION_KEY_HEADER);
      // The endpoint reads one header. An example that told a reader to send
      // `Authorization: Bearer …` would produce a 401 they cannot diagnose,
      // because the credential they were given is not a token and the header
      // they were told to use is not read.
      expect(snippet).not.toContain("Authorization");
      expect(snippet).not.toContain("Bearer ");
    },
  );

  it.each(Object.entries(allSnippets()))(
    "%s carries a variable reference rather than anything key-shaped",
    (_name, snippet) => {
      // The drawer is shown to a signed-in author inside the product. It has no
      // access to the operator's configured key and must never look as though
      // it does — a snippet containing a plausible literal is one a reader will
      // paste and then wonder why it fails.
      expect(snippet).not.toMatch(/X-Policy-Subscription-Key:\s*[A-Za-z0-9_-]{16,}/);
    },
  );
});

describe("every example addresses the project by its key", () => {
  it.each(Object.entries(allSnippets()))("%s never contains the project UUID", (_name, snippet) => {
    expect(snippet).not.toContain(PROJECT_UUID);
  });

  it("posts to the external case endpoint, keyed by the project key", () => {
    const path = caseEndpointPath(TARGET.projectKey);
    expect(path).toBe("/api/policy-decisions/ACME-HR-2024/case");
    expect(buildCurlSnippet(TARGET)).toContain(`https://policy.example.com${path}`);
    expect(buildRawHttpRequestSnippet(TARGET)).toContain(`POST ${path} HTTP/1.1`);
  });

  it("builds the Python path from the key at runtime rather than hardcoding a UUID", () => {
    const python = buildPythonSnippet(TARGET);
    expect(python).toContain('PROJECT_KEY = "ACME-HR-2024"');
    expect(python).toContain('f"{BASE}/api/policy-decisions/{PROJECT_KEY}/case"');
  });

  it("escapes a key that would otherwise change the shape of the path", () => {
    expect(caseEndpointPath("a key/with slash")).toBe("/api/policy-decisions/a%20key%2Fwith%20slash/case");
  });
});

describe("the Python example reads each track's outcome before its section", () => {
  const python = buildPythonSnippet(TARGET);

  it("teaches the contract every decision is answered as now", () => {
    expect(python).toContain(`receipt["schema_version"] == "${RECEIPT_SCHEMA_V1}"`);
    expect(python).toContain(RECEIPT_SCHEMA_V2);
    // v1 is the replay arm, not the shape a new caller is taught to expect.
    expect(python).toContain("replayed in the shape it was written in");
  });

  it("branches on each track's outcome", () => {
    expect(python).toContain('outcome = receipt["outcome"]');
    expect(python).toContain('if outcome["information"] == "answered":');
    expect(python).toContain('if outcome["verdict"] == "answered":');
  });

  it("never subscripts a section that is null when its track did not run", () => {
    // `information` and `verdict` are null for a track that was not requested
    // and for a receipt where nothing was evaluated. An example that reached
    // into either before reading its outcome would raise a TypeError on a
    // perfectly ordinary reply.
    const informationBranch = python.indexOf('outcome["information"] == "answered"');
    const informationRead = python.indexOf('receipt["information"]["answer"]');
    expect(informationBranch).toBeGreaterThan(-1);
    expect(informationRead).toBeGreaterThan(informationBranch);

    const verdictBranch = python.indexOf('outcome["verdict"] == "answered"');
    const verdictRead = python.indexOf('receipt["verdict"]["decision"]');
    expect(verdictBranch).toBeGreaterThan(-1);
    expect(verdictRead).toBeGreaterThan(verdictBranch);
  });

  it("names the two outcomes that are nobody's refusal", () => {
    expect(python).toContain("not_requested");
    expect(python).toContain("not_evaluated");
  });

  it("reads the facts a case still needs instead of calling it a verdict", () => {
    const missingBranch = python.indexOf('outcome["verdict"] == "missing_required_facts"');
    expect(missingBranch).toBeGreaterThan(-1);
    expect(python).toContain('for fact in receipt["verdict"]["missing_information"]:');
    expect(python).toContain('fact["label"]');
    expect(python).toContain('fact["why_needed"]');
    expect(python).toContain("it is not a verdict");
  });

  it("keeps the v1 replay honest: one status, one verdict, no information track", () => {
    const versionBranch = python.indexOf(`receipt["schema_version"] == "${RECEIPT_SCHEMA_V1}"`);
    const legacyStatus = python.indexOf('receipt["decision_status"] == "answered"');
    const legacyVerdict = python.indexOf('receipt["decision"]["verdict"]');
    expect(versionBranch).toBeGreaterThan(-1);
    expect(legacyStatus).toBeGreaterThan(versionBranch);
    // Even on the old arm the status is read before the verdict, because a v1
    // receipt only carries one when its status is `answered`.
    expect(legacyVerdict).toBeGreaterThan(legacyStatus);
    // And the v1 arm never invents the two-track fields that receipt never had.
    const legacyArm = python.slice(versionBranch, python.indexOf("outcome = receipt"));
    expect(legacyArm).not.toContain('receipt["information"]');
    expect(legacyArm).not.toContain('receipt["asked"]');
  });

  it("prints the receipt fields a caller has to keep", () => {
    expect(python).toContain('receipt["decision_id"]');
    expect(python).toContain('receipt["verdict"]["explanation"]');
    expect(python).toContain('receipt["citations"]');
    expect(python).toContain('receipt["receipt_url"]');
  });

  it("shows which track cited each rule", () => {
    expect(python).toContain('citation["serves"]');
    expect(python).toContain("appears once and carries both tags");
  });

  it("reads only keys the declared receipt contract carries", () => {
    // The interface in `api.ts` is the promise this example makes. A fixture
    // that satisfies it proves every key the snippet subscripts is one the
    // server documents, so an example cannot quietly start reading a field that
    // is not there.
    const v2: ExternalCaseDecisionReceiptFields = {
      schema_version: RECEIPT_SCHEMA_V2,
      decision_id: "0f1a3c5e-7b9d-4f21-8a63-5c4e2b7d9f08",
      correlation_id: "6f1c9d2e-1b7a-4a55-9a4c-2d3f5b8e1c04",
      asked: { information_requested: true, verdict_requested: true },
      outcome: { information: "answered", verdict: "missing_required_facts" },
      information: { status: "answered", answered: true, answer: "What the policies state.", explanation: null },
      verdict: {
        status: "missing_required_facts",
        reached: false,
        decision: "",
        explanation: "The case cannot be decided yet.",
        missing_information: [
          { fact: "hours_worked", label: "Hours worked", why_needed: "The cap is weekly.", required_by_rule_ids: ["r-1"] },
        ],
      },
      citations: [{ rule_id: "r-1", serves: ["information", "verdict"] }],
      decision_hash: "sha256:…",
      receipt_url: "https://policy.example.com/api/policy-decisions/0f1a3c5e-7b9d-4f21-8a63-5c4e2b7d9f08",
    };
    const v1: ExternalCaseDecisionReceiptV1Fields = {
      schema_version: RECEIPT_SCHEMA_V1,
      decision_id: v2.decision_id,
      decision_status: "answered",
      decision: { status: "answered", verdict: "compliant", explanation: "Because the rule allows it." },
    };

    // Every top-level key the snippet subscripts, on the arm that carries it.
    for (const key of ["decision_id", "schema_version", "asked", "outcome", "information", "verdict", "citations", "receipt_url"]) {
      expect(python).toContain(`receipt["${key}"]`);
      expect(v2).toHaveProperty(key);
    }
    for (const key of ["decision_status", "decision"]) {
      expect(python).toContain(`receipt["${key}"]`);
      expect(v1).toHaveProperty(key);
    }
    // Only a reached verdict carries a determination, and the fixture that
    // cannot reach one leaves it empty rather than saying "not compliant".
    expect(v2.verdict?.reached).toBe(false);
    expect(v2.verdict?.decision).toBe("");
  });

  it("teaches none of the v1 receipt shape on the current arm", () => {
    const currentArm = python.slice(python.indexOf("outcome = receipt"));
    expect(currentArm).not.toContain("decision_status");
    expect(currentArm).not.toContain('receipt["decision"]');
  });
});

describe("the request body and its headers are what the API documents", () => {
  it.each(Object.entries({ curl: buildCurlSnippet(TARGET), python: buildPythonSnippet(TARGET), http: buildRawHttpRequestSnippet(TARGET) }))(
    "%s sends scenario, reasoning effort and a caller label",
    (_name, snippet) => {
      expect(snippet).toContain("scenario");
      expect(snippet).toContain("reasoning_effort");
      expect(snippet).toContain("calling_system_identity");
    },
  );

  it.each(Object.entries({ curl: buildCurlSnippet(TARGET), python: buildPythonSnippet(TARGET), http: buildRawHttpRequestSnippet(TARGET) }))(
    "%s offers additional_instructions as an optional field",
    (_name, snippet) => {
      expect(snippet).toContain("additional_instructions");
    },
  );

  it("carries correlation and idempotency as headers, never as body keys", () => {
    const http = buildRawHttpRequestSnippet(TARGET);
    const [head, body] = http.split("\n\n");
    expect(head).toContain("X-Correlation-Id:");
    expect(head).toContain("Idempotency-Key:");
    expect(body).not.toContain("correlation_id");
    expect(body).not.toContain("idempotency");
    expect(JSON.parse(body)).toEqual({
      scenario: "Describe the situation you want decided.",
      reasoning_effort: "medium",
      calling_system_identity: "my-service",
      additional_instructions: "Explain the approval path first.",
    });
  });

  it("shows the read-back that verifies a stored receipt", () => {
    const receipt = buildRawHttpReceiptSnippet(TARGET);
    expect(receipt).toMatch(/^GET \/api\/policy-decisions\/[0-9a-f-]{36} HTTP\/1\.1$/m);
    expect(receipt).toContain("Host: policy.example.com");
  });
});

describe("the API base drives every example", () => {
  it("regenerates each snippet from an edited base", () => {
    const edited = { ...TARGET, apiBase: "https://x.test" };
    expect(buildCurlSnippet(edited)).toContain("https://x.test/api/policy-decisions/ACME-HR-2024/case");
    expect(buildPythonSnippet(edited)).toContain('BASE = "https://x.test"');
    expect(buildRawHttpRequestSnippet(edited)).toContain("Host: x.test");
    expect(buildRawHttpReceiptSnippet(edited)).toContain("Host: x.test");
    expect(buildApiDocsLinks(edited.apiBase).map((l) => l.href)).toEqual([
      "https://x.test/docs",
      "https://x.test/redoc",
      "https://x.test/openapi.json",
    ]);
  });

  it("strips trailing slashes so a base is never doubled", () => {
    expect(normaliseApiBase("  https://x.test///  ")).toBe("https://x.test");
    expect(caseEndpointUrl({ apiBase: "https://x.test/", projectKey: "k" })).toBe(
      "https://x.test/api/policy-decisions/k/case",
    );
  });

  it("still renders an example for a base that is not a URL", () => {
    // A reader who typed a placeholder host is telling us what their
    // environment looks like. Withholding the example would be the drawer
    // refusing its one job.
    const placeholder = { apiBase: "policy.internal", projectKey: "k" };
    expect(isUsableApiBase(placeholder.apiBase)).toBe(false);
    expect(buildCurlSnippet(placeholder)).toContain("policy.internal/api/policy-decisions/k/case");
    expect(apiBaseHost("policy.internal")).toBe("policy.internal");
  });

  it("recognises only absolute http(s) bases as usable", () => {
    expect(isUsableApiBase("https://policy.example.com")).toBe(true);
    expect(isUsableApiBase("http://localhost:8010")).toBe(true);
    expect(isUsableApiBase("")).toBe(false);
    expect(isUsableApiBase("   ")).toBe(false);
    expect(isUsableApiBase("javascript:alert(1)")).toBe(false);
  });
});

describe("the docs register points at the server the snippets call", () => {
  it("offers exactly Swagger, ReDoc and the schema", () => {
    expect(buildApiDocsLinks(TARGET.apiBase).map((l) => l.id)).toEqual(["swagger", "redoc", "openapi"]);
  });

  it("claims no SDK or connector in any caption", () => {
    const words = buildApiDocsLinks(TARGET.apiBase)
      .map((l) => `${l.title} ${l.caption}`)
      .join(" ")
      .toLowerCase();
    expect(words).not.toContain("sdk");
    expect(words).not.toContain("connector");
  });
});
