# Optional repeater discovery

Discovery supplies untrusted candidate metadata, not RF truth or permission to transmit.
Manual targets work without network access, a directory subscription or an API key.

`RepeaterDirectoryProvider` defines `search`, `get` and `normalize`. Included implementations
are Open Repeater, manual and organization catalogs. The provider has no access to Edge
registration credentials, tenant selection, TX execution or shell command construction.
Normalization admits bounded analog records only and selects the repeater output.
Discovered targets start with `enabled: false`, `discovered: true` and
`transmit_authorized: false`. An operator must inspect and explicitly add/enable a target.

## Open Repeater

The optional integration follows [Open Repeater's public API documentation](https://www.openrepeater.org/docs),
reviewed September 12, 2026. It documents header API-key authentication, geographic/text
search, frequencies/offsets in MHz, and 30 requests per day (reset at midnight UTC).
The public documentation illustrates individual records but does not specify the search
envelope fully. The adapter accepts a list or `repeaters`/`data` list; unknown envelopes
fail safely. Live authenticated API behavior still needs verification with an operator key.

PowerShell:

```powershell
$env:TERRASATCH_OPEN_REPEATER_API_KEY = '<your operator API key>'
terrasatch-edge radio discover --latitude 40.62 --longitude -111.81 --radius 75 --mode nfm --limit 20
```

Linux:

```bash
export TERRASATCH_OPEN_REPEATER_API_KEY='<your operator API key>'
terrasatch-edge radio discover --region 'Cottonwood Heights' --provider open-repeater --limit 20
```

Coordinates are explicitly provided examples. No IP geolocation or inferred transmitter
position is used. Alternatively configure `radio.location` locally with `latitude`,
`longitude` and `source` (`site` or `receiver`). The cache records the location source;
CLI overrides are labeled `cli`, and text queries `region`. Radius is kilometers, bounded
to 500 km. No GPS is required; automatic GPS fixes are not integrated in this release.

`--mode` accepts `nfm`/`fm` analog voice candidates only. Directory FM labels do not reliably
specify deviation/bandwidth: validate the target's modulation and bandwidth before admission.
Results can be fewer than `--limit` after rejecting unsupported/invalid entries. Only one
bounded page is fetched; there is no bulk crawler or background refresh.

## Cache and failure behavior

`repeater-cache.sqlite3` is separate from the transmission outbox. Queries cache normalized
targets with provider IDs, location/radius/mode, retrieval time and expiry (24 hours).
Up to 100 recent query entries are retained. A persisted local daily budget prevents more
than 30 search attempts per state directory; requests time out after 10 seconds and responses
are bounded to 1 MB. A provider 429 exhausts the local budget until the next UTC day;
its remote quota remains authoritative.
Do not use multiple installations with the same key to bypass provider limits.

On network/provider failure an expired matching result is returned with `stale: true` and
its original retrieval time. Without a cached result discovery fails clearly. Reception
never calls the directory and does not depend on this cache or a successful discovery.
Keys are supplied in request headers and never stored in the directory cache or logs.

Manual/organization catalog searches are local, e.g.:

```console
terrasatch-edge radio discover --provider manual --region Cottonwood
terrasatch-edge radio discover --provider organization --region Primary
```

No RepeaterBook scraping or API implementation is included. Any future provider must use
a properly authorized API and comply with its applicable commercial terms.
