"""Prepare one two-strip sheet using generated circle samples, never personal photos."""

import argparse
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from display_test import load_test_image
from photobooth import Session


def prepare_test_sheet(output: Path, strip_text: str = "") -> Path:
    directory = output / (
        "circle_test_" + datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:8]
    )
    session = Session(4, 5, directory, strip_text=strip_text)
    directory.mkdir(parents=True)
    for index in range(4):
        path = directory / f"circle_{index + 1:02d}.png"
        load_test_image(index).save(path)
        session.photos.append(path)
    return session.prepare_print_layout()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "photos")
    parser.add_argument("--strip-text", default="")
    args = parser.parse_args()
    try:
        path = prepare_test_sheet(args.output, args.strip_text)
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f"Could not prepare the test sheet: {error}\n")
    print(f"Test sheet: {path}")
    print("One sheet contains two identical four-photo strips with black borders.")
    print("No personal photos were read. No print job has been sent.")


if __name__ == "__main__":
    main()
