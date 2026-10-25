# Decky Framegen — FSR 4 Lite

An independently maintained update of [Decky-Framegen](https://github.com/xXJSONDeruloXx/Decky-Framegen)
for FSR 4.1.2 INT8 Lite on SteamOS handhelds, targeting the Legion Go S.
It installs and configures upstream OptiScaler per game through Decky Loader.
This fork is not an official AMD or OptiScaler product.

## Install on Legion Go S

1. If a game is patched with an older Framegen version, **unpatch it with that version first**.
   v10 uses a different library layout; this build refuses to guess ownership of older files.
2. In Decky settings, enable Developer Mode and choose **Install Plugin from URL**.
   Paste the reusable preview URL shown below.
3. Open the plugin and choose **Setup OptiScaler Mod**. The binaries are bundled; setup works offline.
4. Leave **Default FSR4 runtime** at **FSR 4.1.2 | INT8 Lite (handhelds)**.
5. Close the game, select it in the plugin and apply the patch/launch options.
6. Launch with a current Proton build and select a supported upscaler input in the game
   (DLSS, XeSS or FSR, depending on the game's OptiScaler compatibility entry).
7. Bind a rear button to **Insert** to open OptiScaler. Confirm the active provider/version,
   **INT8 Lite** model and FSR4 watermark. The installed SDK DLL may still say 4.1.1;
   the 4.1.2 Lite model comes from the AMD Vulkan driver provider.

Compatibility depends on the game, Proton and Mesa. Start with a supported DX12 game.
An FSR4 watermark alone does not prove that Lite was selected; inspect the model too.
Compare base frame rate and motion quality in the same scene. This build has been tested
for packaging and file installation on a desktop, **not GPU-validated on a Legion Go S**.
Do not inject mods into games whose anti-cheat forbids them.

Lite changes **upscaling**. Upstream frame-generation defaults are retained; enable and test
frame generation separately in OptiScaler if desired. The Automatic model preset clears the
Lite override; it may fall back to FSR3 on unsupported combinations.

## Quick updates

The plugin has a **Copy update URL** button under **Plugin updates**.
Paste it into **Decky → Settings → Install Plugin from URL** to install the newest
published preview. You can also copy the same URL from here:

```text
https://github.com/patrickshao/Decky-Framegen/releases/download/latest-preview/Decky-Framegen-latest.zip
```

Reuse this URL for future updates; the version number never needs editing.
The link includes prereleases, which GitHub's `/releases/latest` URL excludes.
Updating the plugin does not update the OptiScaler bundle or existing game patches:
when a release changes the runtime, follow that release's setup/repatch instructions.
Versioned downloads remain available on the [releases page](https://github.com/patrickshao/Decky-Framegen/releases).

## Remove or change a patch

Close the game and use its **Unpatch** button before removing the plugin.
Original displaced files are restored, and unrelated ASI plugins are retained.
A per-game manifest records exactly which files belong to this build. If a managed DLL
has been changed outside the plugin, removal stops so you can preserve that modification.

The default preset controls future patches. Repatch an existing game to change its preset.
For manual/Heroic installs, enable Manual Mode and use the wrapper commands. The wrapper
and Decky use the same installer. `DLL=winmm.dll` selects a different proxy;
`FGMOD_FSR4_VARIANT=fsr4-auto` selects automatic model detection.
INI environment overrides are supported by the launch wrapper, for example:

```sh
FSR_Fsr4EnableWatermark=true ~/fgmod/fgmod %command%
```

## Sources and builds

All runtime dependencies are pinned in [runtime-assets.json](defaults/assets/runtime-assets.json):

- Official **OptiScaler v10 prerelease, 2026-10-24** from the OptiScaler team's nightly repository.
- Unmodified `amdvkffx64.dll` and `amdxcffx64.dll`, extracted from **AMD Adrenalin 26.10.1**
  downloaded directly from AMD. The Windows driver installer is **never executed**.
- Official **OptiPatcher v0.42** rolling snapshot, pinned by SHA-256.

No custom live-control ASI or repacked OptiScaler injector is included. Runtime installation
has no network downloader. The build downloader verifies TLS and rejects changed hashes.
See [runtime provenance](docs/runtime-provenance.md) for verification and update details.

Build with Python 3.9+, Node.js 22+, pnpm 10.28.2 and bsdtar/libarchive (included on SteamOS
and macOS; on Ubuntu use the distribution's `libarchive-tools` package):

```sh
pnpm install --frozen-lockfile --ignore-scripts
python3 scripts/fetch_assets.py
python3 -m unittest discover -s tests -v
pnpm exec tsc --noEmit
pnpm build
python3 scripts/package.py
```

The first asset fetch downloads AMD's approximately 1 GB driver package temporarily;
only the two verified DLLs are retained. You can reuse an already downloaded exact package
with `python3 scripts/fetch_assets.py --amd-package /path/to/installer.exe`.
Output: `out/Decky-Framegen-0.18.2.zip` and its `.sha256` file. The ZIP includes only the
locally built frontend, source backend, launcher assets and explicitly verified binaries.
GitHub Actions repeats the build and publishes an artifact with the checksum.

After a versioned release is published, the **Update preview download** workflow
verifies its ZIP checksum and plugin version, then copies the unchanged ZIP to the
reusable preview link. Run that workflow manually to repair or refresh the link.
The channel remains a prerelease; changing its tag does not change versioned tags.

## Credits

### Core Technologies
- **[Nukem9](https://github.com/Nukem9/dlssg-to-fsr3)** - Creator of the DLSS to FSR3 mod that makes frame generation possible
- **[Cdozdil/OptiScaler Team](https://github.com/optiscaler/OptiScaler)** - OptiScaler mod that provides the core functionality and bleeding-edge improvements
- **[Artur Graniszewski](https://github.com/artur-graniszewski/DLSS-Enabler)** - DLSS Enabler that allows DLSS features on non-RTX hardware
- **[FakeMichau](https://github.com/FakeMichau)** - Various essential tools including fgmod scripts, innoextract, and fakenvapi for AMD/Intel GPU support

### Community & Documentation
- **[Deck Wizard](https://www.youtube.com/watch?v=o_TkF-Eiq3M)** - Extensive community support including comprehensive guides, promotional content, thorough testing and feedback, custom artworks, and tutorial videos. His passionate advocacy and continuous support have been instrumental in Decky Framegen's success.

- **The DLSS2FSR Community** - Ongoing support and guidance for understanding the various mods and tools
