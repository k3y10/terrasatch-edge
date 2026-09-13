import io
import queue
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from terrasatch_edge.config import EdgeConfig
from terrasatch_edge.radio_calibration import RadioNoiseSample
from terrasatch_edge.radio_lock import ReceiverLock
from terrasatch_edge.radio_receiver import RadioReceiveSettings, _pump_pcm
from terrasatch_edge.radio_scanner import ScanningReceiver
from terrasatch_edge.radio_service import RadioMonitorService, resolve_radio_config
from terrasatch_edge.radio_targets import direct_target


def test_receiver_lock_excludes_another_process_and_releases(tmp_path):
    code = "from pathlib import Path; from terrasatch_edge.radio_lock import ReceiverLock; import sys; lease=ReceiverLock(root=Path(sys.argv[1])); lease.__enter__(); lease.__exit__()"
    with ReceiverLock(root=tmp_path):
        result = subprocess.run([sys.executable, "-c", code, str(tmp_path)], capture_output=True, timeout=10)
        assert result.returncode != 0
        assert b"already in use" in result.stderr
    assert subprocess.run([sys.executable, "-c", code, str(tmp_path)], capture_output=True, timeout=10).returncode == 0


def test_full_pcm_queue_cancels_without_leaking_reader_thread():
    done = threading.Event()
    chunks = queue.Queue(maxsize=1)
    reader = threading.Thread(target=_pump_pcm, args=(io.BytesIO(b"1" * 100000), chunks, 100, done))
    reader.start()
    done.set()
    reader.join(timeout=2)
    assert not reader.is_alive()


def test_scan_tunes_in_order_holds_activity_and_cleans_up():
    stop = threading.Event()
    targets = [direct_target("462.650M"), direct_target("462.675M")]
    tuned, closed, states = [], [], []
    def probe(settings, *, probe_seconds, stop_event):
        assert probe_seconds == 0.5
        tuned.append(settings.profile.frequency_hz)
        return RadioNoiseSample((0,)) if len(tuned) == 1 else RadioNoiseSample((1000,))
    class Receiver:
        def __init__(self, settings, **kwargs):
            self.target = settings.profile
        def captures(self, event):
            try:
                yield self.target
                stop.set()
            finally:
                closed.append(True)
    receiver = ScanningReceiver(RadioReceiveSettings(target=targets[0]), targets, lambda: Path("unused"),
                                None, dwell=0.5, probe=probe, receiver_type=Receiver,
                                on_state=lambda state, target: states.append(state))
    assert list(receiver.captures(stop)) == [targets[1]]
    assert tuned == [462650000, 462675000]
    assert closed == [True]
    assert states == ["SCANNING", "SCANNING", "MONITORING"]


def test_scan_cancel_during_probe_never_starts_monitor():
    stop = threading.Event()
    target = direct_target("462.650M")
    def probe(settings, **kwargs):
        stop.set()
        return RadioNoiseSample((1000,))
    scanner = ScanningReceiver(RadioReceiveSettings(target=target), [target], lambda: None, None, probe=probe)
    assert list(scanner.captures(stop)) == []


def test_scan_rejects_disabled_unbounded_or_unsupported_targets():
    target = direct_target("462.650M")
    for targets, dwell in [([], 2), ([target], 60), ([target.model_copy(update={"enabled": False})], 2),
                           ([direct_target("2M")], 2)]:
        with pytest.raises(ValueError):
            ScanningReceiver(RadioReceiveSettings(target=target), targets, lambda: None, None, dwell=dwell)


def test_receiver_failure_returns_failure_to_supervisor_and_unlocks(tmp_path):
    class Receiver:
        def captures(self, stop_event):
            raise RuntimeError("USB removed")
            yield
    edge = EdgeConfig(site_id="paired", radio_channel=19)
    config = resolve_radio_config(edge).config
    service = RadioMonitorService(edge_config=edge, monitor_config=config, provider=None, client=None,
                                  receiver_factory=lambda *args: Receiver(), state_dir=tmp_path)
    with pytest.raises(RuntimeError, match="USB removed"):
        service.run_forever(install_signal_handlers=False)
    assert all(not thread.is_alive() for thread in service._threads)
    with ReceiverLock(root=tmp_path / "radio-locks", name="monitor.lock"):
        pass


def test_independent_native_service_and_packaging_contracts():
    root = Path(__file__).resolve().parents[1]
    unit = (root / "deploy/systemd/terrasatch-radio.service").read_text()
    assert "ExecStart=/usr/local/bin/terrasatch-edge radio start" in unit
    assert "/etc/terrasatch-edge" in unit and "/var/lib/terrasatch-edge" in unit
    assert "%h" not in unit and "venv" not in unit
    assert "KillMode=control-group" in unit and "Restart=on-failure" in unit
    assert "WantedBy=multi-user.target" in unit
    assert "%h/.local" in (root / "deploy/systemd/user/terrasatch-radio.service").read_text()
    package = (root / "scripts/build-linux-deb.sh").read_text()
    assert 'cp deploy/systemd/terrasatch-radio.service' in package
    assert "Recommends: rtl-sdr" in package
    assert "systemctl stop terrasatch-radio.service" in package
    from xml.etree import ElementTree
    xml = ElementTree.parse(root / "packaging/windows/TerraSatchRadioService.xml").getroot()
    assert xml.findtext("id") == "TerraSatchRadio"
    assert xml.findtext("arguments") == "radio start"
    assert xml.findtext("stoparguments") == "radio stop"
    assert xml.findtext("startmode") == "Manual"
    assert xml.find("onfailure").get("action") == "restart"
    assert xml.find("env[@name='PYTHONIOENCODING']").get("value") == "utf-8"
    setup = (root / "packaging/windows/TerraSatchRadioServiceSetup.ps1").read_text()
    assert "$Wrapper start" not in setup
    build = (root / "scripts/build-windows.ps1").read_text()
    assert '@("rtl_sdr.exe", "rtl_fm.exe", "rtl_test.exe")' in build
    installer = (root / "packaging/windows/TerraSatchEdge.iss").read_text()
    assert 'DestName: "TerraSatchRadioService.exe"' in installer
    assert 'RunOnceId: "RemoveTerraSatchRadio"' in installer


def test_rx_provider_never_advertises_tx(monkeypatch):
    from terrasatch_edge.radio_rx_provider import RtlRxProvider
    monkeypatch.setattr("terrasatch_edge.radio_rx_provider.find_executable", lambda name: Path(name))
    assert RtlRxProvider().status()["capabilities"] == ["radio:receive", "audio:capture"]
    monkeypatch.setattr("terrasatch_edge.radio_rx_provider.find_executable", lambda name: None)
    assert RtlRxProvider().status()["capabilities"] == []


def test_monitor_startup_filesystem_failure_releases_lease(tmp_path, monkeypatch):
    edge = EdgeConfig(site_id="paired", radio_channel=19)
    service = RadioMonitorService(edge_config=edge, monitor_config=resolve_radio_config(edge).config,
                                  provider=None, client=None, state_dir=tmp_path)
    def fail():
        raise OSError("Disk unavailable")
    monkeypatch.setattr(service.qa, "enforce_limits", fail)
    with pytest.raises(OSError, match="Disk unavailable"):
        service.start()
    with ReceiverLock(root=tmp_path / "radio-locks", name="monitor.lock"):
        pass


def test_scan_receiver_setup_failure_cleans_up_watcher():
    before = set(threading.enumerate())
    target = direct_target("462.650M")
    def fail(*args, **kwargs):
        raise RuntimeError("Missing runtime")
    scanner = ScanningReceiver(RadioReceiveSettings(target=target), [target], lambda: None, None,
                               probe=lambda *args, **kwargs: RadioNoiseSample((1000,)), receiver_type=fail)
    with pytest.raises(RuntimeError, match="Missing runtime"):
        list(scanner.captures(threading.Event()))
    assert set(threading.enumerate()) <= before


def test_provider_identity_never_becomes_windows_capture_filename(tmp_path):
    target = direct_target("462.650M").model_copy(update={"id": "provider:external-id"})
    edge = EdgeConfig(site_id="paired", radio={"targets": [target.model_dump()]})
    service = RadioMonitorService(edge_config=edge, monitor_config=resolve_radio_config(edge).config,
                                  provider=None, client=None, state_dir=tmp_path)
    path = service._capture_path()
    assert ":" not in path.name and "provider" not in path.name
    assert path.parent == service.capture_dir
    path.write_bytes(b"audio")
    assert path.read_bytes() == b"audio"
