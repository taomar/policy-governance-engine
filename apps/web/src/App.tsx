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
import { distinctLabelsByKey } from "./distinctNames";
import { PROJECT_NAV_PREFIX, projectNavTarget } from "./projectNav";
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

/** Namespaces project keys in the menu so they cannot collide with a `Page` id.
 *  Defined in `projectNav` so surfaces other than the sider can navigate to a
 *  named project rather than only to the register. */

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

  /**
   * Projects listed directly in the sider.
   *
   * The sider listed every project, so on an instance with fifty it became a
   * fifty-item scrolling menu that buried the four fixed destinations below it.
   * The nav is a shortcut to the ones in play; the register enumerates them all.
   * The overflow entry below says how many are not shown and opens the register,
   * so the list is never silently partial. This is a display constant — no
   * project, name or count is treated specially by it.
   */
  const SIDER_PROJECT_ROWS = 8;
  const siderProjects = policySets.slice(0, SIDER_PROJECT_ROWS);
  const siderOverflow = policySets.length - siderProjects.length;
  // The sider is 224px wide, so names are cut hard. Cutting from the end makes
  // projects that share a prefix render as the same string; this keeps whatever
  // part of the name actually distinguishes them. Labels are computed across
  // the whole portfolio, not just the shown slice, so a label does not change
  // meaning when the list scrolls.
  const siderNames = distinctLabelsByKey(policySets, (ps) => ps.key, (ps) => ps.name, 26);

  // Central navigation entrypoint: keeps the lifted `activeProject` (used to scope the
  // "Ask AI" drawer to whatever project the user is currently inside) in sync whenever the
  // user leaves the Projects page via any route — top nav, Dashboard quick links, etc.
  const handleNavigate = (target: string) => {
    // The sider's overflow row is a doorway to the register, not a project.
    if (target === "projects-overflow") {
      setProjectOpenRequest({ key: null, nonce: Date.now() });
      setActiveProject(null);
      setPage("projects");
      return;
    }
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
            // sider always shows where the user actually is. A project past the
            // shortcut list has no row to light up, so the parent carries it.
            page === "projects" &&
            activeProject &&
            !siderCollapsed &&
            siderProjects.some((ps) => ps.key === activeProject.key)
              ? projectNavTarget(activeProject.key)
              : page,
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
                    ...siderProjects.map((ps) => ({
                      key: projectNavTarget(ps.key),
                      label: (
                        <span className="nav-item nav-item--child">
                          <span className="nav-item-label">{siderNames.labelFor(ps.key)}</span>
                          {/* When no shortening can tell two names apart the key
                              does, and the key is real data the project already
                              carries -- never a counter invented for display. */}
                          {siderNames.hasCollisions && <span className="nav-item-key">{ps.key}</span>}
                        </span>
                      ),
                      title: `Open ${ps.name}`,
                    })),
                    ...(siderOverflow > 0
                      ? [
                          {
                            key: "projects-overflow",
                            label: (
                              <span className="nav-item nav-item--child nav-item--overflow">
                                <span className="nav-item-label">
                                  {siderOverflow} more in the register
                                </span>
                              </span>
                            ),
                            title: "Open the project register",
                          },
                        ]
                      : []),
                  ];
                }),
              },
            ];
          })}
          onClick={({ key }) => handleNavigate(key)}
        />
        <div className="sider-footer">
          <Tag icon={<DesktopOutlined />} variant="filled" className="env-tag">
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
