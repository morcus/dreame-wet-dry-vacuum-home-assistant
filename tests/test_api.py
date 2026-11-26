"""Tests for the cloud API client (fake aiohttp session, no network)."""
import asyncio
import json
from urllib.parse import urlsplit

import pytest

from custom_components.dreame_wet_dry_vacuum.api import (
    DreameAPI,
    DreameAPIError,
    DreameAuthError,
    _compute_rlc,
    _md5_password,
    _parse_prop_value,
)

TOKEN_OK = {"access_token": "token-1", "uid": "UID1", "expires_in": 7200}


def assert_secure_origin(url: str, hostname: str) -> None:
    """Check the parsed URL origin instead of matching a hostname substring."""
    parts = urlsplit(url)
    assert parts.scheme == "https"
    assert parts.hostname == hostname
    assert parts.port == 13267
    assert parts.username is None
    assert parts.password is None


class FakeResponse:
    def __init__(self, status: int, body):
        self.status = status
        self._body = body

    async def json(self, content_type=None):
        return self._body

    async def text(self):
        return json.dumps(self._body)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class FakeSession:
    """Routes POSTs to a handler(url, kwargs) -> FakeResponse."""

    closed = False

    def __init__(self, handler):
        self._handler = handler
        self.calls: list[str] = []
        self.close_called = False

    def post(self, url, **kwargs):
        self.calls.append(url)
        return self._handler(url, kwargs)

    async def close(self):
        self.close_called = True


def run(coro):
    return asyncio.run(coro)


class TestHelpers:
    def test_parse_prop_value_int(self):
        assert _parse_prop_value("0") == 0
        assert _parse_prop_value("-5") == -5

    def test_parse_prop_value_list(self):
        assert _parse_prop_value("[81]") == [81]

    def test_parse_prop_value_passthrough(self):
        assert _parse_prop_value("abc") == "abc"
        assert _parse_prop_value(7) == 7
        assert _parse_prop_value(None) is None
        # json can't parse these; stay strings
        assert _parse_prop_value("0123") == "0123"
        assert _parse_prop_value("12.5") == "12.5"

    def test_md5_password_is_salted_and_stable(self):
        h = _md5_password("secret")
        assert h == _md5_password("secret")
        assert len(h) == 32
        import hashlib

        assert h != hashlib.md5(b"secret").hexdigest()

    def test_compute_rlc_one_aes_block(self):
        rlc = _compute_rlc("eu")
        assert len(rlc) == 32  # 16-byte block, hex-encoded
        assert rlc == _compute_rlc("eu")
        assert rlc != _compute_rlc("cn")
        assert rlc != _compute_rlc("eu", "IL")
        assert _compute_rlc("eu", "il") == _compute_rlc("eu", "IL")


class TestLogin:
    def test_login_success_exposes_uid_and_token(self):
        seen = {}

        def handler(url, kw):
            seen["data"] = kw["data"]
            seen["headers"] = kw["headers"]
            return FakeResponse(200, TOKEN_OK)

        session = FakeSession(handler)
        api = DreameAPI("user", "pw", country="IL", session=session)
        run(api.login())
        assert api.access_token == "token-1"
        assert api.uid == "UID1"
        assert seen["data"]["country"] == "IL"
        assert seen["headers"]["dreame-rlc"] == _compute_rlc("eu", "IL")

    def test_auto_region_uses_country_bootstrap(self):
        seen = {}

        def handler(url, kw):
            seen["url"] = url
            return FakeResponse(200, TOKEN_OK)

        api = DreameAPI("user", "pw", region="auto", country="US", session=FakeSession(handler))
        run(api.login())
        assert_secure_origin(seen["url"], "us.iot.dreame.tech")

    def test_login_response_region_switches_auto_backend(self):
        token = {**TOKEN_OK, "region": "i2"}
        session = FakeSession(lambda url, kw: FakeResponse(200, token))
        api = DreameAPI("user", "pw", region="auto", country="IL", session=session)
        run(api.login())
        assert api._region == "i2"
        assert api._base_url == "https://i2.iot.dreame.tech:13267"

    def test_region_selects_matching_cloud_host(self):
        seen = {}

        def handler(url, kw):
            seen["url"] = url
            return FakeResponse(200, TOKEN_OK)

        api = DreameAPI("user", "pw", region="us", country="US", session=FakeSession(handler))
        run(api.login())
        assert_secure_origin(seen["url"], "us.iot.dreame.tech")

    def test_unknown_region_is_rejected(self):
        with pytest.raises(ValueError):
            DreameAPI("user", "pw", region="unknown", country="IL", session=FakeSession(lambda u, k: FakeResponse(200, TOKEN_OK)))

    def test_login_rejected_raises_auth_error(self):
        session = FakeSession(
            lambda url, kw: FakeResponse(401, {"error": "unauthorized"})
        )
        api = DreameAPI("user", "bad", country="IL", session=session)
        with pytest.raises(DreameAuthError):
            run(api.login())

    def test_close_never_closes_shared_session(self):
        session = FakeSession(lambda url, kw: FakeResponse(200, TOKEN_OK))
        api = DreameAPI("user", "pw", country="IL", session=session)
        run(api.close())
        assert session.close_called is False


class TestAuthedRequests:
    @pytest.mark.parametrize("region", ["auto", "eu"])
    def test_device_listing_never_repeats_password_between_backends(self, region):
        tokens = []
        lists = []

        def handler(url, kwargs):
            if "oauth/token" in url:
                tokens.append(kwargs["data"])
                return FakeResponse(200, TOKEN_OK)
            lists.append(url)
            return FakeResponse(200, {"data": {"page": {"records": []}}})

        api = DreameAPI("user", "pw", region=region, country="IL", session=FakeSession(handler))
        assert run(api.get_devices()) == []
        first_count = len(lists)
        assert first_count > 1 if region == "auto" else first_count == 1
        assert run(api.get_devices()) == []
        assert len(lists) == first_count + 1
        assert len(tokens) == 1
        assert tokens[0]["country"] == "IL"

    def test_login_region_with_devices_does_not_probe_other_backends(self):
        lists = []

        def handler(url, kwargs):
            if "oauth/token" in url:
                return FakeResponse(200, {**TOKEN_OK, "region": "i2"})
            lists.append(url)
            return FakeResponse(200, {"data": {"page": {"records": [{"did": "saved"}]}}})

        api = DreameAPI("user", "pw", region="auto", country="IL", session=FakeSession(handler))
        assert run(api.get_devices()) == [{"did": "saved"}]
        assert len(lists) == 1
        assert lists[0].startswith("https://i2.iot.dreame.tech:")

    def test_found_region_is_reused_after_device_list_becomes_empty(self):
        found = False
        lists = []

        def handler(url, kwargs):
            nonlocal found
            if "oauth/token" in url:
                return FakeResponse(200, TOKEN_OK)
            lists.append(url)
            if url.startswith("https://us.iot.dreame.tech:") and not found:
                found = True
                return FakeResponse(200, {"data": {"page": {"records": [{"did": "device"}]}}})
            return FakeResponse(200, {"data": {"page": {"records": []}}})

        api = DreameAPI("user", "pw", region="auto", country="IL", session=FakeSession(handler))
        assert run(api.get_devices()) == [{"did": "device"}]
        count = len(lists)
        assert run(api.get_devices()) == []
        assert len(lists) == count + 1
        assert lists[-1].startswith("https://us.iot.dreame.tech:")

    @pytest.mark.parametrize("body", [
        {}, {"data": None}, {"data": {"result": [{"code": 0, "value": -1}, {"code": 0}]}}, {"data": {"result": []}},
        {"data": {"result": [{"code": -1}, {"code": 0}]}},
        {"data": {"result": [{"siid": 24, "piid": 1, "code": 0}] * 2}},
    ])
    def test_h15_write_requires_acknowledgement_for_every_setting(self, body):
        session = FakeSession(lambda url, kw: FakeResponse(
            200, TOKEN_OK if "oauth/token" in url else body
        ))
        api = DreameAPI("u", "p", country="IL", session=session)
        assert not run(api.set_h15_properties("did", {(16, 1): 1, (16, 2): 2}))

    def test_h15_write_accepts_string_encoded_acknowledgement(self):
        def handler(url, kw):
            return FakeResponse(200, TOKEN_OK if "oauth/token" in url else {
                "data": {"code": "0", "result": [{
                    "siid": "16", "piid": "14", "code": "0",
                }]},
            })

        api = DreameAPI("u", "p", country="IL", session=FakeSession(handler))
        assert run(api.set_h15_properties("did", {(16, 14): 30}))

    def test_h15_batch_write_uses_one_rpc_and_preserves_h14_single_write(self):
        calls = []

        def handler(url, kwargs):
            if "oauth/token" in url:
                return FakeResponse(200, TOKEN_OK)
            params = kwargs["json"]["data"]["params"]
            calls.append(params)
            return FakeResponse(200, {"data": {"result": [
                {"siid": p["siid"], "piid": p["piid"], "code": 0} for p in params
            ]}})

        api = DreameAPI("u", "p", country="IL", session=FakeSession(handler))
        assert run(api.set_h15_properties("did", {(16, 1): 1, (16, 2): 2}))
        assert calls == [[
            {"did": "did", "siid": 16, "piid": 1, "value": 1},
            {"did": "did", "siid": 16, "piid": 2, "value": 2},
        ]]
        assert run(api.set_property("did", 23, 1, 1))
        assert calls[-1] == [{"siid": 23, "piid": 1, "value": 1}]

    def test_get_properties_normalizes_server_string_values_and_ids(self):
        def handler(url, kw):
            if "oauth/token" in url:
                return FakeResponse(200, TOKEN_OK)
            sent = kw["json"]["data"]["params"]
            assert sent == [{"did": "did", "siid": 16, "piid": 7}]
            return FakeResponse(200, {"data": {"result": [
                {"siid": "16", "piid": "7", "code": "0", "value": "4"},
                {"siid": "4", "piid": "5", "code": "0", "value": "[81]"},
            ]}})

        api = DreameAPI("u", "p", country="IL", session=FakeSession(handler))
        assert run(api.get_properties("did", [{"siid": 16, "piid": 7}])) == [
            {"siid": 16, "piid": 7, "code": 0, "value": 4},
            {"siid": 4, "piid": 5, "code": 0, "value": [81]},
        ]

    @pytest.mark.parametrize("body", [{"data": None}, {}, {"data": {"result": None}}])
    def test_get_properties_handles_empty_sleeping_response(self, body):
        def handler(url, kwargs):
            return FakeResponse(200, TOKEN_OK if "oauth/token" in url else body)

        api = DreameAPI("u", "p", country="IL", session=FakeSession(handler))
        assert run(api.get_properties("did", [{"siid": 1, "piid": 8}])) == []

    def test_get_properties_preserves_valid_h14_response(self):
        rows = [{"siid": 2, "piid": 1, "code": 0, "value": 16}]

        def handler(url, kwargs):
            body = TOKEN_OK if "oauth/token" in url else {"data": {"result": rows}}
            return FakeResponse(200, body)

        api = DreameAPI("u", "p", country="IL", session=FakeSession(handler))
        assert run(api.get_properties("did", [{"siid": 2, "piid": 1}])) == rows

    def _handler(self, unauthorized_data_calls: int):
        """Token endpoint always succeeds; data endpoint 401s N times first."""
        state = {"data_calls": 0, "logins": 0}

        def handler(url, kwargs):
            if "oauth/token" in url:
                state["logins"] += 1
                return FakeResponse(200, TOKEN_OK)
            state["data_calls"] += 1
            if state["data_calls"] <= unauthorized_data_calls:
                return FakeResponse(401, {})
            return FakeResponse(
                200, {"data": {"page": {"records": [{"did": 1, "model": "m"}]}}}
            )

        return handler, state

    def test_get_devices_happy_path(self):
        handler, state = self._handler(unauthorized_data_calls=0)
        api = DreameAPI("u", "p", country="IL", session=FakeSession(handler))
        devices = run(api.get_devices())
        assert devices == [{"did": 1, "model": "m"}]
        assert state["logins"] == 1  # only the initial ensure-logged-in

    def test_401_triggers_single_relogin_then_succeeds(self):
        handler, state = self._handler(unauthorized_data_calls=1)
        api = DreameAPI("u", "p", country="IL", session=FakeSession(handler))
        devices = run(api.get_devices())
        assert devices == [{"did": 1, "model": "m"}]
        assert state["logins"] == 2  # initial + one re-login
        assert state["data_calls"] == 2

    def test_persistent_401_raises_instead_of_recursing(self):
        handler, state = self._handler(unauthorized_data_calls=99)
        api = DreameAPI("u", "p", country="IL", session=FakeSession(handler))
        with pytest.raises(DreameAPIError):
            run(api.get_devices())
        assert state["data_calls"] == 2  # exactly one retry, no infinite loop

    def test_get_status_props_parses_values(self):
        def handler(url, kwargs):
            if "oauth/token" in url:
                return FakeResponse(200, TOKEN_OK)
            return FakeResponse(
                200,
                {
                    "data": [
                        {"key": "2.1", "value": "7"},
                        {"key": "4.5", "value": "[81]"},
                        {"key": "1.53", "value": None},
                        {"key": None, "value": "ignored"},
                        {"key": "9.9"},  # no value -> skipped
                    ]
                },
            )

        api = DreameAPI("u", "p", country="IL", session=FakeSession(handler))
        props = run(api.get_status_props("did", ["2.1", "4.5", "1.53", "9.9"]))
        assert props == {"2.1": 7, "4.5": [81], "1.53": None}

    def test_get_device_snapshot_matches_did_as_string(self):
        record = {
            "did": -12345678,
            "battery": 100,
            "latestStatus": 7,
            "online": True,
            "model": "dreame.hold.w2306e",
            "deviceInfo": {"displayName": "H14 Pro"},
            "ver": "1.0",
            "mac": "aa:bb",
        }

        def handler(url, kwargs):
            if "oauth/token" in url:
                return FakeResponse(200, TOKEN_OK)
            return FakeResponse(200, {"data": {"page": {"records": [record]}}})

        api = DreameAPI("u", "p", country="IL", session=FakeSession(handler))
        snap = run(api.get_device_snapshot("-12345678"))  # str vs int did
        assert snap["name"] == "H14 Pro"
        assert snap["battery"] == 100
        assert snap["online"] is True


@pytest.mark.parametrize("model", ["dreame.hold.w2449e", "dreame.hold.w2306e"])
def test_saved_device_uses_direct_info_when_cloud_list_is_empty(model):
    record = {"did": "saved", "model": model, "bindDomain": "mqtt.example", "online": True, "latestStatus": 7, "deviceInfo": None}
    def handler(url, kwargs):
        if "oauth/token" in url:
            return FakeResponse(200, {**TOKEN_OK, "region": "eu"})
        if url.endswith("/device/info"):
            assert kwargs["json"] == {"did": "saved"}
            return FakeResponse(200, {"code": 0, "success": True, "data": record})
        return FakeResponse(200, {"data": {"page": {"records": []}}})
    session = FakeSession(handler)
    api = DreameAPI("u", "p", region="auto", country="IL", session=session)
    assert run(api.get_device_record("saved")) == record
    assert run(api.get_device_snapshot("saved"))["online"] is True
    assert api._region == "eu"
    assert sum("oauth/token" in url for url in session.calls) == 1


@pytest.mark.parametrize("body", [
    {"code": 0, "data": {}},
    {"code": 0, "data": {"did": "other", "model": "dreame.hold.w2449e"}},
    {"code": 1, "data": {"did": "saved", "model": "dreame.hold.w2449e"}},
    {"code": 0, "success": False, "data": {"did": "saved", "model": "dreame.hold.w2449e"}},
])
def test_unresolved_saved_device_does_not_create_unknown_model(body):
    session = FakeSession(lambda url, kwargs: FakeResponse(200, TOKEN_OK if "oauth/token" in url else body))
    api = DreameAPI("u", "p", country="IL", session=session)
    with pytest.raises(DreameAPIError, match="could not be resolved"):
        run(api.get_device_record("saved", []))


@pytest.mark.parametrize("hint", [{"region": "eu"}, {"domain": "https://eu.iot.dreame.tech"}])
def test_empty_login_region_does_not_suppress_auto_discovery(hint):
    lists = []
    def handler(url, kwargs):
        if "oauth/token" in url:
            return FakeResponse(200, {**TOKEN_OK, **hint})
        lists.append(url)
        rows = [{"did": "saved", "model": "dreame.hold.w2449e"}] if url.startswith("https://i2.") else []
        return FakeResponse(200, {"data": {"page": {"records": rows}}})
    session = FakeSession(handler)
    api = DreameAPI("u", "p", region="auto", country="IL", session=session)
    assert run(api.get_devices())[0]["did"] == "saved"
    assert api._region == "i2"
    assert len(lists) == 2
    assert len([url for url in session.calls if "oauth/token" in url]) == 1
    assert api._country == "IL"
    assert run(api.get_devices())[0]["did"] == "saved"
    assert len(lists) == 3  # Confirmed server is reused.
