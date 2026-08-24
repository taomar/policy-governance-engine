/**
 * Reusable notes/collaboration panel attached to any governed entity
 * (policy set, policy version, candidate rule, or individual rule).
 *
 * Notes are append-only (matching the domain's audit-trail posture — see
 * `NoteRepository` in the backend): there is no edit action, only add and
 * delete. Author + role are auto-filled from the current `ActorContext` so
 * a user never has to retype who they are.
 */
import { useEffect, useState } from "react";
import { Avatar, Button, Empty, Input, Popconfirm, Space, Spin, Tag, Typography } from "antd";
import { DeleteOutlined, MessageOutlined, SendOutlined } from "@ant-design/icons";
import { ACTOR_ROLE_LABELS, useActor } from "../ActorContext";
import { api, PolicyPlatformApiError, type Note, type NoteEntityType } from "../api";

const { Text, Paragraph } = Typography;
const { TextArea } = Input;

function formatTimestamp(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function initialsFor(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "?";
  const parts = trimmed.split(/[\s._-]+/).filter(Boolean);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

interface NotesPanelProps {
  entityType: NoteEntityType;
  entityId: string;
  /** Shown above the list, e.g. "Notes on this policy set". */
  title?: string;
  compact?: boolean;
}

export function NotesPanel({ entityType, entityId, title, compact }: NotesPanelProps) {
  const { actor } = useActor();
  const [notes, setNotes] = useState<Note[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [posting, setPosting] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await api.listNotes(entityType, entityId);
      setNotes(list.slice().sort((a, b) => (a.created_at < b.created_at ? 1 : -1)));
    } catch (e) {
      setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entityType, entityId]);

  const handleAdd = async () => {
    if (!draft.trim()) return;
    if (!actor.name.trim()) {
      setError('Set your name via "Acting as" in the header before adding a note.');
      return;
    }
    setPosting(true);
    setError(null);
    try {
      await api.createNote({
        entity_type: entityType,
        entity_id: entityId,
        author: actor.name,
        author_role: ACTOR_ROLE_LABELS[actor.role],
        body: draft.trim(),
      });
      setDraft("");
      await load();
    } catch (e) {
      setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    } finally {
      setPosting(false);
    }
  };

  const handleDelete = async (noteId: string) => {
    setError(null);
    try {
      await api.deleteNote(noteId);
      await load();
    } catch (e) {
      setError(e instanceof PolicyPlatformApiError ? e.detail : String(e));
    }
  };

  return (
    <div className="notes-panel">
      {title && (
        <Text strong className="notes-panel-title">
          <MessageOutlined /> {title} {notes.length > 0 && <Tag className="notes-count-tag">{notes.length}</Tag>}
        </Text>
      )}

      {error && (
        <Paragraph type="danger" className="notes-panel-error">
          {error}
        </Paragraph>
      )}

      <div className={`notes-list ${compact ? "notes-list--compact" : ""}`} aria-busy={loading}>
        <Spin spinning={loading}>
          {notes.length === 0 ? (
            <Empty description="No notes yet" image={Empty.PRESENTED_IMAGE_SIMPLE} />
          ) : (
            <ul className="semantic-list semantic-list--split notes-list-items">
              {notes.map((note) => (
                <li key={note.id} className="semantic-list-item notes-list-item">
                  <div className="notes-list-meta">
                    <Avatar size="small">{initialsFor(note.author)}</Avatar>
                    <div className="notes-list-content">
                      <Space size={8} wrap>
                        <Text strong>{note.author}</Text>
                        <Tag variant="filled" className="notes-role-tag">
                          {note.author_role}
                        </Tag>
                        <Text type="secondary" className="notes-timestamp">
                          {formatTimestamp(note.created_at)}
                        </Text>
                      </Space>
                      <Text className="notes-body">{note.body}</Text>
                    </div>
                  </div>
                  <Popconfirm
                    title="Delete this note?"
                    onConfirm={() => handleDelete(note.id)}
                    okText="Delete"
                    okButtonProps={{ danger: true }}
                  >
                    <Button type="text" size="small" icon={<DeleteOutlined />} danger />
                  </Popconfirm>
                </li>
              ))}
            </ul>
          )}
        </Spin>
      </div>

      <Space.Compact className="notes-composer">
        <TextArea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={`Add a note as ${actor.name || "…set your name above…"}`}
          autoSize={{ minRows: 1, maxRows: 4 }}
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault();
              void handleAdd();
            }
          }}
        />
        <Button type="primary" icon={<SendOutlined />} loading={posting} onClick={handleAdd} disabled={!draft.trim()}>
          Add
        </Button>
      </Space.Compact>
    </div>
  );
}
