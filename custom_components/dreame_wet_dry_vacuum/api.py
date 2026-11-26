"""Dreame Home cloud API client."""
from __future__ import annotations

import hashlib
import json
import logging
import random
import re
import string
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import aiohttp
from Crypto.Cipher import AES

from .const import (
    CN_BASE_URL,
    DREAME_BASIC_AUTH,
    DREAME_IOT_PREFIX,
    DREAME_PASSWORD_SALT,
    DREAME_RLC_KEY,
    DREAME_TENANT_ID,
    ENDPOINTS,
    EU_BASE_URL,
    H15_PRO_HEAT_MODEL,
    H15_PROPERTY_META,
    H15_TARGETED_KEYS,
)

_LOGGER = logging.getLogger(__name__)

REGION_URLS = {
    "eu": EU_BASE_URL,
    "de": "https://de.iot.dreame.tech:13267",
    "cn": CN_BASE_URL,
    "us": "https://us.iot.dreame.tech:13267",
    "ru": "https://ru.iot.dreame.tech:13267",
    "tw": "https://tw.iot.dreame.tech:13267",
    "sg": "https://sg.iot.dreame.tech:13267",
    "in": "https://in.iot.dreame.tech:13267",
    "i2": "https://i2.iot.dreame.tech:13267",
    "kr": "https://kr.iot.dreame.tech:13267",
}

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)

# Safe bootstrap choices for automatic discovery. The account country is an ISO
# country code and is deliberately separate from the Dreame cloud backend.
COUNTRY_BOOTSTRAP_REGION = {
    "CN": "cn",
    "US": "us",
    "RU": "ru",
    "TW": "tw",
    "SG": "sg",
    "IN": "in",
    "KR": "kr",
}

AUTO_REGION_ORDER = ("eu", "i2", "de", "sg", "us", "in", "tw", "kr", "ru", "cn")
AUTO_DISCOVERY_TIMEOUT = aiohttp.ClientTimeout(total=10)



def _md5_password(password: str) -> str:
    return hashlib.md5((password + DREAME_PASSWORD_SALT).encode()).hexdigest()


def _parse_prop_value(value: Any) -> Any:
    """Parse an iotstatus value (returned as a string) to a native type.

    "0" -> 0, "[81]" -> [81], "abc" -> "abc". Keeps types consistent with the
    MQTT feed, which delivers ints/lists natively.
    """
    if not isinstance(value, str):
        return value
    s = value.strip()
    if s and (s[0] in "[-" or s.isdigit()):
        try:
            return json.loads(s)
        except (ValueError, TypeError):
            pass
    return value


def _compute_rlc(region: str = "eu", country: str = "DE") -> str:
    """Generate the dreame-rlc header value via AES-128-ECB."""
    plain = f"{region}|en|{country.upper()}"
    key = DREAME_RLC_KEY
    cipher = AES.new(key, AES.MODE_ECB)
    # Pad to 16-byte block
    pad_len = 16 - (len(plain) % 16)
    plain_padded = plain + chr(pad_len) * pad_len
    encrypted = cipher.encrypt(plain_padded.encode("utf-8"))
    return encrypted.hex()


def _random_request_id() -> str:
    return "".join(random.choices(string.digits, k=8))


class DreameAPIError(Exception):
    pass


class DreameAuthError(DreameAPIError):
    pass


class DreameAPI:
    """Client for the Dreame Home cloud API."""

    def __init__(
        self,
        username: str,
        password: str,
        region: str = "eu",
        country: str = "",
        session: aiohttp.ClientSession | None = None,
        request_timeout: aiohttp.ClientTimeout | None = None,
    ) -> None:
        self._username = username
        self._password = password
        self._requested_region = region
        self._country = country.upper()
        if len(self._country) != 2:
            raise ValueError("Dreame account country must be a two-letter ISO country code")
        if region == "auto":
            self._region = COUNTRY_BOOTSTRAP_REGION.get(self._country, "eu")
        elif region in REGION_URLS:
            self._region = region
        else:
            raise ValueError(f"Unsupported Dreame cloud region: {region}")
        self._base_url = REGION_URLS[self._region]
        self._access_token: str | None = None
        self._uid: str | None = None
        self._session = session
        self._owns_session = session is None
        self._request_timeout = request_timeout or (
            AUTO_DISCOVERY_TIMEOUT if region == "auto" else REQUEST_TIMEOUT
        )
        self._rlc = _compute_rlc(self._region, self._country)
        self._region_discovery_done = region != "auto"
        self._authenticated_any = False

    @property
    def region(self) -> str:
        """Selected cloud backend after discovery."""
        return self._region

    @property
    def country(self) -> str:
        """Country code used for the account login."""
        return self._country

    @property
    def authenticated_any(self) -> bool:
        """Whether discovery authenticated successfully on any candidate."""
        return self._authenticated_any

    def _set_region(self, region: str) -> None:
        """Switch to a known Dreame cloud backend without re-authenticating."""
        if region not in REGION_URLS:
            return
        self._region = region
        self._base_url = REGION_URLS[region]
        self._rlc = _compute_rlc(region, self._country)

    def _set_domain(self, domain: str) -> None:
        """Use a Dreame-provided API domain when it is safe to trust."""
        host = domain.removeprefix("https://").removeprefix("http://").split("/", 1)[0]
        host = host.split(":", 1)[0]
        if not host.endswith(".dreame.tech"):
            _LOGGER.warning("Ignoring unexpected Dreame login domain: %s", domain)
            return
        self._base_url = f"https://{host}:13267"
        prefix = host.split(".", 1)[0]
        if prefix in REGION_URLS:
            self._region = prefix
            self._rlc = _compute_rlc(prefix, self._country)

    @property
    def uid(self) -> str | None:
        """Account uid, available after login()."""
        return self._uid

    @property
    def access_token(self) -> str | None:
        """Current access token, available after login()."""
        return self._access_token

    def _get_base_headers(self) -> dict[str, str]:
        return {
            "user-agent": "Dart/3.2 (dart:io)",
            "dreame-meta": "cv=i_829",
            "dreame-rlc": self._rlc,
            "tenant-id": DREAME_TENANT_ID,
        }

    def _get_auth_headers(self) -> dict[str, str]:
        headers = self._get_base_headers()
        headers["dreame-auth"] = f"bearer {self._access_token}"
        headers["content-type"] = "application/json"
        return headers

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        return self._session

    async def close(self) -> None:
        # Only close a session we created ourselves, never a shared one.
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()

    async def login(self) -> None:
        """Authenticate and store access token."""
        session = await self._get_session()
        url = self._base_url + ENDPOINTS["token"]

        headers = self._get_base_headers()
        headers["authorization"] = DREAME_BASIC_AUTH
        headers["content-type"] = "application/x-www-form-urlencoded"

        data = {
            "grant_type": "password",
            "scope": "all",
            "platform": "IOS",
            "type": "account",
            "username": self._username,
            "password": _md5_password(self._password),
            "country": self._country,
            "lang": "en",
        }

        try:
            async with session.post(
                url, headers=headers, data=data, timeout=self._request_timeout
            ) as resp:
                if resp.status == 429:
                    raise DreameAPIError("Dreame cloud rate-limited automatic discovery")
                if resp.status != 200:
                    text = await resp.text()
                    raise DreameAuthError(f"Login failed ({resp.status}): {text[:200]}")
                result = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise DreameAPIError(f"Login request failed: {err}") from err

        if "access_token" not in result:
            raise DreameAuthError(f"No access_token in response: {result}")

        self._access_token = result["access_token"]
        self._uid = result.get("uid")

        # Dreame may tell us the account's actual backend in the login response.
        # Try that metadata before the other discovery candidates. A login
        # hint alone does not prove that device discovery has succeeded.
        response_region = str(result.get("region") or "").lower()
        response_domain = str(result.get("domain") or "").strip().lower()
        if self._requested_region == "auto":
            if response_region in REGION_URLS:
                self._set_region(response_region)
            elif response_domain:
                self._set_domain(response_domain)

        _LOGGER.debug(
            "Dreame login successful, uid=%s requested_region=%s active_region=%s country=%s",
            self._uid,
            self._requested_region,
            self._region,
            self._country,
        )

    async def _authed_post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST with bearer auth; re-login and retry exactly once on 401.

        Raises DreameAuthError if the re-login itself is rejected (bad
        credentials), DreameAPIError for transport/protocol failures.
        """
        await self._ensure_logged_in()
        session = await self._get_session()
        for attempt in (1, 2):
            try:
                async with session.post(
                    url,
                    headers=self._get_auth_headers(),
                    json=payload,
                    timeout=self._request_timeout,
                ) as resp:
                    if resp.status == 401 and attempt == 1:
                        await self.login()
                        continue
                    if resp.status != 200:
                        text = await resp.text()
                        raise DreameAPIError(
                            f"Request failed ({resp.status}): {text[:200]}"
                        )
                    return await resp.json(content_type=None)
            except (aiohttp.ClientError, TimeoutError, ValueError) as err:
                raise DreameAPIError(f"Request failed: {err}") from err
        raise DreameAPIError("Still unauthorized after re-login")

    async def _authed_get(
        self, url: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """GET with the existing Dreame bearer session."""
        await self._ensure_logged_in()
        session = await self._get_session()
        for attempt in (1, 2):
            try:
                async with session.get(
                    url,
                    headers=self._get_auth_headers(),
                    params=params or {},
                    timeout=self._request_timeout,
                ) as resp:
                    if resp.status == 401 and attempt == 1:
                        await self.login()
                        continue
                    if resp.status != 200:
                        body = await resp.text()
                        raise DreameAPIError(
                            f"GET failed ({resp.status}): {body[:200]}"
                        )
                    return await resp.json(content_type=None)
            except (aiohttp.ClientError, TimeoutError, ValueError) as err:
                raise DreameAPIError(f"GET request failed: {err}") from err
        raise DreameAPIError("Still unauthorized after re-login")

    async def get_device_info_full(self, device_id: str) -> dict[str, Any]:
        """Return Dreame's full device/info payload for diagnostics."""
        return await self._authed_post(
            self._base_url + "/dreame-user-iot/iotuserbind/device/info",
            {"did": str(device_id)},
        )

    async def get_clean_statistics(
        self, device_id: str, piid: int, stat_type: int, begin_ms: int, end_ms: int, time_zone: str
    ) -> list[dict[str, Any]]:
        """App CleanLog chart data: per-period seconds at one dirt level (1.64-1.66)."""
        result = await self._authed_post(
            self._base_url + "/dreame-iot-data/iotaggr/statitics-data",
            {"did": str(device_id), "uid": self.uid, "statisticsType": stat_type,
             "timeZoneId": time_zone, "siid": 1, "piid": piid,
             "beginDate": begin_ms, "endDate": end_ms},
        )
        if not isinstance(result, dict) or result.get("code") != 0:
            raise DreameAPIError(f"statistics request rejected: {str(result)[:200]}")
        data = result.get("data")
        return data if isinstance(data, list) else []

    async def get_clean_sessions(
        self, device_id: str, begin_ms: int, end_ms: int
    ) -> list[dict[str, Any]]:
        """App CleanLog session list (event siid 30 / eiid 1)."""
        result = await self._authed_post(
            self._base_url + "/dreame-iot-data/iotaggr/event-data",
            {"did": str(device_id), "uid": self.uid, "siid": 30, "eiid": 1,
             "beginDate": begin_ms, "endDate": end_ms},
        )
        if not isinstance(result, dict) or result.get("code") != 0:
            raise DreameAPIError(f"session request rejected: {str(result)[:200]}")
        data = result.get("data")
        return data if isinstance(data, list) else []

    async def check_device_version(self, device_id: str) -> dict[str, Any]:
        """App OTA page firmware check (read-only)."""
        result = await self._authed_post(
            self._base_url + "/dreame-user-iot/iotuserbind/checkDeviceVersionV2",
            {"did": str(device_id)},
        )
        if not isinstance(result, dict) or result.get("code") != 0:
            raise DreameAPIError(f"version check rejected: {str(result)[:200]}")
        data = result.get("data")
        return data if isinstance(data, dict) else {}

    async def get_dev_otc_info(self, device_id: str) -> dict[str, Any]:
        """Return the app-facing devOTCInfo payload."""
        return await self._authed_post(
            self._base_url + "/dreame-user-iot/iotstatus/devOTCInfo",
            {"did": str(device_id)},
        )

    async def get_device_data_probe(self, device_id: str) -> dict[str, Any]:
        """Probe the app's device-data endpoint using the two known request forms."""
        url = self._base_url + "/dreame-user-iot/iotuserdata/getDeviceData"
        result: dict[str, Any] = {}
        for name, payload in (
            ("keys_empty", {"did": str(device_id), "keys": []}),
            ("model_empty", {"did": str(device_id), "model": []}),
        ):
            try:
                result[name] = await self._authed_post(url, payload)
            except DreameAPIError as err:
                result[name] = {"_error": str(err)}
        return result

    async def get_app_plugin_info(
        self,
        model: str,
        app_versions: tuple[int, ...] = (150, 148),
    ) -> dict[str, Any]:
        """Query the Dreamehome per-model RN plugin metadata.

        The Dreame app uses /dreame-product/upgrades/appplugin with the device
        model and an app/plugin compatibility version. This method is read-only
        and returns both attempts so we can see which version the backend accepts.
        """
        url = self._base_url + "/dreame-product/upgrades/appplugin"
        attempts: dict[str, Any] = {}
        for app_ver in app_versions:
            try:
                response = await self._authed_get(
                    url,
                    {
                        "model": model,
                        "appVer": app_ver,
                        "os": 1,
                    },
                )
                attempts[str(app_ver)] = response
                data = response.get("data") if isinstance(response, dict) else None
                if (
                    isinstance(data, dict)
                    and data.get("url")
                    and int(data.get("version") or 0) > 0
                ):
                    return {
                        "selected_app_version": app_ver,
                        "selected": response,
                        "attempts": attempts,
                    }
            except DreameAPIError as err:
                attempts[str(app_ver)] = {"_error": str(err)}
        return {
            "selected_app_version": None,
            "selected": None,
            "attempts": attempts,
        }

    @staticmethod
    def _extract_device_records(result: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract device records from known Dreame device-list response shapes."""
        data = result.get("data") or {}
        records = (data.get("page") or {}).get("records") or []
        if not records:
            records = data.get("records") or []
        return records

    async def _get_devices_from_url(
        self, base_url: str, *, relogin_on_401: bool
    ) -> list[dict[str, Any]]:
        payload = {
            "sharedStatus": 1,
            "current": 1,
            "size": 100,
            "lang": "en",
            "timestamp": int(time.time() * 1000),
        }
        url = base_url + ENDPOINTS["device_list"]
        if relogin_on_401:
            result = await self._authed_post(url, payload)
            return self._extract_device_records(result)

        # Auto-discovery reuses the already-issued bearer token. It must not
        # retry the user's password against every backend.
        session = await self._get_session()
        try:
            async with session.post(
                url,
                headers=self._get_auth_headers(),
                json=payload,
                timeout=self._request_timeout,
            ) as resp:
                if resp.status != 200:
                    return []
                result = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError):
            return []
        return self._extract_device_records(result)

    async def get_devices(self) -> list[dict[str, Any]]:
        """Return devices and auto-detect the correct cloud backend when requested.

        The account password is sent once, for the configured account country.
        Automatic discovery then probes the other Dreame backends with that same
        bearer token; it never repeats the password against other servers or
        other countries.
        """
        # Login may redirect the account to its authoritative region/domain.
        # Resolve that before constructing the device-list URL.
        await self._ensure_logged_in()
        records = await self._get_devices_from_url(
            self._base_url, relogin_on_401=True
        )

        if records:
            self._region_discovery_done = True
        if not records and self._requested_region == "auto" and not self._region_discovery_done:
            # A missing/offline device must not restart a full backend search
            # every time the periodic snapshot is refreshed. One bounded scan
            # per client is enough; a reload permits a deliberate fresh attempt.
            self._region_discovery_done = True
            tried = {self._region}
            for region in AUTO_REGION_ORDER:
                if region in tried:
                    continue
                tried.add(region)
                candidate_records = await self._get_devices_from_url(
                    REGION_URLS[region], relogin_on_401=False
                )
                if candidate_records:
                    self._set_region(region)
                    records = candidate_records
                    _LOGGER.info(
                        "Dreame cloud auto-discovery selected region=%s for country=%s",
                        region,
                        self._country,
                    )
                    break
        self._request_timeout = REQUEST_TIMEOUT

        if records:
            _LOGGER.debug(
                "Dreame device discovery returned %d device(s) for region=%s country=%s; models=%s",
                len(records),
                self._region,
                self._country,
                [record.get("model", "unknown") for record in records],
            )
        else:
            _LOGGER.warning(
                "Dreame device discovery returned no devices for requested_region=%s "
                "active_region=%s country=%s",
                self._requested_region,
                self._region,
                self._country,
            )
        return records

    async def get_device_record(
        self, device_id: str, records: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """Resolve an existing device even when the cloud list is empty.

        The direct info endpoint uses the same bearer session and backend.
        Never initialize an unknown model as a legacy device or substitute a
        different device returned by the server.
        """
        if records is None:
            records = await self.get_devices()
        record = next(
            (item for item in records if str(item.get("did")) == str(device_id)),
            {},
        )
        if record.get("model"):
            return record
        response = await self.get_device_info_full(device_id)
        data = response.get("data")
        if (
            response.get("code") not in (0, "0")
            or response.get("success") is False
            or not isinstance(data, dict)
            or str(data.get("did")) != str(device_id)
            or not data.get("model")
        ):
            raise DreameAPIError(
                "Saved Dreame device could not be resolved by list or device/info; "
                "check account access and cloud region"
            )
        return data

    async def get_device_snapshot(self, device_id: str) -> dict[str, Any]:
        """
        Return the cloud-cached state for a device (battery, status, online).
        This always works, even when the vacuum is docked/asleep, because it
        reads the last state the device reported to the cloud.
        """
        d = await self.get_device_record(device_id)
        return {
            "battery": d.get("battery"),
            "status": d.get("latestStatus"),
            "online": d.get("online"),
            "model": d.get("model"),
            "name": (d.get("deviceInfo") or {}).get("displayName")
            or d.get("customName")
            or d.get("model"),
            "firmware": d.get("ver"),
            "mac": d.get("mac"),
        }

    async def get_status_props(
        self, device_id: str, keys: list[str]
    ) -> dict[str, Any]:
        """
        Read cloud-cached property values by key ("siid.piid").
        Uses /dreame-user-iot/iotstatus/props, which works on this model (unlike
        the realtime get_properties RPC that returns null). Returns {key: value}
        with values parsed to native types (int / list), keys never reported are
        simply absent.
        """
        # The endpoint expects keys as a single comma-separated string.
        payload = {"did": device_id, "keys": ",".join(keys)}
        result = await self._authed_post(
            self._base_url + ENDPOINTS["status_props"], payload
        )

        out: dict[str, Any] = {}
        items = result.get("data")
        if not isinstance(items, list):
            return out
        for item in items:
            if not isinstance(item, dict):
                continue
            key = item.get("key")
            if not isinstance(key, str) or "value" not in item:
                continue
            out[key] = _parse_prop_value(item["value"])
        return out

    async def get_properties(
        self, device_id: str, props: list[dict[str, int]]
    ) -> list[dict[str, Any]]:
        """
        Fetch device properties.
        props: list of {siid, piid} dicts
        Returns list of {siid, piid, value, code} dicts.
        """
        url = self._base_url + ENDPOINTS["send_command"].format(prefix=DREAME_IOT_PREFIX)

        req_id = _random_request_id()
        # Match Dreamehome's Model.getProps request rows. Keep response values
        # normalized so string-encoded enums cannot overwrite valid cached ints.
        params = [
            {"did": device_id, "siid": p["siid"], "piid": p["piid"]}
            for p in props
        ]

        payload = {
            "did": device_id,
            "id": req_id,
            "data": {
                "did": device_id,
                "id": req_id,
                "method": "get_properties",
                "params": params,
                "from": "100000",
            },
        }

        result = await self._authed_post(url, payload)
        data = result.get("data")
        if not isinstance(data, dict):
            return []
        rows = data.get("result")
        if not isinstance(rows, list):
            return []
        normalized: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            item = dict(row)
            for field in ("siid", "piid", "code"):
                if field in item:
                    item[field] = _parse_prop_value(item[field])
            if "value" in item:
                item["value"] = _parse_prop_value(item["value"])
            normalized.append(item)
        return normalized

    async def set_property(
        self, device_id: str, siid: int, piid: int, value: Any
    ) -> bool:
        """Set a single device property."""
        url = self._base_url + ENDPOINTS["send_command"].format(prefix=DREAME_IOT_PREFIX)

        req_id = _random_request_id()
        payload = {
            "did": device_id,
            "id": req_id,
            "data": {
                "did": device_id,
                "id": req_id,
                "method": "set_properties",
                "params": [{"siid": siid, "piid": piid, "value": value}],
                "from": "100000",
            },
        }

        result = await self._authed_post(url, payload)
        results = result.get("data", {}).get("result", [])
        return all(r.get("code", -1) == 0 for r in results)

    async def set_h15_properties(
        self, device_id: str, properties: dict[tuple[int, int], int]
    ) -> bool:
        """Send one H15 app-style batch and require explicit acknowledgements.

        Kept separate from the existing H14 set_property path.
        """
        if not properties:
            return False
        req_id = _random_request_id()
        # The official Dreamehome plugin puts the device DID on every property
        # row (Model.createSetPropReq), in addition to the outer command DID.
        params = [
            {"did": device_id, "siid": siid, "piid": piid, "value": value}
            for (siid, piid), value in properties.items()
        ]
        result = await self._authed_post(
            self._base_url + ENDPOINTS["send_command"].format(prefix=DREAME_IOT_PREFIX),
            {
                "did": device_id, "id": req_id,
                "data": {
                    "did": device_id, "id": req_id, "method": "set_properties",
                    "params": params, "from": "100000",
                },
            },
        )
        data = result.get("data")
        if not isinstance(data, dict):
            # Verified on a real H15 Pro Heat: the cloud answers code 80001
            # ("device may be offline, command timed out") even though the device
            # receives and executes the command. Treat only that code as sent;
            # the result is confirmed afterwards from device telemetry.
            if _parse_prop_value(result.get("code")) == 80001:
                _LOGGER.warning(
                    "H15 set_properties sent; cloud timed out waiting for the device reply (80001)"
                )
                return True
            _LOGGER.warning(
                "H15 set_properties was not acknowledged (cloud reply: %s)", str(result)[:300]
            )
            return False
        outer_code = _parse_prop_value(data.get("code", 0)) if isinstance(data, dict) else None
        rows = data.get("result") if isinstance(data, dict) and outer_code == 0 else None
        if not isinstance(rows, list) or len(rows) != len(params):
            _LOGGER.warning(
                "H15 set_properties was not acknowledged (response_code=%s, expected_rows=%d, received_rows=%s)",
                outer_code, len(params), len(rows) if isinstance(rows, list) else "invalid",
            )
            return False
        returned: set[tuple[int, int]] = set()
        for row in rows:
            if not isinstance(row, dict) or _parse_prop_value(row.get("code")) != 0 or _parse_prop_value(row.get("value")) == -1:
                _LOGGER.warning("H15 set_properties rejected a row (code=%s)", row.get("code") if isinstance(row, dict) else "invalid")
                return False
            if "siid" in row or "piid" in row:
                try:
                    pair = (int(_parse_prop_value(row["siid"])), int(_parse_prop_value(row["piid"])))
                except (KeyError, TypeError, ValueError):
                    return False
                if pair not in properties or pair in returned:
                    return False
                returned.add(pair)
        # Some cloud responses contain only code=0 in request order.
        return not returned or returned == set(properties)

    async def call_action(
        self, device_id: str, siid: int, aiid: int, params: list | None = None
    ) -> bool:
        """Call a device action."""
        url = self._base_url + ENDPOINTS["send_command"].format(prefix=DREAME_IOT_PREFIX)

        req_id = _random_request_id()
        payload = {
            "did": device_id,
            "id": req_id,
            "data": {
                "did": device_id,
                "id": req_id,
                "method": "action",
                "params": {
                    "siid": siid,
                    "aiid": aiid,
                    "did": device_id,
                    "in": params or [],
                },
                "from": "100000",
            },
        }

        result = await self._authed_post(url, payload)
        return result.get("data", {}).get("code", -1) == 0

    async def discover_properties(
        self,
        device_id: str,
        siid_range: range = range(1, 41),
        piid_range: range = range(1, 121),
    ) -> dict[tuple[int, int], Any]:
        """
        Probe SIID/PIID combinations and return properties with valid responses.

        The default range is intentionally broad (SIID 1-40 / PIID 1-120) so
        newer wet & dry models such as H15 are not clipped at the older PIID-80
        discovery boundary. H15 additionally probes SIID 100 in its coordinator.
        """
        all_props = [
            {"siid": s, "piid": p} for s in siid_range for p in piid_range
        ]
        # Chunk into groups of 50
        results: dict[tuple[int, int], Any] = {}
        chunk_size = 50
        for i in range(0, len(all_props), chunk_size):
            chunk = all_props[i : i + chunk_size]
            try:
                data = await self.get_properties(device_id, chunk)
                for item in data:
                    if item.get("code", -1) == 0:
                        key = (item["siid"], item["piid"])
                        results[key] = item.get("value")
            except DreameAPIError as err:
                _LOGGER.warning("Discovery chunk failed: %s", err)
        return results

    async def _ensure_logged_in(self) -> None:
        if self._access_token is None:
            await self.login()


_MAX_DOWNLOAD_BYTES = 150 * 1024 * 1024

_SENSITIVE_KEYS = {
    "accesstoken",
    "refreshtoken",
    "authorization",
    "binddomain",
    "deviceid",
    "did",
    "email",
    "mac",
    "masteruid",
    "masteruid2uuid",
    "password",
    "serial",
    "serialnumber",
    "sn",
    "ssid",
    "token",
    "uid",
    "uuid",
    "username",
}


def _redact_for_sharing(value: Any) -> Any:
    """Redact account/device identifiers while keeping mapping metadata."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            normalized = str(key).replace("_", "").replace("-", "").lower()
            if normalized in _SENSITIVE_KEYS:
                out[key] = "<redacted>"
            elif normalized in {"url", "respackageurl"} and isinstance(item, str):
                # Preserve host/path so the source can be identified without
                # exposing a signed query string.
                parts = urlsplit(item)
                out[key] = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
            else:
                out[key] = _redact_for_sharing(item)
        return out
    if isinstance(value, list):
        return [_redact_for_sharing(item) for item in value]

    # Dreame sometimes nests device metadata as JSON serialized inside a
    # string. Sanitize that payload too so metadata_share.json stays safe.
    if isinstance(value, str):
        stripped = value.strip()
        if (
            len(stripped) >= 2
            and stripped[0] in "[{"
            and stripped[-1] in "]}"
        ):
            try:
                decoded = json.loads(stripped)
            except (TypeError, ValueError, json.JSONDecodeError):
                decoded = None
            if isinstance(decoded, (dict, list)):
                return json.dumps(
                    _redact_for_sharing(decoded),
                    ensure_ascii=False,
                    separators=(",", ":"),
                )

        # Last-resort redaction for MAC addresses embedded in opaque strings.
        return re.sub(
            r"(?i)(?<![0-9a-f])(?:[0-9a-f]{2}:){5}[0-9a-f]{2}(?![0-9a-f])",
            "<redacted-mac>",
            value,
        )

    return value


async def _download(
    coordinator,
    url: str,
    destination: Path,
) -> dict[str, Any]:
    """Download a Dreame-provided plugin resource to a fixed local path."""
    if not url.lower().startswith("https://"):
        return {"ok": False, "error": "Refusing non-HTTPS download URL"}

    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    session = async_get_clientsession(coordinator.hass)
    timeout = aiohttp.ClientTimeout(total=120)

    try:
        async with session.get(url, timeout=timeout) as response:
            if response.status != 200:
                return {
                    "ok": False,
                    "status": response.status,
                    "error": (await response.text())[:300],
                }

            content_length = response.headers.get("Content-Length")
            if content_length:
                try:
                    if int(content_length) > _MAX_DOWNLOAD_BYTES:
                        return {
                            "ok": False,
                            "error": "Plugin resource exceeds 150 MiB safety limit",
                        }
                except ValueError:
                    pass

            data = await response.read()
            if len(data) > _MAX_DOWNLOAD_BYTES:
                return {
                    "ok": False,
                    "error": "Plugin resource exceeds 150 MiB safety limit",
                }

    except (aiohttp.ClientError, TimeoutError) as err:
        return {"ok": False, "error": str(err)}

    await coordinator.hass.async_add_executor_job(destination.write_bytes, data)
    return {
        "ok": True,
        "path": str(destination),
        "bytes": len(data),
    }



_TEXT_EXTENSIONS = {
    ".js", ".json", ".txt", ".xml", ".html", ".htm", ".css",
    ".map", ".plist", ".properties", ".yaml", ".yml",
}
_MAX_SCAN_FILE_BYTES = 8 * 1024 * 1024
_MAX_SCAN_TOTAL_BYTES = 40 * 1024 * 1024
_MAX_HITS_PER_FILE = 100

_H15_SEARCH_TERMS = (
    "siid",
    "piid",
    "get_properties",
    "set_properties",
    "action",
    "battery",
    "charging",
    "dock",
    "suction",
    "water",
    "detergent",
    "dirty",
    "tank",
    "drying",
    "self-clean",
    "self clean",
    "roller",
    "brush",
    "filter",
    "traction",
    "mode",
    "hot water",
    "temperature",
)


def _safe_snippet(text: str, start: int, end: int, radius: int = 120) -> str:
    """Return a compact printable context snippet."""
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    snippet = text[left:right].replace("\x00", " ")
    snippet = re.sub(r"\s+", " ", snippet).strip()
    return snippet[:600]


def _inspect_archive_sync(path: Path) -> dict[str, Any]:
    """Inventory a downloaded plugin/archive without executing its contents."""
    result: dict[str, Any] = {
        "path": str(path),
        "is_zip": False,
        "files": [],
        "miot_pairs": [],
        "keyword_hits": [],
    }

    if not path.exists():
        result["error"] = "file does not exist"
        return result

    if not zipfile.is_zipfile(path):
        result["error"] = "download is not a ZIP archive"
        return result

    result["is_zip"] = True
    scanned_total = 0
    pair_seen: set[tuple[int, int, str]] = set()

    pair_patterns = (
        re.compile(
            r"""["']?siid["']?\s*[:=]\s*(\d+).{0,120}?["']?piid["']?\s*[:=]\s*(\d+)""",
            re.IGNORECASE | re.DOTALL,
        ),
        re.compile(
            r"""["']?piid["']?\s*[:=]\s*(\d+).{0,120}?["']?siid["']?\s*[:=]\s*(\d+)""",
            re.IGNORECASE | re.DOTALL,
        ),
    )

    with zipfile.ZipFile(path, "r") as archive:
        infos = archive.infolist()
        result["file_count"] = len(infos)
        result["uncompressed_bytes"] = sum(info.file_size for info in infos)

        for info in infos:
            if info.is_dir():
                continue

            result["files"].append(
                {
                    "name": info.filename,
                    "bytes": info.file_size,
                    "compressed_bytes": info.compress_size,
                }
            )

            suffix = Path(info.filename).suffix.lower()
            likely_text = (
                suffix in _TEXT_EXTENSIONS
                or "bundle" in info.filename.lower()
                or info.filename.lower().endswith("index")
            )
            if not likely_text:
                continue
            if info.file_size <= 0 or info.file_size > _MAX_SCAN_FILE_BYTES:
                continue
            if scanned_total + info.file_size > _MAX_SCAN_TOTAL_BYTES:
                break

            try:
                raw = archive.read(info)
            except (OSError, RuntimeError, zipfile.BadZipFile) as err:
                _LOGGER.debug("Could not inspect archive member %s: %s", info.filename, err)
                continue

            scanned_total += len(raw)
            text = raw.decode("utf-8", errors="ignore")
            if not text:
                continue

            # Extract likely MIoT pair definitions from JavaScript/config.
            for pattern_index, pattern in enumerate(pair_patterns):
                for match in pattern.finditer(text):
                    if pattern_index == 0:
                        siid, piid = int(match.group(1)), int(match.group(2))
                    else:
                        piid, siid = int(match.group(1)), int(match.group(2))

                    marker = (siid, piid, info.filename)
                    if marker in pair_seen:
                        continue
                    pair_seen.add(marker)

                    result["miot_pairs"].append(
                        {
                            "siid": siid,
                            "piid": piid,
                            "property": f"{siid}.{piid}",
                            "file": info.filename,
                            "context": _safe_snippet(
                                text, match.start(), match.end()
                            ),
                        }
                    )

            # Find semantic words near property definitions / UI strings.
            lower = text.lower()
            per_file_hits = 0
            for term in _H15_SEARCH_TERMS:
                start = 0
                while per_file_hits < _MAX_HITS_PER_FILE:
                    pos = lower.find(term, start)
                    if pos < 0:
                        break
                    result["keyword_hits"].append(
                        {
                            "term": term,
                            "file": info.filename,
                            "context": _safe_snippet(
                                text, pos, pos + len(term)
                            ),
                        }
                    )
                    per_file_hits += 1
                    start = pos + len(term)

    result["scanned_text_bytes"] = scanned_total
    result["miot_pairs"].sort(
        key=lambda item: (item["siid"], item["piid"], item["file"])
    )
    return result


async def _write_archive_report(coordinator, archive_path: Path) -> str | None:
    """Create a JSON inventory/search report for a downloaded package."""
    if not archive_path.exists():
        return None

    report = await coordinator.hass.async_add_executor_job(
        _inspect_archive_sync, archive_path
    )
    report_path = archive_path.with_name(
        f"{archive_path.stem}_inventory.json"
    )
    text = json.dumps(report, ensure_ascii=False, indent=2)
    await coordinator.hass.async_add_executor_job(
        report_path.write_text, text, "utf-8"
    )
    return str(report_path)


async def async_export_h15_app_probe(coordinator) -> dict[str, Any]:
    """Collect Dreamehome app metadata and download the H15 model plugin.

    All cloud operations are read-only. No property/action write is performed.
    """
    model = str(coordinator.device_info_raw.get("model") or coordinator.model or "")
    if model.lower() != H15_PRO_HEAT_MODEL:
        raise ValueError(f"H15 app probe only supports {H15_PRO_HEAT_MODEL}, got {model}")

    api = coordinator.api
    did = coordinator.device_id

    # Refresh the expanded read-only H15 profile first so the exported
    # properties represent the newest cache/live values available.
    refresh: dict[str, Any] = {"ok": True}
    try:
        await coordinator.async_refresh_h15_mapping()
    except Exception as err:  # noqa: BLE001 -- diagnostic export preserves partial results
        refresh = {"ok": False, "error": f"{type(err).__name__}: {err}"}
        _LOGGER.debug("H15 pre-export refresh failed (non-fatal): %s", err)

    manifest = await coordinator.hass.async_add_executor_job(
        (Path(__file__).parent / "manifest.json").read_text, "utf-8"
    )

    probe: dict[str, Any] = {
        "model": model,
        "exported_at": datetime.now(UTC).isoformat(),
        "integration_version": json.loads(manifest)["version"],
        "mapping_refresh": refresh,
        "last_mapping_scan": (
            coordinator.h15_last_scan.isoformat()
            if coordinator.h15_last_scan is not None else None
        ),
        "mapping_changes": coordinator.h15_last_changes,
        "mapping_profile": {
            f"{siid}.{piid}": {
                **meta,
                "observed": (siid, piid) in coordinator.props,
            }
            for (siid, piid), meta in sorted(H15_PROPERTY_META.items())
        },
        "properties": {
            f"{siid}.{piid}": value
            for (siid, piid), value in sorted(coordinator.props.items())
        },
    }

    async def capture(name: str, awaitable) -> None:
        try:
            probe[name] = await awaitable
        except DreameAPIError as err:
            probe[name] = {"_error": str(err)}
        except Exception as err:  # noqa: BLE001 -- report individual diagnostic failures
            probe[name] = {"_error": f"{type(err).__name__}: {err}"}

    await capture("device_info", api.get_device_info_full(did))
    await capture("dev_otc_info", api.get_dev_otc_info(did))
    await capture("device_data", api.get_device_data_probe(did))
    await capture("app_plugin", api.get_app_plugin_info(model))

    # Export the exact app-derived keys through both available read paths.
    targeted_key_strings = [f"{siid}.{piid}" for siid, piid in H15_TARGETED_KEYS]
    await capture(
        "targeted_status_props",
        coordinator._get_status_props_chunked(targeted_key_strings),
    )

    async def read_targeted_live() -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for start in range(0, len(H15_TARGETED_KEYS), 50):
            chunk = H15_TARGETED_KEYS[start : start + 50]
            rows.extend(await api.get_properties(
                did, [{"siid": siid, "piid": piid} for siid, piid in chunk]
            ))
        return rows

    await capture(
        "targeted_live_props",
        read_targeted_live(),
    )

    output_dir = Path(coordinator.hass.config.path("dreame_h15_probe"))
    await coordinator.hass.async_add_executor_job(
        output_dir.mkdir, 0o777, True, True
    )

    private_json = output_dir / "metadata_private.json"
    share_json = output_dir / "metadata_share.json"

    private_text = json.dumps(probe, ensure_ascii=False, indent=2, default=str)
    share_text = json.dumps(
        _redact_for_sharing(probe),
        ensure_ascii=False,
        indent=2,
        default=str,
    )

    await coordinator.hass.async_add_executor_job(
        private_json.write_text, private_text, "utf-8"
    )
    await coordinator.hass.async_add_executor_job(
        share_json.write_text, share_text, "utf-8"
    )

    downloads: dict[str, Any] = {}
    plugin_section = probe.get("app_plugin")
    selected = (
        plugin_section.get("selected")
        if isinstance(plugin_section, dict)
        else None
    )
    plugin_data = selected.get("data") if isinstance(selected, dict) else None

    if isinstance(plugin_data, dict):
        plugin_url = plugin_data.get("url")
        if isinstance(plugin_url, str) and plugin_url:
            downloads["appplugin"] = await _download(
                coordinator,
                plugin_url,
                output_dir / "appplugin.zip",
            )

        resource_url = plugin_data.get("resPackageUrl")
        if isinstance(resource_url, str) and resource_url:
            downloads["resources"] = await _download(
                coordinator,
                resource_url,
                output_dir / "resources.zip",
            )

    inventories: dict[str, str] = {}

    appplugin_path = output_dir / "appplugin.zip"
    if (
        isinstance(downloads.get("appplugin"), dict)
        and downloads["appplugin"].get("ok")
    ):
        report = await _write_archive_report(coordinator, appplugin_path)
        if report:
            inventories["appplugin"] = report

    resources_path = output_dir / "resources.zip"
    if (
        isinstance(downloads.get("resources"), dict)
        and downloads["resources"].get("ok")
    ):
        report = await _write_archive_report(coordinator, resources_path)
        if report:
            inventories["resources"] = report

    result = {
        "output_dir": str(output_dir),
        "share_metadata": str(share_json),
        "private_metadata": str(private_json),
        "downloads": downloads,
        "inventories": inventories,
    }

    _LOGGER.warning(
        "H15 app metadata probe completed. Output: %s",
        result,
    )
    return result
