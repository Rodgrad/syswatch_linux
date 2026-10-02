# Manjaro SysWatch

The standalone package includes Python, Qt, and application dependencies.
Recipients do not need to install Python or run pip.

## Distribute and install

Share `dist/syswatch-linux-x86_64.tar.gz`. On the receiving Linux PC:

```sh
tar -xzf syswatch-linux-x86_64.tar.gz
cd syswatch
./syswatch
```

Click the header **gear icon**, then **Install app for this user**.
This copies the package to `~/.local/share/syswatch` and adds **Manjaro
SysWatch** to the application launcher. Select **Start at login** to enable
startup; select it again to disable it. Startup uses the current widget,
background, or wallpaper mode when enabled. To change the startup mode,
turn startup off and on after choosing the desired mode.

The gear menu also includes **Install and set KDE wallpaper**, which
installs the bundled Plasma plugin and selects it only on the monitor
containing the widget, in the current KDE activity. Other monitors and
activities keep their wallpaper. Move the widget to the desired monitor
before using this action. KDE virtual desktops within an activity share
wallpaper configuration; this action does not create per-workspace wallpapers.
Keep SysWatch running for live wallpaper updates. Enable **Start at login**
after setting the wallpaper to run the renderer at login without a widget.
No terminal commands or root privileges are required for the gear actions.

For installation directly from a terminal:

```sh
./install.sh --enable-startup
# Or start background at login:
./install.sh --enable-startup --startup-mode background
# Or run the KDE wallpaper renderer at login:
./install.sh --enable-startup --startup-mode wallpaper
```

To disable startup later:

```sh
~/.local/share/syswatch/syswatch --disable-startup
```

After installing, the downloaded archive and extracted original can be
removed. Run future copies from the app launcher. To upgrade, quit the app
and install the newly extracted package using the same installer.
Installation respects `XDG_DATA_HOME` and `XDG_CONFIG_HOME` when configured.

## Build the package

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-build.txt
PYTHON_BIN=.venv/bin/python bash build.sh
```

The result is an executable folder plus a compressed distribution archive.
Keep the complete folder together; `_internal` contains its runtime libraries.
The GitHub **Build Linux package** workflow builds on Ubuntu 22.04 for a
broader compatibility baseline and uploads the archive as a downloadable
artifact. Run it from Actions or push a `v*` tag; it does not publish a release.

Packages target Linux x86-64, not Windows, macOS, or ARM. Build on the oldest
Linux release you intend to support: PyInstaller does not bundle glibc, and
newer systems can usually run older builds but older systems cannot necessarily
run newer builds. `BUILD-INFO.txt` records the build's glibc version and CPU
architecture. The locally built Manjaro package uses glibc 2.44; use the Ubuntu
workflow for older PCs and test on your target distributions before sharing.
GPU telemetry still needs the receiving PC's NVIDIA driver and `nvidia-smi`.

## Run from source

Install `requirements.txt`, then run `python main.py`.

Click **BIG MODE** / **SMALL MODE** or press **B** to switch layouts.
The chosen layout and position are remembered. Drag the header to move;
on Wayland the compositor handles the move. Click X to close.

CPU model, cores, memory capacity, GPU names and active network interfaces
are detected automatically. CPU, memory, network, disks and processes refresh
every second in a background worker. NVIDIA telemetry is polled every five
seconds with bounded subprocess timeouts. Missing sensor readings show N/A;
GPU model detection uses `lspci` when `nvidia-smi` is unavailable. Graphs show
the most recent 60 samples, initially padded with zeroes.

Click **Under windows (F)** at the bottom-right, press **F**, or use the
right-click menu to put the fixed-size Big dashboard beneath other windows. Exiting
restores the previous Small or Big layout and window position. Click
**Leave background (Esc / F)**, press **Esc** or **F**, or choose **Leave background** from the right-click menu to restore the widget.

Keyboard shortcuts work while SysWatch has focus. Click an exposed part
of the dashboard, or select **Manjaro SysWatch** with Alt+Tab first when
another application has focus. The exit button also works without a keyboard.
The selected layout and previous window position are restored on exit.

Under windows requests the window system's stay-below hint. KDE Plasma 6
additionally gets a temporary KWin script that keeps this app's background
window below other windows and releases it when leaving background. It is
unloaded on app exit and does not change persistent KWin settings. Other
desktops depend on their support for Qt's stay-below hint. KWin behavior
needs validation in an actual KDE session.

## KDE-only wallpaper mode

The existing Plasma 6 wallpaper package works on KDE Wayland and KDE X11.
Install it once from the project directory:

```sh
kpackagetool6 --type Plasma/Wallpaper --install plasma-wallpaper/org.syswatch.live
```

Choose **SysWatch Live** in KDE's **Desktop and Wallpaper** settings. Then
select **KDE wallpaper mode** in the widget's right-click menu or press **W**
to start exporting live frames. Select it again to stop exporting. Alternatively,
run `python main.py --wallpaper` for a renderer without a visible widget;
stop that renderer with Ctrl+C. Only one renderer should export at a time.
The wallpaper keeps desktop icons interactive and scales to fit the screen.
The widget remains available when wallpaper mode is enabled through its menu.
The plugin is KDE-only; background and the regular widget do not need it.

## Minimize and uninstall

Click the header **minus button** or choose **Minimize / hide to tray** in
the gear menu. Wallpaper rendering continues while the widget is hidden.
Click the SysWatch tray icon or choose **Show SysWatch** to reopen it.
The tray menu includes Settings, Uninstall, and Quit. Without a system tray,
the minimize action uses the taskbar instead. Wallpaper startup also shows
a tray icon in a desktop session; command-line headless rendering remains supported.

Use **gear menu → Uninstall SysWatch** or the tray's **Uninstall SysWatch**
action. After confirmation, SysWatch disables startup, removes its launcher,
installed executable folder, KDE wallpaper plugin and exported frames, then
quits. In a running KDE session, desktops using SysWatch switch back to KDE's
image wallpaper before the plugin is removed. Saved window preferences and
downloaded distribution archives are retained.

The terminal equivalent is:

```sh
~/.local/share/syswatch/syswatch --uninstall
```

Quit any other SysWatch instances before uninstalling. If uninstalling while
Plasma is not running, select an available wallpaper when next logging in.

After extracting a newer distribution, quit the previous running instance
and use **Install app for this user** (or `./install.sh`) again to upgrade.
Then launch SysWatch from the application menu. Rebuilding or downloading
an archive does not replace a previously installed or running copy.

Wallpaper actions both install/select the KDE plugin on the widget monitor. Frames render at that monitor's native pixel resolution, including display scaling.
