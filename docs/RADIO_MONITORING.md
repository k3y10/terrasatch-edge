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

`--hotwords` biases local transcription; `--callsign` labels the source callsign. They do not activate the receiver and
their absence never invalidates otherwise authorized speech.

## Filtering and temporary audio

At startup, Edge samples the quiet channel and automatically selects an RTL gain/squelch pair plus
local PCM activity/release thresholds. Keep the channel clear for the short calibration period.
This local RMS gate is required because some Linux `rtl_fm` builds continuously emit quiet PCM
even while squelch is closed; byte flow by itself does not indicate a transmission. Hysteresis and
the configured end gap form real transmission boundaries instead of fixed 30-second noise files.

Edge then enforces minimum/maximum duration before writing a temporary WAV. An inexpensive energy
voice check runs before Faster Whisper, whose own VAD remains the higher-quality second check.
Carrier pops, weak candidates, silence, and Faster Whisper's normal “no speech” result are
discarded without creating API transmissions or stopping the receiver. `radio status` reports the
measured noise floor and active calibration settings.

Use `--no-auto-calibrate` only when validating known manual settings. `--squelch` or `--gain-db`
pins that value while calibration resolves the other settings. Environment overrides include
`TERRASATCH_EDGE_RADIO_AUTO_CALIBRATE`, `TERRASATCH_EDGE_RADIO_CALIBRATION_SECONDS`,
`TERRASATCH_EDGE_RADIO_MIN_PEAK_RMS`, `TERRASATCH_EDGE_RADIO_RELEASE_RMS_THRESHOLD`, and
`TERRASATCH_EDGE_RADIO_MAX_SECONDS`.

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
    auto_calibrate: true
    calibration_seconds: 0.4
    min_transmission_seconds: 0.5
    max_transmission_seconds: 30
    end_gap_seconds: 0.9
    min_peak_rms: 180
    release_rms_threshold: 120
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
