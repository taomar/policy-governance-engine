import { useEffect, useState } from "react";
import { Badge, Button, Input, Layout, Menu, Popover, Select, Space, Tag, Typography } from "antd";
import {
  DesktopOutlined,
  FolderOutlined,
  HomeOutlined,
  InboxOutlined,
  PlayCircleOutlined,
  ThunderboltOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { aiApi, api, type AiStatus, type PolicySet } from "./api";
import { ACTOR_ROLE_DESCRIPTIONS, ACTOR_ROLE_LABELS, useActor, type ActorRole } from "./ActorContext";
import { Dashboard } from "./components/Dashboard";
import { ProjectsPage } from "./components/ProjectsPage";
import { DocumentsPage } from "./components/DocumentsPage";
import { EvaluatePage } from "./components/EvaluatePage";
import { AskAiDrawer } from "./components/AskAiDrawer";
import "./App.css";

const { Sider, Header, Content } = Layout;
const { Text } = Typography;

type Page = "dashboard" | "projects" | "document-inbox" | "evaluate";

const NAV_ITEMS: { id: Page; label: string; icon: React.ReactNode }[] = [
  { id: "dashboard", label: "Dashboard", icon: <HomeOutlined /> },
  { id: "projects", label: "Projects", icon: <FolderOutlined /> },
  { id: "document-inbox", label: "Document Inbox", icon: <InboxOutlined /> },
  { id: "evaluate", label: "Evaluate", icon: <PlayCircleOutlined /> },
];

function ActorSwitcher() {
  const { actor, setActor } = useActor();
  const [open, setOpen] = useState(false);
  const [draftName, setDraftName] = useState(actor.name);

  useEffect(() => setDraftName(actor.name), [actor.name]);

  const content = (
    <Space direction="vertical" size={12} className="actor-switcher-popover">
      <div>
        <Text type="secondary" className="actor-field-label">
          Your name
        </Text>
        <Input
          value={draftName}
          onChange={(e) => setDraftName(e.target.value)}
          onBlur={() => setActor({ ...actor, name: draftName.trim() })}
          onPressEnter={() => setActor({ ...actor, name: draftName.trim() })}
          placeholder="jane.doe"
        />
      </div>
      <div>
        <Text type="secondary" className="actor-field-label">
          Acting as
        </Text>
        <Select
          value={actor.role}
          style={{ width: "100%" }}
          onChange={(role: ActorRole) => setActor({ ...actor, role })}
          options={(Object.keys(ACTOR_ROLE_LABELS) as ActorRole[]).map((role) => ({
            value: role,
            label: ACTOR_ROLE_LABELS[role],
          }))}
        />
        <Text type="secondary" className="actor-role-description">
          {ACTOR_ROLE_DESCRIPTIONS[actor.role]}
        </Text>
      </div>
    </Space>
  );

  return (
    <Popover
      content={content}
      title="Acting as"
      trigger="click"
      open={open}
      onOpenChange={setOpen}
      placement="bottomRight"
    >
      <Button icon={<UserOutlined />} className="actor-switcher-btn">
        {actor.name || "Set name"} <span className="actor-switcher-role">· {ACTOR_ROLE_LABELS[actor.role]}</span>
      </Button>
    </Popover>
  );
}

function App() {
  const [page, setPage] = useState<Page>("dashboard");
  const [apiHealthy, setApiHealthy] = useState<"unknown" | "ok" | "down">("unknown");
  const [aiStatus, setAiStatus] = useState<AiStatus | null>(null);
  const [askAiOpen, setAskAiOpen] = useState(false);
  const [policySets, setPolicySets] = useState<PolicySet[]>([]);
  const [activeProject, setActiveProject] = useState<PolicySet | null>(null);

  useEffect(() => {
    api
      .health()
      .then(() => setApiHealthy("ok"))
      .catch(() => setApiHealthy("down"));
    aiApi
      .status()
      .then(setAiStatus)
      .catch(() => setAiStatus(null));
    api
      .listPolicySets()
      .then(setPolicySets)
      .catch(() => undefined);
  }, []);

  const currentNavItem = NAV_ITEMS.find((item) => item.id === page);

  // Central navigation entrypoint: keeps the lifted `activeProject` (used to scope the
  // "Ask AI" drawer to whatever project the user is currently inside) in sync whenever the
  // user leaves the Projects page via any route — top nav, Dashboard quick links, etc.
  const handleNavigate = (target: string) => {
    setPage(target as Page);
    if (target !== "projects") setActiveProject(null);
  };

  return (
    <Layout className="app-shell">
      <Sider width={240} className="app-sider">
        <div className="brand">
          <div className="brand-mark">PP</div>
          <div>
            <div className="brand-title">Policy Platform</div>
            <div className="brand-subtitle">Deterministic Evaluation</div>
          </div>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[page]}
          className="app-menu"
          items={NAV_ITEMS.map((item) => ({ key: item.id, icon: item.icon, label: item.label }))}
          onClick={({ key }) => handleNavigate(key)}
        />
        <div className="sider-footer">
          <Tag icon={<DesktopOutlined />} bordered={false} className="env-tag">
            Local instance
          </Tag>
        </div>
      </Sider>

      <Layout>
        <Header className="app-header">
          <Space size={8} className="breadcrumb">
            <Text type="secondary">Policy Platform</Text>
            <Text type="secondary">/</Text>
            <Text strong>
              {currentNavItem?.icon} {currentNavItem?.label}
            </Text>
            {page === "projects" && activeProject && (
              <>
                <Text type="secondary">/</Text>
                <Text strong>{activeProject.name}</Text>
              </>
            )}
          </Space>
          <Space size={10} className="header-actions">
            <Badge status={apiHealthy === "ok" ? "success" : apiHealthy === "down" ? "error" : "default"} />
            <Text type="secondary" className="status-text">
              API {apiHealthy === "ok" ? "connected" : apiHealthy === "down" ? "unreachable" : "checking…"}
            </Text>
            {aiStatus && (
              <>
                <span className="header-divider" />
                <Badge status={aiStatus.ai_enabled ? "success" : "default"} />
                <Text type="secondary" className="status-text">
                  AI {aiStatus.ai_enabled ? "enabled" : "disabled"}
                </Text>
              </>
            )}
            {aiStatus?.ai_enabled && (
              <Button
                type="primary"
                icon={<ThunderboltOutlined />}
                onClick={() => setAskAiOpen(true)}
                className="ask-ai-launch-btn"
              >
                Ask AI
              </Button>
            )}
            <span className="header-divider" />
            <ActorSwitcher />
          </Space>
        </Header>

        <Content className="app-content">
          <div className="page-inner">
            {page === "dashboard" && (
              <Dashboard
                onNavigate={handleNavigate}
                onOpenAskAi={aiStatus?.ai_enabled ? () => setAskAiOpen(true) : undefined}
              />
            )}
            {page === "projects" && (
              <ProjectsPage
                onActiveProjectChange={setActiveProject}
                onOpenAskAi={aiStatus?.ai_enabled ? () => setAskAiOpen(true) : undefined}
              />
            )}
            {page === "document-inbox" && <DocumentsPage onNavigate={handleNavigate} />}
            {page === "evaluate" && <EvaluatePage />}
          </div>
        </Content>
      </Layout>

      {aiStatus?.ai_enabled && (
        <AskAiDrawer
          open={askAiOpen}
          onClose={() => setAskAiOpen(false)}
          policySets={policySets}
          initialPolicySetKey={activeProject?.key}
        />
      )}
    </Layout>
  );
}

export default App;
