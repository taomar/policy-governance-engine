import { useCallback, useEffect, useId, useRef, useState } from "react";
import {
  BranchesOutlined,
  BulbOutlined,
  ClockCircleOutlined,
  CopyOutlined,
  DiffOutlined,
  DownloadOutlined,
  EditOutlined,
  ExportOutlined,
  FileSearchOutlined,
  MoreOutlined,
  SendOutlined,
  ThunderboltOutlined,
  UndoOutlined,
} from "@ant-design/icons";
import { message, Tooltip } from "antd";
import { candidateEditability, type CandidateEditability } from "../candidateEditability";
import { DirectionalText } from "./DirectionalText";
import "./recordActionsMenu.css";

/**
 * ONE OVERFLOW MENU, FOR RULES AND FOR POLICIES, ON EVERY PAGE THAT HOLDS THEM.
 *
 * WHY ONE COMPONENT AND NOT FOUR
 *
 * A rule in the review queue, a rule on the Policies page, a policy in the
 * review queue and a policy on the Policies page are four places the same
 * question gets asked — what else can I do with this record. Four menus built
 * separately answer it four ways within a release: one grows `Copy ID`, one
 * spells it `Copy rule id`, one puts history first and one forgets it. This is
 * one component whose entries are a function of *where it is* and *what the
 * record is*, so the four places cannot drift apart without the table below
 * changing, in one file, on purpose.
 *
 * WHAT IS NOT IN HERE, AND WHY
 *
 * Approving and rejecting are not menu entries and must not become them. They
 * are the reviewer's primary act; a decision reached by opening a menu is a
 * decision the interface made harder to take than to avoid. Nor is any evidence
 * here — the passage, the compiled test, the attributes. `nothingIsBehindAClick`
 * states that principle and this menu is deliberately on the other side of it:
 * secondary acts and destinations only.
 *
 * WHY EDITABILITY IS DERIVED HERE RATHER THAN PASSED IN
 *
 * The menu is told the record's review states and works out what may be done to
 * it with `candidateEditability` — the same table the server enforces and the
 * review surfaces already read. A surface that handed in its own `canEdit` would
 * be a second opinion on a question that already has an authority, and two
 * opinions on it is exactly how one page came to offer controls another page
 * refused.
 *
 * The actor's role is a different kind of fact — it is about the person, not
 * the record — and it stays with the caller, expressed as whether a handler was
 * supplied. A surface that knows the reader is not a Policy Manager passes no
 * override handler and no override entry is drawn.
 *
 * ABSENT, NOT DISABLED
 *
 * An entry that cannot apply is not rendered. A greyed `Edit` on a published
 * record tells the reader they have the wrong permissions, which is false — the
 * record is immutable and the act they want is `Revise`. Where the distinction
 * carries information the interface says it in words instead: `Revise` carries
 * `editBlockedReason` as its hint, so the entry that *is* the route is also
 * where the reader learns why the other one is closed.
 *
 * THE SEALED-RECORD ARM
 *
 * A published record answers `canEdit: false`, so `Edit`, `Suggest rewrite`,
 * `Send back` and both overrides all fall out of the table on their own, and
 * what is left is reading it plus `Revise`. That is the whole of what the
 * Policies page needs, and it is reached without that page passing a flag or
 * this component learning which page it is on — which is the point. A menu that
 * took `canReview` could be wired to offer a decision on a sealed record; one
 * that reads the record's own status cannot.
 *
 * `Revise` stays conditional on the caller supplying a handler, and that is not
 * a hole in the above. Whether a revision may be *started* is a fact about the
 * version — only the active one may be revised — and that is a different
 * question from whether this record may be changed. The record answers the
 * second; only the surface holding the version can answer the first.
 */

export type RecordActionsScope = "rule" | "policy";

/**
 * Every action this menu can ever offer, in either scope, on either page.
 *
 * Published deliberately as one closed list: the Policies page adopts this
 * component by supplying handlers for the keys it can service, and gets the
 * entries — and their wording, order and grouping — for free. Adding a key is a
 * change to this file; it is never a change a calling surface can make alone.
 */
export type RecordActionKey =
  | "copy-id"
  | "view-history"
  | "view-source"
  | "explain"
  | "ask-ai"
  | "open-record"
  | "edit"
  | "suggest-rewrite"
  | "request-changes"
  | "override-approve"
  | "override-reject"
  | "revise"
  | "compare-versions"
  | "export";

/** What a surface can service. An action with no handler is not drawn. */
export type RecordActionHandlers = Partial<Record<RecordActionKey, () => void>>;

/** The two halves of the menu, in this order. Acting on a record and reading
 *  one are different enough that running them together makes a reader check
 *  every line for whether it changes anything. */
type RecordActionSection = "act" | "read";

interface RecordActionDefinition {
  key: RecordActionKey;
  label: string;
  /** Said in the row beneath the label when the label alone would leave two
   *  entries looking like two spellings of one idea. */
  hint?: string;
  /** A hint the record's own state supplies, which supersedes the fixed one.
   *  Used where the reason an entry is the route is a fact the server already
   *  states, and restating it here in our words would be a second opinion that
   *  can drift from it. */
  hintFor?: (state: RecordState) => string | null | undefined;
  icon: React.ReactNode;
  section: RecordActionSection;
  /** The scopes this action means anything in. */
  scopes: readonly RecordActionsScope[];
  /** Whether the record's own state admits it. Absent means "always". */
  admits?: (state: RecordState) => boolean;
}

/** What the menu knows about the record, derived from its review states. */
interface RecordState {
  editability: CandidateEditability;
  /** Some part of the record is approved — the state a send-back or an
   *  override-to-reject acts on. */
  hasApproved: boolean;
  /** Some part of the record is rejected — what an override-to-approve acts on. */
  hasRejected: boolean;
  /** Every part of the record is part of a published version. */
  isPublished: boolean;
}

/**
 * THE TABLE. Which action belongs to which scope, and what the record must be
 * for it to apply. Each line carries its own reason.
 */
const ACTIONS: readonly RecordActionDefinition[] = [
  // ── Acting on the record ────────────────────────────────────────────────
  {
    // Rule-only: a policy is an assembly of rules and has no wording of its
    // own to change. Editing "the policy" would have to mean editing each of
    // its rules, which is not one act and has no endpoint.
    key: "edit",
    label: "Edit",
    hint: "Change this record's wording, logic or effect",
    icon: <EditOutlined />,
    section: "act",
    scopes: ["rule"],
    admits: (state) => state.editability.canEdit,
  },
  {
    // Also rule-only, and for the same reason: a rewrite is a proposal about
    // one statement's words.
    key: "suggest-rewrite",
    label: "Suggest rewrite",
    hint: "Propose different wording without deciding the record",
    icon: <ThunderboltOutlined />,
    section: "act",
    scopes: ["rule"],
    admits: (state) => state.editability.canReview,
  },
  {
    // A published version is an immutable snapshot, so the way to change it is
    // to start a new revision beside it rather than overwrite what it promised.
    // That is why `Revise` and `Edit` are two entries and never both drawn.
    key: "revise",
    label: "Revise",
    hint: "Start a new revision beside the published one",
    // The record's own state says why editing in place is closed, and that
    // sentence belongs on the entry that is the route instead. Taken from
    // `candidateEditability` rather than written again here, so the menu and
    // the server cannot come to say different things about the same record.
    hintFor: (state) => state.editability.editBlockedReason,
    icon: <BranchesOutlined />,
    section: "act",
    scopes: ["rule", "policy"],
    admits: (state) => state.isPublished,
  },
  {
    key: "request-changes",
    label: "Send back for changes",
    hint: "Reopen a decided record, with the reason on the record",
    icon: <SendOutlined />,
    section: "act",
    scopes: ["rule", "policy"],
    admits: (state) => state.hasApproved,
  },
  {
    key: "override-approve",
    label: "Override & approve",
    icon: <UndoOutlined />,
    section: "act",
    scopes: ["rule", "policy"],
    admits: (state) => state.hasRejected,
  },
  {
    key: "override-reject",
    label: "Override & reject",
    icon: <UndoOutlined />,
    section: "act",
    scopes: ["rule", "policy"],
    admits: (state) => state.hasApproved,
  },

  // ── Reading the record ──────────────────────────────────────────────────
  {
    // Answers one fixed question without the reader having to compose it.
    key: "explain",
    label: "Explain",
    hint: "What this record says, in plain words",
    icon: <BulbOutlined />,
    section: "read",
    scopes: ["rule", "policy"],
  },
  {
    // Answers the reader's own question. Sibling of Explain, not a second
    // spelling of it — hence both hints, which is what tells them apart.
    key: "ask-ai",
    label: "Ask AI",
    hint: "Ask your own question about this record",
    icon: <ThunderboltOutlined />,
    section: "read",
    scopes: ["rule", "policy"],
  },
  {
    key: "view-history",
    label: "View history",
    icon: <ClockCircleOutlined />,
    section: "read",
    scopes: ["rule", "policy"],
  },
  {
    key: "view-source",
    label: "View source",
    hint: "The document this was read from, at this record's passage",
    icon: <FileSearchOutlined />,
    section: "read",
    scopes: ["rule", "policy"],
  },
  {
    key: "compare-versions",
    label: "Compare versions",
    icon: <DiffOutlined />,
    section: "read",
    scopes: ["rule", "policy"],
  },
  {
    key: "open-record",
    label: "Open the full record",
    icon: <ExportOutlined />,
    section: "read",
    scopes: ["rule", "policy"],
  },
  {
    // Exporting one rule is not a thing this app does; exporting a policy is.
    key: "export",
    label: "Export",
    icon: <DownloadOutlined />,
    section: "read",
    scopes: ["policy"],
  },
  {
    // Last, and always: the one act every record admits, whatever its state and
    // whoever is reading. Ours rather than the document's, which is why it sits
    // apart from everything the document supplies.
    key: "copy-id",
    label: "Copy ID",
    icon: <CopyOutlined />,
    section: "read",
    scopes: ["rule", "policy"],
  },
];

/** Fold the record's review states into the facts the table asks about.
 *
 *  A rule has one state. A policy has one per rule, and a policy-level act
 *  reaches every rule it can — the same reading `Approve policy` already takes,
 *  where one press decides every reviewable rule on the card. So a policy admits
 *  an action when any of its rules does. */
export function recordStateFrom(reviewStatuses: readonly string[]): RecordState {
  const states = reviewStatuses.length > 0 ? reviewStatuses : ["candidate"];
  const each = states.map((status) => candidateEditability(status));
  const permissive = each.find((e) => e.canEdit) ?? each.find((e) => e.canReview) ?? each[0];
  return {
    editability: {
      canEdit: each.some((e) => e.canEdit),
      canReview: each.some((e) => e.canReview),
      editBlockedReason: permissive.editBlockedReason,
    },
    hasApproved: states.includes("approved"),
    hasRejected: states.includes("rejected"),
    isPublished: states.length > 0 && states.every((status) => status === "published"),
  };
}

/**
 * The entries this menu would draw, as data.
 *
 * Separate from the rendering so a surface — or the Policies page, when it
 * adopts this — can ask what a record offers without mounting a menu, and so
 * the table above can be tested for what it says rather than for what it looks
 * like.
 */
export function recordActionsFor({
  scope,
  reviewStatuses,
  on,
}: {
  scope: RecordActionsScope;
  reviewStatuses: readonly string[];
  on: RecordActionHandlers;
}): RecordActionDefinition[] {
  const state = recordStateFrom(reviewStatuses);
  return ACTIONS.filter((action) => {
    if (!action.scopes.includes(scope)) return false;
    if (action.admits && !action.admits(state)) return false;
    // Copying an id needs nothing from the surface; everything else is a
    // destination or a change only the surface knows how to make.
    if (action.key === "copy-id") return true;
    return typeof on[action.key] === "function";
  }).map((action) => {
    // Resolved here rather than at render time so that asking this function
    // what a record offers gives the same words the reader will see.
    const supplied = action.hintFor?.(state);
    return supplied ? { ...action, hint: supplied } : action;
  });
}

export function RecordActionsMenu({
  scope,
  recordId,
  recordName,
  reviewStatuses,
  on = {},
  className,
}: {
  scope: RecordActionsScope;
  /** The identifier this record is known by. `Copy ID` copies exactly this. */
  recordId: string;
  /** What the record is called, so the trigger names what it opens onto rather
   *  than saying "More" three times in one column. */
  recordName: string;
  /** Every review state present on the record: one entry for a rule, one per
   *  distinct state for a policy. What may be done is derived from this. */
  reviewStatuses: readonly string[];
  on?: RecordActionHandlers;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const menuId = `${useId()}-record-actions`;

  const entries = recordActionsFor({ scope, reviewStatuses, on });

  /** Close, and put focus back where the reader left it. A menu that closes to
   *  nowhere strands a keyboard reader at the top of the document. */
  const close = useCallback((restoreFocus: boolean) => {
    setOpen(false);
    if (restoreFocus) triggerRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (menuRef.current?.contains(target) || triggerRef.current?.contains(target)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  useEffect(() => {
    if (open) itemRefs.current[activeIndex]?.focus();
  }, [open, activeIndex]);

  if (entries.length === 0) return null;

  const openAt = (index: number) => {
    setActiveIndex(index);
    setOpen(true);
  };

  const run = (action: RecordActionDefinition) => {
    close(true);
    if (action.key === "copy-id") {
      void navigator.clipboard
        ?.writeText(recordId)
        .then(() => message.success("Copied"))
        .catch(() => message.error("Couldn't copy — the clipboard is unavailable"));
      return;
    }
    on[action.key]?.();
  };

  const onTriggerKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openAt(0);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      openAt(entries.length - 1);
    }
  };

  const onMenuKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Escape") {
      event.preventDefault();
      close(true);
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((i) => (i + 1) % entries.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((i) => (i - 1 + entries.length) % entries.length);
    } else if (event.key === "Home") {
      event.preventDefault();
      setActiveIndex(0);
    } else if (event.key === "End") {
      event.preventDefault();
      setActiveIndex(entries.length - 1);
    } else if (event.key === "Tab") {
      // Leaving by Tab is leaving; it should not also steal focus back.
      close(false);
    }
  };

  return (
    <span className={`record-actions${className ? ` ${className}` : ""}`}>
      <Tooltip title={`More actions for this ${scope}`}>
        <button
          type="button"
          ref={triggerRef}
          className="record-actions__trigger"
          aria-haspopup="menu"
          aria-expanded={open}
          aria-controls={open ? menuId : undefined}
          aria-label={`More actions for ${recordName}`}
          data-testid="record-actions-menu"
          onClick={(event) => {
            event.stopPropagation();
            if (open) close(false);
            else openAt(0);
          }}
          onKeyDown={onTriggerKeyDown}
        >
          <MoreOutlined />
        </button>
      </Tooltip>

      {/* Built only while it is open. A queue can hold seventy rules, and a
          menu per row rendered closed is seventy menus nobody asked for. */}
      {open && (
        <div
          id={menuId}
          ref={menuRef}
          role="menu"
          className="record-actions__menu"
          aria-label={`Actions for ${recordName}`}
          onKeyDown={onMenuKeyDown}
          onClick={(event) => event.stopPropagation()}
        >
          {entries.map((action, index) => (
            <button
              key={action.key}
              type="button"
              role="menuitem"
              ref={(node) => {
                itemRefs.current[index] = node;
              }}
              // One tab stop for the whole menu: arrows move within it, Tab
              // leaves it. Roving `tabIndex` is what makes that true.
              tabIndex={index === activeIndex ? 0 : -1}
              className={`record-actions__item record-actions__item--${action.section}`}
              data-action={action.key}
              onMouseEnter={() => setActiveIndex(index)}
              onClick={() => run(action)}
            >
              <span className="record-actions__icon" aria-hidden="true">
                {action.icon}
              </span>
              <span className="record-actions__text">
                <span className="record-actions__label">{action.label}</span>
                {action.key === "copy-id" ? (
                  // The one label carrying the record's own text. Isolated,
                  // because an id read from an Arabic document is a run with its
                  // own direction and takes the surrounding line with it
                  // otherwise.
                  <span className="record-actions__hint record-actions__hint--mono">
                    <DirectionalText>{recordId}</DirectionalText>
                  </span>
                ) : (
                  action.hint && <span className="record-actions__hint">{action.hint}</span>
                )}
              </span>
            </button>
          ))}
        </div>
      )}
    </span>
  );
}
