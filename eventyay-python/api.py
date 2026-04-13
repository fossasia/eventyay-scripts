import argparse
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import os
import re
from time import sleep
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter


def load_dotenv(file_name=".env"):
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), file_name)
    if not os.path.exists(env_path):
        return

    with open(env_path, encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()

            if value[:1] == value[-1:] and value[:1] in {'"', "'"}:
                value = value[1:-1]

            os.environ.setdefault(key, value)


def format_env_token(token, prefix):
    cleaned = str(token or "").strip()
    if not cleaned:
        return ""
    return cleaned if cleaned.startswith(prefix) else f"{prefix}{cleaned}"


load_dotenv()

headers = {
    "accept": "application/vnd.api+json",
    "authorization": format_env_token(os.environ.get("EVENTYAY_JWT"), "JWT "),
}

url = "https://api.eventyay.com/v1"

new_system_url = "http://localhost:8000/api/v1/organizers/legacy/events/"

new_system_headers = {
    "Accept": "application/json, text/javascript",
    "Content-Type": "application/json",
    "Authorization": format_env_token(os.environ.get("OPENEVENT_AUTH_TOKEN"), "Token "),
    "Authourization": format_env_token(
        os.environ.get("OPENEVENT_AUTH_TOKEN"), "Token "
    ),
}

timezone_aliases = {
    "Singapore": "Asia/Singapore",
    "Asia/Calcutta": "Asia/Kolkata",
    "Asia/Rangoon": "Asia/Yangon",
    "Asia/Saigon": "Asia/Ho_Chi_Minh",
    "CET": "Europe/Berlin",
    "Etc/GMT+8": "Asia/Taipei",
    "America/Montreal": "America/Toronto",
    "Iran": "Asia/Tehran",
    "Etc/GMT-2": "Europe/Berlin",
}

session = requests.Session()
new_system_session = requests.Session()
new_system_session.mount(
    "http://",
    HTTPAdapter(pool_connections=1, pool_maxsize=1, pool_block=True),
)
valid_timezones = None
ENABLE_TICKET_SALES_VALIDATION = False
NEW_SYSTEM_WRITE_DELAY_SECONDS = float(
    os.environ.get("OPENEVENT_WRITE_DELAY_SECONDS", "0.1")
)


def get_old_api_headers():
    request_headers = dict(headers)
    request_headers["authorization"] = format_env_token(
        os.environ.get("EVENTYAY_JWT", request_headers["authorization"]), "JWT "
    )
    if not request_headers["authorization"]:
        raise RuntimeError("Missing EVENTYAY_JWT in .env or the shell environment")
    return request_headers


def get_new_system_headers():
    request_headers = dict(new_system_headers)
    token = os.environ.get("OPENEVENT_AUTH_TOKEN")
    if token:
        token_value = format_env_token(token, "Token ")
        request_headers["Authorization"] = token_value
        request_headers["Authourization"] = token_value
    if not request_headers["Authorization"]:
        raise RuntimeError(
            "Missing OPENEVENT_AUTH_TOKEN in .env or the shell environment"
        )
    return request_headers


def build_url(path):
    if not path:
        return None
    return urljoin(f"{url}/", path)


def build_new_system_url(*parts):
    suffix = "/".join(str(part).strip("/") for part in parts if part is not None)
    if not suffix:
        return new_system_url
    return urljoin(new_system_url, f"{suffix}/")


def build_next_url(base_url, path):
    if not path:
        return None
    return urljoin(base_url, path)


def request_with_retry(method, endpoint, request_headers, retries=3, **kwargs):
    last_error = None
    request_method = str(method).upper()
    active_session = (
        new_system_session if endpoint.startswith(new_system_url) else session
    )

    for attempt in range(retries):
        try:
            response = active_session.request(
                method,
                endpoint,
                headers=request_headers,
                timeout=30,
                **kwargs,
            )
        except requests.RequestException as error:
            last_error = error
            if attempt == retries - 1:
                print(
                    f"request failed: {request_method} {endpoint} - {error}",
                    flush=True,
                )
                raise

            retry_delay = 2**attempt
            print(
                f"request error: {request_method} {endpoint} - {error}; "
                f"retrying in {retry_delay}s ({attempt + 1}/{retries})",
                flush=True,
            )
            sleep(retry_delay)
            continue

        if response.status_code < 500:
            if (
                endpoint.startswith(new_system_url)
                and request_method in {"POST", "PATCH", "PUT", "DELETE"}
                and NEW_SYSTEM_WRITE_DELAY_SECONDS > 0
            ):
                sleep(NEW_SYSTEM_WRITE_DELAY_SECONDS)
            return response

        last_error = requests.HTTPError(response=response)
        if attempt == retries - 1:
            print(
                f"server error: {request_method} {endpoint} - "
                f"{response.status_code} {get_response_message(response)}",
                flush=True,
            )
            return response

        retry_delay = 2**attempt
        if "too many clients already" in response.text.lower():
            retry_delay = 130

        print(
            f"server error: {request_method} {endpoint} - "
            f"{response.status_code} {get_response_message(response)}; "
            f"retrying in {retry_delay}s ({attempt + 1}/{retries})",
            flush=True,
        )

        sleep(retry_delay)

    raise last_error


def fetch_json(endpoint, retries=3):
    response = request_with_retry(
        "GET",
        endpoint,
        get_old_api_headers(),
        retries=retries,
    )
    response.raise_for_status()
    return response.json()


def fetch_new_system_json(endpoint, method="GET", retries=5, payload=None):
    response = request_with_retry(
        method,
        endpoint,
        get_new_system_headers(),
        retries=retries,
        json=payload,
    )
    return response


def get_valid_timezones():
    global valid_timezones

    if valid_timezones is not None:
        return valid_timezones

    response = fetch_new_system_json(new_system_url, method="OPTIONS", retries=1)
    response.raise_for_status()
    timezone_choices = (
        response.json()
        .get("actions", {})
        .get("POST", {})
        .get("timezone", {})
        .get("choices", [])
    )
    valid_timezones = {choice["value"] for choice in timezone_choices}
    return valid_timezones


def iter_old_pages(endpoint):
    next_page = endpoint

    while next_page:
        payload = fetch_json(next_page)
        yield payload
        next_page = build_url(payload.get("links", {}).get("next"))


def get_paginated_results(endpoint):
    results = []
    next_page = endpoint

    while next_page:
        response = fetch_new_system_json(next_page)
        response.raise_for_status()
        payload = response.json()
        results.extend(payload.get("results", []))
        next_page = build_next_url(next_page, payload.get("next"))

    return results


def clean_string(value):
    if value is None:
        return ""
    return str(value).strip()


def build_translated_field(value, fallback=""):
    text = clean_string(value) or clean_string(fallback)
    return {"en": text} if text else {}


def format_datetime(value):
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return value

    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_decimal(value, default="0.00"):
    if value in (None, ""):
        return default

    try:
        decimal_value = Decimal(str(value)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    except (InvalidOperation, TypeError, ValueError):
        return default

    return f"{decimal_value:.2f}"


def normalize_limit(value):
    if value in (None, ""):
        return None

    try:
        limit = int(value)
    except (TypeError, ValueError):
        return None

    return limit if limit > 0 else None


def normalize_quantity(value):
    if value in (None, ""):
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_timezone(value):
    if not value:
        return "UTC"

    allowed_timezones = get_valid_timezones()

    if value in allowed_timezones:
        return value

    alias = timezone_aliases.get(value)
    if alias in allowed_timezones:
        return alias

    return "UTC"


def is_test_like(value):
    tokens = re.split(r"[^a-z0-9]+", clean_string(value).lower())
    return any(token.startswith("test") for token in tokens if token)


def should_skip_event(details):
    return is_test_like(details.get("name", "")) or is_test_like(
        details.get("slug", "")
    )


def get_order_counts():
    event_order_counts = Counter()
    sample_positions = {}
    order_position = 0

    for payload in iter_old_pages(f"{url}/orders?page[size]=5000"):
        for order in payload.get("data", []):
            order_position += 1
            event_link = (
                order.get("relationships", {})
                .get("event", {})
                .get("links", {})
                .get("related")
            )

            if not event_link:
                continue

            event_id = event_link.rstrip("/").rsplit("/", 1)[-1]
            event_order_counts[event_id] += 1
            sample_positions.setdefault(event_id, order_position)

    return event_order_counts, sample_positions


def build_event_details(attributes, event_id):
    source_timezone = attributes.get("timezone") or "UTC"
    identifier = attributes.get("identifier") or str(event_id)

    details = {
        "old_event_id": str(event_id),
        "name": clean_string(attributes.get("name")) or identifier,
        "slug": identifier,
        "currency": attributes.get("payment-currency") or "USD",
        "location": clean_string(attributes.get("location-name"))
        or clean_string(attributes.get("searchable-location-name")),
        "date_from": format_datetime(attributes.get("starts-at")),
        "date_to": format_datetime(attributes.get("ends-at")),
        "source_timezone": source_timezone,
        "timezone": normalize_timezone(source_timezone),
        "latitude": attributes.get("latitude"),
        "longitude": attributes.get("longitude"),
        "frontpage_text": clean_string(attributes.get("description")),
        "header_image_url": clean_string(attributes.get("original-image-url")),
        "logo_image_url": clean_string(attributes.get("logo-url")),
    }

    return details


def get_event_details(event_id, sample_position):
    try:
        payload = fetch_json(f"{url}/events/{event_id}")
        attributes = payload.get("data", {}).get("attributes", {})
        return build_event_details(attributes, event_id)
    except requests.HTTPError as error:
        status_code = getattr(error.response, "status_code", None)
        if status_code != 404:
            raise

    payload = fetch_json(
        f"{url}/orders?page[size]=1&include=event&page[number]={sample_position}",
        retries=1,
    )

    for item in payload.get("included", []):
        if item.get("type") == "event" and item.get("id") == str(event_id):
            return build_event_details(item.get("attributes", {}), event_id)

    return build_event_details({}, event_id)


def build_event_payload(details, order_count):
    if not details.get("slug"):
        raise ValueError("missing slug")

    if not details.get("date_from") or not details.get("date_to"):
        raise ValueError("missing event dates")

    payload = {
        "name": build_translated_field(details["name"], details["slug"]),
        "slug": details["slug"],
        "live": False,
        "testmode": False,
        "currency": details["currency"],
        "date_from": details["date_from"],
        "date_to": details["date_to"],
        "is_public": False,
        "location": build_translated_field(details.get("location", "")),
        "timezone": details["timezone"],
        "all_sales_channels": True,
    }

    latitude = details.get("latitude")
    longitude = details.get("longitude")
    if latitude not in (None, "") and longitude not in (None, ""):
        payload["geo_lat"] = latitude
        payload["geo_lon"] = longitude

    return payload


def build_event_content_payload(details):
    payload = {}

    frontpage_text = build_translated_field(details.get("frontpage_text", ""))
    if frontpage_text:
        payload["frontpage_text"] = frontpage_text

    # In the new system, `logo_image` is the header image and
    # `event_logo_image` is the event logo shown in the presale header.
    header_image_url = clean_string(details.get("header_image_url"))
    if header_image_url:
        payload["logo_image"] = header_image_url

    logo_image_url = clean_string(details.get("logo_image_url"))
    if logo_image_url:
        payload["event_logo_image"] = logo_image_url

    return payload


def get_response_message(response):
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip()

    if isinstance(payload, dict):
        if "detail" in payload:
            return str(payload["detail"])
        if "errors" in payload:
            return str(payload["errors"])
        return str(payload)

    return str(payload)


def is_already_created(response):
    try:
        payload = response.json()
    except ValueError:
        return False

    slug_errors = payload.get("slug")
    if not isinstance(slug_errors, list):
        return False

    return any("already been used" in error.lower() for error in slug_errors)


def get_existing_events():
    return {
        event.get("slug"): event
        for event in get_paginated_results(new_system_url)
        if event.get("slug")
    }


def get_event_tickets(event_id):
    tickets = []

    try:
        for payload in iter_old_pages(
            f"{url}/events/{event_id}/tickets?page[size]=1000"
        ):
            for ticket in payload.get("data", []):
                attributes = ticket.get("attributes", {})
                tickets.append(
                    {
                        "old_ticket_id": str(ticket.get("id")),
                        "name": clean_string(attributes.get("name"))
                        or f"Legacy Ticket {ticket.get('id')}",
                        "description": clean_string(attributes.get("description")),
                        "price": attributes.get("price"),
                        "quantity": normalize_quantity(attributes.get("quantity")),
                        "position": attributes.get("position") or 0,
                        "available_from": format_datetime(
                            attributes.get("sales-starts-at")
                        ),
                        "available_until": format_datetime(
                            attributes.get("sales-ends-at")
                        ),
                        "min_per_order": normalize_limit(attributes.get("min-order")),
                        "max_per_order": normalize_limit(attributes.get("max-order")),
                        "deleted_at": attributes.get("deleted-at"),
                        "is_hidden": bool(attributes.get("is-hidden")),
                        "is_checkin_restricted": bool(
                            attributes.get("is-checkin-restricted")
                        ),
                        "ticket_type": attributes.get("type") or "paid",
                        "raw_attributes": attributes,
                    }
                )
    except requests.HTTPError as error:
        status_code = getattr(error.response, "status_code", None)
        if status_code == 404:
            return []
        raise

    return tickets


def get_completed_ticket_sales(event_id):
    for page_size in (50, 20, 10):
        completed_sales = Counter()
        attendee_statuses = Counter()
        unknown_orders = 0

        try:
            first_page_url = f"{url}/events/{event_id}/orders?page[size]={page_size}&include=attendees,tickets"
            first_payload = fetch_json(first_page_url)
            page_payloads = [first_payload]

            total_count = first_payload.get("meta", {}).get("count")
            if total_count is not None:
                total_pages = max(1, (int(total_count) + page_size - 1) // page_size)
                for page_number in range(2, total_pages + 1):
                    page_payloads.append(
                        fetch_json(f"{first_page_url}&page[number]={page_number}")
                    )

            for payload in page_payloads:
                order_statuses = {
                    order.get("id"): order.get("attributes", {}).get("status")
                    for order in payload.get("data", [])
                }

                for attendee in payload.get("included", []):
                    if attendee.get("type") != "attendee":
                        continue

                    order_id = (
                        attendee.get("relationships", {})
                        .get("order", {})
                        .get("data", {})
                        .get("id")
                    )
                    ticket_id = attendee.get("attributes", {}).get("ticket-id")
                    status = order_statuses.get(order_id)

                    if not status:
                        unknown_orders += 1
                        continue

                    attendee_statuses[status] += 1
                    if status == "completed" and ticket_id:
                        completed_sales[str(ticket_id)] += 1

            return completed_sales, attendee_statuses, unknown_orders
        except requests.HTTPError as error:
            status_code = getattr(error.response, "status_code", None)
            if status_code and status_code >= 500 and page_size != 10:
                continue
            raise

    return Counter(), Counter(), 0


def get_order_statistics(event_id):
    payload = fetch_json(f"{url}/events/{event_id}/order-statistics")
    return payload.get("data", {}).get("attributes", {})


def get_existing_products(event_slug):
    products = get_paginated_results(build_new_system_url(event_slug, "products"))
    products_by_lookup_key = {}

    for product in products:
        internal_name = clean_string(product.get("internal_name"))
        if internal_name:
            products_by_lookup_key[f"internal:{internal_name}"] = product

        product_name = clean_string((product.get("name") or {}).get("en"))
        if product_name:
            signature = build_product_signature(
                product_name,
                product.get("default_price"),
                product.get("position"),
            )
            products_by_lookup_key[signature] = product

    return products_by_lookup_key, products


def get_existing_quotas(event_slug):
    quotas = get_paginated_results(build_new_system_url(event_slug, "quotas"))
    quotas_by_name = {}

    for quota in quotas:
        quota_name = quota.get("name")
        if quota_name:
            quotas_by_name[quota_name] = quota

    return quotas_by_name, quotas


def get_product_display_name(ticket):
    return (
        clean_string(ticket.get("name")) or f"Legacy Ticket {ticket['old_ticket_id']}"
    )


def build_product_signature(name, price, position):
    return f"signature:{name}|{format_decimal(price)}|{position or 0}"


def get_product_lookup_keys(ticket):
    return [
        f"internal:legacy-ticket-{ticket['old_ticket_id']}",
        build_product_signature(
            get_product_display_name(ticket),
            ticket.get("price"),
            ticket.get("position"),
        ),
    ]


def build_product_payload(event_details, ticket, sold_count):
    payload = {
        "name": build_translated_field(
            get_product_display_name(ticket), f"Legacy Ticket {ticket['old_ticket_id']}"
        ),
        "default_price": format_decimal(ticket.get("price")),
        "description": build_translated_field(ticket.get("description", "")),
        "admission": True,
        "position": ticket.get("position", 0),
        "available_from": ticket.get("available_from"),
        "available_until": ticket.get("available_until"),
        "min_per_order": ticket.get("min_per_order"),
        "max_per_order": ticket.get("max_per_order"),
        "checkin_attention": ticket.get("is_checkin_restricted", False),
        "active": ticket.get("deleted_at") is None,
    }

    if not payload["description"]:
        payload["description"] = None

    return payload


def build_quota_name(ticket):
    return f"legacy-ticket-{ticket['old_ticket_id']}"


def build_quota_payload(ticket, product_id):
    return {
        "name": build_quota_name(ticket),
        "size": ticket.get("quantity"),
        "products": [product_id],
        "closed": ticket.get("deleted_at") is not None,
    }


def create_event(payload):
    return fetch_new_system_json(new_system_url, method="POST", payload=payload)


def update_event_settings(event_slug, payload):
    return fetch_new_system_json(
        build_new_system_url(event_slug, "settings"),
        method="PATCH",
        payload=payload,
    )


def create_product(event_slug, payload):
    return fetch_new_system_json(
        build_new_system_url(event_slug, "products"),
        method="POST",
        payload=payload,
    )


def create_quota(event_slug, payload):
    return fetch_new_system_json(
        build_new_system_url(event_slug, "quotas"),
        method="POST",
        payload=payload,
    )


def migrate_products_for_event(details):
    tickets = get_event_tickets(details["old_event_id"])
    sales_lookup_failed = not ENABLE_TICKET_SALES_VALIDATION
    completed_sales = Counter()
    attendee_statuses = Counter()
    unknown_orders = 0
    completed_total = None

    if ENABLE_TICKET_SALES_VALIDATION:
        try:
            completed_sales, attendee_statuses, unknown_orders = (
                get_completed_ticket_sales(details["old_event_id"])
            )
            completed_total = sum(completed_sales.values())
            sales_lookup_failed = False
        except requests.RequestException as error:
            print(
                f"warning: could not validate completed ticket sales for {details['slug']} "
                f"({details['name']}) - {error}"
            )

    order_statistics = get_order_statistics(details["old_event_id"])
    stats_completed_total = (
        order_statistics.get("tickets", {}).get("completed")
        if isinstance(order_statistics, dict)
        else None
    )

    existing_products_by_lookup_key, _ = get_existing_products(details["slug"])
    existing_quotas_by_name, _ = get_existing_quotas(details["slug"])

    summary = {
        "products_created": 0,
        "products_existing": 0,
        "products_failed": 0,
        "quotas_created": 0,
        "quotas_existing": 0,
        "quotas_failed": 0,
        "completed_sold": completed_total,
        "completed_stat": stats_completed_total,
        "unknown_orders": unknown_orders,
        "attendee_statuses": dict(attendee_statuses),
        "validation_mismatch": (
            not sales_lookup_failed
            and stats_completed_total not in (None, completed_total)
        ),
        "validation_skipped": sales_lookup_failed,
    }

    if not tickets:
        print(
            f"warning: no legacy tickets found for {details['slug']} ({details['name']})"
        )
        return summary

    for ticket in tickets:
        old_ticket_id = ticket["old_ticket_id"]
        sold_count = completed_sales.get(old_ticket_id, 0)
        product = None
        for lookup_key in get_product_lookup_keys(ticket):
            product = existing_products_by_lookup_key.get(lookup_key)
            if product:
                break

        if product:
            summary["products_existing"] += 1
        else:
            product_response = create_product(
                details["slug"],
                build_product_payload(details, ticket, sold_count),
            )

            if product_response.status_code not in (200, 201):
                summary["products_failed"] += 1
                print(
                    f"failed product: {details['slug']} ticket {old_ticket_id} "
                    f"({ticket['name']}) - {product_response.status_code} "
                    f"{get_response_message(product_response)}"
                )
                continue

            product = product_response.json()
            for lookup_key in get_product_lookup_keys(ticket):
                existing_products_by_lookup_key[lookup_key] = product
            summary["products_created"] += 1
            print(
                f"created product: {details['slug']} ticket {old_ticket_id} "
                f"({ticket['name']}) sold={sold_count}"
            )

        quota_name = build_quota_name(ticket)
        if quota_name in existing_quotas_by_name:
            summary["quotas_existing"] += 1
            continue

        quota_response = create_quota(
            details["slug"],
            build_quota_payload(ticket, product["id"]),
        )

        if quota_response.status_code not in (200, 201):
            summary["quotas_failed"] += 1
            print(
                f"failed quota: {details['slug']} ticket {old_ticket_id} "
                f"({ticket['name']}) - {quota_response.status_code} "
                f"{get_response_message(quota_response)}"
            )
            continue

        existing_quotas_by_name[quota_name] = quota_response.json()
        summary["quotas_created"] += 1
        print(
            f"created quota: {details['slug']} ticket {old_ticket_id} "
            f"({ticket['name']})"
        )

    return summary


def migrate_events_with_more_than_ten_orders(limit=None):
    event_order_counts, sample_positions = get_order_counts()
    existing_events = get_existing_events()

    qualifying_events = []
    summary = {
        "events_created": 0,
        "events_existing": 0,
        "events_failed": 0,
        "events_updated": 0,
        "event_updates_failed": 0,
        "events_skipped": 0,
        "skipped_test_events": 0,
        "products_created": 0,
        "products_existing": 0,
        "products_failed": 0,
        "quotas_created": 0,
        "quotas_existing": 0,
        "quotas_failed": 0,
        "validation_mismatches": 0,
    }

    for event_id, order_count in event_order_counts.items():
        if order_count > 10:
            qualifying_events.append((event_id, order_count))

    total_qualifying_events = len(qualifying_events)
    if limit is not None:
        qualifying_events = qualifying_events[:limit]
        print(
            f"Test mode enabled: processing {len(qualifying_events)} of {total_qualifying_events} qualifying events"
        )

    for event_id, order_count in qualifying_events:
        details = get_event_details(event_id, sample_positions[event_id])

        if should_skip_event(details):
            summary["events_skipped"] += 1
            summary["skipped_test_events"] += 1
            print(
                f"skipped event: {details['slug']} ({details['name']}) - matched test filter"
            )
            continue

        try:
            event_payload = build_event_payload(details, order_count)
        except ValueError as error:
            summary["events_skipped"] += 1
            print(f"skipped event: {details['slug']} ({details['name']}) - {error}")
            continue

        event_content_payload = build_event_content_payload(details)

        event_exists = details["slug"] in existing_events
        if event_exists:
            summary["events_existing"] += 1
            print(f"existing event: {details['slug']} ({details['name']})")
        else:
            event_response = create_event(event_payload)

            if event_response.status_code in (200, 201):
                existing_events[details["slug"]] = event_response.json()
                summary["events_created"] += 1
                print(
                    f"created event: {details['slug']} ({details['name']}) - {order_count} orders"
                )
            elif event_response.status_code == 400 and is_already_created(
                event_response
            ):
                existing_events[details["slug"]] = {"slug": details["slug"]}
                summary["events_existing"] += 1
                print(f"existing event: {details['slug']} ({details['name']})")
            else:
                summary["events_failed"] += 1
                print(
                    f"failed event: {details['slug']} ({details['name']}) - "
                    f"{event_response.status_code} {get_response_message(event_response)}"
                )
                continue

        if event_content_payload:
            event_update_response = update_event_settings(
                details["slug"], event_content_payload
            )
            if event_update_response.status_code in (200, 202, 204):
                summary["events_updated"] += 1
                print(f"updated event settings: {details['slug']} ({details['name']})")
            else:
                summary["event_updates_failed"] += 1
                print(
                    f"warning: failed to update event settings for {details['slug']} "
                    f"({details['name']}) - {event_update_response.status_code} "
                    f"{get_response_message(event_update_response)}"
                )

        product_summary = migrate_products_for_event(details)
        for key in (
            "products_created",
            "products_existing",
            "products_failed",
            "quotas_created",
            "quotas_existing",
            "quotas_failed",
        ):
            summary[key] += product_summary[key]

        if product_summary["validation_mismatch"]:
            summary["validation_mismatches"] += 1
            print(
                f"validation mismatch: {details['slug']} ({details['name']}) - "
                f"completed attendees={product_summary['completed_sold']} "
                f"stats completed={product_summary['completed_stat']}"
            )

        print(
            f"event product summary: {details['slug']} - "
            f"products created={product_summary['products_created']}, "
            f"products existing={product_summary['products_existing']}, "
            f"products failed={product_summary['products_failed']}, "
            f"quotas created={product_summary['quotas_created']}, "
            f"quotas existing={product_summary['quotas_existing']}, "
            f"quotas failed={product_summary['quotas_failed']}, "
            f"completed sold={product_summary['completed_sold']}, "
            f"completed stats={product_summary['completed_stat']}"
        )

    print(f"Created events: {summary['events_created']}")
    print(f"Existing events: {summary['events_existing']}")
    print(f"Updated events: {summary['events_updated']}")
    print(f"Failed event updates: {summary['event_updates_failed']}")
    print(f"Skipped events: {summary['events_skipped']}")
    print(f"Skipped test events: {summary['skipped_test_events']}")
    print(f"Failed events: {summary['events_failed']}")
    print(f"Created products: {summary['products_created']}")
    print(f"Existing products: {summary['products_existing']}")
    print(f"Failed products: {summary['products_failed']}")
    print(f"Created quotas: {summary['quotas_created']}")
    print(f"Existing quotas: {summary['quotas_existing']}")
    print(f"Failed quotas: {summary['quotas_failed']}")
    print(f"Validation mismatches: {summary['validation_mismatches']}")
    print(f"Processed qualifying events: {len(qualifying_events)}")
    print(f"Total qualifying events: {total_qualifying_events}")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-test",
        "--test",
        action="store_true",
        dest="test_mode",
        help="Run the migration only for the first 50 qualifying events.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    migrate_events_with_more_than_ten_orders(limit=50 if args.test_mode else None)
