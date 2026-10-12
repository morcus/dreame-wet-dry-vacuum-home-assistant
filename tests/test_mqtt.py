"""Tests for the MQTT client message handling and token refresh (no network)."""
import json

from custom_components.dreame_wet_dry_vacuum.dreame_mqtt import DreameMqttClient


class FakeMsg:
    def __init__(self, payload) -> None:
        self.payload = payload if isinstance(payload, bytes) else json.dumps(payload).encode()


def make_client(updates: list) -> DreameMqttClient:
    return DreameMqttClient(
        uid="UID1",
        access_token="token-1",
        device_id="-12345678",
        model="dreame.hold.w2306e",
        bind_domain="10000.mt.eu.iot.dreame.tech:19973",
        on_update=updates.append,
    )


class TestOnMessage:
    def test_nested_data_params_payload(self):
        updates: list = []
        client = make_client(updates)
        client._on_message(None, None, FakeMsg(
            {"data": {"params": [{"siid": 2, "piid": 1, "value": 7}]}}
        ))
        assert client.state == {(2, 1): 7}
        assert updates == [{(2, 1): 7}]

    def test_top_level_params_payload(self):
        updates: list = []
        client = make_client(updates)
        client._on_message(None, None, FakeMsg(
            {"params": [{"siid": 3, "piid": 1, "value": 100}]}
        ))
        assert client.state == {(3, 1): 100}

    def test_state_accumulates_and_full_state_is_reported(self):
        updates: list = []
        client = make_client(updates)
        client._on_message(None, None, FakeMsg(
            {"params": [{"siid": 2, "piid": 1, "value": 7}]}
        ))
        client._on_message(None, None, FakeMsg(
            {"params": [{"siid": 3, "piid": 1, "value": 99}]}
        ))
        assert updates[-1] == {(2, 1): 7, (3, 1): 99}

    def test_invalid_json_is_ignored(self):
        updates: list = []
        client = make_client(updates)
        client._on_message(None, None, FakeMsg(b"not json"))
        assert client.state == {}
        assert updates == []

    def test_unexpected_json_shapes_are_ignored(self):
        updates: list = []
        client = make_client(updates)
        client._on_message(None, None, FakeMsg([]))
        client._on_message(None, None, FakeMsg({"data": []}))
        client._on_message(None, None, FakeMsg({"params": {"siid": 2}}))
        assert client.state == {}
        assert updates == []

    def test_items_without_siid_piid_are_skipped(self):
        updates: list = []
        client = make_client(updates)
        client._on_message(None, None, FakeMsg(
            {"params": [{"siid": 2}, "garbage", {"siid": 4, "piid": 1, "value": 0}]}
        ))
        assert client.state == {(4, 1): 0}

    def test_callback_exception_does_not_propagate(self):
        client = DreameMqttClient(
            uid="u", access_token="t", device_id="d", model="m",
            bind_domain="h:19973",
            on_update=lambda state: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        client._on_message(None, None, FakeMsg(
            {"params": [{"siid": 2, "piid": 1, "value": 7}]}
        ))  # must not raise
        assert client.state == {(2, 1): 7}


class RecordingPahoClient:
    def __init__(self) -> None:
        self.creds: list[tuple[str, str]] = []

    def username_pw_set(self, username, password) -> None:
        self.creds.append((username, password))


class TestUpdateToken:
    def test_before_start_only_stores_token(self):
        client = make_client([])
        client.update_token("token-2")
        assert client._token == "token-2"  # no paho client yet, no crash

    def test_after_start_refreshes_paho_credentials(self):
        client = make_client([])
        client._client = RecordingPahoClient()
        client.update_token("token-2")
        assert client._client.creds == [("UID1", "token-2")]

    def test_same_token_is_a_noop(self):
        client = make_client([])
        client._client = RecordingPahoClient()
        client.update_token("token-1")  # unchanged
        assert client._client.creds == []


class TestTopic:
    def test_topic_format(self):
        client = make_client([])
        assert client.topic == "/status/-12345678/UID1/dreame.hold.w2306e/eu/"

    def test_default_port_when_missing(self):
        client = DreameMqttClient(
            uid="u", access_token="t", device_id="d", model="m",
            bind_domain="host-only", on_update=lambda s: None,
        )
        assert client._port == 19973


class TestStop:
    def test_disconnect_precedes_loop_stop(self):
        events = []

        class FakePahoClient:
            def disconnect(self):
                events.append("disconnect")

            def loop_stop(self):
                events.append("loop_stop")

        client = make_client([])
        client._client = FakePahoClient()
        client.stop()
        assert events == ["disconnect", "loop_stop"]
        assert client._client is None
