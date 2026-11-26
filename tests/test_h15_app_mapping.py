"""H15 Pro Heat (dreame.hold.w2449e): integration output must equal the Dreame app.

tests/fixtures/h15_app_reference.json was produced by executing the official
Dreamehome plugin (dreame.vacuum.common versionCode 1240 with the w2449e
resource config) against a simulated device and recording what the app shows
for each raw value. These tests feed the same raw values to the integration.
"""
import json
from pathlib import Path

import pytest

from custom_components.dreame_wet_dry_vacuum.const import (
    H15_DRY_COMMAND_VALUES,
    H15_ERROR_FIELDS,
    H15_PROPERTY_META,
    H15_SELECT_SETTINGS,
    H15_SELECT_VALUE_ALIASES,
    H15_WARN_FIELDS,
    decode_h15_alerts,
)

REF = json.loads((Path(__file__).parent / "fixtures" / "h15_app_reference.json").read_text(encoding="utf-8"))


def _triggered(raw: int, fields) -> list[str]:
    return sorted(f"{shift}:{(raw >> shift) & mask}" for shift, mask, labels in fields if ((raw >> shift) & mask) in labels)


def _label(key, raw):
    return H15_PROPERTY_META[key]["value_map"].get(int(raw), f"Unknown ({raw})")


@pytest.mark.parametrize("raw,warn,error", REF["alerts"]["vectors"])
def test_alert_fields_match_app(raw, warn, error):
    assert _triggered(raw, H15_WARN_FIELDS) == sorted(warn)
    assert _triggered(raw, H15_ERROR_FIELDS) == sorted(error)
    assert len(decode_h15_alerts(raw, H15_WARN_FIELDS)) == len(dict.fromkeys(warn))


@pytest.mark.parametrize("raw,text", sorted(REF["work_state_text"].items(), key=lambda kv: int(kv[0])))
def test_work_state_text_matches_app(raw, text):
    assert _label((1, 28), raw) == text


@pytest.mark.parametrize("key", [(1, 10), (1, 82), (1, 83)])
def test_dry_mode_values_match_app(key):
    for raw, title in REF["dry_title"].items():
        assert _label(key, raw) == title
        option = H15_SELECT_SETTINGS[key].get(H15_SELECT_VALUE_ALIASES.get(key, {}).get(int(raw), int(raw)))
        assert option and title.startswith(option)


def test_dry_command_values_match_app():
    for mode, value in REF["dry_set_value"].items():
        if int(mode):
            assert H15_DRY_COMMAND_VALUES[int(mode)] == value


@pytest.mark.parametrize("key", [(1, 8), (1, 75), (1, 81)])
def test_self_clean_mode_text_matches_app(key):
    for raw, text in REF["self_clean_text"].items():
        assert _label(key, raw) == text


@pytest.mark.parametrize("key,ref", [((16, 1), "clean_power"), ((16, 2), "clean_water"), ((16, 8), "hot_water")])
def test_level_labels_match_app(key, ref):
    for raw, text in REF[ref].items():
        assert _label(key, raw).lower() == text.lower()


def test_cleaning_mode_labels_match_app():
    for raw, text in REF["custom_mode"].items():
        assert _label((16, 7), raw) == text  # exact app wording (Quiet Mode, ...)


@pytest.mark.parametrize("full,left,app_percent,app_hours", REF["consumables"]["samples"])
def test_consumable_percent_matches_app(full, left, app_percent, app_hours):
    # Same expression as sensor.DreameWetDryConsumableSensor for the H15.
    assert max(0, min(100, int(left / full * 100))) == app_percent
    assert int(left / full * full / 60) == app_hours
