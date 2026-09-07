# Channel-aware Edge integration and QA — 2026-09-07

## Branch decision

Continue on `feat/channel-aware-radio-ingest`, as specified in the September 4 scope.
Start from `main` at `7497384e5ae637a095732f0046d431ecc82574f2` and integrate
`feat/continuous-radio-monitor-vnext` at `4f18f4dbe8a209ea6c2deefa3cd96efe8d12df96`.
Main already contains the simulation command client (PR #10), console, branding,
Windows logging fixes, and restored bounded BCA receive workflow.

Counts below are commit ancestry differences against that main, not proof of semantic differences.

| Remote branch | Behind main | Ahead of main | Decision |
| --- | ---: | ---: | --- |
| agent/edge-0.2.2-qa-cleanup | 42 | 0 | Already included |
| agent/edge-bca-frs-autocal | 36 | 19 | Historical divergent work; use current continuous implementation |
| agent/edge-bca-frs-receive | 36 | 16 | Historical divergent work; restored receive path already in main |
| agent/edge-speech-0.2 | 118 | 22 | Historical; current speech implementation retained |
| agent/edge-v0.2-pilot | 44 | 1 | Historical pilot branch |
| agent/restore-bca-receive-main | 4 | 0 | Already included |
| agent/windows-service-ascii-log-fix | 37 | 0 | Already included |
| chore/partner-beta-release-channel | 2 | 1 | Excluded; PR #9 explicitly closed as website-only scope |
| docs/v0.2.3-public-source | 3 | 1 | Main already has the public-source documentation update |
| feat/continuous-radio-monitor-vnext | 2 | 2 | Integrated both continuous capture/calibration commits |
| feat/satchy-edge-command-client | 1 | 0 | Already included through PR #10 |
| feature/edge-console-brand-refresh-v0.3 | 6 | 0 | Already included |
| feature/operator-setup-ui-v1 | 12 | 0 | Already included |

## Changes and behavior

- Combine continuous RX workers, calibration, noise/silence gates, bounded audio retention,
  SQLite outbox, and heartbeat radio telemetry with main's Satchy command client.
- Resolve the API-client merge conflict while preserving HTTP status codes.
- Preserve raw STT text; API/Satchy retains responsibility for normalization and interpretation.
- Always send RF metadata as an object, fixing current API rejection of `null` on ordinary audio/text ingestion.
- Preserve physical-channel suffixes even when the configured source name is long.
- Add `radio.channel_bindings`, mapping physical BCA channel numbers to logical API channel IDs.
  Explicit mapping never falls back to an unrelated logical channel. Legacy single-channel binding
  applies only to its configured carrier. Existing `radio.ai_channel` binding is recognized only
  when its frequency matches the RX carrier.
- Invalid remote receiver/profile/binding settings and explicit receive-disable fail closed.
  Disabled monitoring is rejected before automatic RF calibration opens hardware.
- Prevent starting the same monitor object twice or reusing an already stopped object.
- Strip all radio/PTT/duplex/audio-output capability claims from hardware discovery.
  Keep operational provider state separate through `RadioCapability`, `RadioProviderStatus`,
  and the hardware-neutral `RadioTxProvider` interface. Simulation never advertises TX.
- Agent command processing checks paired organization/site/device, terminal state, expiry,
  unchanged ACK identity/payload, reply text, and consistent simulation routing.
- Include UI dependencies in the full QA gate and isolate test credentials/config/state.
  Correct the console regression assertion to compare the effective API target, including
  the QA script's localhost environment override.

Example remote configuration for the current single receiver:

```json
{
  "radio": {
    "enabled": true,
    "receivers": [{"name": "primary", "device_index": 0, "channels": [5]}],
    "channel_bindings": {"5": "<existing logical channel UUID>"}
  }
}
```

The illustrative UUID slot must be supplied by the organization's existing API channel.
Binding metadata does not add simultaneous reception. Current continuous monitoring still
uses the first receiver/carrier and warns about additional entries. Privacy codes remain
configured context, not detected CTCSS evidence.

## Executed QA

Environment: Linux x86_64, Python 3.12.13, installed dev/UI/speech extras.

- Unmodified main baseline: **87 passed**.
- Integrated branch full suite: **159 passed**, no skips, two upstream deprecation warnings.
- Full `scripts/qa-local.sh` with speech enabled: **PASS**.
- Ruff and compile/import smoke: **PASS**.
- Source wheel build and inclusion of the new modules: **PASS** (not a native installer).
- CLI version/help and canonical audio-ingest help: **PASS**.
- `faster_whisper` dependency import: **PASS**; no model download or real speech inference claimed.
- Existing speech/ingest/config coverage gate: **83.47%**, required **75%**.
  This is not whole-package or whole-radio coverage.
- Replay regressions exercise generated PCM/WAV fixtures, blocked transcription with continued
  capture, short/weak/silent rejection, offline outbox persistence, restart delivery with stable
  IDs, all 22 physical-channel source suffixes, logical-channel separation, simulation retry,
  foreign identity/terminal/expired command handling, and altered ACK payload rejection.
- A real localhost HTTP server checks polling, ACK, bearer authentication and result reporting.
  The test environment required `socksio` for its inherited proxy configuration and localhost
  `NO_PROXY`; this was an environment dependency, not a product change.
- Console tests exercise local mutation headers, pairing assignment preservation, and refusal
  to redirect the API target through the browser.

Reproduce:

```bash
TERRASATCH_QA_WITH_SPEECH=1 bash scripts/qa-local.sh
```

## RF completion blocker — not a completed bidirectional release

Read against API main `17ea63b4d0357484c56d541fee817a4aef5a7bbe`:

- `src/terrasatch/actions/service.py` queues approved, policy-gated `radio_reply` commands.
- `src/terrasatch/edge/schemas.py::EdgeCommandResultRequest` permits only `simulated`/`failed`.
- `src/terrasatch/edge/command_service.py::complete_command` also rejects any other result.

Therefore a successful physical TX cannot currently be represented by this API contract.
This Edge branch deliberately does not invoke physical TX and never calls a real send
"simulated". The provider interface is groundwork, not an installed hardware adapter.
The full bidirectional goal remains incomplete pending compatible API transmitted-result
handling, an implemented TX adapter, persistent execution deduplication for uncertain
outcomes, enforced duration/cooldown and channel policy, and proven PTT/duplex cleanup.
The existing natural-addressing API work is kept separate; no API files were changed here.

## Remaining release validation

- Live preview API pairing/approval/ingest round trip with an assigned test device/site.
- Actual RF reception, range/noise tests and real recorded field-audio accuracy evaluation.
- Compatible TX hardware/provider and half-duplex/independent RX/TX device tests after the API gap is fixed.
- Windows signed installer clean-machine install/upgrade/reboot/service and hardware tests.
- macOS/Linux native installer gates from `NATIVE_BUILDS.md` as applicable.

Vercel project inventory was inspected: no project is linked to `k3y10/terrasatch-edge`.
The Edge runtime/console runs locally; website/download publishing belongs to
`wasatch-ascent`. No Vercel deployment, main merge, release tag, installer publication,
or production configuration was performed. Keep this PR draft until the outstanding
release gates appropriate to its intended release are satisfied.
