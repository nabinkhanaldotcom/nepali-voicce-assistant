# backend_api/app/services/usage_metrics_service.py
#
# SQLite usage tracking for the Nepali Voice app.
#
# What this records:
# - how many backend audio requests happened
# - which endpoint was used
# - success/failure
# - request IP
# - approximate city/region/country/postal from IP lookup when available
# - audio duration
# - upload size
# - provider/model
# - RVC settings
#
# What this does NOT record:
# - actual audio contents
# - transcript text
# - user GPS location
#
# Important:
# IP location is approximate. It can say something like Seattle, Washington, USA,
# but it is not guaranteed to be the user's exact city or ZIP.

from __future__ import annotations

import ipaddress
import json
import logging
import os
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Request

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

USAGE_METRICS_DIR = BACKEND_ROOT / "data" / "usage_metrics"

USAGE_METRICS_DB_PATH = Path(
    os.getenv(
        "USAGE_METRICS_DB_PATH",
        str(USAGE_METRICS_DIR / "usage_metrics.sqlite3"),
    )
)

IP_GEOLOCATION_ENABLED = (
    os.getenv("IP_GEOLOCATION_ENABLED", "true").strip().lower()
    not in {"false", "0", "no", "off"}
)

IPINFO_TOKEN = os.getenv("IPINFO_TOKEN", "").strip()

IP_GEOLOCATION_TIMEOUT_SECONDS = float(
    os.getenv("IP_GEOLOCATION_TIMEOUT_SECONDS", "2.0")
)

IP_LOCATION_CACHE_TTL_SECONDS = int(
    os.getenv("IP_LOCATION_CACHE_TTL_SECONDS", str(30 * 24 * 60 * 60))
)


COUNTRY_CODE_NAMES = {
    "US": "United States",
    "NP": "Nepal",
    "CA": "Canada",
    "GB": "United Kingdom",
    "IN": "India",
    "AU": "Australia",
    "DE": "Germany",
    "FR": "France",
    "JP": "Japan",
}


USAGE_EVENT_COLUMNS = {
    "created_at_utc": "TEXT NOT NULL DEFAULT ''",
    "created_at_epoch": "INTEGER NOT NULL DEFAULT 0",
    "endpoint": "TEXT NOT NULL DEFAULT ''",
    "action": "TEXT NOT NULL DEFAULT ''",
    "success": "INTEGER NOT NULL DEFAULT 0",
    "status_code": "INTEGER",
    "error_message": "TEXT",
    "username": "TEXT",
    "client_ip": "TEXT",
    "x_forwarded_for": "TEXT",
    "x_real_ip": "TEXT",
    "cf_connecting_ip": "TEXT",
    "cf_ip_country": "TEXT",
    "ip_city": "TEXT",
    "ip_region": "TEXT",
    "ip_country": "TEXT",
    "ip_country_code": "TEXT",
    "ip_postal": "TEXT",
    "ip_timezone": "TEXT",
    "ip_coordinates": "TEXT",
    "ip_org": "TEXT",
    "ip_geo_provider": "TEXT",
    "user_agent": "TEXT",
    "original_filename": "TEXT",
    "content_type": "TEXT",
    "upload_bytes": "INTEGER",
    "duration_seconds": "REAL",
    "provider": "TEXT",
    "model": "TEXT",
    "tone_preset": "TEXT",
    "rvc_pitch": "INTEGER",
    "rvc_index_rate": "REAL",
    "rvc_protect": "REAL",
    "rvc_method": "TEXT",
    "output_bytes": "INTEGER",
    "processing_ms": "INTEGER",
}


def get_utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_db_connection() -> sqlite3.Connection:
    USAGE_METRICS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(str(USAGE_METRICS_DB_PATH), timeout=10)
    connection.row_factory = sqlite3.Row

    connection.execute("PRAGMA journal_mode=WAL;")
    connection.execute("PRAGMA busy_timeout=10000;")

    return connection


def get_existing_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row["name"]) for row in rows}


def ensure_usage_event_columns(connection: sqlite3.Connection) -> None:
    existing_columns = get_existing_columns(connection, "usage_events")

    for column_name, column_definition in USAGE_EVENT_COLUMNS.items():
        if column_name not in existing_columns:
            connection.execute(
                f"ALTER TABLE usage_events ADD COLUMN {column_name} {column_definition}"
            )


def initialize_usage_metrics_database() -> None:
    """
    Create or upgrade local SQLite tables.
    """
    with get_db_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS usage_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT
            )
            """
        )

        ensure_usage_event_columns(connection)

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_usage_events_created_at_epoch
            ON usage_events(created_at_epoch)
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_usage_events_endpoint
            ON usage_events(endpoint)
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_usage_events_success
            ON usage_events(success)
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ip_location_cache (
                ip TEXT PRIMARY KEY,
                looked_up_at_epoch INTEGER NOT NULL,
                city TEXT,
                region TEXT,
                country TEXT,
                country_code TEXT,
                postal TEXT,
                timezone TEXT,
                coordinates TEXT,
                org TEXT,
                provider TEXT,
                raw_json TEXT
            )
            """
        )


def safe_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_country_code(country_code: str | None) -> str | None:
    if not country_code:
        return None

    cleaned = country_code.strip().upper()

    if not cleaned or cleaned == "XX":
        return None

    return cleaned


def country_name_from_code(country_code: str | None) -> str | None:
    cleaned = normalize_country_code(country_code)

    if not cleaned:
        return None

    return COUNTRY_CODE_NAMES.get(cleaned, cleaned)


def get_first_header_value(request: Request, header_name: str) -> str | None:
    value = request.headers.get(header_name)

    if value is None:
        return None

    cleaned = value.strip()

    return cleaned or None


def get_client_ip(request: Request) -> str | None:
    """
    Best effort client IP detection.

    If your domain is proxied by Cloudflare, CF-Connecting-IP is best.

    If your domain is DNS-only / direct Caddy, X-Forwarded-For or request.client
    is usually enough.
    """
    cf_connecting_ip = get_first_header_value(request, "cf-connecting-ip")
    if cf_connecting_ip:
        return cf_connecting_ip

    x_forwarded_for = get_first_header_value(request, "x-forwarded-for")
    if x_forwarded_for:
        first_ip = x_forwarded_for.split(",")[0].strip()
        if first_ip:
            return first_ip

    x_real_ip = get_first_header_value(request, "x-real-ip")
    if x_real_ip:
        return x_real_ip

    if request.client and request.client.host:
        return request.client.host

    return None


def is_public_ip(ip_text: str | None) -> bool:
    if not ip_text:
        return False

    try:
        ip = ipaddress.ip_address(ip_text.strip())
    except ValueError:
        return False

    return ip.is_global


def read_cached_ip_location(ip: str) -> dict[str, Any] | None:
    initialize_usage_metrics_database()

    now_epoch = int(time.time())

    with get_db_connection() as connection:
        row = connection.execute(
            """
            SELECT
                ip,
                looked_up_at_epoch,
                city,
                region,
                country,
                country_code,
                postal,
                timezone,
                coordinates,
                org,
                provider
            FROM ip_location_cache
            WHERE ip = ?
            """,
            (ip,),
        ).fetchone()

    if row is None:
        return None

    looked_up_at_epoch = int(row["looked_up_at_epoch"] or 0)

    if now_epoch - looked_up_at_epoch > IP_LOCATION_CACHE_TTL_SECONDS:
        return None

    return dict(row)


def save_cached_ip_location(ip: str, location: dict[str, Any]) -> None:
    initialize_usage_metrics_database()

    with get_db_connection() as connection:
        connection.execute(
            """
            INSERT INTO ip_location_cache (
                ip,
                looked_up_at_epoch,
                city,
                region,
                country,
                country_code,
                postal,
                timezone,
                coordinates,
                org,
                provider,
                raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ip) DO UPDATE SET
                looked_up_at_epoch = excluded.looked_up_at_epoch,
                city = excluded.city,
                region = excluded.region,
                country = excluded.country,
                country_code = excluded.country_code,
                postal = excluded.postal,
                timezone = excluded.timezone,
                coordinates = excluded.coordinates,
                org = excluded.org,
                provider = excluded.provider,
                raw_json = excluded.raw_json
            """,
            (
                ip,
                int(time.time()),
                location.get("city"),
                location.get("region"),
                location.get("country"),
                location.get("country_code"),
                location.get("postal"),
                location.get("timezone"),
                location.get("coordinates"),
                location.get("org"),
                location.get("provider"),
                json.dumps(location.get("raw_json", {}), ensure_ascii=False),
            ),
        )


def lookup_ip_location_from_ipinfo(ip: str) -> dict[str, Any] | None:
    """
    Look up approximate IP location using IPinfo.

    If IPINFO_TOKEN is set, we use it.
    If not set, this still tries the public endpoint, but fields/rate limits may
    be limited depending on IPinfo behavior.
    """
    if not IP_GEOLOCATION_ENABLED:
        return None

    if not is_public_ip(ip):
        return None

    cached_location = read_cached_ip_location(ip)
    if cached_location is not None:
        return cached_location

    quoted_ip = urllib.parse.quote(ip, safe="")

    url = f"https://ipinfo.io/{quoted_ip}/json"

    if IPINFO_TOKEN:
        url = f"{url}?token={urllib.parse.quote(IPINFO_TOKEN, safe='')}"

    request = urllib.request.Request(
        url=url,
        headers={
            "Accept": "application/json",
            "User-Agent": "nepali-voice-usage-metrics/1.0",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=IP_GEOLOCATION_TIMEOUT_SECONDS,
        ) as response:
            raw_body = response.read().decode("utf-8", errors="replace")
            payload = json.loads(raw_body)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        logger.exception("IP geolocation lookup failed for IP %s", ip)
        return None

    country_code = normalize_country_code(payload.get("country"))
    country_name = country_name_from_code(country_code)

    location = {
        "ip": ip,
        "city": payload.get("city"),
        "region": payload.get("region"),
        "country": country_name,
        "country_code": country_code,
        "postal": payload.get("postal"),
        "timezone": payload.get("timezone"),
        "coordinates": payload.get("loc"),
        "org": payload.get("org"),
        "provider": "ipinfo",
        "raw_json": payload,
    }

    save_cached_ip_location(ip, location)

    return location


def build_request_usage_context(
    request: Request,
    username: str | None = None,
) -> dict[str, Any]:
    cf_country_code = normalize_country_code(
        get_first_header_value(request, "cf-ipcountry")
    )

    return {
        "username": username,
        "client_ip": get_client_ip(request),
        "x_forwarded_for": get_first_header_value(request, "x-forwarded-for"),
        "x_real_ip": get_first_header_value(request, "x-real-ip"),
        "cf_connecting_ip": get_first_header_value(request, "cf-connecting-ip"),
        "cf_ip_country": cf_country_code,
        "user_agent": get_first_header_value(request, "user-agent"),
        "request_content_length": safe_int(
            get_first_header_value(request, "content-length")
        ),
    }


def resolve_location_for_request_context(
    request_context: dict[str, Any],
) -> dict[str, Any]:
    client_ip = request_context.get("client_ip")
    cf_country_code = normalize_country_code(request_context.get("cf_ip_country"))

    location = None

    if client_ip:
        location = lookup_ip_location_from_ipinfo(str(client_ip))

    if location:
        return location

    return {
        "city": None,
        "region": None,
        "country": country_name_from_code(cf_country_code),
        "country_code": cf_country_code,
        "postal": None,
        "timezone": None,
        "coordinates": None,
        "org": None,
        "provider": "cloudflare_header" if cf_country_code else None,
    }


def record_usage_event(
    *,
    endpoint: str,
    action: str,
    success: bool,
    status_code: int | None = None,
    error_message: str | None = None,
    request_context: dict[str, Any] | None = None,
    original_filename: str | None = None,
    content_type: str | None = None,
    upload_bytes: int | None = None,
    duration_seconds: float | None = None,
    provider: str | None = None,
    model: str | None = None,
    tone_preset: str | None = None,
    rvc_pitch: int | None = None,
    rvc_index_rate: float | None = None,
    rvc_protect: float | None = None,
    rvc_method: str | None = None,
    output_bytes: int | None = None,
    processing_ms: int | None = None,
) -> None:
    """
    Store one usage event.

    This function catches its own errors so analytics never breaks the real app.
    """
    initialize_usage_metrics_database()

    context = request_context or {}

    if upload_bytes is None:
        upload_bytes = safe_int(context.get("request_content_length"))

    location = resolve_location_for_request_context(context)

    try:
        with get_db_connection() as connection:
            connection.execute(
                """
                INSERT INTO usage_events (
                    created_at_utc,
                    created_at_epoch,
                    endpoint,
                    action,
                    success,
                    status_code,
                    error_message,
                    username,
                    client_ip,
                    x_forwarded_for,
                    x_real_ip,
                    cf_connecting_ip,
                    cf_ip_country,
                    ip_city,
                    ip_region,
                    ip_country,
                    ip_country_code,
                    ip_postal,
                    ip_timezone,
                    ip_coordinates,
                    ip_org,
                    ip_geo_provider,
                    user_agent,
                    original_filename,
                    content_type,
                    upload_bytes,
                    duration_seconds,
                    provider,
                    model,
                    tone_preset,
                    rvc_pitch,
                    rvc_index_rate,
                    rvc_protect,
                    rvc_method,
                    output_bytes,
                    processing_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    get_utc_now_iso(),
                    int(time.time()),
                    endpoint,
                    action,
                    1 if success else 0,
                    status_code,
                    error_message,
                    context.get("username"),
                    context.get("client_ip"),
                    context.get("x_forwarded_for"),
                    context.get("x_real_ip"),
                    context.get("cf_connecting_ip"),
                    context.get("cf_ip_country"),
                    location.get("city"),
                    location.get("region"),
                    location.get("country"),
                    location.get("country_code"),
                    location.get("postal"),
                    location.get("timezone"),
                    location.get("coordinates"),
                    location.get("org"),
                    location.get("provider"),
                    context.get("user_agent"),
                    original_filename,
                    content_type,
                    upload_bytes,
                    duration_seconds,
                    provider,
                    model,
                    tone_preset,
                    rvc_pitch,
                    rvc_index_rate,
                    rvc_protect,
                    rvc_method,
                    output_bytes,
                    processing_ms,
                ),
            )
    except Exception:
        logger.exception("Failed to write usage metrics event.")


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def get_usage_summary(days: int = 30) -> dict[str, Any]:
    initialize_usage_metrics_database()

    days = max(1, min(days, 365))
    cutoff_epoch = int(time.time()) - days * 24 * 60 * 60

    with get_db_connection() as connection:
        totals = connection.execute(
            """
            SELECT
                COUNT(*) AS total_backend_events,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS successful_events,
                SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) AS failed_events,
                SUM(CASE WHEN endpoint = '/generate-voice' THEN 1 ELSE 0 END) AS artist_generation_attempts,
                SUM(CASE WHEN endpoint = '/generate-voice' AND success = 1 THEN 1 ELSE 0 END) AS artist_generation_successes,
                SUM(CASE WHEN endpoint = '/generate-voice' AND success = 0 THEN 1 ELSE 0 END) AS artist_generation_failures,
                SUM(CASE WHEN duration_seconds IS NOT NULL THEN 1 ELSE 0 END) AS clips_with_known_duration,
                SUM(COALESCE(duration_seconds, 0)) AS total_duration_seconds,
                AVG(duration_seconds) AS average_duration_seconds,
                SUM(COALESCE(upload_bytes, 0)) AS total_upload_bytes
            FROM usage_events
            WHERE created_at_epoch >= ?
            """,
            (cutoff_epoch,),
        ).fetchone()

        by_endpoint = connection.execute(
            """
            SELECT
                endpoint,
                action,
                COUNT(*) AS total_events,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS successful_events,
                SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) AS failed_events,
                SUM(COALESCE(duration_seconds, 0)) AS total_duration_seconds,
                AVG(duration_seconds) AS average_duration_seconds,
                SUM(COALESCE(upload_bytes, 0)) AS total_upload_bytes
            FROM usage_events
            WHERE created_at_epoch >= ?
            GROUP BY endpoint, action
            ORDER BY total_events DESC
            """,
            (cutoff_epoch,),
        ).fetchall()

        by_location = connection.execute(
            """
            SELECT
                COALESCE(ip_city, 'unknown') AS city,
                COALESCE(ip_region, 'unknown') AS region,
                COALESCE(ip_country, 'unknown') AS country,
                COALESCE(ip_postal, 'unknown') AS postal,
                COUNT(*) AS total_events,
                SUM(CASE WHEN endpoint = '/generate-voice' THEN 1 ELSE 0 END) AS artist_generation_attempts,
                SUM(CASE WHEN endpoint = '/generate-voice' AND success = 1 THEN 1 ELSE 0 END) AS artist_generation_successes,
                SUM(CASE WHEN endpoint = '/generate-voice' AND success = 0 THEN 1 ELSE 0 END) AS artist_generation_failures
            FROM usage_events
            WHERE created_at_epoch >= ?
            GROUP BY
                COALESCE(ip_city, 'unknown'),
                COALESCE(ip_region, 'unknown'),
                COALESCE(ip_country, 'unknown'),
                COALESCE(ip_postal, 'unknown')
            ORDER BY total_events DESC
            LIMIT 50
            """,
            (cutoff_epoch,),
        ).fetchall()

        by_client_ip = connection.execute(
            """
            SELECT
                COALESCE(client_ip, 'unknown') AS client_ip,
                COALESCE(ip_city, 'unknown') AS city,
                COALESCE(ip_region, 'unknown') AS region,
                COALESCE(ip_country, 'unknown') AS country,
                COALESCE(ip_postal, 'unknown') AS postal,
                COUNT(*) AS total_events
            FROM usage_events
            WHERE created_at_epoch >= ?
            GROUP BY
                COALESCE(client_ip, 'unknown'),
                COALESCE(ip_city, 'unknown'),
                COALESCE(ip_region, 'unknown'),
                COALESCE(ip_country, 'unknown'),
                COALESCE(ip_postal, 'unknown')
            ORDER BY total_events DESC
            LIMIT 50
            """,
            (cutoff_epoch,),
        ).fetchall()

    return {
        "days": days,
        "databasePath": str(USAGE_METRICS_DB_PATH),
        "totals": row_to_dict(totals) if totals else {},
        "byEndpoint": [row_to_dict(row) for row in by_endpoint],
        "byLocation": [row_to_dict(row) for row in by_location],
        "byClientIp": [row_to_dict(row) for row in by_client_ip],
    }


def get_recent_usage_events(limit: int = 50) -> dict[str, Any]:
    initialize_usage_metrics_database()

    limit = max(1, min(limit, 500))

    with get_db_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                created_at_utc,
                endpoint,
                action,
                success,
                status_code,
                error_message,
                username,
                client_ip,
                ip_city,
                ip_region,
                ip_country,
                ip_country_code,
                ip_postal,
                user_agent,
                original_filename,
                content_type,
                upload_bytes,
                duration_seconds,
                provider,
                model,
                tone_preset,
                rvc_pitch,
                rvc_index_rate,
                rvc_protect,
                rvc_method,
                output_bytes,
                processing_ms
            FROM usage_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return {
        "databasePath": str(USAGE_METRICS_DB_PATH),
        "limit": limit,
        "events": [row_to_dict(row) for row in rows],
    }