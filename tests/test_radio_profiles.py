from __future__ import annotations

import pytest

from terrasatch_edge.radio_profiles import BCA_FRS_NA_PROFILE, bca_frs_channel, bca_frs_channels


def test_bca_channel_table_has_all_22_standard_carriers() -> None:
    channels = bca_frs_channels()
    assert len(channels) == 22
    assert channels[0].frequency_hz == 462_562_500
    assert channels[4].frequency_hz == 462_662_500
    assert channels[7].frequency_hz == 467_562_500
    assert channels[14].frequency_hz == 462_550_000
    assert channels[-1].frequency_hz == 462_725_000
    assert all(item.profile == BCA_FRS_NA_PROFILE for item in channels)


def test_bca_channel_display_name_keeps_channel_and_frequency() -> None:
    profile = bca_frs_channel(5)
    assert profile.display_name == "BCA/FRS CH 5 · 462.6625 MHz"


@pytest.mark.parametrize("channel", [0, 23, -1, 100])
def test_invalid_bca_channel_is_rejected(channel: int) -> None:
    with pytest.raises(ValueError, match="1 and 22"):
        bca_frs_channel(channel)
