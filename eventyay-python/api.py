import argparse
import builtins
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import os
import re
import sys
import threading
from time import sleep, time
from urllib.parse import urljoin, urlparse

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

new_system_url = "http://localhost:8000/api/v1/organizers/ev/events/"

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
DB_OVERLOAD_RETRY_SECONDS = float(
    os.environ.get("OPENEVENT_DB_OVERLOAD_RETRY_SECONDS", "130")
)
SHOW_STATUS_TIMER = os.environ.get("OPENEVENT_SHOW_TIMER", "1").lower() not in {
    "0",
    "false",
    "no",
}
STATUS_REFRESH_SECONDS = float(os.environ.get("OPENEVENT_STATUS_REFRESH_SECONDS", "1"))
SPEAKER_IMPORT_BATCH_SIZE = int(os.environ.get("OPENEVENT_SPEAKER_IMPORT_BATCH_SIZE", "25"))
SUBMISSION_IMPORT_BATCH_SIZE = int(
    os.environ.get("OPENEVENT_SUBMISSION_IMPORT_BATCH_SIZE", "25")
)
ORDER_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ1234567890"
FOSSASIA_EVENT_IDENTIFIER = "45da88b7"
DEFAULT_TRACK_COLOR = "#3AA57C"
LEGACY_SPEAKER_IDENTIFIER_PREFIX = "lspk"
LEGACY_SPEAKER_IDENTIFIER_MAX_LENGTH = 16
LEGACY_ORDER_STATUS_MAP = {
    "completed": {"create_status": "p", "final_status": "p"},
    "confirmed": {"create_status": "p", "final_status": "p"},
    "pending": {"create_status": "n", "final_status": "n"},
    "placed": {"create_status": "n", "final_status": "n"},
    "initializing": {"create_status": "n", "final_status": "n"},
    "expired": {"create_status": "n", "final_status": "e"},
    "cancelled": {"create_status": "n", "final_status": "c"},
    "canceled": {"create_status": "n", "final_status": "c"},
}
MANUAL_PAYMENT_PROVIDER = "manual"
HIDDEN_FROM_STARTPAGE_PAYLOAD = {
    "startpage_visible": False,
    "startpage_featured": False,
}
language_aliases = {
    "english": "en",
    "en": "en",
    "german": "de",
    "de": "de",
    "spanish": "es",
    "es": "es",
    "french": "fr",
    "fr": "fr",
    "thai": "th",
    "th": "th",
    "japanese": "ja",
    "ja": "ja",
    "chinese": "zh",
    "zh": "zh",
    "portuguese": "pt",
    "pt": "pt",
    "polish": "pl",
    "pl": "pl",
    "russian": "ru",
    "ru": "ru",
}
_status_lock = threading.Lock()
_status_stop_event = threading.Event()
_status_thread = None
_status_started_at = None
_status_last_line_length = 0


def should_render_status_timer():
    return SHOW_STATUS_TIMER and sys.stderr.isatty()


def format_elapsed(seconds):
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"


def get_status_line():
    if _status_started_at is None:
        return ""
    return f"[elapsed {format_elapsed(time() - _status_started_at)}]"


def clear_status_line_locked():
    global _status_last_line_length
    if not should_render_status_timer() or not _status_last_line_length:
        return

    builtins.print(
        f"\r{' ' * _status_last_line_length}\r",
        end="",
        file=sys.stderr,
        flush=True,
    )
    _status_last_line_length = 0


def render_status_line_locked():
    global _status_last_line_length
    if not should_render_status_timer():
        return

    status_line = get_status_line()
    if not status_line:
        return

    padded_line = status_line.ljust(_status_last_line_length)
    builtins.print(f"\r{padded_line}", end="", file=sys.stderr, flush=True)
    _status_last_line_length = len(status_line)


def status_timer_worker():
    while not _status_stop_event.wait(STATUS_REFRESH_SECONDS):
        with _status_lock:
            render_status_line_locked()


def start_status_timer():
    global _status_thread, _status_started_at
    if not should_render_status_timer() or _status_thread is not None:
        return

    _status_stop_event.clear()
    _status_started_at = time()
    _status_thread = threading.Thread(target=status_timer_worker, daemon=True)
    _status_thread.start()

    with _status_lock:
        render_status_line_locked()


def stop_status_timer():
    global _status_thread, _status_started_at
    if _status_thread is None:
        return

    _status_stop_event.set()
    _status_thread.join(timeout=STATUS_REFRESH_SECONDS + 1)

    with _status_lock:
        clear_status_line_locked()

    _status_started_at = None
    _status_thread = None


def print(*args, **kwargs):
    if not should_render_status_timer():
        return builtins.print(*args, **kwargs)

    with _status_lock:
        clear_status_line_locked()
        builtins.print(*args, **kwargs)
        render_status_line_locked()


def get_old_api_headers(include_auth=True):
    request_headers = dict(headers)
    token_value = format_env_token(
        os.environ.get("EVENTYAY_JWT", request_headers.get("authorization", "")),
        "JWT ",
    )
    if include_auth and token_value:
        request_headers["authorization"] = token_value
    else:
        request_headers.pop("authorization", None)
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
            retry_delay = DB_OVERLOAD_RETRY_SECONDS

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
    if response.status_code == 401 and endpoint.startswith(url):
        public_response = request_with_retry(
            "GET",
            endpoint,
            get_old_api_headers(include_auth=False),
            retries=1,
        )
        if public_response.status_code < 400:
            return public_response.json()
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


def get_localized_text(value):
    if isinstance(value, dict):
        return clean_string(value.get("en")) or clean_string(
            next(iter(value.values()), "")
        )
    return clean_string(value)


def normalize_token(value):
    return re.sub(r"[^a-z0-9]+", "", clean_string(value).lower())


def extract_url_domain(value):
    raw_value = clean_string(value)
    if not raw_value:
        return ""

    candidate = raw_value if "://" in raw_value else f"https://{raw_value}"
    parsed = urlparse(candidate)
    return clean_string(parsed.netloc.split("@")[-1].split(":")[0]).lower()


def extract_email_domain(value):
    email = clean_string(value).lower()
    if "@" not in email:
        return ""
    return email.rsplit("@", 1)[-1]


def get_partner_domains(partner):
    domains = {
        domain
        for domain in (
            extract_url_domain(partner.get("url")),
            extract_url_domain(partner.get("contact_url")),
            extract_email_domain(partner.get("email")),
        )
        if domain
    }
    return sorted(domains)


def build_partner_lookup_keys(partner):
    normalized_name = normalize_token(get_localized_text(partner.get("name")))
    if not normalized_name:
        return []

    domains = get_partner_domains(partner)
    keys = [f"name:{normalized_name}|domain:{domain}" for domain in domains]
    keys.append(f"name:{normalized_name}|any")
    return keys


def choose_preferred_text(current, incoming):
    current_text = clean_string(current)
    incoming_text = clean_string(incoming)
    if not current_text:
        return incoming_text
    if len(incoming_text) > len(current_text):
        return incoming_text
    return current_text


def normalize_country_code(value):
    country = clean_string(value).upper()
    if re.fullmatch(r"[A-Z]{2}", country):
        return country
    return None


def build_stable_order_code(identifier, length=12):
    normalized_identifier = clean_string(identifier) or "legacy-order"
    digest = hashlib.sha1(normalized_identifier.encode("utf-8")).digest()
    number = int.from_bytes(digest, "big")
    encoded = []

    while number:
        number, remainder = divmod(number, len(ORDER_CODE_ALPHABET))
        encoded.append(ORDER_CODE_ALPHABET[remainder])

    if not encoded:
        encoded.append(ORDER_CODE_ALPHABET[0])

    code = "".join(encoded)
    padded = (code + (ORDER_CODE_ALPHABET[0] * length))[:length]
    return padded


def map_legacy_order_status(value):
    status = clean_string(value).lower()
    return LEGACY_ORDER_STATUS_MAP.get(
        status, {"create_status": "n", "final_status": "n"}
    )


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

    for payload in iter_old_pages(f"{url}/orders?page[size]=5000"):
        for order in payload.get("data", []):
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

    return event_order_counts


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
        "state": clean_string(attributes.get("state")).lower(),
        "schedule_published_on": format_datetime(
            attributes.get("schedule-published-on")
            or attributes.get("scheduled-published-on")
        ),
        "frontpage_text": clean_string(attributes.get("description")),
        "header_image_url": clean_string(attributes.get("original-image-url")),
        "logo_image_url": clean_string(attributes.get("logo-url")),
    }

    return details


def get_event_details(event_id):
    try:
        payload = fetch_json(f"{url}/events/{event_id}")
        attributes = payload.get("data", {}).get("attributes", {})
        return build_event_details(attributes, event_id)
    except requests.HTTPError as error:
        status_code = getattr(error.response, "status_code", None)
        if status_code != 404:
            raise

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
        **HIDDEN_FROM_STARTPAGE_PAYLOAD,
        "testmode": False,
        "currency": details["currency"],
        "date_from": details["date_from"],
        "date_to": details["date_to"],
        "is_public": False,
        "location": build_translated_field(details.get("location", "")),
        "timezone": details["timezone"],
        "all_sales_channels": True,
        "plugins": ["exhibition"],
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
    header_image_url = normalize_external_url(details.get("header_image_url"))
    if header_image_url:
        payload["logo_image"] = header_image_url

    logo_image_url = normalize_external_url(details.get("logo_image_url"))
    if logo_image_url:
        payload["event_logo_image"] = logo_image_url

    return payload


def append_page_size(endpoint, page_size=1000):
    separator = "&" if "?" in endpoint else "?"
    if "page[size]=" in endpoint:
        return endpoint
    return f"{endpoint}{separator}page[size]={page_size}"


def parse_duration_minutes(value, default=30):
    raw_value = clean_string(value)
    if not raw_value:
        return default

    match = re.fullmatch(r"(?:(\d+):)?(\d{1,2})", raw_value)
    if match:
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2))
        total_minutes = (hours * 60) + minutes
        return total_minutes if total_minutes > 0 else default

    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def normalize_language_code(value):
    raw_value = clean_string(value).lower()
    if not raw_value:
        return ""
    if raw_value in language_aliases:
        return language_aliases[raw_value]
    if re.fullmatch(r"[a-z]{2}(-[a-z]{2})?", raw_value):
        return raw_value
    return ""


def normalize_track_color(value):
    color = clean_string(value)
    if re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
        return color.upper()
    if re.fullmatch(r"#[0-9A-Fa-f]{3}", color):
        return color.upper()
    return DEFAULT_TRACK_COLOR


def build_legacy_speaker_identifier(old_speaker_id):
    cleaned = clean_string(old_speaker_id)
    candidate = f"{LEGACY_SPEAKER_IDENTIFIER_PREFIX}{cleaned}"
    if cleaned and re.fullmatch(r"[A-Za-z0-9]+", cleaned) and len(candidate) <= LEGACY_SPEAKER_IDENTIFIER_MAX_LENGTH:
        return candidate

    suffix = hashlib.sha1((cleaned or "unknown").encode("utf-8")).hexdigest()
    suffix_length = LEGACY_SPEAKER_IDENTIFIER_MAX_LENGTH - len(LEGACY_SPEAKER_IDENTIFIER_PREFIX)
    return f"{LEGACY_SPEAKER_IDENTIFIER_PREFIX}{suffix[:suffix_length]}"


def build_legacy_submission_code(old_session_id):
    return build_stable_order_code(f"legacy-session:{clean_string(old_session_id)}")


def get_related_endpoint(item, relation_name):
    relation_path = (
        item.get("relationships", {})
        .get(relation_name, {})
        .get("links", {})
        .get("related")
    )
    return build_url(relation_path)


def get_related_resource(item, relation_name, cache):
    endpoint = get_related_endpoint(item, relation_name)
    if not endpoint:
        return None
    if endpoint in cache:
        return cache[endpoint]
    try:
        payload = fetch_json(endpoint)
    except requests.HTTPError as error:
        if getattr(error.response, "status_code", None) == 404:
            cache[endpoint] = None
            return None
        raise
    resource = payload.get("data")
    cache[endpoint] = resource
    return resource


def get_related_collection(item, relation_name, cache, page_size=100):
    endpoint = get_related_endpoint(item, relation_name)
    if not endpoint:
        return []
    paged_endpoint = append_page_size(endpoint, page_size=page_size)
    if paged_endpoint in cache:
        return cache[paged_endpoint]
    resources = []
    try:
        for payload in iter_old_pages(paged_endpoint):
            resources.extend(payload.get("data", []))
    except requests.HTTPError as error:
        if getattr(error.response, "status_code", None) == 404:
            cache[paged_endpoint] = []
            return []
        raise
    cache[paged_endpoint] = resources
    return resources


def get_event_session_types(event_id):
    session_types = []
    for payload in iter_old_pages(
        append_page_size(f"{url}/events/{event_id}/session-types")
    ):
        for item in payload.get("data", []):
            attributes = item.get("attributes", {})
            if attributes.get("deleted-at"):
                continue
            session_types.append(
                {
                    "old_session_type_id": str(item.get("id")),
                    "name": clean_string(attributes.get("name"))
                    or f"Legacy Session Type {item.get('id')}",
                    "length": clean_string(attributes.get("length")),
                }
            )
    return session_types


def get_event_tracks(event_id):
    tracks = []
    for payload in iter_old_pages(append_page_size(f"{url}/events/{event_id}/tracks")):
        for position, item in enumerate(payload.get("data", []), start=len(tracks)):
            attributes = item.get("attributes", {})
            if attributes.get("deleted-at"):
                continue
            tracks.append(
                {
                    "old_track_id": str(item.get("id")),
                    "name": clean_string(attributes.get("name"))
                    or f"Legacy Track {item.get('id')}",
                    "description": clean_string(attributes.get("description")),
                    "color": normalize_track_color(attributes.get("color")),
                    "position": position,
                }
            )
    return tracks


def get_event_speakers(event_id):
    speakers = []
    for payload in iter_old_pages(
        append_page_size(f"{url}/events/{event_id}/speakers")
    ):
        for item in payload.get("data", []):
            attributes = item.get("attributes", {})
            if attributes.get("deleted-at"):
                continue
            speakers.append(item)
    return speakers


def get_event_sessions(event_id):
    sessions = []
    for payload in iter_old_pages(
        append_page_size(f"{url}/events/{event_id}/sessions")
    ):
        for item in payload.get("data", []):
            attributes = item.get("attributes", {})
            if attributes.get("deleted-at"):
                continue
            sessions.append(item)
    return sessions


def build_submission_type_payload(session_type):
    return {
        "name": build_translated_field(session_type["name"], session_type["name"]),
        "default_duration": parse_duration_minutes(
            session_type.get("length"), default=30
        ),
        "requires_access_code": False,
    }


def build_track_payload(track):
    return {
        "name": build_translated_field(track["name"], track["name"]),
        "description": build_translated_field(track.get("description", "")),
        "color": normalize_track_color(track.get("color")),
        "position": track.get("position") or 0,
        "requires_access_code": False,
    }


def get_speaker_avatar_url(attributes):
    for key in (
        "photo-url",
        "thumbnail-image-url",
        "small-image-url",
        "icon-image-url",
    ):
        avatar_url = normalize_external_url(attributes.get(key))
        if avatar_url:
            return avatar_url
    return ""


def parse_legacy_featured_position(value):
    if isinstance(value, (list, tuple)):
        for item in value:
            position = parse_legacy_featured_position(item)
            if position is not None:
                return position
        return None

    if isinstance(value, dict):
        for key in ("position", "sort", "order"):
            position = parse_legacy_featured_position(value.get(key))
            if position is not None:
                return position
        return None

    raw_value = clean_string(value)
    if not raw_value:
        return None
    try:
        position = int(raw_value)
    except (TypeError, ValueError):
        return None
    return position if position >= 0 else None


def build_speaker_import_record(speaker_item):
    attributes = speaker_item.get("attributes", {})
    old_speaker_id = str(speaker_item.get("id"))
    name = clean_string(attributes.get("name")) or f"Legacy Speaker {old_speaker_id}"
    email = (
        clean_string(attributes.get("email"))
        or f"{build_legacy_speaker_identifier(old_speaker_id)}@eventyay.invalid"
    )
    biography = clean_string(attributes.get("long-biography")) or clean_string(
        attributes.get("short-biography")
    )
    avatar_url = get_speaker_avatar_url(attributes)
    featured_position = parse_legacy_featured_position(
        attributes.get("speaker-positions")
    )
    extras = {
        "website": clean_string(attributes.get("website")),
        "twitter": clean_string(attributes.get("twitter")),
        "facebook": clean_string(attributes.get("facebook")),
        "github": clean_string(attributes.get("github")),
        "linkedin": clean_string(attributes.get("linkedin")),
        "company": clean_string(attributes.get("organisation")),
        "job_title": clean_string(attributes.get("position")),
        "phone": clean_string(attributes.get("mobile")),
        "city": clean_string(attributes.get("city")),
        "country": clean_string(attributes.get("country")),
        "location": clean_string(attributes.get("location")),
        "speaking_experience": clean_string(attributes.get("speaking-experience")),
        "gender": clean_string(attributes.get("gender")),
        "heard_from": clean_string(attributes.get("heard-from")),
        "sponsorship_required": clean_string(attributes.get("sponsorship-required")),
    }
    speaker_record = {
        "identifier": build_legacy_speaker_identifier(old_speaker_id),
        "email": email,
        "full_name": name,
        "biography": biography,
    }
    if avatar_url:
        speaker_record["avatar_url"] = avatar_url
    if attributes.get("is-featured") is not None:
        speaker_record["is_featured"] = attributes.get("is-featured")
    if featured_position is not None:
        speaker_record["featured_position"] = featured_position
    speaker_extras = {
        key: value for key, value in extras.items() if value not in (None, "", [], {})
    }
    if speaker_extras:
        speaker_record["speaker_extras"] = speaker_extras
    return speaker_record


def build_legacy_speaker_refs(speaker_item):
    refs = []
    identifier = ""
    if speaker_item.get("id") is not None:
        identifier = build_legacy_speaker_identifier(speaker_item.get("id"))
        refs.append(identifier)

    attributes = speaker_item.get("attributes", {})
    email = clean_string(attributes.get("email")) or (f"{identifier}@eventyay.invalid" if identifier else "")
    if email:
        refs.append(email)

    return refs


def build_room_metadata(microlocation_item):
    if not microlocation_item:
        return None
    attributes = microlocation_item.get("attributes", {})
    return {
        "id": str(microlocation_item.get("id")),
        "name": clean_string(attributes.get("name")),
        "room": clean_string(attributes.get("room")),
        "floor": attributes.get("floor"),
        "latitude": attributes.get("latitude"),
        "longitude": attributes.get("longitude"),
    }


def get_room_display_name(room_metadata):
    if not room_metadata:
        return ""
    return clean_string(room_metadata.get("room")) or clean_string(
        room_metadata.get("name")
    )


def extract_slide_links(value):
    links = []
    for item in re.split(r"[\n,]", clean_string(value)):
        cleaned = normalize_external_url(item)
        if cleaned and is_pdf_link(cleaned):
            links.append(cleaned)
    return links


def map_legacy_submission_state(value):
    state = clean_string(value).lower()
    mapping = {
        "confirmed": "confirmed",
        "accepted": "accepted",
        "submitted": "submitted",
        "pending": "submitted",
        "draft": "draft",
        "rejected": "rejected",
        "withdrawn": "withdrawn",
        "deleted": "deleted",
        "canceled": "canceled",
        "cancelled": "canceled",
    }
    return mapping.get(state, "submitted")


def build_schedule_version(details):
    published_at = clean_string(details.get("schedule_published_on"))
    if not published_at:
        return "legacy-import"
    normalized = published_at.replace(":", "").replace("-", "")
    normalized = normalized.replace("T", "-").replace("Z", "")
    return f"legacy-{normalized}"


def normalize_external_url(value):
    cleaned = clean_string(value)
    if cleaned.startswith("//"):
        return f"https:{cleaned}"
    return cleaned


def is_pdf_link(value):
    return urlparse(value).path.lower().endswith(".pdf")


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


def is_api_version_error(response):
    if response is None or getattr(response, "status_code", None) != 400:
        return False
    return "API version not supported" in get_response_message(response)


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


def build_legacy_partner_record(item, source_type):
    attributes = item.get("attributes", {})
    return {
        "legacy_ids": [str(item.get("id"))],
        "source_types": [source_type],
        "name": clean_string(attributes.get("name"))
        or f"Legacy {source_type.title()} {item.get('id')}",
        "description": clean_string(attributes.get("description")),
        "url": clean_string(attributes.get("url")),
        "email": clean_string(attributes.get("contact-email")),
        "contact_url": clean_string(attributes.get("contact-link")),
        "video_url": clean_string(attributes.get("video-url")),
        "slides_url": clean_string(attributes.get("slides-url")),
        "logo_url": clean_string(attributes.get("logo-url")),
        "header_image_url": clean_string(attributes.get("banner-url")),
        "is_exhibitor": source_type == "exhibitor",
        "is_sponsor": source_type == "sponsor",
        "sponsor_group_name": clean_string(attributes.get("type")),
        "sponsor_group_level": normalize_quantity(attributes.get("level")),
    }


def can_merge_partner_records(current, incoming):
    if normalize_token(current.get("name")) != normalize_token(incoming.get("name")):
        return False

    current_domains = set(get_partner_domains(current))
    incoming_domains = set(get_partner_domains(incoming))
    if (
        current_domains
        and incoming_domains
        and current_domains.isdisjoint(incoming_domains)
    ):
        return False

    return True


def merge_partner_records(current, incoming):
    merged = dict(current)
    merged["legacy_ids"] = sorted(
        {str(value) for value in current["legacy_ids"] + incoming["legacy_ids"]}
    )
    merged["source_types"] = sorted(
        set(current["source_types"]) | set(incoming["source_types"])
    )
    merged["is_exhibitor"] = bool(current.get("is_exhibitor")) or bool(
        incoming.get("is_exhibitor")
    )
    merged["is_sponsor"] = bool(current.get("is_sponsor")) or bool(
        incoming.get("is_sponsor")
    )

    for field in (
        "name",
        "url",
        "email",
        "contact_url",
        "video_url",
        "slides_url",
        "logo_url",
        "header_image_url",
    ):
        if not clean_string(merged.get(field)):
            merged[field] = incoming.get(field)

    merged["description"] = choose_preferred_text(
        merged.get("description"), incoming.get("description")
    )

    if not clean_string(merged.get("sponsor_group_name")):
        merged["sponsor_group_name"] = incoming.get("sponsor_group_name")

    if merged.get("sponsor_group_level") is None:
        merged["sponsor_group_level"] = incoming.get("sponsor_group_level")

    return merged


def get_event_partners(event_id):
    merged_partners = []

    for source_type in ("exhibitor", "sponsor"):
        endpoint = f"{url}/events/{event_id}/{source_type}s?page[size]=1000"
        try:
            for payload in iter_old_pages(endpoint):
                for item in payload.get("data", []):
                    record = build_legacy_partner_record(item, source_type)
                    matched = False
                    for index, existing_record in enumerate(merged_partners):
                        if can_merge_partner_records(existing_record, record):
                            merged_partners[index] = merge_partner_records(
                                existing_record, record
                            )
                            matched = True
                            break
                    if not matched:
                        merged_partners.append(record)
        except requests.HTTPError as error:
            if getattr(error.response, "status_code", None) == 404:
                continue
            raise

    return merged_partners


def build_exhibitor_payload(partner):
    payload = {
        "name": build_translated_field(partner.get("name"), "Legacy Partner"),
        "description": build_translated_field(partner.get("description", "")) or None,
        "url": clean_string(partner.get("url")) or None,
        "email": clean_string(partner.get("email")) or None,
        "contact_url": clean_string(partner.get("contact_url")) or None,
        "video_url": clean_string(partner.get("video_url")) or None,
        "slides_url": clean_string(partner.get("slides_url")) or None,
        "logo_url": clean_string(partner.get("logo_url")) or None,
        "header_image_url": clean_string(partner.get("header_image_url")) or None,
        "is_exhibitor": bool(partner.get("is_exhibitor")),
        "is_sponsor": bool(partner.get("is_sponsor")),
    }

    sponsor_group_name = clean_string(partner.get("sponsor_group_name"))
    if payload["is_sponsor"] and sponsor_group_name:
        payload["sponsor_group_name"] = sponsor_group_name

    sponsor_group_level = partner.get("sponsor_group_level")
    if payload["is_sponsor"] and sponsor_group_level is not None:
        payload["sponsor_group_level"] = sponsor_group_level

    return payload


def get_existing_exhibitors(event_slug):
    exhibitors = get_paginated_results(build_new_system_url(event_slug, "exhibitors"))
    exhibitors_by_lookup_key = defaultdict(list)

    for exhibitor in exhibitors:
        for lookup_key in build_partner_lookup_keys(exhibitor):
            exhibitors_by_lookup_key[lookup_key].append(exhibitor)

    return exhibitors_by_lookup_key


def find_matching_exhibitor(exhibitors_by_lookup_key, partner):
    matches = {}
    for lookup_key in build_partner_lookup_keys(partner):
        for exhibitor in exhibitors_by_lookup_key.get(lookup_key, []):
            matches[exhibitor["id"]] = exhibitor

    if len(matches) == 1:
        return next(iter(matches.values()))
    return None


def partner_payload_matches(existing, payload):
    fields = (
        "url",
        "email",
        "contact_url",
        "video_url",
        "slides_url",
        "logo_url",
        "header_image_url",
        "is_exhibitor",
        "is_sponsor",
        "sponsor_group_name",
        "sponsor_group_level",
    )

    if get_localized_text(existing.get("name")) != get_localized_text(
        payload.get("name")
    ):
        return False

    if get_localized_text(existing.get("description")) != get_localized_text(
        payload.get("description")
    ):
        return False

    for field in fields:
        if clean_string(existing.get(field)) != clean_string(payload.get(field)):
            return False

    return True


def create_exhibitor(event_slug, payload):
    return fetch_new_system_json(
        build_new_system_url(event_slug, "exhibitors"),
        method="POST",
        payload=payload,
    )


def update_exhibitor(event_slug, exhibitor_id, payload):
    return fetch_new_system_json(
        build_new_system_url(event_slug, "exhibitors", exhibitor_id),
        method="PATCH",
        payload=payload,
    )


def migrate_partners_for_event(details):
    summary = {
        "partners_created": 0,
        "partners_updated": 0,
        "partners_existing": 0,
        "partners_failed": 0,
    }

    partners = get_event_partners(details["old_event_id"])
    if not partners:
        return summary

    try:
        exhibitors_by_lookup_key = get_existing_exhibitors(details["slug"])
    except requests.HTTPError as error:
        if getattr(error.response, "status_code", None) == 404:
            print(
                f"warning: exhibitor endpoint is unavailable for {details['slug']} "
                f"({details['name']}); skipping partners"
            )
            return summary
        raise

    for partner in partners:
        payload = build_exhibitor_payload(partner)
        existing_exhibitor = find_matching_exhibitor(exhibitors_by_lookup_key, partner)

        if existing_exhibitor and partner_payload_matches(existing_exhibitor, payload):
            summary["partners_existing"] += 1
            continue

        if existing_exhibitor:
            response = update_exhibitor(
                details["slug"], existing_exhibitor["id"], payload
            )
            if response.status_code not in (200, 202):
                summary["partners_failed"] += 1
                print(
                    f"failed partner update: {details['slug']} {partner['name']} - "
                    f"{response.status_code} {get_response_message(response)}"
                )
                continue

            updated_exhibitor = response.json()
            for lookup_key in build_partner_lookup_keys(updated_exhibitor):
                exhibitors_by_lookup_key[lookup_key] = [updated_exhibitor]
            summary["partners_updated"] += 1
            print(f"updated partner: {details['slug']} {partner['name']}")
            continue

        response = create_exhibitor(details["slug"], payload)
        if response.status_code not in (200, 201):
            summary["partners_failed"] += 1
            print(
                f"failed partner create: {details['slug']} {partner['name']} - "
                f"{response.status_code} {get_response_message(response)}"
            )
            continue

        created_exhibitor = response.json()
        for lookup_key in build_partner_lookup_keys(created_exhibitor):
            exhibitors_by_lookup_key[lookup_key].append(created_exhibitor)
        summary["partners_created"] += 1
        print(f"created partner: {details['slug']} {partner['name']}")

    return summary


def build_legacy_order_record(item):
    attributes = item.get("attributes", {})
    identifier = clean_string(attributes.get("identifier")) or clean_string(
        item.get("id")
    )
    return {
        "legacy_order_id": str(item.get("id")),
        "legacy_identifier": identifier,
        "status": clean_string(attributes.get("status")),
        "amount": attributes.get("amount"),
        "email": clean_string(attributes.get("email")),
        "phone": clean_string(attributes.get("phone")),
        "company": clean_string(attributes.get("company")),
        "address": clean_string(attributes.get("address")),
        "city": clean_string(attributes.get("city")),
        "state": clean_string(attributes.get("state")),
        "country": clean_string(attributes.get("country")),
        "zipcode": clean_string(attributes.get("zipcode")),
        "payment_mode": clean_string(attributes.get("payment-mode")),
        "paid_via": clean_string(attributes.get("paid-via")),
        "transaction_id": clean_string(attributes.get("transaction-id")),
        "order_notes": clean_string(attributes.get("order-notes")),
        "completed_at": format_datetime(attributes.get("completed-at")),
    }


def get_event_order_identifiers(event_id):
    order_identifiers = []
    for payload in iter_old_pages(f"{url}/events/{event_id}/orders?page[size]=100"):
        for item in payload.get("data", []):
            identifier = clean_string(item.get("attributes", {}).get("identifier"))
            if identifier:
                order_identifiers.append(identifier)
    return order_identifiers


def get_order_details(order_identifier):
    payload = fetch_json(f"{url}/orders/{order_identifier}")
    order = payload.get("data", {})
    return build_legacy_order_record(order)


def build_legacy_attendee_record(item):
    attributes = item.get("attributes", {})
    order_related_path = (
        item.get("relationships", {}).get("order", {}).get("links", {}).get("related")
    )

    return {
        "legacy_attendee_id": str(item.get("id") or ""),
        "ticket_id": clean_string(attributes.get("ticket-id")),
        "firstname": clean_string(attributes.get("firstname")),
        "lastname": clean_string(attributes.get("lastname")),
        "email": clean_string(attributes.get("email")),
        "company": clean_string(attributes.get("company")),
        "job_title": clean_string(attributes.get("job-title")),
        "street": clean_string(attributes.get("address")),
        "city": clean_string(attributes.get("city")),
        "state": clean_string(attributes.get("state")),
        "country": clean_string(attributes.get("country")),
        "zipcode": clean_string(attributes.get("zipcode")),
        "order_url": build_url(order_related_path),
    }


def get_order_attendees(order_identifier):
    attendees = []
    for payload in iter_old_pages(
        f"{url}/orders/{order_identifier}/attendees?page[size]=100"
    ):
        for item in payload.get("data", []):
            attendees.append(build_legacy_attendee_record(item))
    return attendees


def get_ticket_attendees(ticket_id):
    attendees = []
    for payload in iter_old_pages(
        f"{url}/tickets/{ticket_id}/attendees?page[size]=100"
    ):
        for item in payload.get("data", []):
            attendees.append(build_legacy_attendee_record(item))
    return attendees


def get_attendee_order_details(attendee, order_details_by_url):
    order_url = attendee.get("order_url")
    if not order_url:
        return None

    if order_url in order_details_by_url:
        return order_details_by_url[order_url]

    payload = fetch_json(order_url)
    order = build_legacy_order_record(payload.get("data", {}))
    order_details_by_url[order_url] = order
    return order


def build_attendee_order_code(attendee):
    code_source = "|".join(
        value
        for value in (
            clean_string(attendee.get("legacy_attendee_id")),
            clean_string(attendee.get("ticket_id")),
            clean_string(attendee.get("email")),
            clean_string(attendee.get("firstname")),
            clean_string(attendee.get("lastname")),
        )
        if value
    )
    return build_stable_order_code(code_source or "legacy-attendee-order")


def get_attendee_label(attendee):
    attendee_name = " ".join(
        part
        for part in (
            clean_string(attendee.get("firstname")),
            clean_string(attendee.get("lastname")),
        )
        if part
    )

    return (
        clean_string(attendee.get("legacy_attendee_id"))
        or clean_string(attendee.get("email"))
        or attendee_name
        or clean_string(attendee.get("ticket_id"))
        or "unknown-attendee"
    )


def build_orders_url(event_slug):
    return build_new_system_url(event_slug, "orders")


def build_order_action_url(event_slug, order_code, action):
    return build_new_system_url(event_slug, "orders", order_code, action)


def get_existing_order(event_slug, order_code):
    response = fetch_new_system_json(
        build_new_system_url(event_slug, "orders", order_code), retries=5
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def build_order_comment(order, attendee=None):
    comment_parts = [f"Legacy order {order['legacy_identifier']}"]
    if attendee is not None and clean_string(attendee.get("legacy_attendee_id")):
        comment_parts.append(f"Attendee {clean_string(attendee['legacy_attendee_id'])}")
    if clean_string(order.get("status")):
        comment_parts.append(f"Status {clean_string(order['status'])}")
    if clean_string(order.get("order_notes")):
        comment_parts.append(clean_string(order["order_notes"]))
    return " | ".join(comment_parts)


def build_attendee_order_position(
    attendee,
    product_ids_by_old_ticket_id,
    ticket_prices_by_old_ticket_id,
):
    ticket_id = clean_string(attendee.get("ticket_id"))
    product_id = product_ids_by_old_ticket_id.get(ticket_id)
    if not product_id:
        return None, [ticket_id or "missing-ticket-id"]

    attendee_name = " ".join(
        part
        for part in (
            clean_string(attendee.get("firstname")),
            clean_string(attendee.get("lastname")),
        )
        if part
    )

    position = {
        "positionid": 1,
        "product": product_id,
        "attendee_name": attendee_name or None,
        "attendee_email": clean_string(attendee.get("email")) or None,
        "company": clean_string(attendee.get("company")) or None,
        "job_title": clean_string(attendee.get("job_title")) or None,
        "street": clean_string(attendee.get("street")) or None,
        "city": clean_string(attendee.get("city")) or None,
        "zipcode": clean_string(attendee.get("zipcode")) or None,
    }

    price_source = ticket_prices_by_old_ticket_id.get(ticket_id)
    price = format_decimal(price_source, default=None)
    if price is not None:
        position["price"] = price

    country = normalize_country_code(attendee.get("country"))
    if country:
        position["country"] = country

    state = clean_string(attendee.get("state"))
    if country and state:
        position["state"] = state

    return position, []


def build_attendee_order_payload(
    order,
    attendee,
    product_ids_by_old_ticket_id,
    ticket_prices_by_old_ticket_id,
):
    position, errors = build_attendee_order_position(
        attendee,
        product_ids_by_old_ticket_id,
        ticket_prices_by_old_ticket_id,
    )
    if errors:
        return None, errors

    mapped_status = map_legacy_order_status(order.get("status"))
    payload = {
        "code": build_attendee_order_code(attendee),
        "status": mapped_status["create_status"],
        "email": clean_string(attendee.get("email"))
        or clean_string(order.get("email"))
        or None,
        "phone": clean_string(order.get("phone")) or None,
        "positions": [position],
        "comment": build_order_comment(order, attendee),
        "sales_channel": "web",
        "send_email": False,
        "force": True,
    }

    if mapped_status["create_status"] == "p":
        payload["payment_provider"] = MANUAL_PAYMENT_PROVIDER
        payload["payment_info"] = {
            "legacy_order_identifier": clean_string(order.get("legacy_identifier"))
            or None,
            "legacy_order_id": clean_string(order.get("legacy_order_id")) or None,
            "legacy_status": clean_string(order.get("status")) or None,
            "legacy_payment_mode": clean_string(order.get("payment_mode")) or None,
            "legacy_paid_via": clean_string(order.get("paid_via")) or None,
            "legacy_transaction_id": clean_string(order.get("transaction_id")) or None,
            "legacy_attendee_id": clean_string(attendee.get("legacy_attendee_id"))
            or None,
        }
        if order.get("completed_at"):
            payload["payment_date"] = order.get("completed_at")

    return payload, []


def create_order(event_slug, payload):
    return fetch_new_system_json(
        build_orders_url(event_slug), method="POST", payload=payload
    )


def post_order_action(event_slug, order_code, action, payload=None):
    return fetch_new_system_json(
        build_order_action_url(event_slug, order_code, action),
        method="POST",
        payload=payload,
    )


def ensure_order_final_status(event_slug, order, legacy_status):
    desired_status = map_legacy_order_status(legacy_status)["final_status"]
    current_order = order

    def apply_action(action, payload=None):
        nonlocal current_order
        response = post_order_action(event_slug, current_order["code"], action, payload)
        if response.status_code not in (200, 201, 202):
            return f"{action} {response.status_code} {get_response_message(response)}"

        try:
            current_order = response.json()
        except ValueError:
            pass
        return None

    current_status = clean_string(current_order.get("status")).lower()
    if current_status == desired_status:
        return current_order, None

    if desired_status == "p":
        if current_status not in {"n", "e"}:
            return (
                current_order,
                f"cannot transition {current_status or 'unknown'} to paid",
            )
        error = apply_action("mark_paid", {"send_email": False})
        return current_order, error

    if current_status == "p":
        error = apply_action("mark_pending")
        if error:
            return current_order, error
        current_status = clean_string(current_order.get("status")).lower()

    if desired_status == "n":
        if current_status == "n":
            return current_order, None
        return (
            current_order,
            f"cannot transition {current_status or 'unknown'} to pending",
        )

    if current_status != "n":
        return (
            current_order,
            f"cannot transition {current_status or 'unknown'} to {desired_status}",
        )

    if desired_status == "e":
        error = apply_action("mark_expired")
        return current_order, error

    if desired_status == "c":
        error = apply_action("mark_canceled", {"send_email": False})
        return current_order, error

    return current_order, f"unknown final status {desired_status}"


def migrate_orders_for_event(
    details,
    product_ids_by_old_ticket_id,
    ticket_prices_by_old_ticket_id,
    products_by_old_ticket_id,
):
    summary = {
        "orders_created": 0,
        "orders_existing": 0,
        "orders_failed": 0,
        "orders_skipped": 0,
    }
    order_details_by_url = {}

    for ticket_id in sorted(ticket_prices_by_old_ticket_id):
        try:
            attendees = get_ticket_attendees(ticket_id)
        except requests.RequestException as error:
            summary["orders_failed"] += 1
            print(
                f"failed ticket attendee fetch: {details['slug']} ticket {ticket_id} - {error}"
            )
            continue

        if not attendees:
            continue

        for attendee in attendees:
            attendee_label = get_attendee_label(attendee)
            try:
                order = get_attendee_order_details(attendee, order_details_by_url)
            except requests.RequestException as error:
                summary["orders_failed"] += 1
                print(
                    f"failed attendee order fetch: {details['slug']} ticket {ticket_id} "
                    f"attendee {attendee_label} - {error}"
                )
                continue

            if not order:
                summary["orders_failed"] += 1
                print(
                    f"failed attendee order fetch: {details['slug']} ticket {ticket_id} "
                    f"attendee {attendee_label} - missing-related-order"
                )
                continue

            payload, errors = build_attendee_order_payload(
                order,
                attendee,
                product_ids_by_old_ticket_id,
                ticket_prices_by_old_ticket_id,
            )
            if errors:
                summary["orders_skipped"] += 1
                print(
                    f"skipped order: {details['slug']} ticket {ticket_id} "
                    f"attendee {attendee_label} - {', '.join(errors)}"
                )
                continue

            try:
                existing_order = get_existing_order(details["slug"], payload["code"])
            except requests.RequestException as error:
                summary["orders_failed"] += 1
                print(
                    f"failed order lookup: {details['slug']} {payload['code']} - {error}"
                )
                continue

            if existing_order:
                _, transition_error = ensure_order_final_status(
                    details["slug"], existing_order, order.get("status")
                )
                if transition_error:
                    summary["orders_failed"] += 1
                    print(
                        f"failed existing order finalization: {details['slug']} "
                        f"{payload['code']} - {transition_error}"
                    )
                    continue

                summary["orders_existing"] += 1
                continue

            ticket_id = clean_string(attendee.get("ticket_id"))
            product = products_by_old_ticket_id.get(ticket_id)
            if product and not product.get("active", True):
                product_response = update_product(
                    details["slug"], product["id"], {"active": True}
                )
                if product_response.status_code not in (200, 201):
                    summary["orders_failed"] += 1
                    print(
                        f"failed order product activation: {details['slug']} "
                        f"ticket {ticket_id} - {product_response.status_code} "
                        f"{get_response_message(product_response)}"
                    )
                    continue

                products_by_old_ticket_id[ticket_id] = product_response.json()
                print(
                    f"reactivated product for order import: {details['slug']} ticket {ticket_id}"
                )

            response = create_order(details["slug"], payload)
            if response.status_code not in (200, 201):
                summary["orders_failed"] += 1
                print(
                    f"failed order: {details['slug']} {order['legacy_identifier']} "
                    f"attendee {attendee_label} - {response.status_code} "
                    f"{get_response_message(response)}"
                )
                continue

            created_order = response.json()
            _, transition_error = ensure_order_final_status(
                details["slug"], created_order, order.get("status")
            )
            if transition_error:
                summary["orders_failed"] += 1
                print(
                    f"failed order finalization: {details['slug']} {payload['code']} - "
                    f"{transition_error}"
                )
                continue

            summary["orders_created"] += 1
            print(
                f"created order: {details['slug']} {payload['code']} from "
                f"{order['legacy_identifier']} attendee {attendee_label}"
            )

    return summary


def get_completed_ticket_sales(event_id):
    completed_sales = Counter()
    attendee_statuses = Counter()
    unknown_orders = 0

    for order_identifier in get_event_order_identifiers(event_id):
        order = get_order_details(order_identifier)
        status = clean_string(order.get("status"))
        if not status:
            unknown_orders += 1
            continue

        attendees = get_order_attendees(order_identifier)
        attendee_statuses[status] += len(attendees)
        if status == "completed":
            for attendee in attendees:
                ticket_id = clean_string(attendee.get("ticket_id"))
                if ticket_id:
                    completed_sales[ticket_id] += 1

    return completed_sales, attendee_statuses, unknown_orders


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


def update_event(event_slug, payload):
    return fetch_new_system_json(
        build_new_system_url(event_slug), method="PATCH", payload=payload
    )


def update_event_settings(event_slug, payload):
    return fetch_new_system_json(
        build_new_system_url(event_slug, "settings"),
        method="PATCH",
        payload=payload,
    )


def get_existing_submission_types(event_slug):
    endpoint = build_new_system_url(event_slug, "submission-types")
    try:
        submission_types = get_paginated_results(endpoint)
    except requests.HTTPError as error:
        if is_api_version_error(getattr(error, "response", None)):
            raise RuntimeError(
                "The local eventyay server is serving an outdated API version for submission types. "
                "Restart the local eventyay server and rerun the import."
            ) from error
        raise
    return {
        normalize_token(get_localized_text(item.get("name"))): item
        for item in submission_types
        if get_localized_text(item.get("name"))
    }


def create_submission_type(event_slug, payload):
    return fetch_new_system_json(
        build_new_system_url(event_slug, "submission-types"),
        method="POST",
        payload=payload,
    )


def update_submission_type(event_slug, submission_type_id, payload):
    return fetch_new_system_json(
        build_new_system_url(event_slug, "submission-types", submission_type_id),
        method="PATCH",
        payload=payload,
    )


def get_existing_tracks(event_slug):
    endpoint = build_new_system_url(event_slug, "tracks")
    try:
        tracks = get_paginated_results(endpoint)
    except requests.HTTPError as error:
        if is_api_version_error(getattr(error, "response", None)):
            raise RuntimeError(
                "The local eventyay server is serving an outdated API version for tracks. "
                "Restart the local eventyay server and rerun the import."
            ) from error
        raise
    return {
        normalize_token(get_localized_text(item.get("name"))): item
        for item in tracks
        if get_localized_text(item.get("name"))
    }


def create_track(event_slug, payload):
    return fetch_new_system_json(
        build_new_system_url(event_slug, "tracks"),
        method="POST",
        payload=payload,
    )


def update_track(event_slug, track_id, payload):
    return fetch_new_system_json(
        build_new_system_url(event_slug, "tracks", track_id),
        method="PATCH",
        payload=payload,
    )


def import_speakers(event_slug, payload):
    return fetch_new_system_json(
        build_new_system_url(event_slug, "speakers", "import"),
        method="POST",
        payload=payload,
    )


def import_submissions(event_slug, payload):
    return fetch_new_system_json(
        build_new_system_url(event_slug, "submissions", "import"),
        method="POST",
        payload=payload,
    )


def iter_batches(items, batch_size):
    if batch_size <= 0:
        batch_size = len(items) or 1
    for index in range(0, len(items), batch_size):
        yield items[index : index + batch_size]


def import_record_batches(event_slug, records, *, payload_key, import_func, batch_size, label):
    result = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
        "failed_batches": 0,
    }
    batches = list(iter_batches(records, batch_size))
    total_batches = len(batches)

    for batch_number, batch in enumerate(batches, start=1):
        print(
            f"{label} import batch: {event_slug} {batch_number}/{total_batches} "
            f"records={len(batch)}",
            flush=True,
        )
        response = import_func(event_slug, {payload_key: batch})
        if response.status_code not in (200, 201):
            result["failed_batches"] += 1
            print(
                f"failed {label} import batch: {event_slug} {batch_number}/{total_batches} - "
                f"{response.status_code} {get_response_message(response)}"
            )
            continue

        batch_result = response.json()
        result["created"] += batch_result.get("created", 0)
        result["updated"] += batch_result.get("updated", 0)
        result["skipped"] += batch_result.get("skipped", 0)
        result["errors"].extend(batch_result.get("errors", []))

    return result


def get_existing_schedule_versions(event_slug):
    schedules = get_paginated_results(build_new_system_url(event_slug, "schedules"))
    return {
        clean_string(schedule.get("version"))
        for schedule in schedules
        if schedule.get("version")
    }


def release_schedule(event_slug, payload):
    return fetch_new_system_json(
        build_new_system_url(event_slug, "schedules", "release"),
        method="POST",
        payload=payload,
    )


def enable_manual_payment(event_slug):
    return fetch_new_system_json(
        build_new_system_url(event_slug, "enable-manual-payment"),
        method="POST",
        payload={},
    )


def publish_talks(event_slug):
    return fetch_new_system_json(
        build_new_system_url(event_slug, "publish-talks"),
        method="POST",
        payload={},
    )


def publish_tickets(event_slug):
    return fetch_new_system_json(
        build_new_system_url(event_slug, "publish-tickets"),
        method="POST",
        payload={},
    )


def create_product(event_slug, payload):
    return fetch_new_system_json(
        build_new_system_url(event_slug, "products"),
        method="POST",
        payload=payload,
    )


def update_product(event_slug, product_id, payload):
    return fetch_new_system_json(
        build_new_system_url(event_slug, "products", product_id),
        method="PATCH",
        payload=payload,
    )


def create_quota(event_slug, payload):
    return fetch_new_system_json(
        build_new_system_url(event_slug, "quotas"),
        method="POST",
        payload=payload,
    )


def migrate_submission_types_for_event(details):
    legacy_session_types = get_event_session_types(details["old_event_id"])
    if not legacy_session_types:
        legacy_session_types = [
            {
                "old_session_type_id": "default",
                "name": "Talk",
                "length": "00:30",
            }
        ]

    existing_submission_types = get_existing_submission_types(details["slug"])
    summary = {
        "submission_types_created": 0,
        "submission_types_updated": 0,
        "submission_types_existing": 0,
        "submission_types_failed": 0,
    }

    for legacy_session_type in legacy_session_types:
        lookup_key = normalize_token(legacy_session_type["name"])
        payload = build_submission_type_payload(legacy_session_type)
        existing_submission_type = existing_submission_types.get(lookup_key)

        if existing_submission_type:
            current_duration = existing_submission_type.get("default_duration")
            if current_duration != payload["default_duration"]:
                response = update_submission_type(
                    details["slug"], existing_submission_type["id"], payload
                )
                if response.status_code not in (200, 201):
                    summary["submission_types_failed"] += 1
                    print(
                        f"failed session type update: {details['slug']} {legacy_session_type['name']} - "
                        f"{response.status_code} {get_response_message(response)}"
                    )
                    continue
                summary["submission_types_updated"] += 1
                print(
                    f"updated session type: {details['slug']} {legacy_session_type['name']}"
                )
            else:
                summary["submission_types_existing"] += 1
            continue

        response = create_submission_type(details["slug"], payload)
        if response.status_code not in (200, 201):
            summary["submission_types_failed"] += 1
            print(
                f"failed session type: {details['slug']} {legacy_session_type['name']} - "
                f"{response.status_code} {get_response_message(response)}"
            )
            continue

        existing_submission_types[lookup_key] = response.json()
        summary["submission_types_created"] += 1
        print(f"created session type: {details['slug']} {legacy_session_type['name']}")

    return summary


def migrate_tracks_for_event(details):
    legacy_tracks = get_event_tracks(details["old_event_id"])
    existing_tracks = get_existing_tracks(details["slug"])
    summary = {
        "tracks_created": 0,
        "tracks_updated": 0,
        "tracks_existing": 0,
        "tracks_failed": 0,
    }

    for legacy_track in legacy_tracks:
        lookup_key = normalize_token(legacy_track["name"])
        payload = build_track_payload(legacy_track)
        existing_track = existing_tracks.get(lookup_key)

        if existing_track:
            current_description = get_localized_text(existing_track.get("description"))
            current_color = normalize_track_color(existing_track.get("color"))
            current_position = existing_track.get("position") or 0
            if (
                current_description != clean_string(legacy_track.get("description"))
                or current_color != payload["color"]
                or current_position != payload["position"]
            ):
                response = update_track(details["slug"], existing_track["id"], payload)
                if response.status_code not in (200, 201):
                    summary["tracks_failed"] += 1
                    print(
                        f"failed track update: {details['slug']} {legacy_track['name']} - "
                        f"{response.status_code} {get_response_message(response)}"
                    )
                    continue
                summary["tracks_updated"] += 1
                print(f"updated track: {details['slug']} {legacy_track['name']}")
            else:
                summary["tracks_existing"] += 1
            continue

        response = create_track(details["slug"], payload)
        if response.status_code not in (200, 201):
            summary["tracks_failed"] += 1
            print(
                f"failed track: {details['slug']} {legacy_track['name']} - "
                f"{response.status_code} {get_response_message(response)}"
            )
            continue

        existing_tracks[lookup_key] = response.json()
        summary["tracks_created"] += 1
        print(f"created track: {details['slug']} {legacy_track['name']}")

    return summary


def build_session_import_record(session_item, details, related_cache):
    attributes = session_item.get("attributes", {})
    old_session_id = str(session_item.get("id"))

    session_type_item = get_related_resource(
        session_item, "session-type", related_cache
    )
    track_item = get_related_resource(session_item, "track", related_cache)
    microlocation_item = get_related_resource(
        session_item, "microlocation", related_cache
    )
    speaker_items = get_related_collection(session_item, "speakers", related_cache)

    slide_links = extract_slide_links(attributes.get("slides-url"))
    room_metadata = build_room_metadata(microlocation_item)
    start = format_datetime(attributes.get("starts-at"))
    end = format_datetime(attributes.get("ends-at"))
    linked_speakers = []
    for speaker in speaker_items:
        linked_speakers.extend(build_legacy_speaker_refs(speaker))
    linked_speakers = list(dict.fromkeys(linked_speakers))

    submission_extras = {
        "subtitle": clean_string(attributes.get("subtitle")),
        "level": clean_string(attributes.get("level")),
        "language": clean_string(attributes.get("language")),
        "comments": clean_string(attributes.get("comments")),
        "legacy_state": clean_string(attributes.get("state")),
        "video_url": clean_string(attributes.get("video-url")),
        "audio_url": clean_string(attributes.get("audio-url")),
        "signup_url": clean_string(attributes.get("signup-url")),
    }

    record = {
        "title": clean_string(attributes.get("title"))
        or f"Legacy Session {old_session_id}",
        "code": build_legacy_submission_code(old_session_id),
        "abstract": clean_string(attributes.get("short-abstract"))
        or clean_string(attributes.get("long-abstract")),
        "description": clean_string(attributes.get("long-abstract"))
        or clean_string(attributes.get("comments")),
        "submission_type": clean_string(
            (session_type_item or {}).get("attributes", {}).get("name")
        ),
        "track": clean_string((track_item or {}).get("attributes", {}).get("name")),
        "state": map_legacy_submission_state(attributes.get("state")),
        "content_locale": normalize_language_code(attributes.get("language")),
        "linked_speakers": linked_speakers,
        "room": get_room_display_name(room_metadata),
        "scheduled_public": bool(details.get("schedule_published_on") and start and end),
    }

    if start:
        record["start"] = start
    if end:
        record["end"] = end
    if room_metadata:
        record["room_metadata"] = room_metadata
    if slide_links:
        if len(slide_links) == 1:
            record["slides_link"] = slide_links[0]
        else:
            record["slides_links"] = slide_links

    cleaned_extras = {
        key: value
        for key, value in submission_extras.items()
        if value not in (None, "", [], {})
    }
    if cleaned_extras:
        record["submission_extras"] = cleaned_extras

    return record


def migrate_program_for_event(details):
    summary = {
        "submission_types_created": 0,
        "submission_types_updated": 0,
        "submission_types_existing": 0,
        "submission_types_failed": 0,
        "tracks_created": 0,
        "tracks_updated": 0,
        "tracks_existing": 0,
        "tracks_failed": 0,
        "speakers_created": 0,
        "speakers_updated": 0,
        "speakers_skipped": 0,
        "submissions_created": 0,
        "submissions_updated": 0,
        "submissions_skipped": 0,
        "program_errors": 0,
        "program_ready_for_publish": False,
        "submissions_total": 0,
    }

    submission_type_summary = migrate_submission_types_for_event(details)
    track_summary = migrate_tracks_for_event(details)
    for key, value in submission_type_summary.items():
        summary[key] += value
    for key, value in track_summary.items():
        summary[key] += value

    legacy_speakers = get_event_speakers(details["old_event_id"])
    speaker_records = [
        build_speaker_import_record(speaker) for speaker in legacy_speakers
    ]
    speaker_result = import_record_batches(
        details["slug"],
        speaker_records,
        payload_key="speakers",
        import_func=import_speakers,
        batch_size=SPEAKER_IMPORT_BATCH_SIZE,
        label="speaker",
    )
    summary["speakers_created"] += speaker_result.get("created", 0)
    summary["speakers_updated"] += speaker_result.get("updated", 0)
    summary["speakers_skipped"] += speaker_result.get("skipped", 0)
    summary["program_errors"] += len(speaker_result.get("errors", []))
    summary["program_errors"] += speaker_result.get("failed_batches", 0)
    print(
        f"speaker import summary: {details['slug']} - created={speaker_result.get('created', 0)}, "
        f"updated={speaker_result.get('updated', 0)}, skipped={speaker_result.get('skipped', 0)}"
    )
    for error in speaker_result.get("errors", [])[:5]:
        print(f"speaker import error: {details['slug']} - {error}")
    if speaker_result.get("failed_batches"):
        return summary

    related_cache = {}
    submission_records = []
    for session_item in get_event_sessions(details["old_event_id"]):
        try:
            submission_records.append(
                build_session_import_record(session_item, details, related_cache)
            )
        except requests.RequestException as error:
            summary["submissions_skipped"] += 1
            summary["program_errors"] += 1
            print(
                f"failed session relationship fetch: {details['slug']} session {session_item.get('id')} - {error}"
            )

    summary["submissions_total"] = len(submission_records)
    if not submission_records:
        return summary

    submission_result = import_record_batches(
        details["slug"],
        submission_records,
        payload_key="submissions",
        import_func=import_submissions,
        batch_size=SUBMISSION_IMPORT_BATCH_SIZE,
        label="submission",
    )
    summary["submissions_created"] += submission_result.get("created", 0)
    summary["submissions_updated"] += submission_result.get("updated", 0)
    summary["submissions_skipped"] += submission_result.get("skipped", 0)
    summary["program_errors"] += len(submission_result.get("errors", []))
    summary["program_errors"] += submission_result.get("failed_batches", 0)
    summary["program_ready_for_publish"] = not submission_result.get("failed_batches")
    print(
        f"submission import summary: {details['slug']} - created={submission_result.get('created', 0)}, "
        f"updated={submission_result.get('updated', 0)}, skipped={submission_result.get('skipped', 0)}"
    )
    for error in submission_result.get("errors", [])[:5]:
        print(f"submission import error: {details['slug']} - {error}")

    return summary


def has_paid_tickets(product_summary):
    for price in product_summary.get("ticket_prices_by_old_ticket_id", {}).values():
        if format_decimal(price, default=None) not in (None, "0.00"):
            return True
    return False


def finalize_event_import(details, product_summary, program_summary):
    summary = {
        "events_finalized": 0,
        "event_finalizations_failed": 0,
        "schedules_released": 0,
        "schedules_existing": 0,
    }

    if details.get("state") != "published":
        print(
            f"skipping finalization: {details['slug']} ({details['name']}) - legacy state is {details.get('state') or 'unknown'}"
        )
        return summary

    if has_paid_tickets(product_summary):
        payment_response = enable_manual_payment(details["slug"])
        if payment_response.status_code not in (200, 201):
            summary["event_finalizations_failed"] += 1
            print(
                f"failed manual payment enablement: {details['slug']} - {payment_response.status_code} "
                f"{get_response_message(payment_response)}"
            )
            return summary

    event_response = update_event(
        details["slug"],
        {
            "is_public": True,
            "live": True,
            **HIDDEN_FROM_STARTPAGE_PAYLOAD,
        },
    )
    if event_response.status_code not in (200, 202):
        summary["event_finalizations_failed"] += 1
        print(
            f"failed event finalization: {details['slug']} - {event_response.status_code} "
            f"{get_response_message(event_response)}"
        )
        return summary

    summary["events_finalized"] += 1
    print(f"finalized event: {details['slug']} ({details['name']})")

    if product_summary.get("product_ids_by_old_ticket_id"):
        tickets_response = publish_tickets(details["slug"])
        if tickets_response.status_code not in (200, 201):
            summary["event_finalizations_failed"] += 1
            print(
                f"failed ticket publication: {details['slug']} - {tickets_response.status_code} "
                f"{get_response_message(tickets_response)}"
            )

    if details.get("schedule_published_on") and program_summary.get(
        "program_ready_for_publish"
    ):
        version_name = build_schedule_version(details)
        existing_versions = get_existing_schedule_versions(details["slug"])
        if version_name in existing_versions:
            summary["schedules_existing"] += 1
        else:
            release_response = release_schedule(
                details["slug"],
                {
                    "version": version_name,
                    "comment": f"Legacy schedule import from {details['old_event_id']}",
                },
            )
            if release_response.status_code not in (200, 201):
                summary["event_finalizations_failed"] += 1
                print(
                    f"failed schedule release: {details['slug']} - {release_response.status_code} "
                    f"{get_response_message(release_response)}"
                )
            else:
                summary["schedules_released"] += 1
                print(f"released schedule: {details['slug']} version={version_name}")

        talks_response = publish_talks(details["slug"])
        if talks_response.status_code not in (200, 201):
            summary["event_finalizations_failed"] += 1
            print(
                f"failed talk publication: {details['slug']} - {talks_response.status_code} "
                f"{get_response_message(talks_response)}"
            )

    return summary


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
        "product_ids_by_old_ticket_id": {},
        "products_by_old_ticket_id": {},
        "ticket_prices_by_old_ticket_id": {},
    }

    if not tickets:
        print(
            f"warning: no legacy tickets found for {details['slug']} ({details['name']})"
        )
        return summary

    for ticket in tickets:
        old_ticket_id = ticket["old_ticket_id"]
        sold_count = completed_sales.get(old_ticket_id, 0)
        summary["ticket_prices_by_old_ticket_id"][old_ticket_id] = ticket.get("price")
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

        summary["product_ids_by_old_ticket_id"][old_ticket_id] = product["id"]
        summary["products_by_old_ticket_id"][old_ticket_id] = product

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


def migrate_events_with_more_than_ten_orders(
    limit=None,
    event_id=None,
    include_partners=True,
    include_orders=True,
    include_program=False,
    finalize_event_state=False,
):
    event_order_counts = {} if event_id is not None else get_order_counts()
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
        "partners_created": 0,
        "partners_updated": 0,
        "partners_existing": 0,
        "partners_failed": 0,
        "orders_created": 0,
        "orders_existing": 0,
        "orders_failed": 0,
        "orders_skipped": 0,
        "validation_mismatches": 0,
        "submission_types_created": 0,
        "submission_types_updated": 0,
        "submission_types_existing": 0,
        "submission_types_failed": 0,
        "tracks_created": 0,
        "tracks_updated": 0,
        "tracks_existing": 0,
        "tracks_failed": 0,
        "speakers_created": 0,
        "speakers_updated": 0,
        "speakers_skipped": 0,
        "submissions_created": 0,
        "submissions_updated": 0,
        "submissions_skipped": 0,
        "program_errors": 0,
        "events_finalized": 0,
        "event_finalizations_failed": 0,
        "schedules_released": 0,
        "schedules_existing": 0,
    }

    if event_id is not None:
        qualifying_events = [(str(event_id), 0)]
        total_qualifying_events = len(qualifying_events)
    else:
        for current_event_id, order_count in event_order_counts.items():
            if order_count > 10:
                qualifying_events.append((current_event_id, order_count))
        total_qualifying_events = len(qualifying_events)
    if limit is not None:
        qualifying_events = qualifying_events[:limit]
        print(
            f"Test mode enabled: processing {len(qualifying_events)} of {total_qualifying_events} qualifying events"
        )

    for event_id, order_count in qualifying_events:
        details = get_event_details(event_id)

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

        startpage_response = update_event(details["slug"], HIDDEN_FROM_STARTPAGE_PAYLOAD)
        if startpage_response.status_code in (200, 202):
            summary["events_updated"] += 1
            print(f"hid event from start page: {details['slug']} ({details['name']})")
        else:
            summary["event_updates_failed"] += 1
            print(
                f"warning: failed to hide event from start page for {details['slug']} "
                f"({details['name']}) - {startpage_response.status_code} "
                f"{get_response_message(startpage_response)}"
            )

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

        if include_partners:
            partner_summary = migrate_partners_for_event(details)
            for key in (
                "partners_created",
                "partners_updated",
                "partners_existing",
                "partners_failed",
            ):
                summary[key] += partner_summary[key]

            print(
                f"event partner summary: {details['slug']} - "
                f"partners created={partner_summary['partners_created']}, "
                f"partners updated={partner_summary['partners_updated']}, "
                f"partners existing={partner_summary['partners_existing']}, "
                f"partners failed={partner_summary['partners_failed']}"
            )

        if include_orders:
            order_summary = migrate_orders_for_event(
                details,
                product_summary["product_ids_by_old_ticket_id"],
                product_summary["ticket_prices_by_old_ticket_id"],
                product_summary["products_by_old_ticket_id"],
            )
            for key in (
                "orders_created",
                "orders_existing",
                "orders_failed",
                "orders_skipped",
            ):
                summary[key] += order_summary[key]

            print(
                f"event order summary: {details['slug']} - "
                f"orders created={order_summary['orders_created']}, "
                f"orders existing={order_summary['orders_existing']}, "
                f"orders failed={order_summary['orders_failed']}, "
                f"orders skipped={order_summary['orders_skipped']}"
            )

        if include_program:
            program_summary = migrate_program_for_event(details)
            for key in (
                "submission_types_created",
                "submission_types_updated",
                "submission_types_existing",
                "submission_types_failed",
                "tracks_created",
                "tracks_updated",
                "tracks_existing",
                "tracks_failed",
                "speakers_created",
                "speakers_updated",
                "speakers_skipped",
                "submissions_created",
                "submissions_updated",
                "submissions_skipped",
                "program_errors",
            ):
                summary[key] += program_summary[key]

            print(
                f"event program summary: {details['slug']} - "
                f"session types created={program_summary['submission_types_created']}, "
                f"tracks created={program_summary['tracks_created']}, "
                f"speakers created={program_summary['speakers_created']}, "
                f"submissions created={program_summary['submissions_created']}, "
                f"program errors={program_summary['program_errors']}"
            )
        else:
            program_summary = {
                "program_ready_for_publish": False,
                "submissions_total": 0,
            }

        if finalize_event_state:
            finalization_summary = finalize_event_import(
                details, product_summary, program_summary
            )
            for key in (
                "events_finalized",
                "event_finalizations_failed",
                "schedules_released",
                "schedules_existing",
            ):
                summary[key] += finalization_summary[key]

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
    print(f"Created partners: {summary['partners_created']}")
    print(f"Updated partners: {summary['partners_updated']}")
    print(f"Existing partners: {summary['partners_existing']}")
    print(f"Failed partners: {summary['partners_failed']}")
    print(f"Created orders: {summary['orders_created']}")
    print(f"Existing orders: {summary['orders_existing']}")
    print(f"Failed orders: {summary['orders_failed']}")
    print(f"Skipped orders: {summary['orders_skipped']}")
    print(f"Created session types: {summary['submission_types_created']}")
    print(f"Updated session types: {summary['submission_types_updated']}")
    print(f"Existing session types: {summary['submission_types_existing']}")
    print(f"Failed session types: {summary['submission_types_failed']}")
    print(f"Created tracks: {summary['tracks_created']}")
    print(f"Updated tracks: {summary['tracks_updated']}")
    print(f"Existing tracks: {summary['tracks_existing']}")
    print(f"Failed tracks: {summary['tracks_failed']}")
    print(f"Created speakers: {summary['speakers_created']}")
    print(f"Updated speakers: {summary['speakers_updated']}")
    print(f"Skipped speakers: {summary['speakers_skipped']}")
    print(f"Created submissions: {summary['submissions_created']}")
    print(f"Updated submissions: {summary['submissions_updated']}")
    print(f"Skipped submissions: {summary['submissions_skipped']}")
    print(f"Program errors: {summary['program_errors']}")
    print(f"Finalized events: {summary['events_finalized']}")
    print(f"Failed finalizations: {summary['event_finalizations_failed']}")
    print(f"Released schedules: {summary['schedules_released']}")
    print(f"Existing schedules: {summary['schedules_existing']}")
    print(f"Validation mismatches: {summary['validation_mismatches']}")
    print(f"Processed qualifying events: {len(qualifying_events)}")
    print(f"Total qualifying events: {total_qualifying_events}")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-fossasia",
        "--fossasia",
        action="store_true",
        dest="fossasia_mode",
        help=(
            "Run a full import for the FOSSASIA event 45da88b7, including "
            "tickets, orders, partners, program, and event finalization."
        ),
    )
    parser.add_argument(
        "-test",
        "--test",
        action="store_true",
        dest="test_mode",
        help="Run the migration only for the first 25 qualifying events.",
    )
    parser.add_argument(
        "--event-id",
        dest="event_id",
        help="Run the migration only for a specific legacy event id.",
    )
    parser.add_argument(
        "--skip-partners",
        action="store_true",
        help="Skip importing exhibitors and sponsors.",
    )
    parser.add_argument(
        "--skip-orders",
        action="store_true",
        help="Skip importing orders for any selected events.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    start_status_timer()
    try:
        if args.fossasia_mode:
            print(
                f"FOSSASIA mode enabled: importing legacy event {FOSSASIA_EVENT_IDENTIFIER}"
            )
            migrate_events_with_more_than_ten_orders(
                event_id=FOSSASIA_EVENT_IDENTIFIER,
                include_partners=not args.skip_partners,
                include_orders=not args.skip_orders,
                include_program=True,
                finalize_event_state=True,
            )
            sys.exit(0)

        migrate_events_with_more_than_ten_orders(
            limit=25 if args.test_mode else None,
            event_id=args.event_id,
            include_partners=not args.skip_partners,
            include_orders=not args.skip_orders,
            include_program=True,
            finalize_event_state=True,
        )
    finally:
        stop_status_timer()
