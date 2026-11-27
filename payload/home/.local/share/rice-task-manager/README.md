# Rice Task Manager

A Windows 11 inspired task manager for Linux. Native GTK4, dark sidebar, live process table, configurable colors. No browser, server, pip packages or background daemon. Works independently of Omarchy, Hyprland and the original rice. Linux only; this is not a Windows executable.

## Install

Extract the ZIP, open a terminal inside the extracted folder, and install dependencies for your distro:

```bash
# Arch / Omarchy
sudo pacman -S --needed python python-gobject gtk4 python-cairo
# Ubuntu / Debian
sudo apt install python3 python3-gi gir1.2-gtk-4.0 python3-cairo python3-gi-cairo
# Fedora
sudo dnf install python3 python3-gobject gtk4 python3-cairo
```

Then run:

```bash
bash install.sh
```

Open **Task Manager** in your app launcher, or run `~/.local/bin/rice-task-manager`. Installation needs no sudo and leaves existing color settings intact. Run `python3 task_manager.py` for a preview without installing. Requires Python 3.9+, GTK 4 and a graphical Linux session (Wayland or X11). Tested on Arch with GTK 4; other distro commands are provided for convenience, not independently tested.

## Appearance settings

Open **Settings → Appearance** to choose how Task Manager gets its colors. Select a theme and click **Apply theme**.

- **Automatic** follows a custom GTK theme, a `GTK_THEME` override, or your GTK4 user stylesheet when GTK can resolve their colors. With stock GTK defaults or unavailable colors, it uses your saved app palette.
- **Follow GTK theme** also uses the stock GTK palette when it is active. The app uses GTK4 theme variables and named colors. For GTK3-only themes with named colors in their stylesheet, it reads those colors and keeps its GTK4 widgets.
- **Saved app palette** uses your saved colors, with Lumina as the default. Select **Lumina**, **Black Raptor**, or **Mockup Blue** to load a bundled palette.

Text size and row spacing apply in every mode. Color and settings changes are picked up within two seconds, even when process updates are paused. Restart the app after editing the desktop GTK stylesheet itself.

## Colors

Edit `~/.config/rice-task-manager/colors.json`. If you use `XDG_CONFIG_HOME`, the file lives under that directory instead. The app picks up edits within two seconds, even when process updates are paused.

```json
{
  "theme_mode": "palette",
  "background": "#11111b",
  "sidebar": "#0c0c14",
  "surface": "#1e1e2e",
  "border": "#313244",
  "foreground": "#cdd6f4",
  "muted": "#9aa6bd",
  "accent": "#89b4fa",
  "metric": "#89dceb",
  "selection": "#313c53",
  "font_size": 16,
  "row_padding": 8
}
```

Set `theme_mode` to `"palette"` to use the JSON colors, `"gtk"` to follow GTK, or `"auto"` for Automatic. An omitted mode uses Automatic. Use six-digit hex colors. `font_size` accepts 14–22 pixels and `row_padding` accepts 4–16 pixels. `accent` controls the selected navigation stripe and graph, `metric` the usage figures, `surface` buttons and cards, and `selection` selected rows and navigation. Missing or invalid individual colors use Lumina defaults.

The title bar and sidebar use the exact Arch symbol from the Lumina top bar, bundled as vector outlines so friends do not need a Nerd Font. Its color follows the active palette. Three presets are included. For example, from the extracted folder:

```bash
cp palettes/black-raptor.json ~/.config/rice-task-manager/colors.json
# Then select Saved app palette in Settings to apply it.
```

Lumina uses soft blue/cyan on dark violet. Black Raptor uses amber on charcoal. Mockup Blue recreates the original steel blue concept. On the original desktop, the rice manager owns this file and restores each rice's palette when switching; save changes into that rice to retain them. Friends do not need the rice manager.

## Features and controls

- Processes / Details: live Linux process name, state, CPU, resident memory, disk I/O, PID and owner. Click any column heading to sort; click it again to reverse the direction. Numeric columns sort their actual values, and the chosen sort remains active through live refreshes. Processes opens with CPU descending; PID and owner are in Details to keep the main table spacious. Search filters name, PID and owner.
- Performance: a six-card dashboard for CPU, memory, busiest physical disk, total network throughput, GPU and system information. Switch between 60 and 120 seconds of history. History begins when this window opens; unavailable earlier samples are left blank.
- App history: observed CPU time, disk I/O and peak per-process resident memory grouped by process name. Remains available after processes exit, until you close this window or press Reset history. It is session-only; the app does not invent seven-day history or Windows tile-update statistics.
- Startup apps: toggle desktop autostart entries with confirmation. Changes apply at next login and write a user override, preserving the original command. Does not include every compositor or systemd startup mechanism; no startup impact is guessed.
- Users: expand a desktop account to inspect its processes. Shows up to 50 processes per account; Details contains all processes. These are accounts owning processes, not a count of login sessions.
- Details: PID, Linux scheduler state, CPU, memory and owner, with full command lines available in tooltips.
- Services: switch between user and system service lists. Start, Stop and Restart operate on the selected **user** service after confirmation. System services are read-only; no automatic privilege elevation.
- Settings: palette presets, font size, row spacing and an Open color file button.
- Pause / Resume freezes metrics. Right-click any process row in Processes or Details and choose **End task**, or use the toolbar button. End task asks for confirmation and sends SIGTERM to the selected process, subject to your normal user permissions. PID reuse is checked; PID 1 and the task manager itself are protected.

“Running” in Processes means the process is healthy and present, including normal waiting between tasks. Details shows whether the Linux scheduler currently considers it executing, sleeping, waiting for I/O, stopped or a zombie. The CPU percentage covers the sampling interval, so a process can show recent CPU usage while currently waiting.

Process CPU can exceed 100% for multithreaded applications (100% per logical CPU). Total CPU is normalized to 0–100%. Resident memory can count shared pages in multiple processes. Kernel threads may report zero memory. Disk counters for other users may be inaccessible and display zero. Per-process network/GPU columns are omitted because reliable attribution needs additional platform-specific support. The Performance dashboard shows total network and GPU metrics. GPU telemetry supports NVIDIA through an installed `nvidia-smi` command and Linux DRM drivers exposing busy/VRAM sysfs counters (commonly AMD); unsupported readings display Unavailable. Disk active time and throughput describe the busiest physical device during each sample, excluding partitions and virtual devices. The memory card uses Linux available-memory accounting.

The app reads local `/proc` and `/sys` counters, `ip -j address`, optional NVIDIA telemetry, and systemd service lists. Only explicitly confirmed startup or user-service actions change other system state. It makes no network requests and stores no process history. The ZIP contains only source, documentation and palettes, never personal rice snapshots or credentials.

## Share on Discord

Send `rice-task-manager.zip` as an attachment. Your friends extract it and follow this README. No build step is needed. The archive is small enough for a normal Discord attachment. To make your own ZIP, zip this folder without `__pycache__` or any personal configuration. You can include your customized colors as an additional palette JSON.

## Custom GTK themes and global fades

The app styles its text, inputs, scrollbars and scroll edges using the active palette. GTK animations and CSS transitions are disabled inside this process to keep the process list steady during live refreshes.

After upgrading, close and reopen Task Manager to load the updated styles. If the **whole window** still fades or becomes translucent, that effect may be applied by the compositor; GTK styling cannot override it. Exclude application ID `local.rice.TaskManager` in your compositor's effect rules. The exact syntax depends on the compositor and version.

## Verify / troubleshoot

```bash
python3 task_manager.py --self-test
python3 test_task_manager.py
python3 test_gtk_theme.py  # Optional graphical palette-switching and theme-isolation test
RICE_TASK_MANAGER_UI_TEST=1 python3 task_manager.py
```

The UI test uses a separate window, visits all eight pages, tests search and numeric sorting in both directions through live refreshes, then closes its own window. Management tests use temporary startup files and mocked service execution; they do not change your real startup entries or services. If Python reports `No module named gi` or `cairo`, install the dependencies above and use your distro Python, outside a virtualenv. If startup fails, run the app from a terminal to see errors. Very old GTK releases may lack required widgets.

## Uninstall

```bash
rm -rf ~/.local/share/rice-task-manager
rm -f ~/.local/bin/rice-task-manager ~/.local/share/applications/rice-task-manager.desktop
# Optional: remove your saved colors
rm -rf ~/.config/rice-task-manager
```

Adjust these paths if you set `XDG_DATA_HOME` or `XDG_CONFIG_HOME`.

## Optional Hyprland layout

The original desktop has a rice-managed floating rule so this opens at 1280 × 820 with an opaque text surface. Friends using other desktops can resize normally. On current Lua-based Omarchy, the equivalent user rule is:

```lua
o.window("^local.rice.TaskManager.*$", {
  float = true, center = true, size = {1280, 820},
  opacity = "1 override 1 override", tag = "-default-opacity"
})
```

This is optional and specific to Lua-based Omarchy; the installer does not modify your window manager.

Licensed under MIT. This is an independent Linux utility, unaffiliated with Microsoft.
