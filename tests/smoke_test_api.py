#!/usr/bin/env python3
"""Smoke test script for Gardena Smart System API v2.

This script validates our assumptions about the real Gardena/Husqvarna API
by making read-only requests and logging the actual response structures.
No commands are sent — this is purely observational.

Usage:
    export GARDENA_CLIENT_ID="your-client-id"
    export GARDENA_CLIENT_SECRET="your-client-secret"
    python tests/smoke_test_api.py

Optionally set GARDENA_LOG_LEVEL=DEBUG for verbose output.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import ssl
import sys
from typing import Any

import aiohttp

# ── Configuration ──────────────────────────────────────────────────────

CLIENT_ID = os.environ.get("GARDENA_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("GARDENA_CLIENT_SECRET", "")
LOG_LEVEL = os.environ.get("GARDENA_LOG_LEVEL", "INFO").upper()

# Endpoints (these are what we want to verify)
AUTH_URL = "https://api.authentication.husqvarnagroup.dev/v1/oauth2/token"
API_BASE = "https://api.smart.gardena.dev/v2"
LOCATIONS_URL = f"{API_BASE}/locations"
WEBSOCKET_URL = f"{API_BASE}/websocket"

# How long to listen on WebSocket before disconnecting
WS_LISTEN_SECONDS = 30

# ── Logging ────────────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)-7s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("smoke_test")

# ── Helpers ────────────────────────────────────────────────────────────

PASS = "\033[92m✔ PASS\033[0m"
FAIL = "\033[91m✘ FAIL\033[0m"
WARN = "\033[93m⚠ WARN\033[0m"
INFO = "\033[94mℹ INFO\033[0m"


def pretty(obj: Any, max_depth: int = 3) -> str:
    """Pretty-print JSON, truncating deeply nested structures."""
    return json.dumps(obj, indent=2, default=str)[:4000]


def check(label: str, condition: bool, detail: str = "") -> bool:
    """Print a pass/fail check."""
    status = PASS if condition else FAIL
    suffix = f"  ({detail})" if detail else ""
    print(f"  {status}  {label}{suffix}")
    return condition


# ── Test steps ─────────────────────────────────────────────────────────


async def step_1_authenticate(session: aiohttp.ClientSession) -> str | None:
    """Step 1: Authenticate with client_credentials grant."""
    print("\n═══ Step 1: Authentication ═══")
    print(f"  {INFO}  POST {AUTH_URL}")
    print(f"  {INFO}  grant_type=client_credentials")

    data = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }

    try:
        async with session.post(AUTH_URL, data=data) as resp:
            status = resp.status
            body = await resp.text()
            print(f"  {INFO}  HTTP {status}")

            check("Auth endpoint reachable", status != 0)

            if status != 200:
                print(f"  {FAIL}  Authentication failed: {body[:500]}")

                # Try alternative: maybe they need a different grant type?
                if status == 400:
                    print(f"  {WARN}  Got 400 — client_credentials might not be supported.")
                    print(f"  {WARN}  Check if authorization_code flow is required instead.")
                if status == 401:
                    print(f"  {WARN}  Got 401 — credentials may be invalid or expired.")
                    print(f"  {WARN}  Verify client_id and client_secret in Husqvarna Developer Portal.")
                return None

            result = json.loads(body)
            log.debug("Auth response:\n%s", pretty(result))

            # Validate expected fields
            token = result.get("access_token")
            expires_in = result.get("expires_in")
            token_type = result.get("token_type")
            provider = result.get("provider")
            scope = result.get("scope")

            check("Response has access_token", token is not None)
            check("Response has expires_in", expires_in is not None, f"{expires_in}s")
            check(
                "token_type is Bearer",
                str(token_type).lower() == "bearer",
                f"got '{token_type}'",
            )

            # Log extra fields we might not expect
            expected_keys = {"access_token", "expires_in", "token_type", "scope", "provider"}
            extra_keys = set(result.keys()) - expected_keys
            if extra_keys:
                print(f"  {WARN}  Unexpected fields in auth response: {extra_keys}")
                for k in extra_keys:
                    print(f"         {k}: {result[k]}")

            if provider:
                print(f"  {INFO}  provider: {provider}")
            if scope:
                print(f"  {INFO}  scope: {scope}")

            return token

    except aiohttp.ClientError as err:
        print(f"  {FAIL}  Connection error: {err}")
        print(f"  {WARN}  Is the auth URL correct? Tried: {AUTH_URL}")
        return None


async def step_2_get_locations(
    session: aiohttp.ClientSession, token: str
) -> list[dict[str, Any]]:
    """Step 2: Fetch locations."""
    print("\n═══ Step 2: Get Locations ═══")
    print(f"  {INFO}  GET {LOCATIONS_URL}")

    headers = {
        "Authorization": f"Bearer {token}",
        "X-Api-Key": CLIENT_ID,
        "Content-Type": "application/vnd.api+json",
    }

    try:
        async with session.get(LOCATIONS_URL, headers=headers) as resp:
            status = resp.status
            body = await resp.text()
            print(f"  {INFO}  HTTP {status}")

            if status != 200:
                print(f"  {FAIL}  Get locations failed: {body[:500]}")
                if status == 403:
                    print(f"  {WARN}  403 — X-Api-Key header may be wrong or missing scope.")
                return []

            result = json.loads(body)
            log.debug("Locations response:\n%s", pretty(result))

            # Validate structure
            check("Response is JSON object", isinstance(result, dict))
            data = result.get("data")
            check("Response has 'data' key", data is not None)
            check("'data' is a list", isinstance(data, list))

            if not data:
                print(f"  {WARN}  No locations found. Is this account linked to a Gardena system?")
                return []

            print(f"  {INFO}  Found {len(data)} location(s)")

            for loc in data:
                loc_id = loc.get("id", "?")
                loc_type = loc.get("type", "?")
                loc_name = loc.get("attributes", {}).get("name", "?")
                print(f"  {INFO}  Location: {loc_name} (id={loc_id}, type={loc_type})")

                check(
                    f"Location type is 'LOCATION'",
                    loc_type == "LOCATION",
                    f"got '{loc_type}'",
                )

                # Check for unexpected structure
                expected_keys = {"id", "type", "attributes", "relationships"}
                extra = set(loc.keys()) - expected_keys
                if extra:
                    print(f"  {WARN}  Extra keys on location: {extra}")

            return data

    except aiohttp.ClientError as err:
        print(f"  {FAIL}  Connection error: {err}")
        return []


async def step_3_get_location_details(
    session: aiohttp.ClientSession, token: str, location_id: str
) -> list[dict[str, Any]]:
    """Step 3: Fetch location details with devices."""
    print(f"\n═══ Step 3: Get Location Details ({location_id}) ═══")
    url = f"{LOCATIONS_URL}/{location_id}"
    print(f"  {INFO}  GET {url}")

    headers = {
        "Authorization": f"Bearer {token}",
        "X-Api-Key": CLIENT_ID,
        "Content-Type": "application/vnd.api+json",
    }

    try:
        async with session.get(url, headers=headers) as resp:
            status = resp.status
            body = await resp.text()
            print(f"  {INFO}  HTTP {status}")

            if status != 200:
                print(f"  {FAIL}  Get location details failed: {body[:500]}")
                return []

            result = json.loads(body)
            log.debug("Location details:\n%s", pretty(result))

            # Top-level structure
            check("Response has 'data' key", "data" in result)
            included = result.get("included", [])
            check("Response has 'included' key", "included" in result)
            check("'included' is a list", isinstance(included, list))

            if not included:
                print(f"  {WARN}  No devices/services in 'included'. Garden may have no devices.")
                return []

            print(f"  {INFO}  'included' has {len(included)} items")

            # Categorize items
            devices = []
            services_by_type: dict[str, int] = {}
            for item in included:
                item_type = item.get("type", "UNKNOWN")
                if item_type == "DEVICE":
                    devices.append(item)
                services_by_type[item_type] = services_by_type.get(item_type, 0) + 1

            print(f"  {INFO}  Item types: {dict(sorted(services_by_type.items()))}")

            # Validate DEVICE items
            for dev in devices:
                dev_id = dev.get("id", "?")
                attrs = dev.get("attributes", {})
                name = attrs.get("name") or attrs.get("modelType", {}).get("value", "?")

                print(f"\n  {INFO}  ── Device: {name} (id={dev_id}) ──")

                # Check device structure
                check("Device has 'attributes'", "attributes" in dev)
                check("Device has 'relationships'", "relationships" in dev)

                rels = dev.get("relationships", {})
                svc_rel = rels.get("services", {})
                svc_data = svc_rel.get("data", [])
                check(
                    "Device has relationships.services.data[]",
                    isinstance(svc_data, list),
                    f"{len(svc_data)} service(s)",
                )

                # Log device attributes
                for attr_key, attr_val in attrs.items():
                    if isinstance(attr_val, dict) and "value" in attr_val:
                        print(f"         {attr_key}: {attr_val['value']}")
                    else:
                        print(f"         {attr_key}: {attr_val}")

                # Show linked services
                for svc_ref in svc_data:
                    svc_id = svc_ref.get("id", "?")
                    svc_type = svc_ref.get("type", "?")
                    print(f"         → service: {svc_type} ({svc_id})")

            # Validate service items
            print(f"\n  {INFO}  ── Service details ──")
            known_service_types = {
                "MOWER", "VALVE", "VALVE_SET", "SENSOR", "COMMON", "DEVICE",
                "POWER_SOCKET",
            }
            for item in included:
                item_type = item.get("type", "")
                if item_type == "DEVICE":
                    continue

                item_id = item.get("id", "?")
                attrs = item.get("attributes", {})

                if item_type not in known_service_types:
                    print(f"  {WARN}  Unknown service type: '{item_type}' (id={item_id})")

                # Check attribute format: {attr_name: {value: ..., timestamp: ...}}
                nested_value_count = 0
                flat_value_count = 0
                for attr_key, attr_val in attrs.items():
                    if isinstance(attr_val, dict) and "value" in attr_val:
                        nested_value_count += 1
                    else:
                        flat_value_count += 1

                if nested_value_count > 0 or flat_value_count > 0:
                    format_desc = (
                        f"{nested_value_count} nested ({{value:...}}), "
                        f"{flat_value_count} flat"
                    )
                    print(f"         {item_type} ({item_id}): {format_desc}")

                    if flat_value_count > 0 and nested_value_count > 0:
                        print(
                            f"  {WARN}  Mixed attribute formats in {item_type}!"
                        )
                        for k, v in attrs.items():
                            if not (isinstance(v, dict) and "value" in v):
                                print(f"           flat attr: {k} = {v}")

            return included

    except aiohttp.ClientError as err:
        print(f"  {FAIL}  Connection error: {err}")
        return []


async def step_4_get_websocket_url(
    session: aiohttp.ClientSession, token: str, location_id: str
) -> str | None:
    """Step 4: Request a WebSocket URL."""
    print(f"\n═══ Step 4: Get WebSocket URL ({location_id}) ═══")
    print(f"  {INFO}  POST {WEBSOCKET_URL}")

    headers = {
        "Authorization": f"Bearer {token}",
        "X-Api-Key": CLIENT_ID,
        "Content-Type": "application/vnd.api+json",
    }

    payload = {
        "data": {
            "type": "WEBSOCKET",
            "attributes": {"locationId": location_id},
            "id": "smoke-test-request-1",
        }
    }

    log.debug("WebSocket request payload:\n%s", pretty(payload))

    try:
        async with session.post(
            WEBSOCKET_URL, headers=headers, json=payload
        ) as resp:
            status = resp.status
            body = await resp.text()
            print(f"  {INFO}  HTTP {status}")

            if status not in (200, 201):
                print(f"  {FAIL}  WebSocket URL request failed: {body[:500]}")

                if status == 404:
                    print(f"  {WARN}  404 — endpoint may have changed.")
                    print(f"  {WARN}  Try /websocket vs /websockets")
                if status == 400:
                    print(f"  {WARN}  400 — request payload format may be wrong.")
                    log.info("Sent payload: %s", pretty(payload))
                return None

            result = json.loads(body)
            log.debug("WebSocket response:\n%s", pretty(result))

            check("Response has 'data'", "data" in result)

            data = result.get("data", {})
            check("data has 'type'", "type" in data, f"got '{data.get('type')}'")
            check("data has 'id'", "id" in data)
            check("data has 'attributes'", "attributes" in data)

            attrs = data.get("attributes", {})
            ws_url = attrs.get("url")
            check("attributes has 'url'", ws_url is not None)

            if ws_url:
                # Mask the URL for security (it may contain auth tokens)
                masked = ws_url[:50] + "..." if len(ws_url) > 50 else ws_url
                print(f"  {INFO}  WebSocket URL: {masked}")
                check(
                    "URL starts with wss://",
                    ws_url.startswith("wss://"),
                    f"starts with '{ws_url[:8]}'",
                )

            # Check for extra fields
            expected_attrs = {"url"}
            extra = set(attrs.keys()) - expected_attrs
            if extra:
                print(f"  {WARN}  Extra attributes in WS response: {extra}")
                for k in extra:
                    print(f"         {k}: {attrs[k]}")

            return ws_url

    except aiohttp.ClientError as err:
        print(f"  {FAIL}  Connection error: {err}")
        return None


async def step_5_websocket_listen(
    session: aiohttp.ClientSession, ws_url: str
) -> None:
    """Step 5: Connect to WebSocket and log messages."""
    print(f"\n═══ Step 5: WebSocket Listen ({WS_LISTEN_SECONDS}s) ═══")

    ssl_context = ssl.create_default_context()
    msg_count = 0
    msg_types: dict[str, int] = {}

    try:
        async with session.ws_connect(
            ws_url, ssl=ssl_context, heartbeat=30, timeout=15
        ) as ws:
            print(f"  {PASS}  WebSocket connected")

            async def listen():
                nonlocal msg_count
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        msg_count += 1
                        try:
                            data = json.loads(msg.data)
                            msg_type = data.get("type", "UNKNOWN")
                            msg_types[msg_type] = msg_types.get(msg_type, 0) + 1

                            # Log first few messages in detail
                            if msg_count <= 5:
                                print(f"\n  {INFO}  Message #{msg_count} (type={msg_type}):")
                                # Show structure without flooding
                                print(f"         keys: {list(data.keys())}")
                                if "id" in data:
                                    print(f"         id: {data['id']}")
                                if "attributes" in data:
                                    attrs = data["attributes"]
                                    print(f"         attributes keys: {list(attrs.keys())}")
                                    # Check attribute format
                                    for k, v in list(attrs.items())[:3]:
                                        if isinstance(v, dict) and "value" in v:
                                            print(f"         {k}: {{value: {v['value']}}}")
                                        else:
                                            print(f"         {k}: {v}")
                                log.debug("Full message:\n%s", pretty(data))
                            elif msg_count % 10 == 0:
                                print(f"  {INFO}  ... {msg_count} messages received")

                        except json.JSONDecodeError:
                            print(f"  {WARN}  Non-JSON message: {msg.data[:200]}")

                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        print(f"  {FAIL}  WebSocket error: {ws.exception()}")
                        break
                    elif msg.type in (
                        aiohttp.WSMsgType.CLOSE,
                        aiohttp.WSMsgType.CLOSING,
                        aiohttp.WSMsgType.CLOSED,
                    ):
                        print(f"  {INFO}  WebSocket closed by server")
                        break

            try:
                await asyncio.wait_for(listen(), timeout=WS_LISTEN_SECONDS)
            except asyncio.TimeoutError:
                print(f"\n  {INFO}  Listen timeout ({WS_LISTEN_SECONDS}s) reached")

            print(f"\n  {INFO}  Total messages received: {msg_count}")
            if msg_types:
                print(f"  {INFO}  Message types: {dict(sorted(msg_types.items()))}")
                # Validate against expected types
                known = {
                    "MOWER", "VALVE", "VALVE_SET", "SENSOR", "COMMON",
                    "DEVICE", "POWER_SOCKET", "LOCATION",
                }
                unknown = set(msg_types.keys()) - known
                if unknown:
                    print(f"  {WARN}  Unknown message types: {unknown}")
            else:
                print(f"  {WARN}  No messages received in {WS_LISTEN_SECONDS}s")
                print(f"  {WARN}  This is normal if no device state changed.")

    except aiohttp.WSServerHandshakeError as err:
        print(f"  {FAIL}  WebSocket handshake failed: {err}")
        print(f"  {WARN}  The WS URL may have expired or the format is wrong.")
    except aiohttp.ClientError as err:
        print(f"  {FAIL}  WebSocket connection error: {err}")
    except asyncio.TimeoutError:
        print(f"  {FAIL}  WebSocket connection timeout (15s)")


async def step_6_verify_command_endpoint(
    session: aiohttp.ClientSession, token: str
) -> None:
    """Step 6: Probe the command endpoint (without sending a real command).

    We send a deliberately invalid request to see if the endpoint exists
    and returns a structured error (vs 404).
    """
    print("\n═══ Step 6: Probe Command Endpoint ═══")

    # Test both /command and /commands (plural) to see which exists
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Api-Key": CLIENT_ID,
        "Content-Type": "application/vnd.api+json",
    }

    for path in ["/command/fake-service-id", "/commands/fake-service-id"]:
        url = f"{API_BASE}{path}"
        print(f"  {INFO}  PUT {url}")

        try:
            # Send an empty body to provoke a validation error (not a real command)
            async with session.put(url, headers=headers, json={}) as resp:
                status = resp.status
                body = await resp.text()
                print(f"         HTTP {status}")

                if status == 404:
                    print(f"         → Endpoint does not exist")
                elif status == 422 or status == 400:
                    print(f"         → Endpoint exists! (validation error as expected)")
                    log.debug("Error response: %s", body[:500])
                elif status == 403:
                    print(f"         → Endpoint may exist (permission denied)")
                else:
                    print(f"         → Unexpected status, body: {body[:300]}")

        except aiohttp.ClientError as err:
            print(f"         → Connection error: {err}")


# ── Main ───────────────────────────────────────────────────────────────


async def main() -> None:
    """Run all smoke test steps."""
    print("╔══════════════════════════════════════════════════════╗")
    print("║  Gardena Smart System API v2 — Smoke Test           ║")
    print("╚══════════════════════════════════════════════════════╝")

    if not CLIENT_ID or not CLIENT_SECRET:
        print(f"\n  {FAIL}  Missing credentials!")
        print("  Set GARDENA_CLIENT_ID and GARDENA_CLIENT_SECRET env vars.")
        print("  Get these from: https://developer.husqvarnagroup.cloud/")
        sys.exit(1)

    print(f"\n  {INFO}  Client ID: {CLIENT_ID[:8]}...{CLIENT_ID[-4:]}")
    print(f"  {INFO}  Log level: {LOG_LEVEL}")

    async with aiohttp.ClientSession() as session:
        # Step 1: Auth
        token = await step_1_authenticate(session)
        if not token:
            print(f"\n  {FAIL}  Cannot continue without authentication.")
            sys.exit(1)

        # Step 2: Locations
        locations = await step_2_get_locations(session, token)
        if not locations:
            print(f"\n  {WARN}  No locations — skipping device/WS tests.")
            await step_6_verify_command_endpoint(session, token)
            print_summary()
            return

        location_id = locations[0]["id"]

        # Step 3: Location details + devices
        await step_3_get_location_details(session, token, location_id)

        # Step 4: WebSocket URL
        ws_url = await step_4_get_websocket_url(session, token, location_id)

        # Step 5: WebSocket listen
        if ws_url:
            await step_5_websocket_listen(session, ws_url)
        else:
            print(f"\n  {WARN}  Skipping WebSocket listen (no URL obtained)")

        # Step 6: Command endpoint probe
        await step_6_verify_command_endpoint(session, token)

    print_summary()


def print_summary() -> None:
    """Print final summary."""
    print("\n╔══════════════════════════════════════════════════════╗")
    print("║  Summary                                            ║")
    print("╠══════════════════════════════════════════════════════╣")
    print("║  Review the output above for ✔/✘/⚠ markers.        ║")
    print("║  Key things to verify:                              ║")
    print("║  1. Auth: client_credentials grant works            ║")
    print("║  2. Locations: JSON:API format with data[]          ║")
    print("║  3. Devices: included[] with DEVICE + services      ║")
    print("║  4. Attributes: nested {value: ...} format          ║")
    print("║  5. WebSocket: URL obtained and connectable         ║")
    print("║  6. Commands: /command vs /commands endpoint        ║")
    print("╚══════════════════════════════════════════════════════╝")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n  {INFO}  Interrupted by user")
