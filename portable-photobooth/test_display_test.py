from pathlib import Path
import os
import tempfile
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from display_test import MemoryPhotoTest, load_test_image


class MemoryPhotoTests(unittest.TestCase):
    def test_four_distinct_sample_images_are_generated_in_memory(self):
        photos = [load_test_image(index) for index in range(4)]
        self.assertTrue(all(photo.size == (640, 360) for photo in photos))
        self.assertEqual(len({photo.tobytes() for photo in photos}), 4)
        with self.assertRaises(ValueError):
            load_test_image(4)

    def test_existing_picture_is_loaded_without_changing_original(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "photo.jpg"
            Image.new("RGB", (1600, 900), "blue").save(path)
            original = path.read_bytes()
            photo = load_test_image(0, path)
            self.assertEqual(photo.size, (1280, 720))
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(directory).iterdir()), [path])
            self.assertGreater(photo.getpixel((0, 0))[2], 240)

    def make_app(self):
        app = MemoryPhotoTest.__new__(MemoryPhotoTest)
        app.paths = None
        app.photos = []
        for name in ("root", "progress", "clear", "label", "button"):
            setattr(app, name, Mock())
        return app

    def test_simulation_keeps_four_images_in_memory_then_offers_review(self):
        app = self.make_app()
        with patch.object(Image.Image, "save") as save:
            for index in range(4):
                app.capture_next()
                self.assertEqual(len(app.photos), index + 1)
                if index < 3:
                    app.button.assert_not_called()
            save.assert_not_called()
        self.assertTrue(all(isinstance(photo, Image.Image) for photo in app.photos))
        self.assertEqual(app.root.after.call_count, 3)
        self.assertEqual(app.button.call_args.args[0], "Review")

    def test_unreadable_picture_displays_error(self):
        app = self.make_app()
        app.paths = [Path("/nonexistent/photobooth-test-image.jpg")] * 4
        app.show_start = Mock()
        with patch("display_test.show_error") as showerror:
            app.capture_next()
        showerror.assert_called_once()
        app.show_start.assert_called_once()
        self.assertEqual(app.photos, [])
        app.button.assert_not_called()


@unittest.skipUnless(
    os.environ.get("PHOTOBOOTH_GUI_TESTS") == "1",
    "Set PHOTOBOOTH_GUI_TESTS=1 in a desktop session to test real Tk widgets.",
)
class MemoryDisplayLayoutTests(unittest.TestCase):
    def test_in_memory_review_and_controls_fit_landscape_and_portrait(self):
        for portrait, width, height in ((False, 480, 320), (True, 320, 480)):
            with self.subTest(portrait=portrait):
                self.check_layout(portrait, width, height)

    def check_layout(self, portrait, width, height):
        root = tk.Tk()
        root.withdraw()
        app = MemoryPhotoTest(root, portrait=portrait)
        try:
            root.update_idletasks()
            self.assertLessEqual(root.winfo_reqwidth(), width)
            self.assertLessEqual(root.winfo_reqheight(), height)
            app.start()
            for _ in range(4):
                app.capture_next()
            self.assertEqual(len(app.photos), 4)
            for index in range(4):
                app.show_photo(index)
                root.update_idletasks()
                self.assertEqual(app.index, index)
                self.assertIsNotNone(app.image)
                self.assertGreater(app.image.width(), 200)
                self.assertGreater(app.image.height(), 100)
                self.assertLessEqual(root.winfo_reqwidth(), width)
                self.assertLessEqual(root.winfo_reqheight(), height)
                self.assertFalse(any(
                    isinstance(widget, tk.Label)
                    and str(widget.cget("text")).startswith("Photo ")
                    for widget in app.frame.winfo_children()
                ))
                controls = next(
                    widget for widget in app.frame.winfo_children()
                    if isinstance(widget, tk.Frame) and widget.winfo_children()
                    and isinstance(widget.winfo_children()[0], tk.Button)
                )
                previous, following, _ = controls.winfo_children()
                self.assertEqual(str(previous.cget("state")), "disabled" if index == 0 else "normal")
                self.assertEqual(str(following.cget("state")), "disabled" if index == 3 else "normal")
            app.show_start()
            self.assertEqual(app.photos, [])
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
