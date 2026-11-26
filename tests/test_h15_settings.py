"""H15 writes must follow app enums, coupled settings and inverted bitfields."""
import pytest

from custom_components.dreame_wet_dry_vacuum.const import (
    H15_CONTROL_KEYS,
    build_h15_write_plan,
)


@pytest.mark.parametrize("key,value", [
    ((16, 7), 2), ((16, 2), 1), ((1, 8), 5), ((1, 10), 2),
    ((23, 1), 3), ((26, 3), 1), ((1, 14), 101), ((1, 14), -1),
    ((1, 28), 4), ((3, 1), 50), ((1, 17), 1), ((100, 1), 1),
])
def test_unmapped_or_unsupported_setting_is_not_written(key, value):
    with pytest.raises(ValueError):
        build_h15_write_plan(key, value, {})


@pytest.mark.parametrize("value", [0, 60])
def test_volume_range_includes_mute_and_full(value):
    assert build_h15_write_plan((1, 14), value, {}) == {(1, 14): value}


def test_custom_water_change_preserves_suction_and_enables_custom_mode():
    plan = build_h15_write_plan((16, 2), 3, {(16, 1): 2, (16, 8): 0})
    assert plan == {(16, 1): 2, (16, 2): 3, (16, 7): 4, (16, 6): 1}


def test_hot_water_forces_gentle_suction_and_preserves_water():
    plan = build_h15_write_plan((16, 8), 3, {(16, 1): 3, (16, 2): 3})
    assert plan == {(16, 1): 1, (16, 2): 3, (16, 7): 4, (16, 6): 1, (16, 8): 3}
    assert build_h15_write_plan((16, 8), 0, {}) == {(16, 8): 0}


@pytest.mark.parametrize("key,value", [((16, 1), 3)])
def test_incompatible_suction_or_preset_is_rejected_while_hot(key, value):
    with pytest.raises(ValueError):
        build_h15_write_plan(key, value, {(16, 8): 1})


@pytest.mark.parametrize("mode,power,water", [(1, 1, 2), (3, 3, 3), (4, 2, 2)])
def test_cleaning_preset_sets_matching_power_and_water(mode, power, water):
    assert build_h15_write_plan((16, 7), mode, {(16, 8): 0}) == {
        (16, 7): mode, (16, 1): power, (16, 2): water, (16, 6): 1,
    }


@pytest.mark.parametrize("key,value", [((1, 8), 3), ((1, 10), 3), ((1, 81), 3), ((1, 82), 3)])
def test_wash_dry_preferences_preserve_companion_in_complete_app_batch(key, value):
    props = {(1, 8): 2, (1, 10): 1, (1, 81): 2, (1, 82): 1}
    wash, dry = (value, 1) if key[1] in (8, 81) else (2, value)
    assert build_h15_write_plan(key, value, props) == {
        (1, 8): wash, (1, 10): dry, (1, 81): wash,
        (1, 82): dry, (1, 75): wash, (1, 83): dry,
    }


def test_wash_dry_never_guesses_missing_companion():
    with pytest.raises(ValueError):
        build_h15_write_plan((1, 10), 3, {})


@pytest.mark.parametrize("mode,power,water", [(1, 1, 2), (3, 3, 3), (4, 1, 2)])
def test_hot_water_does_not_prevent_app_preset_selection(mode, power, water):
    plan = build_h15_write_plan((16, 7), mode, {(16, 8): 1})
    assert plan == {(16, 7): mode, (16, 1): power, (16, 2): water, (16, 6): 1}


def test_arm_mode_change_preserves_other_modes_and_unused_bit():
    # 2: all four modes selected, unused bit1 set. Disable Smart only.
    assert build_h15_write_plan((24, 1), 0, {(24, 1): 2}, arm_bit=0) == {(24, 1): 3}
    # Re-enable Smart while Suction remains off (bit2=1).
    assert build_h15_write_plan((24, 1), 1, {(24, 1): 7}, arm_bit=0) == {(24, 1): 6}


@pytest.mark.parametrize("props", [{}, {(24, 1): -1}, {(24, 1): 32}])
def test_arm_never_overwrites_unknown_state(props):
    with pytest.raises(ValueError):
        build_h15_write_plan((24, 1), 1, props, arm_bit=0)


def test_missing_custom_setting_dependency_is_not_invented():
    with pytest.raises(ValueError):
        build_h15_write_plan((16, 1), 3, {})
    assert (1, 28) not in H15_CONTROL_KEYS
    assert (3, 1) not in H15_CONTROL_KEYS

from custom_components.dreame_wet_dry_vacuum.const import (
    H15_ERROR_FIELDS,
    H15_WARN_FIELDS,
    build_h15_command_plan,
    build_schedule_day_plan,
    decode_h15_alerts,
    decode_schedule,
)


@pytest.mark.parametrize('mode,command', [(2, 2), (3, 3), (4, 4)])
def test_self_clean_start_uses_selected_app_mode(mode, command):
    assert build_h15_command_plan('start_self_clean', {(1, 28): 7, (3, 1): 100, (1, 8): mode}) == {(1, 1): command}


@pytest.mark.parametrize('mode,command', [(1, 1), (3, 4)])
def test_dry_command_differs_from_super_speed_setting(mode, command):
    assert build_h15_command_plan('start_self_dry', {(1, 28): 4, (1, 10): mode}) == {(1, 2): command}


@pytest.mark.parametrize('command,props', [
    ('start_self_clean', {(1, 28): 16, (3, 1): 100, (1, 8): 4}),
    ('start_self_clean', {(1, 28): 7, (3, 1): 19, (1, 8): 4}),
    ('start_self_dry', {(1, 28): 28, (1, 10): 1}),
    ('resume_self_clean', {(1, 28): 7}),
    ('stop_self_dry', {(1, 28): 7}),
    ('reset_filter', {(19, 3): -1}),
    ('reset_back_brush', {(7, 7): -1}),
    ('move_forward', {(10, 1): 1}),
    ('reset_clean_water', {}),
])
def test_commands_reject_unknown_or_wrong_state(command, props):
    with pytest.raises(ValueError):
        build_h15_command_plan(command, props)


@pytest.mark.parametrize('command,key,remaining', [
    ('reset_front_brush', (6, 1), (6, 7)),
    ('reset_back_brush', (7, 1), (7, 7)),
    ('reset_filter', (19, 1), (19, 3)),
])
def test_reset_is_a_device_command_not_a_sensor_overwrite(command, key, remaining):
    assert build_h15_command_plan(command, {remaining: 100}) == {key: 1}


def test_schedule_encoding_matches_app_order_and_time_preservation():
    assert decode_schedule(11111)['days'] == [1, 2, 3, 4, 5]
    assert decode_schedule(1100000)['days'] == [0, 6]
    assert decode_schedule(10000000) == {'enabled': True, 'once': True, 'days': []}
    assert build_schedule_day_plan(0, True, {(1, 77): 11111, (1, 76): 7200}) == {(1, 77): 1011111, (1, 76): 7200}
    assert build_schedule_day_plan(1, False, {(1, 77): 1011111, (1, 76): 7200}) == {(1, 77): 1011110, (1, 76): 7200}


@pytest.mark.parametrize('raw', [-1, None, 2, 2222222, 11111112, True])
def test_schedule_rejects_unknown_decimal_digits(raw):
    with pytest.raises(ValueError):
        decode_schedule(raw)


def test_schedule_can_initialize_time_without_fabricating_repeat():
    assert build_h15_write_plan((1, 76), 7200, {}) == {(1, 76): 7200}
    with pytest.raises(ValueError, match='scheduled time'):
        build_h15_write_plan((1, 77), 1111111, {})
    assert build_h15_write_plan((1, 77), 1111111, {(1, 76): 7200}) == {(1, 77): 1111111, (1, 76): 7200}


def test_h15_warn_multibit_field_requires_app_value_three():
    assert decode_h15_alerts(4, H15_WARN_FIELDS) == []
    assert decode_h15_alerts(8, H15_WARN_FIELDS) == []
    assert decode_h15_alerts(12, H15_WARN_FIELDS) == ['Self-cleaning recommended']
    assert decode_h15_alerts(1 | 256, H15_WARN_FIELDS) == ['Clean water tank empty', 'Dirty water tank needs cleaning']


@pytest.mark.parametrize('field', [3, 7, 23, 27, 43, 47])
def test_roller_fault_matches_exact_multibit_error_field(field):
    assert decode_h15_alerts(field << 4, H15_ERROR_FIELDS) == ['Roller brush blocked']
    assert decode_h15_alerts(1 << 4, H15_ERROR_FIELDS) == ['Roller brush missing']


def test_js_integer_key_order_preserves_high_error_bits():
    assert decode_h15_alerts(1 << 23, H15_ERROR_FIELDS) == ['Clean water tank empty']
    assert decode_h15_alerts(1 << 24, H15_ERROR_FIELDS) == ['Vacuum tube blocked']
    assert decode_h15_alerts(1 << 28, H15_ERROR_FIELDS) == ['Dirty water tank blocked']
    assert decode_h15_alerts(1 << 12, H15_ERROR_FIELDS) == ['Dirty water tank full']
    assert decode_h15_alerts(-1, H15_ERROR_FIELDS) is None


def test_voice_list_and_volume_match_h15_resource_selection():
    from custom_components.dreame_wet_dry_vacuum.const import H15_SELECT_SETTINGS
    assert H15_SELECT_SETTINGS[(1, 17)] == {2: 'English', 3: 'German', 4: 'French', 6: 'Italian', 7: 'Spanish', 16: 'Dutch', 17: 'Portuguese'}
    assert build_h15_write_plan((1, 17), 2, {}) == {(1, 17): 2}
    assert build_h15_write_plan((1, 14), 30, {}) == {(1, 14): 30}
    with pytest.raises(ValueError):
        build_h15_write_plan((1, 14), 100, {})


def test_legacy_h14_tables_still_match_previous_release():
    import hashlib

    from custom_components.dreame_wet_dry_vacuum import const
    names = ['DEVICE_STATUS', 'STATUS_GROUP', 'KNOWN_MQTT_PROPS', 'CONSUMABLE_SENSORS', 'WARN_DECODE', 'ERROR_DECODE', 'ALERT_BINARY_SENSORS', 'KNOWN_BINARY_PROPS', 'KNOWN_SWITCH_PROPS', 'KNOWN_NUMBER_PROPS', 'KNOWN_SELECT_PROPS', 'KNOWN_BUTTON_PROPS']
    payload = repr([getattr(const, name) for name in names])
    assert hashlib.sha256(payload.encode()).hexdigest() == '84eae2da91988d080a62f03367e61ac861a6fbe51e789227b1aa93c813aa8f38'


@pytest.mark.parametrize("key,value,companion,current", [
    ((1, 75), 4, (1, 83), 1), ((1, 83), 3, (1, 75), 2),
])
def test_scheduled_modes_preserve_companion_without_overwriting_manual_modes(key, value, companion, current):
    assert build_h15_write_plan(key, value, {companion: current}) == {key: value, companion: current}


def test_arm_select_preserves_reserved_bit_for_every_combination():
    from custom_components.dreame_wet_dry_vacuum.const import H15_SELECT_SETTINGS
    options = H15_SELECT_SETTINGS[(24, 1)]
    assert len(options) == 16
    assert options[0] == 'All modes'
    assert options[29] == 'None'
    for raw in options:
        assert build_h15_write_plan((24, 1), raw, {(24, 1): 2}) == {(24, 1): raw | 2}
    with pytest.raises(ValueError):
        build_h15_write_plan((24, 1), 0, {})


def test_start_self_clean_without_reported_mode_uses_app_auto_adjust():
    """The app starts with the selected wash mode; unknown mode falls back to Auto-Adjust (4)."""
    assert build_h15_command_plan('start_self_clean', {(1, 28): 7, (3, 1): 100}) == {(1, 1): 4}
