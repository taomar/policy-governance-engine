import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  Divider,
  Form,
  Input,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  Upload,
} from "antd";
import {
  InboxOutlined,
  PartitionOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import type { UploadFile } from "antd/es/upload/interface";
import { aiApi, api, PolicyPlatformApiError, type ContentAlreadyPresent, type ExtractResult, type PolicySet, type SourceDocument } from "../api";
import { DocumentBodyDrawer } from "./DocumentBodyDrawer";
import { uploadOutcome, uploadWaitState } from "../uploadFeedback";
import { ingestionOutcome } from "../ingestionOutcome";
import ExtractionInsightDrawer from "./ExtractionInsightDrawer";
import ExtractionProgressPanel from "./ExtractionProgressPanel";
import ExtractionRunHistory from "./ExtractionRunHistory";
import { useActor } from "../ActorContext";
import { canAuthor } from "../rbac";

const { Title, Text, Paragraph } = Typography;
const { Dragger } = Upload;

function formatBytes(hash: string): string {
  return hash.slice(0, 12) + "…";
}

/** How a prior registration's title reads in the "already registered" note.
 *
 * The register still holds one document with an empty heading — it predates the
 * required-title enforcement added in 0ffd06d — so a blank title must read as an
 * explicit "Untitled document", a record a reviewer can still place by its
 * owner, never as an empty gap that looks like a rendering fault. That is
 * constraint 5 on a field rather than a state. */
function registrationTitle(entry: ContentAlreadyPresent): string {
  return entry.title.trim() === "" ? "Untitled document" : entry.title;
}

/** The ingestion fields the register reads off each version.
 *
 * Declared here rather than on `DocumentVersion` in `api.ts` only because that
 * file is held by another workstream this session. It is the same shape the
 * endpoint returns and belongs on the shared interface; fold it in when free.
 */
type VersionIngestion = {
  ingestion_status?: string | null;
  ingestion_error?: string | null;
  ingestion_diagnostics?: { code?: string; severity?: string; detail?: string }[] | null;
};

interface DocumentsPageProps {
  onNavigate?: (page: string) => void;
  /** When set, this page is embedded inside a Project Workspace: uploads/list are scoped to
   * this project automatically and the per-extraction target-policy-set picker is hidden
   * (the project is already known). When omitted, this renders as the global "Document Inbox"
   * showing every document across all projects, each with an inline "file into project" control. */
  policySetKey?: string;
  policySetName?: string;
}

export function DocumentsPage({ onNavigate, policySetKey, policySetName }: DocumentsPageProps) {
  const scoped = Boolean(policySetKey);
  // Uploading a document and running extraction are both AUTHOR routes on the
  // server. The surface map already marks this tab read-only for a viewer and
  // the workspace renders a banner saying documents are "uploaded by a Policy
  // Author" — but the banner sat directly above a live dropzone. A declaration
  // no component consumes is not a restriction.
  const { role } = useActor();
  const mayAuthor = canAuthor(role);
  const [documents, setDocuments] = useState<SourceDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [title, setTitle] = useState("");
  const [owner, setOwner] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  // Wall-clock start of the in-flight upload, and a tick that re-renders it.
  // The elapsed number is what distinguishes a slow parse from a hung request,
  // so it has to keep moving on its own rather than only on other state changes.
  const [uploadStartedAt, setUploadStartedAt] = useState<number | null>(null);
  const [uploadElapsedMs, setUploadElapsedMs] = useState(0);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
  const [uploadProblem, setUploadProblem] = useState<string | null>(null);
  const [uploadNotes, setUploadNotes] = useState<string[]>([]);
  // Other registrations of the exact bytes just uploaded, returned by the
  // endpoint. Non-empty means the upload succeeded AND the register already held
  // this source under another name; [] means it was checked and is new. This is
  // a distinct fact from the success line, so it renders as its own note.
  const [uploadCopies, setUploadCopies] = useState<ContentAlreadyPresent[]>([]);

  const [policySets, setPolicySets] = useState<PolicySet[]>([]);
  const [extractOpenFor, setExtractOpenFor] = useState<string | null>(null);
  const [extractTargetKey, setExtractTargetKey] = useState<string>("");
  // The id of the version currently extracting, not a bare boolean: progress is
  // per-document-version, and a boolean would spin the button on every version
  // panel while only one is actually running.
  const [extractingId, setExtractingId] = useState<string | null>(null);
  const [activeExtractionByVersion, setActiveExtractionByVersion] = useState<Record<string, boolean>>({});
  //. Bumped after each run so the history table refetches without the panel
  //. having to know how history is loaded.
  const [runHistoryKey, setRunHistoryKey] = useState(0);
  const [extractResults, setExtractResults] = useState<Record<string, ExtractResult | { error: string }>>({});
  const [assigningId, setAssigningId] = useState<string | null>(null);
  const [bodyViewer, setBodyViewer] = useState<{ versionId: string; docTitle: string; versionLabel: string } | null>(
    null
  );
  const [insightFor, setInsightFor] = useState<{ versionId: string; docTitle: string } | null>(null);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const docs = await api.listDocuments(policySetKey);
      setDocuments(docs);
    } catch (e) {
      setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
    api
      .listPolicySets()
      .then((sets) => {
        setPolicySets(sets);
        if (!scoped && sets.length > 0) setExtractTargetKey(sets[0].key);
      })
      .catch(() => undefined);
    // refresh/scoped intentionally omitted: re-run only when the embedding project changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [policySetKey]);

  useEffect(() => {
    if (uploadStartedAt === null) return;
    // One second is fine: this clock exists to show the request is still open,
    // not to time it precisely.
    const timer = window.setInterval(() => {
      setUploadElapsedMs(Date.now() - uploadStartedAt);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [uploadStartedAt]);

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setUploadMessage(null);
    setUploadProblem(null);
    setUploadNotes([]);
    setUploadCopies([]);
    // Title and Owner are marked required (the `*` on their fields); enforce
    // that promise before sending, or a blank title becomes a nameless document
    // in the register — worse than a refused upload, because a reviewer cannot
    // tell what an unnamed source is. Each missing field gets its own sentence:
    // "no title", "no owner" and "no file" are different facts (constraint 5)
    // and must not collapse into one refusal.
    if (!title.trim()) {
      setError("Enter a title before uploading.");
      return;
    }
    if (!owner.trim()) {
      setError("Enter an owner before uploading.");
      return;
    }
    if (!file) {
      setError("Choose a file to upload.");
      return;
    }
    const uploaded = file;
    setUploading(true);
    setUploadStartedAt(Date.now());
    setUploadElapsedMs(0);
    try {
      const result = await api.uploadDocument(title, owner, uploaded, policySetKey);
      const outcome = uploadOutcome(uploaded.name, result ?? {});
      setUploadMessage(outcome.message);
      setUploadProblem(outcome.problem);
      setUploadNotes(outcome.notes);
      // [] vs non-empty is the whole signal; the endpoint always sends the field
      // on success, and an older server that omits it is treated as "new" rather
      // than claiming a duplicate it never checked for.
      setUploadCopies(Array.isArray(result?.content_already_present) ? result.content_already_present : []);
      setTitle("");
      setOwner("");
      setFile(null);
      await refresh();
    } catch (e) {
      setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setUploading(false);
      setUploadStartedAt(null);
    }
  };

  const handleExtract = async (versionId: string) => {
    const targetKey = scoped ? policySetKey : extractTargetKey;
    if (!targetKey) return;
    setExtractingId(versionId);
    setExtractResults((prev) => {
      const { [versionId]: _drop, ...rest } = prev;
      return rest;
    });
    try {
      const result = await aiApi.extractWithAi(targetKey, versionId);
      setExtractResults((prev) => ({ ...prev, [versionId]: result }));
    } catch (e) {
      const detail = e instanceof PolicyPlatformApiError ? e.detail : String(e);
      setExtractResults((prev) => ({ ...prev, [versionId]: { error: detail } }));
    } finally {
      setExtractingId(null);
      // A finished run is new history, whatever its outcome.
      setRunHistoryKey((k) => k + 1);
    }
  };

  const handleAssign = async (documentId: string, targetKey: string | null) => {
    setAssigningId(documentId);
    setError(null);
    try {
      await api.assignDocumentToProject(documentId, targetKey);
      await refresh();
    } catch (e) {
      setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setAssigningId(null);
    }
  };

  const noteExtractionActivity = useCallback((versionId: string, active: boolean) => {
    setActiveExtractionByVersion((prev) =>
      prev[versionId] === active ? prev : { ...prev, [versionId]: active },
    );
  }, []);

  // Only while a request is actually open and a file is in hand: the panel
  // states facts about that file, so it has nothing to say without one.
  const waitState = uploading && file ? uploadWaitState(file.name, file.size, uploadElapsedMs) : null;

  return (
    <>
      <div>
        <Title level={3} style={{ marginBottom: 4 }}>
          {scoped ? "Documents" : "Document Inbox"}
        </Title>
        <Paragraph type="secondary">
          {scoped ? (
            mayAuthor ? (
              <>
                Source policy documents for this project. Uploading a file under an existing title adds a new version
                of that document — useful for tracking policy revisions (e.g. v3.2 → v3.3) over time. Use{" "}
                <strong>✨ Extract with AI</strong> to turn a document version into draft candidate rules for human
                review.
              </>
            ) : (
              <>
                The source policy documents this project's rules were extracted from. Open any version to read it and
                see how its rules were derived. Uploading and extraction are done by a Policy Author.
              </>
            )
          ) : (
            <>
              Every document uploaded across all projects, in one place. Documents not yet filed into a project are
              marked <Tag style={{ margin: "0 4px" }}>Unassigned</Tag> — use the selector on each card to file them,
              or open a project and upload directly there.
            </>
          )}
        </Paragraph>
      </div>

      {error && <Alert type="error" showIcon title={error} />}
      {uploadMessage && (
        <Alert
          type={uploadProblem ? "warning" : "success"}
          showIcon
          title={uploadMessage}
          description={
            uploadProblem || uploadNotes.length > 0 ? (
              <Space orientation="vertical" size={2}>
                {uploadProblem && <Text>{uploadProblem}</Text>}
                {uploadNotes.map((note, i) => (
                  <Text key={i} type="secondary">
                    {note}
                  </Text>
                ))}
              </Space>
            ) : undefined
          }
        />
      )}
      {uploadCopies.length > 0 && (
        <Alert
          type="info"
          showIcon
          title="This document's contents are already in the register under another name"
          description={
            <Space orientation="vertical" size={2}>
              <Text type="secondary">
                The upload was recorded. A second registration of the same source is legitimate — an archived
                snapshot, a re-parse, or one source filed into two projects — so this is not a problem to fix. It is
                flagged so two registrations of one source are not mistaken for two sources. The same contents are
                already held as:
              </Text>
              {uploadCopies.map((copy) => (
                <Text key={copy.document_version_id}>
                  {registrationTitle(copy)} — owned by {copy.owner} (version {copy.version_number})
                </Text>
              ))}
            </Space>
          }
        />
      )}

      {mayAuthor && (
      <Card title="Upload Document">
        <Form layout="vertical" onSubmitCapture={handleUpload}>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item label="Title" required>
                <Input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Workplace Hardware Provisioning Policy"
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="Owner" required>
                <Input value={owner} onChange={(e) => setOwner(e.target.value)} placeholder="it-team" />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item label="File (PDF or DOCX)" required>
                <Dragger
                  multiple={false}
                  accept=".pdf,.docx,.doc"
                  fileList={file ? ([{ uid: "1", name: file.name, status: "done" } as UploadFile] as UploadFile[]) : []}
                  beforeUpload={(f) => {
                    setFile(f);
                    return false;
                  }}
                  onRemove={() => setFile(null)}
                >
                  <p className="ant-upload-drag-icon">
                    <InboxOutlined />
                  </p>
                  <p className="ant-upload-text">Click or drag a policy document to this area</p>
                  <p className="ant-upload-hint">
                    {scoped
                      ? `Filed automatically into ${policySetName ?? policySetKey}`
                      : "PDF or DOCX up to a reasonable size"}
                  </p>
                </Dragger>
              </Form.Item>
            </Col>
          </Row>
          <Button type="primary" htmlType="submit" loading={uploading} disabled={uploading}>
            {uploading ? "Reading document…" : "Upload"}
          </Button>
          {waitState && (
            <div className="upload-wait" role="status" aria-live="polite">
              <Space orientation="vertical" size={4}>
                <Text strong>
                  {waitState.headline} · {waitState.elapsed} elapsed
                </Text>
                <Text type="secondary">{waitState.activity}</Text>
                <Text type="secondary">{waitState.next}</Text>
              </Space>
            </div>
          )}
        </Form>
      </Card>
      )}
      <section className="documents-register">
        <div className="documents-register__header">
          <Title level={4}>{scoped ? "Documents in this project" : "All documents"}</Title>
          <Text type="secondary">{documents.length} total</Text>
        </div>
        <div className="documents-register__body">
        {loading ? (
          <Text type="secondary">Loading…</Text>
        ) : (
          <Space orientation="vertical" style={{ width: "100%" }} size={10}>
            {documents.map((doc) => (
              <article key={doc.id} className="document-record">
                <div className="document-record__header">
                  <div>
                    <Title level={5}>{doc.title}</Title>
                    <Text type="secondary">Owned by {doc.owner}</Text>
                  </div>
                  <Space>
                    {!scoped &&
                      (doc.policy_set_name ? (
                        <Tag color="blue">{doc.policy_set_name}</Tag>
                      ) : (
                        <Tag>Unassigned</Tag>
                      ))}
                    {!scoped && (
                      <Select
                        size="small"
                        style={{ minWidth: 170 }}
                        placeholder="File into project…"
                        value={doc.policy_set_key ?? undefined}
                        loading={assigningId === doc.id}
                        allowClear
                        onClear={() => handleAssign(doc.id, null)}
                        onChange={(val) => handleAssign(doc.id, val)}
                        options={policySets.map((ps) => ({ value: ps.key, label: ps.name }))}
                      />
                    )}
                  </Space>
                </div>
                <div className="document-record__body">
                <Table
                  size="small"
                  pagination={false}
                  rowKey="id"
                  dataSource={doc.versions}
                  columns={[
                    { title: "Version", dataIndex: "version_number", render: (v) => `v${v}` },
                    { title: "Type", dataIndex: "mime_type" },
                    {
                      title: "Content Hash",
                      dataIndex: "content_hash",
                      render: (h: string) => <code>{formatBytes(h)}</code>,
                    },
                    {
                      title: "Uploaded",
                      dataIndex: "created_at",
                      render: (c: string) => new Date(c).toLocaleString(),
                    },
                    {
                      // A version that did not read cleanly must not look like
                      // one that did. This sits in the register itself, beside
                      // the hash and the date, because the reviewer choosing
                      // which document to trust is looking at this list.
                      title: "Ingestion",
                      key: "ingestion",
                      render: (_: unknown, v) => {
                        const ing = v as unknown as VersionIngestion;
                        const outcome = ingestionOutcome(ing.ingestion_status);
                        const details = [
                          ...(ing.ingestion_error ? [ing.ingestion_error] : []),
                          ...(ing.ingestion_diagnostics ?? []).map((d) =>
                            [d.code, d.detail].filter(Boolean).join(": "),
                          ),
                        ].filter(Boolean);
                        return (
                          <Tooltip
                            title={
                              <span>
                                {outcome.hint}
                                {details.length > 0 && (
                                  <>
                                    <br />
                                    <br />
                                    {details.map((d, i) => (
                                      <div key={i}>{d}</div>
                                    ))}
                                  </>
                                )}
                              </span>
                            }
                          >
                            <Tag color={outcome.color}>{outcome.label}</Tag>
                          </Tooltip>
                        );
                      },
                    },
                    {
                      title: "",
                      key: "actions",
                      render: (_: unknown, v) => {
                        const extractionActive = Boolean(activeExtractionByVersion[v.id] || extractingId === v.id);
                        return (
                        <Space size={6}>
                          <Button
                            size="small"
                            icon={<PartitionOutlined />}
                            onClick={() =>
                              setInsightFor({ versionId: v.id, docTitle: `${doc.title} v${v.version_number}` })
                            }
                          >
                            View document &amp; structure
                          </Button>
                          {mayAuthor && (
                            <Button
                              size="small"
                              icon={<ThunderboltOutlined />}
                              disabled={extractionActive || (scoped ? false : policySets.length === 0)}
                              onClick={() => setExtractOpenFor(extractOpenFor === v.id ? null : v.id)}
                            >
                              {extractionActive ? "Extraction running — view progress" : "Extract with AI"}
                            </Button>
                          )}
                        </Space>
                        );
                      },
                    },
                  ]}
                />
                {doc.versions.map((v) => (
                  <ExtractionProgressPanel
                    key={`progress-${v.id}`}
                    documentVersionId={v.id}
                    running={extractingId === v.id}
                    onActivityChange={(active) => noteExtractionActivity(v.id, active)}
                  />
                ))}

                {doc.versions.map(
                  (v) =>
                    extractOpenFor === v.id && (
                      <div key={`extract-${v.id}`} className="extract-panel">
                        <Space orientation="vertical" style={{ width: "100%" }}>
                          <Space>
                            {!scoped && (
                              <>
                                <Text>Target policy set</Text>
                                <Select
                                  value={extractTargetKey}
                                  onChange={setExtractTargetKey}
                                  style={{ minWidth: 220 }}
                                  options={policySets.map((ps) => ({ value: ps.key, label: ps.name }))}
                                />
                              </>
                            )}
                            <Button
                              type="primary"
                              onClick={() => handleExtract(v.id)}
                              loading={extractingId === v.id}
                              disabled={extractingId !== null && extractingId !== v.id}
                            >
                              Run Extraction
                            </Button>
                          </Space>

                          {extractResults[v.id] && "error" in extractResults[v.id] && (
                            <Alert type="error" showIcon title={(extractResults[v.id] as { error: string }).error} />
                          )}
                          {extractResults[v.id] && "created" in extractResults[v.id] && (
                            <Alert
                              type="success"
                              showIcon
                              title={`Created ${(extractResults[v.id] as ExtractResult).created.length} candidate rule(s)${
                                (extractResults[v.id] as ExtractResult).skipped.length > 0
                                  ? `, skipped ${(extractResults[v.id] as ExtractResult).skipped.length}`
                                  : ""
                              }.${
                                !scoped && extractTargetKey
                                  ? ` Sent to "${policySets.find((p) => p.key === extractTargetKey)?.name ?? extractTargetKey}".`
                                  : ""
                              }`}
                              action={
                                onNavigate && (
                                  <Button size="small" onClick={() => onNavigate(scoped ? "review" : "projects")}>
                                    {scoped ? "Review candidates →" : "Go to Projects →"}
                                  </Button>
                                )
                              }
                            />
                          )}

                          <Divider style={{ margin: "4px 0" }} />
                          <Text strong>Extraction runs for this version</Text>
                          <ExtractionRunHistory documentVersionId={v.id} refreshKey={runHistoryKey} />
                        </Space>
                      </div>
                    )
                )}
                </div>
              </article>
            ))}
            {documents.length === 0 && (
              <Text type="secondary">
                {scoped ? "No documents uploaded to this project yet." : "No documents uploaded yet."}
              </Text>
            )}
          </Space>
        )}
        </div>
      </section>

      <DocumentBodyDrawer
        open={bodyViewer !== null}
        onClose={() => setBodyViewer(null)}
        documentVersionId={bodyViewer?.versionId ?? null}
        documentTitle={bodyViewer?.docTitle}
        versionLabel={bodyViewer?.versionLabel}
      />

      <ExtractionInsightDrawer
        open={insightFor !== null}
        onClose={() => setInsightFor(null)}
        documentVersionId={insightFor?.versionId ?? null}
        documentTitle={insightFor?.docTitle}
      />
    </>
  );
}
