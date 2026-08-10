import { useEffect, useState } from "react";
import { Button, Input, Layout, Menu, Popover, Select, Space, Tag, Typography } from "antd";
import {
  DesktopOutlined,
  FolderOutlined,
  HomeOutlined,
  InboxOutlined,
  PlayCircleOutlined,
  SolutionOutlined,
  ThunderboltOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { aiApi, api, type AiStatus, type PolicySet } from "./api";
import { ACTOR_ROLE_DESCRIPTIONS, ACTOR_ROLE_LABELS, useActor, type ActorRole } from "./ActorContext";
import { Dashboard } from "./components/Dashboard";
import { ProjectsPage } from "./components/ProjectsPage";
import { DocumentsPage } from "./components/DocumentsPage";
import { EvaluatePage } from "./components/EvaluatePage";
import { MyAttestationsPage } from "./components/MyAttestationsPage";
import { AskAiDrawer } from "./components/AskAiDrawer";
import "./App.css";

const { Sider, Header, Content } = Layout;
const { Text } = Typography;

type Page = "dashboard" | "projects" | "document-inbox" | "evaluate" | "my-attestations";

/**
 * Nav items grouped by what the user is trying to do, with a one-line
 * explanation each. A flat five-item list gave a newcomer no sense of which
 * destinations belong to authoring policy versus running them, and no
 * indication of whether anything was waiting for them behind a link.
 */
const NAV_ITEMS: {
  id: Page;
  label: string;
  icon: React.ReactNode;
  group: "overview" | "author" | "runtime";
  hint: string;
}[] = [
  {
    id: "dashboard",
    label: "Dashboard",
    icon: <HomeOutlined />,
    group: "overview",
    hint: "Activity and health across every project.",
  },
  {
    id: "projects",
    label: "Projects",
    icon: <FolderOutlined />,
    group: "author",
    hint: "Each project holds its own documents, rules and versions.",
  },
  {
    id: "document-inbox",
    label: "Document Inbox",
    icon: <InboxOutlined />,
    group: "author",
    hint: "Files that have arrived but are not yet filed into a project.",
  },
  {
    id: "evaluate",
    label: "Evaluate",
    icon: <PlayCircleOutlined />,
    group: "runtime",
    hint: "Run facts against a published version and see the decision.",
  },
  {
    id: "my-attestations",
    label: "My Attestations",
    icon: <SolutionOutlined />,
    group: "runtime",
    hint: "Policies awaiting your sign-off.",
  },
];

const NAV_GROUP_LABELS: Record<"overview" | "author" | "runtime", string> = {
  overview: "Overview",
  author: "Author",
  runtime: "Runtime",
};

/**
 * Attestations are out of scope for this phase. Hidden rather than deleted: the
 * page, its routes and its data are untouched, so restoring it means removing a
 * key from this list. Declared once and applied to both the rendered menu and
 * the navigation guard, so a hidden page cannot be reached by any other route
 * and render as a blank shell.
 */
const HIDDEN_NAV_IDS: Page[] = ["my-attestations"];
const VISIBLE_NAV_ITEMS = NAV_ITEMS.filter((item) => !HIDDEN_NAV_IDS.includes(item.id));

/** Namespaces project keys in the menu so they cannot collide with a `Page` id. */
const PROJECT_NAV_PREFIX = "project:";

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
  const [siderCollapsed, setSiderCollapsed] = useState(false);
  const [policySets, setPolicySets] = useState<PolicySet[]>([]);
  const [activeProject, setActiveProject] = useState<PolicySet | null>(null);
  const [projectOpenRequest, setProjectOpenRequest] = useState<{ key: string | null; nonce: number }>();

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
    // Project entries in the sider carry the project key, so a project is one
    // click away instead of three (Projects → find card → open).
    if (target.startsWith(PROJECT_NAV_PREFIX)) {
      setPage("projects");
      setProjectOpenRequest({ key: target.slice(PROJECT_NAV_PREFIX.length), nonce: Date.now() });
      return;
    }
    if (HIDDEN_NAV_IDS.includes(target as Page)) return;
    if (target === "projects") {
      // The parent destination is the register, not whichever child happened to
      // be opened last. Clear the one-shot child intent before ProjectsPage is
      // mounted again or its stale request will immediately reopen that project.
      setProjectOpenRequest({ key: null, nonce: Date.now() });
      setActiveProject(null);
    }
    setPage(target as Page);
    if (target !== "projects") setActiveProject(null);
  };

  return (
    <Layout className="app-shell">
      <Sider
        width={224}
        breakpoint="lg"
        collapsedWidth={68}
        collapsed={siderCollapsed}
        onBreakpoint={setSiderCollapsed}
        className="app-sider"
      >
        <div className="brand">
          <div className="brand-mark">PP</div>
          <div>
            <div className="brand-title">PolicyVerbAItim</div>
            <div className="brand-subtitle">Deterministic Evaluation</div>
          </div>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[
            // Reflect the open project rather than just the Projects page, so the
            // sider always shows where the user actually is.
            page === "projects" && activeProject && !siderCollapsed ? `${PROJECT_NAV_PREFIX}${activeProject.key}` : page,
          ]}

          className="app-menu"
          items={(["overview", "author", "runtime"] as const).flatMap((group) => {
            const groupItems = VISIBLE_NAV_ITEMS.filter((item) => item.group === group);
            if (groupItems.length === 0) return [];
            return [
              {
                key: `grp-${group}`,
                type: "group" as const,
                label: NAV_GROUP_LABELS[group],
                children: groupItems.flatMap((item) => {
                  const entry = {
                    key: item.id,
                    icon: item.icon,
                    label: (
                      <span className="nav-item">
                        <span className="nav-item-label">{item.label}</span>
                        {/* Only badge a destination when there is genuinely
                            something behind it — a "0" pill is noise, and an
                            always-present badge stops meaning anything. */}
                        {item.id === "projects" && policySets.length > 0 && (
                          <span className="nav-item-count">{policySets.length}</span>
                        )}
                      </span>
                    ),
                    title: item.hint,
                  };
                  if (item.id !== "projects" || siderCollapsed) return [entry];
                  // The projects themselves are the sider's most-used
                  // destinations, so they are listed rather than buried behind
                  // the list page. This also makes the sider reflect what this
                  // instance actually contains instead of a fixed four links.
                  return [
                    entry,
                    ...policySets.map((ps) => ({
                      key: `${PROJECT_NAV_PREFIX}${ps.key}`,
                      label: (
                        <span className="nav-item nav-item--child">
                          <span className="nav-item-label">{ps.name}</span>
                        </span>
                      ),
                      title: `Open ${ps.name}`,
                    })),
                  ];
                }),
              },
            ];
          })}
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
            <span className="crumb-icon">{currentNavItem?.icon}</span>
            <Text strong>{currentNavItem?.label}</Text>
            {page === "projects" && activeProject && (
              <>
                <Text type="secondary">/</Text>
                <Text strong>{activeProject.name}</Text>
              </>
            )}
          </Space>
          <Space size={10} className="header-actions">
            <span className={`status-pill status-pill--${apiHealthy === "ok" ? "ok" : apiHealthy === "down" ? "bad" : "idle"}`}>
              <span className="status-dot" />
              <span className="status-label">
                API {apiHealthy === "ok" ? "connected" : apiHealthy === "down" ? "unreachable" : "checking…"}
              </span>
            </span>
            {aiStatus && (
              <span className={`status-pill status-pill--${aiStatus.ai_enabled ? "ok" : "idle"}`}>
                <span className="status-dot" />
                <span className="status-label">AI {aiStatus.ai_enabled ? "enabled" : "disabled"}</span>
              </span>
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
                openRequest={projectOpenRequest}
              />
            )}
            {page === "document-inbox" && <DocumentsPage onNavigate={handleNavigate} />}
            {page === "evaluate" && <EvaluatePage />}
            {page === "my-attestations" && <MyAttestationsPage />}
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
