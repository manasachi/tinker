from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from booth_startup import install, wait_for_lcd


class StartupTests(unittest.TestCase):
    def test_install_is_repeatable_and_keeps_unrelated_desktop_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            desktop = home / ".config/autostart"
            desktop.mkdir(parents=True)
            other = desktop / "other.desktop"
            other.write_text("unchanged")
            for _ in range(2):
                install(home, Path("/home/pi/portable-photobooth"))
            self.assertEqual(other.read_text(), "unchanged")
            entry = (desktop / "photobooth.desktop").read_text()
            self.assertIn("--start-service", entry)
            unit = (home / ".config/systemd/user/photobooth.service").read_text()
            self.assertIn("Restart=on-failure", unit)
            self.assertIn("StartLimitIntervalSec=600", unit)
            self.assertIn("StartLimitBurst=3", unit)
            self.assertIn('"/home/pi/portable-photobooth/booth_startup.py" --run', unit)

    def test_lcd_startup_retries_until_display_rotation_is_ready(self):
        with patch("photobooth.lcd_geometry", side_effect=[
            ValueError("not enabled"), subprocess.CalledProcessError(1, ["wlr-randr"]),
            subprocess.TimeoutExpired(["wlr-randr"], 10),
            (480, 320, 0, 0),
            (320, 480, 0, 0),
        ]) as lcd, patch("booth_startup.time.sleep") as sleep, self.assertLogs():
            wait_for_lcd()
        self.assertEqual(lcd.call_count, 5)
        self.assertEqual(sleep.call_count, 4)

    def test_missing_display_fails_explicitly_after_timeout(self):
        with patch("photobooth.lcd_geometry", side_effect=ValueError("not enabled")), \
                patch("booth_startup.time.monotonic", side_effect=[0, 91]):
            with self.assertRaisesRegex(RuntimeError, "LCD did not become ready"):
                wait_for_lcd()

    def test_service_launcher_does_not_load_the_gui_or_camera_stack(self):
        subprocess.run(
            [sys.executable, "-c",
             "import sys; from unittest.mock import patch; import booth_startup; "
             "sys.argv = ['booth_startup.py', '--start-service']; "
             "run = patch('booth_startup.subprocess.run'); run.start(); "
             "booth_startup.main(); "
             "assert not {'tkinter', 'photobooth', 'picamera2', 'PIL'} & sys.modules.keys()"],
            cwd=Path(__file__).parent, check=True, capture_output=True, text=True,
        )


if __name__ == "__main__":
    unittest.main()
