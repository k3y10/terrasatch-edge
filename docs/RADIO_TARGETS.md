# Receive targets on Windows and Linux

Nooelec NESDR SMArt v5 is receive-only. Repeater discovery does not imply transmit
authorization. TerraSatch can monitor repeater outputs without transmitting.

`RadioTarget` carries a stable ID, display name, integer frequency, analog modulation,
profile and source provenance. BCA/FRS is one profile. Both commands below select
462650000 Hz through the same RTL receiver, PCM gate, continuous segmentation,
speech validation, Faster Whisper and durable SQLite outbox:

```console
terrasatch-edge radio start --channel 19
terrasatch-edge radio start --frequency 462.650M
```

Frequency input also accepts `462650000` and `462.650MHz`. Explicit frequency and
channel options are mutually exclusive. `--modulation nfm` is the default;
`--modulation fm` selects the analog FM voice path with a wider demodulation rate.
Both use rtl_fm's `fm` demodulator, not its broadcast `wbfm` mode.
The implemented normal tuner path accepts 25–1750 MHz. HF direct sampling,
broadcast stereo, digital modes and trunking are outside this implementation.
This is a runtime limit, not a claim that the SMArt v5 hardware lacks HF reception.

## Persistent configuration

Add the following `radio` object to the existing **config.json**, retaining registration,
credentials and all other configuration. Edge reads JSON locally; YAML examples in
older documentation describe the API's conceptual configuration only.

```json
{
  "radio": {
    "enabled": true,
    "mode": "continuous",
    "receivers": [{"name": "primary", "device_index": 0}],
    "targets": [
      {
        "id": "cottonwood-650",
        "name": "Cottonwood Repeater",
        "profile": "gmrs-repeater",
        "source_type": "repeater",
        "frequency_hz": 462650000,
        "modulation": "nfm",
        "enabled": true,
        "repeater": {
          "provider": "manual",
          "output_frequency_hz": 462650000,
          "input_frequency_hz": 467650000
        }
      }
    ],
    "processing": {
      "auto_calibrate": true,
      "calibration_seconds": 0.4,
      "min_transmission_seconds": 0.5,
      "max_transmission_seconds": 30,
      "end_gap_seconds": 0.9,
      "vad_enabled": true,
      "discard_no_speech": true
    }
  }
}
```

The frequencies and repeater name above are an operator example, not independently
verified directory information. The selected frequency must match the repeater output.
Input/offset and configured tones are metadata; tone detection is not claimed.

Windows config: `%ProgramData%\TerraSatch\Edge\config.json`.
Native Debian config: `/etc/terrasatch-edge/config.json`.
Venv installations retain the existing XDG/environment configuration paths.
All processes controlling one receiver must use the same Edge state directory so
they participate in the same OS-held receiver locks. Do not run a separate venv and
native installation against one receiver with different state directories.

The existing authenticated `/api/v1/edge/config` response accepts the same `radio`
object. Radio configuration cannot change pairing, credentials or TX settings.
Malformed remote RX config disables reception with a warning; absent remote config
uses the local targets. Remove/correct invalid remote config to restore that fallback.
Remote `receive_enabled: false` remains authoritative over CLI target selection.
The Edge agent refreshes its remote cache; restart the independent radio monitor
to apply a changed target/configuration. No automatic live retuning is claimed.

An unconfigured service never defaults to an arbitrary carrier. Continuous monitoring
selects the highest-priority enabled target (configuration order breaks ties). This
release operates one receiver; additional receivers are not activated concurrently.
Legacy `radio_channel` and receiver `channels` remain supported. Legacy BCA channel
bindings remain frequency/channel-specific; explicit-frequency targets do not inherit
an unrelated logical API channel binding.

## Probe and scan

```console
terrasatch-edge doctor
terrasatch-edge radio devices
terrasatch-edge radio targets
terrasatch-edge radio probe --frequency 462.650MHz --seconds 10
terrasatch-edge radio scan --dwell 2
terrasatch-edge radio status
terrasatch-edge radio stop
```

Probe uses the configured receiver index, gain, squelch and PCM threshold. It performs
no transcription, ingestion or WAV retention. Output distinguishes requested duration,
observed PCM chunk count, peak RMS, PCM floor and cancellation. A squelched stream can
produce no chunks: floor is then null and lack of detected activity is inconclusive.
PCM amplitude is not calibrated RF power; RSSI/SNR are not invented.

Scan is sequential over explicitly configured, enabled targets only. Dwell is bounded
to 0.5–10 seconds. A probe exceeding the configured activity threshold starts a bounded
continuous hold (at most `max_transmission_seconds`) using the normal speech/outbox
pipeline, then advances. The scan repeats until stopped. It uses configured gain and
thresholds rather than running the multi-attempt startup calibration on every hop.
Each subprocess is owned, stopped and reaped before the next starts. Cancellation
propagates to probes and holds; the PCM reader can exit even when its queue is full.
Status/logs identify scan transitions and the current target.

This single-tuner scan can miss the beginning of speech, traffic on other targets,
or a call crossing a hold boundary. Use continuous monitoring for a critical channel.
There is no `--auto` spectrum sweep. Discovered targets are never admitted automatically.
