import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { DocumentsPage } from "./DocumentsPage";

/**
 * Why this file exists.
 *
 * Title and Owner are marked required — each Form.Item carries the `*` — but
 * `handleUpload` only ever checked that a file was attached. So an upload with
 * a blank Title was accepted, and the register gained a document with a blank
 * heading. A nameless record in a compliance register is worse than a refused
 * upload: a reviewer scanning the source list sees an unnamed document and
 * cannot tell what it is or whether it matters. This was observed live — two
 * register entries for one source, identical content, one titled and one blank,
 * the blank one the direct product of an empty-Title upload succeeding.
 *
 * These tests pin the enforcement the interface was already promising, and pin
 * it as DISTINCT refusals (constraint 5): "no title", "no owner" and "no file"
 * are different facts and must read differently, not collapse into one
 * sentence. The set-size assertion in the last test keeps holding if a fourth
 * required field is ever added, and fails the moment two refusals merge.
 *
 * The important negative here is `uploadCalls() === 0`: a refusal that still
 * fired the POST would leave the nameless document in the register regardless
 * of what the screen said, so the test asserts the request never left.
 */

const UPLOAD_URL = "/api/documents/upload";
const TITLE_PLACEHOLDER = "Workplace Hardware Provisioning Policy";
const OWNER_PLACEHOLDER = "it-team";

function jsonResponse(body: unknown) {
  return { ok: true, status: 200, json: async () => body } as unknown as Response;
}

let fetchMock: ReturnType<typeof vi.fn>;

/** How many times the upload endpoint was actually called. */
function uploadCalls(): number {
  return fetchMock.mock.calls.filter((c) => String(c[0]).includes(UPLOAD_URL)).length;
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

async function clickUpload() {
  const button = await screen.findByRole("button", { name: /^Upload$/ });
  await act(async () => {
    fireEvent.click(button);
  });
}

/**
 * The sentence shown in the error alert, or "" when none is rendered.
 *
 * The error Alert renders with `role="alert"` on its root (antd sets it for
 * type="error"), and `handleUpload` clears any success message before the
 * guards run, so in a refusal state this role uniquely selects the error
 * sentence. Reading the alert root's textContent (rather than an inner
 * `.ant-alert-message` class) keeps this robust to antd markup changes and
 * matches how the sibling upload suite reads messages.
 */
function refusal(): string {
  const el = document.querySelector('[role="alert"]');
  return el?.textContent ?? "";
}

beforeEach(() => {
  // antd measures the viewport; jsdom provides neither of these.
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
  fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.includes(UPLOAD_URL)) return jsonResponse({ version_number: 1 });
    // The list/policy-set loads the page makes on mount; shape does not matter here.
    return jsonResponse([]);
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("required fields are enforced before the upload is sent", () => {
  it("refuses an upload whose title is blank, and names the field", async () => {
    render(<DocumentsPage />);
    attachFile();
    setField(OWNER_PLACEHOLDER, "hr-team"); // only the title is left blank
    await clickUpload();

    expect(refusal()).toMatch(/title/i);
    expect(uploadCalls()).toBe(0);
  });

  it("treats a whitespace-only title as blank", async () => {
    render(<DocumentsPage />);
    attachFile();
    setField(OWNER_PLACEHOLDER, "hr-team");
    setField(TITLE_PLACEHOLDER, "   ");
    await clickUpload();

    expect(refusal()).toMatch(/title/i);
    expect(uploadCalls()).toBe(0);
  });

  it("refuses a blank owner with its own sentence, not the title's", async () => {
    render(<DocumentsPage />);
    attachFile();
    setField(TITLE_PLACEHOLDER, "Staff Handbook"); // only the owner is left blank
    await clickUpload();

    const message = refusal();
    expect(message).toMatch(/owner/i);
    expect(message).not.toMatch(/title/i);
    expect(uploadCalls()).toBe(0);
  });

  it("gives each missing required field its own refusal (constraint 5)", async () => {
    render(<DocumentsPage />);
    const seen: string[] = [];

    // nothing filled -> the first missing field
    await clickUpload();
    seen.push(refusal());

    setField(TITLE_PLACEHOLDER, "Staff Handbook");
    await clickUpload();
    seen.push(refusal());

    setField(OWNER_PLACEHOLDER, "hr-team");
    await clickUpload();
    seen.push(refusal());

    // Three distinct sentences, one per missing field, and nothing was sent.
    expect(new Set(seen).size).toBe(3);
    expect(seen.some((m) => /title/i.test(m))).toBe(true);
    expect(seen.some((m) => /owner/i.test(m))).toBe(true);
    expect(seen.some((m) => /file/i.test(m))).toBe(true);
    expect(uploadCalls()).toBe(0);
  });

  it("sends the upload once every required field is provided", async () => {
    render(<DocumentsPage />);
    setField(TITLE_PLACEHOLDER, "Staff Handbook");
    setField(OWNER_PLACEHOLDER, "hr-team");
    attachFile();
    await clickUpload();

    await waitFor(() => expect(uploadCalls()).toBe(1));
    // The guard must not silently drop the values the reviewer typed.
    const call = fetchMock.mock.calls.find((c) => String(c[0]).includes(UPLOAD_URL));
    const url = String(call?.[0] ?? "");
    expect(url).toContain("title=Staff+Handbook");
    expect(url).toContain("owner=hr-team");
  });
});
