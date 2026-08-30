# TerraSatch Edge release checklist

TerraSatch Edge has two distributable native channels: **Partner Beta** and **Official Release**. See [`RELEASE_CHANNELS.md`](RELEASE_CHANNELS.md).

A SHA-256 checksum verifies artifact integrity. It is **not** a publisher/code signature.

## 1. API readiness

Production Edge clients target:

```text
https://api.terrasatch.com
```

Before distributing a new native artifact:

1. Deploy the intended API `main` revision.
2. Confirm `/health/ready` is healthy over HTTPS and reports the intended revision.
3. Confirm an already-paired Edge service can send authenticated heartbeats without reinstalling or re-pairing.
4. Start a disposable pairing and confirm the verification URL uses `https://api.terrasatch.com/admin/edge/pair?code=`.

Do not ship a new client build merely to work around an API-side regression.

## 2. Edge environment contract

The Edge runtime defaults to:

```text
TERRASATCH_EDGE_API_URL=https://api.terrasatch.com
```

Verify on every native package:

```text
terrasatch-edge --version
terrasatch-edge status
terrasatch-edge doctor
```

After pairing, `status` should show the expected API URL, `API: ONLINE`, and `Auth: OK`.

## 3. Partner Beta gate

Partner Beta is for controlled testing, pilot validation, and invited evaluation. It can contain a newer working version before the official signing/notarization gate is complete.

For each exact Partner Beta artifact:

1. Build from the intended source revision.
2. Run the full native test suite.
3. Install the produced artifact on a clean/native target.
4. Pair once and confirm Device ID/site.
5. Confirm the background service sends heartbeats.
6. Restart/reboot and confirm registration persists.
7. Test actual supported receive hardware where advertised.
8. Confirm the filename visibly includes `partner-beta` and, when applicable, `unsigned`.
9. Generate and verify `<artifact>.sha256`.
10. Generate `<artifact>.release.json` with version, source revision, channel, signature state, checksum, and `official_release: false`.
11. Tell the recipient that the package is evaluation software and may trigger Windows SmartScreen/Unknown publisher or macOS Gatekeeper warnings.
12. Do not describe the artifact as the official signed installer or as evidence of a formal partnership/endorsement.

Recommended Partner Beta paths:

```text
edge/beta/windows/v0.2.3/TerraSatch-Edge-0.2.3-Windows-x64-partner-beta-unsigned.exe
edge/beta/macos/v0.2.3/TerraSatch-Edge-0.2.3-macOS-arm64-partner-beta-unsigned.pkg
edge/beta/linux/v0.2.3/terrasatch-edge_0.2.3_partner-beta_amd64.deb
```

Never overwrite a beta object with different bytes. Publish a new version/path.

## 4. Official native artifact gate

Only label an artifact **Official Release** after it passes the Partner Beta/native functional checks plus the applicable platform trust gate.

### Windows

Verify a valid, timestamped TerraSatch Authenticode signature on:

- native Edge executable;
- service wrapper;
- installer;
- uninstaller.

The signer must be the expected TerraSatch publisher identity and the signature must validate on a clean Windows target.

### macOS

Require:

- Developer ID signing;
- signed installer package;
- Apple notarization acceptance;
- stapled ticket validation;
- Gatekeeper validation on a clean target.

### Linux

Require the native package, architecture, service lifecycle, checksum, and immutable publication checks plus any package-signing requirements adopted for the target distribution channel. Do not call a SHA-256 checksum a code signature.

## 5. Official artifact publication

Recommended immutable Official paths:

```text
edge/windows/v0.2.3/TerraSatch-Edge-0.2.3-Windows-x64.exe
edge/macos/v0.2.3/TerraSatch-Edge-0.2.3-macOS-arm64.pkg
edge/macos/v0.2.3/TerraSatch-Edge-0.2.3-macOS-x64.pkg
edge/linux/v0.2.3/terrasatch-edge_0.2.3_amd64.deb
edge/linux/v0.2.3/terrasatch-edge_0.2.3_arm64.deb
```

Publish SHA-256 verification alongside every Official artifact as an additional integrity check.

## 6. Downloads-page contract

The website must visually distinguish channels before a user downloads anything.

Partner Beta copy should say, in substance:

> **TerraSatch Edge v0.2.3 — Partner Beta**  
> Newer evaluation build for controlled testing. SHA-256 verified. This is not the official signed installer and may show an operating-system publisher warning.

Official copy should say:

> **TerraSatch Edge v0.2.3 — Official Release**  
> Native release that passed the TerraSatch release gate, including platform-appropriate publisher signing/notarization and published SHA-256 verification.

Never place an unsigned beta artifact behind a button labeled only “Download” or “Official” without the beta status visible next to the action.

## 7. Final verification

From a clean browser/session:

1. Open the download location.
2. Confirm version, platform, architecture, and channel are visible.
3. Download the exact immutable artifact.
4. Compare SHA-256 with the published checksum.
5. Inspect `.release.json` for Partner Beta packages.
6. Install that downloaded copy on a clean target.
7. Confirm `--version`, setup/pairing, `status`, `doctor`, and service heartbeat.
8. For Official Windows/macOS releases, independently verify publisher signing/notarization.

Only then treat the artifact according to its labeled channel.
