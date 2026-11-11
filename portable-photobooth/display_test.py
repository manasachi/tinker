"""Camera-free LCD photo review test; images stay in memory."""

import argparse
from pathlib import Path
import subprocess
import tkinter as tk
from typing import Optional

from PIL import Image, ImageDraw, ImageOps, ImageTk

from photobooth import CREAM, FOREST, LEAF, LIME, RED, lcd_geometry, place_on_lcd, show_error


def load_test_image(index: int, path: Optional[Path] = None) -> Image.Image:
    if index not in range(4):
        raise ValueError("The test has exactly four photos.")
    if path is not None:
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((1280, 720))
            return image
    image = Image.new("RGB", (160, 90), (FOREST, LEAF, LIME, RED)[index])
    draw = ImageDraw.Draw(image)
    draw.rectangle((4, 4, 155, 85), outline=CREAM, width=2)
    draw.text((14, 14), f"PHOTO {index + 1} OF 4", fill=CREAM)
    draw.ellipse((64, 34, 96, 66), fill=CREAM)
    return image.resize((640, 360), Image.Resampling.NEAREST)


class MemoryPhotoTest:
    def __init__(
        self, root: tk.Tk, paths: Optional[list[Path]] = None, portrait: bool = False
    ) -> None:
        if paths is not None and len(paths) != 4:
            raise ValueError("Provide exactly four image paths.")
        self.root = root
        self.paths = paths
        self.portrait = portrait
        self.photos: list[Image.Image] = []
        self.image = None
        self.index = 0
        root.title("Photobooth display test")
        root.geometry("320x480" if portrait else "480x320")
        root.configure(bg=CREAM)
        root.bind("<Escape>", lambda event: root.attributes("-fullscreen", False))
        self.frame = tk.Frame(root, bg=CREAM, padx=8, pady=6)
        self.frame.pack(fill="both", expand=True)
        self.show_start()

    def clear(self) -> None:
        for widget in self.frame.winfo_children():
            widget.destroy()
        self.image = None

    def label(self, text: str, size: int = 18) -> tk.Label:
        label = tk.Label(
            self.frame, text=text, font=("Arial", -size), bg=CREAM, fg=FOREST,
            wraplength=280 if self.portrait else 440,
        )
        label.pack(pady=5)
        return label

    def button(self, text: str, command) -> tk.Button:
        button = tk.Button(
            self.frame, text=text, command=command, font=("Arial", -16),
            bg=FOREST, fg=CREAM, activebackground=LEAF, activeforeground=CREAM,
            padx=14, pady=10,
        )
        button.pack(pady=6)
        return button

    def show_start(self) -> None:
        self.clear()
        self.photos.clear()
        self.label("Photo display test", 24)
        self.label("No camera or printer needed.", 14)
        self.label("Four images stay in RAM until you start again.", 13)
        self.label("Using your images" if self.paths else "Using colored sample images", 14)
        self.button("Simulate 4 photos", self.start)

    def start(self) -> None:
        self.clear()
        self.photos.clear()
        self.label("Simulating a photo session", 22)
        self.progress = self.label("Getting ready...", 18)
        self.label("Review will appear after all four images are ready.", 13)
        self.root.after(1000, self.capture_next)

    def capture_next(self) -> None:
        index = len(self.photos)
        try:
            path = self.paths[index] if self.paths else None
            image = load_test_image(index, path)
        except Exception as error:
            show_error(self.root, "Image test failed", f"Could not load test image:\n{error}")
            self.show_start()
            return
        self.photos.append(image)
        self.progress.config(text=f"Captured {len(self.photos)} of 4")
        if len(self.photos) < 4:
            self.root.after(1000, self.capture_next)
        else:
            self.clear()
            self.label("All 4 images are in memory", 22)
            self.label("No image files were written to disk.", 14)
            self.button("Review", lambda: self.show_photo(0))

    def show_photo(self, index: int) -> None:
        if index not in range(len(self.photos)):
            raise ValueError("Photo index is outside the captured images.")
        self.clear()
        self.index = index
        controls = tk.Frame(self.frame, bg=CREAM)
        controls.pack(side="bottom", pady=4)
        for text, destination in (("Previous", index - 1), ("Next", index + 1)):
            tk.Button(
                controls, text=text, font=("Arial", -15), padx=10, pady=10,
                state="normal" if 0 <= destination < len(self.photos) else "disabled",
                command=lambda target=destination: self.show_photo(target),
            ).pack(side="left", padx=4)
        tk.Button(
            controls, text="New test", command=self.show_start,
            font=("Arial", -15), padx=10, pady=10,
        ).pack(side="left", padx=4)
        area = tk.Frame(self.frame, bg=FOREST)
        area.pack(fill="both", expand=True, pady=4)
        self.photo_label = tk.Label(area, bg=FOREST, borderwidth=0)
        self.photo_label.place(relx=0.5, rely=0.5, anchor="center")

        def render(width: int, height: int) -> None:
            preview = self.photos[index].copy()
            preview.thumbnail((max(1, width - 4), max(1, height - 4)))
            self.image = ImageTk.PhotoImage(preview)
            self.photo_label.config(image=self.image)

        render(440, 200)
        area.bind("<Configure>", lambda event: render(event.width, event.height))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fullscreen", action="store_true")
    parser.add_argument(
        "--lcd", action="store_true",
        help="Fill the SPI-1 LCD with only the test UI.",
    )
    parser.add_argument("--portrait", action="store_true", help="Use a 320x480 window.")
    parser.add_argument(
        "--images", type=Path, nargs=4, metavar="IMAGE",
        help="Use four existing pictures instead of generated samples.",
    )
    args = parser.parse_args()
    try:
        geometry = lcd_geometry() if args.lcd else None
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError) as error:
        parser.error(f"Cannot open the LCD: {error}")
    root = tk.Tk()
    root.attributes("-fullscreen", args.fullscreen and not args.lcd)
    MemoryPhotoTest(
        root, args.images,
        portrait=args.portrait or (geometry is not None and geometry[0] < geometry[1]),
    )
    if geometry is not None:
        place_on_lcd(root, geometry)
        root.bind("<Escape>", lambda event: root.destroy())
    root.mainloop()


if __name__ == "__main__":
    main()
