import { useEffect, useMemo, useState } from "react";
import { Button, Drawer, Empty, Input, message, Select, Space, Spin, Tag, Typography } from "antd";
import { CopyOutlined, FileTextOutlined, SearchOutlined, TableOutlined } from "@ant-design/icons";
import type { Clause } from "../api";
import { getClausesForDocumentVersion } from "../clauseCache";

const { Text, Title, Paragraph } = Typography;

interface DocumentBodyDrawerProps {
  open: boolean;
  onClose: () => void;
  /** The document version whose original extracted text should be displayed. */
  documentVersionId: string | null;
  documentTitle?: string;
  versionLabel?: string;
  /** Optional clause to scroll to and highlight on open — lets a rule's "Original
   * source text" evidence link jump straight into its place in the full document. */
  focusClauseId?: string | null;
  /** Fallback page to scroll to when no clause-level anchor is available (e.g. a
   * citation whose clause_id went stale after re-extraction) — still gets the reviewer
   * to the right place in the document, just without a highlighted quote. Ignored when
   * focusClauseId is set. */
  focusPage?: number | null;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Wrap every case-insensitive occurrence of `query` in `text` with a <mark>. Read-only
 * highlighting — never alters the underlying verbatim text, only how it's displayed. */
function highlightMatches(text: string, query: string): React.ReactNode {
  const trimmed = query.trim();
  if (!trimmed) return text;
  const parts = text.split(new RegExp(`(${escapeRegExp(trimmed)})`, "ig"));
  if (parts.length === 1) return text;
  return parts.map((part, i) =>
    part.toLowerCase() === trimmed.toLowerCase() ? (
      <mark key={i} className="doc-body-highlight">
        {part}
      </mark>
    ) : (
      <span key={i}>{part}</span>
    )
  );
}

interface Row {
  clause: Clause;
  showSection: boolean;
  showPageMarker: boolean;
}

/**
 * Full-text reading view of a source document, exactly as it was extracted —
 * every clause in original document order (`sequence`), grouped by section
 * and annotated with page numbers where known. This is the "where is the body
 * of the policy" surface: nothing here is reworded or summarized, it is the
 * verbatim original text the AI/human reviewers derived rules from.
 */
export function DocumentBodyDrawer({
  open,
  onClose,
  documentVersionId,
  documentTitle,
  versionLabel,
  focusClauseId,
  focusPage,
}: DocumentBodyDrawerProps) {
  const [clauses, setClauses] = useState<Clause[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (!open || !documentVersionId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setQuery("");
    getClausesForDocumentVersion(documentVersionId)
      .then((list) => {
        if (cancelled) return;
        setClauses([...list].sort((a, b) => a.sequence - b.sequence));
      })
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [open, documentVersionId]);

  // Scroll to (and briefly flash) a specific clause once its content has rendered.
  // Falls back to scrolling to the cited page when no clause anchor is available
  // (a stale/backfilled citation) — still lands the reviewer near the right text.
  useEffect(() => {
    if (!open || clauses.length === 0) return;
    if (focusClauseId) {
      const id = `doc-body-clause-${focusClauseId}`;
      const timer = setTimeout(() => {
        const el = document.getElementById(id);
        if (el) {
          el.scrollIntoView({ behavior: "smooth", block: "center" });
          el.classList.add("doc-body-focus");
          setTimeout(() => el.classList.remove("doc-body-focus"), 2200);
        }
      }, 120);
      return () => clearTimeout(timer);
    }
    if (focusPage != null) {
      const timer = setTimeout(() => {
        document.getElementById(`doc-body-page-${focusPage}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 120);
      return () => clearTimeout(timer);
    }
  }, [open, focusClauseId, focusPage, clauses]);

  const pages = useMemo(() => {
    const set = new Set<number>();
    for (const c of clauses) if (c.page !== null) set.add(c.page);
    return [...set].sort((a, b) => a - b);
  }, [clauses]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return clauses;
    return clauses.filter((c) => c.text.toLowerCase().includes(q) || (c.section ?? "").toLowerCase().includes(q));
  }, [clauses, query]);

  const rows = useMemo<Row[]>(() => {
    let lastSection: string | null = null;
    let lastPage: number | null = null;
    let first = true;
    return filtered.map((clause) => {
      const showSection = first || clause.section !== lastSection;
      const showPageMarker = clause.page !== null && clause.page !== lastPage;
      lastSection = clause.section;
      lastPage = clause.page;
      first = false;
      return { clause, showSection, showPageMarker };
    });
  }, [filtered]);

  const handleCopyAll = async () => {
    try {
      await navigator.clipboard.writeText(clauses.map((c) => c.text).join("\n\n"));
      message.success("Full document text copied to clipboard.");
    } catch {
      message.error("Couldn't access the clipboard.");
    }
  };

  const scrollToPage = (page: number) => {
    document.getElementById(`doc-body-page-${page}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <Drawer
      title={
        <Space size={8}>
          <FileTextOutlined />
          <Text strong>{documentTitle ?? "Document"}</Text>
          {versionLabel && <Tag>{versionLabel}</Tag>}
        </Space>
      }
      placement="right"
      width={680}
      open={open}
      onClose={onClose}
      extra={
        <Button size="small" icon={<CopyOutlined />} onClick={handleCopyAll} disabled={clauses.length === 0}>
          Copy full text
        </Button>
      }
      className="doc-body-drawer"
    >
      <div className="doc-body-toolbar">
        <Input
          allowClear
          prefix={<SearchOutlined />}
          placeholder="Find text in this document…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        {pages.length > 1 && (
          <Select<number>
            style={{ width: 150 }}
            placeholder="Jump to page"
            options={pages.map((p) => ({ value: p, label: `Page ${p}` }))}
            onChange={(p) => scrollToPage(p)}
          />
        )}
      </div>

      {query.trim() && !loading && (
        <Text type="secondary" className="doc-body-match-count">
          {filtered.length} of {clauses.length} passage{clauses.length === 1 ? "" : "s"} match “{query.trim()}”
        </Text>
      )}

      {loading && (
        <div className="doc-body-loading">
          <Spin /> <Text type="secondary">Loading original document text…</Text>
        </div>
      )}
      {!loading && error && <Text type="danger">{error}</Text>}
      {!loading && !error && clauses.length === 0 && (
        <Empty description="No extracted text is available for this document version yet." />
      )}
      {!loading && !error && clauses.length > 0 && filtered.length === 0 && (
        <Empty description={`No passages match "${query.trim()}".`} />
      )}

      <div className="doc-body-flow">
        {rows.map(({ clause, showSection, showPageMarker }) => {
          const isTableRow = clause.clause_ref.startsWith("table-");
          return (
            <div
              key={clause.id}
              id={showPageMarker && clause.page !== null ? `doc-body-page-${clause.page}` : undefined}
            >
              {showPageMarker && clause.page !== null && <div className="doc-body-page-marker">Page {clause.page}</div>}
              {showSection && clause.section && (
                <Title level={5} className="doc-body-section-heading">
                  {clause.section}
                </Title>
              )}
              <div id={`doc-body-clause-${clause.id}`} className={isTableRow ? "doc-body-table-row" : "doc-body-paragraph"}>
                {isTableRow && <TableOutlined className="doc-body-table-icon" />}
                <div className="doc-body-paragraph-main">
                  <Paragraph className="doc-body-paragraph-text">{highlightMatches(clause.text, query)}</Paragraph>
                  <Text type="secondary" className="doc-body-clause-ref">
                    {clause.clause_ref}
                  </Text>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </Drawer>
  );
}
