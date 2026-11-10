from pathlib import Path
import tempfile
import unittest
from concurrent.futures import Future
from unittest.mock import Mock, patch

from PIL import Image, ImageChops

from photobooth import PhotoBooth, Session


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
        app.closed = False
        for name in ("root", "worker", "session", "status", "countdown",
                     "clear", "label", "button"):
            setattr(app, name, Mock())
        return app

    def test_final_capture_prepares_layout_before_review(self):
        app = self.make_app()
        app.session.photos = [Path(f"photo_{i}.jpg") for i in range(3)]
        app.session.photo_count = 3
        future = Future()
        future.set_result(app.session.photos[-1])
        app.check_capture(future)
        app.worker.submit.assert_called_once_with(app.session.prepare_print_layout)
        app.button.assert_not_called()
        app.root.after.assert_called_once_with(
            50, app.check_layout, app.worker.submit.return_value
        )

    def test_layout_failure_is_visible_and_originals_remain_reviewable(self):
        app = self.make_app()
        future = Future()
        future.set_exception(OSError("Disk full"))
        with patch("photobooth.messagebox.showerror") as showerror:
            app.check_layout(future)
        showerror.assert_called_once()
        self.assertIn("Disk full", showerror.call_args.args[1])
        self.assertEqual(app.button.call_args.args[0], "Review")

    def test_successful_layout_offers_review(self):
        app = self.make_app()
        future = Future()
        future.set_result(Path("print_layout.png"))
        with patch("photobooth.messagebox.showerror") as showerror:
            app.check_layout(future)
        showerror.assert_not_called()
        self.assertEqual(app.button.call_args.args[0], "Review")


if __name__ == "__main__":
    unittest.main()
