"""Installation removals are scoped to SysWatch and never touch neighboring apps."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import installation


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.environment = patch.dict(os.environ, {
            'XDG_DATA_HOME': str(self.root / 'data'),
            'XDG_CONFIG_HOME': str(self.root / 'config'),
            'XDG_CACHE_HOME': str(self.root / 'cache'),
        })
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.directory.cleanup()

    def test_uninstall_removes_app_and_startup_but_preserves_other_files(self):
        app = installation.data_home() / 'syswatch'
        (app / '_internal').mkdir(parents=True)
        (app / 'syswatch').write_text('executable')
        launcher = installation.data_home() / 'applications' / (installation.APP_ID + '.desktop')
        installation.write_entry(launcher, [str(app / 'syswatch')])
        installation.set_startup(True, 'wallpaper', [str(app / 'syswatch')])
        neighbor = installation.data_home() / 'another-app.txt'
        neighbor.write_text('keep')
        preferences = self.root / 'config/syswatch/position.conf'
        preferences.parent.mkdir(parents=True)
        preferences.write_text('keep')
        cache = self.root / 'cache/syswatch/wallpaper.png'
        cache.parent.mkdir(parents=True)
        cache.write_text('frame')
        installation.uninstall_app()
        self.assertFalse(app.exists())
        self.assertFalse(launcher.exists())
        self.assertFalse(installation.startup_path().exists())
        self.assertFalse(cache.exists())
        self.assertEqual(neighbor.read_text(), 'keep')
        self.assertEqual(preferences.read_text(), 'keep')
        installation.uninstall_app()  # repeated uninstall is harmless

    def test_uninstall_rejects_unrecognized_directory_before_removing_startup(self):
        app = installation.data_home() / 'syswatch'
        app.mkdir(parents=True)
        keep = app / 'notes.txt'
        keep.write_text('keep')
        installation.set_startup(True)
        with self.assertRaises(RuntimeError):
            installation.uninstall_app()
        self.assertTrue(installation.startup_path().exists())
        self.assertEqual(keep.read_text(), 'keep')
