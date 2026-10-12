"""Every translation_key used by the entity platforms must exist in the
translation files, otherwise the entity shows up unnamed in HA."""
import json
from pathlib import Path

import pytest

from custom_components.dreame_wet_dry_vacuum.const import (
    ALERT_BINARY_SENSORS,
    CONSUMABLE_SENSORS,
    KNOWN_BINARY_PROPS,
    KNOWN_BUTTON_PROPS,
    KNOWN_MQTT_PROPS,
    KNOWN_NUMBER_PROPS,
    KNOWN_SELECT_PROPS,
    KNOWN_SWITCH_PROPS,
)

COMPONENT = Path(__file__).parent.parent / "custom_components" / "dreame_wet_dry_vacuum"

# {platform: set of translation_keys the code will request}
EXPECTED: dict[str, set[str]] = {
    "sensor": {m["key"] for m in KNOWN_MQTT_PROPS.values()}
    | {f"consumable_{m['key']}" for m in CONSUMABLE_SENSORS},
    "binary_sensor": {"online", "charging"}
    | {m["key"] for m in KNOWN_BINARY_PROPS.values()}
    | {m["key"] for m in ALERT_BINARY_SENSORS},
    "switch": {m["key"] for m in KNOWN_SWITCH_PROPS.values()},
    "number": {m["key"] for m in KNOWN_NUMBER_PROPS.values()},
    "select": {m["key"] for m in KNOWN_SELECT_PROPS.values()},
    "button": {m["key"] for m in KNOWN_BUTTON_PROPS.values()},
}

TRANSLATION_FILES = [
    COMPONENT / "strings.json",
    COMPONENT / "translations" / "en.json",
    COMPONENT / "translations" / "fr.json",
    COMPONENT / "translations" / "hi.json",
    COMPONENT / "translations" / "ko.json",
    COMPONENT / "translations" / "ru.json",
    COMPONENT / "translations" / "ta.json",
    COMPONENT / "translations" / "zh-Hans.json",
]


def _leaf_strings(value: dict, path: tuple[str, ...] = ()) -> dict[tuple[str, ...], str]:
    """Collect translated strings so flow text and placeholders are checked too."""
    result = {}
    for key, item in value.items():
        nested_path = (*path, key)
        if isinstance(item, dict):
            result.update(_leaf_strings(item, nested_path))
        else:
            result[nested_path] = item
    return result


@pytest.mark.parametrize("path", TRANSLATION_FILES, ids=lambda p: p.name)
def test_flow_keys_and_placeholders_match_english(path: Path):
    import string

    english = _leaf_strings(
        json.loads((COMPONENT / "translations" / "en.json").read_text(encoding="utf-8"))
    )
    translated = _leaf_strings(json.loads(path.read_text(encoding="utf-8")))
    assert translated.keys() == english.keys()
    for key, source in english.items():
        assert isinstance(translated[key], str) and translated[key].strip(), key
        placeholders = lambda value: {name for _, name, _, _ in string.Formatter().parse(value) if name}
        assert placeholders(translated[key]) == placeholders(source), key


@pytest.mark.parametrize("path", TRANSLATION_FILES, ids=lambda p: p.name)
def test_all_translation_keys_have_names(path: Path):
    entity = json.loads(path.read_text(encoding="utf-8"))["entity"]
    for platform, keys in EXPECTED.items():
        available = set(entity.get(platform, {}))
        missing = keys - available
        assert not missing, f"{path.name}: missing {platform} names for {sorted(missing)}"
        for key in keys:
            assert entity[platform][key].get("name"), f"{path.name}: empty name for {platform}.{key}"


@pytest.mark.parametrize("path", TRANSLATION_FILES, ids=lambda p: p.name)
def test_no_orphan_translation_keys(path: Path):
    entity = json.loads(path.read_text(encoding="utf-8"))["entity"]
    for platform, translated in entity.items():
        orphans = set(translated) - EXPECTED.get(platform, set())
        assert not orphans, f"{path.name}: translations for unknown {platform} keys {sorted(orphans)}"
