# ASME Ops Stage 4 – Parts Inventory and Purchase Requests

Status: approved for implementation 2026-09-14. Scope: ASME Ops only (`asme/ops`, `/api/v1`, `apps/ops-web`). Legacy tool-checkout tables are not read or migrated; the ops inventory is new and self-contained.

## Global constraints

- Everything from the Stage 1–2 plan still binds: services take `ctx`, authorize before mutating, filter by `ctx.org.id`, `policy.get_or_404` for ids, audit in the same transaction, commit inside the service, emit events after commit, validate with `validation.validate` + module-level SPEC, JSON envelope, `list_payload`, `parse_filters`, `parse_sort`.
- Quantities are `Numeric(14, 3)` and travel as JSON numbers; money is `Numeric(12, 2)` through `money()`; unit costs are `Numeric(12, 4)` serialized as float rounded to 4 places.
- No endpoint updates or deletes an inventory transaction. Corrections are new transactions that reference the original.
- Every quantity change goes through one primitive, `inventory_ledger.post(...)`. Nothing else writes `ops_inventory_balances`.

## Data model (migration `0004_ops_inventory`, down_revision `0003_ops_foundation`)

All tables carry `OpsBase` columns (UUID id, organization_id, created_at, updated_at) unless noted.

### ops_part_types
name (<=120, unique per org), color (default `#475569`), icon (default `package`).

### ops_parts
| column | type | notes |
|---|---|---|
| name | String(200) not null | |
| sku | String(60) null | unique per org when present (`uq_ops_parts_org_sku`) |
| description | Text | |
| part_type_id | uuid fk ops_part_types | |
| manufacturer | String(160) | |
| manufacturer_part_number | String(160) | |
| unit | String(20) not null default `each` | one of PART_UNITS |
| unit_cost | Numeric(12,4) null | weighted by receipts (see ledger) |
| is_critical | Boolean default false | |
| minimum_stock | Numeric(14,3) null | chapter-wide reorder point |
| maximum_stock | Numeric(14,3) null | >= minimum_stock |
| reorder_quantity | Numeric(14,3) null | default quantity for a reorder draft |
| default_location_id | uuid fk ops_locations | |
| qr_code | String(160) null | unique per org when present (`uq_ops_parts_org_qr`) |
| created_by_user_id | user fk | |
| is_active | Boolean default true | |

`PART_UNITS = ("each", "pack", "box", "pair", "set", "g", "kg", "lb", "oz", "m", "cm", "mm", "ft", "in", "roll", "spool", "sheet", "L", "mL")`

### ops_part_vendors (no OpsBase; id uuid pk)
part_id (fk cascade), vendor_id (fk), vendor_part_number (<=160), url (<=500), preferred (bool), last_price Numeric(12,4) null, last_ordered_at UTCDateTime null. Unique (part_id, vendor_id). At most one preferred per part (service rule).

### ops_part_assets (no OpsBase)
part_id (fk cascade), asset_id (fk cascade). Unique pair. "Spare part for this asset".

### ops_inventory_balances (no OpsBase; id uuid pk, organization_id, updated_at)
part_id (fk cascade), location_id (fk), on_hand Numeric(14,3) default 0, reserved Numeric(14,3) default 0. Unique (part_id, location_id). Check constraints `on_hand >= 0`, `reserved >= 0`. Cached projection of the ledger.

### ops_inventory_transactions (no OpsBase; id uuid pk, organization_id, created_at)
| column | notes |
|---|---|
| part_id, location_id | not null |
| transaction_type | INVENTORY_TRANSACTION_TYPES |
| on_hand_delta | Numeric(14,3) signed, not null |
| reserved_delta | Numeric(14,3) signed, not null default 0 |
| quantity | Numeric(14,3) > 0, the magnitude the user entered |
| counted_quantity | Numeric(14,3) null (cycle_count only) |
| on_hand_after, reserved_after | Numeric(14,3) not null – balance at that location after this row |
| unit_cost | Numeric(12,4) null |
| work_order_id | fk ops_work_orders null |
| work_order_part_id | fk ops_work_order_parts null |
| purchase_request_id | fk null |
| purchase_request_item_id | fk null |
| reference_transaction_id | fk self null (transfer pair, return-of-issue, correction) |
| note | Text |
| created_by_user_id | user fk |

`INVENTORY_TRANSACTION_TYPES = ("receipt", "issue", "return", "adjustment", "transfer", "reservation", "release", "cycle_count", "scrap")`

Immutability: SQLAlchemy `before_update` and `before_delete` mapper listeners on `InventoryTransaction` raise `RuntimeError("inventory transactions are immutable")`. Organization-wide deletes for dev resets are not provided.

### ops_work_order_parts (OpsBase)
work_order_id (fk cascade), part_id (fk), location_id (fk null – where it is drawn from), quantity_planned > 0, quantity_reserved >= 0, quantity_issued >= 0, quantity_returned >= 0, readiness in `WORK_ORDER_PART_READINESS = ("assigned", "reserved", "kitted", "staged", "issued")`, note, created_by_user_id. Unique (work_order_id, part_id, location_id).

### ops_purchase_requests (OpsBase)
number int (numbering key `purchase_request`, displayed `PR-<number>`; unique per org), title String(200) not null, requester_user_id (user fk not null), project_id null, vendor_id null, status (PURCHASE_REQUEST_STATUSES, index), needed_by Date null, purpose Text, budget_code String(60), shipping_amount Numeric(12,2) default 0, tax_amount Numeric(12,2) default 0, estimated_total Numeric(12,2) (items + shipping + tax, recomputed by the service), approved_total Numeric(12,2) null, order_reference String(120) null, decline_reason Text null, submitted_at, approved_at, ordered_at, received_at, declined_at, canceled_at (UTCDateTime null).

`PURCHASE_REQUEST_STATUSES = ("draft", "submitted", "treasurer_review", "advisor_review", "approved", "ordered", "partially_received", "received", "declined", "canceled")`

### ops_purchase_request_items (no OpsBase; id uuid pk, created_at)
purchase_request_id (fk cascade), part_id null, description String(300) not null, vendor_part_number (<=160), url (<=500), quantity Numeric(14,3) > 0, unit_price Numeric(12,4) >= 0, received_quantity Numeric(14,3) default 0, receive_location_id null, position int.

### ops_purchase_request_events (no OpsBase; id uuid pk, organization_id, created_at)
purchase_request_id (fk cascade), from_status null, to_status, action (`submit`, `approve`, `decline`, `request_changes`, `order`, `receive`, `cancel`, `reopen`), step (`project_lead`, `treasurer`, `advisor`, null), comment Text, actor_user_id. The approval timeline.

### ops_cost_entries – additive column
`inventory_transaction_id` uuid fk ops_inventory_transactions null. System-created parts cost entries set it; `DELETE /work-orders/:id/cost-entries/:cid` returns 409 `inventory_linked` for them.

### Organization settings (settings_json, no migration)
`purchasing`: `{"advisor_review_threshold": number|null (default null = no advisor step), "require_project_lead_approval": bool (default false), "critical_parts_team_id": uuid|null}`.

## Permissions

New keys (registry + seeded by `ensure_permissions`): `purchase.advisor_review` – "Give faculty-advisor sign-off on purchase requests".

Default grant changes (`sync_role_grants` only adds, so existing chapters keep manual edits):
- `_FULL_MEMBER_CHAPTER` += `inventory.read`, `purchase.submit` (members see stock and ask for purchases; this flows to inventory_manager, safety_officer, treasurer).
- `project_lead` chapter += `inventory.read`, `purchase.submit`; `team_lead` chapter += `inventory.read`, `purchase.submit`; `shop_operator` chapter += `inventory.read`; `faculty_advisor` chapter += `inventory.read`, `vendor.read`, `purchase.advisor_review`.
- `inventory_manager`: drop `purchase.review` from the default (they order and receive; spending approval belongs to the treasurer).
- `chapter_admin` / `executive_officer` get everything through `_ALL`.

Rules that are not a single key:
- Purchase request read: `purchase.review` or `purchase.advisor_review` or `inventory.manage` → all; otherwise own requests plus requests on projects where `policy.can(ctx, "project.manage", project)`. Anything else is 404.
- Nobody approves a request they requested (409 `self_approval`).
- Issuing or returning parts on a work order: `inventory.manage`, or `policy.can(ctx, "work_order.log_time", wo)` (assignees).

## Ledger primitive – `asme/ops/services/inventory_ledger.py`

```python
post(ctx, *, part, location, transaction_type, on_hand_delta, reserved_delta=0, quantity,
     unit_cost=None, counted_quantity=None, work_order=None, work_order_part=None,
     purchase_request=None, purchase_request_item=None, reference=None, note=None) -> InventoryTransaction
```
- Locks or creates the `(part, location)` balance row (`with_for_update()` where supported), applies deltas, rejects a result with `on_hand < 0` or `reserved < 0` or `reserved > on_hand` using `Conflict(code="insufficient_stock", extra={"part_id", "location_id", "on_hand", "reserved", "requested"})`.
- Writes the transaction with `on_hand_after` / `reserved_after`. Does not commit; callers commit once.
- Receipts with `unit_cost` update `part.unit_cost` to the weighted average `((old_total_on_hand * old_cost) + qty * cost) / new_total_on_hand` (old cost missing → new cost).
- Calls `stock_state_changed(ctx, part, before, after)` which, when the part moves into `low` or `out`, notifies every active member whose role grants `inventory.manage` (type `inventory.low_stock`, dedupe `low_stock:<part_id>:<utc date>`), plus the leads of `purchasing.critical_parts_team_id` when `part.is_critical`.
- `part_totals(part_ids) -> {part_id: {"on_hand", "reserved", "available", "ordered"}}` with grouped queries. `ordered` = sum over items of requests in `ordered`/`partially_received` of `quantity - received_quantity`.
- `stock_state(totals, part) -> "ok" | "low" | "out" | "untracked"`: `untracked` when `minimum_stock` is null and on_hand is 0 with no transactions; `out` when available <= 0; `low` when minimum_stock is not null and available < minimum_stock; else `ok`. This is the only low-stock definition in ASME Ops.
- `reconcile(org_id) -> list[dict]`: recompute balances from transactions and return mismatches (used by tests and a `manage.py reconcile-ops-inventory` command that reports and never auto-corrects).

## API

### Parts and inventory (`inventory.read` to read, `inventory.manage` to change unless stated)
- `GET /parts` – q (name, sku, manufacturer_part_number, qr_code), filter[type] multi, filter[location] multi (has balance there), filter[vendor] multi, filter[asset] multi, filter[stock] multi (`ok|low|out|untracked`), filter[critical] single, filter[active] single default true; sort `name|-name|sku|available|-available|-updated_at`. Item = `part` shape. Extra key `stock_counts: {"low": n, "out": n}`.
- `POST /parts`, `GET /parts/:id` (`part_detail`), `PATCH /parts/:id` (no quantity fields; `unit_cost` editable only while the part has no transactions). Deactivate via `is_active=false`; no delete.
- `GET /parts/by-code/:code` – exact sku or qr_code.
- `GET /part-types`, `POST /part-types`.
- `PUT /parts/:id/vendors` `{"vendors": [{"vendor_id", "vendor_part_number", "url", "preferred", "last_price"}]}` replaces; `PUT /parts/:id/assets` `{"asset_ids": [...]}` replaces (assets must be visible).
- `GET /parts/:id/inventory` → `{"balances": [{"location": location_ref, "on_hand", "reserved", "available"}], "totals": {...}}`.
- `GET /parts/:id/transactions` (cursor paginated, newest first; filter[type] multi, filter[location] multi).
- `POST /parts/:id/transactions` `{"type": "receipt|issue|return|adjustment|scrap", "location_id", "quantity" > 0, "direction": "increase|decrease" (adjustment only), "unit_cost" (receipt), "work_order_id" (issue/return, optional), "note" (required for adjustment and scrap)}`. Issue without a work order is allowed for inventory managers (shop use).
- `POST /inventory/transfers` `{"part_id", "from_location_id", "to_location_id" (different), "quantity", "note"}` → two `transfer` rows linked by reference.
- `POST /inventory/cycle-counts` `{"location_id", "lines": [{"part_id", "counted_quantity" >= 0}], "note", "work_order_id"}` → one `cycle_count` row per line whose counted differs from on_hand (delta may be 0 → still recorded so the count date is known). Returns `{"lines": [{"part": part_ref, "expected", "counted", "delta"}]}`.
- `GET /inventory/cycle-counts/sheet?location_id=` → expected quantities for every part with a balance there.
- `GET /inventory/low-stock` → parts in `low`/`out` with preferred vendor and suggested order quantity (`reorder_quantity`, else `maximum_stock - available`, else `minimum_stock - available`, min 1).
- `GET /inventory/transactions` – chapter-wide ledger (same filters + filter[part], filter[work_order], filter[purchase_request], date range `from`/`to`).

### Work-order parts
- `GET /work-orders/:id/parts` (work-order readable) → items `work_order_part` + `readiness_summary` (`"none"` or the least-advanced readiness across lines).
- `POST /work-orders/:id/parts` `{"part_id", "location_id", "quantity_planned", "note"}` (`work_order.edit`); `PATCH /work-orders/:id/parts/:pid` (planned quantity cannot drop below issued − returned); `DELETE` only when nothing reserved or issued.
- `POST /work-orders/:id/parts/:pid/reserve` `{"quantity"}` (`inventory.manage` or `work_order.edit`) → `reservation`; `/release` `{"quantity"}` → `release`.
- `POST /work-orders/:id/parts/:pid/kit` and `/stage` (`inventory.manage`) → readiness only (audit, no transaction).
- `POST /work-orders/:id/parts/:pid/issue` `{"quantity"}` (issue rule above): consumes reservation first (reservation release + issue in one transaction), creates `issue` row and a system `CostEntry(type="parts", amount=qty*unit_cost rounded 2dp, description="<qty> <unit> <part name>", inventory_transaction_id=...)` when unit_cost is known; readiness `issued` when issued >= planned.
- `POST /work-orders/:id/parts/:pid/return` `{"quantity"}` (<= issued − returned) → `return` row referencing the latest issue, plus a negative system cost entry.
- Completing a work order leaves unissued reservations in place and adds `"parts_outstanding": n` to the complete response; `POST /work-orders/:id/parts/release-all` releases every reservation.

### Purchase requests
- `GET /purchase-requests` – tab `mine|review|open|closed|all` (review = requests at a step the caller can act on); filter[status] multi, filter[project] multi, filter[vendor] multi, filter[requester] multi; q (title, number, `PR-12`, item description); sort `-updated_at|-created_at|needed_by|-estimated_total|number`. Extra `tabs` counts.
- `POST /purchase-requests` (`purchase.submit`) creates a draft: title, project_id (visible), vendor_id, needed_by, purpose, budget_code, shipping_amount, tax_amount, items [{part_id, description (defaults to part name), vendor_part_number, url, quantity, unit_price, receive_location_id}] (1–100 items).
- `POST /purchase-requests/from-low-stock` `{"part_ids": [...]}` (`purchase.submit` + `inventory.read`) → one draft per preferred vendor (parts without a preferred vendor share a vendorless draft), quantities from the suggestion rule, unit price from `last_price` or `unit_cost`.
- `GET /purchase-requests/:id` (`purchase_request_detail`: items, events, attachments count, `available_actions`).
- `PATCH /purchase-requests/:id` – requester or `purchase.review`, only in `draft`; replaces items when `items` is present.
- Actions (`POST /purchase-requests/:id/<action>`), each writes a `PurchaseRequestEvent`, audit `purchase_request.<action>`, notifications:
  - `submit` (requester, draft, ≥1 item) → `submitted` when `require_project_lead_approval` and the request has a project (notify project lead) else `treasurer_review` (notify holders of `purchase.review`).
  - `approve` `{"comment", "approved_total"}`: at `submitted` needs `project.manage` on the project → `treasurer_review`; at `treasurer_review` needs `purchase.review` → `advisor_review` when threshold is set and `estimated_total >= threshold` (notify holders of `purchase.advisor_review`) else `approved`; at `advisor_review` needs `purchase.advisor_review` → `approved`. Sets approved_at/approved_total on reaching `approved`; notify requester.
  - `decline` `{"comment"}` required, at any review status by that step's approver → `declined` (decline_reason).
  - `request-changes` `{"comment"}` required, at any review status → `draft`.
  - `order` `{"order_reference", "ordered_at", "approved_total"}` (`inventory.manage` or `purchase.review`), `approved` → `ordered`; updates `part_vendors.last_ordered_at`.
  - `receive` `{"lines": [{"item_id", "quantity" > 0, "location_id"}], "note"}` (`inventory.manage`), `ordered|partially_received` → `partially_received` or `received`; quantity may not exceed `quantity - received_quantity`; stock items post `receipt` transactions (`unit_cost=unit_price`, `purchase_request_item`), update `part_vendors.last_price`; location defaults to item receive_location_id, then part default_location_id, then org default location.
  - `cancel` `{"comment"}`: requester in `draft|submitted|treasurer_review|advisor_review`; `purchase.review` in any status before `ordered`.
  - `reopen` (`purchase.review`): `declined|canceled` → `draft`.
- Invalid from-state → `Conflict(code="invalid_transition", extra={"from", "action"})`.
- `GET /projects/:id/health` budget gains `committed` = sum of `approved_total or estimated_total` over the project's requests in `approved|ordered|partially_received|received`.

### Shared integration
- `entities.resolve` segments `parts` → `part` (inventory.read) and `purchase-requests` → `purchase_request` (read rule above), so comments and attachments work on both.
- Change feed `_readable_ids`: `part`, `part_type` readable with `inventory.read`; `purchase_request` via the read rule; `inventory_transaction` audit events are not emitted (the ledger is its own history).
- Search gains `parts` (inventory.read) and `purchase_requests` (read rule) groups.
- Setup Center task `parts` becomes available: complete when the org has ≥ 5 active parts, href `/app/parts`, stage null.
- Notification hrefs: `part` → `/app/parts/<id>`, `purchase_request` → `/app/purchase-requests/<id>`.
- Events: `ops.inventory.low_stock`, `ops.purchase_request.status_changed`.

## Serializer shapes

- `part_ref`: `{"id", "name", "sku", "unit"}`; `purchase_request_ref`: `{"id", "number", "display_number", "title", "status"}`.
- `part`: part_ref + description, part_type {id,name,color,icon}|null, manufacturer, manufacturer_part_number, unit_cost, is_critical, minimum_stock, maximum_stock, reorder_quantity, default_location location_ref|null, qr_code, is_active, totals {on_hand, reserved, available, ordered}, stock_state, preferred_vendor vendor_ref|null, created_at, updated_at.
- `part_detail`: part + balances, vendors [{vendor: vendor_ref, vendor_part_number, url, preferred, last_price, last_ordered_at}], assets [asset_ref], open_purchase_requests [purchase_request_ref + item quantity outstanding], recent_transactions (10).
- `inventory_transaction`: id, type, part part_ref, location location_ref, quantity, on_hand_delta, reserved_delta, on_hand_after, reserved_after, counted_quantity, unit_cost, work_order {id, number, title}|null, purchase_request purchase_request_ref|null, reference_transaction_id, note, created_by user_ref, created_at.
- `work_order_part`: id, part part_ref (+ stock_state, totals), location location_ref|null, quantity_planned, quantity_reserved, quantity_issued, quantity_returned, readiness, note, created_at.
- `purchase_request`: purchase_request_ref + requester user_ref, project project_ref|null, vendor vendor_ref|null, needed_by, purpose, budget_code, shipping_amount, tax_amount, estimated_total, approved_total, item_count, order_reference, submitted_at, approved_at, ordered_at, received_at, created_at, updated_at, is_overdue (needed_by < today and status not received/declined/canceled).
- `purchase_request_detail`: purchase_request + items [{id, part part_ref|null, description, vendor_part_number, url, quantity, unit_price, line_total, received_quantity, receive_location location_ref|null}], events [{id, action, from_status, to_status, step, comment, actor user_ref, created_at}], decline_reason, available_actions [strings].

## Frontend (apps/ops-web)

- `/parts` master-detail: tabs All / Low stock / Out of stock, filters (type, location, vendor, critical), columns name+sku, available/unit with stock-state chip, locations, preferred vendor; right pane `PartDetail` with stock by location, actions Receive / Issue / Adjust / Transfer / Count (dialogs, visible only with `inventory.manage`), vendors, spare-for assets, open purchase requests, transaction history, comments and files. "New part" side pane. Low-stock tab has "Create purchase requests" for selected rows.
- `/parts/:id` deep link opens the same page with the pane selected.
- `/purchase-requests` master-detail: tabs Mine / Needs review / Open / Closed; right pane with header (PR-n, status chip, total), line items table, approval timeline, action bar driven by `available_actions`, receive dialog (per-line quantities and location), comments and files. "New purchase request" pane with part picker (creates free-text lines too), live totals.
- Work-order detail gains a "Parts" section: add part (picker shows available per location), per-line readiness chip, reserve / issue / return actions, readiness summary in the header.
- Sidebar: Parts Inventory and Purchase Requests lose their stage tags. Setup Center parts task links to `/parts`. Global search shows the two new groups.
- Component names: `features/parts/PartsPage.tsx` (`PartsPage`), `features/purchase-requests/PurchaseRequestsPage.tsx` (`PurchaseRequestsPage`), `features/work-orders/WorkOrderPartsSection.tsx` (`WorkOrderPartsSection`). API contracts in `src/api/contracts/{parts,purchaseRequests,workOrderParts}.ts`, queries in `src/api/queries/{parts,purchaseRequests,workOrderParts}.ts`.

## Acceptance tests (must exist)

1. Ledger: balances always equal the sum of transactions after a randomized sequence of 200 operations (property-style with a fixed seed); `reconcile` returns nothing.
2. Transactions cannot be updated or deleted through the ORM.
3. Issue beyond available → 409 `insufficient_stock` and nothing written.
4. Reserve → issue on a work order consumes the reservation, writes a parts cost entry, and the operations report `parts_cost` and project health `budget.used` include it; return writes the negative entry.
5. Low-stock notification fires once per part per day, only on the transition into low/out, to `inventory.manage` holders only.
6. Purchase request full path: draft → submit → treasurer approve → advisor approve (threshold) → order → partial receive → receive; receipts post, `ordered` totals fall to 0, weighted unit cost updates, `last_price` updates.
7. Self-approval 409; member cannot read another member's request (404); project lead reads requests on their project; treasurer cannot receive without `inventory.manage`.
8. Cross-organization ids 404 on every new endpoint.
9. `from-low-stock` groups by preferred vendor with the documented quantities.
10. Migration 0004 upgrades from 0003 and downgrades cleanly on SQLite.
