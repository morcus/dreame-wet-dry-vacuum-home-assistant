"""Persistent MQTT client for the Dreame wet & dry vacuum real-time state.

The device publishes property changes to the Dreame MQTT broker (the device's
bindDomain). We subscribe to /status/{did}/{uid}/{model}/eu/ and maintain a
live dict of {(siid, piid): value}. Commands/RPC are NOT supported by this
model, so this client is receive-only.
"""
from __future__ import annotations

import json
import logging
import random
import ssl
from collections.abc import Callable
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt

_LOGGER = logging.getLogger(__name__)

# The Dreame brokers present a certificate issued by Dreame's private CA, so
# validation against the public store is impossible. We pin that CA (bundled
# below, extracted from the live broker chain) and keep full certificate-chain
# and hostname verification enabled.
CA_CERT_FILE = Path(__file__).parent / "dreame_mqtt_ca.pem"


def _make_ssl_context() -> ssl.SSLContext:
    """SSL context pinned to Dreame's private CA, hostname check enabled."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)  # CERT_REQUIRED + check_hostname
    ctx.load_verify_locations(cafile=str(CA_CERT_FILE))
    # Dreame's CA certs lack the AuthorityKeyIdentifier extension, which the
    # strict validation some Python builds enable by default rejects.
    ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return ctx


class DreameMqttClient:
    """Receive-only MQTT client maintaining the device's live property state."""

    def __init__(
        self,
        uid: str,
        access_token: str,
        device_id: str,
        model: str,
        bind_domain: str,
        on_update: Callable[[dict[tuple[int, int], Any]], None],
        region: str = "eu",
    ) -> None:
        self._uid = uid
        self._token = access_token
        self._did = device_id
        self._model = model
        host, _, port = bind_domain.partition(":")
        self._host = host
        self._port = int(port or 19973)
        self._region = region
        self._on_update = on_update
        self._client: mqtt.Client | None = None
        self.state: dict[tuple[int, int], Any] = {}
        self.connected = False

    @property
    def topic(self) -> str:
        return f"/status/{self._did}/{self._uid}/{self._model}/{self._region}/"

    def update_token(self, access_token: str) -> None:
        """Refresh the token used as MQTT password for future reconnects."""
        if access_token == self._token:
            return
        self._token = access_token
        if self._client:
            self._client.username_pw_set(self._uid, access_token)

    def start(self) -> None:
        """Connect in the background.

        Does blocking I/O (SSL context, CA file) — call from an executor.
        """
        cid = "p_" + "".join(random.choices("0123456789abcdef", k=16))
        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id=cid, protocol=mqtt.MQTTv311
        )
        client.username_pw_set(self._uid, self._token)
        client.tls_set_context(_make_ssl_context())
        client.reconnect_delay_set(min_delay=5, max_delay=120)
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.on_disconnect = self._on_disconnect
        self._client = client
        client.connect_async(self._host, self._port, keepalive=60)
        client.loop_start()
        _LOGGER.debug("Dreame MQTT client started for %s", self._did)

    def stop(self) -> None:
        if self._client:
            try:
                self._client.disconnect()
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Dreame MQTT disconnect failed: %s", err)
            self._client.loop_stop()
            self._client = None

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            _LOGGER.warning("Dreame MQTT connect failed: %s", reason_code)
            return
        self.connected = True
        client.subscribe(self.topic)
        _LOGGER.info("Dreame MQTT connected, subscribed %s", self.topic)

    def _on_disconnect(
        self, client, userdata, disconnect_flags, reason_code, properties
    ) -> None:
        self.connected = False
        _LOGGER.debug("Dreame MQTT disconnected: %s", reason_code)

    def _on_message(self, client, userdata, msg) -> None:
        try:
            payload = msg.payload.decode("utf-8", "replace")
            data = json.loads(payload)
        except (ValueError, UnicodeDecodeError):
            return
        if not isinstance(data, dict):
            return
        nested = data.get("data")
        params = (nested.get("params") if isinstance(nested, dict) else None) or data.get("params") or []
        if not isinstance(params, list):
            return
        changed: dict[tuple[int, int], Any] = {}
        for item in params:
            if isinstance(item, dict) and "siid" in item and "piid" in item:
                key = (item["siid"], item["piid"])
                self.state[key] = item.get("value")
                changed[key] = item.get("value")
        if changed:
            try:
                self._on_update(dict(self.state))
            except Exception:
                _LOGGER.exception("Error in MQTT update callback")
