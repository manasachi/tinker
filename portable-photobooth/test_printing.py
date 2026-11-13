import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image, ImageChops

from printing import QUEUE, job_status, prepare_print_document, submit_layout


class PrintingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "print_layout.png"
        with Image.new("RGB", (1182, 1748), "black") as sheet:
            sheet.paste("red", (18, 18, 573, 1730))
            sheet.paste("red", (609, 18, 1164, 1730))
            sheet.save(self.path)
        self.client = Mock()
        self.uri = "ipp://192.168.0.1:631/ipp/print"
        self.client.getPrinters.return_value = {
            QUEUE: {"device-uri": self.uri, "printer-state": 3},
        }
        self.client.getJobs.return_value = {}
        self.client.printFile.return_value = 42
        for target, value in (
            ("connection", self.client), ("direct_printer_uri", self.uri),
            ("verify_direct", "verified"), ("configure_queue", None),
        ):
            patcher = patch(f"printing.{target}", return_value=value)
            setattr(self, target, patcher.start())
            self.addCleanup(patcher.stop)

    def test_all_quantities_submit_one_job_with_exact_sheet_count(self):
        for strips in range(1, 9):
            with self.subTest(strips=strips):
                self.client.printFile.reset_mock()
                marker = self.path.parent / "print-job.json"
                if marker.exists():
                    marker.unlink()
                self.assertEqual(submit_layout(self.path, strips), 42)
                self.client.printFile.assert_called_once()
                options = self.client.printFile.call_args.args[-1]
                self.assertEqual(options["copies"], "1" if strips % 2 else str(strips // 2))
                submitted = Path(self.client.printFile.call_args.args[1])
                self.assertEqual(submitted.suffix, ".pdf" if strips % 2 else ".png")
                self.assertEqual(options["print-color-mode"], "color")
                self.assertEqual(options["PageSize"], "Postcard.Borderless")
                record = json.loads(marker.read_text())
                self.assertEqual(record["job_id"], 42)
                self.assertEqual(record["strips"], strips)
                self.assertEqual(record["sheets"], (strips + 1) // 2)
                self.verify_direct.assert_called_with(self.uri, "wlan0")

    def test_monochrome_diagnostic_uses_same_submission_path(self):
        submit_layout(self.path, 1, monochrome=True)
        self.assertEqual(self.client.printFile.call_args.args[-1]["ColorModel"], "Gray")

    def test_persistent_guard_blocks_repeated_submission_even_after_restart(self):
        submit_layout(self.path, 1)
        with self.assertRaisesRegex(RuntimeError, "already attempted"):
            submit_layout(self.path, 1)
        self.client.printFile.assert_called_once()

    def test_uncertain_submission_keeps_guard_and_is_not_retried(self):
        self.client.printFile.side_effect = RuntimeError("Lost reply")
        with self.assertRaisesRegex(RuntimeError, "Lost reply"):
            submit_layout(self.path, 1)
        marker = self.path.parent / "print-job.json"
        self.assertEqual(json.loads(marker.read_text())["state"], "submitting")
        with self.assertRaisesRegex(RuntimeError, "already attempted"):
            submit_layout(self.path, 1)
        self.client.printFile.assert_called_once()

    def test_offline_pending_or_paused_queue_does_not_submit(self):
        self.verify_direct.side_effect = RuntimeError("Offline")
        with self.assertRaisesRegex(RuntimeError, "Offline"):
            submit_layout(self.path, 1)
        self.verify_direct.side_effect = None
        self.client.getJobs.return_value = {10: {}}
        with self.assertRaisesRegex(RuntimeError, "pending"):
            submit_layout(self.path, 1)
        self.client.getJobs.return_value = {}
        self.client.getPrinters.return_value[QUEUE]["printer-state"] = 5
        with self.assertRaisesRegex(RuntimeError, "paused"):
            submit_layout(self.path, 1)
        self.client.printFile.assert_not_called()
        self.assertFalse((self.path.parent / "print-job.json").exists())

    def test_dhcp_address_change_refreshes_queue_before_submitting(self):
        self.client.getPrinters.return_value[QUEUE]["device-uri"] = "ipp://192.168.4.1/ipp/print"
        submit_layout(self.path, 1)
        self.configure_queue.assert_called_once_with(QUEUE, self.uri)

    def test_missing_layout_invalid_copies_and_missing_queue_are_explicit(self):
        for sheets in (0, 9, -1, 1.5, True):
            with self.assertRaises(ValueError):
                submit_layout(self.path, sheets)
        with self.assertRaisesRegex(ValueError, "missing"):
            submit_layout(self.path.with_name("missing.png"), 1)
        self.client.getPrinters.return_value = {}
        with self.assertRaisesRegex(RuntimeError, "queue is missing"):
            submit_layout(self.path, 1)
        self.client.printFile.assert_not_called()

    def test_even_quantities_reuse_original_lossless_png(self):
        original = self.path.read_bytes()
        for strips in (2, 4, 6, 8):
            self.assertEqual(prepare_print_document(self.path, strips), (self.path, strips // 2))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse(self.path.with_name("print_job.pdf").exists())

    def test_odd_pdf_contains_exact_number_of_strips_with_blank_last_half(self):
        original = self.path.read_bytes()
        for strips in (1, 3, 5, 7):
            with self.subTest(strips=strips):
                path, copies = prepare_print_document(self.path, strips)
                self.assertEqual(copies, 1)
                data = path.read_bytes()
                self.assertEqual(len(re.findall(rb"/Type /Page\b", data)), (strips + 1) // 2)
                images = re.findall(rb"/Subtype /Image\b.*?stream\n(.*?)\nendstream", data, re.S)
                self.assertEqual(len(images), (strips + 1) // 2)
                # Decode the actual PDF image streams, not a mocked layout.
                for index, encoded in enumerate(images):
                    with Image.open(io.BytesIO(encoded)) as page:
                        self.assertEqual(page.size, (1182, 1748))
                        self.assertEqual(page.getpixel((100, 100)), (254, 0, 0))
                        if index == len(images) - 1:
                            with page.crop((591, 0, 1182, 1748)) as blank:
                                self.assertTrue(all(low >= 250 for low, high in blank.getextrema()))
                        else:
                            with page.crop((0, 0, 591, 1748)) as left, \
                                    page.crop((591, 0, 1182, 1748)) as right:
                                self.assertLess(
                                    max(high for low, high in ImageChops.difference(left, right).getextrema()),
                                    10,
                                )
                self.assertIn(b"/MediaBox [ 0 0 283.68 419.52 ]", data)
        self.assertEqual(self.path.read_bytes(), original)

    def test_document_generation_failure_cannot_submit_or_set_attempt_guard(self):
        self.path.write_bytes(b"invalid image")
        with self.assertRaises(OSError):
            submit_layout(self.path, 3)
        self.client.printFile.assert_not_called()
        self.assertFalse((self.path.parent / "print-job.json").exists())

    def test_job_states_distinguish_completion_failure_and_pending(self):
        for state, expected in ((3, "pending"), (4, "pending"), (5, "pending"),
                                (6, "failed"), (7, "failed"), (8, "failed"), (9, "completed")):
            with self.subTest(state=state):
                self.client.getJobAttributes.return_value = {"job-state": state}
                self.assertEqual(job_status(42)[0], expected)
        self.client.getJobAttributes.return_value = {"job-state": 99}
        with self.assertRaisesRegex(RuntimeError, "Unknown state"):
            job_status(42)


if __name__ == "__main__":
    unittest.main()
