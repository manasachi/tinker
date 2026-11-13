"""Prepare one two-strip sheet using monochrome circle samples, never personal photos."""

import argparse
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageDraw, ImageFont

from photobooth import Session


def circle_sample(index: int, size: tuple[int, int] = (640, 360)) -> Image.Image:
    if index not in range(4):
        raise ValueError("The test has exactly four photos.")
    image = Image.new("RGB", size, "white")
    width, height = size
    radius = min(width, height) // 6
    draw = ImageDraw.Draw(image)
    draw.text(
        (30, 25), f"PHOTO {index + 1} OF 4",
        fill="black", font=ImageFont.load_default(size=32),
    )
    draw.ellipse((
        width // 2 - radius, height // 2 - radius,
        width // 2 + radius, height // 2 + radius,
    ), fill="black")
    return image


def prepare_test_sheet(output: Path, strip_text: str = "") -> Path:
    directory = output / (
        "circle_test_" + datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:8]
    )
    session = Session(4, 5, directory, strip_text=strip_text)
    directory.mkdir(parents=True)
    for index in range(4):
        path = directory / f"circle_{index + 1:02d}.png"
        circle_sample(index, session.photo_size).save(path)
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
