"""Constants for Dreame wet & dry vacuum integration."""

from __future__ import annotations

from typing import Any

DOMAIN = "dreame_wet_dry_vacuum"
MANUFACTURER = "Dreame"
MODEL = "H14 Pro"

# API
EU_BASE_URL = "https://eu.iot.dreame.tech:13267"
CN_BASE_URL = "https://cn.iot.dreame.tech:13267"

# DREAME_BASIC_AUTH = base64("dreame_appv1:AP^dv@z@SQYVxN88") — app client credentials
DREAME_BASIC_AUTH = "Basic ZHJlYW1lX2FwcHYxOkFQXmR2QHpAU1FZVnhOODg="
DREAME_TENANT_ID = "000000"
DREAME_PASSWORD_SALT = "RAylYC%fmSKp7%Tq"
DREAME_RLC_KEY = b"EETjszu*XI5znHsI"
DREAME_IOT_PREFIX = "10000"

ENDPOINTS = {
    "token": "/dreame-auth/oauth/token",
    "device_list": "/dreame-user-iot/iotuserbind/device/listV2",
    "send_command": "/dreame-iot-com-{prefix}/device/sendCommand",
    # Reads the cloud-cached property values by key ("siid.piid"). Works on this
    # model where the realtime get_properties RPC returns null. Verified live.
    "status_props": "/dreame-user-iot/iotstatus/props",
}

# Device status codes for the H14 Pro (model dreame.hold.w2306e).
# Source: official Dreame keyDefine file, property 2.1.
# This mirrors the `latestStatus` field returned by device/listV2.
DEVICE_STATUS = {
    1: "Washing",
    2: "Offline",
    3: "Standby",
    4: "Charging",
    5: "Self-cleaning",
    6: "Self-drying",
    7: "Sleeping",
    8: "Vacuuming",
    9: "Adding clean water",
    10: "Washing paused",
    11: "Self-cleaning paused",
    12: "Self-drying paused",
    13: "OTA upgrade",
    14: "Voice package upgrade",
    15: "Charging complete",
    # Codes 16-22 are all labelled as washing in the original dictionary,
    # while observed values distinguish specific operating modes.
    16: "Washing — Auto mode",
    17: "Washing — Ultra mode",
    18: "Washing — Suction mode",
    19: "Washing",
    20: "Washing",
    21: "Washing",
    22: "Washing",
    23: "Self-drying",
    24: "Self-drying",
    25: "Self-drying",
    26: "Self-cleaning",
    27: "Self-cleaning",
    28: "Self-cleaning",
    29: "Convenient mode paused",
}

# Status enum names decoded from the official app plugin (index.android.bundle):
# StandBy:3 Charging:4 SelfCleaning:5 SelfDrying:6 Sleeping:7 Convenient:8
# AddWater:9 WashingPause:10 CleaningPause:11 DryingPause:12 OTAUpgrading:13
# ... SelfDrying_Quite:25 SelfCleaning_Fast:26 SelfCleaning_Deep:27
# SelfCleaning_Smart:28 ConvenientPause:29

# Coarse activity grouping (useful for automations / binary states)
STATUS_GROUP = {
    1: "mopping", 16: "mopping", 17: "mopping", 18: "mopping",
    19: "mopping", 20: "mopping", 21: "mopping", 22: "mopping",
    8: "vacuuming",
    3: "idle", 7: "idle",
    4: "charging", 15: "charging",
    5: "self_cleaning", 11: "self_cleaning", 26: "self_cleaning",
    27: "self_cleaning", 28: "self_cleaning",
    6: "drying", 12: "drying", 23: "drying", 24: "drying", 25: "drying",
    9: "filling_water",
    10: "paused", 29: "paused",
    13: "updating", 14: "updating",
    2: "offline",
}

# Property siid/piid known for this model
PROP_STATUS = (2, 1)  # device status (matches latestStatus)

# Known MQTT properties for the H14 Pro, discovered by live capture.
# (siid, piid): metadata for entity creation and value decoding.
# Confidence: HIGH for status/battery/progress; the rest are exposed raw.
# Meta schema per property:
#   key, name, icon, unit, device_class ("battery"|"duration"|"timestamp")
#   enum=True            -> map int via DEVICE_STATUS
#   list_scalar=True     -> value arrives as a list; use first element
#   timestamp=True       -> value is a Unix epoch (seconds)
#   diagnostic=True      -> entity category Diagnostic
# Names are kept in English in source; UI localization is handled by translations.
# Dreame's SIID/PIID mapping is authoritative; see debug/dumps/DECODED_SPEC.md.
# "name" is a source-code fallback; UI names use translation_key = "key"
# (the "entity" section of translations/en.json and other locale files).
KNOWN_MQTT_PROPS: dict[tuple[int, int], dict] = {
    # --- Service principal (SIID 1) ---
    (2, 1): {"key": "status", "name": "Status", "enum": True, "icon": "mdi:robot-vacuum-variant"},
    (3, 1): {"key": "battery", "name": "Battery", "unit": "%", "device_class": "battery"},
    (1, 28): {"key": "work_mode", "name": "Work mode", "icon": "mdi:state-machine", "diagnostic": True},
    (1, 29): {"key": "level_washing", "name": "Washing level", "icon": "mdi:water-percent", "state_class": "measurement"},
    (1, 30): {"key": "level_drying", "name": "Drying level", "icon": "mdi:hair-dryer", "state_class": "measurement"},
    (1, 53): {"key": "total_time", "name": "Total runtime", "unit": "s", "device_class": "duration", "icon": "mdi:timer-cog", "diagnostic": True},
    (1, 54): {"key": "total_clean_count", "name": "Total clean count", "icon": "mdi:counter", "state_class": "total_increasing"},
    (1, 55): {"key": "start_time", "name": "Start time", "device_class": "timestamp", "timestamp": True, "icon": "mdi:clock-start", "diagnostic": True},
    (1, 56): {"key": "total_time_self_dry", "name": "Total self-dry time", "unit": "s", "device_class": "duration", "icon": "mdi:timer-sand", "diagnostic": True},
    (1, 57): {"key": "total_time_self_clean", "name": "Total self-clean time", "unit": "s", "device_class": "duration", "icon": "mdi:timer-sand", "diagnostic": True},
    # Cleaning-history fields observed through the cloud API.
    (1, 47): {"key": "last_clean_time", "name": "Last clean", "device_class": "timestamp", "timestamp": True, "icon": "mdi:clock-check"},
    (1, 64): {"key": "last_clean_duration", "name": "Last clean duration", "unit": "s", "device_class": "duration", "icon": "mdi:timer"},
    (1, 49): {"key": "clean_count_2", "name": "Clean counter (alt.)", "icon": "mdi:counter", "state_class": "total_increasing", "diagnostic": True},
    (1, 68): {"key": "last_vacuum_duration", "name": "Last vacuum duration", "unit": "s", "device_class": "duration", "diagnostic": True},
    (1, 69): {"key": "last_mop_duration", "name": "Last mop duration", "unit": "s", "device_class": "duration", "diagnostic": True},
    # Consumable raw values are remaining minutes. Dedicated consumable sensors
    # expose hours/percentage; optional "max" properties are handled separately.
    (6, 7): {"key": "front_brush_left", "name": "Front roller brush — minutes left", "unit": "min", "icon": "mdi:rotate-right", "diagnostic": True},
    (7, 7): {"key": "back_brush_left", "name": "Back roller brush — minutes left", "unit": "min", "icon": "mdi:rotate-right", "diagnostic": True},
    (19, 3): {"key": "filter_left", "name": "Filter — minutes left", "unit": "min", "icon": "mdi:air-filter", "diagnostic": True},
    # Rare/optional consumables retained for devices that publish them.
    (20, 3): {"key": "dustbag_left", "name": "Dust bag — minutes left", "unit": "min", "icon": "mdi:sack", "diagnostic": True},
    (21, 7): {"key": "suck_brush_left", "name": "Suction brush — minutes left", "unit": "min", "icon": "mdi:rotate-right", "diagnostic": True},
    (22, 7): {"key": "suck_filter_left", "name": "Suction filter — minutes left", "unit": "min", "icon": "mdi:air-filter", "diagnostic": True},
    # Settings also exposed as writable controls below.
    (16, 3): {"key": "elec_water", "name": "Electrolysis / detergent", "icon": "mdi:flash", "diagnostic": True},
    (1, 67): {"key": "detergent_fav", "name": "Detergent preference", "icon": "mdi:bottle-tonic-plus", "diagnostic": True},
    # Warning/error properties (SIID 4).
    (4, 1): {"key": "warn", "name": "Warnings", "icon": "mdi:alert", "bitmask": True, "decode": "warn", "diagnostic": True},
    (4, 2): {"key": "error", "name": "Error codes", "icon": "mdi:alert-circle", "bitmask": True, "decode": "error", "diagnostic": True},
    (4, 3): {"key": "warn_push", "name": "Push notification (raw)", "icon": "mdi:bell-alert", "bitmask": True, "diagnostic": True},
    # Water/suction properties observed in live device data.
    (4, 5): {"key": "water_level_set", "name": "Water level (setting)", "unit": "%", "list_scalar": True, "icon": "mdi:water-percent"},
    (4, 6): {"key": "water_level", "name": "Water level", "unit": "%", "icon": "mdi:water"},
    (4, 7): {"key": "suction_mode", "name": "Suction mode", "list_scalar": True, "icon": "mdi:fan"},
}

# Consumable sensors.
# The "left" value is remaining minutes. Hours are derived as left / 60.
# If a device exposes the "max" property it is used for percentage; otherwise
# full_life_min is used as a documented fallback.
CONSUMABLE_SENSORS: list[dict] = [
    {"key": "front_brush", "name": "Front roller brush", "left": "6.7", "max": "6.6",
     "full_life_min": 3600, "icon": "mdi:rotate-right"},
    {"key": "back_brush", "name": "Back roller brush", "left": "7.7", "max": "7.6",
     "full_life_min": 3600, "icon": "mdi:rotate-right"},
    {"key": "filter", "name": "Filter", "left": "19.3", "max": "19.2",
     "full_life_min": 3600, "icon": "mdi:air-filter"},
]

# Query the optional maximum-life keys as well. If the device exposes them,
# percentage calculations automatically use the real device value.
CONSUMABLE_MAX_KEYS: list[str] = [c["max"] for c in CONSUMABLE_SENSORS]

# ---------------------------------------------------------------------------
# Warning / error bitfield decoding
# ---------------------------------------------------------------------------
WARN_DECODE: list[tuple[int, int, dict[int, str]]] = [
    (0, 1, {1: "Clean water tank empty"}),
    (1, 1, {1: "Detergent empty"}),
    (1, 3, {1: "Brush/tube dirty — run self-cleaning",
            2: "Brush/tube dirty — run self-cleaning",
            3: "Brush/tube dirty — run self-cleaning"}),
    (2, 1, {}), (1, 1, {}), (1, 1, {}), (1, 1, {}),
    (1, 1, {1: "Dirty water tank needs cleaning after self-cleaning"}),  # bit 8
    (1, 1, {}), (1, 1, {}), (1, 1, {}), (1, 1, {}), (1, 1, {}), (1, 1, {}), (1, 1, {}),
    (1, 1, {1: "Station water supply low"}),   # bit 16
    (1, 1, {1: "Station filter needs replacement"}),  # bit 17
]
ERROR_DECODE: list[tuple[int, int, dict[int, str]]] = [
    (0, 15, {}),
    (4, 63, {1: "Roller brush not installed",
             3: "Roller brush blocked — clean it"}),  # bits 4-9
    (6, 1, {}),
    (1, 1, {1: "Dirty water tank not installed"}),   # bit 11
    (1, 1, {1: "Dirty water tank full — empty it"}),  # bit 12
    (1, 7, {}), (3, 15, {}), (4, 1, {}), (1, 1, {}), (1, 1, {}), (1, 1, {}),
    (1, 1, {1: "Vacuum tube blocked"}),   # bit 24
    (1, 1, {}),
    (1, 1, {1: "Station tube blocked"}),   # bit 26
    (1, 1, {}),
    (1, 1, {1: "Dirty water tank blocked"}),  # bit 28
]


def decode_field_alerts(value: int, table: list[tuple[int, int, dict[int, str]]]) -> list[str]:
    """Decode a warning/error bitfield into active English labels."""
    alerts: list[str] = []
    v = value
    for pos, cal, labels in table:
        if pos:
            v >>= pos
        field = v & cal
        if field in labels:
            alerts.append(labels[field])
    return alerts


# Binary alert sensors derived from warning/error bitfields.
ALERT_BINARY_SENSORS: list[dict] = [
    {"key": "dirty_tank_full", "name": "Dirty water tank full", "data_key": "4.2",
     "bit_mask": 4096, "device_class": "problem", "icon": "mdi:cup-water"},
    {"key": "dirty_tank_not_clean", "name": "Dirty water tank needs cleaning", "data_key": "4.1",
     "bit_mask": 256, "device_class": "problem", "icon": "mdi:cup-water"},
    {"key": "dirty_tank_missing", "name": "Dirty water tank missing", "data_key": "4.2",
     "bit_mask": 2048, "device_class": "problem", "icon": "mdi:cup-off-outline"},
    {"key": "clean_water_empty", "name": "Clean water tank empty", "data_key": "4.1",
     "bit_mask": 1, "device_class": "problem", "icon": "mdi:water-alert"},
    {"key": "detergent_empty", "name": "Detergent empty", "data_key": "4.1",
     "bit_mask": 2, "device_class": "problem", "icon": "mdi:bottle-tonic-outline"},
    {"key": "needs_self_clean", "name": "Self-cleaning recommended (dirty brush/tube)", "data_key": "4.1",
     "bit_mask": 12, "device_class": "problem", "icon": "mdi:broom"},
]

# Binary properties: (siid, piid): meta.
#   bit_mask=N  -> on when (value & N) != 0 (instead of value != 0)
KNOWN_BINARY_PROPS: dict[tuple[int, int], dict] = {
    # 17.8 = automatic detergent state (1=enabled, 0=disabled).
    (17, 8): {"key": "auto_detergent_17", "name": "Auto detergent (sensor)", "icon": "mdi:bottle-tonic-plus", "diagnostic": True},
}

# ---------------------------------------------------------------------------
# Writable controls (set_properties)
# ---------------------------------------------------------------------------

# Boolean switches. optimistic=True means the device does not report the
# current value, so Home Assistant reflects the last command sent.
KNOWN_SWITCH_PROPS: dict[tuple[int, int], dict] = {
    (1, 3): {"key": "light_control", "name": "Light", "icon": "mdi:lightbulb", "optimistic": True},
    (1, 4): {"key": "auto_mix_detergent", "name": "Auto detergent mixing", "icon": "mdi:bottle-tonic-plus", "optimistic": True},
    (1, 7): {"key": "auto_backwash", "name": "Auto rinse", "icon": "mdi:water-sync"},
    (1, 9): {"key": "auto_dry_switch", "name": "Auto drying", "icon": "mdi:hair-dryer", "optimistic": True},
    (1, 11): {"key": "time_dry_after_clean", "name": "Timed dry after cleaning", "icon": "mdi:timer-cog", "optimistic": True},
    (16, 6): {"key": "custom_switch", "name": "Custom mode", "icon": "mdi:tune-variant"},
}

# Number controls: {min, max, step, unit} (+ optimistic when unreadable)
KNOWN_NUMBER_PROPS: dict[tuple[int, int], dict] = {
    (1, 14): {"key": "volume", "name": "Voice volume", "icon": "mdi:volume-high", "min": 0, "max": 100, "step": 1, "unit": "%", "optimistic": True},
    (1, 12): {"key": "time_dry_value", "name": "Timed-dry duration", "icon": "mdi:timer-sand", "min": 0, "max": 21600, "step": 600, "unit": "s", "optimistic": True},
        # Custom-mode settings. These are configuration controls rather than
    # primary operational controls.
    (16, 1): {"key": "clean_power", "name": "Suction power (custom)", "icon": "mdi:fan", "min": 0, "max": 3, "step": 1, "config": True},
    (16, 2): {"key": "clean_water", "name": "Water flow (custom)", "icon": "mdi:water", "min": 0, "max": 3, "step": 1, "config": True},
    (16, 4): {"key": "brush_speed", "name": "Brush speed (custom)", "icon": "mdi:rotate-right", "min": 0, "max": 3, "step": 1, "optimistic": True, "config": True},
}

# Select controls: {options: {int_value: label}}
KNOWN_SELECT_PROPS: dict[tuple[int, int], dict] = {
    (23, 1): {
        "key": "power_wheel",
        "name": "Traction force",
        "icon": "mdi:car-traction-control",
        "options": {0: "Light", 1: "Balanced", 2: "Strong"},
        "optimistic": True,
    },
}

# Buttons send a fixed value as a one-shot command
KNOWN_BUTTON_PROPS: dict[tuple[int, int], dict] = {
    (1, 1): {"key": "start_self_clean", "name": "Start self-cleaning", "icon": "mdi:water-sync", "press_value": 1},
    (1, 2): {"key": "start_self_dry", "name": "Start self-drying", "icon": "mdi:hair-dryer", "press_value": 1},
}

# Properties driven only by real-time MQTT push. Slow cloud polling must not
# overwrite these rapidly changing values.
MQTT_ONLY_KEYS: set[tuple[int, int]] = {(1, 29), (1, 30)}

CONF_REGION = "region"
CONF_COUNTRY = "country"
CONF_DEVICE_ID = "device_id"

REGIONS = {
    "auto": "Automatic",
    "eu": "Europe",
    "de": "Germany / Europe",
    "cn": "China",
    "us": "United States",
    "ru": "Russia",
    "tw": "Taiwan",
    "sg": "Singapore / Southeast Asia",
    "in": "India",
    "i2": "International",
    "kr": "South Korea",
}


# Model-specific definitions; legacy H14 tables above are unchanged.
H15_PRO_HEAT_MODEL = "dreame.hold.w2449e"

# Values decoded from the Dreamehome common plugin/resource package delivered
# for dreame.hold.w2449e, plus UI states verified against the user's H15.
H15_WORK_MODE_MAP = {
    1: "Power on",
    2: "Power off",
    3: "Standby",
    4: "Charging",
    5: "Self-cleaning",
    6: "Self-drying",
    7: "Sleeping",
    8: "Convenient",
    9: "Adding clean water",
    10: "Washing paused",
    11: "Cleaning paused",
    12: "Drying paused",
    13: "OTA upgrading",
    14: "Voice upgrading",
    15: "Charging complete",
    16: "Auto cleaning",
    17: "Degerming",
    18: "Water suction",
    19: "Quiet cleaning",
    20: "Quick cleaning",
    21: "Strong cleaning",
    22: "Personalized cleaning",
    23: "Fast drying",
    24: "Faster drying",
    25: "Quiet drying",
    26: "Fast self-cleaning",
    27: "Deep self-cleaning",
    28: "Smart self-cleaning",
    29: "Convenient paused",
    30: "Fast self-cleaning paused",
    31: "Deep self-cleaning paused",
    32: "Fast self-cleaning drying",
    33: "Deep self-cleaning drying",
    34: "Smart self-cleaning drying",
    35: "Retry drying",
    36: "Retry self-cleaning",
    37: "Smart self-cleaning paused",
    40: "Power mode",
    41: "Hot water cleaning",
    42: "Hot water self-cleaning",
    43: "Hot water self-cleaning paused",
}

H15_SUCTION_MAP = {
    1: "Gentle",
    2: "Standard",
    3: "Strong",
}

H15_WATER_LEVEL_MAP = {
    1: "Low / legacy",
    2: "Standard",
    3: "High",
}

H15_CLEANING_MODE_MAP = {
    1: "Quiet Mode",
    3: "Turbo Mode",
    4: "Personalized Mode",
}

H15_HOT_WATER_MAP = {
    0: "Off",
    1: "Mild",
    2: "Standard",
    3: "Thermal",
}

H15_TRACTION_MAP = {
    0: "Balanced",
    1: "Gentle",
    2: "Turbo",
}

H15_MOISTURE_SENSITIVITY_MAP = {
    2: "Low Sensitivity",
    3: "Medium Sensitivity",
    4: "High Sensitivity",
}

H15_SELF_CLEAN_MODE_MAP = {
    2: "Standard Immersive Self-Cleaning",
    3: "Deep-Clean Immersive Self-Cleaning",
    4: "Smart Self-Cleaning",
    5: "Hot-Water Self-Cleaning",
}

H15_DRY_MODE_MAP = {
    1: "High-Speed",
    3: "Super-Speed",
}

H15_DETERGENT_MODE_MAP = {
    2: "Smart Mode",
    3: "Powerful stain removal",
}

# Known app-facing properties worth probing explicitly even when the broad
# iotstatus cache omits them. This is read-only.
H15_TARGETED_KEYS: tuple[tuple[int, int], ...] = (
    # SIID 1: all properties defined by Dreame's Vacuum model plus the
    # additional w2449e values already observed from cloud/MQTT.
    (1, 1), (1, 2), (1, 3), (1, 4), (1, 6), (1, 7), (1, 8), (1, 9),
    (1, 10), (1, 11), (1, 12), (1, 13), (1, 14), (1, 17),
    (1, 28), (1, 29), (1, 30),
    (1, 33), (1, 34), (1, 35), (1, 36), (1, 47),
    (1, 49), (1, 50), (1, 51), (1, 52),
    (1, 53), (1, 54), (1, 55), (1, 56), (1, 57),
    (1, 64), (1, 65), (1, 66), (1, 67), (1, 68), (1, 69),
    (1, 70), (1, 71), (1, 72), (1, 73),
    (1, 75), (1, 76), (1, 77), (1, 81), (1, 82), (1, 83),

    # Standard/status and warning services.
    (2, 1), (3, 1),
    (4, 1), (4, 2), (4, 3), (4, 5), (4, 6), (4, 7), (4, 38),

    # Consumables / model services defined by the downloaded Dreame plugin.
    (6, 6), (6, 7), (7, 6), (7, 7), (10, 1), (13, 2),
    (16, 1), (16, 2), (16, 3), (16, 4), (16, 6), (16, 7), (16, 8),
    (19, 2), (19, 3),
    (20, 2), (20, 3), (21, 6), (21, 7), (22, 6), (22, 7),
    (23, 1), (24, 1), (25, 1),
    (26, 1), (26, 2), (26, 3), (26, 4), (26, 5),

    # The common plugin also defines a DeviceControl service. The H15 resource
    # disables normal remote control, so these are diagnostic read probes only.
    (100, 1), (100, 2), (100, 3), (100, 4), (100, 5), (100, 6),
)

H15_PROPERTY_META: dict[tuple[int, int], dict[str, Any]] = {
    (1, 1): {
        "name": "Self-cleaning command raw",
        "confidence": "plugin",
        "icon": "mdi:waves-arrow-up",
        "diagnostic": True,
        "note": "Dreame plugin property PropSelfCleaning. Exposed read-only on H15; no write is performed.",
    },
    (1, 2): {
        "name": "Self-drying command raw",
        "confidence": "plugin",
        "icon": "mdi:hair-dryer",
        "diagnostic": True,
        "note": "Dreame plugin property PropSelfDrying. Exposed read-only on H15; no write is performed.",
    },
    (1, 3): {
        "name": "Roller brush head light raw",
        "confidence": "plugin",
        "icon": "mdi:lightbulb-outline",
        "diagnostic": True,
        "note": "Dreame PropLightControl. w2449e resource has brushLight=false, so this is expected to be unsupported/hidden.",
    },
    (1, 4): {
        "name": "Auto detergent mixing raw",
        "confidence": "plugin",
        "icon": "mdi:bottle-tonic-plus-outline",
        "diagnostic": True,
        "note": "Dreame plugin property PropAutoMixDetergent. Read-only until H15 write semantics are verified.",
    },
    (1, 6): {
        "name": "High-level mode raw",
        "confidence": "plugin",
        "icon": "mdi:tune-variant",
        "diagnostic": True,
        "note": "Dreame plugin property PropHighLevelMode.",
    },
    (1, 7): {
        "name": "Return to automatic wash & dry",
        "confidence": "confirmed",
        "icon": "mdi:home-import-outline",
        "diagnostic": False,
        "value_map": {0: "On", 1: "Off"},
        "note": "Dreame plugin property PropAutoBackwash. H15 UI verified raw 1 while Return to Automatic Wash & Dry is off.",
    },
    (1, 8): {
        "name": "Self-cleaning mode",
        "confidence": "plugin",
        "icon": "mdi:waves-arrow-up",
        "diagnostic": False,
        "value_map": H15_SELF_CLEAN_MODE_MAP,
        "note": "Dreame PropSelfCleanWaterMode. Plugin maps 2=Standard Immersive, 3=Deep-Clean Immersive, 4=Smart; 5 is the hot-water self-clean mode.",
    },
    (1, 9): {
        "name": "Auto roller brush drying",
        "confidence": "plugin",
        "icon": "mdi:hair-dryer",
        "diagnostic": False,
        "value_map": {0: "On", 1: "Off"},
        "note": "Dreame PropAutoDrySwitch. App code explicitly treats raw 0 as enabled and writes 0 for On / 1 for Off.",
    },
    (1, 10): {
        "name": "Drying mode",
        "confidence": "confirmed",
        "icon": "mdi:weather-sunny",
        "diagnostic": False,
        "value_map": H15_DRY_MODE_MAP,
        "note": "Dreame PropAutoDryMode. w2449e UI/code maps 1=High-Speed and 3=Super-Speed.",
    },
    (1, 11): {
        "name": "Timed drying after cleaning",
        "confidence": "plugin",
        "icon": "mdi:timer-cog-outline",
        "diagnostic": True,
        "note": "Dreame plugin property PropTimeDryAfterCleanSwitch.",
    },
    (1, 12): {
        "name": "Scheduled drying time raw",
        "confidence": "plugin",
        "icon": "mdi:clock-outline",
        "diagnostic": True,
        "note": "Dreame plugin property PropTimeDryValue.",
    },
    (1, 13): {
        "name": "Scheduled drying repeat raw",
        "confidence": "plugin",
        "icon": "mdi:calendar-sync",
        "diagnostic": True,
        "note": "Dreame plugin property PropTimeDryCircle.",
    },
    (1, 14): {
        "name": "Voice volume",
        "confidence": "plugin",
        "icon": "mdi:volume-high",
        "unit": "%",
        "diagnostic": False,
        "note": "Dreame plugin property PropVolume.",
    },
    (1, 17): {
        "name": "Voice language pack",
        "confidence": "plugin",
        "icon": "mdi:translate",
        "diagnostic": False,
        "note": "Dreame plugin property PropVoicePacketId. The app currently shows English in use.",
    },
    (1, 28): {
        "name": "Work mode",
        "confidence": "confirmed",
        "icon": "mdi:state-machine",
        "diagnostic": False,
        "value_map": H15_WORK_MODE_MAP,
        "note": "Dreame plugin property PropWorkMode. Raw 7 was verified against the app as Sleeping.",
    },
    (1, 29): {
        "name": "Washing level",
        "confidence": "plugin",
        "icon": "mdi:waves",
        "diagnostic": True,
        "note": "Dreame plugin property PropLevelWashing.",
    },
    (1, 30): {
        "name": "Drying level",
        "confidence": "plugin",
        "icon": "mdi:weather-windy",
        "diagnostic": True,
        "note": "Dreame plugin property PropLevelDrying.",
    },
    (1, 47): {
        "name": "Last-clean timestamp candidate",
        "confidence": "candidate",
        "icon": "mdi:clock-outline",
        "diagnostic": True,
        "note": "Raw value has Unix-timestamp shape; keep raw until a controlled cleaning session confirms it.",
    },
    (1, 53): {
        "name": "Total working time",
        "confidence": "plugin",
        "icon": "mdi:timer-outline",
        "diagnostic": True,
        "note": "Dreame plugin property PropTotalTime.",
    },
    (1, 54): {
        "name": "Clean count",
        "confidence": "plugin",
        "icon": "mdi:counter",
        "diagnostic": False,
        "note": "Dreame plugin property PropTotalTimes.",
    },
    (1, 55): {
        "name": "Start time raw",
        "confidence": "plugin",
        "icon": "mdi:clock-start",
        "diagnostic": True,
        "note": "Dreame plugin property PropStartTime.",
    },
    (1, 56): {
        "name": "Total self-dry time raw",
        "confidence": "plugin",
        "icon": "mdi:timer-outline",
        "diagnostic": True,
        "note": "Dreame plugin property PropTotalTimeSelfDry; unit still needs H15 confirmation.",
    },
    (1, 57): {
        "name": "Total self-clean time raw",
        "confidence": "plugin",
        "icon": "mdi:timer-outline",
        "diagnostic": True,
        "note": "Dreame plugin property PropTotalTimeSelfClean; unit still needs H15 confirmation.",
    },
    (1, 64): {
        "name": "Last clean mild-dirt time raw",
        "confidence": "candidate",
        "icon": "mdi:chart-timeline-variant",
        "diagnostic": True,
        "note": "The Dreame CleanLog code reads PIID 64-66 in order for mild/moderate/severe dirt duration. Unit still needs confirmation.",
    },
    (1, 65): {
        "name": "Last clean moderate-dirt time raw",
        "confidence": "candidate",
        "icon": "mdi:chart-timeline-variant",
        "diagnostic": True,
        "note": "The Dreame CleanLog code reads PIID 64-66 in order for mild/moderate/severe dirt duration. Unit still needs confirmation.",
    },
    (1, 66): {
        "name": "Last clean severe-dirt time raw",
        "confidence": "candidate",
        "icon": "mdi:chart-timeline-variant",
        "diagnostic": True,
        "note": "The Dreame CleanLog code reads PIID 64-66 in order for mild/moderate/severe dirt duration. Unit still needs confirmation.",
    },
    (1, 67): {
        "name": "Cleaning solution ratio mode",
        "confidence": "plugin",
        "icon": "mdi:bottle-tonic-plus-outline",
        "diagnostic": False,
        "value_map": H15_DETERGENT_MODE_MAP,
        "note": "Dreame PropDetergentFav. w2449e has allowSterilize=false, so raw 2=Smart Mode and raw 3=Powerful stain removal.",
    },
    (1, 75): {
        "name": "Scheduled wash & dry mode",
        "confidence": "plugin",
        "icon": "mdi:washing-machine",
        "diagnostic": False,
        "note": "Dreame plugin property PropAutoCleanMode.",
    },
    (1, 76): {
        "name": "Scheduled wash & dry start time raw",
        "confidence": "plugin",
        "icon": "mdi:clock-start",
        "diagnostic": True,
        "note": "Dreame plugin property PropTimeCleanValue.",
    },
    (1, 77): {
        "name": "Scheduled wash & dry repeat raw",
        "confidence": "plugin",
        "icon": "mdi:calendar-sync",
        "diagnostic": True,
        "note": "Dreame plugin property PropTimeCleanCircle.",
    },
    (1, 81): {
        "name": "Return self-cleaning wash mode",
        "confidence": "plugin",
        "icon": "mdi:waves-arrow-up",
        "diagnostic": True,
        "note": "Dreame plugin property PropBackSelfCleanWaterMode.",
    },
    (1, 82): {
        "name": "Return self-cleaning dry mode",
        "confidence": "plugin",
        "icon": "mdi:weather-sunny",
        "diagnostic": True,
        "note": "Dreame plugin property PropBackSelfCleanDryMode.",
    },
    (1, 83): {
        "name": "Scheduled self-dry mode",
        "confidence": "plugin",
        "icon": "mdi:calendar-clock",
        "diagnostic": True,
        "note": "Dreame plugin property PropTimeSelfDryMode.",
    },
    (2, 1): {
        "name": "Cloud status code raw",
        "confidence": "candidate",
        "icon": "mdi:state-machine",
        "diagnostic": True,
        "note": "Observed mirroring latestStatus and often 1.28. Kept raw until independent semantics are proven.",
    },
    (3, 1): {
        "name": "Battery",
        "confidence": "confirmed",
        "icon": "mdi:battery",
        "unit": "%",
        "device_class": "battery",
        "state_class": "measurement",
        "diagnostic": False,
        "note": "Confirmed H15 battery percentage.",
    },
    (4, 1): {
        "name": "Warnings raw",
        "confidence": "plugin",
        "icon": "mdi:alert-outline",
        "diagnostic": True,
        "bitfield": True,
        "note": "Dreame plugin property PropWarn. H15 bit meanings remain under test.",
    },
    (4, 2): {
        "name": "Errors raw",
        "confidence": "plugin",
        "icon": "mdi:alert-circle-outline",
        "diagnostic": True,
        "bitfield": True,
        "note": "Dreame plugin property PropError. H15 bit meanings remain under test.",
    },
    (4, 3): {
        "name": "Warning push raw",
        "confidence": "plugin",
        "icon": "mdi:bell-alert-outline",
        "diagnostic": True,
        "bitfield": True,
        "note": "Dreame plugin property PropWarnPush.",
    },
    (4, 5): {
        "name": "Raw 4.5",
        "confidence": "unmapped",
        "icon": "mdi:code-array",
        "diagnostic": True,
        "note": "Observed list value on H15; do not inherit H14 water semantics until verified.",
    },
    (4, 6): {
        "name": "Dirty water tank status",
        "confidence": "confirmed",
        "icon": "mdi:water-alert-outline",
        "diagnostic": True,
        "value_map": {0: "Normal", 81: "Full"},
        "note": "H15-only live comparison: raw 81 coincided with the app's Used water tank is full alert and error bit 4096; a later export after the alert cleared returned raw 0. Other raw values are unknown; this is a state, not a percentage.",
    },
    (4, 7): {
        "name": "Raw 4.7",
        "confidence": "unmapped",
        "icon": "mdi:code-array",
        "diagnostic": True,
        "note": "Observed list value on H15; do not inherit H14 suction semantics until verified.",
    },
    (4, 38): {
        "name": "Raw 4.38",
        "confidence": "unmapped",
        "icon": "mdi:code-tags",
        "diagnostic": True,
    },
    (6, 6): {
        "name": "Roller brush maximum life raw",
        "confidence": "plugin",
        "icon": "mdi:rotate-right",
        "unit": "min",
        "diagnostic": True,
        "note": "Dreame FrontBrush/PropFrontBrushMaxHeal.",
    },
    (6, 7): {
        "name": "Roller brush remaining",
        "confidence": "confirmed",
        "icon": "mdi:rotate-right",
        "unit": "min",
        "device_class": "duration",
        "state_class": "measurement",
        "diagnostic": False,
        "remaining_time": True,
        "note": "Dreame FrontBrush/PropFrontBrushLeftHeal. App percentage/hours matched the raw minutes.",
    },
    (7, 6): {
        "name": "Rear brush maximum life raw",
        "confidence": "plugin",
        "icon": "mdi:rotate-right",
        "unit": "min",
        "diagnostic": True,
        "note": "Dreame BackBrush/PropBackBrushMaxHeal. Optional service on H15.",
    },
    (7, 7): {
        "name": "Rear brush remaining raw",
        "confidence": "plugin",
        "icon": "mdi:rotate-right",
        "unit": "min",
        "device_class": "duration",
        "diagnostic": True,
        "remaining_time": True,
        "note": "Dreame BackBrush service. H15 currently reports -1, so this accessory is likely unsupported.",
    },
    (10, 1): {
        "name": "Dip angle level",
        "confidence": "plugin",
        "icon": "mdi:angle-acute",
        "diagnostic": True,
        "note": "Dreame plugin property PropDipAngleLevel.",
    },
    (16, 1): {
        "name": "Suction setting",
        "confidence": "confirmed",
        "icon": "mdi:fan",
        "diagnostic": False,
        "value_map": H15_SUCTION_MAP,
        "note": "Dreame PropCleanPower. H15 UI: Gentle/Standard/Strong.",
    },
    (16, 2): {
        "name": "Water level",
        "confidence": "confirmed",
        "icon": "mdi:water",
        "diagnostic": False,
        "value_map": H15_WATER_LEVEL_MAP,
        "note": "Dreame PropCleanWater. H15 UI exposes Standard and High; value 1 is retained as legacy/low until observed.",
    },
    (16, 6): {
        "name": "Personalized mode flag",
        "confidence": "plugin",
        "icon": "mdi:tune-variant",
        "diagnostic": True,
        "note": "Dreame PropCustomSwitch.",
    },
    (16, 7): {
        "name": "Cleaning mode",
        "confidence": "confirmed",
        "icon": "mdi:broom",
        "diagnostic": False,
        "value_map": H15_CLEANING_MODE_MAP,
        "note": "Dreame internal PropVoiceName; w2449e resource enables correctPropVoiceName. H15 UI maps 1=Quiet, 3=Turbo, 4=Personalized.",
    },
    (16, 8): {
        "name": "Hot water mode",
        "confidence": "confirmed",
        "icon": "mdi:water-thermometer",
        "diagnostic": False,
        "value_map": H15_HOT_WATER_MAP,
        "note": "Dreame PropCustomHotWaterMode. H15 UI: Off/Mild/Standard/Thermal.",
    },
    (13, 2): {
        "name": "Electrolyzed water setting raw",
        "confidence": "plugin",
        "icon": "mdi:flash-outline",
        "diagnostic": True,
        "note": "Dreame ElectrolyzedWater/PropElectrolyzedWaterSwitch. w2449e resource disables this setting in the UI.",
    },
    (16, 3): {
        "name": "Electrolyzed water raw",
        "confidence": "plugin",
        "icon": "mdi:flash-outline",
        "diagnostic": True,
        "note": "Dreame VacuumExtend/PropElecWater. w2449e does not expose the electrolyzed-water setting in its UI.",
    },
    (16, 4): {
        "name": "Brush speed raw",
        "confidence": "plugin",
        "icon": "mdi:rotate-right",
        "diagnostic": True,
        "note": "Dreame VacuumExtend/PropBrushSpeed. Not shown in the current H15 UI.",
    },
    (19, 2): {
        "name": "Filter maximum life raw",
        "confidence": "plugin",
        "icon": "mdi:air-filter",
        "unit": "min",
        "diagnostic": True,
        "note": "Dreame Filter/PropFilterMaxHeal.",
    },
    (19, 3): {
        "name": "Filter remaining",
        "confidence": "confirmed",
        "icon": "mdi:air-filter",
        "unit": "min",
        "device_class": "duration",
        "state_class": "measurement",
        "diagnostic": False,
        "remaining_time": True,
        "note": "Dreame Filter/PropFilterLeftHeal. App percentage/hours matched the raw minutes.",
    },
    (20, 2): {
        "name": "Dust bag maximum life raw",
        "confidence": "plugin",
        "icon": "mdi:sack-outline",
        "unit": "min",
        "diagnostic": True,
        "note": "Dreame DustBag/PropDustBagMaxHeal. Optional service; not currently observed on this H15.",
    },
    (20, 3): {
        "name": "Dust bag remaining raw",
        "confidence": "plugin",
        "icon": "mdi:sack-outline",
        "unit": "min",
        "diagnostic": True,
        "note": "Dreame DustBag/PropDustBagLeftHeal. Optional service; not currently observed on this H15.",
    },
    (21, 6): {
        "name": "Suction brush maximum life raw",
        "confidence": "plugin",
        "icon": "mdi:rotate-right",
        "unit": "min",
        "diagnostic": True,
        "note": "Dreame SuckBrush/PropSuckBrushMaxHeal. Optional service.",
    },
    (21, 7): {
        "name": "Suction brush remaining raw",
        "confidence": "plugin",
        "icon": "mdi:rotate-right",
        "unit": "min",
        "diagnostic": True,
        "note": "Dreame SuckBrush/PropSuckBrushLeftHeal. Optional service.",
    },
    (22, 6): {
        "name": "Suction filter maximum life raw",
        "confidence": "plugin",
        "icon": "mdi:air-filter",
        "unit": "min",
        "diagnostic": True,
        "note": "Dreame SuckFilter/PropSuckFilterMaxHeal. Optional service.",
    },
    (22, 7): {
        "name": "Suction filter remaining raw",
        "confidence": "plugin",
        "icon": "mdi:air-filter",
        "unit": "min",
        "diagnostic": True,
        "note": "Dreame SuckFilter/PropSuckFilterLeftHeal. Optional service.",
    },
    (23, 1): {
        "name": "GlideWheel traction",
        "confidence": "plugin",
        "icon": "mdi:car-traction-control",
        "diagnostic": False,
        "value_map": H15_TRACTION_MAP,
        "note": "Dreame Wheel/PropPowerWheel. App code maps raw 1=Gentle, 0=Balanced, 2=Turbo.",
    },
    (24, 1): {
        "name": "Lifting robotic arm modes raw",
        "confidence": "plugin",
        "icon": "mdi:robot-industrial-outline",
        "diagnostic": False,
        "decoder": "mechanical_arm_2449",
        "note": "Dreame MechanicalArm/PropMechanicalArmSwitch. w2449e uses inverted bits: bit0 Smart, bit3 Hot Water, bit2 Suction, bit4 Custom; 0 means selected. Bit1 is unused by the w2449e UI.",
    },
    (25, 1): {
        "name": "Global hot water mode raw",
        "confidence": "candidate",
        "icon": "mdi:water-thermometer-outline",
        "diagnostic": True,
        "note": "Dreame HotWater/PropGlobalHotWaterMode. Not yet observed in the H15 cache.",
    },
    (26, 1): {
        "name": "Smart drying",
        "confidence": "plugin",
        "icon": "mdi:weather-sunny-alert",
        "diagnostic": False,
        "value_map": {0: "On", 1: "Off"},
        "note": "Dreame Smart/PropSmartDrySwitch at 26.1. App code treats raw 0 as Smart Drying enabled.",
    },
    (26, 2): {
        "name": "Smart moisture protection",
        "confidence": "plugin",
        "icon": "mdi:water-sync",
        "diagnostic": False,
        "value_map": {0: "On", 1: "Off"},
        "note": "Dreame Smart/PropSmartReDrySwitch at 26.2. App code treats raw 0 as Smart Moisture Protection enabled.",
    },
    (26, 3): {
        "name": "Roller brush moisture sensitivity",
        "confidence": "plugin",
        "icon": "mdi:water-percent",
        "diagnostic": False,
        "value_map": H15_MOISTURE_SENSITIVITY_MAP,
        "note": "Dreame Smart/PropSmartDryRate at 26.3. App slider writes raw 2=Low, 3=Medium, 4=High.",
    },
    (26, 4): {
        "name": "Raw 26.4",
        "confidence": "unmapped",
        "icon": "mdi:code-tags",
        "diagnostic": True,
    },
    (26, 5): {
        "name": "Raw 26.5",
        "confidence": "unmapped",
        "icon": "mdi:code-tags",
        "diagnostic": True,
    },
    (100, 1): {
        "name": "Remote forward raw",
        "confidence": "plugin",
        "icon": "mdi:arrow-up",
        "diagnostic": True,
        "note": "Dreame DeviceControl/PropDeviceControlFront. w2449e has isSupportControl=false; diagnostic read only.",
    },
    (100, 2): {
        "name": "Remote backward raw",
        "confidence": "plugin",
        "icon": "mdi:arrow-down",
        "diagnostic": True,
        "note": "Dreame DeviceControl/PropDeviceControlBack. w2449e has isSupportControl=false; diagnostic read only.",
    },
    (100, 3): {
        "name": "Remote left raw",
        "confidence": "plugin",
        "icon": "mdi:arrow-left",
        "diagnostic": True,
        "note": "Dreame DeviceControl/PropDeviceControlLeft. w2449e has isSupportControl=false; diagnostic read only.",
    },
    (100, 4): {
        "name": "Remote right raw",
        "confidence": "plugin",
        "icon": "mdi:arrow-right",
        "diagnostic": True,
        "note": "Dreame DeviceControl/PropDeviceControlRight. w2449e has isSupportControl=false; diagnostic read only.",
    },
    (100, 5): {
        "name": "Remote left-back raw",
        "confidence": "plugin",
        "icon": "mdi:arrow-bottom-left",
        "diagnostic": True,
        "note": "Dreame DeviceControl/PropDeviceControlLeftBack. w2449e has isSupportControl=false; diagnostic read only.",
    },
    (100, 6): {
        "name": "Remote right-back raw",
        "confidence": "plugin",
        "icon": "mdi:arrow-bottom-right",
        "diagnostic": True,
        "note": "Dreame DeviceControl/PropDeviceControlRightBack. w2449e has isSupportControl=false; diagnostic read only.",
    },
}


def is_h15_pro_heat(model: str | None) -> bool:
    """Return whether a device uses the H15 Pro Heat profile."""
    return str(model or "").lower() == H15_PRO_HEAT_MODEL


H15_SELECT_SETTINGS: dict[tuple[int, int], dict[int, str]] = {
    (16, 7): H15_CLEANING_MODE_MAP,
    (16, 1): H15_SUCTION_MAP,
    (16, 2): {2: "Standard", 3: "High"},
    (16, 8): H15_HOT_WATER_MAP,
    (1, 8): {4: "Auto-Adjust", 2: "Standard", 3: "Deep-Clean"},
    (1, 10): H15_DRY_MODE_MAP,
    (23, 1): {1: H15_TRACTION_MAP[1], 0: H15_TRACTION_MAP[0], 2: H15_TRACTION_MAP[2]},
    (26, 3): H15_MOISTURE_SENSITIVITY_MAP,
    (1, 67): H15_DETERGENT_MODE_MAP,
    (25, 1): {1: "Mild", 2: "Standard", 3: "Thermal"},
    (1, 77): {0: "None", 10000000: "Once", 1111111: "Whole Week", 11111: "Weekday", 1100000: "Weekends"},
}

# (on, off) values differ from the legacy H14 switch implementation.
H15_SWITCH_SETTINGS: dict[tuple[int, int], tuple[int, int]] = {
    (1, 7): (0, 1),
    (1, 9): (0, 1),
    (26, 1): (0, 1),
    (26, 2): (0, 1),
    (16, 6): (1, 0),
    (1, 11): (0, 1),
}

H15_ARM_MODES: dict[int, str] = {0: "Smart", 3: "Hot Water", 2: "Suction", 4: "Custom"}
H15_NUMBER_SETTINGS: dict[tuple[int, int], tuple[int, int, int]] = {(1, 14): (0, 60, 30), (1, 76): (0, 86340, 60)}
H15_CONTROL_KEYS = (
    set(H15_SELECT_SETTINGS) | set(H15_SWITCH_SETTINGS) | set(H15_NUMBER_SETTINGS) | {(24, 1)}
)


def h15_setting_name(key: tuple[int, int]) -> str:
    """Return the profile name without duplicating H15/H14 mappings."""
    if key == (1, 77):
        return "Wash and dry schedule"
    if key == (1, 76):
        return "Scheduled time (minutes after midnight)"
    if key == (25, 1):
        return "Default hot water temperature"
    if key == (16, 6):
        return "Custom cleaning enabled"
    return H15_PROPERTY_META[key]["name"]


def _current(props: dict[tuple[int, int], Any], key: tuple[int, int]) -> int:
    try:
        value = props[key]
        number = int(value)
        if isinstance(value, bool) or number != float(value) or number < 0:
            raise ValueError
        return number
    except (KeyError, TypeError, ValueError, OverflowError) as err:
        raise ValueError(f"Current H15 property {key[0]}.{key[1]} is unknown; refresh the device first") from err


def build_h15_write_plan(
    key: tuple[int, int], value: int, props: dict[tuple[int, int], Any], *, arm_bit: int | None = None,
) -> dict[tuple[int, int], int]:
    """Validate a setting and preserve the app's coupled setting behavior.

    Never write status/telemetry, unknown enums, schedule encodings or H14
    controls. The arm is read-modify-write with inverted bits.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("H15 setting values must be integers")  # noqa: TRY004 -- user-facing validation
    if arm_bit is not None:
        if key != (24, 1) or arm_bit not in H15_ARM_MODES or value not in (0, 1):
            raise ValueError("Invalid H15 lifting arm setting")
        current = _current(props, key)
        if current > 31:
            raise ValueError("Unknown H15 lifting arm encoding")
        updated = current & ~(1 << arm_bit) if value else current | (1 << arm_bit)
        return {key: updated}

    if key in H15_SELECT_SETTINGS:
        if value not in H15_SELECT_SETTINGS[key]:
            raise ValueError("Unsupported H15 option")
    elif key in H15_SWITCH_SETTINGS:
        if value not in H15_SWITCH_SETTINGS[key]:
            raise ValueError("Unsupported H15 switch value")
    elif key in H15_NUMBER_SETTINGS:
        minimum, maximum, step = H15_NUMBER_SETTINGS[key]
        if not minimum <= value <= maximum or (value - minimum) % step:
            raise ValueError("H15 number is outside its supported range")
    else:
        raise ValueError("This H15 property is not a writable setting")

    if key in {(1, 76), (1, 77)}:
        companion = (1, 77) if key == (1, 76) else (1, 76)
        if companion not in props or props[companion] in (None, -1, "-1"):
            if key == (1, 76) or value == 0:
                return {key: value}
            raise ValueError("Set the scheduled time before enabling a schedule")
        current = _current(props, companion)
        if companion == (1, 77):
            decode_schedule(current)
        elif current > 86340 or current % 60:
            raise ValueError("Unknown scheduled time encoding")
        return {key: value, companion: current}

    if key == (24, 1):
        current = _current(props, key)
        if current > 31:
            raise ValueError("Unknown lifting arm encoding")
        return {key: value | (current & 2)}

    if key in {(1, 8), (1, 81), (1, 75), (1, 10), (1, 82), (1, 83)}:
        # Main-page PopWashDry writes six fields together. Advanced scheduling
        # writes only its own wash/dry pair. Preserve the companion preference.
        pairs = {8: 10, 10: 8, 81: 82, 82: 81, 75: 83, 83: 75}
        companion = (1, pairs[key[1]])
        current = _current(props, companion)
        if current not in H15_SELECT_SETTINGS[companion]:
            raise ValueError("Refresh the companion wash/dry mode before changing this setting")
        if key[1] in (75, 83):
            return {key: value, companion: current}
        wash = value if key[1] in (8, 81) else current
        dry = value if key[1] in (10, 82) else current
        return {(1, 8): wash, (1, 10): dry, (1, 81): wash,
                (1, 82): dry, (1, 75): wash, (1, 83): dry}

    if key in {(16, 1), (16, 2), (16, 7), (16, 8)}:
        if key == (16, 8) and value == 0:
            return {key: value}
        hot = value if key == (16, 8) else _current(props, (16, 8))
        if hot not in H15_HOT_WATER_MAP:
            raise ValueError("Unknown H15 hot water setting")
        if key == (16, 1) and hot:
            raise ValueError("Suction is fixed to Gentle while hot water is enabled")
        if key == (16, 7):
            power, water = {1: (1, 2), 3: (3, 3), 4: (1 if hot else 2, 2)}[value]
            return {(16, 7): value, (16, 1): power, (16, 2): water, (16, 6): 1}
        water = value if key == (16, 2) else _current(props, (16, 2))
        power = value if key == (16, 1) else (1 if hot or key == (16, 8) else _current(props, (16, 1)))
        if water not in H15_SELECT_SETTINGS[(16, 2)] or power not in H15_SUCTION_MAP:
            raise ValueError("Refresh current H15 suction and water settings first")
        result = {(16, 1): power, (16, 2): water, (16, 7): 4, (16, 6): 1}
        if key == (16, 8):
            result[key] = value
        return result

    return {key: value}


# Decimal digits, not a binary bitfield: Sunday / Saturday ... Monday.
H15_SCHEDULE_DAYS = {0: "Sunday", 1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday"}


def decode_schedule(value: int) -> dict[str, Any]:
    """Decode the app's decimal weekday encoding, rejecting unknown digits."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 11111111:
        raise ValueError("Unknown schedule encoding")
    digits = f"{value:08d}"
    if any(digit not in "01" for digit in digits):
        raise ValueError("Unknown schedule encoding")
    days = [day for day in H15_SCHEDULE_DAYS if (value // 10 ** (6 if day == 0 else day - 1)) % 10]
    return {"enabled": value != 0, "once": bool(value // 10000000), "days": days}


def build_schedule_day_plan(day: int, enabled: bool, props: dict[tuple[int, int], Any]) -> dict[tuple[int, int], int]:
    if day not in H15_SCHEDULE_DAYS or not isinstance(enabled, bool):
        raise ValueError("Invalid schedule weekday")
    current = _current(props, (1, 77))
    decode_schedule(current)
    seconds = _current(props, (1, 76))
    if seconds > 86340 or seconds % 60:
        raise ValueError("Unknown scheduled time encoding")
    # Selecting weekdays creates a recurring schedule, as in the app UI.
    code = current % 10000000
    power = 10 ** (6 if day == 0 else day - 1)
    code += (int(enabled) - (code // power) % 10) * power
    return {(1, 77): code, (1, 76): seconds}


H15_BUTTON_COMMANDS = {
    "start_self_clean": {"name": "Start self-cleaning", "icon": "mdi:water-sync"},
    "resume_self_clean": {"name": "Resume self-cleaning", "icon": "mdi:play"},
    "stop_self_clean": {"name": "Stop self-cleaning", "icon": "mdi:stop"},
    "start_self_dry": {"name": "Start drying", "icon": "mdi:hair-dryer"},
    "stop_self_dry": {"name": "Stop drying", "icon": "mdi:stop"},
    "reset_front_brush": {"name": "Reset roller brush life", "icon": "mdi:restart", "reset": (6, 1), "remaining": (6, 7), "maximum": (6, 6)},
    "reset_back_brush": {"name": "Reset rear brush life", "icon": "mdi:restart", "reset": (7, 1), "remaining": (7, 7), "maximum": (7, 6), "optional": True},
    "reset_filter": {"name": "Reset filter life", "icon": "mdi:restart", "reset": (19, 1), "remaining": (19, 3), "maximum": (19, 2)},
}
H15_WASH_STATES = {5, 26, 27, 28, 42}
H15_WASH_PAUSED_STATES = {11, 30, 31, 37, 43}
H15_DRY_STATES = {6, 23, 24, 25, 32, 33, 34, 35, 12}
H15_DOCK_IDLE_STATES = {4, 7, 15}


def build_h15_command_plan(command: str, props: dict[tuple[int, int], Any]) -> dict[tuple[int, int], int]:
    """App-defined commands, separate from settings and sensor values."""
    if command not in H15_BUTTON_COMMANDS:
        raise ValueError("Unknown device command")
    meta = H15_BUTTON_COMMANDS[command]
    if "move" in meta:
        if _current(props, (10, 1)) != 2:
            raise ValueError("Movement requires the device to be horizontal, as in the app")
        return {meta["move"]: 1}
    if "reset" in meta:
        _current(props, meta["remaining"])
        return {meta["reset"]: 1}
    state = _current(props, (1, 28))
    if command == "stop_self_clean":
        if state not in H15_WASH_STATES | H15_WASH_PAUSED_STATES:
            raise ValueError("Self-cleaning is not running")
        return {(1, 1): 0}
    if command == "stop_self_dry":
        if state not in H15_DRY_STATES:
            raise ValueError("Drying is not running")
        return {(1, 2): 0}
    # This is checked again after the coordinator refreshes control properties,
    # so a newly reported fault cannot be bypassed by a stale native dialog.
    if props.get((4, 2)) not in (None, -1, "-1") and _current(props, (4, 2)) > 0:
        raise ValueError("Resolve the device fault before starting or resuming a task")
    if command == "resume_self_clean":
        if state not in H15_WASH_PAUSED_STATES:
            raise ValueError("Self-cleaning is not paused")
        return {(1, 1): 1}
    if state not in H15_DOCK_IDLE_STATES:
        raise ValueError("Place the idle device on its dock before starting a task")
    if command == "start_self_clean":
        if _current(props, (3, 1)) < 20:
            raise ValueError("Self-cleaning requires at least 20% battery")
        # The cloud cache never reports the self-cleaning mode (1.8), so it is
        # usually unknown. Fall back to Auto-Adjust (4), the app default, so the
        # start button works; a known/selected mode is still used as-is.
        mode = props.get((1, 8))
        try:
            mode = int(mode)
        except (TypeError, ValueError):
            mode = None
        if mode not in H15_SELECT_SETTINGS[(1, 8)]:
            mode = 4
        return {(1, 1): mode}
    mode = _current(props, (1, 10))
    if mode not in H15_DRY_COMMAND_VALUES:
        raise ValueError("Unknown drying mode")
    return {(1, 2): H15_DRY_COMMAND_VALUES[mode]}

H15_WARN_FIELDS = [(0, 1, {1: 'Clean water tank empty'}),
 (1, 1, {1: 'Detergent empty'}),
 (2, 3, {3: 'Self-cleaning recommended'}),
 (4, 1, {1: 'Roller brush worn'}),
 (5, 1, {}),
 (6, 1, {1: 'Filter worn'}),
 (7, 1, {1: 'Detergent replacement reminder'}),
 (8, 1, {1: 'Dirty water tank needs cleaning'}),
 (9, 1, {1: 'Low battery for automatic self-cleaning'}),
 (10, 1, {1: 'Scheduled cleaning skipped: low battery'}),
 (11, 1, {1: 'Device locked on dock'}),
 (12, 1, {1: 'Device unlocked'}),
 (13, 1, {1: 'Dock filter replacement reminder'}),
 (14, 1, {1: 'Suction brush worn'}),
 (15, 1, {1: 'Suction filter worn'}),
 (16, 1, {1: 'Dock water supply low'}),
 (17, 1, {1: 'Disposable filter reminder'})]

H15_ERROR_FIELDS = [(0, 15, {8: 'HEPA filter missing'}),
 (4,
  63,
  {1: 'Roller brush missing',
   2: 'Device fault',
   3: 'Roller brush blocked',
   4: 'Roller brush blocked',
   5: 'Roller brush blocked',
   6: 'Roller brush blocked',
   7: 'Roller brush blocked',
   21: 'Roller brush missing',
   23: 'Roller brush blocked',
   24: 'Roller brush blocked',
   25: 'Roller brush blocked',
   26: 'Roller brush blocked',
   27: 'Roller brush blocked',
   41: 'Roller brush missing',
   43: 'Roller brush blocked',
   44: 'Roller brush blocked',
   45: 'Roller brush blocked',
   46: 'Roller brush blocked',
   47: 'Roller brush blocked'}),
 (10, 1, {}),
 (11, 1, {1: 'Dirty water tank missing'}),
 (12, 1, {1: 'Dirty water tank full'}),
 (13, 7, {}),
 (16, 15, {}),
 (20, 1, {}),
 (21, 1, {}),
 (22, 1, {}),
 (23, 1, {1: 'Clean water tank empty'}),
 (24, 1, {1: 'Vacuum tube blocked'}),
 (25, 1, {1: 'Dock sewage cover open'}),
 (26, 1, {1: 'Dock tube blocked'}),
 (27, 1, {}),
 (28, 1, {1: 'Dirty water tank blocked'}),
 (29, 1, {}),
 (30, 1, {1: 'Device fault'}),
 (31, 1, {})]


H15_ALERT_BINARY_SENSORS = []
for _kind, _piid, _fields in [("warn", 1, H15_WARN_FIELDS), ("error", 2, H15_ERROR_FIELDS)]:
    for _shift, _mask, _labels in _fields:
        for _label in dict.fromkeys(_labels.values()):
            _values = tuple(value for value, label in _labels.items() if label == _label)
            H15_ALERT_BINARY_SENSORS.append({
                "key": f"h15_{_kind}_{_shift}_{_values[0]}", "name": _label,
                "data_key": f"4.{_piid}", "shift": _shift,
                "field_mask": _mask, "field_values": _values,
            })


def decode_h15_alerts(value: Any, fields: list) -> list[str] | None:
    try:
        raw = int(value)
        if isinstance(value, bool) or raw < 0 or raw != float(value):
            return None
    except (ValueError, TypeError, OverflowError):
        return None
    return list(dict.fromkeys(labels[(raw >> shift) & mask] for shift, mask, labels in fields if (raw >> shift) & mask in labels))


H15_PROPERTY_META[(4, 1)].update(name="Warnings", decoder="warnings")
H15_PROPERTY_META[(4, 2)].update(name="Errors", decoder="errors")
H15_PROPERTY_META[(25, 1)].update(name="Default hot water temperature", confidence="plugin", value_map={1: "Mild", 2: "Standard", 3: "Thermal"})
H15_PROPERTY_META[(1, 76)].update(name="Scheduled wash and dry time", confidence="plugin", note="Seconds after midnight on the device's configured timezone.")
H15_PROPERTY_META[(1, 77)].update(name="Scheduled wash and dry repeat", confidence="plugin", decoder="schedule", note="Decimal weekday digits; leading 1 denotes a once-only task.")


# w2449e enables the two-direction control page (isSupportControlS), while
# six-direction robot control remains disabled (isSupportControl=false).
H15_BUTTON_COMMANDS.update({
    "move_forward": {"name": "Move forward briefly", "icon": "mdi:arrow-up", "move": (100, 1)},
    "move_backward": {"name": "Move backward briefly", "icon": "mdi:arrow-down", "move": (100, 2)},
})
for _key in [(100, 1), (100, 2)]:
    H15_PROPERTY_META[_key]["note"] = "w2449e isSupportControlS=true: forward/back while horizontal (10.1=2). HA buttons send a bounded 0.3 s pulse with an explicit stop."
H15_PROPERTY_META[(4, 1)]["note"] = "App SoakWashWarnInfo49 warning table, selected by w2449e warnVersion=2; raw value retained."
H15_PROPERTY_META[(4, 2)]["note"] = "App SoakWashWarnInfo49 error table, selected by w2449e warnVersion=2; raw value retained."
H15_PROPERTY_META[(1, 1)]["note"] = "Self-clean command: 0 stop; 1 resume; start uses selected H15 wash mode 2/3/4. Not a writable sensor."
H15_PROPERTY_META[(1, 2)]["note"] = "Dry command: 0 stop; High-Speed setting 1 sends 1; Super-Speed setting 3 sends 4. Not a writable sensor."
H15_PROPERTY_META[(4, 83)] = {"name": "Raw 4.83", "confidence": "unmapped", "diagnostic": True, "icon": "mdi:code-tags", "note": "Reported as -1 in the 2026-10-07 tank-removal snapshot. No tank meaning can be inferred."}
H15_TARGETED_KEYS = tuple(dict.fromkeys((*H15_TARGETED_KEYS, (4, 83))))


# w2449e holdPluginVoiceType=4 selects DATA_VOICE4, not the common default list.
H15_VOICE_LANGUAGE_MAP = {2: "English", 3: "German", 4: "French", 6: "Italian", 7: "Spanish", 16: "Dutch", 17: "Portuguese"}
H15_SELECT_SETTINGS[(1, 17)] = H15_VOICE_LANGUAGE_MAP
H15_CONTROL_KEYS.add((1, 17))
H15_PROPERTY_META[(1, 17)].update(value_map=H15_VOICE_LANGUAGE_MAP, confidence="plugin", note="VoiceSettingPage DATA_VOICE4 for w2449e: select an installed voice ID with set_properties; physical verification pending.")
H15_PROPERTY_META[(1, 14)]["note"] = "VoiceSettingPage app slider uses 0/30/60. HA writes these app-supported levels; exact raw telemetry is retained."
H15_PROPERTY_META[(1, 53)].update(name="Total working time", unit="min", device_class="duration", note="CleanLog displays PropTotalTime / 60 as hours, so this property is minutes.")
H15_PROPERTY_META[(1, 55)].update(name="Start time", device_class="timestamp", timestamp=True, note="CleanLog converts PropStartTime seconds to milliseconds (value * 1000).")
for _key, _name in [((1, 56), "Self-drying task duration"), ((1, 57), "Self-cleaning task duration")]:
    H15_PROPERTY_META[_key].update(name=_name, unit="s", device_class="duration", note="StatusUtil divides this task duration by 60 for minutes and combines it with progress. This is not a lifetime cumulative counter.")
for _key, _name in [((1, 29), "Self-cleaning progress"), ((1, 30), "Self-drying progress")]:
    H15_PROPERTY_META[_key].update(name=_name, unit="%", state_class="measurement", note="StatusUtil uses (100 - progress) / 100 to estimate remaining task duration.")


# Every writable wash/dry mode is a select, including return/schedule aliases.
# The app synchronizes the three copies when a preference changes.
for _mode_key in [(1, 81), (1, 75)]:
    H15_SELECT_SETTINGS[_mode_key] = dict(H15_SELECT_SETTINGS[(1, 8)])
    H15_PROPERTY_META[_mode_key]["value_map"] = dict(H15_SELECT_SETTINGS[(1, 8)])
for _mode_key in [(1, 82), (1, 83)]:
    H15_SELECT_SETTINGS[_mode_key] = dict(H15_DRY_MODE_MAP)
    H15_PROPERTY_META[_mode_key]["value_map"] = dict(H15_DRY_MODE_MAP)

# A dropdown can select any of the 16 valid combinations of arm modes;
# individual switches remain available, and reserved bit 1 is preserved.
H15_SELECT_SETTINGS[(24, 1)] = {}
for _combination in range(16):
    _enabled = [name for index, (bit, name) in enumerate(H15_ARM_MODES.items()) if _combination & (1 << index)]
    _wire_value = sum(1 << bit for index, bit in enumerate(H15_ARM_MODES) if not _combination & (1 << index))
    H15_SELECT_SETTINGS[(24, 1)][_wire_value] = "All modes" if len(_enabled) == 4 else " + ".join(_enabled) if _enabled else "None"
H15_PROPERTY_META[(24, 1)]["name"] = "Lifting arm modes"
H15_CONTROL_KEYS.update(H15_SELECT_SETTINGS)
H15_PROPERTY_META[(1, 28)]["name"] = "Work state"
H15_PROPERTY_META[(1, 6)].update(name="Altitude setting raw", confidence="plugin", value_map={0: "Standard altitude", 1: "High altitude"}, note="DeviceLocationPage writes PropHighLevelMode based on selected city ASL. w2449e holdPluginEnableLocation=false; not a user cleaning-mode selector.")
H15_PROPERTY_META[(4, 6)].update(name="Dirty water tank status", confidence="confirmed", value_map={0: "Normal", 81: "Full"}, note="H15-only live comparison: raw 81 coincided with the app's Used water tank is full alert and error bit 4096; the 2026-10-08 export after the alert cleared returned raw 0. Other raw values remain unknown; this is a state, not a percentage.")
H15_PROPERTY_META[(4, 2)]["note"] += " Live-confirmed 2026-10-07: raw 4096 matches app Used water tank is full."
for _alert in H15_ALERT_BINARY_SENSORS:
    _alert["confidence"] = "confirmed" if _alert["data_key"] == "4.2" and _alert["shift"] == 12 and _alert["field_values"] == (1,) else "plugin"


# Only display useful telemetry in the device Sensors card. Other raw fields
# remain available as optional diagnostics without altering property mappings.
H15_GENERAL_SENSOR_KEYS = {(3, 1), (1, 28), (1, 29), (1, 30),
                           (1, 53), (1, 54), (1, 55), (1, 56), (1, 57)}
H15_MAINTENANCE_SENSOR_KEYS = {(4, 1), (4, 2), (4, 6), (6, 7), (7, 7), (19, 3)}


def h15_sensor_is_optional(key: tuple[int, int]) -> bool:
    """Keep unresolved/duplicate readings out of the main device cards."""
    return key not in H15_GENERAL_SENSOR_KEYS | H15_MAINTENANCE_SENSOR_KEYS


# The app presents one wash/dry choice while internally synchronizing copies.
H15_PRIMARY_SELECT_KEYS = set(H15_SELECT_SETTINGS) - {(1, 75), (1, 81), (1, 82), (1, 83), (24, 1), (25, 1)}

# Separate entities only for tank, wear and routine maintenance indicators.
# All other decoded warnings/errors remain on the aggregate alert sensors.
H15_PRIMARY_ALERT_KEYS = {"h15_warn_0_1", "h15_warn_1_1", "h15_warn_2_3",
                          "h15_warn_4_1", "h15_warn_6_1", "h15_warn_7_1", "h15_warn_8_1",
                          "h15_error_11_1", "h15_error_12_1", "h15_error_23_1", "h15_error_28_1"}


# ---------------------------------------------------------------------------
# App-verified display mappings for dreame.hold.w2449e (H15 Pro Heat).
# Source: Dreamehome RN plugin dreame.vacuum.common versionCode 1240 with the
# w2449e resource config, executed against a simulated device so every value
# below is exactly what the official app derives from the raw property.
# ---------------------------------------------------------------------------

# PopParamList.dryTitleMap: 1/2 = High-Speed, 3/4 = Super-Speed. The app
# writes 4 for Super-Speed (drySetValueMap 3 -> 4), so the device can report 4.
H15_DRY_MODE_VALUE_MAP = {1: "High-Speed Drying", 2: "High-Speed Drying", 3: "Super-Speed Drying", 4: "Super-Speed Drying"}
# PopParamList.drySetValueMap: value sent to the (1, 2) dry command.
H15_DRY_COMMAND_VALUES = {1: 1, 2: 2, 3: 4, 4: 4}
for _mode_key in [(1, 10), (1, 82), (1, 83)]:
    H15_PROPERTY_META[_mode_key]["value_map"] = dict(H15_DRY_MODE_VALUE_MAP)
# Raw values that the selects show as an equivalent option (no duplicate options).
H15_SELECT_VALUE_ALIASES: dict[tuple[int, int], dict[int, int]] = {
    _mode_key: {2: 1, 4: 3} for _mode_key in [(1, 10), (1, 82), (1, 83)]
}

# CustomWashSetting.getCleanWaterTitleMap with correctPropCleanWater=true.
H15_WATER_LEVEL_MAP.update({1: "Slightly dry", 2: "Standard", 3: "High"})
H15_PROPERTY_META[(16, 2)]["value_map"] = dict(H15_WATER_LEVEL_MAP)

# PopParamList.selfCleanTextMap applies to all three wash-mode copies
# (washDryKeyMap: 1.8 / 1.81 / 1.75).
H15_SELF_CLEAN_MODE_MAP.update({2: "Standard Immersive Self-Cleaning", 3: "Deep-Clean Immersive Self-Cleaning",
                                4: "Smart Self-Cleaning", 5: "Hot Wash Self-Cleaning"})
for _mode_key in [(1, 8), (1, 75), (1, 81)]:
    H15_PROPERTY_META[_mode_key]["value_map"] = dict(H15_SELF_CLEAN_MODE_MAP)

# StatusUtil.getStatusText for every WorkMode (1.28), as shown in the app.
# H15_WORK_MODE_MAP keeps the internal WorkMode names (vacuum attributes).
H15_WORK_STATE_APP_TEXT: dict[int, str] = {
    1: "Mop in progress", 2: "Offline", 3: "Standby", 4: "Charging",
    5: "Self-cleaning with hot water in progress", 6: "Drying", 7: "Sleeping",
    8: "Vacuuming", 9: "Adding clean water", 10: "Floor washing paused",
    11: "Self-cleaning paused", 12: "Drying paused", 13: "OTA is being updated",
    14: "Voice package is being upgraded", 15: "Charging Complete",
    16: "Mop in progress", 17: "Mop in progress", 18: "Mop in progress",
    19: "Mop in progress", 20: "Mop in progress", 21: "Mop in progress",
    22: "Mop in progress", 23: "Drying", 24: "Drying", 25: "Drying",
    26: "Self-cleaning with hot water in progress",
    27: "Self-cleaning with hot water in progress",
    28: "Self-cleaning with hot water in progress", 29: "Vacuuming paused",
    30: "Self-cleaning paused", 31: "Self-cleaning paused", 32: "Drying",
    33: "Drying", 34: "Smart drying in progress",
    35: "Smart moisture protection in progress", 36: "Smart re-wash in progress",
    37: "Self-cleaning paused", 40: "Mop in progress", 41: "Mop in progress",
    42: "Hot wash self-cleaning in progress", 43: "Hot wash self-cleaning paused",
}
H15_PROPERTY_META[(1, 28)]["value_map"] = dict(H15_WORK_STATE_APP_TEXT)
H15_PROPERTY_META[(1, 28)]["note"] = "Display text from Dreamehome StatusUtil.getStatusText (w2449e). Internal WorkMode name is exposed as the vacuum work_mode attribute."
