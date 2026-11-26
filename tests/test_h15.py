"""H15 profile isolation and shareable diagnostic export regressions."""
import asyncio
import importlib
import json
import sys
import types
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

import pytest

from custom_components.dreame_wet_dry_vacuum.const import (
    H15_PROPERTY_META,
    H15_TARGETED_KEYS,
    KNOWN_SELECT_PROPS,
    is_h15_pro_heat,
)


def test_h14_and_h15_traction_keep_distinct_values():
    # These devices deliberately interpret the same property differently.
    assert KNOWN_SELECT_PROPS[(23, 1)]["options"] == {
        0: "Light", 1: "Balanced", 2: "Strong",
    }
    assert H15_PROPERTY_META[(23, 1)]["value_map"] == {
        0: "Balanced", 1: "Gentle", 2: "Turbo",
    }
    assert not is_h15_pro_heat("dreame.hold.w2306e")
    assert not is_h15_pro_heat(None)
    assert is_h15_pro_heat("dreame.hold.w2449e")


@pytest.fixture
def probe(monkeypatch):
    # The exporter needs only this HA adapter; no HA installation or real
    # cloud account is required. Restore modules after each test.
    name = "homeassistant.helpers.aiohttp_client"
    adapter = types.ModuleType(name)
    adapter.async_get_clientsession = lambda hass: None
    monkeypatch.setitem(sys.modules, name, adapter)
    module_name = "custom_components.dreame_wet_dry_vacuum.api"
    monkeypatch.delitem(sys.modules, module_name, raising=False)
    module = importlib.import_module(module_name)
    yield module
    sys.modules.pop(module_name, None)


def test_shared_export_redacts_token_variants_and_signed_urls(probe):
    original = {
        "access_token": "secret-a", "refresh-token": "secret-b",
        "nested": [{"serial_number": "secret-c", "did": "secret-d"}],
        "url": "https://example.com/plugin.zip?signature=secret-e#token",
        "properties": {"3.1": 100, "1.7": 1},
    }
    shared = probe._redact_for_sharing(original)
    assert shared["access_token"] == "<redacted>"
    assert shared["refresh-token"] == "<redacted>"
    assert shared["nested"][0] == {
        "serial_number": "<redacted>", "did": "<redacted>",
    }
    assert shared["url"] == "https://example.com/plugin.zip"
    assert shared["properties"] == original["properties"]
    assert "secret-" not in json.dumps(shared)
    assert original["access_token"] == "secret-a"


def test_h15_export_includes_profile_and_bounded_live_reads(probe, tmp_path):
    class FakeAPI:
        batches: ClassVar[list] = []

        async def get_device_info_full(self, did):
            return {"did": did, "access_token": "secret"}

        async def get_dev_otc_info(self, did):
            return {}

        async def get_device_data_probe(self, did):
            return {}

        async def get_app_plugin_info(self, model):
            return {}

        async def get_properties(self, did, props):
            self.batches.append(props)
            return []

    class FakeHass:
        config = types.SimpleNamespace(path=lambda folder: str(tmp_path / folder))

        async def async_add_executor_job(self, func, *args):
            return func(*args)

    class FakeCoordinator:
        model = "dreame.hold.w2449e"
        device_info_raw: ClassVar[dict] = {"model": model}
        device_id = "private-device-id"
        api = FakeAPI()
        hass = FakeHass()
        props: ClassVar[dict] = {(3, 1): 100, (16, 7): 4}
        h15_last_scan = datetime.now(UTC)
        h15_last_changes: ClassVar[dict] = {"16.7": {"old": 1, "new": 4}}

        async def async_refresh_h15_mapping(self):
            return self.h15_last_changes

        async def _get_status_props_chunked(self, keys):
            return {"3.1": 100}

    coordinator = FakeCoordinator()
    result = asyncio.run(probe.async_export_h15_app_probe(coordinator))
    shared = json.loads(Path(result["share_metadata"]).read_text())
    assert shared["integration_version"] == json.loads(Path(probe.__file__).with_name("manifest.json").read_text())["version"]
    assert shared["exported_at"]
    assert shared["mapping_refresh"] == {"ok": True}
    assert shared["mapping_changes"]["16.7"] == {"old": 1, "new": 4}
    assert shared["mapping_profile"]["16.7"]["observed"] is True
    assert shared["mapping_profile"]["23.1"]["observed"] is False
    assert shared["mapping_profile"]["23.1"]["value_map"]["0"] == "Balanced"
    assert all(len(batch) <= 50 for batch in coordinator.api.batches)
    assert sum(map(len, coordinator.api.batches)) == len(H15_TARGETED_KEYS)
    assert "secret" not in json.dumps(shared)
    assert "private-device-id" not in json.dumps(shared)
