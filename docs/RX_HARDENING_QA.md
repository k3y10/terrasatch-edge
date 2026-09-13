# RX hardening validation — 2026-09-12/13

## Architecture and scope

BCA/FRS channels, manual frequencies, organization targets and explicitly admitted repeater
outputs resolve to a validated `RadioTarget`. The RTL receive provider creates the controlled
capture process; the existing PCM gate, calibration, segmentation, speech/VAD validation,
Faster Whisper and durable SQLite outbox feed the authenticated transmission API.

Nooelec NESDR SMArt v5 remains receive-only: `radio:receive` and `audio:capture` when the
runtime is available. Directory metadata grants neither receive admission nor TX permission.
TX execution, approval gates and capability models were not expanded.

## Branch review

Both branches started from fetched authoritative main, and main was fetched again before
commit preparation. Edge base: `b98d25e2fe1fe976b4ffeadd553cf85cd84d4491`.
API base: `0738be2cae25fe45615ddd83f32a308a83f69597`.
Reviewed all remote branches and the 12 Edge / 38 API PR records. No open prerequisite PRs.
The only unique old Edge pilot commit was macOS-specific; it was not merged.
Unrelated API natural-radio-addressing work was not incorporated. No branches deleted.

## Software QA

Windows 11 x64, Python 3.12.14 QA environment, all existing gates unchanged:

| Check | Result |
| --- | --- |
| Complete Edge regression suite | 301 passed |
| Edge speech/ingest/config coverage, minimum 75% | 85.16% |
| Edge command/TX coverage, minimum 90% | 91.41% |
| Additional targets/scanner/directory/lock/provider coverage | 90.31% |
| Complete API suite | 205 passed |
| API intelligence/schema coverage, minimum 80% | 92.70% |
| API command lifecycle coverage, minimum 80% | 86.26% |
| Actual Edge/API compatibility suite | 6 passed |
| Ruff, compile/import checks, pip dependency consistency | Passed |
| API migration head/OpenAPI/deterministic fallback checks | Passed |

Coverage percentages describe their named module groups, not full-repository coverage.
The joint tests exercise authenticated config retrieval, Edge target resolution, SQLite
outbox serialization, real API ingestion, duplicate suppression and stored RF metadata/site
identity. They include four existing TX scenarios and two generalized RX scenarios, using
the repository's local SQLite API fixture rather than production services.

Two Edge warnings are upstream FastAPI/Starlette deprecations. Joint tests also report
Starlette warnings about the existing TestClient timeout argument. They do not indicate failed assertions.
QA uses isolated state and local endpoints with production credentials removed.

## Native builds and platform status

Windows: native PyInstaller and unsigned Inno Setup installer build succeeded with the
complete RTL runtime (Python 3.12.10 build environment). Required tools also passed launch checks using an isolated PATH. Bundled runtime resolution and NESDR detection tested on Windows 11.
The unsigned installer is a local QA artifact; signing/release publication is not performed.
The final frozen CLI also preserved configuration exit 2 without opening a receiver.
The installed production Edge service was left running. New radio SCM installation,
automatic startup after reboot and independent SCM restart remain field checks.

Linux: Ubuntu 22.04 WSL amd64 native PyInstaller/`.deb` build succeeded. The full native
QA script (including speech runtime import) passed 301 tests; speech/ingest/config coverage
was 84.34% (minimum 75%) and TX coverage 91.41% (minimum 90%). An isolated Debian 13
container verified package installation, repeated installation/upgrade, removal, config
preservation, CLI commands, systemd unit syntax and explicit radio enablement. The runtime
worked with Debian's optional `rtl-sdr` package and failed clearly when no USB device existed.
The container did not run systemd as PID 1: real service execution, reboot and Linux USB/RF
behavior remain unverified. The native unit uses `/usr/local/bin/terrasatch-edge`,
`/etc/terrasatch-edge` and `/var/lib/terrasatch-edge`, with an independent journal/restart
lifecycle. A separate user unit preserves the development venv layout.

Raspberry Pi: shares the ARM64 Linux architecture. ARM64 build/installation and physical
Pi testing remain outstanding; see the native build guide for udev/plugdev, USB power and
kernel-driver considerations. macOS is deferred and was not a release gate.

## Physical receiver evidence

A connected NESDR SMArt v5 was detected on Windows. `rtl_test -t` returned exit zero and
identified the R820T tuner, but printed an E4000-only test message and PLL warning; this
is detection/runtime evidence, not proof of successful RF reception.

The first final-artifact check exposed a pre-existing staging gap: `rtl_sdr`'s DLL list
omitted `rtl_fm`'s `libwinpthread-1.dll`. Staging now inspects every utility and the build
rejects executables that cannot launch without a developer MSYS2 PATH.

With the corrected runtime, a 10-second native 462.650 MHz NFM probe completed and
observed 147 PCM chunks, peak RMS 6954 and PCM floor 6296. It reported activity, which
can include noise and is not proof of intelligible speech or calibrated RF strength.
A controlled 10-second continuous receiver/service smoke exited STOPPED with no receiver
error, no live worker threads and no retained audio/outbox entries. Its STT collaborator
was a local stub and no production API calls were made. The normal Windows Edge service
remained running; a new heartbeat upload was not independently verified.

Actual intelligible RF speech, live Faster Whisper recognition of that speech, production
API ingestion, unplug/reconnect behavior, reboot survival and sustained field operation
remain unverified. Automatic hotplug recovery is not claimed.

## Commands and compatibility

```console
terrasatch-edge doctor
terrasatch-edge radio devices
terrasatch-edge radio targets
terrasatch-edge radio discover --latitude 40.62 --longitude -111.81 --radius 75 --provider open-repeater
terrasatch-edge radio probe --frequency 462.650M --seconds 10
terrasatch-edge radio start --frequency 462.650M --modulation nfm
terrasatch-edge radio start --channel 19
terrasatch-edge radio scan --dwell 2
terrasatch-edge radio status
terrasatch-edge radio stop
```

Discovery needs an operator API key and explicit configured/CLI location. Manual targets
require neither. Configure a target before explicitly enabling automatic service startup.

`setup`, `doctor`, `radio-channels`, `listen-radio --channel 5 --once`,
`radio start --channel 5`, `radio status` and `radio stop` remain available. All 22 BCA
mappings are tested; channel 19 and direct 462.650 MHz use the same receive pipeline.

## Remaining limitations

- One active receiver. Scan is sequential with bounded holds and can miss partial calls;
  continuous reception is preferable for a critical carrier.
- Shared state directory is required for cooperating Edge receiver locks. Do not point
  independent installations with different state directories at one SDR.
- Normal tuner support is 25–1750 MHz; no HF direct sampling, digital decoding or wideband sweep.
- No RF-calibrated RSSI/SNR, CTCSS/DCS detection, inferred transmitter location or TX permission.
- Remote configuration is read when the radio monitor starts; restart to apply changes.
- Open Repeater integration is optional and mock-tested against its public documentation;
  live authenticated response/envelope and directory accuracy need operator verification.
- Windows service enablement is explicit; upgrades preserve SCM startup mode but leave
  radio monitoring stopped until the operator restarts it.
- Physical Windows/Linux/Pi tests described above are still required before a field release.
