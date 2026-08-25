from __future__ import annotations

from terrasatch_edge.radio_cli import _radio_source


def test_radio_source_preserves_channel_label() -> None:
    assert _radio_source("terrasatch-edge", 5) == "terrasatch-edge-radio-bca-ch05"


def test_radio_source_stays_within_api_limit() -> None:
    value = _radio_source("x" * 200, 22)
    assert len(value) <= 64
    assert value.endswith("-radio-bca-ch22")
