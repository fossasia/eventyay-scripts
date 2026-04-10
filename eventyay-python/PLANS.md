# Sold Ticket Migration Plan

## Goal

Add sold ticket/product migration after event migration, once the new-system product endpoints are available.

## Source Data In The Old System

- Use `/v1/events/{event_id}/tickets` for the ticket catalog and ticket metadata.
- Use `/v1/events/{event_id}/attendees?page[size]=3000&include=order,ticket` as the source of sold ticket rows.
- Use `/v1/events/{event_id}/order-statistics` as a validation endpoint for aggregate counts.

## Aggregation Rules

- Count sold products from attendee rows, not from the ticket catalog alone.
- Only count attendees whose included order has `status == "completed"`.
- Group the completed attendees by `ticket_id`.
- Enrich each grouped ticket with the included ticket data or the event ticket catalog.
- Follow pagination when `links.next` is present.

## Why This Approach

- `/v1/events/{event_id}/tickets` returns product details, but not sold counts.
- `/v1/events/{event_id}/order-statistics` returns totals, but not per-ticket breakdowns.
- `/v1/orders/{order_id}/tickets` is useful for inspection, but not enough by itself for reliable sold quantities.
- On the verified sample event `3048`, the attendee-derived completed count matched `order-statistics.tickets.completed` exactly (`1853`).

## Ticket Fields To Carry Forward

- old ticket id
- ticket name
- price
- description
- ticket type
- quantity
- sales start
- sales end
- order limits
- visibility and check-in flags

## Implementation Once New Endpoints Exist

- Add product creation calls after each event is created in the new system.
- Build a mapping from old ticket id to new product id.
- Create products before any future sold-order or attendee migration.
- Keep a per-event summary of created products and sold counts.
- Validate that the sum of migrated completed ticket counts matches the old `order-statistics` completed total.

## Open Items For The Next Step

- Add the new-system endpoints for product creation.
- Define the payload mapping from old ticket fields to the new product schema.
- Decide whether non-completed states (`expired`, `cancelled`, etc.) should also be stored for audit purposes.


## Endpoints in the new system to be used for this migration

`/api/v1/organizers/legacy/events/<event-slug>/products/` - for creating products in the new system, and later for validating migrated products.

`/api/v1/organizers/legacy/events/<event-slug>/quotas/` - for creating quotas in the new system, for added products.

## Sample Body for endpoints

For `/api/v1/organizers/legacy/events/<event-slug>/products/`:
```json
{
  "name": {"en": "Standard ticket"},
  "default_price": "23.00"
}
```

this would give a response like:
```json
{
    "id": 44,
    "category": null,
    "name": {
        "en": "Standarden ticket"
    },
    "internal_name": null,
    "active": true,
    "sales_channels": [
        "web"
    ],
    "description": null,
    "default_price": "23.00",
    "free_price": false,
    "tax_rate": "0.00",
    "tax_rule": null,
    "admission": false,
    "position": 0,
    "picture": null,
    "available_from": null,
    "available_until": null,
    "require_voucher": false,
    "hide_without_voucher": false,
    "allow_cancel": true,
    "require_bundling": false,
    "min_per_order": null,
    "max_per_order": null,
    "checkin_attention": false,
    "has_variations": false,
    "variations": [],
    "addons": [],
    "bundles": [],
    "original_price": null,
    "require_approval": false,
    "generate_tickets": null,
    "show_quota_left": null,
    "hidden_if_available": null,
    "allow_waitinglist": true,
    "issue_giftcard": false,
    "meta_data": {}
}
```
please note that the `id` field in the response is required for the next step of creating quotas.

For `/api/v1/organizers/legacy/events/<event-slug>/quotas/`:
```json
{
  "name": "Ticket Quota",
  "products": [44]
}
```

and the response would be:
```json
{
    "id": 18,
    "name": "Ticket Quota",
    "size": null,
    "products": [
        44
    ],
    "variations": [],
    "subevent": null,
    "closed": false,
    "close_when_sold_out": false,
    "release_after_exit": false
}
```
