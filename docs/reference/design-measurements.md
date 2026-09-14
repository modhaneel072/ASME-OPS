# Design measurements

All values below are **PROPOSED** and taken from the embedded specification (§6, §7, §35) because the recording was unavailable for measurement. When frames exist, measure and record the OBSERVED value next to each row.

## Layout

| Element | Value | Source |
|---|---|---|
| Desktop sidebar width | 264 px | spec §6.5 |
| Collapsed sidebar | 64 px | spec §6.5 |
| Setup banner height | 40 px | spec §6.5 |
| Page header row | 64–72 px (we use 72) | spec §6.5 |
| Content padding | 24 px desktop, 16 px tablet | spec §6.5 |
| Panel border | 1 px `--color-border` | spec §6.5 |
| Master/detail split | 42 / 58 | spec §40 |
| Create pane width | 58 % of main area (min 560 px, max 880 px) | spec §10.3 |
| Messages list column | 34 % of remaining width | spec §12 |

## Controls

| Element | Value |
|---|---|
| Standard control height | 40 px |
| Compact control height | 32 px |
| Filter chip height | 36 px |
| Table row | 48–56 px (we use 48 compact, 56 default) |
| Sidebar row | 40 px, 16 px horizontal padding, nested indent 20 px |
| Primary button | 40 px high, 16 px horizontal padding |

## Typography (Inter)

| Role | Size / weight / line-height |
|---|---|
| Page title | 32 px / 700 / 1.15 |
| Section heading | 20 px / 650 / 1.25 |
| Card heading | 16 px / 600 / 1.3 |
| Body | 14 px / 400 / 1.5 |
| Label | 13 px / 550 / 1.4 |
| Caption | 12 px / 450 / 1.4 |
| Button | 14 px / 600 |
| Table | 13 px / 400 |

## Colour tokens

Copied verbatim from spec §6.2 into `apps/ops-web/src/ui/tokens.css`. Iowa gold `#ffcd00` is reserved for milestones, chapter identity and selected engineering badges.

## Motion

Hover 120 ms ease-out; pane 180 ms ease-out (opacity + 8 px translate); popover 140 ms scale 0.98→1; toast 180 ms. All disabled under `prefers-reduced-motion`.

## Viewports under test

1440×900 (acceptance), 1366×768, 768×1024, 390×844.
