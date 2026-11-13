"""Submit saved strips once and report the local CUPS job state."""

import json
import os
from pathlib import Path

from portable_setup import configure_queue, direct_printer_uri, verify_direct


QUEUE = "SELPHY_CP1500_Direct"


def validate_strip_count(strips: int) -> None:
    if type(strips) is not int or strips not in range(1, 9):
        raise ValueError("Choose between 1 and 8 photo strips.")


def prepare_print_document(path: Path, strips: int) -> tuple[Path, int]:
    validate_strip_count(strips)
    if strips % 2 == 0:
        return path, strips // 2
    from PIL import Image

    document = path.with_name("print_job.pdf")
    with Image.open(path) as source:
        sheet = source.convert("RGB")
    try:
        if sheet.width % 2:
            raise ValueError("The print layout must contain two equal-width strips.")
        with Image.new("RGB", sheet.size, "white") as last:
            with sheet.crop((0, 0, sheet.width // 2, sheet.height)) as strip:
                last.paste(strip, (0, 0))
            pages = [sheet] * (strips // 2) + [last]
            pages[0].save(
                document, "PDF", save_all=True, append_images=pages[1:],
                resolution=300, quality=100, subsampling=0,
            )
    finally:
        sheet.close()
    return document, 1


def connection():
    try:
        import cups
    except ImportError as error:
        raise RuntimeError("Install printing support with: sudo apt install python3-cups") from error
    return cups.Connection()


def submit_layout(path: Path, strips: int, *, monochrome: bool = False) -> int:
    validate_strip_count(strips)
    if not path.is_file():
        raise ValueError(f"The saved print layout is missing: {path}")
    marker = path.parent / "print-job.json"
    if marker.exists():
        raise RuntimeError(
            "Printing was already attempted for this session. Check the printer "
            "and print-job.json before any manual reprint."
        )
    uri = direct_printer_uri("wlan0")
    verify_direct(uri, "wlan0")
    client = connection()
    printers = client.getPrinters()
    if QUEUE not in printers:
        raise RuntimeError("The direct print queue is missing. Run portable_setup.py connect first.")
    if printers[QUEUE]["printer-state"] == 5:
        raise RuntimeError("The CUPS queue is paused. Resolve its error and resume it before printing.")
    if client.getJobs(which_jobs="not-completed"):
        raise RuntimeError("CUPS already has a pending job. Resolve it before printing again.")
    if printers[QUEUE]["device-uri"] != uri:
        configure_queue(QUEUE, uri)
    document, copies = prepare_print_document(path, strips)
    sheets = (strips + 1) // 2
    options = {
        "copies": str(copies),
        "PageSize": "Postcard.Borderless",
        "print-scaling": "fit",
        "orientation-requested": "3",
        "sides": "one-sided",
        "ColorModel": "Gray" if monochrome else "RGB",
        "print-color-mode": "monochrome" if monochrome else "color",
    }
    # Persist intent before submitting: a crash or uncertain reply must not cause a retry.
    with marker.open("x") as record:
        json.dump({"state": "submitting", "strips": strips, "sheets": sheets}, record)
        record.flush()
        os.fsync(record.fileno())
    job = client.printFile(QUEUE, str(document.resolve()), "Photobooth strips", options)
    marker.write_text(json.dumps({
        "state": "submitted", "job_id": job, "strips": strips, "sheets": sheets,
    }) + "\n")
    return job


def job_status(job: int) -> tuple[str, str]:
    attributes = connection().getJobAttributes(job)
    state = attributes["job-state"]
    detail = str(attributes.get("job-printer-state-message") or attributes.get("job-state-reasons", ""))
    if state == 9:
        return "completed", "CUPS reports complete. Collect your strips."
    if state in (7, 8):
        return "failed", f"Job {job} was canceled or aborted. {detail}"
    if state == 6:
        return "failed", f"Job {job} is stopped. Check the printer. {detail}"
    if state not in (3, 4, 5):
        raise RuntimeError(f"Unknown state {state} for print job {job}.")
    return "pending", f"Job {job}: printing / waiting. {detail}"
