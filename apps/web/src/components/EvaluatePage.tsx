import { useEffect, useState } from "react";
import {
  Alert,
  AutoComplete,
  Button,
  Card,
  Checkbox,
  Col,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Tooltip,
  Typography,
} from "antd";
import { InfoCircleOutlined, PlayCircleOutlined, UserOutlined } from "@ant-design/icons";
import {
  api,
  PolicyPlatformApiError,
  principalToFacts,
  type ApprovedPolicyVersion,
  type CanonicalRule,
  type EvaluationResponse,
  type PolicySet,
  type PrincipalContext,
} from "../api";
import { EvaluationResultView } from "./EvaluationResultView";

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

interface FactField {
  name: string;
  data_type: string;
  required: boolean;
}

interface ScopeOptions {
  jurisdictions: string[];
  organizational_units: string[];
  personas: string[];
  processes: string[];
}

const EMPTY_SCOPE_OPTIONS: ScopeOptions = {
  jurisdictions: [],
  organizational_units: [],
  personas: [],
  processes: [],
};

/**
 * The outcome of building the facts form, kept separate from `factFields` so an
 * empty form can say *why* it is empty. Four causes reach `factFields.length ===
 * 0` and were previously one sentence: the rules are still loading, the load
 * failed, the set has no active version to read, and — the normal case for rules
 * whose test is words rather than a computation — the version has rules but none
 * names a fact for the form to collect. Collapsing "the version has no rules"
 * onto "its rules name no facts" is the defect this type exists to prevent.
 */
type FactsLoad =
  | { status: "loading" }
  | { status: "error" }
  | { status: "no-active-version" }
  | { status: "ready"; ruleCount: number };

export function EvaluatePage() {
  const [policySets, setPolicySets] = useState<PolicySet[]>([]);
  const [selectedKey, setSelectedKey] = useState<string>("");
  const [versions, setVersions] = useState<ApprovedPolicyVersion[]>([]);
  const [versionsLoadedFor, setVersionsLoadedFor] = useState<string | null>(null);
  const [selectedVersionId, setSelectedVersionId] = useState<string>("active");
  const [factFields, setFactFields] = useState<FactField[]>([]);
  const [factsLoad, setFactsLoad] = useState<FactsLoad>({ status: "loading" });
  const [factValues, setFactValues] = useState<Record<string, string>>({});
  const [scopeOptions, setScopeOptions] = useState<ScopeOptions>(EMPTY_SCOPE_OPTIONS);
  const [principal, setPrincipal] = useState<PrincipalContext>({});
  const [useAdvancedJson, setUseAdvancedJson] = useState(false);
  const [factsJson, setFactsJson] = useState("{}");
  const [correlationId, setCorrelationId] = useState("");
  const [response, setResponse] = useState<EvaluationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api
      .listPolicySets()
      .then((sets) => {
        setPolicySets(sets);
        if (sets.length > 0) setSelectedKey(sets[0].key);
      })
      .catch((e) => {
        setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
        setVersionsLoadedFor(selectedKey);
        setFactsLoad({ status: "error" });
      });
  }, []);

  useEffect(() => {
    if (!selectedKey) return;
    setError(null);
    setPrincipal({});
    setVersions([]);
    setVersionsLoadedFor(null);
    setFactsLoad({ status: "loading" });
    api
      .listPolicyVersions(selectedKey)
      .then((v) => {
        setVersions(v);
        setVersionsLoadedFor(selectedKey);
        setSelectedVersionId("active");
      })
      .catch((e) => setError(e instanceof PolicyPlatformApiError ? e.detail : String(e)));
  }, [selectedKey]);

  // Build the dynamic facts form + "who is asking" scope suggestions from the
  // union of required_facts / scope values across the target version's rules.
  useEffect(() => {
    if (!selectedKey) return;
    const loadFacts = async () => {
      setFactsLoad({ status: "loading" });
      try {
        let versionId = selectedVersionId;
        if (versionId === "active") {
          const active = versions.find((v) => v.is_active);
          if (!active) {
            setFactFields([]);
            setScopeOptions(EMPTY_SCOPE_OPTIONS);
            setFactsLoad({ status: "no-active-version" });
            return;
          }
          versionId = active.id;
        }
        const rules: CanonicalRule[] = await api.getVersionRules(selectedKey, versionId);
        const seen = new Map<string, FactField>();
        const jurisdictions = new Set<string>();
        const organizationalUnits = new Set<string>();
        const personas = new Set<string>();
        const processes = new Set<string>();
        for (const rule of rules) {
          for (const f of rule.required_facts) {
            if (!seen.has(f.name)) seen.set(f.name, f);
          }
          for (const j of rule.scope?.jurisdictions ?? []) if (j !== "*") jurisdictions.add(j);
          for (const o of rule.scope?.organizational_units ?? []) if (o !== "*") organizationalUnits.add(o);
          for (const p of rule.scope?.personas ?? []) if (p !== "*") personas.add(p);
          for (const p of rule.scope?.processes ?? []) if (p !== "*") processes.add(p);
        }
        setFactFields(Array.from(seen.values()));
        setScopeOptions({
          jurisdictions: Array.from(jurisdictions),
          organizational_units: Array.from(organizationalUnits),
          personas: Array.from(personas),
          processes: Array.from(processes),
        });
        // rules.length is the count the emptiness message must read, and the
        // line that discarded it is the whole defect: without it, a version of
        // judged rules and a version of no rules render the same sentence.
        setFactsLoad({ status: "ready", ruleCount: rules.length });
      } catch (e) {
        setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
        setFactsLoad({ status: "error" });
      }
    };
    if (versionsLoadedFor !== selectedKey) return;
    if (versions.length === 0) {
      setFactFields([]);
      setScopeOptions(EMPTY_SCOPE_OPTIONS);
      setFactsLoad({ status: "no-active-version" });
      return;
    }
    void loadFacts();
  }, [selectedKey, selectedVersionId, versions, versionsLoadedFor]);

  const handleEvaluate = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      let facts: Record<string, unknown>;
      if (useAdvancedJson) {
        facts = JSON.parse(factsJson);
      } else {
        facts = {};
        for (const f of factFields) {
          const raw = factValues[f.name];
          if (raw === undefined || raw === "") continue;
          if (f.data_type === "number") facts[f.name] = Number(raw);
          else if (f.data_type === "boolean") facts[f.name] = raw === "true";
          else facts[f.name] = raw;
        }
      }
      // Principal-derived reserved keys (subject.*/context.*) merge in first;
      // an explicitly-entered fact of the same name (unlikely, but possible
      // in advanced JSON mode) takes precedence.
      const mergedFacts = { ...principalToFacts(principal), ...facts };
      const result = await api.evaluate({
        policy_set_id: selectedKey,
        use_active_version: selectedVersionId === "active",
        policy_version_id: selectedVersionId === "active" ? undefined : selectedVersionId,
        facts: mergedFacts,
        correlation_id: correlationId || undefined,
      });
      setResponse(result);
    } catch (e) {
      setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setLoading(false);
    }
  };

  if (policySets.length === 0) {
    return (
      <>
        <Title level={3}>Evaluate</Title>
        <Text type="secondary">Create a policy set first (Policy Sets page).</Text>
      </>
    );
  }

  return (
    <>
      <div className="page-header-row">
        <Title level={3} style={{ margin: 0 }}>
          Evaluate
        </Title>
        <Select
          value={selectedKey}
          onChange={setSelectedKey}
          style={{ minWidth: 220 }}
          options={policySets.map((ps) => ({ value: ps.key, label: ps.name }))}
        />
      </div>

      <Paragraph type="secondary" style={{ marginTop: 4, marginBottom: 16, maxWidth: 780 }}>
        This is the evaluation API&apos;s surface — the decision path a calling system invokes. A calling system
        sends the facts of one case and gets back a determination for each rule, and those requests are what the
        evaluation audit trail records. Run the same request here by hand to preview the determination a calling
        system would receive. To ask a policy a question in plain words — what it says, or whether a described case
        settles — open the &ldquo;Put a case&rdquo; dialog on the policy instead; that is a reviewer&apos;s tool, and
        nothing it answers is written to this audit trail.
      </Paragraph>

      {error && <Alert type="error" showIcon title={error} />}

      <Card
        title={
          <Space>
            <UserOutlined />
            Who is asking
            <Tooltip title="Rules whose scope restricts to specific personas, organizational units, jurisdictions, or processes (XACML Target) are only applicable when they match here. Leave a dimension blank for 'unspecified' — an unspecified principal never satisfies a rule that restricts on that dimension (safe default: absence of identity never grants access).">
              <InfoCircleOutlined style={{ color: "#8c8c8c" }} />
            </Tooltip>
          </Space>
        }
        style={{ marginBottom: 16 }}
      >
        <Paragraph type="secondary" style={{ marginTop: -8, marginBottom: 16 }}>
          Optional principal context, used only to check scope-restricted rules. Facts below still drive whether a
          rule's condition is satisfied.
        </Paragraph>
        <Row gutter={16}>
          <Col span={6}>
            <Form.Item label="Persona / role">
              <AutoComplete
                allowClear
                value={principal.persona ?? undefined}
                onChange={(v) => setPrincipal((prev) => ({ ...prev, persona: v || undefined }))}
                options={scopeOptions.personas.map((p) => ({ value: p }))}
                placeholder="e.g. executive, manager"
                filterOption={(input, option) => (option?.value ?? "").toLowerCase().includes(input.toLowerCase())}
              />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item label="Organizational unit">
              <AutoComplete
                allowClear
                value={principal.organizational_unit ?? undefined}
                onChange={(v) => setPrincipal((prev) => ({ ...prev, organizational_unit: v || undefined }))}
                options={scopeOptions.organizational_units.map((o) => ({ value: o }))}
                placeholder="e.g. HR, Finance, IT"
                filterOption={(input, option) => (option?.value ?? "").toLowerCase().includes(input.toLowerCase())}
              />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item label="Jurisdiction">
              <AutoComplete
                allowClear
                value={principal.jurisdiction ?? undefined}
                onChange={(v) => setPrincipal((prev) => ({ ...prev, jurisdiction: v || undefined }))}
                options={scopeOptions.jurisdictions.map((j) => ({ value: j }))}
                placeholder="e.g. US, EU, UK"
                filterOption={(input, option) => (option?.value ?? "").toLowerCase().includes(input.toLowerCase())}
              />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item label="Process">
              <AutoComplete
                allowClear
                value={principal.process ?? undefined}
                onChange={(v) => setPrincipal((prev) => ({ ...prev, process: v || undefined }))}
                options={scopeOptions.processes.map((p) => ({ value: p }))}
                placeholder="e.g. leave-request"
                filterOption={(input, option) => (option?.value ?? "").toLowerCase().includes(input.toLowerCase())}
              />
            </Form.Item>
          </Col>
        </Row>
      </Card>

      <Card>
        <Form layout="vertical" onSubmitCapture={handleEvaluate}>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item label="Policy version">
                <Select
                  value={selectedVersionId}
                  onChange={setSelectedVersionId}
                  options={[
                    { value: "active", label: "Active version (current)" },
                    ...versions.map((v) => ({
                      value: v.id,
                      label: `v${v.version_number} ${v.is_active ? "(active)" : ""} — effective ${v.effective_from}`,
                    })),
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="Correlation id">
                <Input value={correlationId} onChange={(e) => setCorrelationId(e.target.value)} />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Checkbox checked={useAdvancedJson} onChange={(e) => setUseAdvancedJson(e.target.checked)}>
                Advanced (raw JSON facts) mode
              </Checkbox>
            </Col>
          </Row>

          {useAdvancedJson ? (
            <Form.Item label="Facts (JSON object)" style={{ marginTop: 16 }}>
              <TextArea rows={8} value={factsJson} onChange={(e) => setFactsJson(e.target.value)} spellCheck={false} />
            </Form.Item>
          ) : (
            <div style={{ marginTop: 16 }}>
              <Paragraph type="secondary" style={{ marginBottom: 8 }}>
                Facts (auto-generated from required facts of the selected version's rules)
              </Paragraph>
              {factFields.length === 0 &&
                (factsLoad.status === "loading" ? (
                  <Text type="secondary">Loading the selected version's rules…</Text>
                ) : factsLoad.status === "error" ? (
                  <Text type="secondary">
                    The selected version's rules could not be loaded — see the error above.
                  </Text>
                ) : factsLoad.status === "no-active-version" ? (
                  <Text type="secondary">
                    No published version yet. Approve and publish a version before evaluating API calls.
                  </Text>
                ) : factsLoad.ruleCount === 0 ? (
                  <Text type="secondary">
                    This version has no rules yet. Publish a version with rules and return here to evaluate it.
                  </Text>
                ) : (
                  <Text type="secondary">
                    The rules on this version state their tests in words, so there is nothing for this form to collect.
                    Run the evaluation to see how each rule is judged.
                  </Text>
                ))}
              <Row gutter={16}>
                {factFields.map((f) => (
                  <Col span={8} key={f.name}>
                    <Form.Item
                      label={
                        <span>
                          {f.name}
                          {f.required && <Text type="danger"> *</Text>} <Text type="secondary">({f.data_type})</Text>
                        </span>
                      }
                    >
                      {f.data_type === "boolean" ? (
                        <Select
                          allowClear
                          value={factValues[f.name] || undefined}
                          onChange={(v) => setFactValues((prev) => ({ ...prev, [f.name]: v ?? "" }))}
                          options={[
                            { value: "true", label: "true" },
                            { value: "false", label: "false" },
                          ]}
                        />
                      ) : f.data_type === "number" ? (
                        <InputNumber
                          style={{ width: "100%" }}
                          value={factValues[f.name] ? Number(factValues[f.name]) : undefined}
                          onChange={(v) => setFactValues((prev) => ({ ...prev, [f.name]: v === null ? "" : String(v) }))}
                        />
                      ) : (
                        <Input
                          type={f.data_type === "date" ? "date" : "text"}
                          value={factValues[f.name] ?? ""}
                          onChange={(e) => setFactValues((prev) => ({ ...prev, [f.name]: e.target.value }))}
                        />
                      )}
                    </Form.Item>
                  </Col>
                ))}
              </Row>
            </div>
          )}

          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            htmlType="submit"
            loading={loading}
            disabled={factsLoad.status === "no-active-version"}
          >
            {loading ? "Evaluating…" : "Run Evaluation"}
          </Button>
        </Form>
      </Card>

      {response && (
        <Card title="Evaluation Result">
          <EvaluationResultView response={response} />
        </Card>
      )}
    </>
  );
}
