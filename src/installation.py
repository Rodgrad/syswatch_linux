"""User-local installation, desktop launchers and KDE wallpaper setup."""
import os
import shutil
import sys
from pathlib import Path

APP_ID = 'org.syswatch.SysWatch'


def data_home():
    return Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share')


def startup_path():
    return Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'autostart' / (APP_ID + '.desktop')


def bundled_path(relative):
    return Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / relative


def command():
    if getattr(sys, 'frozen', False):
        return [str(Path(sys.executable).resolve())]
    return [str(Path(sys.executable).resolve()), str(Path(__file__).with_name('main.py').resolve())]


def exec_value(arguments):
    quoted = []
    for value in arguments:
        value = str(value)
        if '\n' in value or '\r' in value or '=' in value:
            raise ValueError('Launcher paths cannot contain newlines or equals signs')
        value = ''.join('\\' + ch if ch in '\\"`$' else ch for ch in value).replace('%', '%%')
        quoted.append('"' + value + '"')
    return ' '.join(quoted).replace('\\', '\\\\')


def desktop_entry(arguments, wallpaper=False):
    return '\n'.join([
        '[Desktop Entry]', 'Type=Application', 'Name=Manjaro SysWatch',
        'Comment=Live system dashboard', 'Exec=' + exec_value(arguments),
        'Icon=utilities-system-monitor', 'Terminal=false', 'Categories=System;Monitor;',
        'StartupNotify=false', 'OnlyShowIn=KDE;' if wallpaper else '', '',
    ])


def write_entry(path, arguments, wallpaper=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(desktop_entry(arguments, wallpaper))


def set_startup(enabled, mode='widget', executable=None):
    if enabled:
        arguments = executable or command()
        arguments = arguments + {'widget': [], 'background': ['--under-windows'], 'fullscreen': ['--under-windows'], 'wallpaper': ['--wallpaper']}[mode]
        write_entry(startup_path(), arguments, mode == 'wallpaper')
    else:
        startup_path().unlink(missing_ok=True)


def install_app(autostart=False, startup_mode='widget'):
    if not getattr(sys, 'frozen', False):
        raise RuntimeError('Build the standalone package first with build.sh, then run its syswatch executable.')
    source = Path(sys.executable).resolve().parent
    destination = data_home() / 'syswatch'
    if source != destination.resolve():
        if destination.resolve().is_relative_to(source):
            raise RuntimeError('Installation directory cannot be inside the package directory')
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, destination, dirs_exist_ok=True, symlinks=True)
    executable = destination / Path(sys.executable).name
    write_entry(data_home() / 'applications' / (APP_ID + '.desktop'), [str(executable)])
    if autostart:
        set_startup(True, startup_mode, [str(executable)])
    return executable


def install_wallpaper():
    source = bundled_path('plasma-wallpaper/org.syswatch.live')
    destination = data_home() / 'plasma/wallpapers/org.syswatch.live'
    if not source.is_dir():
        raise RuntimeError('The KDE wallpaper package is missing from this installation')
    shutil.copytree(source, destination, dirs_exist_ok=True, symlinks=True)
    return destination


def uninstall_app():
    """Remove only SysWatch's user-local installation and integration files."""
    destination = data_home() / 'syswatch'
    if destination.exists() and not ((destination / 'syswatch').is_file() and (destination / '_internal').is_dir()):
        raise RuntimeError(f'Refusing to remove an unrecognized installation: {destination}')
    plugin = data_home() / 'plasma/wallpapers/org.syswatch.live'
    if plugin.exists():
        from PySide6.QtCore import QCoreApplication
        from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage
        application = QCoreApplication.instance() or QCoreApplication([])
        plasma = QDBusInterface('org.kde.plasmashell', '/PlasmaShell', 'org.kde.PlasmaShell', QDBusConnection.sessionBus())
        plasma.setTimeout(2000)
        if plasma.isValid():
            reply = plasma.call('evaluateScript', "var ds = desktops(); for (var i=0; i<ds.length; i++) { if (ds[i].wallpaperPlugin === 'org.syswatch.live') ds[i].wallpaperPlugin = 'org.kde.image'; }")
            if reply.type() == QDBusMessage.ErrorMessage:
                raise RuntimeError('Could not switch away from the SysWatch wallpaper: ' + reply.errorMessage())
    set_startup(False)
    (data_home() / 'applications' / (APP_ID + '.desktop')).unlink(missing_ok=True)
    if plugin.is_symlink():
        plugin.unlink()
    elif plugin.is_dir():
        shutil.rmtree(plugin)
    if destination.is_symlink():
        destination.unlink()
    elif destination.is_dir():
        shutil.rmtree(destination)
    cache = Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache') / 'syswatch'
    for name in ('wallpaper.png', 'wallpaper.tmp.png'):
        (cache / name).unlink(missing_ok=True)


def wallpaper_script_for_screen(x, y, width, height, connector=''):
    """Prefer KDE's connector mapping; geometry is a compatibility fallback."""
    import json
    geometry = dict(x=int(x), y=int(y), width=int(width), height=int(height))
    return 'var target = ' + json.dumps(geometry) + ';\nvar connector = ' + json.dumps(connector) + ';\n' + """
var connectorId = -1;
if (connector && typeof screenForConnector === 'function') connectorId = screenForConnector(connector);
var matches = desktopsForActivity(currentActivity());
var selected = false;
for (var i = 0; i < matches.length; i++) {
    if (matches[i].screen < 0) continue;
    var match = connectorId >= 0 && matches[i].screen === connectorId;
    if (connectorId < 0) {
        var area = screenGeometry(matches[i].screen);
        match = area.x === target.x && area.y === target.y &&
                area.width === target.width && area.height === target.height;
    }
    if (match) {
        if (matches[i].wallpaperPlugin === 'org.syswatch.live') matches[i].wallpaperPlugin = 'org.kde.image';
        matches[i].wallpaperPlugin = 'org.syswatch.live';
        selected = true;
        print('SYSWATCH_WALLPAPER_SET');
        break;
    }
}
if (!selected) throw new Error('The widget monitor was not found in the current KDE activity');
"""
