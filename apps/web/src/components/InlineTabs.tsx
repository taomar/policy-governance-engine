import { useCallback, useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

import "./inlineTabs.css";

export interface InlineTabItem {
  key: string;
  /** What the tab button says. */
  label: ReactNode;
  /**
   * The tab's body, as a function.
   *
   * A function and not a node, because a node has already been built by the
   * time it is handed over. This is the whole reason this component exists in
   * place of the library's tabs: a policy can hold dozens of rules, each rule
   * expands into this strip, and a strip that builds seven bodies to show one
   * multiplies that dozens of times over for six results nobody asked to see.
   * Here the closure is passed and only the open tab's is called.
   */
  render: () => ReactNode;
}

interface InlineTabsProps {
  items: InlineTabItem[];
  /** Names the strip for anyone who arrives at it without seeing the row it sits in. */
  ariaLabel: string;
  /** Which tab is open first. Falls back to the first item. */
  defaultActiveKey?: string;
  className?: string;
  /** Told which tab was opened, for callers that want to remember it. */
  onTabChange?: (key: string) => void;
}

/**
 * A tab strip that builds one body at a time.
 *
 * Tabs and "nothing a reviewer needs is behind a click" are in tension, and the
 * tension is resolved by what goes in the first tab rather than by refusing to
 * have tabs: the tab that opens holds everything needed to judge the rule, and
 * the rest hold second arrangements of it, where it came from, what happened to
 * it, and its stored forms. A reviewer who reads only the first tab has been
 * given the decision; the others answer questions that arise after it.
 *
 * Real buttons in a real `role="tablist"`, with arrow keys, Home and End, and
 * one tab in the page tab order at a time — the pattern a screen reader user
 * expects, which a set of divs with click handlers cannot be made into.
 */
export function InlineTabs({ items, ariaLabel, defaultActiveKey, className, onTabChange }: InlineTabsProps) {
  const baseId = useId();
  const firstKey = items[0]?.key;
  const [requestedKey, setRequestedKey] = useState<string | undefined>(defaultActiveKey);
  const tabRefs = useRef(new Map<string, HTMLButtonElement | null>());

  // The open tab is whichever of the requested tabs still exists. A rule whose
  // record loses a tab between renders — no notes target, say — must not leave
  // the strip showing nothing at all.
  const activeKey = useMemo(() => {
    if (requestedKey && items.some((item) => item.key === requestedKey)) return requestedKey;
    if (defaultActiveKey && items.some((item) => item.key === defaultActiveKey)) return defaultActiveKey;
    return firstKey;
  }, [requestedKey, defaultActiveKey, items, firstKey]);

  const select = useCallback(
    (key: string) => {
      setRequestedKey(key);
      onTabChange?.(key);
    },
    [onTabChange],
  );

  const moveFocus = useCallback(
    (index: number) => {
      const target = items[index];
      if (!target) return;
      select(target.key);
      // Focus follows selection, which is what the tablist pattern specifies
      // for automatic activation. The strip is already on screen — the reader
      // just pressed a key on it — so this moves focus without moving the page.
      tabRefs.current.get(target.key)?.focus();
    },
    [items, select],
  );

  const onKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      const current = items.findIndex((item) => item.key === activeKey);
      if (current < 0) return;
      if (event.key === "ArrowRight") {
        event.preventDefault();
        moveFocus((current + 1) % items.length);
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        moveFocus((current - 1 + items.length) % items.length);
      } else if (event.key === "Home") {
        event.preventDefault();
        moveFocus(0);
      } else if (event.key === "End") {
        event.preventDefault();
        moveFocus(items.length - 1);
      }
    },
    [items, activeKey, moveFocus],
  );

  if (items.length === 0) return null;

  const active = items.find((item) => item.key === activeKey) ?? items[0];

  return (
    <div className={className ? `inline-tabs ${className}` : "inline-tabs"}>
      <div className="inline-tabs-strip" role="tablist" aria-label={ariaLabel} onKeyDown={onKeyDown}>
        {items.map((item) => {
          const selected = item.key === active.key;
          return (
            <button
              key={item.key}
              type="button"
              role="tab"
              id={`${baseId}-tab-${item.key}`}
              aria-selected={selected}
              aria-controls={`${baseId}-panel-${item.key}`}
              // One stop in the page tab order for the whole strip: Tab reaches
              // the tabs, arrows move between them, Tab again leaves for the
              // body. Seven stops per rule would make the queue unwalkable.
              tabIndex={selected ? 0 : -1}
              className={selected ? "inline-tab inline-tab--active" : "inline-tab"}
              ref={(node) => {
                tabRefs.current.set(item.key, node);
              }}
              onClick={() => select(item.key)}
            >
              {item.label}
            </button>
          );
        })}
      </div>
      <div
        className="inline-tabs-panel"
        role="tabpanel"
        id={`${baseId}-panel-${active.key}`}
        aria-labelledby={`${baseId}-tab-${active.key}`}
        tabIndex={0}
      >
        {active.render()}
      </div>
    </div>
  );
}
