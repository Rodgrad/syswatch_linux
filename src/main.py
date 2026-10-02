"""Launch SysWatch or manage its standalone installation and startup entry."""
import argparse
import os
import sys


def main():
    parser = argparse.ArgumentParser(description='Manjaro SysWatch live system dashboard')
    parser.add_argument('--wallpaper', action='store_true', help='Run the KDE wallpaper renderer without a window')
    parser.add_argument('--under-windows', '--fullscreen', dest='under_windows', action='store_true', help='Start Big mode beneath other windows')
    parser.add_argument('--mode', choices=('small', 'big'), help='Choose the initial widget layout')
    parser.add_argument('--uninstall', action='store_true', help='Remove the user-local app, startup entry and KDE wallpaper plugin')
    parser.add_argument('--install', action='store_true', help='Install the standalone package for this user')
    parser.add_argument('--enable-startup', action='store_true', help='Enable launch at login and exit')
    parser.add_argument('--disable-startup', action='store_true', help='Disable launch at login and exit')
    parser.add_argument('--startup-mode', choices=('widget', 'background', 'fullscreen', 'wallpaper'), default='widget')
    parser.add_argument('--install-wallpaper', action='store_true', help='Install the KDE wallpaper plugin and exit')
    parser.add_argument('--smoke-test', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.enable_startup and args.disable_startup:
        parser.error('Choose either --enable-startup or --disable-startup')
    if args.uninstall and (args.install or args.enable_startup or args.disable_startup or args.install_wallpaper):
        parser.error("Use --uninstall separately from installation and startup options")
    from installation import install_app, set_startup, install_wallpaper, uninstall_app
    try:
        if args.uninstall:
            uninstall_app()
            print("SysWatch uninstalled; saved widget preferences were retained")
            return
        if args.install:
            installed = install_app(args.enable_startup, args.startup_mode)
            print(f'Installed: {installed}')
        elif args.enable_startup:
            set_startup(True, args.startup_mode)
            print('Launch at login enabled')
        if args.disable_startup:
            set_startup(False)
            print('Launch at login disabled')
        if args.install_wallpaper:
            print(f'KDE wallpaper installed: {install_wallpaper()}')
        if args.install or args.enable_startup or args.disable_startup or args.install_wallpaper:
            return
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f'SysWatch: {error}\n')
    if args.smoke_test or (args.wallpaper and not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    from widgets import SysWatchWidget
    app = QApplication([sys.argv[0]])
    app.setDesktopFileName('org.syswatch.SysWatch')
    widget = SysWatchWidget()
    app.aboutToQuit.connect(widget.close)
    if args.mode:
        widget.set_mode(args.mode)
    if args.wallpaper:
        app.setQuitOnLastWindowClosed(False)
        widget.set_wallpaper_enabled(True)
    else:
        widget.show()
        if args.under_windows:
            widget.toggle_background()
    import signal
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(250)
    if args.smoke_test:
        def check():
            valid = widget.data['memory']['total_gb'] > 0
            widget.close()
            print('SysWatch smoke test: ' + ('PASS' if valid else 'FAIL'), flush=True)
            app.exit(0 if valid else 1)
        QTimer.singleShot(4000, check)
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
