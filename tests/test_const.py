"""Tests for the pure decoding logic and table consistency in const.py."""
from custom_components.dreame_wet_dry_vacuum.const import (
    ALERT_BINARY_SENSORS,
    CONSUMABLE_MAX_KEYS,
    CONSUMABLE_SENSORS,
    DEVICE_STATUS,
    ERROR_DECODE,
    KNOWN_MQTT_PROPS,
    STATUS_GROUP,
    WARN_DECODE,
    decode_field_alerts,
)


class TestDecodeFieldAlerts:
    def test_zero_means_no_alert(self):
        assert decode_field_alerts(0, WARN_DECODE) == []
        assert decode_field_alerts(0, ERROR_DECODE) == []

    def test_warn_bit0_clean_water_empty(self):
        assert decode_field_alerts(1, WARN_DECODE) == ["Clean water tank empty"]

    def test_warn_bit1_detergent_empty(self):
        assert decode_field_alerts(2, WARN_DECODE) == ["Detergent empty"]

    def test_warn_bit8_dirty_tank_not_clean(self):
        assert decode_field_alerts(1 << 8, WARN_DECODE) == [
            "Dirty water tank needs cleaning after self-cleaning"
        ]

    def test_warn_bit16_station_water_low(self):
        assert decode_field_alerts(1 << 16, WARN_DECODE) == [
            "Station water supply low"
        ]

    def test_warn_multiple_bits(self):
        alerts = decode_field_alerts((1 << 16) | 1, WARN_DECODE)
        assert alerts == [
            "Clean water tank empty",
            "Station water supply low",
        ]

    def test_error_bit11_dirty_tank_missing(self):
        assert decode_field_alerts(1 << 11, ERROR_DECODE) == [
            "Dirty water tank not installed"
        ]

    def test_error_bit12_dirty_tank_full(self):
        assert decode_field_alerts(1 << 12, ERROR_DECODE) == [
            "Dirty water tank full — empty it"
        ]

    def test_error_brush_field_value3_blocked(self):
        # Field at bits 4-9, value 3 = roller brush blocked
        assert decode_field_alerts(3 << 4, ERROR_DECODE) == [
            "Roller brush blocked — clean it"
        ]

    def test_unknown_bits_yield_nothing(self):
        # Bit 31 is past every decode table
        assert decode_field_alerts(1 << 31, WARN_DECODE) == []


class TestTableConsistency:
    def test_status_group_codes_are_known_statuses(self):
        assert set(STATUS_GROUP) <= set(DEVICE_STATUS)

    def test_consumable_left_keys_are_known_props(self):
        known = {f"{s}.{p}" for s, p in KNOWN_MQTT_PROPS}
        for meta in CONSUMABLE_SENSORS:
            assert meta["left"] in known, meta["key"]

    def test_consumable_max_keys_derived(self):
        assert CONSUMABLE_MAX_KEYS == [c["max"] for c in CONSUMABLE_SENSORS]

    def test_alert_sensors_reference_warn_or_error_props(self):
        for meta in ALERT_BINARY_SENSORS:
            assert meta["data_key"] in {"4.1", "4.2"}, meta["key"]
            assert isinstance(meta["bit_mask"], int) and meta["bit_mask"] > 0

    def test_meta_keys_are_unique_per_platform(self):
        keys = [m["key"] for m in KNOWN_MQTT_PROPS.values()]
        assert len(keys) == len(set(keys))
