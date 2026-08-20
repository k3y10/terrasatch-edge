from __future__ import annotations

import pytest

from terrasatch_edge.radio_calibration import RadioCalibrationError, auto_calibrate_radio
from terrasatch_edge.radio_receiver import RadioReceiveSettings


def test_auto_calibration_prefers_moderate_gain_with_quiet_threshold() -> None:
    # 19.7 dB needs the maximum squelch, while 12.5 dB closes cleanly at 80.
    floors = {19.7: 95, 12.5: 75, 7.7: 65, 0.0: 55}

    def probe(settings: RadioReceiveSettings) -> bool:
        assert settings.gain_db is not None
        return settings.rtl_squelch <= floors[settings.gain_db]

    result = auto_calibrate_radio(RadioReceiveSettings(channel=5), activity_probe=probe)

    assert result.mode == "auto"
    assert result.gain_db == 12.5
    assert result.squelch == 80
    assert result.attempts > 0


def test_auto_calibration_finds_gain_when_squelch_is_fixed() -> None:
    def probe(settings: RadioReceiveSettings) -> bool:
        assert settings.gain_db is not None
        return settings.gain_db > 7.7

    result = auto_calibrate_radio(
        RadioReceiveSettings(channel=5),
        fixed_squelch=80,
        activity_probe=probe,
    )

    assert result.mode == "auto-gain"
    assert result.gain_db == 7.7
    assert result.squelch == 80


def test_manual_gain_and_squelch_skip_rf_probe() -> None:
    def unexpected_probe(settings: RadioReceiveSettings) -> bool:
        raise AssertionError(f"probe should not run: {settings}")

    result = auto_calibrate_radio(
        RadioReceiveSettings(channel=5),
        fixed_squelch=80,
        fixed_gain_db=0,
        activity_probe=unexpected_probe,
    )

    assert result.mode == "manual"
    assert result.attempts == 0
    assert result.gain_db == 0
    assert result.squelch == 80


def test_auto_calibration_keeps_safe_fallback_at_squelch_100() -> None:
    def probe(settings: RadioReceiveSettings) -> bool:
        return settings.rtl_squelch < 100

    result = auto_calibrate_radio(
        RadioReceiveSettings(channel=5),
        gain_candidates=(12.5, 0),
        activity_probe=probe,
    )

    assert result.gain_db == 12.5
    assert result.squelch == 100


def test_auto_calibration_raises_when_channel_never_closes() -> None:
    with pytest.raises(RadioCalibrationError, match="quiet RF baseline"):
        auto_calibrate_radio(
            RadioReceiveSettings(channel=5),
            activity_probe=lambda settings: True,
        )
