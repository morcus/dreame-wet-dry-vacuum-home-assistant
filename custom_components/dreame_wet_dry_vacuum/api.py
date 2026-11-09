"""Dreame Home cloud API client."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import string
import time
from typing import Any

import aiohttp
from Crypto.Cipher import AES

from .const import (
    DREAME_BASIC_AUTH,
    DREAME_IOT_PREFIX,
    DREAME_PASSWORD_SALT,
    DREAME_RLC_KEY,
    DREAME_TENANT_ID,
    ENDPOINTS,
    EU_BASE_URL,
    CN_BASE_URL,
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

AUTO_REGION_ORDER = ("eu", "i2", "de", "sg", "us", "in", "tw", "kr", "ru", "cn")
AUTO_DISCOVERY_CONCURRENCY = 6
AUTO_DISCOVERY_TIMEOUT = aiohttp.ClientTimeout(total=10)

# ISO 3166-1 alpha-2 country codes. Kept local so discovery has no extra
# runtime dependency that Home Assistant does not guarantee.
COUNTRY_CODES = tuple("""
AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ
BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR
CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR
GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU
ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ
LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ
MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF
PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI
SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR
TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW
""".split())

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


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
        session: aiohttp.ClientSession | None = None,
        country: str = "DE",
        request_timeout: aiohttp.ClientTimeout | None = None,
    ) -> None:
        self._username = username
        self._password = password
        self._requested_region = region
        self._region = "eu" if region == "auto" else region
        self._country = country.upper()
        self._base_url = REGION_URLS.get(self._region, EU_BASE_URL)
        self._access_token: str | None = None
        self._uid: str | None = None
        self._session = session
        self._owns_session = session is None
        self._request_timeout = request_timeout or (
            AUTO_DISCOVERY_TIMEOUT if region == "auto" else REQUEST_TIMEOUT
        )
        self._rlc = _compute_rlc(self._region, self._country)
        self._region_discovery_done = False
        self._authenticated_any = False

    @property
    def region(self) -> str:
        """Selected backend region after automatic discovery."""
        return self._region

    @property
    def country(self) -> str:
        """Country code used by the successful Dreame login."""
        return self._country

    @property
    def authenticated_any(self) -> bool:
        """Whether any automatic-discovery candidate accepted the account."""
        return self._authenticated_any

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
        _LOGGER.debug("Dreame login successful, uid=%s", self._uid)

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

    async def get_devices(self) -> list[dict[str, Any]]:
        """Return devices, searching all known region/country pairs in auto mode."""
        if self._requested_region == "auto" and not self._region_discovery_done:
            self._region_discovery_done = True
            return await self._discover_devices()

        await self._ensure_logged_in()
        return await self._get_devices_once()

    async def _get_devices_once(self) -> list[dict[str, Any]]:
        """Read the device list from this client's selected backend."""
        payload = {
            "sharedStatus": 1,
            "current": 1,
            "size": 100,
            "lang": "en",
            "timestamp": int(time.time() * 1000),
        }
        result = await self._authed_post(
            self._base_url + ENDPOINTS["device_list"], payload
        )
        data = result.get("data") or {}
        records = (data.get("page") or {}).get("records") or []
        if not records:
            records = data.get("records") or []
        return records

    async def _discover_devices(self) -> list[dict[str, Any]]:
        """Try backend/country combinations concurrently, stopping on a match.

        The worker count and per-request timeout are bounded to avoid flooding
        Dreame. Credentials and tokens are never included in discovery logs.
        """
        country_order = [self._country]
        country_order.extend(code for code in COUNTRY_CODES if code != self._country)
        candidates = [
            (region, country)
            for country in country_order
            for region in AUTO_REGION_ORDER
        ]
        semaphore = asyncio.Semaphore(AUTO_DISCOVERY_CONCURRENCY)
        auth_failures = 0
        other_errors: list[str] = []

        async def try_candidate(region: str, country: str):
            nonlocal auth_failures
            async with semaphore:
                client = DreameAPI(
                    self._username,
                    self._password,
                    region,
                    session=self._session,
                    country=country,
                    request_timeout=AUTO_DISCOVERY_TIMEOUT,
                )
                try:
                    await client.login()
                    self._authenticated_any = True
                    records = await client._get_devices_once()
                    return region, country, records
                except DreameAuthError:
                    auth_failures += 1
                    return None
                except DreameAPIError as err:
                    other_errors.append(f"{region}/{country}: {err}")
                    return None

        tasks = [
            asyncio.create_task(try_candidate(region, country))
            for region, country in candidates
        ]
        try:
            for completed in asyncio.as_completed(tasks):
                result = await completed
                if result and result[2]:
                    region, country, records = result
                    self._region = region
                    self._country = country
                    self._base_url = REGION_URLS[region]
                    self._rlc = _compute_rlc(region, country)
                    self._access_token = None
                    self._uid = None
                    _LOGGER.info(
                        "Dreame auto-discovery selected backend=%s country=%s",
                        region,
                        country,
                    )
                    return records
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        if not self._authenticated_any and other_errors:
            raise DreameAPIError(
                "Automatic region discovery could not reach Dreame cloud endpoints"
            )
        if not self._authenticated_any and auth_failures == len(candidates):
            raise DreameAuthError(
                "Dreame rejected credentials for every region/country combination"
            )
        return []

    async def get_device_snapshot(self, device_id: str) -> dict[str, Any]:
        """
        Return the cloud-cached state for a device (battery, status, online).
        This always works, even when the vacuum is docked/asleep, because it
        reads the last state the device reported to the cloud.
        """
        devices = await self.get_devices()
        for d in devices:
            if str(d.get("did")) == str(device_id):
                return {
                    "battery": d.get("battery"),
                    "status": d.get("latestStatus"),
                    "online": d.get("online"),
                    "model": d.get("model"),
                    "name": d.get("deviceInfo", {}).get("displayName")
                    or d.get("customName")
                    or d.get("model"),
                    "firmware": d.get("ver"),
                    "mac": d.get("mac"),
                }
        return {}

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
        for item in result.get("data") or []:
            key = item.get("key")
            if key is None or "value" not in item:
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
        params = [
            {"siid": p["siid"], "piid": p["piid"], "code": 0, "updateTime": 0}
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
        return result.get("data", {}).get("result", [])

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
        self, device_id: str, siid_range: range = range(1, 11), piid_range: range = range(1, 21)
    ) -> dict[tuple[int, int], Any]:
        """
        Probe all siid/piid combinations and return those that return valid values.
        Useful for discovering what a new device exposes.
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
