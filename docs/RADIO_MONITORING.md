# Continuous radio monitoring

TerraSatch Edge vNext keeps the RTL-SDR receiver open while separate local workers validate
audio, transcribe speech, and deliver accepted transmissions. The current release monitors one
configured BCA/FRS carrier. The worker boundaries and remote configuration can represent more
receivers and channels, but simultaneous 462/467 MHz channelization is Phase 2 work.

## Simple demo

```bash
terrasatch-edge setup
terrasatch-edge doctor
terrasatch-edge radio start --channel 5
```

Use another terminal to inspect or stop the foreground monitor:

```bash
terrasatch-edge radio status
terrasatch-edge radio stop
```

The established single-call workflow remains available during validation:

```bash
terrasatch-edge radio-channels
terrasatch-edge listen-radio --channel 5 --once --callsign "BCA TEST"
```

`--hotwords` and `--callsign` bias local transcription. They do not activate the receiver and
their absence never invalidates otherwise authorized speech.

## Filtering and temporary audio

`rtl_fm` squelch performs the first carrier gate. Edge then enforces minimum/maximum duration and
a conservative PCM peak threshold before writing a temporary WAV. An inexpensive energy voice
check runs before Faster Whisper, whose own VAD remains the higher-quality second check. Carrier
pops, weak candidates, silence, and Faster Whisper's normal “no speech” result are discarded
without creating API transmissions or stopping the receiver.

Temporary WAV files live under the Edge state directory and are deleted after success, rejection,
or processing failure. Set `radio.qa.enabled` only during field tuning. QA retention is always
bounded by age, file count, and total bytes; oldest files are removed first. `radio.keep_audio`
also uses these QA bounds and is not an unbounded archive.

Validated transcripts enter `radio-outbox.sqlite3` before upload. API/network failure leaves the
same `source_message_id` in the outbox and retries with 10-second, 30-second, 1-minute, 5-minute,
then bounded exponential delays. This makes retries idempotent and lets reception continue during
LTE, Starlink, or Wi-Fi outages. `radio status` reports queue depth and degraded state.

## Remote configuration

The existing `/api/v1/edge/config` response may include a partial radio section. Local defaults
remain in effect for omitted values and malformed radio configuration is ignored safely.

```yaml
radio:
  enabled: true
  mode: continuous
  profile: bca-frs-na
  receivers:
    - name: primary
      device_index: 0
      channels: [5]
      privacy_code: 10
  processing:
    min_transmission_seconds: 0.5
    max_transmission_seconds: 30
    end_gap_seconds: 0.9
    vad_enabled: true
    discard_no_speech: true
    keep_audio: false
  qa:
    enabled: false
    max_storage_mb: 500
    max_age_hours: 24
    max_files: 100
```

Configured privacy codes are contextual metadata only. Edge sets `tone_detected: false` unless a
future decoder actually identifies CTCSS/DCS from the signal. RSSI and SNR remain null when the
current RTL pipeline cannot measure them reliably.

## Raspberry Pi 4/5

Install Raspberry Pi OS 64-bit, Python 3.12+, and the distribution `rtl-sdr` package. Add the
service user to the group that owns the RTL-SDR USB device (commonly `plugdev`), install the
Nooelec/RTL-SDR udev rules, reconnect the dongle, and confirm `rtl_test` and `rtl_fm` with
`terrasatch-edge doctor`. BCA/FRS support is receive-only; TerraSatch Edge never transmits.

For unattended operation, install `deploy/systemd/terrasatch-radio.service` as a user template,
then enable the instance for the service account. The command stays in the foreground so systemd
owns restart and shutdown behavior. Keep the ordinary Edge heartbeat agent enabled separately.

```bash
sudo cp deploy/systemd/terrasatch-radio.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now terrasatch-radio@terrasatch.service
```

Review the unit's install path and user before enabling it on a field node.
