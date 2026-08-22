import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { render } from "../testing/renderWithActor";
import { DocumentsPage } from "./DocumentsPage";

/**
 * Why this file exists.
 *
 * The upload endpoint returns `content_already_present`: the other registrations
 * that already hold the exact bytes just uploaded, under a different title or
 * owner. The register's dedup is project-scoped, so a second registration is
 * legitimate — an archived snapshot, a re-parse, one source serving two
 * projects — and the upload proceeds. But the server computed this list on every
 * upload and NOTHING in the web tree read it, so a reviewer who uploaded a
 * document the register already held under another name saw a plain green
 * success identical to genuinely new content. That is the §4.1 pattern this
 * repository logs most — a capability that works and reaches nobody — and it is
 * the constraint 5 gap: "this is new content" and "this is content you already
 * hold under another name" are different facts and must read differently.
 *
 * Three states must read differently (constraint 5):
 *   1. success, content new         -> success alert, NO "already registered" note
 *   2. success, already held        -> success alert + an info note naming the copies
 *   3. refused (identical re-upload) -> the 409 error, and NO info note
 *
 * THE DISCRIMINATING NEGATIVE. The load-bearing assertion here is that state 1
 * does NOT render the note: `content_already_present: []` is a positive "checked,
 * this is new" answer, and a build that always showed the note would still
 * satisfy a test that only proved the note appears. So the []-case asserts the
 * note is absent, and would fail on such a build.
 *
 * THE UNTITLED CASE. The live register holds a real document with an empty
 * heading (it predates the required-title enforcement in 0ffd06d). A blank title
 * must read as an explicit "Untitled document", not as an empty gap that looks
 * like a rendering fault — constraint 5 on a field rather than a state.
 */

const UPLOAD_URL = "/api/documents/upload";
const TITLE_PLACEHOLDER = "Workplace Hardware Provisioning Policy";
const OWNER_PLACEHOLDER = "it-team";

type UploadResponse = { ok: boolean; status: number; body: unknown };

// Each test sets this before clicking Upload. Default: a clean, new-content 200.
let uploadResponse: UploadResponse;

function jsonResponse(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as unknown as Response;
}

function attachFile() {
  const input = document.querySelector('input[type="file"]') as HTMLInputElement;
  expect(input, "the upload control renders no file input").not.toBeNull();
  const file = new File(["x".repeat(64)], "handbook.docx", {
    type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  });
  fireEvent.change(input, { target: { files: [file] } });
}

function setField(placeholder: string, value: string) {
  fireEvent.change(screen.getByPlaceholderText(placeholder), { target: { value } });
}

/** A valid upload: required Title + Owner + file, so the field guards pass and
 *  the request actually leaves — these tests are about what the response says. */
async function validUpload() {
  attachFile();
  setField(TITLE_PLACEHOLDER, "New Handbook");
  setField(OWNER_PLACEHOLDER, "it-team");
  const button = await screen.findByRole("button", { name: /^Upload$/ });
  await act(async () => {
    fireEvent.click(button);
  });
}

/** Text of the blue "already registered" note, or "" when it is not rendered.
 *  Scoped to the info alert so it never picks up the green success line (which
 *  also carries "version 1"). */
function infoNote(): string {
  return document.querySelector(".ant-alert-info")?.textContent ?? "";
}

function successLine(): string {
  return document.querySelector(".ant-alert-success")?.textContent ?? "";
}

function errorLine(): string {
  return document.querySelector(".ant-alert-error")?.textContent ?? "";
}

beforeEach(() => {
  uploadResponse = { ok: true, status: 200, body: { version_number: 1, content_already_present: [] } };
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))
  );
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  );
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes(UPLOAD_URL)) {
        return {
          ok: uploadResponse.ok,
          status: uploadResponse.status,
          statusText: "",
          json: async () => uploadResponse.body,
        } as unknown as Response;
      }
      return jsonResponse([]);
    })
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("a second registration of already-held content is surfaced, not silent", () => {
  it("state 1: new content shows a plain success and NO already-registered note", async () => {
    render(<DocumentsPage />);
    await validUpload();

    // The upload succeeded...
    await waitFor(() => expect(successLine()).toMatch(/uploaded/i));
    // ...and the note is absent. [] is "checked, this is new", not the note with
    // an empty list, and not "unknown". This is the discriminating negative: a
    // build that always renders the note fails here.
    expect(infoNote()).toBe("");
  });

  it("state 2: content already held elsewhere is flagged and every copy is named", async () => {
    uploadResponse = {
      ok: true,
      status: 200,
      body: {
        version_number: 1,
        content_already_present: [
          {
            document_id: "620b45f0",
            title: "HR Special Leave Policy",
            owner: "hr-team",
            document_version_id: "c8505ab8",
            version_number: 1,
          },
        ],
      },
    };
    render(<DocumentsPage />);
    await validUpload();

    const note = await waitFor(() => {
      const text = infoNote();
      expect(text).not.toBe("");
      return text;
    });
    // Names the copy — title AND owner, so a compliance officer can tell which
    // is which (constraint 11: not reduced to "held under 1 other name").
    expect(note).toContain("HR Special Leave Policy");
    expect(note).toContain("hr-team");
    // The success line still stands — the upload did succeed.
    expect(successLine()).toMatch(/uploaded/i);
  });

  it("state 2 is an info note, not a warning or an error — a second registration is legitimate", async () => {
    uploadResponse = {
      ok: true,
      status: 200,
      body: {
        version_number: 1,
        content_already_present: [
          { document_id: "d1", title: "AIS Employee Handbook", owner: "Policy Team", document_version_id: "v1", version_number: 1 },
        ],
      },
    };
    render(<DocumentsPage />);
    await validUpload();

    await waitFor(() => expect(infoNote()).not.toBe(""));
    // The note is deliberately informational. Rendering it as a warning or error
    // would scold the user for a legitimate act.
    expect(document.querySelector(".ant-alert-info")).not.toBeNull();
    expect(document.querySelector(".ant-alert-warning")).toBeNull();
    // The only error class present must not be the upload note; the upload was a
    // clean 200 here, so there is no error alert at all.
    expect(document.querySelector(".ant-alert-error")).toBeNull();
  });

  it("untitled copy: a blank title reads as 'Untitled document', never as an empty gap", async () => {
    uploadResponse = {
      ok: true,
      status: 200,
      body: {
        version_number: 1,
        content_already_present: [
          { document_id: "620b45f0", title: "HR Special Leave Policy", owner: "hr-team", document_version_id: "a", version_number: 1 },
          // The real untitled document in the live register.
          { document_id: "19effadc", title: "", owner: "validation-probe", document_version_id: "b", version_number: 1 },
        ],
      },
    };
    render(<DocumentsPage />);
    await validUpload();

    const note = await waitFor(() => {
      const text = infoNote();
      expect(text).not.toBe("");
      return text;
    });
    // The blank-titled copy is identifiable, by an explicit token and its owner.
    expect(note).toContain("Untitled document");
    expect(note).toContain("validation-probe");
    // Discriminating: a build that did not handle the blank would render
    // " — owned by validation-probe …" with nothing before the dash, so this
    // exact line (token first) would not be a substring.
    expect(note).toContain("Untitled document — owned by validation-probe (version 1)");
  });

  it("state 3: an identical re-upload is refused, and shows the error — not the info note", async () => {
    uploadResponse = { ok: false, status: 409, body: { detail: "identical document content already uploaded" } };
    render(<DocumentsPage />);
    await validUpload();

    await waitFor(() => expect(errorLine()).toMatch(/identical document content already uploaded/i));
    // The refusal is its own state: no success line, and crucially no info note
    // (which would imply the upload was accepted alongside other copies).
    expect(infoNote()).toBe("");
    expect(successLine()).toBe("");
  });
});
