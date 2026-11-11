from pathlib import Path
import json
import os
import tempfile
import tkinter as tk
import unittest
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import Mock, patch
import sys

from PIL import Image, ImageChops

from photobooth import PhotoBooth, PiCamera, Session, lcd_geometry, place_on_lcd, show_error


class LCDLaunchTests(unittest.TestCase):
    def output(self, transform="normal"):
        return {
            "name": "SPI-1", "enabled": True, "transform": transform, "scale": 1.0,
            "position": {"x": 1920, "y": 0},
            "modes": [{"width": 480, "height": 320, "current": True}],
        }

    def test_lcd_geometry_follows_output_rotation_and_position(self):
        for transform, dimensions in (
            ("normal", (480, 320)), ("90", (320, 480)), ("270", (320, 480)),
        ):
            with self.subTest(transform=transform), patch(
                "photobooth.subprocess.run",
                return_value=SimpleNamespace(stdout=json.dumps([self.output(transform)])),
            ):
                self.assertEqual(lcd_geometry(), (*dimensions, 1920, 0))

    def test_missing_disabled_or_unconfigured_lcd_reports_error(self):
        disabled = self.output()
        disabled["enabled"] = False
        no_mode = self.output()
        no_mode["modes"] = []
        for outputs in ([], [disabled], [no_mode]):
            with self.subTest(outputs=outputs), patch(
                "photobooth.subprocess.run",
                return_value=SimpleNamespace(stdout=json.dumps(outputs)),
            ):
                with self.assertRaises(ValueError):
                    lcd_geometry()

    def test_lcd_window_has_no_decoration_and_uses_exact_output_bounds(self):
        root = Mock()
        place_on_lcd(root, (320, 480, -320, 0))
        root.overrideredirect.assert_called_once_with(True)
        root.geometry.assert_called_once_with("320x480-320+0")

    def test_lcd_error_dialog_stays_inside_lcd_bounds(self):
        root = Mock()
        root.overrideredirect.return_value = True
        root.winfo_geometry.return_value = "320x480+1920+0"
        root.winfo_width.return_value = 320
        with patch("photobooth.tk.Toplevel") as top, \
                patch("photobooth.tk.Label"), patch("photobooth.tk.Message"), \
                patch("photobooth.tk.Button") as button, \
                patch("photobooth.messagebox.showerror") as desktop_error:
            show_error(root, "Camera failed", "No camera detected")
        dialog = top.return_value
        top.assert_called_once_with(root)
        dialog.geometry.assert_called_once_with("320x480+1920+0")
        dialog.grab_set.assert_called_once()
        root.wait_window.assert_called_once_with(dialog)
        self.assertEqual(button.call_args.kwargs["command"], dialog.destroy)
        desktop_error.assert_not_called()

    def test_normal_window_keeps_standard_error_dialog(self):
        root = Mock()
        root.overrideredirect.return_value = False
        with patch("photobooth.messagebox.showerror") as desktop_error:
            show_error(root, "Camera failed", "No camera detected")
        desktop_error.assert_called_once_with("Camera failed", "No camera detected", parent=root)


class FakeCamera:
    def capture_file(self, path: str) -> None:
        Path(path).write_bytes(b"test photo")


class SessionTests(unittest.TestCase):
    def test_allowed_options_save_exact_number_in_order(self):
        for count in (3, 4):
            for interval in (5, 10):
                with self.subTest(count=count, interval=interval):
                    with tempfile.TemporaryDirectory() as directory:
                        session = Session(count, interval, Path(directory) / "session")
                        for _ in range(count):
                            session.capture_next(FakeCamera())
                        self.assertEqual(
                            [path.name for path in session.photos],
                            [f"photo_{i:02d}.jpg" for i in range(1, count + 1)],
                        )
                        self.assertTrue(all(path.is_file() for path in session.photos))
                        with self.assertRaises(ValueError):
                            session.capture_next(FakeCamera())

    def test_invalid_options(self):
        for count, interval in ((2, 5), (5, 10), (3, 0), (4, 7)):
            with self.subTest(count=count, interval=interval):
                with self.assertRaises(ValueError):
                    Session(count, interval, Path("unused"))

    def test_failed_capture_is_not_added_to_review(self):
        class BrokenCamera:
            def capture_file(self, path: str) -> None:
                raise OSError("Camera disconnected")

        with tempfile.TemporaryDirectory() as directory:
            session = Session(3, 5, Path(directory))
            with self.assertRaisesRegex(OSError, "Camera disconnected"):
                session.capture_next(BrokenCamera())
            self.assertEqual(session.photos, [])
            session.capture_next(FakeCamera())
            self.assertEqual(session.photos[0].name, "photo_01.jpg")

    def test_print_layout_dimensions_order_duplicate_strips_and_originals(self):
        colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]

        class ColorCamera:
            def __init__(self):
                self.index = 0

            def capture_file(self, path: str) -> None:
                Image.new("RGB", (800, 450), colors[self.index]).save(path)
                self.index += 1

        for count in (3, 4):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as directory:
                session = Session(count, 5, Path(directory))
                camera = ColorCamera()
                for _ in range(count):
                    session.capture_next(camera)
                originals = [path.read_bytes() for path in session.photos]
                layout = session.prepare_print_layout()
                self.assertEqual(layout.name, "print_layout.png")
                self.assertEqual(len(session.photos), count)
                with Image.open(layout) as sheet:
                    self.assertEqual(sheet.size, (1200, 1800))
                    self.assertEqual(sheet.mode, "RGB")
                    self.assertAlmostEqual(sheet.info["dpi"][0], 300, places=1)
                    self.assertAlmostEqual(sheet.info["dpi"][1], 300, places=1)
                    left = sheet.crop((0, 0, 600, 1800))
                    right = sheet.crop((600, 0, 1200, 1800))
                    self.assertIsNone(ImageChops.difference(left, right).getbbox())
                    self.assertEqual(sheet.getpixel((0, 0)), (255, 255, 255))
                    slot_height = (1800 - 60 - 30 * (count - 1)) // count
                    for index, color in enumerate(colors[:count]):
                        y = 30 + index * (slot_height + 30) + slot_height // 2
                        actual = sheet.getpixel((300, y))
                        self.assertTrue(all(abs(a - b) <= 2 for a, b in zip(actual, color)))
                    for index in range(count - 1):
                        y = 30 + index * (slot_height + 30) + slot_height + 15
                        self.assertEqual(sheet.getpixel((300, y)), (255, 255, 255))
                self.assertEqual([path.read_bytes() for path in session.photos], originals)

    def test_print_layout_rejects_incomplete_session(self):
        with tempfile.TemporaryDirectory() as directory:
            session = Session(3, 5, Path(directory))
            session.capture_next(FakeCamera())
            with self.assertRaisesRegex(ValueError, "Capture all photos"):
                session.prepare_print_layout()
            self.assertFalse((session.directory / "print_layout.png").exists())

    def test_print_layout_reports_unreadable_photo(self):
        with tempfile.TemporaryDirectory() as directory:
            session = Session(3, 5, Path(directory))
            for _ in range(3):
                session.capture_next(FakeCamera())
            with self.assertRaises(OSError):
                session.prepare_print_layout()
            self.assertEqual(len(session.photos), 3)
            self.assertFalse((session.directory / "print_layout.png").exists())

    def test_print_layout_honors_exif_orientation(self):
        with tempfile.TemporaryDirectory() as directory:
            session = Session(3, 5, Path(directory))
            photo = Image.new("RGB", (200, 100), "red")
            photo.paste("blue", (100, 0, 200, 100))
            exif = Image.Exif()
            exif[274] = 6  # Rotate 90 degrees clockwise for display.
            for index in range(3):
                path = Path(directory) / f"photo_{index + 1:02d}.jpg"
                photo.save(path, exif=exif)
                session.photos.append(path)
            with Image.open(session.prepare_print_layout()) as sheet:
                top = sheet.getpixel((300, 100))
                bottom = sheet.getpixel((300, 500))
                self.assertGreater(top[0], 240)
                self.assertGreater(bottom[2], 240)


class LayoutFlowTests(unittest.TestCase):
    def make_app(self):
        app = PhotoBooth.__new__(PhotoBooth)
        app.compact = False
        app.portrait = False
        app.closed = False
        app.active = True
        app.previewing = True
        app.preview_ready = True
        for name in ("root", "worker", "camera", "session", "status", "countdown",
                     "clear", "label", "button"):
            setattr(app, name, Mock())
        app.root.overrideredirect.return_value = False
        app.session.photos = []
        app.session.photo_count = 3
        app.session.interval = 5
        return app

    def test_start_uses_fixed_positioning_countdown_for_either_interval(self):
        for interval in (5, 10):
            with self.subTest(interval=interval):
                app = self.make_app()
                app.active = False
                app.output = Path("unused")
                app.count = Mock()
                app.count.get.return_value = 3
                app.interval = Mock()
                app.interval.get.return_value = interval
                app.tick = Mock()
                app.request_preview = Mock()
                app.frame = Mock()
                with patch("photobooth.tk.Frame"), patch("photobooth.tk.Label"):
                    app.start()
                app.tick.assert_called_once_with(15, app.session)
                app.request_preview.assert_called_once_with(app.session)
                self.assertEqual(app.session.interval, interval)

    def test_first_capture_waits_fifteen_seconds_then_uses_selected_interval(self):
        for count in (3, 4):
            for interval in (5, 10):
                with self.subTest(count=count, interval=interval):
                    app = self.make_app()
                    app.camera = Mock()
                    app.session.photo_count = count
                    app.session.interval = interval
                    app.session.photos = []
                    events = []
                    capture_times = []
                    now = 0

                    def schedule(delay, callback, *args):
                        events.append((now + delay / 1000, callback, args))

                    def capture(camera):
                        capture_times.append(now)
                        app.session.photos.append(Path(f"photo_{len(capture_times)}.jpg"))
                        return app.session.photos[-1]

                    def submit(callback, *args):
                        future = Future()
                        future.set_result(callback(*args))
                        return future

                    app.session.capture_next.side_effect = capture
                    app.worker.submit.side_effect = submit
                    app.root.after.side_effect = schedule
                    app.tick(15, app.session)
                    app.worker.submit.assert_not_called()
                    while events:
                        events.sort(key=lambda event: event[0])
                        now, callback, args = events.pop(0)
                        callback(*args)
                    self.assertEqual(len(capture_times), count)
                    self.assertEqual(capture_times[0], 15)
                    for previous, current in zip(capture_times, capture_times[1:]):
                        self.assertAlmostEqual(current - previous, interval + 0.05)

    def test_final_capture_prepares_layout_before_review(self):
        app = self.make_app()
        app.session.photos = [Path(f"photo_{i}.jpg") for i in range(3)]
        app.session.photo_count = 3
        future = Future()
        future.set_result(app.session.photos[-1])
        app.check_capture(future, app.session)
        app.worker.submit.assert_called_once_with(app.session.prepare_print_layout)
        app.button.assert_not_called()
        app.root.after.assert_called_once_with(
            50, app.check_layout, app.worker.submit.return_value, app.session
        )
        self.assertFalse(app.previewing)

    def test_layout_failure_is_visible_and_originals_remain_reviewable(self):
        app = self.make_app()
        future = Future()
        future.set_exception(OSError("Disk full"))
        with patch("photobooth.messagebox.showerror") as showerror:
            app.check_layout(future, app.session)
        showerror.assert_called_once()
        self.assertIn("Disk full", showerror.call_args.args[1])
        self.assertEqual(app.button.call_args.args[0], "Review")

    def test_successful_layout_offers_review(self):
        app = self.make_app()
        future = Future()
        future.set_result(Path("print_layout.png"))
        with patch("photobooth.messagebox.showerror") as showerror:
            app.check_layout(future, app.session)
        showerror.assert_not_called()
        self.assertEqual(app.button.call_args.args[0], "Review")

    def test_preview_renders_and_schedules_only_one_next_frame(self):
        app = self.make_app()
        app.preview_frame = Mock()
        app.preview_frame.winfo_width.return_value = 800
        app.preview_frame.winfo_height.return_value = 360
        app.preview_label = Mock()
        future = Future()
        future.set_result(Image.new("RGB", (640, 360), "green"))
        with patch("PIL.ImageTk.PhotoImage") as image:
            app.check_preview(future, app.session)
        app.preview_label.config.assert_called_once_with(image=image.return_value, text="")
        self.assertTrue(app.preview_ready)
        app.root.after.assert_called_once_with(150, app.request_preview, app.session)

    def test_unfinished_preview_polls_without_submitting_more_frames(self):
        app = self.make_app()
        future = Future()
        app.check_preview(future, app.session)
        app.worker.submit.assert_not_called()
        app.root.after.assert_called_once_with(50, app.check_preview, future, app.session)

    def test_preview_failure_stops_countdown_and_reports_error(self):
        app = self.make_app()
        app.show_options = Mock()
        future = Future()
        future.set_exception(OSError("Camera disconnected"))
        with patch("photobooth.messagebox.showerror") as showerror:
            app.check_preview(future, app.session)
        self.assertIn("Camera disconnected", showerror.call_args.args[1])
        self.assertFalse(app.active)
        self.assertFalse(app.previewing)
        app.show_options.assert_called_once()
        app.tick(0, app.session)
        app.worker.submit.assert_not_called()

    def test_capture_waits_if_camera_is_not_ready_at_end_of_countdown(self):
        app = self.make_app()
        app.preview_ready = False
        app.tick(0, app.session)
        app.worker.submit.assert_not_called()
        app.root.after.assert_called_once_with(50, app.tick, 0, app.session)
        app.preview_ready = True
        app.tick(0, app.session)
        app.worker.submit.assert_called_once()

    def test_old_session_and_shutdown_callbacks_do_not_change_ui(self):
        for stale_session, closed, previewing in (
            (True, False, True), (False, True, True), (False, False, False)
        ):
            with self.subTest(stale=stale_session, closed=closed, previewing=previewing):
                app = self.make_app()
                session = app.session
                if stale_session:
                    app.session = Mock()
                app.closed = closed
                app.previewing = previewing
                app.request_preview(session)
                app.check_preview(Future(), session)
                app.root.after.assert_not_called()
                app.worker.submit.assert_not_called()

    def test_start_ignores_duplicate_click_while_active(self):
        app = self.make_app()
        app.start()
        app.clear.assert_not_called()


class PiCameraTests(unittest.TestCase):
    def test_missing_camera_reports_actionable_error_without_opening_device(self):
        camera_class = Mock()
        camera_class.global_camera_info.return_value = []
        with patch.dict(
            sys.modules,
            picamera2=SimpleNamespace(Picamera2=camera_class),
            libcamera=SimpleNamespace(controls=Mock()),
        ):
            camera = PiCamera()
            with self.assertRaisesRegex(RuntimeError, "No camera detected"):
                camera.prepare()
        camera_class.assert_not_called()
        self.assertIsNone(camera.camera)

    def test_preview_and_capture_share_one_camera_and_enable_autofocus(self):
        hardware = Mock()
        hardware.camera_controls = {"AfMode": ()}
        hardware.capture_image.return_value = Image.new("RGB", (2304, 1296), "red")
        picamera2 = SimpleNamespace(Picamera2=Mock(return_value=hardware))
        libcamera = SimpleNamespace(
            controls=SimpleNamespace(AfModeEnum=SimpleNamespace(Continuous=2))
        )
        with patch.dict(sys.modules, picamera2=picamera2, libcamera=libcamera), \
                patch("time.sleep"):
            camera = PiCamera()
            preview = camera.preview_image()
            camera.capture_file("photo.jpg")
            self.assertEqual(preview.size, (640, 360))
            self.assertEqual(preview.getpixel((0, 0)), (255, 0, 0))
            picamera2.Picamera2.assert_called_once()
            hardware.create_still_configuration.assert_called_once_with(
                main={"size": (2304, 1296), "format": "RGB888"}, buffer_count=2
            )
            hardware.set_controls.assert_called_once_with({"AfMode": 2})
            hardware.capture_image.assert_called_once_with("main")
            hardware.capture_file.assert_called_once_with("photo.jpg")
            camera.close()
            hardware.close.assert_called_once()

    def test_failed_camera_setup_closes_device_and_allows_retry(self):
        hardware = Mock()
        hardware.camera_controls = {}
        hardware.start.side_effect = [OSError("Camera busy"), None]
        picamera2 = SimpleNamespace(Picamera2=Mock(return_value=hardware))
        libcamera = SimpleNamespace(controls=Mock())
        with patch.dict(sys.modules, picamera2=picamera2, libcamera=libcamera), \
                patch("time.sleep"):
            camera = PiCamera()
            with self.assertRaisesRegex(OSError, "Camera busy"):
                camera.prepare()
            self.assertIsNone(camera.camera)
            hardware.close.assert_called_once()
            camera.prepare()
            self.assertIs(camera.camera, hardware)
            hardware.set_controls.assert_not_called()
            camera.close()


@unittest.skipUnless(
    os.environ.get("PHOTOBOOTH_GUI_TESTS") == "1",
    "Set PHOTOBOOTH_GUI_TESTS=1 in a desktop session to test real Tk widgets.",
)
class DisplayLayoutTests(unittest.TestCase):
    def assert_layout_fits(self, root, width, height):
        root.update_idletasks()
        self.assertLessEqual(root.winfo_reqwidth(), width)
        self.assertLessEqual(root.winfo_reqheight(), height)

    def test_options_preview_and_review_fit_all_display_sizes(self):
        for compact, portrait, width, height in (
            (True, False, 480, 320), (False, False, 800, 480),
            (True, True, 320, 480),
        ):
            with self.subTest(compact=compact, portrait=portrait), tempfile.TemporaryDirectory() as output:
                root = tk.Tk()
                root.withdraw()
                app = PhotoBooth(root, Path(output), False, compact=compact, portrait=portrait)
                try:
                    self.assert_layout_fits(root, width, height)
                    app.count.set(3)
                    app.interval.set(10)
                    self.assertEqual(app.summary.get(), "3 photos  /  10 seconds between shots")
                    with patch.object(app, "request_preview"), patch.object(app, "tick"):
                        app.start()
                    app.status.config(text="Get situated! Photo 1 of 4")
                    app.countdown.config(text="Smile!")
                    self.assert_layout_fits(root, width, height)
                    session = app.session
                    session.directory.mkdir()
                    for index in range(3):
                        path = session.directory / f"photo_{index}.jpg"
                        Image.new("RGB", (800, 450), "green").save(path)
                        session.photos.append(path)
                    app.previewing = False
                    future = Future()
                    future.set_result(Path("print_layout.png"))
                    app.check_layout(future, session)
                    self.assert_layout_fits(root, width, height)
                    for index in range(3):
                        app.show_photo(index)
                        self.assert_layout_fits(root, width, height)
                        self.assertFalse(any(
                            isinstance(widget, tk.Label)
                            and str(widget.cget("text")).startswith("Photo ")
                            for widget in app.frame.winfo_children()
                        ))
                    app.show_options()
                    self.assert_layout_fits(root, width, height)
                finally:
                    app.close()

    def test_small_display_selects_compact_layout_automatically(self):
        root = tk.Tk()
        root.withdraw()
        with patch.object(root, "winfo_screenwidth", return_value=480), \
                patch.object(root, "winfo_screenheight", return_value=320):
            app = PhotoBooth(root, Path("unused"), False)
        try:
            self.assertTrue(app.compact)
            self.assertEqual(app.camera.preview_size, (480, 270))
            self.assert_layout_fits(root, 480, 320)
        finally:
            app.close()


if __name__ == "__main__":
    unittest.main()
