# Feature and install reference

Crimson Glass packages a personal Debian 13 and GNOME 48 setup. Start with the [README](../README.md) for the screenshot, supported platform, and hardware behind the project.

## What’s included

| Area | Features |
| --- | --- |
| GNOME Shell | Glass bottom dock on the primary monitor with status controls, tray overflow, auto-hide and window spacing. GNOME opens on the desktop at sign-in. The Overview button opens a workspace view backed by blurred wallpaper. ArcMenu provides search and app categories. Super + Shift + S opens the screenshot tool. |
| Appearance | Dark and light GTK styling, HDR-aware menu blur, Settings sidebar fades and a dock visibility toggle, desktop clock and system widgets, window animations, a red wallpaper, and the animated Crimson Pulse cursor. |
| Files and terminal | Nautilus command bar, tabs and My Computer view, opening the current folder in a terminal, and file associations for Windows executables and installers. |
| Gaming and graphics | Wine and standalone Proton with a separate SDR launch option, optional Mesa Vulkan backports, and MangoHud, GOverlay and LACT integration. |
| Audio and devices | Bluetooth stereo policy, automatic Scarlett capture selection when present, HyperX Haste Studio, Hypercolor lighting, and Thermalright LCD keepalive for the supported cooler. |
| Memory and responsiveness | Compressed swap in RAM, disk swap as a fallback, and cleanup of hidden Shell menu graphics buffers. |
| Boot and storage | A readable GRUB menu that waits for a choice, Windows detection, Linux boot hardening, and an NTFS mount policy for a shared Data drive. |

The bundled Shell extensions contain local changes. When updating an extension, review its diff and check the dock, Start menu, and HDR blur before replacing the bundled copy.

## Installer options

Use `sh ./install.sh` to apply the user profile. The flags below add dependencies and system changes.

| Flag | Effect |
| --- | --- |
| `--all` | Runs the same full profile as `sh ./setup.sh`. Detects an existing GRUB installation and a unique NTFS volume labeled Data. |
| `--packages` | Installs Debian package dependencies for the desktop tools. |
| `--apps` | Installs Bitwarden and Parsec from Flathub. |
| `--boot` | Updates an existing GRUB installation with Windows discovery, a larger font, a persistent menu, and the boot arguments in `payload/system/etc/default/grub.d/`. |
| `--gaming` | Installs power profile support for the per-game launcher when needed. |
| `--memory` | Enables high-priority LZ4 compressed swap sized to half of RAM, up to 8 GiB. Applies the memory settings after compressed swap starts. |
| `--hdr` | Installs Mesa Vulkan from Debian backports. If a saved calibration is unavailable, enable HDR per monitor in GNOME Displays. |
| `--devices` | Installs the HyperX and Thermalright rules. The bundled LCD keepalive service targets the cooler used for this profile. |
| `--data-uuid UUID` | Adds a UDisks read-only fallback for the named NTFS volume. The full profile also configures a read/write automount where the target is available. |
| `--deb PATH` | Installs a supplied Debian package. Repeat for multiple packages. |
| `--dry-run` | Prints the selected installers and system options. |
| `--stage DIRECTORY` | Stages user files in a scratch directory for inspection. |

For an NTFS volume marked dirty by Windows, disable Fast Startup and fully shut down Windows. Run a Windows filesystem repair if the volume still reports errors.

## Gaming profile

`crimson-game` requests the system performance profile for a single launch using Power Profiles Daemon. It passes the game's arguments through, releases the profile when the command exits, and uses normal launch behavior if the system does not offer a performance profile. The optional `--upscale` flag launches [Gamescope](https://github.com/ValveSoftware/gamescope) with explicit render and output resolutions. It requires a separate Gamescope installation and changes the rendering resolution. Prefer a game’s built-in upscaler when available.

## Memory and boot checks

Inspect swap with `/usr/sbin/swapon --show` and current memory pressure with `cat /proc/pressure/memory`. The memory option keeps the existing disk swap and skips setup when zswap or another zram configuration already manages the machine.

The Easy Anti-Cheat v2 boot arguments ship in [the GRUB profile](../payload/system/etc/default/grub.d/97-eac-linux.cfg) and are applied by `--boot` or full setup when GRUB is present. Secure Boot, TPM, measured boot, and signed kernel support depend on the machine and distribution. [Epic’s EAC Linux v2 requirements](https://onlineservices.epicgames.com/news/introducing-easy-anti-cheat-linux-v2)

## Device profiles and upstream tools

- The full profile keeps Bluetooth playback in stereo and selects a Scarlett capture input by name when it finds one. Pair headphones and choose the playback device in GNOME on the destination PC.
- [Hypercolor](https://github.com/hyperb1iss/hypercolor/releases) supplies RGB control. The full setup keeps an existing Hypercolor install and enables startup. If a matching local layout exists, it restores the saved zones and effects.
- [Thermalright TRCC Linux](https://github.com/Lexonight1/thermalright-trcc-linux/releases) drives supported cooler LCDs. The full setup detects supported USB devices. When matching local files are present, it restores the saved display preset.
- [LACT](https://github.com/ilya-zlobintsev/LACT/releases) supplies GPU monitoring and tuning. Set power limits and fan curves for the GPU on the destination machine.
- [umu-launcher](https://github.com/Open-Wine-Components/umu-launcher) runs Proton outside Steam. The launcher uses a locally installed [GE-Proton](https://github.com/GloriousEggroll/proton-ge-custom/releases) build when one is available.
- The dock profile remembers application launcher IDs. Install and pin additional apps through GNOME for the apps you use.

Account sessions, disk UUIDs, device calibration, and vendor installers stay outside the public checkout. Keep device profiles and local packages in `local/`. Bundled extensions retain their upstream license files. The GRUB font uses DejaVu Sans. [DejaVu copyright](DejaVu-copyright)
