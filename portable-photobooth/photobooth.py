"""Touchscreen photobooth for Raspberry Pi OS and a Picamera2 camera."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
import io
import json
import logging
import math
from pathlib import Path
import struct
import subprocess
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional, Protocol
from uuid import uuid4
import wave


FOREST = "#386641"
LEAF = "#6a994e"
LIME = "#a7c957"
CREAM = "#f2e8cf"
RED = "#bc4749"
POSITIONING_SECONDS = 15


def render_strip_footer(text: str):
    from PIL import Image, ImageDraw, ImageFont

    footer = Image.new("RGB", (600, 300), "black")
    draw = ImageDraw.Draw(footer)
    for size in range(64, 27, -2):
        try:
            font = ImageFont.load_default(size=size)
        except TypeError as error:
            raise RuntimeError("Strip text requires Pillow 10.1 or newer.") from error
        lines = []
        for paragraph in text.strip().splitlines():
            line = ""
            for word in paragraph.split():
                candidate = f"{line} {word}".strip()
                if line and draw.textlength(candidate, font=font) > 540:
                    lines.append(line)
                    line = word
                else:
                    line = candidate
            lines.append(line)
        wrapped = "\n".join(lines)
        left, top, right, bottom = draw.multiline_textbbox(
            (0, 0), wrapped, font=font, spacing=8, align="center",
        )
        width, height = right - left, bottom - top
        if width <= 540 and height <= 240:
            draw.multiline_text(
                ((600 - width) / 2 - left, (300 - height) / 2 - top),
                wrapped, font=font, fill="white", spacing=8, align="center",
            )
            return footer
    raise ValueError("Message is too long to print clearly. Please shorten it.")


def shutter_wav() -> bytes:
    rate = 22050
    count = int(rate * 0.06)
    samples = [
        int(6000 * (1 - i / count) ** 3 * (
            math.sin(2 * math.pi * 1800 * i / rate)
            + 0.5 * math.sin(2 * math.pi * 3200 * i / rate)
        ))
        for i in range(count)
    ]
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(struct.pack(f"<{count}h", *samples))
    return buffer.getvalue()


def play_shutter_sound() -> None:
    try:
        subprocess.run(
            ["aplay", "-q"], input=shutter_wav(), check=True,
            capture_output=True, timeout=2,
        )
    except subprocess.CalledProcessError as error:
        detail = error.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"Shutter sound playback failed: {detail or error}") from error


def lcd_geometry() -> tuple[int, int, int, int]:
    result = subprocess.run(
        ["wlr-randr", "--json"], check=True, capture_output=True, text=True,
    )
    output = next(
        (output for output in json.loads(result.stdout) if output["name"] == "SPI-1"),
        None,
    )
    if output is None or not output.get("enabled"):
        raise ValueError("The SPI-1 LCD is not enabled in the Wayland desktop.")
    mode = next((mode for mode in output["modes"] if mode.get("current")), None)
    if mode is None:
        raise ValueError("The SPI-1 LCD has no active display mode.")
    width, height = mode["width"], mode["height"]
    if output["transform"] in ("90", "270", "flipped-90", "flipped-270"):
        width, height = height, width
    scale = output["scale"]
    if scale <= 0:
        raise ValueError("The SPI-1 LCD has an invalid display scale.")
    return (
        round(width / scale), round(height / scale),
        output["position"]["x"], output["position"]["y"],
    )


def place_on_lcd(root: tk.Tk, geometry: tuple[int, int, int, int]) -> None:
    width, height, x, y = geometry
    root.overrideredirect(True)
    root.geometry(f"{width}x{height}{x:+d}{y:+d}")


def show_error(root: tk.Tk, title: str, message: str) -> None:
    if not root.overrideredirect():
        messagebox.showerror(title, message, parent=root)
        return
    dialog = tk.Toplevel(root)
    dialog.title(title)
    dialog.overrideredirect(True)
    dialog.geometry(root.winfo_geometry())
    dialog.configure(bg=CREAM)
    tk.Label(
        dialog, text=title, font=("Arial", -20, "bold"), fg=RED, bg=CREAM,
        wraplength=root.winfo_width() - 24,
    ).pack(padx=12, pady=12)
    tk.Message(
        dialog, text=message, font=("Arial", -14), fg=FOREST, bg=CREAM,
        width=root.winfo_width() - 24,
    ).pack(fill="both", expand=True, padx=12, pady=8)
    tk.Button(
        dialog, text="OK", command=dialog.destroy, font=("Arial", -18),
        bg=FOREST, fg=CREAM, padx=24, pady=12,
    ).pack(pady=12)
    dialog.bind("<Escape>", lambda event: dialog.destroy())
    dialog.lift()
    dialog.wait_visibility()
    dialog.grab_set()
    root.wait_window(dialog)


class Camera(Protocol):
    def capture_file(self, path: str) -> None: ...


@dataclass
class Session:
    photo_count: int
    interval: int
    directory: Path
    strip_count: int = 2
    strip_text: str = ""
    photos: list[Path] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        if self.photo_count not in (3, 4):
            raise ValueError("Choose either 3 or 4 photos.")
        if self.interval not in (5, 10):
            raise ValueError("Choose either a 5 or 10 second timer.")
        if self.strip_count not in (2, 4):
            raise ValueError("Choose either 2 or 4 photo strips.")
        self.strip_text = self.strip_text.strip()

    @property
    def sheet_count(self) -> int:
        return self.strip_count // 2

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
        footer = render_strip_footer(self.strip_text) if self.strip_text else None
        photo_area_height = height - footer.height if footer is not None else height
        margin, gap = 30, 30
        photo_width = strip_width - 2 * margin
        photo_height = (
            photo_area_height - 2 * margin - gap * (self.photo_count - 1)
        ) // self.photo_count
        strip = Image.new("RGB", (strip_width, height), "black")
        for index, path in enumerate(self.photos):
            with Image.open(path) as photo:
                oriented = ImageOps.exif_transpose(photo).convert("RGB")
                fitted = ImageOps.fit(
                    oriented, (photo_width, photo_height),
                    method=Image.Resampling.LANCZOS,
                )
                strip.paste(fitted, (margin, margin + index * (photo_height + gap)))
        if footer is not None:
            strip.paste(footer, (0, photo_area_height))
        sheet = Image.new("RGB", (strip_width * 2, height), "black")
        sheet.paste(strip, (0, 0))
        sheet.paste(strip, (strip_width, 0))
        path = self.directory / "print_layout.png"
        sheet.save(path, dpi=(300, 300))
        return path


class PiCamera:
    """Keep camera setup, capture, and cleanup on the same worker thread."""

    def __init__(self, preview_size: tuple[int, int] = (640, 360)) -> None:
        self.camera = None
        self.preview_size = preview_size

    def prepare(self) -> None:
        if self.camera is None:
            from picamera2 import Picamera2
            from libcamera import controls
            from time import sleep

            if not Picamera2.global_camera_info():
                raise RuntimeError(
                    "No camera detected. Shut down the Pi before connecting the "
                    "CSI camera, then restart. For a camera-free test, run "
                    "display_test.py --lcd."
                )
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
        image.thumbnail(self.preview_size)
        return image

    def capture_file(self, path: str) -> None:
        self.prepare()
        self.camera.capture_file(path)

    def close(self) -> None:
        if self.camera is not None:
            self.camera.close()
            self.camera = None


class PhotoBooth:
    def __init__(
        self, root: tk.Tk, output: Path, fullscreen: bool, compact: bool = False,
        portrait: bool = False, shutter_sound: bool = False, strip_text: str = "",
    ) -> None:
        self.root = root
        self.output = output
        self.portrait = portrait or (
            root.winfo_screenwidth() < 640
            and root.winfo_screenwidth() < root.winfo_screenheight()
        )
        self.compact = (
            compact or self.portrait
            or root.winfo_screenwidth() < 640 or root.winfo_screenheight() < 400
        )
        self.camera = PiCamera((480, 270) if self.compact else (640, 360))
        self.worker = ThreadPoolExecutor(max_workers=1)
        self.shutter_sound = shutter_sound
        self.sound_worker = ThreadPoolExecutor(max_workers=1) if shutter_sound else None
        self.session = None
        self.closed = False
        self.active = False
        self.previewing = False
        self.preview_ready = False
        self.image = None
        self.strip_text = tk.StringVar(master=root, value=strip_text.strip())
        root.title("Portable Photobooth")
        root.geometry(
            "320x480" if self.portrait else "480x320" if self.compact else "800x480"
        )
        root.configure(bg=CREAM)
        root.attributes("-fullscreen", fullscreen)
        root.bind("<Escape>", lambda event: root.attributes("-fullscreen", False))
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.frame = tk.Frame(
            root, padx=8 if self.compact else 16,
            pady=6 if self.compact else 12, bg=CREAM,
        )
        self.frame.pack(fill="both", expand=True)
        self.show_options()

    def clear(self) -> None:
        for widget in self.frame.winfo_children():
            widget.destroy()
        self.image = None

    def font(self, size: int, compact_size: int, bold: bool = False) -> tuple[str, int, str]:
        # Pixel-sized compact fonts keep the 480x320 layout independent of desktop DPI.
        return ("Arial", -compact_size if self.compact else size, "bold" if bold else "normal")

    def label(self, text: str, size: int = 22) -> tk.Label:
        label = tk.Label(
            self.frame, text=text, font=self.font(size, min(size, 20)), bg=CREAM, fg=FOREST
        )
        label.pack(pady=4 if self.compact else 8)
        return label

    def button(
        self, text: str, command, parent: Optional[tk.Misc] = None, **options,
    ) -> tk.Button:
        button = tk.Button(
            self.frame if parent is None else parent,
            text=text, command=command, font=self.font(18, 16),
            padx=10 if self.compact else 14, pady=6 if self.compact else 8,
            bg=FOREST, fg=CREAM,
            activebackground=LEAF, activeforeground=CREAM, **options
        )
        button.pack(pady=4 if self.compact else 6)
        return button

    def show_options(self, *, preserve_choices: bool = False) -> None:
        count = self.count.get() if preserve_choices else 4
        interval = self.interval.get() if preserve_choices else 5
        strips = self.strip_count.get() if preserve_choices else 2
        self.active = False
        self.previewing = False
        self.clear()
        tk.Label(
            self.frame, text="Make a little memory",
            font=self.font(25, 22, bold=True), bg=CREAM, fg=FOREST,
        ).pack(pady=(4, 6 if self.portrait else 10 if self.compact else 16))
        self.count = tk.IntVar(value=count)
        self.interval = tk.IntVar(value=interval)
        self.strip_count = tk.IntVar(value=strips)
        cards = tk.Frame(self.frame, bg=CREAM)
        cards.pack(fill="x", padx=0 if self.compact else 12)
        cards.columnconfigure(0 if self.portrait else (0, 1, 2), weight=1, uniform="options")
        for column, (title, hint, variable, choices) in enumerate((
            ("01  THE PHOTOS", "How many photos?", self.count, (3, 4)),
            ("02  THE PACE", "Seconds between photos", self.interval, (5, 10)),
            ("03  THE COPIES", "How many strips?", self.strip_count, (2, 4)),
        )):
            card = tk.Frame(
                cards, bg=CREAM, padx=6 if self.compact else 12,
                pady=4 if self.portrait else 8 if self.compact else 12,
                highlightbackground=LEAF, highlightthickness=2,
            )
            card.grid(
                row=column if self.portrait else 0,
                column=0 if self.portrait else column,
                sticky="nsew", padx=4 if self.compact else 6,
                pady=2 if self.portrait else 0,
            )
            tk.Label(
                card, text=title, font=self.font(11, 11, bold=True), bg=CREAM, fg=FOREST,
            ).pack(anchor="w")
            tk.Label(
                card, text=hint, font=self.font(11, 11), bg=CREAM, fg=FOREST,
            ).pack(
                anchor="w", pady=(2, 4) if self.portrait else (4, 8 if self.compact else 10)
            )
            row = tk.Frame(card, bg=CREAM)
            row.pack(fill="x")
            for value in choices:
                choice = tk.Radiobutton(
                    row, text=str(value),
                    variable=variable, value=value,
                    indicatoron=False, font=self.font(17, 17, bold=True),
                    bg=CREAM, fg=FOREST, selectcolor=LIME,
                    activebackground=LIME, activeforeground=FOREST,
                    relief="sunken", offrelief="flat", borderwidth=2,
                    highlightbackground=LEAF, highlightcolor=FOREST,
                    highlightthickness=2, padx=4 if self.compact else 8,
                    pady=8 if self.portrait else 10 if self.compact else 12,
                )
                choice.pack(side="left", fill="x", expand=True, padx=3)
        self.summary = tk.StringVar()
        for variable in (self.count, self.interval, self.strip_count):
            variable.trace_add("write", self.update_summary)
        self.update_summary()
        tk.Label(
            self.frame, textvariable=self.summary, font=self.font(12, 12, bold=True),
            bg=CREAM, fg=FOREST,
        ).pack(pady=(6, 2) if self.portrait else (10, 4) if self.compact else (16, 8))
        actions = tk.Frame(self.frame, bg=CREAM)
        actions.pack(fill="x")
        self.button(
            f"Strip text: {'on' if self.strip_text.get() else 'off'}",
            self.show_text_settings, parent=actions,
        ).pack(side="left", expand=True)
        self.button(
            "Start session" if self.portrait else "Start photo session",
            self.start, parent=actions,
        ).pack(
            side="left", expand=True,
        )
        tk.Label(
            self.frame, text=f"You'll have {POSITIONING_SECONDS} seconds to get situated.",
            font=self.font(11, 12), bg=CREAM, fg=FOREST,
        ).pack(pady=(6, 0))

    def show_text_settings(self) -> None:
        if self.closed or self.active:
            return
        self.clear()
        self.label("Text on your strip", 20)
        self.text_entry = tk.Text(
            self.frame, height=2, width=20, wrap="word", font=self.font(14, 14),
            bg="white", fg=FOREST, insertbackground=FOREST, undo=True,
        )
        self.text_entry.pack(fill="x", pady=4)
        self.text_entry.insert("1.0", self.strip_text.get())
        self.text_entry.mark_set("insert", "end-1c")
        self.text_error = tk.Label(
            self.frame, text="Bottom 1/6 for text; blank = full-height photos.",
            font=self.font(11, 11), bg=CREAM, fg=FOREST,
            wraplength=280 if self.portrait else 440 if self.compact else 700,
        )
        self.text_error.pack(fill="x", pady=2)
        self.text_keyboard = tk.Frame(self.frame, bg=CREAM)
        self.text_keyboard.pack(fill="x")
        self.keyboard_symbols = False
        self.keyboard_uppercase = True
        self.draw_text_keyboard()
        actions = tk.Frame(self.frame, bg=CREAM)
        actions.pack(fill="x")
        for title, command in (
            ("Cancel", lambda: self.show_options(preserve_choices=True)),
            ("Clear", lambda: self.text_entry.delete("1.0", "end")),
            ("Save", self.save_strip_text),
        ):
            self.button(title, command, parent=actions).pack(side="left", expand=True)
        self.text_entry.focus_set()

    def insert_text(self, text: str) -> None:
        if self.text_entry.tag_ranges("sel"):
            self.text_entry.delete("sel.first", "sel.last")
        self.text_entry.insert("insert", text)
        self.text_entry.see("insert")
        self.text_entry.focus_set()

    def backspace_text(self) -> None:
        if self.text_entry.tag_ranges("sel"):
            self.text_entry.delete("sel.first", "sel.last")
        else:
            self.text_entry.delete("insert-1c", "insert")
        self.text_entry.focus_set()

    def draw_text_keyboard(self) -> None:
        for widget in self.text_keyboard.winfo_children():
            widget.destroy()
        style = ttk.Style(self.root)
        if "StripKey.border" not in style.element_names():
            style.element_create("StripKey.border", "from", "clam", "Button.border")
        style.layout("StripKey.TButton", [
            ("StripKey.border", {"sticky": "nswe", "children": [
                ("Button.padding", {"sticky": "nswe", "children": [
                    ("Button.label", {"sticky": "nswe"}),
                ]}),
            ]}),
        ])
        style.configure(
            "StripKey.TButton", font=self.font(14, 14),
            padding=(2, 10 if self.portrait else 6), borderwidth=1,
            background=FOREST, foreground=CREAM,
        )
        style.map("StripKey.TButton", background=[("pressed", LEAF), ("active", LEAF)])
        rows = ("1234567890", "-/:&'.,!?", "()@#+=_") if self.keyboard_symbols else (
            "QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM",
        )
        self.text_keyboard.columnconfigure(tuple(range(10)), weight=1, uniform="keys")

        def key(title, command, row, column, span=1):
            ttk.Button(
                self.text_keyboard, text=title, command=command, style="StripKey.TButton",
                width=0, takefocus=False,
            ).grid(row=row, column=column, columnspan=span, sticky="ew", padx=1, pady=1)

        for row, letters in enumerate(rows):
            for column, letter in enumerate(letters):
                value = letter if self.keyboard_uppercase else letter.lower()
                key(value, lambda value=value: self.insert_text(value), row, column)

        def toggle(symbols=False):
            if symbols:
                self.keyboard_symbols = not self.keyboard_symbols
            else:
                self.keyboard_uppercase = not self.keyboard_uppercase
            self.draw_text_keyboard()

        key("ABC" if self.keyboard_symbols else "123", lambda: toggle(True), 3, 0, 2)
        key("Aa", toggle, 3, 2, 2)
        key("Space", lambda: self.insert_text(" "), 3, 4, 4)
        key("Back", self.backspace_text, 3, 8, 2)

    def save_strip_text(self) -> None:
        text = self.text_entry.get("1.0", "end-1c").strip()
        try:
            if text:
                render_strip_footer(text)
        except (OSError, RuntimeError, ValueError) as error:
            self.text_error.config(text=str(error), fg=RED)
            return
        self.strip_text.set(text)
        self.show_options(preserve_choices=True)

    def update_summary(self, *_args) -> None:
        strips = self.strip_count.get()
        sheets = strips // 2
        self.summary.set(
            f"{self.count.get()} photos  /  {self.interval.get()} seconds between shots\n"
            f"{strips} strips  /  {sheets} {'sheet' if sheets == 1 else 'sheets'}"
        )

    def start(self) -> None:
        if self.closed or self.active:
            return
        self.shutter_sound = self.sound_worker is not None
        name = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:8]
        self.session = Session(
            self.count.get(), self.interval.get(), self.output / name,
            strip_count=self.strip_count.get(), strip_text=self.strip_text.get(),
        )
        self.active = True
        self.previewing = True
        self.preview_ready = False
        self.clear()
        header = tk.Frame(self.frame, bg=CREAM)
        header.pack(fill="x", pady=(0, 8))
        self.status = tk.Label(
            header, text="Get ready!", font=self.font(20, 16, bold=True), bg=CREAM, fg=FOREST
        )
        self.status.pack(side="top" if self.portrait else "left", padx=8)
        self.countdown = tk.Label(
            header, text="", font=self.font(36, 32, bold=True), bg=CREAM, fg=RED
        )
        self.countdown.pack(side="top" if self.portrait else "right", padx=8)
        self.sound_warning = tk.Label(
            header, text="", font=self.font(11, 11), bg=CREAM, fg=RED,
        )
        self.preview_frame = tk.Frame(self.frame, bg=FOREST)
        self.preview_frame.pack(fill="both", expand=True)
        self.preview_label = tk.Label(
            self.preview_frame, text="Starting camera...", bg=FOREST, fg=CREAM,
            font=self.font(18, 16), borderwidth=0,
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
            show_error(
                self.root,
                "Camera preview failed",
                f"Could not show the camera preview:\n{error}\n\n"
                f"Any completed photos remain in:\n{session.directory}",
            )
            self.show_options()
            return
        self.preview_ready = True
        self.root.after(250 if self.compact else 150, self.request_preview, session)

    def tick(self, remaining: int, session: Session) -> None:
        if not self.is_active(session) or len(session.photos) >= session.photo_count:
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
            show_error(
                self.root,
                "Capture failed",
                f"Could not capture the photo:\n{error}\n\n"
                f"Any completed photos remain in:\n{session.directory}",
            )
            self.show_options()
            return
        if self.shutter_sound and self.sound_worker is not None:
            sound = self.sound_worker.submit(play_shutter_sound)
            self.root.after(50, self.check_sound, sound, session)
        if len(session.photos) < session.photo_count:
            self.tick(session.interval, session)
        else:
            self.status.config(
                text="Preparing strips..." if self.compact else "Preparing your photo strips..."
            )
            self.countdown.config(text="")
            future = self.worker.submit(session.prepare_print_layout)
            self.root.after(50, self.check_layout, future, session)

    def check_sound(self, future, session: Session) -> None:
        if not future.done():
            if not self.closed:
                self.root.after(50, self.check_sound, future, session)
            return
        try:
            future.result()
        except Exception as error:
            logging.getLogger(__name__).warning("Shutter sound unavailable: %s", error)
            if self.is_active(session):
                self.shutter_sound = False
                self.sound_warning.config(text="Sound unavailable")
                self.sound_warning.pack(side="bottom")

    def check_layout(self, future, session: Session) -> None:
        if not self.is_active(session):
            return
        if not future.done():
            self.root.after(50, self.check_layout, future, session)
            return
        try:
            future.result()
        except Exception as error:
            show_error(
                self.root,
                "Print layout failed",
                f"Could not prepare the photo strips:\n{error}\n\n"
                f"Your original photos remain in:\n{session.directory}",
            )
        if not self.is_active(session):
            return
        self.status.config(text="Photos saved")
        self.countdown.pack_forget()
        availability = "soon" if self.compact else "coming soon"
        self.button(
            f"Print {session.strip_count} strips ({availability})", None, state="disabled",
        )
        self.button("Don't print", self.show_options)

    def close(self) -> None:
        self.closed = True
        self.active = False
        self.previewing = False
        cleanup = self.worker.submit(self.camera.close)
        self.worker.shutdown(wait=False)
        if self.sound_worker is not None:
            self.sound_worker.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()
        try:
            cleanup.result()
        except Exception as error:
            raise RuntimeError("Could not close the camera cleanly.") from error


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fullscreen", action="store_true")
    parser.add_argument(
        "--shutter-sound", action="store_true",
        help="Play a click after successful captures through the default ALSA audio device.",
    )
    parser.add_argument(
        "--test-sound", action="store_true",
        help="Play one shutter click and exit; no camera or display required.",
    )
    parser.add_argument(
        "--lcd", action="store_true",
        help="Fill the SPI-1 LCD with only the UI, using its current position and rotation.",
    )
    parser.add_argument(
        "--portrait", action="store_true",
        help="Use the compact 320x480 portrait layout.",
    )
    parser.add_argument(
        "--compact", action="store_true",
        help="Use the 480x320 layout (also selected automatically on small displays).",
    )
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "photos")
    parser.add_argument(
        "--strip-text", default="",
        help="Initial optional message for the bottom of each strip; editable on the LCD.",
    )
    args = parser.parse_args()
    if args.test_sound:
        try:
            play_shutter_sound()
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
            parser.error(f"Cannot play shutter sound: {error}")
        return
    if args.strip_text.strip():
        try:
            render_strip_footer(args.strip_text)
        except (OSError, RuntimeError, ValueError) as error:
            parser.error(f"Cannot use strip text: {error}")
    try:
        geometry = lcd_geometry() if args.lcd else None
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError) as error:
        parser.error(f"Cannot open the LCD: {error}")
    root = tk.Tk()
    app = PhotoBooth(
        root, args.output, args.fullscreen and not args.lcd,
        args.compact or args.lcd,
        args.portrait or (geometry is not None and geometry[0] < geometry[1]),
        args.shutter_sound,
        args.strip_text,
    )
    if geometry is not None:
        place_on_lcd(root, geometry)
        root.bind("<Escape>", lambda event: app.close())
    root.mainloop()


if __name__ == "__main__":
    main()
