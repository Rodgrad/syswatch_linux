"""Custom painted, compact Manjaro telemetry console."""
import math
import threading
import logging
import tempfile
import json
import os
from pathlib import Path
from datetime import datetime
from collections import deque
from metrics import get_snapshot
from PySide6.QtWidgets import QWidget, QMenu, QPushButton, QMessageBox, QSystemTrayIcon, QApplication
from PySide6.QtGui import QColor, QPainter, QFont, QPen, QPainterPath, QPixmap, QShortcut, QKeySequence, QIcon
from PySide6.QtCore import Qt, QPoint, QRectF, QSettings, QSize, QThread, Signal, QStandardPaths

GREEN = '#00edbd'
CYAN = '#25e5ef'
MAGENTA = '#eb47cd'
MUTED = '#7899a7'

class MetricsWorker(QThread):
    snapshot = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.stop_event = threading.Event()

    def run(self):
        while not self.stop_event.is_set():
            try:
                self.snapshot.emit(get_snapshot())
            except Exception:
                # A transient OS read failure must not stop subsequent updates.
                logging.exception('Unable to collect system metrics')
            if self.stop_event.wait(1):
                break


class SysWatchWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Manjaro SysWatch')
        self.normal_flags = Qt.Window | Qt.FramelessWindowHint
        self.setWindowFlags(self.normal_flags)
        self.setFocusPolicy(Qt.StrongFocus)
        self.kwin_script = None
        self.kwin_directory = None
        self.background_title = f'Manjaro SysWatch Background [{os.getpid()}]'
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.settings = QSettings('syswatch', 'position')
        self.move(self.settings.value('pos', QPoint(100, 100)))
        self.drag_offset = None
        self.data = dict(hardware=dict(cpu='Detecting CPU', gpu='Detecting GPU'), cpu=dict(percent=0, freq=None, cores=None, threads=None, temp=None),
                         memory=dict(used_gb=0, total_gb=0, percent=0, available=0, cached=0),
                         gpu=dict(name='GPU DATA UNAVAILABLE', util=None),
                         network=dict(rx=0, tx=0), uptime=0, kernel='Loading',
                         disks=[], processes=[], interface='NETWORK')
        self.histories = {key: deque([0] * 60, maxlen=60) for key in ('cpu', 'gpu', 'rx', 'tx', 'temp', 'power')}
        self.worker = MetricsWorker(self)
        self.worker.snapshot.connect(self.receive_snapshot)
        self.worker.start()
        self.wallpaper_size = self.settings.value('wallpaper_size', QSize(1280, 820))
        self.wallpaper_enabled = False
        self.background_enabled = False
        self.mode = 'small'
        self.view_scale = 1.0
        self.set_mode(self.settings.value('mode', 'small'))
        self.background_button = QPushButton('Under windows (F)', self)
        self.background_button.setStyleSheet(
            'QPushButton {background: #102c38; color: #25e5ef; border: 1px solid #25e5ef; '
            'padding: 6px; font-family: "DejaVu Sans Mono"; font-weight: bold;} '
            'QPushButton:hover {background: #1b4656;}')
        self.background_button.clicked.connect(self.toggle_background)
        self.shortcuts = []
        for key, callback in [('F', self.toggle_background), ('Escape', self.exit_background), ('B', self.toggle_mode), ('W', self.toggle_wallpaper)]:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.WindowShortcut)
            shortcut.setAutoRepeat(False)
            shortcut.activated.connect(callback)
            self.shortcuts.append(shortcut)
        self.position_background_button()
        self._closing = False
        self.tray = QSystemTrayIcon(self.make_tray_icon(), self)
        self.tray.setToolTip('Manjaro SysWatch')
        self.tray_menu = QMenu(self)
        self.tray_menu.addAction('Show SysWatch', self.restore_from_tray)
        self.tray_menu.addAction('Hide SysWatch', self.minimize_widget)
        self.tray_menu.addAction('Settings', self.show_settings_from_tray)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction('Uninstall SysWatch', self.uninstall_from_settings)
        self.tray_menu.addAction('Quit', self.quit_application)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.activated.connect(self.tray_activated)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def make_tray_icon(self):
        image = QPixmap(32, 32)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        painter.fillRect(QRectF(2, 2, 28, 28), QColor('#07131e'))
        for rect in (QRectF(6,7,5,19), QRectF(13,7,5,6), QRectF(13,16,5,10), QRectF(21,5,5,21)):
            painter.fillRect(rect, QColor(GREEN))
        painter.end()
        return QIcon(image)

    def minimize_rect(self):
        return QRectF(1194, 30, 20, 32) if self.mode == 'big' else QRectF(378, 18, 24, 24)

    def draw_minimize_button(self, painter):
        rect = self.minimize_rect()
        self.line(painter, rect.left()+5, rect.center().y(), rect.right()-5, rect.center().y(), CYAN, 2)

    def minimize_widget(self):
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
            QApplication.instance().setQuitOnLastWindowClosed(False)
            self.hide()
        else:
            # Remain recoverable through the taskbar when there is no tray.
            self.showMinimized()

    def restore_from_tray(self):
        if self.background_enabled:
            self.showNormal()
            self.lower()
        else:
            self.showNormal()
        self.activateWindow()
        self.setFocus(Qt.OtherFocusReason)

    def show_settings_from_tray(self):
        self.restore_from_tray()
        self.open_settings_menu(self.mapToGlobal(self.settings_rect().center().toPoint()))

    def tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.restore_from_tray()

    def quit_application(self):
        self.close()
        QApplication.instance().quit()

    def uninstall_from_settings(self):
        from installation import uninstall_app
        result = QMessageBox.question(self, 'Uninstall SysWatch',
            'Remove the installed app, startup entry and KDE wallpaper plugin? Saved widget preferences will be kept.',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if result != QMessageBox.Yes:
            return
        was_wallpaper = self.wallpaper_enabled
        try:
            self.wallpaper_enabled = False
            self.worker.stop_event.set()
            self.worker.wait()
            uninstall_app()
        except (OSError, RuntimeError) as error:
            self.wallpaper_enabled = was_wallpaper
            if not self._closing:
                self.worker.stop_event.clear()
                self.worker.start()
            QMessageBox.warning(self, 'Uninstall SysWatch', str(error))
            return
        self.quit_application()

    def receive_snapshot(self, data):
        self.data = data
        for key, value in [('cpu', data['cpu']['percent']), ('gpu', data['gpu'].get('util')),
                           ('rx', data['network']['rx'] / 1024**2), ('tx', data['network']['tx'] / 1024**2),
                           ('temp', data['gpu'].get('temp')), ('power', data['gpu'].get('power'))]:
            self.histories[key].append(value or 0)
        if self.wallpaper_enabled:
            self.export_wallpaper()
        self.update()

    def gpu_name(self):
        return self.data['gpu']['name'] if self.data['gpu'].get('util') is not None else self.data['hardware']['gpu']

    def gpu_value(self, key, suffix=''):
        value = self.data['gpu'].get(key)
        return f'{value:.0f}{suffix}' if value is not None else 'N/A'

    def memory_text(self):
        mem = self.data['memory']
        return f"{mem['used_gb']:.1f} / {mem['total_gb']:.1f} GB"

    def status_text(self):
        uptime = int(self.data['uptime'])
        return f"LIVE | UP {uptime//3600:02}:{uptime//60%60:02}:{uptime%60:02}"

    def set_mode(self, mode):
        self.mode = mode if mode in ('small', 'big') else 'small'
        width, height = (1280, 820) if self.mode == 'big' else (460, 920)
        screen = self.screen()
        available = screen.availableGeometry() if screen else None
        self.view_scale = min(1.0, available.width() / width, available.height() / height) if available else 1.0
        self.setFixedSize(QSize(round(width * self.view_scale), round(height * self.view_scale)))
        if available:
            self.move(max(available.left(), min(self.x(), available.right() - self.width() + 1)),
                      max(available.top(), min(self.y(), available.bottom() - self.height() + 1)))
        self.settings.setValue('mode', self.mode)
        self.position_background_button()
        self.update()

    def toggle_mode(self):
        self.set_mode('small' if self.mode == 'big' else 'big')

    def mode_rect(self):
        return QRectF(1050, 30, 142, 32) if self.mode == 'big' else QRectF(334, 90, 94, 25)

    def settings_rect(self):
        return QRectF(1008, 30, 28, 32) if self.mode == 'big' else QRectF(244, 24, 28, 28)

    def draw_settings_button(self, p):
        rect = self.settings_rect()
        center = rect.center()
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(CYAN), 2))
        p.drawEllipse(center, 7, 7)
        p.drawEllipse(center, 2, 2)
        for i in range(8):
            angle = i * math.pi / 4
            self.line(p, center.x()+8*math.cos(angle), center.y()+8*math.sin(angle),
                      center.x()+11*math.cos(angle), center.y()+11*math.sin(angle), CYAN, 3)

    def install_from_settings(self):
        from installation import install_app
        try:
            installed = install_app(self.startup_enabled(), self.startup_mode())
            QMessageBox.information(self, 'SysWatch installed', f'Installed for your account.\nApp launcher: Manjaro SysWatch\nLocation: {installed}')
        except (OSError, RuntimeError, ValueError) as error:
            QMessageBox.warning(self, 'Installation', str(error))

    def startup_enabled(self):
        from installation import startup_path
        return startup_path().is_file()

    def startup_mode(self):
        return 'wallpaper' if self.wallpaper_enabled else ('background' if self.background_enabled else 'widget')

    def set_startup_from_settings(self, enabled):
        from installation import set_startup, data_home, command
        try:
            installed = data_home() / 'syswatch/syswatch'
            executable = [str(installed)] if installed.is_file() else command()
            set_startup(enabled, self.startup_mode(), executable)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, 'Start at login', str(error))

    def set_kde_wallpaper(self):
        from installation import install_wallpaper, wallpaper_script_for_screen
        try:
            from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage
            plasma = QDBusInterface('org.kde.plasmashell', '/PlasmaShell', 'org.kde.PlasmaShell', QDBusConnection.sessionBus())
            plasma.setTimeout(2000)
            if not plasma.isValid():
                raise RuntimeError('Set KDE wallpaper is available in a KDE Plasma session.')
            install_wallpaper()
            screen = self.screen()
            if screen is None:
                raise RuntimeError('Could not identify the screen containing SysWatch.')
            self.wallpaper_size = QSize(round(screen.size().width()*screen.devicePixelRatio()), round(screen.size().height()*screen.devicePixelRatio()))
            self.settings.setValue('wallpaper_size', self.wallpaper_size)
            self.set_wallpaper_enabled(True)
            geometry = screen.geometry()
            script = wallpaper_script_for_screen(geometry.x(), geometry.y(), geometry.width(), geometry.height(), screen.name())
            reply = plasma.call('evaluateScript', script)
            if reply.type() == QDBusMessage.ErrorMessage:
                raise RuntimeError(reply.errorMessage())
            output = '\n'.join(str(item) for item in reply.arguments())
            if 'SYSWATCH_WALLPAPER_SET' not in output:
                raise RuntimeError(output or 'KDE did not confirm the wallpaper selection.')
            if self.startup_enabled():
                self.set_startup_from_settings(True)
            QMessageBox.information(self, 'KDE wallpaper', f'SysWatch wallpaper is set on {screen.name()} in the current KDE activity. Keep SysWatch running to update it.')
        except (ImportError, OSError, RuntimeError) as error:
            QMessageBox.warning(self, 'KDE wallpaper', str(error))

    def close_rect(self):
        return QRectF(1218, 30, 30, 32) if self.mode == 'big' else QRectF(410, 24, 24, 24)

    def draw_mode_button(self, p):
        rect = self.mode_rect()
        p.setBrush(QColor('#102c38'))
        p.setPen(QPen(QColor(CYAN), 1))
        p.drawPath(self.angular(rect.x(), rect.y(), rect.width(), rect.height(), 5))
        p.setFont(QFont('DejaVu Sans Mono', 9, QFont.Bold))
        p.setPen(QColor(CYAN))
        p.drawText(rect, Qt.AlignCenter, 'SMALL MODE' if self.mode == 'big' else 'BIG MODE')
        p.setBrush(Qt.NoBrush)

    def toggle_wallpaper(self):
        if self.wallpaper_enabled:
            self.set_wallpaper_enabled(False)
        else:
            self.set_kde_wallpaper()

    def set_wallpaper_enabled(self, enabled):
        self.wallpaper_enabled = enabled
        if enabled:
            self.export_wallpaper()

    def export_wallpaper(self):
        directory = Path(QStandardPaths.writableLocation(QStandardPaths.GenericCacheLocation)) / 'syswatch'
        directory.mkdir(parents=True, exist_ok=True)
        picture = QPixmap(self.wallpaper_size)
        picture.fill(QColor('#07131e'))
        painter = QPainter(picture)
        painter.setRenderHint(QPainter.Antialiasing)
        factor = min(picture.width()/1280, picture.height()/820)
        painter.translate((picture.width()-1280*factor)/2, (picture.height()-820*factor)/2)
        painter.scale(factor, factor)
        self.paint_big(painter)
        painter.end()
        temporary = directory / 'wallpaper.tmp.png'
        if picture.save(str(temporary), 'PNG'):
            os.replace(temporary, directory / 'wallpaper.png')

    def enable_kwin_background(self):
        """Use KWin's own keepBelow property where Wayland ignores Qt's hint."""
        if self.kwin_script is not None:
            return
        try:
            from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage
            interface = QDBusInterface('org.kde.KWin', '/Scripting', 'org.kde.kwin.Scripting', QDBusConnection.sessionBus())
            interface.setTimeout(1000)
            if not interface.isValid():
                return
            self.kwin_directory = tempfile.TemporaryDirectory(prefix='syswatch-kwin-')
            path = Path(self.kwin_directory.name) / 'background.js'
            path.write_text("const targetTitle = " + json.dumps(self.background_title) + ";\n" +
                """function watch(window) {
    let owned = false;
    function update() {
        if (window.caption === targetTitle) {
            owned = true;
            window.keepAbove = false;
            window.keepBelow = true;
        } else if (owned) {
            window.keepBelow = false;
            owned = false;
        }
    }
    window.captionChanged.connect(update);
    update();
}
workspace.windowList().forEach(watch);
workspace.windowAdded.connect(watch);
""")
            name = 'syswatch-background-' + str(os.getpid())
            reply = interface.call('loadScript', str(path), name)
            if reply.type() == QDBusMessage.ErrorMessage or not reply.arguments() or reply.arguments()[0] < 0:
                logging.warning('KWin background integration unavailable: %s', reply.errorMessage())
                self.kwin_directory.cleanup()
                self.kwin_directory = None
                return
            script = QDBusInterface('org.kde.KWin', '/Scripting/Script' + str(reply.arguments()[0]), 'org.kde.kwin.Script', QDBusConnection.sessionBus())
            script.setTimeout(1000)
            reply = script.call('run')
            if reply.type() == QDBusMessage.ErrorMessage:
                interface.call('unloadScript', name)
                logging.warning('KWin background script failed: %s', reply.errorMessage())
                self.kwin_directory.cleanup()
                self.kwin_directory = None
                return
            self.kwin_script = (interface, name)
        except (ImportError, OSError, RuntimeError):
            logging.exception('KWin background integration unavailable')

    def exit_background(self):
        if self.background_enabled:
            self.toggle_background()

    def toggle_background(self):
        self.drag_offset = None
        if not self.background_enabled:
            self.normal_position = self.pos()
            self.normal_mode = self.mode
            self.set_mode('big')
            self.background_enabled = True
            self.enable_kwin_background()
            self.setWindowTitle(self.background_title)
            self.setWindowFlags(self.normal_flags | Qt.WindowStaysOnBottomHint)
            self.showNormal()
            self.lower()
        else:
            self.background_enabled = False
            self.setWindowTitle('Manjaro SysWatch')
            self.setWindowFlags(self.normal_flags)
            self.showNormal()
            self.set_mode(self.normal_mode)
            self.move(self.normal_position)
            self.activateWindow()
        self.position_background_button()
        self.setFocus(Qt.OtherFocusReason)
        self.update()

    def position_background_button(self):
        if not hasattr(self, 'background_button'):
            return
        if not self.background_enabled and self.mode == 'small':
            self.background_button.setGeometry(round(28*self.view_scale), round(90*self.view_scale), round(108*self.view_scale), round(25*self.view_scale))
            font = self.background_button.font()
            font.setPixelSize(max(7, round(9*self.view_scale)))
            self.background_button.setFont(font)
            self.background_button.setText('Under windows' if self.view_scale < 0.9 else 'Under windows (F)')
        else:
            self.background_button.setText('Exit background (Esc / F)' if self.background_enabled else 'Under windows (F)')
            width = 218 if self.background_enabled else 132
            self.background_button.setGeometry(max(0, self.width()-width-18), self.height()-36, width, 28)
        self.background_button.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.position_background_button()

    def contextMenuEvent(self, event):
        self.open_settings_menu(event.globalPos())

    def open_settings_menu(self, position):
        menu = QMenu(self)
        install = menu.addAction('Install app for this user')
        startup = menu.addAction('Start at login')
        startup.setCheckable(True)
        startup.setChecked(self.startup_enabled())
        uninstall = menu.addAction('Uninstall SysWatch')
        hide_action = menu.addAction('Minimize / hide to tray')
        set_wallpaper = menu.addAction('Install and set KDE wallpaper')
        menu.addSeparator()
        switch = menu.addAction('Switch Big / Small mode')
        background = menu.addAction('Exit background (Esc / F)' if self.background_enabled else 'Big mode under windows (F)')
        wallpaper = menu.addAction('KDE wallpaper mode')
        wallpaper.setCheckable(True)
        wallpaper.setChecked(self.wallpaper_enabled)
        exit_action = menu.addAction('Quit')
        action = menu.exec(position)
        if action == hide_action:
            self.minimize_widget()
        elif action == uninstall:
            self.uninstall_from_settings()
        elif action == install:
            self.install_from_settings()
        elif action == startup:
            self.set_startup_from_settings(startup.isChecked())
        elif action == set_wallpaper:
            self.set_kde_wallpaper()
        elif action == switch:
            self.toggle_mode()
        elif action == background:
            self.toggle_background()
        elif action == wallpaper:
            self.toggle_wallpaper()
        elif action == exit_action:
            self.quit_application()

    def text(self, p, x, y, value, size=12, color=MUTED, bold=False):
        p.setFont(QFont('DejaVu Sans Mono', size, QFont.Bold if bold else QFont.Normal))
        p.setPen(QColor(color))
        p.drawText(QRectF(x, y, 410-x, 30), Qt.AlignLeft | Qt.AlignVCenter, str(value))

    def angular(self, x, y, w, h, cut=12):
        path = QPainterPath()
        path.moveTo(x+cut, y)
        for px, py in [(x+w-cut,y),(x+w,y+cut),(x+w,y+h-cut),(x+w-cut,y+h),(x+cut,y+h),(x,y+h-cut),(x,y+cut)]:
            path.lineTo(px,py)
        path.closeSubpath()
        return path

    def line(self, p, x1,y1,x2,y2,color=MUTED,width=1):
        p.setPen(QPen(QColor(color),width))
        p.drawLine(QPoint(int(x1),int(y1)),QPoint(int(x2),int(y2)))

    def paintEvent(self, event):
        p=QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        self.paint_offset = QPoint(0, 0)
        p.translate(self.paint_offset)
        p.scale(self.view_scale, self.view_scale)
        if self.mode == 'big':
            self.paint_big(p)
        else:
            self.paint_small(p)
        self.draw_mode_button(p)
        self.draw_settings_button(p)
        self.draw_minimize_button(p)
        p.end()

    def paint_small(self, p):
        p.save()
        p.translate(10,10)
        frame=self.angular(4,4,432,892,22)
        for width,alpha in [(14,12),(8,22),(3,70)]:
            c=QColor(GREEN); c.setAlpha(alpha)
            p.setPen(QPen(c,width)); p.drawPath(frame)
        p.setBrush(QColor('#07131e')); p.setPen(QPen(QColor('#288b8c'),1)); p.drawPath(frame)
        p.setBrush(Qt.NoBrush)
        for y in range(16,890,6): self.line(p,12,y,428,y,'#0a1a25')
        for x in [8,432]:
            for y in [34,180,386,560,790,866]:
                self.line(p,x,y,x,y+22,GREEN,2)
        for x,y,s in [(4,4,1),(436,4,-1),(4,896,1),(436,896,-1)]:
            self.line(p,x+22*s,y,x+42*s,y,CYAN,3)
        # Manjaro mark, drawn from three bars.
        p.setPen(Qt.NoPen); p.setBrush(QColor(GREEN))
        for r in [QRectF(30,30,12,40),QRectF(44,30,12,12),QRectF(44,46,12,24),QRectF(60,24,12,46)]: p.drawRect(r)
        self.text(p,88,24,'MANJARO',19,'#eef6f7',True)
        self.text(p,90,51,'L I N U X',9)
        self.text(p,291,18,'SYSTEM  //',8)
        self.text(p,289,34,datetime.now().strftime('%H:%M'),20,CYAN,True)
        p.setFont(QFont('DejaVu Sans Mono', 7))
        p.setPen(QColor(MUTED))
        p.drawText(QRectF(290, 60, 125, 16), Qt.AlignLeft | Qt.AlignVCenter, datetime.now().strftime('%a %d %b %Y').upper())
        self.line(p,270,20,252,76,'#25626f')
        self.line(p,24,88,416,88,'#235360')
        self.text(p,141,83,self.status_text(),7)
        self.line(p,409,22,417,30,MUTED); self.line(p,417,22,409,30,MUTED)
        p.setBrush(Qt.NoBrush)
        for y,h,title,model in [(112,294,'CPU',self.data['hardware']['cpu'][:22]),(416,150,'MEMORY',f"{self.data['memory']['total_gb']:.0f} GB RAM"),(576,204,'GPU',self.gpu_name()[:22]),(790,92,'NETWORK',self.data['interface'][:20])]:
            p.setPen(QPen(QColor('#28606b'),1)); p.drawPath(self.angular(21,y,398,h,12))
            self.text(p,66,y+4,title,13,CYAN,True)
            self.text(p,252,y+4,model,8)
            p.setPen(QPen(QColor(CYAN),1)); p.drawRect(QRectF(34,y+12,18,15))
            self.line(p,30,y+38,410,y+38,'#163c48')
        self.text(p,270,182,f"CORES {self.data['cpu']['cores'] or '?'} / {self.data['cpu']['threads'] or '?'}",10)
        self.text(p,270,222,('TEMP   N/A' if self.data['cpu']['temp'] is None else f"TEMP {self.data['cpu']['temp']:.0f}°C"),10,CYAN)
        self.text(p,270,262,'POWER  N/A',10,CYAN)
        self.text(p,36,461,self.memory_text(),22,'#ecf5f7',True)
        self.text(p,36,493,f"{self.data['memory']['percent']:.0f}% USED",13,CYAN,True)
        self.text(p,224,616,('VRAM N/A' if self.data['gpu'].get('mem_used') is None else f"VRAM {self.data['gpu']['mem_used']/1024:.1f}/{self.data['gpu']['mem_total']/1024:.1f} GB"),9,CYAN)
        self.text(p,224,652,'TEMP ' + self.gpu_value('temp', '°C'),10,CYAN)
        self.text(p,224,687,'POWER ' + self.gpu_value('power', ' W'),10,MAGENTA)
        self.text(p,224,722,'FAN ' + self.gpu_value('fan', '%'),10,CYAN)
        self.text(p,55,821,f"{self.data['network']['rx']/1024**2:.2f} MB/s",12,CYAN,True)
        self.text(p,251,821,f"{self.data['network']['tx']/1024**2:.2f} MB/s",12,MAGENTA,True)
        self.visuals(p)
        p.restore()

    def graph(self,p,x,y,w,h,values,color,ceiling=100):
        p.setBrush(Qt.NoBrush)
        for j in range(4): self.line(p,x,y+j*h/3,x+w,y+j*h/3,'#15313c')
        for j in range(7): self.line(p,x+j*w/6,y,x+j*w/6,y+h,'#102733')
        path=QPainterPath()
        for i,v in enumerate(values):
            px=x+i*w/max(1,len(values)-1); py=y+h-min(1,max(0,v)/max(1,ceiling))*h
            if i==0: path.moveTo(px,py)
            else: path.lineTo(px,py)
        for width,alpha in [(6,20),(3,45),(1,255)]:
            c=QColor(color); c.setAlpha(alpha); p.setPen(QPen(c,width)); p.drawPath(path)

    def visuals(self,p):
        cx,cy=150,262
        p.setBrush(Qt.NoBrush)
        for i in range(32):
            active=i<round(32*self.data['cpu']['percent']/100)
            color=GREEN if i<22 else MAGENTA
            p.setPen(QPen(QColor(color if active else '#223746'),13,Qt.SolidLine,Qt.FlatCap))
            p.drawArc(QRectF(cx-93,cy-93,186,186),int((225-i*9.5)*16),int(-7.4*16))
        for i in range(33):
            a=math.radians(225-i*9.5)
            self.line(p,cx+103*math.cos(a),cy-103*math.sin(a),cx+106*math.cos(a),cy-106*math.sin(a),'#32606c')
        p.setPen(QPen(QColor('#246371'),1)); p.drawEllipse(QRectF(cx-100,cy-100,200,200))
        p.setPen(QPen(QColor(GREEN),2)); p.drawArc(QRectF(cx-76,cy-76,152,152),45*16,270*16)
        self.text(p,108,234,f"{self.data['cpu']['percent']:.0f}%",30,'#edf7fa',True)
        self.text(p,113,273,('N/A' if self.data['cpu']['freq'] is None else f"{self.data['cpu']['freq']/1000:.2f} GHz"),14,CYAN,True)
        self.graph(p,37,351,330,32,self.histories['cpu'],GREEN)
        self.text(p,36,380,'CPU USAGE (60s)',8)
        self.text(p,373,339,'100%',7,CYAN); self.text(p,373,371,'0%',7,CYAN)
        for row in range(2):
            for i in range(24):
                active=row*24+i<round(48*self.data['memory']['percent']/100)
                rect=QRectF(37+i*15,534+row*11,12,7)
                p.setPen(Qt.NoPen); p.setBrush(QColor(GREEN if active else '#213543')); p.drawRect(rect)
        for radius,color,width in [(86,'#17434a',1),(77,GREEN,3),(67,'#205061',2),(56,MAGENTA,2),(49,'#225860',1)]:
            path=QPainterPath()
            for i in range(6):
                a=math.radians(60*i-90); x=128+radius*math.cos(a); y=689+radius*math.sin(a)
                if i==0: path.moveTo(x,y)
                else: path.lineTo(x,y)
            path.closeSubpath(); p.setBrush(Qt.NoBrush)
            if width==3:
                c=QColor(color); c.setAlpha(30); p.setPen(QPen(c,12)); p.drawPath(path)
            p.setPen(QPen(QColor(color),width)); p.drawPath(path)
        self.text(p,96,666,self.gpu_value('util', '%'),24,'#f2f8fa',True)
        self.text(p,104,700,'LOAD' if self.data['gpu'].get('util') is not None else 'NO DATA',10,GREEN)
        p.fillRect(QRectF(224,647,168,5),QColor('#213543')); p.fillRect(QRectF(224,647,168*((self.data['gpu'].get('mem_used') or 0)/max(1,self.data['gpu'].get('mem_total') or 1)),5),QColor(CYAN))
        self.graph(p,317,680,77,14,self.histories['gpu'],GREEN,100)
        self.graph(p,317,715,77,14,self.histories['power'],MAGENTA,max(1,max(self.histories['power'])))
        for x,color,direction in [(40,CYAN,1),(236,MAGENTA,-1)]:
            self.line(p,x,836-direction*7,x,836+direction*5,color,2)
            self.line(p,x,836+direction*5,x-5,836,color,2)
            self.line(p,x,836+direction*5,x+5,836,color,2)
        for x,color,key in [(37,CYAN,'rx'),(235,MAGENTA,'tx')]:
            self.graph(p,x,857,167,17,self.histories[key],color,max(0.01,max(self.histories[key])))

    def wide_text(self, p, x, y, value, size=12, color=MUTED, bold=False, width=600):
        p.setFont(QFont('DejaVu Sans Mono', size, QFont.Bold if bold else QFont.Normal))
        p.setPen(QColor(color))
        p.drawText(QRectF(x, y, width, 32), Qt.AlignLeft | Qt.AlignVCenter, str(value))

    def wide_panel(self, p, x, y, w, h, title, model=''):
        p.setBrush(QColor('#081822'))
        p.setPen(QPen(QColor('#286b75'), 1))
        p.drawPath(self.angular(x, y, w, h))
        self.wide_text(p, x+18, y+8, title, 17, CYAN, True)
        if model:
            self.wide_text(p, x+w-175, y+10, model, 8, width=160)
        self.line(p, x+16, y+46, x+w-16, y+46, '#235360')

    def paint_big(self, p):
        frame = self.angular(12, 12, 1256, 796, 24)
        p.setBrush(Qt.NoBrush)
        for width, alpha in [(14, 12), (8, 22), (3, 70)]:
            c = QColor(CYAN); c.setAlpha(alpha)
            p.setPen(QPen(c, width)); p.drawPath(frame)
        p.setBrush(QColor('#07131e')); p.setPen(QPen(QColor('#288b8c'), 1)); p.drawPath(frame)
        for y in range(24, 800, 6):
            self.line(p, 24, y, 1256, y, '#0a1a25')
        p.setPen(Qt.NoPen); p.setBrush(QColor(GREEN))
        for rect in [QRectF(38,34,14,48), QRectF(55,34,14,14), QRectF(55,52,14,30), QRectF(73,28,14,54)]:
            p.drawRect(rect)
        self.wide_text(p, 110, 28, 'SYSWATCH // MANJARO', 25, CYAN, True)
        self.wide_text(p, 112, 65, self.status_text(), 10)
        self.wide_text(p, 840, 33, datetime.now().strftime('%H:%M'), 22, CYAN, True, 180)
        self.wide_text(p, 840, 64, datetime.now().strftime('%a %d %b %Y').upper(), 9, width=180)
        if not self.wallpaper_enabled:
            self.line(p, 1228, 40, 1240, 52); self.line(p, 1240, 40, 1228, 52)
        self.line(p, 30, 104, 1250, 104, '#235360')
        # Reuse the compact CPU and GPU artwork without scaling their typography.
        for x, y, w, h, title, model in [
            (30,120,420,400,'CPU',self.data['hardware']['cpu'][:22]),
            (462,120,326,400,'MEMORY',f"{self.data['memory']['total_gb']:.0f} GB RAM"),
            (800,120,450,400,'GPU',self.gpu_name()[:22]),
            (30,532,550,250,'NETWORK',self.data['interface'][:20]),
            (592,532,300,250,'DISK','FILESYSTEMS'),
            (904,532,346,250,'PROCESSES','TOP 5 (CPU)')]:
            self.wide_panel(p,x,y,w,h,title,model)
        for target_x, target_y, source_y, height in [(40,170,162,250), (818,185,626,160)]:
            p.save()
            p.setClipRect(QRectF(target_x,target_y,398,height))
            p.translate(target_x-31,target_y-source_y)
            self.paint_small(p)
            p.restore()
        self.wide_text(p, 54, 450, f"KERNEL {self.data['kernel'][:35]}", 11, CYAN)
        self.wide_text(p, 54, 480, 'CPU USAGE (60s)', 9)
        self.wide_text(p, 484, 180, self.memory_text(), 22, '#eef6f7', True, 300)
        self.wide_text(p, 484, 215, f"{self.data['memory']['percent']:.0f}% USED", 13, CYAN, True)
        for col in range(8):
            for row in range(3+col//2):
                active = sum(3+c//2 for c in range(col))+row < round(36*self.data['memory']['percent']/100)
                p.setPen(QPen(QColor('#1a5460'),1))
                p.setBrush(QColor(GREEN if active else '#153440'))
                p.drawPath(self.angular(484+col*35, 388-row*23, 25, 16, 3))
        for y, label, value, color in [(427,'Used',f"{self.data['memory']['used_gb']:.1f} GB",GREEN),(453,'Cached',f"{self.data['memory']['cached']:.1f} GB",CYAN),(479,'Available',f"{self.data['memory']['available']:.1f} GB",MUTED)]:
            self.wide_text(p,484,y,label,10,color)
            self.wide_text(p,610,y,value,10,color,width=175)
        self.graph(p,824,383,398,58,self.histories['gpu'],GREEN,100)
        self.wide_text(p,824,443,'GPU LOAD HISTORY',9)
        self.wide_text(p,824,481,self.gpu_name()[:48],9)
        for x, label, rate, color, values in [
            (50,'DOWNLOAD',f"{self.data['network']['rx']/1024**2:.2f} MB/s",CYAN,self.histories['rx']),
            (318,'UPLOAD',f"{self.data['network']['tx']/1024**2:.2f} MB/s",MAGENTA,self.histories['tx'])]:
            self.wide_text(p,x,586,label,10,color)
            self.wide_text(p,x,616,rate,21,color,True)
            self.graph(p,x,660,240,70,values,color,max(0.01,max(values)))
            self.wide_text(p,x,739,'MB/s  /  60s HISTORY',9)
        for y, (label, used, total, percent) in zip((590,648,706), self.data['disks']):
            value = 'N/A' if used is None else f'{used:.1f}/{total:.1f} GB'
            percent = percent or 0
            self.wide_text(p,610,y,label,10)
            self.wide_text(p,712,y,value,9,width=174)
            p.fillRect(QRectF(610,y+36,220,9),QColor('#213543'))
            p.fillRect(QRectF(610,y+36,220*percent/100,9),QColor(GREEN))
            self.wide_text(p,839,y+23,f'{percent}%',9,CYAN,width=50)
        self.wide_text(p,922,580,'#  NAME          CPU     MEM',10)
        for i, (name,cpu,mem) in enumerate(self.data['processes']):
            y = 613+i*30
            self.line(p,922,y+29,1232,y+29,'#163c48')
            self.wide_text(p,922,y,str(i+1),10)
            self.wide_text(p,947,y,name[:12],10,width=150)
            self.wide_text(p,1100,y,f'{cpu:.1f}%',10,GREEN,width=62)
            self.wide_text(p,1170,y,f'{mem:.0f} MB',10,width=78)
        p.setBrush(Qt.NoBrush)

    def mousePressEvent(self,event):
        pos=(event.position() - getattr(self, "paint_offset", QPoint(0, 0))) / self.view_scale
        if event.button()==Qt.LeftButton:
            self.setFocus(Qt.MouseFocusReason)
            if self.settings_rect().contains(pos): self.open_settings_menu(event.globalPosition().toPoint())
            elif self.minimize_rect().contains(pos): self.minimize_widget()
            elif self.mode_rect().contains(pos): self.toggle_mode()
            elif self.close_rect().contains(pos): self.close()
            elif pos.y()<110:
                # Let the compositor move the native window (required on Wayland).
                handle = self.windowHandle()
                if handle is None or not handle.startSystemMove():
                    self.drag_offset=event.globalPosition().toPoint()-self.pos()
                event.accept()
    def mouseMoveEvent(self,event):
        if self.drag_offset is not None: self.move(event.globalPosition().toPoint()-self.drag_offset)
    def mouseReleaseEvent(self,event): self.drag_offset=None
    def closeEvent(self,event):
        if self._closing:
            event.accept()
            return
        self._closing = True
        self.tray.hide()
        self.worker.stop_event.set()
        self.worker.wait()
        if self.kwin_script is not None:
            interface, name = self.kwin_script
            interface.call('unloadScript', name)
            self.kwin_script = None
        if self.kwin_directory is not None:
            self.kwin_directory.cleanup()
            self.kwin_directory = None
        self.settings.setValue('pos',self.normal_position if self.background_enabled else self.pos())
        super().closeEvent(event)
        QApplication.instance().quit()
