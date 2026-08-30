/** "Call from your app" — how to put a case to this project from somewhere else.
 *
 * The job is narrow and worth stating, because the temptation is to widen it:
 * turn "this project is governed" into "my service can ask it a question",
 * without a human copying a UUID into a URL by hand.
 *
 * What it does *not* do is the load-bearing half of the design. It does not run
 * a request — `Test a Case` does that, and is untouched. It does not manage or
 * issue credentials. And it never reads, renders or copies the signed-in
 * session credential: every example takes its key from the environment variable
 * `POLICY_SUBSCRIPTION_KEY`. The snippets are built by pure functions in
 * `consumeSnippets.ts` that have no way to reach a session, so this is a
 * property of the code rather than a promise in a comment.
 *
 * The identity register is ordered for a machine-path author rather than a
 * human browser: the key first, because it is what goes in a URL; the UUID
 * third, marked as trace identity so nobody pastes it into a path; the display
 * name last and without a copy control, because nothing downstream should ever
 * be keyed on it.
 */

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Alert, Button, Drawer, Input, Tabs, Tooltip, Typography } from "antd";
import {
  ApiOutlined,
  CheckOutlined,
  CopyOutlined,
  DownloadOutlined,
  ExportOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import {
  api,
  CONFIGURED_API_BASE_URL,
  PolicyPlatformApiError,
  type ApprovedPolicyVersion,
  type PolicySet,
} from "../api";
import {
  buildApiDocsLinks,
  buildCurlSnippet,
  buildPythonSnippet,
  buildRawHttpReceiptSnippet,
  buildRawHttpRequestSnippet,
  caseEndpointPath,
  isUsableApiBase,
  normaliseApiBase,
  type ConsumeTarget,
} from "../consumeSnippets";
import "./consumeProject.css";

const { Paragraph, Text } = Typography;

/** What is known about the project's published version, as four honest states.
 *
 *  "Not loaded yet" and "there is none" are different facts and are never
 *  collapsed: one is a spinner, the other is a warning that a request sent
 *  today would be refused. */
type VersionState =
  | { kind: "loading" }
  | { kind: "ready"; version: ApprovedPolicyVersion }
  | { kind: "none" }
  | { kind: "error"; detail: string };

interface ConsumeProjectDrawerProps {
  policySet: PolicySet;
  open: boolean;
  onClose: () => void;
}

// ---------------------------------------------------------------------------
// Copy control
// ---------------------------------------------------------------------------

interface CopyControlProps {
  /** What is being copied, in words. Used in the label and the announcement. */
  what: string;
  text: string;
  testId: string;
  onAnnounce: (message: string) => void;
  /** Icon-only inside a register row; labelled beside a code block. */
  compact?: boolean;
}

/**
 * Copy, with the outcome stated rather than implied.
 *
 * The icon swap follows the JSON viewer's idiom so the two read as one control,
 * but two things are added deliberately. The result is announced through a live
 * region, because an icon changing shape is invisible to a screen reader. And a
 * refusal is *said*: a browser can block `writeText` outright, and the JSON
 * viewer's silent revert leaves a user pressing a button that appears to do
 * nothing. The block is selectable text, so the manual route it names always
 * works.
 */
function CopyControl({ what, text, testId, onAnnounce, compact = false }: CopyControlProps) {
  const [phase, setPhase] = useState<"idle" | "copied" | "failed">("idle");
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const label = `Copy ${what}`;

  const copy = async () => {
    window.clearTimeout(timer.current);
    try {
      await navigator.clipboard.writeText(text);
      setPhase("copied");
      onAnnounce(`Copied ${what} to the clipboard.`);
      timer.current = window.setTimeout(() => setPhase("idle"), 1600);
    } catch {
      setPhase("failed");
      onAnnounce("Copy was blocked by the browser.");
    }
  };

  return (
    <>
      <Button
        size="small"
        type={compact ? "text" : "default"}
        icon={phase === "copied" ? <CheckOutlined /> : <CopyOutlined />}
        onClick={copy}
        data-testid={testId}
        title={label}
        aria-label={label}
      >
        {compact ? null : phase === "copied" ? "Copied" : "Copy"}
      </Button>
      {phase === "failed" && (
        <span className="consume-copy-error" data-testid="consume-copy-error">
          Copy was blocked by the browser. Select the text and copy manually.
        </span>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Register row
// ---------------------------------------------------------------------------

interface RegisterRowProps {
  label: string;
  /** The value as text, used for the row's accessible name and for copying. */
  value: string;
  testId: string;
  /** What this string is for. Rendered as a reference pill and read out as part
   *  of the row, so the marker is never a visual-only cue. */
  marker?: string;
  mono?: boolean;
  muted?: boolean;
  /** Omitted where copying would be wrong — the display name, for one. */
  copy?: { what: string; testId: string };
  onAnnounce: (message: string) => void;
  /** Replaces the value node while it is still resolving. */
  children?: ReactNode;
}

function RegisterRow({
  label,
  value,
  testId,
  marker,
  mono = false,
  muted = false,
  copy,
  onAnnounce,
  children,
}: RegisterRowProps) {
  const valueClass = `consume-row__value${mono ? " consume-row__value--mono" : ""}${
    muted ? " consume-row__value--muted" : ""
  }`;
  return (
    <div
      className="consume-row"
      role="group"
      aria-label={[label, value, marker].filter(Boolean).join(", ")}
      data-testid={`consume-row-${testId}`}
    >
      <span className="consume-row__label">{label}</span>
      <span className={valueClass} data-testid={`consume-${testId}-value`}>
        {children ?? value}
      </span>
      {marker && (
        <span className="consume-marker" data-testid={`consume-${testId}-marker`}>
          {marker}
        </span>
      )}
      {copy && (
        <span className="consume-row__copy">
          <CopyControl what={copy.what} text={value} testId={copy.testId} onAnnounce={onAnnounce} compact />
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Code region
// ---------------------------------------------------------------------------

interface SnippetSectionProps {
  id: "curl" | "python" | "http" | "http-receipt";
  language: string;
  projectKey: string;
  caption: string;
  code: string;
  downloadName: string;
  /** Up to three lines saying what the example does. */
  bullets: string[];
  /** Rendered when the project has no published version: the request is right,
   *  it simply has nothing to decide against today. */
  annotation?: string;
  onAnnounce: (message: string) => void;
}

function SnippetSection({
  id,
  language,
  projectKey,
  caption,
  code,
  downloadName,
  bullets,
  annotation,
  onAnnounce,
}: SnippetSectionProps) {
  const lines = code.split("\n");

  const download = () => {
    const url = URL.createObjectURL(new Blob([code], { type: "text/plain" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = downloadName;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="consume-section">
      <Text type="secondary" className="consume-code-caption">
        {caption}
      </Text>
      {annotation && (
        <span className="consume-code-annotation" data-testid={`consume-annotation-${id}`}>
          {annotation}
        </span>
      )}
      {/* Focusable so the region can be reached and scrolled from the keyboard;
          lines wrap rather than scroll sideways, per the Code Region rule. */}
      <pre
        className="json-view-code consume-code"
        tabIndex={0}
        aria-label={`${language} example for project ${projectKey}`}
        data-testid={`consume-snippet-${id}`}
      >
        <code>
          {lines.map((line, index) => (
            <div className="json-line" key={index}>
              <span className="json-line-no" aria-hidden="true">
                {index + 1}
              </span>
              <span className="json-line-text">{line}</span>
            </div>
          ))}
        </code>
      </pre>
      <div className="consume-controls">
        <CopyControl
          what={`the ${language} example`}
          text={code}
          testId={`consume-copy-${id}`}
          onAnnounce={onAnnounce}
        />
        <Button size="small" icon={<DownloadOutlined />} onClick={download} title={`Download the ${language} example`}>
          Download
        </Button>
      </div>
      <ul className="consume-bullets">
        {bullets.map((bullet) => (
          <li key={bullet}>{bullet}</li>
        ))}
      </ul>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Drawer
// ---------------------------------------------------------------------------

export function ConsumeProjectDrawer({ policySet, open, onClose }: ConsumeProjectDrawerProps) {
  const [apiBase, setApiBase] = useState(CONFIGURED_API_BASE_URL);
  const [version, setVersion] = useState<VersionState>({ kind: "loading" });
  const [announcement, setAnnouncement] = useState("");
  const titleRef = useRef<HTMLSpanElement>(null);

  const announce = useCallback((message: string) => setAnnouncement(message), []);

  // A different project is a different drawer: the edited base belongs to the
  // project it was typed for and must not follow the reader to the next one.
  useEffect(() => {
    setApiBase(CONFIGURED_API_BASE_URL);
  }, [policySet.key]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setVersion({ kind: "loading" });
    api
      .getActiveVersion(policySet.key)
      .then((found) => {
        if (cancelled) return;
        setVersion(found ? { kind: "ready", version: found } : { kind: "none" });
      })
      .catch((caught: unknown) => {
        if (cancelled) return;
        setVersion({
          kind: "error",
          detail: caught instanceof PolicyPlatformApiError ? caught.detail : String(caught),
        });
      });
    return () => {
      cancelled = true;
    };
  }, [open, policySet.key]);

  const target: ConsumeTarget = { apiBase, projectKey: policySet.key };
  const baseUsable = isUsableApiBase(apiBase);
  const docsLinks = buildApiDocsLinks(apiBase);
  const noVersion = version.kind === "none";
  const annotation = noVersion
    ? "This request is correct, but it will return 409 until a version is published."
    : undefined;

  const versionValue =
    version.kind === "ready"
      ? `v${version.version.version_number} · ${version.version.id}`
      : version.kind === "none"
        ? "No published version"
        : version.kind === "error"
          ? "Could not be read"
          : "Resolving…";

  const identityTab = (
    <div className="consume-section">
      <div className="consume-register">
        <RegisterRow
          label="Project key"
          value={policySet.key}
          testId="key"
          marker="Use this in API paths"
          mono
          copy={{ what: `project key ${policySet.key}`, testId: "consume-copy-key" }}
          onAnnounce={announce}
        />
        <RegisterRow
          label="Active version"
          value={versionValue}
          testId="version"
          marker="Resolved for you when you omit policy_version_id"
          mono
          copy={
            version.kind === "ready"
              ? { what: "active version id", testId: "consume-copy-version" }
              : undefined
          }
          onAnnounce={announce}
        >
          {version.kind === "loading" ? (
            <span role="status" data-testid="consume-version-loading">
              Resolving active version…
            </span>
          ) : undefined}
        </RegisterRow>
        <RegisterRow
          label="Project id"
          value={policySet.id}
          testId="uuid"
          marker="Trace identity — not a URL segment"
          mono
          muted
          copy={{ what: "project id", testId: "consume-copy-uuid" }}
          onAnnounce={announce}
        />
        {/* No copy control, on purpose: nothing downstream should be keyed on a
            name a person is free to rewrite. */}
        <RegisterRow label="Display name" value={policySet.name} testId="name" marker="Display only" onAnnounce={announce} />
        <RegisterRow
          label="API base"
          value={normaliseApiBase(apiBase)}
          testId="base"
          mono
          muted
          copy={{ what: "API base", testId: "consume-copy-base" }}
          onAnnounce={announce}
        />
      </div>
      <Text type="secondary" className="consume-note">
        Paths use the key. The UUID is for tracing a decision back to this project in support and audit
        conversations; it is never a path segment.
      </Text>
    </div>
  );

  const tabs = [
    { key: "identity", testId: "consume-tab-identity", label: "Project identity", children: identityTab },
    {
      key: "curl",
      testId: "consume-tab-curl",
      label: "cURL",
      children: (
        <SnippetSection
          id="curl"
          language="cURL"
          projectKey={policySet.key}
          caption="One request from a terminal. Nothing is installed and no credential is stored."
          code={buildCurlSnippet(target)}
          downloadName={`${policySet.key}-case.sh`}
          annotation={annotation}
          bullets={[
            `Posts one case to ${caseEndpointPath(policySet.key)}.`,
            "Takes the subscription key from POLICY_SUBSCRIPTION_KEY in your environment and sends it in X-Policy-Subscription-Key.",
            "Sends correlation and idempotency as headers, not as body fields.",
          ]}
          onAnnounce={announce}
        />
      ),
    },
    {
      key: "python",
      testId: "consume-tab-python",
      label: "Python",
      children: (
        <SnippetSection
          id="python"
          language="Python"
          projectKey={policySet.key}
          caption="The same call, and the way a receipt has to be read: each track's outcome first, a verdict only if one was reached."
          code={buildPythonSnippet(target)}
          downloadName={`${policySet.key}_case.py`}
          annotation={annotation}
          bullets={[
            "Uses requests; there is no SDK for this product and none is implied.",
            "Reads outcome.information and outcome.verdict before either section: both are null when their track was not asked for, or when nothing was evaluated.",
            "Prints the facts a case still needs when a verdict was asked for but could not be reached.",
            "Prints the decision id, citations with the track that cited each, and the receipt URL.",
          ]}
          onAnnounce={announce}
        />
      ),
    },
    {
      key: "http",
      testId: "consume-tab-http",
      label: "Raw HTTP",
      children: (
        <div className="consume-section">
          <SnippetSection
            id="http"
            language="HTTP"
            projectKey={policySet.key}
            caption="The request on the wire, for a client written in any language."
            code={buildRawHttpRequestSnippet(target)}
            downloadName={`${policySet.key}-case.http`}
            annotation={annotation}
            bullets={[
              "Send your own correlation id; the ids shown are examples.",
              "Idempotency-Key is optional and makes a retry safe.",
              "Reusing a key with a changed body is refused with 409, not replayed.",
            ]}
            onAnnounce={announce}
          />
          <SnippetSection
            id="http-receipt"
            language="HTTP receipt"
            projectKey={policySet.key}
            caption="Read a stored decision back by id to verify the hash you were given."
            code={buildRawHttpReceiptSnippet(target)}
            downloadName={`${policySet.key}-receipt.http`}
            bullets={[
              "Uses the decision_id returned by the POST above.",
              "Replays the stored receipt in the shape it was written in; schema_version names which.",
              "Readable by the caller that made it, and by a policy author or admin.",
            ]}
            onAnnounce={announce}
          />
        </div>
      ),
    },
    {
      key: "docs",
      testId: "consume-tab-docs",
      label: "API docs",
      children: (
        <div className="consume-section">
          <div className="consume-register">
            {docsLinks.map((link) => (
              <div className="consume-docs-row" key={link.id}>
                <span className="consume-docs-row__text">
                  {baseUsable ? (
                    <a
                      className="consume-docs-row__link"
                      href={link.href}
                      target="_blank"
                      rel="noopener noreferrer"
                      data-testid={`consume-docs-${link.id}`}
                    >
                      {link.title} <ExportOutlined aria-hidden="true" />
                    </a>
                  ) : (
                    <Tooltip title="Set a valid API base first">
                      <span
                        className="consume-docs-row__link"
                        aria-disabled="true"
                        data-testid={`consume-docs-${link.id}`}
                      >
                        {link.title}
                      </span>
                    </Tooltip>
                  )}
                  <span className="consume-docs-row__caption">{link.caption}</span>
                  <span className="consume-docs-row__url">{link.href}</span>
                </span>
              </div>
            ))}
          </div>
          <Text type="secondary" className="consume-note">
            Served by the API itself, so they always describe the server at the base URL above. This product has no
            client SDK and no native connector; these three documents and the examples above are the whole contract.
          </Text>
        </div>
      ),
    },
  ];

  return (
    <Drawer
      placement="right"
      size="min(880px, 100vw)"
      open={open}
      onClose={onClose}
      destroyOnHidden
      afterOpenChange={(opened) => {
        // Focus the title, never a Copy button: landing focus on a clipboard
        // action is one stray keypress away from a copy nobody asked for.
        if (opened) titleRef.current?.focus();
      }}
      title={
        <span className="consume-title" tabIndex={-1} ref={titleRef} data-testid="consume-drawer-title">
          Call <code title={policySet.key}>{policySet.key}</code> from your app
        </span>
      }
    >
      <div className="consume-drawer">
        <Paragraph type="secondary" className="consume-purpose" style={{ marginBottom: 0 }}>
          Everything another system needs to put a case to this project&apos;s published policies: the stable key, the
          exact request, and the API&apos;s own documentation. Nothing here sends a request.
        </Paragraph>

        <div className="consume-env">
          <label className="consume-env__field">
            <span className="consume-eyebrow">API base</span>
            <Input
              size="small"
              className="consume-base-input"
              value={apiBase}
              status={baseUsable ? undefined : "warning"}
              onChange={(event) => setApiBase(event.target.value)}
              data-testid="consume-api-base"
              aria-label="API base used in the examples below"
              spellCheck={false}
            />
          </label>
          {apiBase !== CONFIGURED_API_BASE_URL && (
            <Button
              size="small"
              icon={<ReloadOutlined />}
              onClick={() => setApiBase(CONFIGURED_API_BASE_URL)}
              data-testid="consume-api-base-reset"
            >
              Reset to configured base
            </Button>
          )}
          {!baseUsable && (
            <span className="consume-env__note" data-testid="consume-api-base-note">
              Snippets will show this value as written.
            </span>
          )}
        </div>

        {version.kind === "none" && (
          <Alert
            type="warning"
            showIcon
            data-testid="consume-no-version"
            title="This project has no published version, so there is nothing to decide against yet."
            description="A case sent now would be refused by the API. Publish a version first. The examples below are still correct."
          />
        )}
        {version.kind === "error" && (
          <Alert
            type="error"
            showIcon
            data-testid="consume-version-error"
            title="The active version could not be read."
            description={`${version.detail} The examples below do not depend on it.`}
          />
        )}

        <Tabs
          size="small"
          items={tabs.map((tab) => ({
            key: tab.key,
            label: <span data-testid={tab.testId}>{tab.label}</span>,
            children: tab.children,
            // Every section stays in the document. A snippet that only exists
            // once its tab has been visited cannot be found by anything that
            // reads the page as a whole, including a screen reader's own search.
            forceRender: true,
          }))}
        />

        <span className="consume-sr-status" role="status" aria-live="polite">
          {announcement}
        </span>

        <div className="consume-footer" data-testid="consume-footer-note">
          <ApiOutlined aria-hidden="true" /> Snippets never contain your signed-in session token.
        </div>
      </div>
    </Drawer>
  );
}
