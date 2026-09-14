# Reference recording – observations

**Status of the source material (2026-09-08):** the screen recording named in the build prompt ("MaintainX and 1 more page - Personal - Microsoft Edge 2026-09-08 14-58-54.mp4") was **not present** in the workspace, the repository, or the user's Downloads folder when this baseline was taken. No frames could be extracted. ffmpeg is installed, so the extraction procedure below can be run as soon as the file is available.

Because of that, this document distinguishes three evidence levels:

- **OBSERVED** – seen directly in extracted frames. *None yet.*
- **REPORTED** – described in the embedded ASME Ops specification (section 3, "Reference Recording: Observed UI and Module Inventory"), which was written by someone who watched the recording. Treated as second-hand observation.
- **PROPOSED** – our own decision where neither of the above gives guidance.

## Extraction procedure (run when the MP4 arrives)

```bash
mkdir -p docs/reference/frames
# 1 frame every 2 seconds contact sheet
ffmpeg -i "<recording>.mp4" -vf "fps=1/2,scale=480:-1,tile=6x6" docs/reference/frames/contact-%02d.png
# scene changes (page transitions, menus opening)
ffmpeg -i "<recording>.mp4" -vf "select='gt(scene,0.25)',showinfo" -vsync vfr docs/reference/frames/scene-%03d.png
# viewport size
ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 "<recording>.mp4"
```

Then update this file, `screen-inventory.md`, `design-measurements.md` and `unknown-states.md`, upgrading REPORTED/PROPOSED items to OBSERVED with frame references.

## Shell and navigation

| Observation | Level |
|---|---|
| Fixed, dense left sidebar with grouped, nested navigation (Setup / Work / Optimize / Manage) | REPORTED |
| Slim setup/status banner across the top of the workspace | REPORTED |
| Large page title on the left; search field and primary split button aligned right on the same baseline | REPORTED |
| Compact filter chip row under the title row, including "Add Filter" and "My Filters" | REPORTED |
| White workspace, light neutral borders, almost no shadows | REPORTED |
| Group labels uppercase 11–12 px muted; active row pale-blue background with 3 px left accent; rows 40 px | PROPOSED (numbers from spec §7.1, not measured) |

## Lists and detail

| Observation | Level |
|---|---|
| Master-detail split for operational data (list left, detail right) | REPORTED |
| To Do / Done tabs on the work-order list; To Do View / Panel View selectors | REPORTED |
| Sorting selector with options like priority, due date, last updated | REPORTED |
| Right-side in-page create/edit pane that keeps the list visible, with sticky footer actions | REPORTED |
| Split proportions 40/60 or 42/58; create pane ≈ 58 % of main area | PROPOSED (spec §10.3, §40) |

## Reporting

| Observation | Level |
|---|---|
| Report cards in a two-column grid with shared chart framing | REPORTED |
| Date range selector with presets, export menu, add-to-dashboard action | REPORTED |
| Drill-down and grouping controls under the main visualization | REPORTED |

## Messaging

| Observation | Level |
|---|---|
| Messages and Threads tabs; organization-wide, team, group and direct conversations | REPORTED |
| Conversation list about one third of the remaining width | PROPOSED (spec §12) |

## Empty states

| Observation | Level |
|---|---|
| Centered illustration, one-line title, direct call-to-action link | REPORTED |

## What we deliberately do not copy

No MaintainX name, logo, illustrations, icon set, exact copy or screenshots are used anywhere in ASME Ops. Icons are from the MIT-licensed Lucide set; illustrations for empty states are original inline SVGs.
