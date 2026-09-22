# Satchy command client

The historical simulation-only milestone below is extended by the
[current bidirectional provider implementation](RADIO_TX_PROVIDER.md).

TerraSatch Edge v0.2.5 provides the API-to-Edge control-plane client while preserving the receive-first radio path. The current Satchy branch also adds a provider-neutral `asset_mission` boundary with capability negotiation, remote policy/binding validation, and durable at-most-once effect claims.

## Safety boundary

- Edge polls only commands assigned to its paired device credential, organization, and site.
- `radio_reply` is accepted only when its payload contains `simulate_only: true`.
- The handler acknowledges the command and reports `simulated` without opening an SDR, radio, audio, serial, or PTT provider.
- `radio_tx`, missing/false `simulate_only`, and unknown command types are reported as `failed` without performing an operation.
- Physical RF transmission remains separately capability- and policy-gated.
- Field-asset missions are disabled unless the API supports the typed terminal result contract, the Edge heartbeat advertises an installed provider capability, and remote asset policy explicitly enables the bound provider.
- No drone, robot, or relay provider is installed by default in the packaged Edge runtime.
- The current field-asset provider contract is synchronous: `execute()` must return only when the provider has a terminal outcome. A future asynchronous provider requires a richer mission lifecycle rather than treating acceptance as completion.
- Mission abort/cancel is not yet an end-to-end physical provider operation; the current branch fails closed rather than claiming an unsupported stop/return-to-base action.

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
