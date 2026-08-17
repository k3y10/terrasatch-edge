# TerraSatch Edge public release checklist

Use this checklist before enabling a new Edge artifact on the public downloads page.

## 1. API release gate

Production Edge clients target:

```text
https://api.terrasatch.com
```

The API production environment must set:

```text
TERRASATCH_API_BASE_URL=https://api.terrasatch.com
```

Before publishing an Edge build:

1. Deploy the intended API `main` revision.
2. Confirm `/health/ready` is healthy over HTTPS and reports the intended revision.
3. Confirm an already-paired Edge service can send authenticated heartbeats after the API deployment without reinstalling or re-pairing.
4. Start a disposable pairing and confirm `verification_url` begins with `https://api.terrasatch.com/admin/edge/pair?code=`.

Do not publish a client build to work around an API-side pairing or heartbeat regression. Keep the client/API responsibility boundary explicit.

## 2. Edge environment contract

The Edge runtime defaults to:

```text
TERRASATCH_EDGE_API_URL=https://api.terrasatch.com
```

`TERRASATCH_EDGE_API_URL` is an operator/deployment override and takes precedence over saved config. The Windows Setup Wizard uses the same environment contract for new pairing while preserving a valid existing registration.

Verify on every native package:

```text
terrasatch-edge --version
terrasatch-edge status
terrasatch-edge doctor
```

`status` must show the expected API URL, `API: ONLINE`, and `Auth: OK` after pairing.

## 3. Native artifact gate

For each exact artifact:

1. Build from the intended Edge release commit.
2. Run the full test suite as part of the native build.
3. Install the produced artifact, not a source checkout.
4. Pair once and record the Device ID/site.
5. Confirm the background service picks up registration and sends heartbeats.
6. Restart/reboot and confirm registration persists.
7. Record SHA-256 from the exact artifact that passed validation.
8. Test real supported receive hardware when that platform is advertised as receiver-ready.

TX remains provider/hardware gated and must never be inferred from hardware discovery alone.

## 4. Public Blob layout

Keep immutable versioned objects in the public release store. Recommended paths:

```text
edge/windows/v0.2.2/TerraSatch-Edge-Setup-x64.exe
edge/linux/v0.2.2/terrasatch-edge_0.2.2_amd64.deb
edge/linux/v0.2.2/terrasatch-edge_0.2.2_arm64.deb
edge/macos/v0.2.2/TerraSatch-Edge-0.2.2-macOS-arm64.pkg
edge/macos/v0.2.2/TerraSatch-Edge-0.2.2-macOS-x64.pkg
```

Never overwrite a validated versioned object with different bytes. Publish a new version/path instead.

After upload, verify the public URL from a machine/session that is not authenticated to Vercel and compare its SHA-256 to the locally validated artifact.

## 5. Downloads page contract

The TerraSatch downloads page currently supports these release URL environment variables:

```text
VITE_EDGE_WINDOWS_X64_URL
VITE_EDGE_MACOS_ARM64_URL
VITE_EDGE_MACOS_X64_URL
VITE_EDGE_LINUX_AMD64_URL
VITE_EDGE_LINUX_ARM64_URL
```

Do not enable a platform button until its exact public Blob URL and checksum have passed the gates above. Keep the page version label aligned with the artifact version being advertised.

## 6. Final public verification

From a clean browser/session:

1. Open the TerraSatch downloads page.
2. Confirm the intended platform button is enabled and points to the immutable versioned Blob object.
3. Download the artifact through the public URL.
4. Confirm SHA-256 matches the validated local artifact.
5. Install that downloaded copy on a clean target and confirm `--version`, setup/pairing, `status`, and service heartbeat.

Only then treat the native artifact as publicly released.
