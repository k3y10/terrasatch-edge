# Satchy command client

TerraSatch Edge v0.2.4 adds the first API-to-Edge outbound control-plane client while preserving the v0.2.3 receive-only radio pilot.

## Safety boundary

- Edge polls only commands assigned to its paired device credential, organization, and site.
- `radio_reply` is accepted only when its payload contains `simulate_only: true`.
- The handler acknowledges the command and reports `simulated` without opening an SDR, radio, audio, serial, or PTT provider.
- `radio_tx`, missing/false `simulate_only`, and unknown command types are reported as `failed` without performing an operation.
- Physical transmission remains a later provider-specific feature and requires separate capability and policy work.

## Runtime sequence

Each normal Edge agent cycle continues to scan hardware, send its heartbeat, and retrieve remote configuration. It then performs:

```text
GET  /api/v1/edge/commands
POST /api/v1/edge/commands/{command_id}/ack
POST /api/v1/edge/commands/{command_id}/result
```

Acknowledged commands remain pollable until a terminal result is accepted. If the network drops after acknowledgement, the next agent cycle resumes the result instead of acknowledging or executing twice.

## Joint API and Edge test

Run the Satchy API feature branch and apply its migrations. Pair this Edge checkout to that API and site using the existing setup flow. Then:

1. Send `Satchy, Control 2.` through the normal receive or `ingest-text` path.
2. Confirm that the API preserves the transmission and proposes `Control 2, Satchy. Go ahead.`
3. Approve the proposal in `/admin/satchy`.
4. Run one normal Edge cycle with `terrasatch-edge run --once`, or process only commands with `terrasatch-edge commands`.
5. Confirm that the action becomes `COMPLETED`, the outbound transmission becomes `SIMULATED`, and the Edge command becomes `completed`.

The receive-only validation remains unchanged and can still be exercised with:

```bash
terrasatch-edge listen-radio \
  --channel 5 \
  --once \
  --callsign "BCA TEST" \
  --hotwords "TerraSatch, Cardiff Bowl, BCA"
```

## Channel-aware development branch

The agent additionally checks paired identity and unchanged ACK payloads. Physical RF remains blocked by the current API result contract. See [the QA report](EDGE_UPDATE_QA.md) for the provider boundary and remaining completion work.
