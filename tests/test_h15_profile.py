"""Tests for the H15 Pro Heat model profile."""

from custom_components.dreame_wet_dry_vacuum.const import (
    H15_CLEANING_MODE_MAP,
    H15_HOT_WATER_MAP,
    H15_MOISTURE_SENSITIVITY_MAP,
    H15_PRO_HEAT_MODEL,
    H15_PROPERTY_META,
    H15_SUCTION_MAP,
    H15_TARGETED_KEYS,
    H15_TRACTION_MAP,
    H15_WATER_LEVEL_MAP,
    H15_WORK_MODE_MAP,
    is_h15_pro_heat,
)


def test_h15_model_detection() -> None:
    assert is_h15_pro_heat(H15_PRO_HEAT_MODEL)
    assert is_h15_pro_heat(H15_PRO_HEAT_MODEL.upper())
    assert not is_h15_pro_heat("dreame.hold.w2306e")
    assert not is_h15_pro_heat(None)


def test_h15_core_app_enum_mappings() -> None:
    assert H15_WORK_MODE_MAP[4] == "Charging"
    assert H15_WORK_MODE_MAP[7] == "Sleeping"
    assert H15_WORK_MODE_MAP[15] == "Charging complete"

    assert H15_SUCTION_MAP == {
        1: "Gentle",
        2: "Standard",
        3: "Strong",
    }
    assert H15_WATER_LEVEL_MAP[2] == "Standard"
    assert H15_WATER_LEVEL_MAP[3] == "High"
    assert H15_CLEANING_MODE_MAP == {
        1: "Quiet Mode",
        3: "Turbo Mode",
        4: "Personalized Mode",
    }
    assert H15_HOT_WATER_MAP == {
        0: "Off",
        1: "Mild",
        2: "Standard",
        3: "Thermal",
    }


def test_h15_device_setting_mappings() -> None:
    assert H15_TRACTION_MAP == {
        0: "Balanced",
        1: "Gentle",
        2: "Turbo",
    }
    assert H15_MOISTURE_SENSITIVITY_MAP == {
        2: "Low Sensitivity",
        3: "Medium Sensitivity",
        4: "High Sensitivity",
    }

    assert H15_PROPERTY_META[(16, 1)]["name"] == "Suction setting"
    assert H15_PROPERTY_META[(16, 2)]["name"] == "Water level"
    assert H15_PROPERTY_META[(16, 7)]["name"] == "Cleaning mode"
    assert H15_PROPERTY_META[(16, 8)]["name"] == "Hot water mode"
    assert H15_PROPERTY_META[(23, 1)]["name"] == "GlideWheel traction"
    assert H15_PROPERTY_META[(24, 1)]["decoder"] == "mechanical_arm_2449"


def test_h15_smart_drying_and_schedule_keys_are_targeted() -> None:
    targeted = set(H15_TARGETED_KEYS)

    for key in (
        (1, 75),
        (1, 76),
        (1, 77),
        (1, 81),
        (1, 82),
        (1, 83),
        (23, 1),
        (24, 1),
        (26, 1),
        (26, 2),
        (26, 3),
        (26, 4),
        (26, 5),
        (100, 6),
    ):
        assert key in targeted

    assert H15_PROPERTY_META[(26, 1)]["value_map"] == {0: "On", 1: "Off"}
    assert H15_PROPERTY_META[(26, 2)]["value_map"] == {0: "On", 1: "Off"}
    assert H15_PROPERTY_META[(26, 3)]["value_map"] == H15_MOISTURE_SENSITIVITY_MAP


def test_h15_unknown_model_specific_values_stay_unmapped() -> None:
    assert H15_PROPERTY_META[(4, 5)]["confidence"] == "unmapped"
    assert H15_PROPERTY_META[(4, 7)]["confidence"] == "unmapped"
    assert H15_PROPERTY_META[(4, 38)]["confidence"] == "unmapped"
    assert H15_PROPERTY_META[(26, 4)]["confidence"] == "unmapped"
    assert H15_PROPERTY_META[(26, 5)]["confidence"] == "unmapped"
