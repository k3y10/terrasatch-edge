# TerraSatch Edge Operator Setup

## Goal

TerraSatch Edge should be usable by field teams without requiring every operator to understand Python, service management, or API credentials.

The supported operator workflow is:

1. install Edge
2. connect field hardware
3. open the Operator Console or use terminal mode
4. pair the device to the correct TerraSatch organization + site
5. verify API authentication and heartbeat
6. confirm hardware and local runtime settings
7. leave the Edge service running for field operation

Organization, site, and future channel/workflow policy remain control-plane concerns. The local UI intentionally does not let an operator bypass tenant assignment or invent a parallel configuration model.

## Operator Console (recommended)

Start the guided local console:

```bash
terrasatch-edge console
```

The packaged Windows installer exposes the same console through the TerraSatch Edge desktop and Start Menu shortcuts. The command opens the browser automatically and binds to `127.0.0.1:8742` by default.

The Operator Console provides:

- current API reachability
- device credential/authentication state
- organization + site assignment visibility
- hardware discovery and rescans
- supported local Edge settings
- speech runtime settings
- API verification + hardware heartbeat
- pairing from the browser through TerraSatch Admin
- local diagnostics
- credential removal for intentional re-pairing
- terminal command reference for advanced work

Mutating browser actions require an Edge-specific request header and the console is loopback-only by default. Arbitrary shell execution is deliberately not exposed through the browser.

### Network safety

Do not expose the Operator Console to a LAN/WAN by default.

```bash
terrasatch-edge console --host 127.0.0.1
```

A non-loopback bind is rejected unless the operator explicitly supplies `--allow-remote`. Use that option only on a trusted, controlled network.

## Terminal mode

The terminal remains a first-class interface for scripting, service work, and advanced troubleshooting:

```bash
terrasatch-edge setup
terrasatch-edge scan
terrasatch-edge devices
terrasatch-edge status
terrasatch-edge doctor
terrasatch-edge run --once
terrasatch-edge run
terrasatch-edge paths
```

`terrasatch-edge setup` keeps the existing browser/device-code pairing flow and is the preferred non-UI fallback.

## Configuration ownership

### Local Edge settings

The operator may configure local runtime details such as:

- API URL
- node name
- heartbeat / scan interval
- source label
- local speech model/device/compute settings

These values are stored through the existing `EdgeConfig` path used by the CLI and service.

### TerraSatch control-plane settings

The following should stay API/Admin controlled:

- organization assignment
- site assignment
- device credential scope
- remote Edge configuration
- organization workflow/channel policy
- future provider/channel activation rules

This prevents a field computer from silently drifting away from the API's tenant and policy model.

The running Edge agent already reloads local pairing/config changes without reinstalling and retrieves remote configuration from the API after a successful heartbeat.

## Recommended field deployment check

Before deployment:

1. open `terrasatch-edge console`
2. connect the intended SDR/radio/audio/GPS hardware
3. select **Rescan Hardware**
4. select **Pair This Edge** if the device is not already assigned
5. approve the correct organization + site in TerraSatch Admin
6. select **Verify Connection**
7. run **Diagnostics**
8. confirm the device/site assignment and detected hardware
9. close the Operator Console when finished; the installed Edge service continues separately

For deeper validation, terminal users can additionally run:

```bash
terrasatch-edge status
terrasatch-edge doctor
terrasatch-edge run --once
```

## Windows pilot behavior

The v0.2.2 Windows installer now targets a UI-first onboarding model:

- **TerraSatch Edge** desktop shortcut -> Operator Console
- **TerraSatch Edge Operator Console** -> guided local UI
- **TerraSatch Edge Status** -> terminal status
- **TerraSatch Edge Diagnostics** -> terminal diagnostics
- **TerraSatch Edge Hardware Scan** -> terminal hardware scan
- **TerraSatch Edge Terminal Setup** -> legacy/advanced CLI pairing flow

The installer still installs/updates the persistent Windows service. The console is an operator/configuration surface, not the field agent process itself.

## Next operational adapter phase

The setup work does not falsely claim continuous radio-channel operation that the standalone Edge runtime does not yet implement. The next adapter phase should consume API-controlled channel/provider configuration and then continuously:

1. tune approved receive channels
2. segment radio/audio captures
3. run the configured local/remote transcription path
4. submit source-aware transmissions to TerraListen/Satchy
5. retain offline work locally when connectivity is unavailable

That phase should extend the existing API + remote-config contract rather than create organization-specific logic inside Edge.
