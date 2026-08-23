# TerraSatch Edge Operator Setup

## Goal

TerraSatch Edge should be usable by field teams without requiring every operator to understand Python, Linux services, or API credentials.

The operator workflow is:

1. Install Edge
2. Connect hardware
3. Open the local console or use terminal mode
4. Pair the device with TerraSatch
5. Confirm API heartbeat
6. Configure field capabilities

## Two operating modes

### Local UI Mode

Start the local console:

```bash
terrasatch-edge ui
```

The UI provides:

- API connection status
- device pairing status
- hardware discovery
- diagnostics
- operator guidance
- service readiness

The local interface remains bound to the device by default.

### Terminal Mode

Advanced users can use:

```bash
terrasatch-edge setup
terrasatch-edge scan
terrasatch-edge doctor
terrasatch-edge status
terrasatch-edge run
```

Terminal mode supports automation, scripting, and remote administration.

## Recommended field deployment

Before deployment:

- Pair the Edge device to the organization
- Confirm site assignment
- Verify hardware inventory
- Confirm API heartbeat
- Test radio/audio ingestion
- Save diagnostics snapshot

## Future operator improvements

Planned improvements:

- guided first-run wizard
- hardware capability toggles
- radio provider configuration
- remote admin actions
- field profile templates
- offline-first setup workflow
