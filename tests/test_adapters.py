from terrasatch_edge.adapters import classify_device
from terrasatch_edge.models import DeviceKind, HardwareDevice


def test_nooelec_is_classified_as_sdr():
    device = HardwareDevice(
        kind=DeviceKind.USB,
        name="Nooelec NESDR SMArt",
        identifier="usb:0bda:2838",
    )
    result = classify_device(device)
    assert result.kind == DeviceKind.SDR
    assert "radio_rx" in result.capabilities
    assert "radio:receive" in result.capabilities
    assert "radio:rx" in result.capabilities
    assert "rtl-sdr" in result.capabilities
    assert "nooelec" in result.capabilities


def test_hackrf_reports_receive_and_transmit_policy_capabilities():
    device = HardwareDevice(
        kind=DeviceKind.USB,
        name="HackRF One",
        identifier="usb:hackrf",
    )
    result = classify_device(device)
    assert result.kind == DeviceKind.SDR
    assert "radio_rx" in result.capabilities
    assert "radio_tx" in result.capabilities
    assert "radio:receive" in result.capabilities
    assert "radio:transmit" in result.capabilities
    assert "radio:tx" in result.capabilities


def test_gps_is_classified():
    device = HardwareDevice(
        kind=DeviceKind.SERIAL,
        name="u-blox GNSS receiver",
        identifier="COM5",
    )
    result = classify_device(device)
    assert result.kind == DeviceKind.GPS
    assert "position" in result.capabilities
