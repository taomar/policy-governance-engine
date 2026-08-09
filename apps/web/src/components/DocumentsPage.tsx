import { useEffect, useState } from "react";
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
  Typography,
  Upload,
} from "antd";
import { FileTextOutlined, InboxOutlined, ThunderboltOutlined } from "@ant-design/icons";
import type { UploadFile } from "antd/es/upload/interface";
import { aiApi, api, PolicyPlatformApiError, type ExtractResult, type PolicySet, type SourceDocument } from "../api";
import { DocumentBodyDrawer } from "./DocumentBodyDrawer";
import ExtractionProgressPanel from "./ExtractionProgressPanel";
import ExtractionRunHistory from "./ExtractionRunHistory";

const { Title, Text, Paragraph } = Typography;
const { Dragger } = Upload;

function formatBytes(hash: string): string {
  return hash.slice(0, 12) + "…";
}

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
  const [documents, setDocuments] = useState<SourceDocument[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [title, setTitle] = useState("");
  const [owner, setOwner] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);

  const [policySets, setPolicySets] = useState<PolicySet[]>([]);
  const [extractOpenFor, setExtractOpenFor] = useState<string | null>(null);
  const [extractTargetKey, setExtractTargetKey] = useState<string>("");
  // The id of the version currently extracting, not a bare boolean: progress is
  // per-document-version, and a boolean would spin the button on every version
  // panel while only one is actually running.
  const [extractingId, setExtractingId] = useState<string | null>(null);
  //. Bumped after each run so the history table refetches without the panel
  //. having to know how history is loaded.
  const [runHistoryKey, setRunHistoryKey] = useState(0);
  const [extractResults, setExtractResults] = useState<Record<string, ExtractResult | { error: string }>>({});
  const [assigningId, setAssigningId] = useState<string | null>(null);
  const [bodyViewer, setBodyViewer] = useState<{ versionId: string; docTitle: string; versionLabel: string } | null>(
    null
  );

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

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setUploadMessage(null);
    if (!file) {
      setError("Choose a file to upload.");
      return;
    }
    setUploading(true);
    try {
      const result = await api.uploadDocument(title, owner, file, policySetKey);
      setUploadMessage(`Uploaded "${file.name}" as version ${result.version_number}.`);
      setTitle("");
      setOwner("");
      setFile(null);
      await refresh();
    } catch (e) {
      setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setUploading(false);
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

  return (
    <>
      <div>
        <Title level={3} style={{ marginBottom: 4 }}>
          {scoped ? "Documents" : "Document Inbox"}
        </Title>
        <Paragraph type="secondary">
          {scoped ? (
            <>
              Source policy documents for this project. Uploading a file under an existing title adds a new version
              of that document — useful for tracking policy revisions (e.g. v3.2 → v3.3) over time. Use{" "}
              <strong>✨ Extract with AI</strong> to turn a document version into draft candidate rules for human
              review.
            </>
          ) : (
            <>
              Every document uploaded across all projects, in one place. Documents not yet filed into a project are
              marked <Tag style={{ margin: "0 4px" }}>Unassigned</Tag> — use the selector on each card to file them,
              or open a project and upload directly there.
            </>
          )}
        </Paragraph>
      </div>

      {error && <Alert type="error" showIcon message={error} />}
      {uploadMessage && <Alert type="success" showIcon message={uploadMessage} />}

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
          <Button type="primary" htmlType="submit" loading={uploading}>
            {uploading ? "Uploading…" : "Upload"}
          </Button>
        </Form>
      </Card>

      <section className="documents-register">
        <div className="documents-register__header">
          <Title level={4}>{scoped ? "Documents in this project" : "All documents"}</Title>
          <Text type="secondary">{documents.length} total</Text>
        </div>
        <div className="documents-register__body">
        {loading ? (
          <Text type="secondary">Loading…</Text>
        ) : (
          <Space direction="vertical" style={{ width: "100%" }} size={10}>
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
                      title: "",
                      key: "actions",
                      render: (_: unknown, v) => (
                        <Space size={6}>
                          <Button
                            size="small"
                            icon={<FileTextOutlined />}
                            onClick={() =>
                              setBodyViewer({ versionId: v.id, docTitle: doc.title, versionLabel: `v${v.version_number}` })
                            }
                          >
                            View full text
                          </Button>
                          <Button
                            size="small"
                            icon={<ThunderboltOutlined />}
                            disabled={scoped ? false : policySets.length === 0}
                            onClick={() => setExtractOpenFor(extractOpenFor === v.id ? null : v.id)}
                          >
                            Extract with AI
                          </Button>
                        </Space>
                      ),
                    },
                  ]}
                />

                {doc.versions.map(
                  (v) =>
                    extractOpenFor === v.id && (
                      <div key={`extract-${v.id}`} className="extract-panel">
                        <Space direction="vertical" style={{ width: "100%" }}>
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

                          <ExtractionProgressPanel documentVersionId={v.id} running={extractingId === v.id} />

                          {extractResults[v.id] && "error" in extractResults[v.id] && (
                            <Alert type="error" showIcon message={(extractResults[v.id] as { error: string }).error} />
                          )}
                          {extractResults[v.id] && "created" in extractResults[v.id] && (
                            <Alert
                              type="success"
                              showIcon
                              message={`Created ${(extractResults[v.id] as ExtractResult).created.length} candidate rule(s)${
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
    </>
  );
}
