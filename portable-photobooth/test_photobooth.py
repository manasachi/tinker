from pathlib import Path
import tempfile
import unittest

from photobooth import Session


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


if __name__ == "__main__":
    unittest.main()
