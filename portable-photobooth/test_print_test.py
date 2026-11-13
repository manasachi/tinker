from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageChops

from display_test import load_test_image
from print_test import prepare_test_sheet


class PrintTestSheetTests(unittest.TestCase):
    def test_generated_samples_make_one_black_two_strip_sheet(self):
        for text in ("", "Test party"):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as output:
                layout = prepare_test_sheet(Path(output), text)
                samples = sorted(layout.parent.glob("circle_*.png"))
                self.assertEqual(len(samples), 4)
                for index, path in enumerate(samples):
                    with Image.open(path) as sample:
                        self.assertIsNone(ImageChops.difference(
                            sample, load_test_image(index),
                        ).getbbox())
                with Image.open(layout) as sheet:
                    self.assertEqual(sheet.size, (1200, 1800))
                    self.assertAlmostEqual(sheet.info["dpi"][0], 300, places=1)
                    self.assertEqual(sheet.getpixel((0, 0)), (0, 0, 0))
                    self.assertIsNone(ImageChops.difference(
                        sheet.crop((0, 0, 600, 1800)), sheet.crop((600, 0, 1200, 1800)),
                    ).getbbox())
                    area_height = 1500 if text else 1800
                    slot_height = (area_height - 60 - 90) // 4
                    for index in range(4):
                        expected = load_test_image(index).getpixel((0, 0))
                        y = 30 + index * (slot_height + 30) + slot_height // 2
                        self.assertEqual(sheet.getpixel((100, y)), expected)

    def test_repeated_tests_do_not_overwrite_prior_sheets(self):
        with tempfile.TemporaryDirectory() as output:
            first = prepare_test_sheet(Path(output))
            original = first.read_bytes()
            second = prepare_test_sheet(Path(output))
            self.assertNotEqual(first, second)
            self.assertEqual(first.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
