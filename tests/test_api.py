"""Tests for the cloud API client (fake aiohttp session, no network)."""
import asyncio
import json

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


class TestLogin:
    def test_login_success_exposes_uid_and_token(self):
        session = FakeSession(lambda url, kw: FakeResponse(200, TOKEN_OK))
        api = DreameAPI("user", "pw", session=session)
        run(api.login())
        assert api.access_token == "token-1"
        assert api.uid == "UID1"

    def test_login_rejected_raises_auth_error(self):
        session = FakeSession(
            lambda url, kw: FakeResponse(401, {"error": "unauthorized"})
        )
        api = DreameAPI("user", "bad", session=session)
        with pytest.raises(DreameAuthError):
            run(api.login())

    def test_close_never_closes_shared_session(self):
        session = FakeSession(lambda url, kw: FakeResponse(200, TOKEN_OK))
        api = DreameAPI("user", "pw", session=session)
        run(api.close())
        assert session.close_called is False


class TestAuthedRequests:
    def test_get_properties_handles_null_data(self):
        def handler(url, kwargs):
            if "oauth/token" in url:
                return FakeResponse(200, TOKEN_OK)
            return FakeResponse(200, {"code": 0, "data": None})

        api = DreameAPI("u", "p", session=FakeSession(handler))
        assert run(api.get_properties("device", [{"siid": 4, "piid": 2}])) == []

    @pytest.mark.parametrize(
        ("command_result", "accepted"),
        [
            ({"code": 0, "data": {"result": [{"code": 0}]}}, True),
            ({"code": 0, "data": {"result": [{"code": 1}]}}, False),
            ({"code": 0, "data": {"result": []}}, False),
            ({"code": 1, "data": {"result": [{"code": 0}]}}, False),
        ],
    )
    def test_set_property_requires_real_ack(self, command_result, accepted):
        def handler(url, kwargs):
            if "oauth/token" in url:
                return FakeResponse(200, TOKEN_OK)
            return FakeResponse(200, command_result)

        api = DreameAPI("u", "p", session=FakeSession(handler))
        assert run(api.set_property("device", 1, 7, 1)) is accepted

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
        api = DreameAPI("u", "p", session=FakeSession(handler))
        devices = run(api.get_devices())
        assert devices == [{"did": 1, "model": "m"}]
        assert state["logins"] == 1  # only the initial ensure-logged-in

    def test_401_triggers_single_relogin_then_succeeds(self):
        handler, state = self._handler(unauthorized_data_calls=1)
        api = DreameAPI("u", "p", session=FakeSession(handler))
        devices = run(api.get_devices())
        assert devices == [{"did": 1, "model": "m"}]
        assert state["logins"] == 2  # initial + one re-login
        assert state["data_calls"] == 2

    def test_persistent_401_raises_instead_of_recursing(self):
        handler, state = self._handler(unauthorized_data_calls=99)
        api = DreameAPI("u", "p", session=FakeSession(handler))
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

        api = DreameAPI("u", "p", session=FakeSession(handler))
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

        api = DreameAPI("u", "p", session=FakeSession(handler))
        snap = run(api.get_device_snapshot("-12345678"))  # str vs int did
        assert snap["name"] == "H14 Pro"
        assert snap["battery"] == 100
        assert snap["online"] is True
