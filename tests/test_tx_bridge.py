import json
import os
import subprocess
import sys

import pytest

from terrasatch_edge.radio_providers import RadioReply
from terrasatch_edge.tx_bridge import ExternalRadioTxProvider


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    # POSIX can execute the shebang fixture directly. Windows intentionally
    # requires a native executable for real providers, so use an .exe-shaped
    # placeholder there and mock only the process boundary in the round-trip
    # test below. This keeps the production shell=False/native-executable
    # safety contract unchanged.
    path = tmp_path / ("bridge.exe" if os.name == "nt" else "bridge")
    path.write_text(
        f"#!{sys.executable}\n"
        + """import json, os, sys
assert 'TERRASATCH_EDGE_API_KEY' not in os.environ
request = json.load(sys.stdin)
assert request['protocol_version'] == 1
if request['operation'] == 'status':
    response = {'protocol_version': 1, 'ready': True, 'simulated': False, 'device_id': 'tx-1',
                'capabilities': ['radio:transmit', 'radio:ptt', 'audio:output', 'radio:half_duplex'],
                'rx_coordination': 'independent', 'watchdog': True}
else:
    assert request['operation'] == 'transmit'
    assert request['reply']['max_seconds'] == 1
    response = {'protocol_version': 1, 'command_id': request['reply']['command_id'],
                'status': 'transmitted', 'ptt_released': True, 'rx_restored': True}
json.dump(response, sys.stdout)
"""
    )
    path.chmod(0o700)
    monkeypatch.setenv("TERRASATCH_EDGE_API_KEY", "must-not-reach-provider")
    return ExternalRadioTxProvider(str(path))


def test_local_executable_protocol_round_trip_and_secret_isolation(bridge, monkeypatch):
    if os.name == "nt":
        def fake_run(args, **kwargs):
            assert args == [str(bridge.executable)]
            assert kwargs["capture_output"] is True
            assert kwargs["text"] is True
            assert kwargs["check"] is True
            assert "TERRASATCH_EDGE_API_KEY" not in kwargs["env"]

            request = json.loads(kwargs["input"])
            assert request["protocol_version"] == 1
            if request["operation"] == "status":
                response = {
                    "protocol_version": 1,
                    "ready": True,
                    "simulated": False,
                    "device_id": "tx-1",
                    "capabilities": [
                        "radio:transmit",
                        "radio:ptt",
                        "audio:output",
                        "radio:half_duplex",
                    ],
                    "rx_coordination": "independent",
                    "watchdog": True,
                }
            else:
                assert request["operation"] == "transmit"
                assert request["reply"]["max_seconds"] == 1
                response = {
                    "protocol_version": 1,
                    "command_id": request["reply"]["command_id"],
                    "status": "transmitted",
                    "ptt_released": True,
                    "rx_restored": True,
                }

            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=json.dumps(response),
                stderr="",
            )

        monkeypatch.setattr("terrasatch_edge.tx_bridge.subprocess.run", fake_run)

    assert bridge.status().ready
    bridge.transmit(RadioReply("command", "Control 2, Satchy.", "logical", "ops-5", 462662500, 1))


@pytest.mark.parametrize(
    "patch",
    [
        {"watchdog": False},
        {"rx_coordination": None},
        {"device_id": ""},
        {"capabilities": ["radio:ptt"]},
        {"simulated": True},
    ],
)
def test_incomplete_or_simulation_bridge_cannot_advertise_tx(bridge, monkeypatch, patch):
    status = {
        "protocol_version": 1,
        "ready": True,
        "simulated": False,
        "device_id": "tx-1",
        "capabilities": ["radio:transmit", "radio:ptt", "audio:output", "radio:half_duplex"],
        "rx_coordination": "independent",
        "watchdog": True,
        **patch,
    }
    monkeypatch.setattr(bridge, "_call", lambda *args: status)
    assert not bridge.status().reported_capabilities()


def test_missing_ptt_cleanup_is_not_reported_as_success(bridge, monkeypatch):
    monkeypatch.setattr(
        bridge,
        "_call",
        lambda *args: {
            "protocol_version": 1,
            "command_id": "command",
            "status": "transmitted",
            "rx_restored": True,
        },
    )
    with pytest.raises(RuntimeError, match="cleanup"):
        bridge.transmit(RadioReply("command", "text", "logical", "ops", 462662500, 1))


def test_relative_executable_is_rejected():
    with pytest.raises(ValueError):
        ExternalRadioTxProvider("provider.exe")
