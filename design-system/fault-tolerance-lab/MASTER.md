# Fault Tolerance Lab — reference-driven design system

The user's attached 8.3 screenshot is the primary visual source. This revision restructures the existing frontend; it does not create a new application or change backend protocols.

## Design workflow

Read the installed UI UX Pro Max skill at .agents/skills/ui-ux-pro-max/SKILL.md and used its local search workflow:

```powershell
python .agents/skills/ui-ux-pro-max/scripts/search.py "developer tool light minimal" --design-system -p "Fault Tolerance Lab Reference" -f markdown
python .agents/skills/ui-ux-pro-max/scripts/search.py "visual hierarchy progressive disclosure" --domain ux -n 3
```

The generator's generic dark/FAQ suggestion was not a suitable match. The user's explicit screenshot takes precedence. Applied the skill's relevant rules: clear hierarchy, 16px base type, progressive disclosure, accessible text contrast, semantic status labels, keyboard focus, reduced motion, and responsive sizing. There are no remote font or image dependencies.

## Primary interaction

Choose scenario → Run → Watch topology → Observe result.

Only seven control groups appear in the main experiment panel: scenario, run, step, reset, speed, fault mode, current status. Retry/dedup/target/delay settings, theory, state tables, full journal, sequence and export remain available in dialogs.

## Five visual regions

| Region | Desktop specification |
|---|---|
| Sidebar | White, 232–296px, short navigation labels, system status at foot |
| Header and page title | 72px breadcrumb/status header; numbered chapter badge, 36–40px title, one short subtitle |
| Metrics | Four horizontal 100px tiles; 48px icon surface, 32px real values |
| Topology | Dominant center surface, white canvas, large custom nodes, actual directional message labels |
| Right panel and timeline | 320–426px controls; 56px blue primary action; three actual key events under topology |

Main layout: CSS grid, 20px gap, 24–28px workspace padding. Cards: 18–24px radius, subtle border/shadow. Section titles 22px, controls 16–20px, body/labels 14–16px. System font: Segoe UI, Arial, sans-serif. Code: Cascadia Code, Consolas, monospace.

At widths <=1100px the navigation becomes an icon rail and controls move below the canvas. At <=767px navigation becomes a top strip, metrics use two columns, and nodes stack vertically. All content remains reachable without document horizontal scrolling.

## Tokens

| Role | CSS token | Value |
|---|---|---|
| App background | --bg | #F8FAFC |
| Sidebar/header/card | --chrome / --panel | #FFFFFF |
| Raised surface | --surface-raised | #F7F9FC |
| Border | --border | #E5EAF2 |
| Main text | --text | #101828 |
| Secondary text | --muted | #64748B |
| Primary / communication / focus | --primary / --blue | #0669E8 |
| Accent | --accent | #0891B2 |
| Success | --green | #15803D |
| Waiting / blocking | --amber | #A16207 |
| Failure | --red | #C62737 |
| Server icon / border | --violet | #8050DF |

Client nodes have a pale blue surface; server/resource nodes pale violet. Success/waiting/failure always include text and icons, not color alone. Native selects and dialogs use light color-scheme. The application has one consistent light palette.

## Protocol composition

- 8.3: large Client and Server; separate curved request/response paths, actual execution counter.
- 8.4: Sender above three recipients; delivery state, ACK/loss/retransmission from the journal.
- 8.5: Coordinator above participants; phase rail, votes, PREPARED/BLOCKED, durable decision and resolve action. Full synchronized sequence opens from the diagram info button.
- 8.6: Recovery controller, Node A, checkpoint and redo log; current/checkpoint/replay/after metrics and replay operation details.
- Overview: browser, coordinator and three worker processes.

Values and edge labels come from existing API/SSE snapshots. The screenshot's example totals (24/22/2/0) are never seeded. Before connection, metrics show an em dash; before execution, unobserved paths are dashed with neutral labels. Message pulses are finite and triggered only by newly received journal events; reconnecting does not fabricate activity.

## Presentation and accessibility

Presentation hides navigation/header, enlarges the topology and keeps the seven control groups. N steps, P pauses/resumes and Esc closes dialogs/exits presentation. Inputs, IME and modifier keys do not trigger shortcuts. Native dialogs contain focus and restore it on close. Icon buttons have accessible names. Reduced motion disables message pulses. Existing process controls and backend behavior are preserved.

## Verification

See VERIFICATION.md for actual commands, reports, visual checks and deployment limits. Reference screenshots and browser reports are local artifacts under test-results, excluded from the release.
