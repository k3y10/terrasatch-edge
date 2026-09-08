# Bidirectional provider execution and API compatibility

The channel-aware development branch now executes acknowledged `radio_reply` commands
through an explicitly configured local TX bridge. RX continues through the existing
RTL provider. No specific radio manufacturer's TX driver is bundled or claimed validated.

## Compatibility and rollout

The deployed API checked on September 8 is v0.3.0, revision `17ea63b4d035`.
Existing ingest, pairing, heartbeat and simulation routes remain supported. The companion
API branch adds `GET /api/v1/edge/command-capabilities` with protocol version 1 and
`result_statuses: ["simulated", "transmitted", "failed"]`.

An older API returning 404/405 for this endpoint prevents physical TX. Edge does not advertise
bridge TX capabilities to that API, and it never labels real RF as simulated. Deploying the
Edge software first therefore does not require enabling RF or upgrading existing demo flows.
Actual transmitted results require the companion API update; neither branch is production-published.

## Local installation settings

`config.json` supports these local-only keys:

- `radio_tx_enabled`: false by default.
- `radio_tx_executable`: absolute path to a locally installed provider executable.
- `radio_tx_max_seconds`: maximum 15 seconds by default, configurable up to 60.
- `radio_tx_cooldown_seconds`: minimum 10 seconds by default.

Remote configuration cannot select or install an executable. The process uses JSON stdin/stdout,
no shell, and an environment restricted to basic OS/runtime variables. It is not given the
Edge API credential. Windows requires a native executable; POSIX executables must be executable.

The API-managed `radio` policy must also enable `transmit_enabled` and contain an `ai_channel`
with `rf_reply_enabled: true`, `reply_route: "rf"`, the matching `logical_channel_id`,
`provider_channel`, `frequency_hz`, `max_reply_seconds` and `response_cooldown_seconds`.
Edge re-fetches this policy after ACK for each new RF attempt. Local maximum duration and
minimum cooldown remain limits even if remote policy requests more permissive values.

## Bridge protocol version 1

Every invocation receives one JSON object with `protocol_version: 1` and `operation`.

For `operation: "status"`, the executable must return:

```json
{
  "protocol_version": 1,
  "ready": true,
  "simulated": false,
  "device_id": "independent-tx-device",
  "capabilities": ["radio:transmit", "radio:ptt", "audio:output", "radio:half_duplex"],
  "rx_coordination": "independent",
  "watchdog": true
}
```

Exactly one of half/full duplex must be reported. `rx_coordination` is either `independent`
(separate RX device) or `managed` (the provider coordinates its shared receiver).
These are implementation obligations of the installed bridge, not capabilities inferred
from USB detection. A simulation bridge must identify itself as simulated and advertises no TX.

For `operation: "transmit"`, the request's `reply` object contains `command_id`, `text`,
`logical_channel_id`, `provider_channel`, `frequency_hz`, and `max_seconds`.
The provider handles audio generation/output and hardware/PTT operations. It must enforce
its own watchdog, duration limit, stable-command deduplication and channel binding. For a
shared half-duplex device it must pause RX before PTT, release PTT in cleanup, then restore RX.
It must not claim managed RX when the independent Edge RTL process owns that same receiver.

A successful response must include `protocol_version: 1`, the exact `command_id`,
`status: "transmitted"`, `ptt_released: true`, and `rx_restored: true`.
A process timeout, crash, malformed result, or missing cleanup confirmation is recorded as
failed/uncertain, never as proof that no RF occurred. The subprocess timeout is a last resort;
the provider's hardware watchdog must keep PTT safe even if its process dies.

## At-most-once attempts and recovery

Before sending, Edge commits a scoped command/payload fingerprint in
`radio-command-journal.sqlite3`. Concurrent Edge processes cannot claim the same command or
overlap another in-flight attempt. The deadline is checked again after acquiring the claim.
Cooldown is measured from completion and persists across restarts.

Completed/failed outcomes are re-reported from this journal without calling the provider again,
including after the command expires or policy changes. The API accepts late results for
already acknowledged operations and preserves idempotent terminal results.

If Edge dies while an attempt is in flight, its outcome is unknown. Automatic replay is blocked,
and further RF for that identity is blocked until reconciliation. After stopping the adapter
and confirming PTT is released, the operator can run:

```bash
terrasatch-edge reconcile-radio-command COMMAND_ID --confirm-stopped
```

This records failed/uncertain without deleting history or resending RF. The next command cycle
reports that result to the API. The command does not stop the physical radio for the operator.

## Reproducible QA

Run Edge's complete QA with dev/UI/speech dependencies:

```bash
TERRASATCH_QA_WITH_SPEECH=1 bash scripts/qa-local.sh
```

The existing speech/ingest/config gate remains 75%. The newly executable command/TX paths
have their own 90% gate, covering commands, execution policy, durable journal, and bridge.
Coverage measures exercised statements/branches, not a percentage of product completion.

Install both checkouts' development dependencies into a test environment, then run:

```bash
bash scripts/qa-api-compatibility.sh /absolute/path/to/current-api-checkout 0
bash scripts/qa-api-compatibility.sh /absolute/path/to/proposed-api-checkout 1
```

The four scenarios test real FastAPI routes, bearer authentication, SQLite ORM persistence,
ingestion and idempotency, approval services, simulated/transmitted results, foreign-device
rejection, and lost result delivery. Only the database connection factories and external
Redis event publication are substituted. The simulation case uses the valid optional-deadline
contract so that SQLite's naive timestamp storage does not falsely fail the old PostgreSQL API.
The proposed API emits explicit UTC command timestamps, including the RF test deadline.

These tests use fake providers/generated audio and do not establish RF performance, real STT
accuracy, native Windows packaging, PostgreSQL concurrency, or hardware watchdog behavior.

## Verification results — 2026-09-08

- Edge full QA: 194 tests passed; speech/ingest/config coverage 83.66% (75% minimum), command/TX coverage 91.41% (90% minimum).
- Current API revision `17ea63b4d0357484c56d541fee817a4aef5a7bbe`: 195 baseline tests passed; four API/Edge compatibility scenarios passed. Production `/health` reported this revision healthy during QA; production command writes were not used for testing.
- Companion API update: 200 tests passed; command lifecycle coverage 86.26% (80% minimum); four API/Edge compatibility scenarios passed.
- Both full local QA scripts passed. API migration graph, CLI/OpenAPI, deterministic fallback and Edge optional speech imports passed.

The earlier 83.47% number was measured coverage, not a gate or product-completion score.
The minimum remains 75% for that older surface; new command/TX code has a separate 90% minimum.

Deploy the companion API result support before enabling local RF transmission. Until then,
capability negotiation blocks physical RF while ingestion and simulation remain compatible.
Physical hardware acceptance remains required as described above.
