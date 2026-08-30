# TerraSatch Edge release channels

TerraSatch Edge uses explicit release channels so operators can tell the difference between a newer evaluation build and an official platform-trusted release.

## Partner Beta

**Label:** `Partner Beta — SHA-256 verified`

Partner Beta builds are intended for controlled testing, pilot validation, and evaluation with invited organizations or individual testers. They can contain newer working Edge functionality before the official native signing/notarization gate is complete.

A Partner Beta artifact:

- is versioned and tied to an exact source revision;
- includes a SHA-256 checksum for integrity verification;
- may be unsigned or may lack the full operating-system trust chain required for an official release;
- may trigger Windows SmartScreen / Unknown publisher or macOS Gatekeeper warnings;
- must be labeled `partner-beta` in the artifact name and accompanying release metadata;
- must not be described as the official signed TerraSatch Edge installer.

A SHA-256 checksum proves that the downloaded bytes match the artifact TerraSatch published. **It is not a publisher/code signature.** Do not describe a checksum-only artifact as “hash signed” or “signed.”

Use Partner Beta for controlled evaluation only. The word “partner” identifies the distribution channel and does not by itself imply a formal partnership, endorsement, or production deployment.

## Official Release

**Label:** `Official Release`

An Official Release has completed the applicable native release gate and clean-machine validation. It also publishes a SHA-256 checksum.

For platforms with an OS-trusted publisher flow, the official gate currently includes:

- **Windows:** valid TerraSatch Authenticode signature plus RFC 3161 timestamp on the executable, service wrapper, installer, and uninstaller.
- **macOS:** Developer ID signing plus Apple notarization/stapling for the distributed package.
- **Linux:** native package validation, immutable artifact publication, checksum verification, and any platform/package signing requirements adopted for that distribution channel.

Official filenames do not carry the `partner-beta` or `unsigned` suffix.

## Artifact naming

Examples for version `0.2.3`:

```text
Partner Beta / Windows unsigned
TerraSatch-Edge-0.2.3-Windows-x64-partner-beta-unsigned.exe

Official / Windows signed
TerraSatch-Edge-0.2.3-Windows-x64.exe

Partner Beta / macOS unsigned
TerraSatch-Edge-0.2.3-macOS-arm64-partner-beta-unsigned.pkg

Official / macOS signed + notarized
TerraSatch-Edge-0.2.3-macOS-arm64.pkg

Partner Beta / Linux
terrasatch-edge_0.2.3_partner-beta_amd64.deb
```

Every distributable Partner Beta or Official artifact should be accompanied by:

```text
<artifact>.sha256
<artifact>.release.json
```

The release metadata should state at least the version, channel, source revision, code-signature state, and SHA-256.

## Website/download labeling

A controlled beta download should use copy such as:

> **TerraSatch Edge v0.2.3 — Partner Beta**  
> Newer evaluation build for controlled testing. SHA-256 verified. This artifact is not the official signed installer and may show an operating-system publisher warning.

The public official download should use:

> **TerraSatch Edge v0.2.3 — Official Release**  
> Native release that passed the TerraSatch release gate, with platform-appropriate publisher signing/notarization and published SHA-256 verification.
