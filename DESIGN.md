# Design

## Design Brief

AI World Radar is a restrained Chinese AI intelligence product. The interface should feel like a calm editorial desk for AI events: fast to scan, trustworthy to read, and engineered enough to support later Agent-backed workflows.

The current prototype phase focuses on the public event feed and event detail experience only. It does not expose admin terminology, review state, raw source signals, pipeline details, filters, login, subscriptions, or daily brief surfaces.

## Mood

Daylight intelligence desk: white workspace, precise typography, quiet olive accents, real source imagery, and compact information rhythm.

## Color Strategy

Restrained product palette. White carries the surface; olive is used as a quiet brand and state accent; blue is reserved for links and source affordances.

```css
:root {
  --bg: oklch(1 0 0);
  --surface: oklch(0.982 0.004 112);
  --panel: oklch(0.955 0.006 112);
  --ink: oklch(0.19 0.014 245);
  --muted: oklch(0.45 0.018 245);
  --faint: oklch(0.66 0.014 245);
  --line: oklch(0.89 0.008 245);
  --primary: oklch(0.43 0.070 112);
  --primary-soft: oklch(0.93 0.030 112);
  --accent: oklch(0.52 0.090 230);
  --accent-soft: oklch(0.94 0.022 230);
  --danger: oklch(0.52 0.150 25);
}
```

## Typography

Use one system sans stack:

```css
font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
  "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
```

Fixed product scale:

- Page title: 28px / 1.2 / 700
- Detail title: 24px / 1.3 / 700
- Card title: 17px / 1.45 / 650
- Body: 15px / 1.75 / 400
- Meta: 12px / 1.4 / 500

Long prose should stay under roughly 70 Chinese characters per line on desktop.

## Layout

Current scope is Web desktop only. The desktop web prototype uses a two-pane workspace:

- Left: event feed, optimized for scanning.
- Right: selected event dossier preview, always populated, never an empty rail.

The homepage does not include filters, ranking explanations, daily brief blocks, category entry modules, or internal workflow labels.

## Components

### App Header

Compact sticky header with brand, current product surface, and date freshness. It must not become a marketing hero.

### Event Card

Cards are entry points, not reports. Each card shows:

- Cover image.
- Category.
- One signal label.
- Event title.
- Short card summary.
- Source hint.
- Time hint.

Cards do not show heat scores, backend status, "open" buttons, review labels, full source lists, or internal IDs.

### Detail Dossier

Detail view shows:

- Cover image.
- Event meta.
- Title.
- One-sentence summary.
- Natural Chinese body text.
- A compact "why it matters" note.
- Follow-up points.
- Source trail.

The body should read like an explanation, not a formatted report.

### Source Trail

Sources are shown as readable links at the bottom of detail, with domain and short label. The prototype uses static sample links; later implementation maps to `source_refs`.

## Interaction

- Selecting an event updates the detail pane without page reload.
- Keyboard focus states are visible.
- Hover and active states are subtle, mostly border/background changes.
- Motion is limited to short state transitions under 180ms.
- Reduced-motion users get instant state changes.

## Web Scope

- Target surface: Web desktop.
- Prototype viewport: desktop browser, with the two-pane layout kept visible.
- Narrow tablet and mobile breakpoints are out of scope for this phase.

## Explicit Non-Goals

- No public filters in the prototype.
- No daily brief block.
- No admin or review state on public pages.
- No internal model, agent, pipeline, or database terminology on public pages.
- No purple-blue AI gradients, glass cards, oversized hero, or decorative dashboard panels.
