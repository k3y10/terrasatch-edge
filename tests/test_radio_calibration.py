from __future__ import annotations

from terrasatch_edge.radio_calibration import RadioNoiseSample, auto_calibrate_radio
from terrasatch_edge.radio_receiver import RadioReceiveSettings


def test_calibration_selects_lowest_quiet_squelch_at_preferred_gain() -> None:
    seen: list[tuple[float | None, int]] = []

    def probe(settings: RadioReceiveSettings) -> RadioNoiseSample:
        seen.append((settings.gain_db, settings.rtl_squelch))
        level = 0 if settings.rtl_squelch >= 60 else 1_200
        return RadioNoiseSample((level, level, level))

    result = auto_calibrate_radio(
        RadioReceiveSettings(channel=5),
        gain_candidates=(19.7, 12.5),
        squelch_candidates=(30, 40, 50, 60, 70, 80),
        noise_probe=probe,
    )

    assert result.mode == "auto"
    assert result.settings.gain_db == 19.7
    assert result.settings.rtl_squelch == 60
    assert result.noise_floor_rms == 0
    assert result.activity_rms_threshold == 180
    assert result.release_rms_threshold == 120
    assert result.attempts == len(seen)


def test_calibration_uses_pcm_floor_when_rtl_squelch_never_closes() -> None:
    def probe(settings: RadioReceiveSettings) -> RadioNoiseSample:
        assert settings.gain_db is not None
        level = int(settings.gain_db * 100) + (100 - settings.rtl_squelch)
        return RadioNoiseSample((level - 20, level, level + 20))

    result = auto_calibrate_radio(
        RadioReceiveSettings(channel=5),
        gain_candidates=(19.7, 7.7),
        squelch_candidates=(30, 60, 90),
        quiet_rms=0,
        noise_probe=probe,
    )

    assert result.mode == "adaptive-rms"
    assert result.settings.gain_db == 7.7
    assert result.settings.rtl_squelch == 90
    assert result.noise_floor_rms == 800
    assert result.activity_rms_threshold == 920
    assert result.release_rms_threshold == 860


def test_fixed_tuning_is_preserved_while_pcm_gate_is_calibrated() -> None:
    result = auto_calibrate_radio(
        RadioReceiveSettings(channel=5),
        fixed_gain_db=28.0,
        fixed_squelch=45,
        noise_probe=lambda _settings: RadioNoiseSample((200, 240, 220)),
    )

    assert result.settings.gain_db == 28.0
    assert result.settings.rtl_squelch == 45
    assert result.noise_floor_rms == 240
    assert result.activity_rms_threshold == 360
    assert result.release_rms_threshold == 300
    assert result.attempts == 1
