# Agents.md

# Structure
- The main working file is `api.py`.
- Planning notes live in `PLAN.md` and `PLANS.md`.
- Secrets now live in `.env`, with placeholders in `.env.sample`.

# Current Migration Scope
- Only migrate legacy events with more than 10 orders.
- Skip test-like events based on the event name or slug containing a `test...` token.
- Use the old event identifier as the new event slug.
- Migrate products and quotas after the event exists in the new system.

# Old System
- Base URL: `https://api.eventyay.com/v1`
- Auth env var: `EVENTYAY_JWT`
- Event details come from `/events/{id}` with a fallback through `/orders?page[size]=1&include=event&page[number]=...` for deleted legacy events.
- Ticket catalog comes from `/events/{id}/tickets`.
- Some legacy events return `404` on `/events/{id}/tickets`; the script warns and skips product import for those events.
- Old attendee/order endpoints are flaky and can return intermittent `500` errors on some pages.

# New System
- Base URL: `http://localhost:8000/api/v1/organizers/legacy/events/`
- Auth env var: `OPENEVENT_AUTH_TOKEN`
- Event creation is done against the organizer event endpoint above.
- Product creation is done at `/api/v1/organizers/legacy/events/{event_slug}/products/`.
- Quota creation is done at `/api/v1/organizers/legacy/events/{event_slug}/quotas/`.
- The local API can intermittently fail with `too many clients already`; the script retries and can be rerun safely.

# Current Script Behavior
- Keep the `headers` and `url` variables in `api.py`; their auth values are loaded from `.env`.
- Timezone aliases are normalized before event creation.
- Product public names use the original legacy ticket names.
- New product payloads no longer send `internal_name`.
- Existing products are matched by either legacy `internal_name` values from earlier runs or by a name/price/position signature, so reruns stay idempotent.
- Quotas use deterministic names: `legacy-ticket-{old_ticket_id}`.
- Ticket sales validation code exists, but `ENABLE_TICKET_SALES_VALIDATION = False` because the legacy attendee/order pagination is unreliable and slows or blocks the import.

# Migration Status
- Event migration is implemented and resumable.
- Product and quota migration is implemented and resumable.
- A partial run already created many events/products/quotas in the local system.
- Rerunning `python api.py` continues from the current state instead of duplicating imported records.

# Plans
- Read `PLAN.md` first.
- `PLAN.md` points to `PLANS.md` for the detailed sold-ticket migration notes and broader migration plan.

# Testing
- Source the environment with `. .venv/bin/activate`
- Syntax check with `python -m py_compile api.py`
- Run the migration with `python api.py`

# Environment Files
- `.env` contains the active local tokens for the current session.
- `.env.sample` documents the required variables for a fresh setup.
- `.gitignore` ignores `.env`.
