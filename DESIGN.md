---
name: Policy Platform
description: An evidence ledger for policy work — source to decision to state, never a grid of dashboard cards.
colors:
  indigo-ink: "#5b4db1"
  indigo-index: "#7c3aed"
  indigo-index-deep: "#6d28d9"
  indigo-wash: "#f0eef8"
  indigo-tint: "#f5f3ff"
  slate-ledger-night: "#171826"
  code-night: "#161824"
  ink-heading: "#0f172a"
  ink-body: "#1e293b"
  ink-secondary: "#64748b"
  ink-tertiary: "#94a3b8"
  rule-hairline: "#e2e8f0"
  rule-hairline-strong: "#cbd5e1"
  cold-white: "#ffffff"
  cold-paper: "#f4f5f7"
  cold-sunken: "#eef0f3"
  state-allow: "#1a7f37"
  state-allow-field: "#dafbe1"
  state-deny: "#cf222e"
  state-deny-field: "#ffebe9"
  state-action: "#9a6700"
  state-action-field: "#fff8c5"
  state-note: "#0969da"
  state-note-field: "#ddf4ff"
typography:
  display:
    fontFamily: "IBM Plex Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "clamp(20px, 2vw, 26px)"
    fontWeight: 650
    lineHeight: 1.18
    letterSpacing: "-0.025em"
  headline:
    fontFamily: "IBM Plex Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "19px"
    fontWeight: 650
    lineHeight: 1.25
    letterSpacing: "-0.018em"
  title:
    fontFamily: "IBM Plex Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "16px"
    fontWeight: 650
    lineHeight: 1.3
    letterSpacing: "-0.01em"
  subtitle:
    fontFamily: "IBM Plex Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 650
    lineHeight: 1.35
    letterSpacing: "normal"
  body:
    fontFamily: "IBM Plex Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
  caption:
    fontFamily: "IBM Plex Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "11.5px"
    fontWeight: 400
    lineHeight: 1.45
    letterSpacing: "normal"
  label:
    fontFamily: "IBM Plex Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "11px"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "0.06em"
  key:
    fontFamily: "IBM Plex Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "9.5px"
    fontWeight: 700
    lineHeight: 1.4
    letterSpacing: "0.055em"
  identifier:
    fontFamily: "IBM Plex Mono, ui-monospace, SFMono-Regular, Consolas, Liberation Mono, monospace"
    fontSize: "11px"
    fontWeight: 400
    lineHeight: 1.45
    letterSpacing: "normal"
  code:
    fontFamily: "IBM Plex Mono, ui-monospace, SFMono-Regular, Consolas, Liberation Mono, monospace"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.65
    letterSpacing: "normal"
rounded:
  sm: "6px"
  md: "8px"
  lg: "10px"
  xl: "14px"
  pill: "999px"
spacing:
  sp-1: "4px"
  sp-2: "8px"
  sp-3: "12px"
  sp-4: "16px"
  sp-5: "20px"
  sp-6: "28px"
  card-pad: "14px"
  section-gap: "12px"
components:
  button-primary:
    backgroundColor: "{colors.indigo-ink}"
    textColor: "{colors.cold-white}"
    rounded: "{rounded.md}"
    height: "30px"
    padding: "0 15px"
    typography: "{typography.body}"
  button-default:
    backgroundColor: "{colors.cold-white}"
    textColor: "{colors.ink-body}"
    rounded: "{rounded.md}"
    height: "30px"
    padding: "0 15px"
    typography: "{typography.body}"
  button-default-hover:
    textColor: "#51458f"
  button-text-icon:
    backgroundColor: "transparent"
    textColor: "#687385"
    rounded: "{rounded.sm}"
    height: "24px"
    width: "24px"
  button-text-icon-hover:
    backgroundColor: "{colors.indigo-wash}"
    textColor: "#51458f"
  input-search:
    backgroundColor: "{colors.cold-white}"
    textColor: "{colors.ink-body}"
    rounded: "{rounded.md}"
    height: "30px"
    padding: "0 10px"
    typography: "{typography.body}"
  segmented-track:
    backgroundColor: "{colors.cold-sunken}"
    rounded: "{rounded.md}"
    padding: "3px"
  segmented-option:
    backgroundColor: "transparent"
    textColor: "{colors.ink-secondary}"
    rounded: "{rounded.sm}"
    padding: "4px 10px"
    typography: "{typography.caption}"
  segmented-option-active:
    backgroundColor: "{colors.cold-white}"
    textColor: "{colors.indigo-index-deep}"
  panel:
    backgroundColor: "{colors.cold-white}"
    rounded: "{rounded.lg}"
    padding: "0"
  panel-header:
    backgroundColor: "#fbfbfc"
    textColor: "{colors.ink-heading}"
    typography: "{typography.subtitle}"
    padding: "10px 12px"
    height: "50px"
  toolbar:
    backgroundColor: "{colors.cold-white}"
    rounded: "{rounded.md}"
    padding: "9px 10px"
  ledger-row:
    backgroundColor: "{colors.cold-white}"
    textColor: "{colors.ink-body}"
    padding: "7px 12px"
    typography: "{typography.body}"
  ledger-row-hover:
    backgroundColor: "#f8f8fb"
  ledger-row-selected:
    backgroundColor: "#f2f0f8"
  register-row:
    backgroundColor: "{colors.cold-white}"
    textColor: "{colors.ink-body}"
    padding: "12px 16px"
    height: "88px"
  register-columns:
    backgroundColor: "#f8fafc"
    textColor: "{colors.ink-secondary}"
    typography: "{typography.label}"
    padding: "0 16px"
    height: "34px"
  status-pill:
    backgroundColor: "#fafbfc"
    textColor: "{colors.ink-secondary}"
    rounded: "{rounded.sm}"
    height: "22px"
    padding: "0 8px"
    typography: "{typography.caption}"
  status-pill-ok:
    backgroundColor: "#f0fdf4"
    textColor: "#15803d"
  status-pill-bad:
    backgroundColor: "#fef2f2"
    textColor: "#b91c1c"
  family-chip:
    backgroundColor: "{colors.indigo-tint}"
    textColor: "{colors.indigo-index}"
    rounded: "{rounded.pill}"
    height: "17px"
    padding: "0 7px 0 6px"
    typography: "{typography.identifier}"
  reference-pill:
    backgroundColor: "#faf5ff"
    textColor: "{colors.indigo-index-deep}"
    rounded: "{rounded.pill}"
    padding: "0 7px"
    typography: "{typography.identifier}"
  nav-item:
    backgroundColor: "transparent"
    textColor: "rgba(255, 255, 255, 0.75)"
    rounded: "{rounded.sm}"
    typography: "{typography.body}"
  nav-item-selected:
    backgroundColor: "rgba(99, 102, 241, 0.22)"
    textColor: "{colors.cold-white}"
  code-region:
    backgroundColor: "{colors.code-night}"
    textColor: "#c7ccdb"
    rounded: "{rounded.lg}"
    padding: "14px 0"
    typography: "{typography.code}"
---

# Design System: Policy Platform

## Overview

**Creative North Star: "The Evidence Ledger"**

This is a ledger, not a dashboard. Every screen is built to be read in one direction — from the source a rule came from, through the decision a human made about it, to the state that decision put it in. The visual system exists to keep that chain unbroken and legible at desk distance, for hours, across hundreds of rules per session. Where a generic admin tool would float independent cards on a grid and let each one restate its own totals, this system builds one bordered register and rules it into rows with hairlines. The container is the object; the rows are its entries.

The world is cold white and slate, worked at close density. Indigo is not decoration — it is the indexing colour, used to mark what is currently selected, currently active, or currently the primary action, and almost nothing else. Green, red and gold are held back entirely for policy semantics (allow, deny, require action, ambiguity), so a colour is never ambiguous about whether it means "you are here" or "this rule denies". IBM Plex Sans carries all human-readable text at a compact 13px base; IBM Plex Mono appears only where the content is a machine identifier — a rule ID, a project key, a JSON body. Corners are squared to 6–10px: enough to read as software, not enough to read as consumer product.

Depth is used sparingly and structurally. Surfaces are flat and bordered at rest; a shadow appears only when a layer has genuinely detached from the page — a modal, a drawer, a popover, or the inspector opened full screen over a scrim. Motion is fast and confined to state change: 120–180ms on a custom easing curve, on background, colour and border only. The anti-reference is explicit and confirmed by the incumbent build: the generic dashboard-card grid, and the giant expanding detail card that made the policy list unreadable. Both were replaced by a fixed register that expands only the record currently under review.

**Key Characteristics:**
- Cold white and slate surfaces; a single dark indigo sidebar as the only inverted region, and a single near-black JSON surface as the only other one.
- Restrained indigo indexing — selection, active state, and the primary action, nothing else.
- Fine ruled dividers instead of gaps: rows live inside one bordered container, separated by 1px hairlines.
- Compact IBM Plex Sans at a 13px base, with IBM Plex Mono reserved strictly for identifiers and code.
- Squared 6–10px corners; pills only for counts and chips.
- Flat by default; shadow only signals detachment from the page.
- Every record row reads as WHEN → THEN before it reads as metadata.

## Colors

A cold, near-neutral field with one indexing hue and a strictly reserved semantic set.

### Primary
- **Indigo Ink** (`#5b4db1`): The application's committed accent. Owns primary buttons, focus outlines on interactive rows and lists, the brand mark, the register glyph, and every "you are here" affordance. It is muted rather than saturated on purpose — it appears often enough that a bright hue would fatigue.
- **Indigo Index** (`#7c3aed`): The brighter marking hue. Used on the inspector's active-tab ink bar, family/cluster default accents, clickable rule-reference pills, and inline links. Reserved for marking *relationships between records*, where Indigo Ink marks *actions and position*.
- **Deep Index** (`#6d28d9`): Active tab labels and selected-tab counts. The darkest step of the indexing hue; used where indigo has to sit on a white pill and still read as text.
- **Indigo Wash** (`#f0eef8`) and **Indigo Tint** (`#f5f3ff`): The two tinted resting surfaces for indexed state — icon plates, hovered icon buttons, selected list backgrounds, family chip fields.

### Secondary
- **Ledger Night** (`#171826`): The sidebar. The only large inverted region in the product; it anchors navigation as permanent chrome distinct from the work surface.
- **Code Night** (`#161824`): The JSON region. Deliberately near-black and *not* the same value as the sidebar — it marks machine-readable content as a different kind of content, the way a code block does in prose.

### Tertiary
Cluster/family accents are assigned deterministically from a fixed eight-colour palette (`#2563eb`, `#0d9488`, `#4f46e5`, `#c026d3`, `#0891b2`, `#92400e`, `#475569`, `#be185d`), hashed from the family's identity so a family keeps the same colour across every screen and every render order. The palette excludes green, red and gold on purpose.

### Neutral
- **Heading Ink** (`#0f172a`): Page titles, panel titles, metric values — the only text at full darkness.
- **Body Ink** (`#1e293b`): Default body text and row content.
- **Secondary Ink** (`#64748b`): Captions, metadata lines, column headers, inactive tab labels.
- **Tertiary Ink** (`#94a3b8`): Eyebrows, disclosure carets, row arrows, breadcrumb landmark icons — present but never competing.
- **Hairline** (`#e2e8f0`): The default 1px divider and container border. The most-used non-white value in the system.
- **Strong Hairline** (`#cbd5e1`): Reserved for quotation rules (the left rule on verbatim source text) and scrollbar thumbs.
- **Cold White** (`#ffffff`): Every content surface.
- **Cold Paper** (`#f4f5f7`): The application background behind all panels.
- **Cold Sunken** (`#eef0f3`): Recessed tracks — segmented-control backgrounds, progress rails, column headers.

### Semantic
- **Allow Green** (`#1a7f37` on `#dafbe1`), **Deny Red** (`#cf222e` on `#ffebe9`), **Action Gold** (`#9a6700` on `#fff8c5`), **Note Blue** (`#0969da` on `#ddf4ff`): rule effect, ambiguity severity, and system health. These are the product's semantics, not its decoration.

### Named Rules
**The Reserved-Hue Rule.** Green, red and gold belong to policy semantics — effect (allow / deny / require action) and ambiguity severity. Never spend them on selection, navigation, branding, or emphasis. Any new categorical palette must exclude them, exactly as the cluster palette does.

**The One Index Rule.** Indigo marks position, action and relationship. If a colour on screen is neither semantic status nor indigo indexing, it is probably decoration and should be removed.

**The Single-Source Token Rule.** Colour, radius, shadow, spacing and motion primitives are defined once in `index.css`. Downstream files may alias them (`--border: var(--border-subtle)`) but must never redefine them — redefining a primitive silently rewrites every existing use of it.

## Typography

**Display / Body Font:** IBM Plex Sans (with `-apple-system`, `Segoe UI`, Roboto, Helvetica, Arial fallbacks)
**Mono Font:** IBM Plex Mono (with `ui-monospace`, `SFMono-Regular`, Consolas fallbacks)

**Character:** One humanist grotesque doing all the human work, at a compact size with slightly tightened tracking on headings, and one monospace doing all the machine work. The pairing is deliberately unglamorous — it is a working typeface set for a workbench, chosen so that a rule ID and a rule title are never confusable at a glance.

### Hierarchy
- **Display** (650, `clamp(20px, 2vw, 26px)`, 1.18, `-0.025em`): The single priority headline in the work docket — the sentence that states how much judgement is waiting. One per viewport, never more.
- **Headline** (650, 19px, 1.25, `-0.018em`): Page titles, and the project name in the workspace bar. The only element at its weight on a page.
- **Title** (650, 16px, 1.3, `-0.01em`): The inspector's record title, and section headings inside a project tab — one clear step below the page title so a tab never restates the page at full size.
- **Subtitle** (650, 14px, 1.35): Panel and card headers.
- **Body** (400, 13px, 1.5): All running text and row content. Prose blocks cap at 68–78ch; modal intros cap at 72ch.
- **Caption** (400, 11.5px, 1.45): Metadata lines, secondary panel text, chip labels, status pills.
- **Label** (600, 11px, `0.06em`, uppercase): Section eyebrows, scope/governance field labels, group headers, register column headers.
- **Key** (700, 9.5px, `0.055em`, uppercase): The WHEN/THEN keys inside a decision line. Deliberately the smallest type in the system — the keys are scaffolding, the values are the content.
- **Identifier** (mono, 400, 10–11.5px): Rule IDs, project keys, revision numbers, run references.
- **Code** (mono, 400, 12px, 1.65): The JSON region only.

### Named Rules
**The Mono-For-Identifiers Rule.** IBM Plex Mono appears only where the string is a machine identifier or machine-readable payload — a rule ID, a project key, a run reference, a JSON body. Never use it for emphasis, headings, or human labels.

**The Two-Heading Rule.** A page carries exactly one element at headline weight and size. Everything below it steps down to Title or Subtitle. When a tab strip already names the view, the view's own heading drops a step rather than repeating the page title's size.

**The Tabular-Numeral Rule.** Any number that will be scanned in a column or replaced in place — metric values, counts, register totals, JSON line numbers — sets `font-variant-numeric: tabular-nums`.

## Layout

The shell is fixed and never scrolls as a whole: a 224px sidebar (68px collapsed below the `lg` breakpoint), a 52px single-row header that is explicitly forbidden from wrapping, and a scrolling content region sized `calc(100vh - 52px)`. Inside it, `.page-inner` centres at a 1440px cap with 16px/22px padding and a 12px stack gap — except the policies workspace, which opts up to 1760px because it is a two-pane data view rather than prose.

Spacing runs on a single 4px scale (4 / 8 / 12 / 16 / 20 / 28) with two derived constants: a 14px card padding and a 12px section gap. Density is applied globally rather than per page — Ant Design's default 24px card body padding is overridden once at the `.page-inner` level so no new surface can re-inherit the airiness.

The first viewport of the product is a compact two-column work docket: a `1.55fr / 0.8fr` grid holding the review queue's priority statement on the left with the primary action, and the portfolio register adjacent on the right. Both halves live in **one** bordered container divided by a single vertical hairline, not two floating cards. Below 1000px it collapses to a single column and the divider becomes horizontal.

The policy workspace is a fixed register with three explicit modes: **List** (register only, full width), **Split** (register plus inspector, `1 1 520px` / `1 1 640px`, register capped at 760px), and **Detail** (inspector only). The inspector can additionally be lifted to full screen, fixed at `inset: 10px` over a `rgba(15, 23, 42, 0.46)` scrim. Only the record under review expands; the register itself never grows a row.

Long lists are virtualized inside a single scrolling container with a fixed height (`calc(100vh - 214px)`, minimum 520px) so the register keeps its position while the page around it stays still. Below the desktop breakpoint the workspace stacks, the list takes 60vh, and the inspector moves into a full-width right drawer.

Responsive behaviour is a series of narrow, purposeful steps rather than one global grid: 1280/1120/1100/1000/980/900/860/760/720/700/640px breakpoints each solve a specific crowding problem (header affordances, register columns, workflow cards, filter rows) instead of restating the whole layout.

### Named Rules
**The Ruled-Divider Rule.** Related records live inside one bordered container separated by 1px hairlines, with the last row's divider removed. Do not express a list as gapped cards — the gap destroys the reading that these entries belong to one register.

**The One-Row Header Rule.** The application header is exactly one row and never bleeds into the content below. The variable-length side (the breadcrumb) yields and ellipsizes; fixed affordances — status readouts, actions, the actor switcher — never shrink.

**The Scale-Or-Nothing Rule.** Use the 4px spacing scale rather than literal pixel values. Competing per-component rhythms are what forced the global density layer to exist.

## Elevation & Depth

This system is flat by default and structural when it is not. Resting surfaces are white with a 1px hairline border and, at most, a single 1px hover-lift shadow; hierarchy is carried by border, tone and rule rather than by stacking. Shadow is a statement that a layer has genuinely left the page, and it is used at exactly three intensities: card-level for a panel that owns its own scroll region, popover-level for transient overlays, and modal-level for a layer that has taken the screen.

### Shadow Vocabulary
- **Card lift** (`box-shadow: 0 1px 3px rgba(15,23,42,0.07), 0 1px 2px rgba(15,23,42,0.04)`): Registers, panels, the workspace bar, the inspector shell. Barely visible; it separates a container from the paper, nothing more.
- **Hover lift** (`box-shadow: 0 2px 8px rgba(15,23,42,0.05)`): The only shadow a card gains on hover, paired with a border darkening to `#c7cbd3`.
- **Popover** (`box-shadow: 0 10px 28px rgba(15,23,42,0.14), 0 2px 6px rgba(15,23,42,0.05)`): Popovers and filter menus.
- **Tooltip** (`box-shadow: 0 8px 22px rgba(15,23,42,0.18)`): Tooltips only.
- **Drawer** (`box-shadow: -12px 0 36px rgba(15,23,42,0.12)`): Right-edge drawers.
- **Modal** (`box-shadow: 0 20px 60px rgba(15,23,42,0.2), 0 4px 14px rgba(15,23,42,0.08)`): Dialogs.
- **Full-screen record** (`box-shadow: 0 24px 80px rgba(15,23,42,0.28), 0 6px 18px rgba(15,23,42,0.12)`): The inspector when opened over the scrim. The heaviest shadow in the system, and the only one paired with a backdrop.

### Named Rules
**The Detachment Rule.** A shadow means "this layer is no longer part of the page". If a surface is still in the document flow, it gets a border, not a shadow. Buttons carry no shadow at all — default, primary and danger shadows are switched off at the theme level.

**The Inset-Track Rule.** Recessed elements — segmented control tracks, progress rails — are expressed with a `#eef0f3` fill plus a 1px inset shadow, never by cutting a hole with a heavy border.

## Shapes

Corners are squared. The scale is 6px for controls and small chips, 8px for buttons, inputs, toolbars and cards, 10px for registers, panels and the JSON region, and 14px only where a container needs to read as visibly larger than its contents. The full pill (`999px`) is reserved for quantities and identity chips — nav counts, tab counts, family chips, rule-reference pills — where the shape itself says "this is a token, not a container".

Borders do the work that shadow does elsewhere. The default is a 1px `#e2e8f0` hairline; a dashed hairline marks a heuristic, display-only relationship (the "decision variations" strip, the "show more families" affordance) rather than stored data. A left 1px rule in the *strong* neutral marks verbatim quoted source text — a blockquote convention, deliberately not an accent colour, so quotation never reads as emphasis.

The signature form of the system is the **family spine**: a 3px vertical rail inset at the run's indent line, with a hollow 11px node centred on each member row. A run of same-family rows shares one continuous surface — internal dividers go transparent, only the run's outer corners round to 12px, and the resting wash is the family colour at 5.5% alpha. When a family is fragmented across the list, the corresponding end of the rail fades out with a mask gradient instead of capping, so a partial run never reads as the whole family.

### Named Rules
**The Squared-Corner Rule.** Nothing rounds past 14px except deliberate pills. A radius above that reads as consumer software and undermines the register.

**The Pill-Means-Token Rule.** Full-radius shapes are counts and identity chips only. A pill-shaped button or panel is out of world.

## Components

The component character is *quiet, dense and operable*: controls are small (30px default height, 24px small, 36px large), labels are always present, and no affordance depends on colour alone.

### Buttons
- **Shape:** Squared (8px radius), no shadow in any variant.
- **Primary:** Indigo Ink fill (`#5b4db1`) with white text, 30px tall, 500 weight, 6px icon gap. Used once per surface — the docket's "Open project register", the queue's publish action.
- **Default:** White fill, `#d5d9e0` border, body ink text.
- **Hover / Focus:** Default buttons shift border to `#8f86c4` and text to `#51458f`. Focus is always a 2px `#8b5cf6` outline at 2px offset (inset `-2px` on rows and scroll containers so it is never clipped).
- **Text / icon:** Transparent, `#687385` glyph; on hover the glyph goes `#51458f` on an Indigo Wash plate. Used for window actions on the inspector (hide, full screen, close) and row overflow menus.

### Chips
- **Family chip:** Full pill, 17px tall, family accent text on a 10%-alpha field of the same accent, with a leading cluster glyph and a trailing count on a solid accent field. Clicking isolates the family; while isolated the chip carries a `0 0 0 1.5px currentColor` ring so it is obvious what the lens is holding and that clicking again releases it.
- **Continuation chip:** Transparent with an inset accent ring, carrying position ("3 of 7") rather than the name — used only when a family is fragmented across the list.
- **Reference pill:** `#faf5ff` field, Deep Index text, capped at 240px with ellipsis. Shared by the heuristic "variations" strip and curated related/supersedes lists so both read as the same "jump to another rule" affordance.
- **Status pill (header):** 6px radius, 22px tall, a 6px `currentColor` dot plus its label as one reading — never a bare dot next to loose text.

### Cards / Containers
- **Corner Style:** 10px for registers and panels, 8px for toolbars and inline records.
- **Background:** Cold White body; panel headers on `#fbfbfc` with a hairline beneath.
- **Shadow Strategy:** Card lift only (see Elevation). Ant Design's default card shadow is switched off globally.
- **Border:** 1px Hairline, darkening to `#c8ccd4` on hoverable cards.
- **Internal Padding:** 14px body, 9–10px header.

### Inputs / Fields
- **Style:** White fill, 8px radius, 30px height, 13px text; search fields flex to fill the toolbar row at `1 1 200px` with a 160px floor.
- **Focus:** Border to `#5b4db1` with a `rgba(91,77,177,0.12)` outline ring; hover border to `#8f86c4`.
- **Select options:** 30px rows, 12px text, selected on `#efedf8` at 600 weight.

### Navigation
- **Sidebar:** Ledger Night (`#171826`), 224px wide, collapsing to 68px at `lg`. Group captions are 10px/700 uppercase at `0.08em` and 46% white — signposts that recede. Items sit at 75% white, selected on `rgba(99,102,241,0.22)` at full white with a 6px radius. Projects are listed as indented 12.5px children under the Projects destination, so the sider reflects what the instance actually contains.
- **Count badges:** Deliberately neutral (`rgba(255,255,255,0.12)`) — the sidebar is not where an alarm is raised, and a count only renders when it is non-zero.
- **Workspace tabs:** A segmented pill bar on an `#ebedf3` inset track; the active tab is a white pill with Deep Index text at 600 and no ink bar. Each tab carries an icon, a label and a count; the two queues representing human-assigned work carry an amber count instead of neutral.
- **Inspector tabs:** Underlined, quieter — 12.5px, `#8a93a3` inactive, Deep Index active with a 2.5px Index ink bar. The two tab levels are never confusable.

### Ledger Row (signature)
The atom of the system. One row is a button: a title line (13px/600 with effect badge and flag glyphs pushed right), then the **decision line** — `WHEN <condition> → THEN <result>` at 11.5px on a five-track baseline-aligned grid, with 9px uppercase keys, regular-weight conditions and a 500-weight result — then a 10.5px muted metadata caption carrying family chip, rule type, mono rule ID, revision and category. This hierarchy is deliberately restrained: only the policy title is semibold; the condition, result and metadata must never form three stacked bands of black bold text. Compact density hides the second and third lines; nothing else changes. Rows separate on a 1px `#eceef1` hairline, hover to `#f8f8fb`, and select to `#f2f0f8` with a `#cbc5e5` inset ring. Search matches highlight on `#fef08a` without changing what is shown. The same markup and CSS render a published policy and a pending candidate, so a rule looks like itself before and after approval.

### Register Row (signature)
The portfolio's entry. A six-track grid (identity / documents / published / review queue / status / chevron) with an uppercase column header band on Cold Sunken above it. Identity is a 36px squared glyph of the project's initials plus name, mono key, owner and a one-line ellipsized description. On hover the row tints to `#fafafe` and the chevron slides 2px right and takes Indigo Ink. Below 1000px the column header disappears and each stat grows its own small caption instead.

### Decision Evidence Surface (signature)
Quality, comparison, validation, and future project-level assurance views use the same evidence grammar: a compact summary register opens a read-only drawer that separates the allegation, canonical evidence, operational consequence, acceptable boundary, unacceptable boundary, reviewer questions, and closure action. The drawer leads with one semantic icon on a severity-tinted 34px plate, a 16px decision headline, and 12px evidence copy. Green and red fields are reserved for acceptable/unacceptable policy states, never decoration. Affected policy records render as ruled rows with `WHEN → THEN`, source text, lifecycle facts, and a quiet inline **View policy record →** link; repeated boxed action buttons are forbidden because they compete with the evidence itself. Reuse this hierarchy and type scale across project workspaces whenever a user must judge evidence rather than merely browse inventory.

### Code Region (signature)
The JSON view is the only light-on-dark content surface. Code Night (`#161824`) with a `#23263a` border and 10px radius, 12px mono at 1.65. Line numbers sit in a 40px right-aligned gutter with a `#262a3d` rule and are `user-select: none`, so copying the body never picks up wayfinding. Lines wrap with `pre-wrap` and `overflow-wrap: anywhere` — nothing is ever hidden off the right edge, and there is no horizontal scrolling. Token colours: keys `#8ab4f8`, strings `#9ae6a4`, numbers `#f0b072`, booleans `#c8a6f5`, null `#7c8399` italic. Its scrollbar is themed to the dark surface rather than inheriting the light one.

Inside the inspector, the region is a **capped, independently vertically scrollable pane**: the JSON pane owns the space below the tab bar (`min-height: 220px`, `overflow-y: auto`, `overscroll-behavior: contain`, `scrollbar-gutter: stable`), so a 100-line record scrolls inside itself rather than growing the inspector. Above it, a sticky full-width segmented switcher offers three explicit peer variants — **Evaluator JSON**, **Canonical formulation**, and **DMN / FEEL** — each with its own title, one-line caption and download name. The two formulation variants additionally carry a provenance banner naming the source documents, or an explicit warning when the rule has no linked evidence. Variants unavailable for a rule are disabled in place, never hidden.

## Do's and Don'ts

### Do:
- **Do** build lists as one bordered container ruled into rows with 1px `#e2e8f0` hairlines, dropping the last row's divider.
- **Do** lead every record with its decision — `WHEN <condition> → THEN <result>` — before any identifier or metadata.
- **Do** keep indigo (`#5b4db1` for action and position, `#7c3aed` for relationship) as the only non-semantic colour on a screen.
- **Do** reserve IBM Plex Mono for rule IDs, project keys, run references and JSON.
- **Do** pair every status colour with a word. The effect badge is always labeled (`ALLOW`, `DENY`, `REQUIRE ACTION`); colour alone is never the signal.
- **Do** use the 4px spacing scale and the shared radius scale (6/8/10/14/pill) rather than new literals.
- **Do** give any unbounded region an explicit cap and its own scroll — the JSON pane, the activity trail (340px), the family strip (118px) — so a long record never pushes the rest of the screen away.
- **Do** render focus as a 2px `#8b5cf6` outline, inset by `-2px` on rows and scroll containers.
- **Do** keep every mode of a surface reachable and visible: disable an unavailable option in place rather than removing it.
- **Do** honour `prefers-reduced-motion` on anything that moves; state must still be legible with all animation off.

### Don't:
- **Don't** lay work out as a grid of independent dashboard cards, each restating its own totals. That is the confirmed anti-reference.
- **Don't** expand a record inside the register. Only the record under review expands, and it expands in the inspector.
- **Don't** spend green, red or gold on selection, navigation, branding or emphasis — they belong to effect and ambiguity.
- **Don't** add a shadow to something still in the page flow, and don't add shadow to a button in any variant.
- **Don't** redefine a token from `index.css` further down the cascade. Alias it instead.
- **Don't** set `fontSize` inline on a component. Per-call-site type is how page-to-page drift started; style the shared element once.
- **Don't** introduce horizontal scrolling in the code region — long values wrap.
- **Don't** render a count badge for zero. An always-present badge stops meaning anything.
- **Don't** cap the policies workspace at the prose reading width; it is a two-pane data view and widens to 1760px.
- **Don't** round past 14px, and don't use a pill shape for anything that is not a count or an identity chip.
