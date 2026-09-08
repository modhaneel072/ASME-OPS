# Unknown states

States the reference material does not show (or that we could not see because the recording was unavailable). Each is implemented from the specification or our own judgement and is flagged for review once evidence exists.

| Area | Unknown | Our interim decision |
|---|---|---|
| Whole product | Every screen (recording missing) | Follow spec §3–§46 and label all visual claims REPORTED or PROPOSED |
| Work-order detail | Exact card order and which cards collapse | Order from spec §10.7; all cards expanded by default |
| Create pane | Behaviour when navigating away with unsaved changes | Confirm dialog; draft is not auto-saved |
| Filters | Multi-select vs single-select per chip | Multi-select for Assigned To, Team, Category, Status, Priority; single for Due Date preset |
| Saved filters | Sharing UI | Popover with Personal / Shared sections; share to team or chapter |
| Empty states | Illustration style | Original monochrome line illustrations, 96 px |
| Table view | Column chooser | Column menu in header; persisted per user in `ops_user_preferences` |
| Mobile | Detail navigation | Stacked routes with back button; create form as full-screen sheet |
| Notifications | Notification center layout | Bell in header opens right sheet listing unread first |
| Hierarchy view (assets) | Tree interaction | Indented rows with expand/collapse; keyboard arrows |
| Setup banner | Dismiss persistence | Per user per organization in `ops_user_preferences` (`setup_banner_dismissed`) |
