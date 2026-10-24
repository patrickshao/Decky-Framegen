# Runtime provenance: 0.18.0

The authoritative URLs, archive members and SHA-256 values are in
[`defaults/assets/runtime-assets.json`](../defaults/assets/runtime-assets.json).
The same manifest drives asset fetching, packaging and backend setup. Changing an
upstream URL does not bypass an existing hash: extraction and packaging fail closed.

## OptiScaler

Source: <https://github.com/optiscaler/OptiScaler>

Published binary: the OptiScaler team's
[nightly-20261024](https://github.com/optiscaler/OptiScaler-nightly/releases/tag/nightly-20261024).
Archive SHA-256 was checked against GitHub's release-asset digest. The injector and
support libraries are extracted unchanged. Only the generated default INI changes:
ASI plugins are enabled for official OptiPatcher, and HQ fonts are disabled for Proton.
Frame generation is not forced on. No community-fork injector is used.

## AMD providers

Original distribution: [AMD RX 7600 driver download page](https://www.amd.com/en/support/downloads/drivers.html/graphics/radeon-rx/radeon-rx-7000-series/amd-radeon-rx-7600.html),
Adrenalin 26.10.1 (`whql-amd-software-adrenalin-edition-26.10.1-win11-b.exe`).

The package was fetched directly from `drivers.amd.com` using HTTPS. Its SHA-256
was recorded locally; this is a reproducibility pin, not a claim that AMD publishes
that checksum or that the package's Authenticode signature was independently validated.
The self-extracting EXE is treated purely as data. At offset 1785344 it contains a
7z archive. `bsdtar` reads the two named members under
`Packages/Drivers/Display/WT6A_INF/B026676/`; the builder then verifies each DLL hash.

The DLLs are not patched or recompiled. `amdvkffx64.dll` supplies the INT8 Lite
model, selected with `Fsr4GpuSupport=4` and `Fsr4Model=3`. The original SDK upscaler
still reports 4.1.1, so that file's version does not establish the running model.

## OptiPatcher

Source and binary: <https://github.com/optiscaler/OptiPatcher/releases/tag/rolling>

Pinned snapshot: v0.42, commit `b3f8c1b821db739963625ee0767d2d7df9ace0b5`.
The checksum was checked against GitHub's release-asset digest. The rolling URL is
mutable: if upstream replaces it, a fresh build must stop on a checksum mismatch.
Use a previously verified cached file or review and pin a new release explicitly.

## Updating and verification limits

To update, obtain new files from their original publishers, review the associated
source/release changes, update the manifest and provenance notes, then run the tests
and build. Keep AMD driver extraction as data-only processing. Do not substitute a
mirror's checksum for independent origin verification.

Pinned hashes detect changes relative to the reviewed downloads; they cannot prove
that upstream software has no vulnerabilities. Builds are deterministic within the
same Python/zlib environment; cross-environment ZIP compression can differ. The
checksum belongs to the exact ZIP produced by each build.

The local test suite covers file ownership, backups, configuration, rollback,
tampering, symlinks, path traversal and launch-wrapper behavior. A desktop smoke
test also runs setup, patch and unpatch with the actual payload. Neither test
establishes GPU compatibility, image quality or performance on the Legion Go S.
