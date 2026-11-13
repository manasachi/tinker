from pathlib import Path
import io
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageChops

from photobooth import Session
from print_test import circle_sample, prepare_test_sheet, main


class PrintTestSheetTests(unittest.TestCase):
    def test_next_print_defaults_to_no_text_but_explicit_text_is_supported(self):
        for arguments, expected in (([], ""), (["--strip-text", "Party"], "Party")):
            with self.subTest(arguments=arguments), patch.object(
                sys, "argv", ["print_test.py", *arguments],
            ), patch("print_test.prepare_test_sheet") as prepare, patch(
                "sys.stdout", new_callable=io.StringIO,
            ):
                main()
            self.assertEqual(prepare.call_args.args[1], expected)

    def test_samples_have_centered_black_circle_white_background_and_labels(self):
        for index in range(4):
            sample = circle_sample(index)
            self.assertEqual(sample.getpixel((320, 180)), (0, 0, 0))
            self.assertEqual(sample.getpixel((10, 10)), (255, 255, 255))
            channels = sample.split()
            self.assertIsNone(ImageChops.difference(channels[0], channels[1]).getbbox())
            self.assertIsNone(ImageChops.difference(channels[1], channels[2]).getbbox())
            label = sample.crop((30, 25, 300, 65))
            self.assertIsNotNone(ImageChops.difference(
                label, Image.new("RGB", label.size, "white"),
            ).getbbox())
            if index:
                self.assertIsNotNone(ImageChops.difference(sample, circle_sample(index - 1)).getbbox())
        with self.assertRaises(ValueError):
            circle_sample(4)

    def test_generated_samples_make_one_black_two_strip_sheet(self):
        for text in ("", "manupi test"):
            with self.subTest(text=text), tempfile.TemporaryDirectory() as output:
                layout = prepare_test_sheet(Path(output), text)
                samples = sorted(layout.parent.glob("circle_*.png"))
                self.assertEqual(len(samples), 4)
                session = Session(4, 5, layout.parent, strip_text=text)
                for index, path in enumerate(samples):
                    with Image.open(path) as sample:
                        self.assertEqual(sample.size, session.photo_size)
                        self.assertIsNone(ImageChops.difference(
                            sample, circle_sample(index, session.photo_size),
                        ).getbbox())
                        self.assertEqual(sample.getpixel((1, 1)), (255, 255, 255))
                        self.assertEqual(
                            sample.getpixel((sample.width - 2, sample.height - 2)),
                            (255, 255, 255),
                        )
                with Image.open(layout) as sheet:
                    self.assertEqual(sheet.size, (1182, 1748))
                    self.assertAlmostEqual(sheet.info["dpi"][0], 300, places=1)
                    self.assertEqual(sheet.getpixel((0, 0)), (0, 0, 0))
                    self.assertIsNone(ImageChops.difference(
                        sheet.crop((0, 0, 591, 1748)), sheet.crop((591, 0, 1182, 1748)),
                    ).getbbox())
                    slot_height = session.photo_size[1]
                    for index in range(4):
                        y = 18 + index * (slot_height + 12)
                        with Image.open(samples[index]) as sample:
                            self.assertIsNone(ImageChops.difference(
                                sheet.crop((18, y, 573, y + slot_height)), sample,
                            ).getbbox(), "The complete sample, including the P, must survive composition")

    def test_original_strip_dimensions_have_thin_borders_and_tight_gaps(self):
        blank = Session(4, 5, Path("unused"))
        with_text = Session(4, 5, Path("unused"), strip_text="manupi test")
        self.assertEqual(blank.photo_size, (555, 419))
        self.assertEqual(with_text.photo_size, (555, 346))
        self.assertAlmostEqual(591 / 1182 * 100, 50)
        self.assertAlmostEqual(1748 / 300 * 25.4, 148, delta=0.1)
        self.assertLessEqual(18 / 1182 * 100, 1.6)
        self.assertGreater(with_text.photo_size[0] * with_text.photo_size[1], 471 * 311)

    def test_repeated_tests_do_not_overwrite_prior_sheets(self):
        with tempfile.TemporaryDirectory() as output:
            first = prepare_test_sheet(Path(output))
            original = first.read_bytes()
            second = prepare_test_sheet(Path(output))
            self.assertNotEqual(first, second)
            self.assertEqual(first.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
