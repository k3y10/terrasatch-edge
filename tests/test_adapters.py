from terrasatch_edge.adapters import classify_device
from terrasatch_edge.models import DeviceKind, HardwareDevice


def test_nooelec_is_classified_as_sdr_without_claiming_runtime_readiness():
    device = HardwareDevice(
        kind=DeviceKind.USB,
        name="Nooelec NESDR SMArt",
        identifier="usb:0bda:2838",
    )
    result = classify_device(device)
    assert result.kind == DeviceKind.SDR
    assert "rtl-sdr" in result.capabilities
    assert "nooelec" in result.capabilities
    assert "iq_stream" in result.capabilities
    assert "radio:receive" not in result.capabilities


def test_hackrf_is_discovery_only_until_provider_adapter_exists():
    device = HardwareDevice(
        kind=DeviceKind.USB,
        name="HackRF One",
        identifier="usb:hackrf",
    )
    result = classify_device(device)
    assert result.kind == DeviceKind.SDR
    assert "hardware:hackrf" in result.capabilities
    assert "hackrf" in result.capabilities
    assert "radio:receive" not in result.capabilities
    assert "radio:transmit" not in result.capabilities
    assert "radio:tx" not in result.capabilities


def test_gps_is_classified():
    device = HardwareDevice(
        kind=DeviceKind.SERIAL,
        name="u-blox GNSS receiver",
        identifier="COM5",
    )
    result = classify_device(device)
    assert result.kind == DeviceKind.GPS
    assert "position" in result.capabilities
