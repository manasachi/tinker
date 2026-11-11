"""Touchscreen photobooth for Raspberry Pi OS and a Picamera2 camera."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from typing import Protocol
from uuid import uuid4


FOREST = "#386641"
LEAF = "#6a994e"
LIME = "#a7c957"
CREAM = "#f2e8cf"
RED = "#bc4749"
POSITIONING_SECONDS = 15


class Camera(Protocol):
    def capture_file(self, path: str) -> None: ...


@dataclass
class Session:
    photo_count: int
    interval: int
    directory: Path
    photos: list[Path] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        if self.photo_count not in (3, 4):
            raise ValueError("Choose either 3 or 4 photos.")
        if self.interval not in (5, 10):
            raise ValueError("Choose either a 5 or 10 second timer.")

    def capture_next(self, camera: Camera) -> Path:
        if len(self.photos) >= self.photo_count:
            raise ValueError("All photos in this session have already been taken.")
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"photo_{len(self.photos) + 1:02d}.jpg"
        camera.capture_file(str(path))
        self.photos.append(path)
        return path

    def prepare_print_layout(self) -> Path:
        from PIL import Image, ImageOps

        if len(self.photos) != self.photo_count:
            raise ValueError("Capture all photos before preparing the print layout.")
        strip_width, height = 600, 1800
        margin, gap = 30, 30
        photo_width = strip_width - 2 * margin
        photo_height = (height - 2 * margin - gap * (self.photo_count - 1)) // self.photo_count
        strip = Image.new("RGB", (strip_width, height), "white")
        for index, path in enumerate(self.photos):
            with Image.open(path) as photo:
                oriented = ImageOps.exif_transpose(photo).convert("RGB")
                fitted = ImageOps.fit(
                    oriented, (photo_width, photo_height),
                    method=Image.Resampling.LANCZOS,
                )
                strip.paste(fitted, (margin, margin + index * (photo_height + gap)))
        sheet = Image.new("RGB", (strip_width * 2, height), "white")
        sheet.paste(strip, (0, 0))
        sheet.paste(strip, (strip_width, 0))
        path = self.directory / "print_layout.png"
        sheet.save(path, dpi=(300, 300))
        return path


class PiCamera:
    """Keep camera setup, capture, and cleanup on the same worker thread."""

    def __init__(self) -> None:
        self.camera = None

    def prepare(self) -> None:
        if self.camera is None:
            from picamera2 import Picamera2
            from libcamera import controls
            from time import sleep

            camera = Picamera2()
            try:
                camera.configure(
                    camera.create_still_configuration(
                        main={"size": (2304, 1296), "format": "RGB888"},
                        buffer_count=2,
                    )
                )
                if "AfMode" in camera.camera_controls:
                    camera.set_controls({"AfMode": controls.AfModeEnum.Continuous})
                camera.start()
                sleep(2)  # Allow automatic exposure and white balance to settle.
            except Exception:
                camera.close()
                raise
            self.camera = camera

    def preview_image(self):
        self.prepare()
        image = self.camera.capture_image("main")
        image.thumbnail((640, 360))
        return image

    def capture_file(self, path: str) -> None:
        self.prepare()
        self.camera.capture_file(path)

    def close(self) -> None:
        if self.camera is not None:
            self.camera.close()
            self.camera = None


class PhotoBooth:
    def __init__(self, root: tk.Tk, output: Path, fullscreen: bool) -> None:
        self.root = root
        self.output = output
        self.camera = PiCamera()
        self.worker = ThreadPoolExecutor(max_workers=1)
        self.session = None
        self.closed = False
        self.active = False
        self.previewing = False
        self.preview_ready = False
        self.review_index = 0
        self.image = None
        root.title("Portable Photobooth")
        root.geometry("800x480")
        root.configure(bg=CREAM)
        root.attributes("-fullscreen", fullscreen)
        root.bind("<Escape>", lambda event: root.attributes("-fullscreen", False))
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.frame = tk.Frame(root, padx=16, pady=12, bg=CREAM)
        self.frame.pack(fill="both", expand=True)
        self.show_options()

    def clear(self) -> None:
        for widget in self.frame.winfo_children():
            widget.destroy()
        self.image = None

    def label(self, text: str, size: int = 22) -> tk.Label:
        label = tk.Label(
            self.frame, text=text, font=("Arial", size), bg=CREAM, fg=FOREST
        )
        label.pack(pady=8)
        return label

    def button(self, text: str, command, **options) -> tk.Button:
        button = tk.Button(
            self.frame, text=text, command=command, font=("Arial", 18),
            padx=14, pady=8, bg=FOREST, fg=CREAM,
            activebackground=LEAF, activeforeground=CREAM, **options
        )
        button.pack(pady=6)
        return button

    def show_options(self) -> None:
        self.active = False
        self.previewing = False
        self.clear()
        tk.Label(
            self.frame, text="Make a little memory",
            font=("Arial", 25, "bold"), bg=CREAM, fg=FOREST,
        ).pack(pady=(4, 16))
        self.count = tk.IntVar(value=4)
        self.interval = tk.IntVar(value=5)
        cards = tk.Frame(self.frame, bg=CREAM)
        cards.pack(fill="x", padx=12)
        cards.columnconfigure((0, 1), weight=1, uniform="options")
        for column, (title, hint, variable, choices, suffix) in enumerate((
            ("01  THE STRIP", "How many photos?", self.count, (3, 4), "photos"),
            ("02  THE PACE", "Seconds between photos", self.interval, (5, 10), "sec"),
        )):
            card = tk.Frame(
                cards, bg=CREAM, padx=12, pady=12,
                highlightbackground=LEAF, highlightthickness=2,
            )
            card.grid(row=0, column=column, sticky="nsew", padx=6)
            tk.Label(
                card, text=title, font=("Arial", 11, "bold"), bg=CREAM, fg=FOREST,
            ).pack(anchor="w")
            tk.Label(
                card, text=hint, font=("Arial", 11), bg=CREAM, fg=FOREST,
            ).pack(anchor="w", pady=(4, 10))
            row = tk.Frame(card, bg=CREAM)
            row.pack(fill="x")
            for value in choices:
                choice = tk.Radiobutton(
                    row, text=f"{value} {suffix}", variable=variable, value=value,
                    indicatoron=False, font=("Arial", 17, "bold"),
                    bg=CREAM, fg=FOREST, selectcolor=LIME,
                    activebackground=LIME, activeforeground=FOREST,
                    relief="sunken", offrelief="flat", borderwidth=2,
                    highlightbackground=LEAF, highlightcolor=FOREST,
                    highlightthickness=2, padx=8, pady=12,
                )
                choice.pack(side="left", fill="x", expand=True, padx=3)
        self.summary = tk.StringVar()
        for variable in (self.count, self.interval):
            variable.trace_add("write", self.update_summary)
        self.update_summary()
        tk.Label(
            self.frame, textvariable=self.summary, font=("Arial", 12, "bold"),
            bg=CREAM, fg=FOREST,
        ).pack(pady=(16, 8))
        self.button("Start photo session", self.start, width=23)
        tk.Label(
            self.frame, text=f"You'll have {POSITIONING_SECONDS} seconds to get situated.",
            font=("Arial", 11), bg=CREAM, fg=FOREST,
        ).pack(pady=(6, 0))

    def update_summary(self, *_args) -> None:
        self.summary.set(
            f"{self.count.get()} photos  /  {self.interval.get()} seconds between shots"
        )

    def start(self) -> None:
        if self.closed or self.active:
            return
        name = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:8]
        self.session = Session(self.count.get(), self.interval.get(), self.output / name)
        self.active = True
        self.previewing = True
        self.preview_ready = False
        self.clear()
        header = tk.Frame(self.frame, bg=CREAM)
        header.pack(fill="x", pady=(0, 8))
        self.status = tk.Label(
            header, text="Get ready!", font=("Arial", 20, "bold"), bg=CREAM, fg=FOREST
        )
        self.status.pack(side="left", padx=8)
        self.countdown = tk.Label(
            header, text="", font=("Arial", 36, "bold"), bg=CREAM, fg=RED
        )
        self.countdown.pack(side="right", padx=8)
        self.preview_frame = tk.Frame(self.frame, bg=FOREST)
        self.preview_frame.pack(fill="both", expand=True)
        self.preview_label = tk.Label(
            self.preview_frame, text="Starting camera...", bg=FOREST, fg=CREAM,
            font=("Arial", 18), borderwidth=0,
        )
        self.preview_label.place(relx=0.5, rely=0.5, anchor="center")
        self.request_preview(self.session)
        self.tick(POSITIONING_SECONDS, self.session)

    def is_active(self, session: Session) -> bool:
        return not self.closed and self.active and session is self.session

    def request_preview(self, session: Session) -> None:
        if not self.is_active(session) or not self.previewing:
            return
        future = self.worker.submit(self.camera.preview_image)
        self.root.after(50, self.check_preview, future, session)

    def check_preview(self, future, session: Session) -> None:
        if not self.is_active(session) or not self.previewing:
            return
        if not future.done():
            self.root.after(50, self.check_preview, future, session)
            return
        try:
            from PIL import ImageTk

            frame = future.result()
            frame.thumbnail((
                max(1, self.preview_frame.winfo_width() - 8),
                max(1, self.preview_frame.winfo_height() - 8),
            ))
            self.image = ImageTk.PhotoImage(frame)
            self.preview_label.config(image=self.image, text="")
        except Exception as error:
            self.active = False
            self.previewing = False
            messagebox.showerror(
                "Camera preview failed",
                f"Could not show the camera preview:\n{error}\n\n"
                f"Any completed photos remain in:\n{session.directory}",
            )
            self.show_options()
            return
        self.preview_ready = True
        self.root.after(150, self.request_preview, session)

    def tick(self, remaining: int, session: Session) -> None:
        if not self.is_active(session):
            return
        self.status.config(
            text=(
                f"Get situated! Photo 1 of {session.photo_count}"
                if not session.photos
                else f"Photo {len(session.photos) + 1} of {session.photo_count}"
            )
        )
        if remaining:
            self.countdown.config(text=str(remaining))
            self.root.after(1000, self.tick, remaining - 1, session)
        elif not self.preview_ready:
            self.status.config(text="Waiting for camera...")
            self.countdown.config(text="")
            self.root.after(50, self.tick, 0, session)
        else:
            self.countdown.config(text="Smile!")
            future = self.worker.submit(session.capture_next, self.camera)
            self.root.after(50, self.check_capture, future, session)

    def check_capture(self, future, session: Session) -> None:
        if not self.is_active(session):
            return
        if not future.done():
            self.root.after(50, self.check_capture, future, session)
            return
        try:
            future.result()
        except Exception as error:
            self.active = False
            self.previewing = False
            messagebox.showerror(
                "Capture failed",
                f"Could not capture the photo:\n{error}\n\n"
                f"Any completed photos remain in:\n{session.directory}",
            )
            self.show_options()
            return
        if len(session.photos) < session.photo_count:
            self.tick(session.interval, session)
        else:
            self.previewing = False
            self.status.config(text="Preparing your photo strips...")
            self.countdown.config(text="")
            future = self.worker.submit(session.prepare_print_layout)
            self.root.after(50, self.check_layout, future, session)

    def check_layout(self, future, session: Session) -> None:
        if not self.is_active(session):
            return
        if not future.done():
            self.root.after(50, self.check_layout, future, session)
            return
        try:
            future.result()
        except Exception as error:
            messagebox.showerror(
                "Print layout failed",
                f"Could not prepare the photo strips:\n{error}\n\n"
                f"Your original photos remain in:\n{session.directory}",
            )
        self.active = False
        self.clear()
        self.label("Your photos are ready!")
        self.button("Review", lambda: self.show_photo(0))

    def show_photo(self, index: int) -> None:
        from PIL import Image, ImageOps, ImageTk

        try:
            with Image.open(self.session.photos[index]) as photo:
                preview = ImageOps.exif_transpose(photo)
                preview.thumbnail((
                    max(1, self.frame.winfo_width() - 40),
                    max(1, self.frame.winfo_height() - 170),
                ))
                image = ImageTk.PhotoImage(preview)
        except Exception as error:
            messagebox.showerror("Review failed", f"Could not display photo:\n{error}")
            return
        self.clear()
        self.review_index = index
        self.image = image
        self.label(f"Photo {index + 1} of {len(self.session.photos)}", 18)
        tk.Label(self.frame, image=self.image).pack(expand=True)
        row = tk.Frame(self.frame)
        row.pack(pady=6)
        for text, step in (("Previous", -1), ("Next", 1)):
            destination = index + step
            tk.Button(
                row, text=text, font=("Arial", 18), padx=12, pady=8,
                state="normal" if 0 <= destination < len(self.session.photos) else "disabled",
                command=lambda target=destination: self.show_photo(target),
            ).pack(side="left", padx=6)
        tk.Button(
            row, text="Print (coming soon)", state="disabled",
            font=("Arial", 18), padx=12, pady=8,
        ).pack(side="left", padx=6)
        self.button("New session", self.show_options)

    def close(self) -> None:
        self.closed = True
        self.active = False
        self.previewing = False
        cleanup = self.worker.submit(self.camera.close)
        self.worker.shutdown(wait=False)
        self.root.destroy()
        try:
            cleanup.result()
        except Exception as error:
            raise RuntimeError("Could not close the camera cleanly.") from error


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fullscreen", action="store_true")
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "photos")
    args = parser.parse_args()
    root = tk.Tk()
    PhotoBooth(root, args.output, args.fullscreen)
    root.mainloop()


if __name__ == "__main__":
    main()
