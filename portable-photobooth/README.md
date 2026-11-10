# Portable photobooth

Basic Python touchscreen app for a Raspberry Pi 5, a Raspberry Pi Camera Module,
and an LCD running the Raspberry Pi OS desktop.

## Target flow (latest design)

The LCD interface and camera capture should be separate programs. The LCD program
stays open for the entire session; its Submit button starts the capture program,
not another copy of the interface.

1. The LCD asks for **3 or 4 photos** and a **5 or 10 second interval between
   photos**.
2. The user taps **Submit** once. Lock the choices and disable Submit so another
   session cannot start while one is running.
3. Show **Get ready!** with a **10-second positioning countdown**, regardless of
   the selected interval. Prepare the camera during this stage; if it is not
   ready, show a preparation message rather than silently taking a failed shot.
4. Take and save photo 1 when the positioning countdown and camera preparation
   are complete. Do **not** add the selected 5/10-second interval before photo 1.
5. Show the selected 5/10-second countdown, then take and save the next photo.
   Repeat until exactly 3 or 4 photos have been saved. No further button presses
   are needed.
6. Return the LCD to a **Your photos are ready!** screen with a **Review** button.
   Do not display the photos until Review is tapped.
7. Review shows the saved photos one at a time in capture order, with
   **Next/Previous** controls. A 3-photo session shows only 3 photos.
8. Show **Print (coming soon)**, disabled for now. Do not send anything to a
   printer. **New session** returns to the choices without deleting saved photos.

Example: with 3 photos and a 5-second interval, the sequence is:

```text
Submit -> 10-second positioning countdown -> capture/save photo 1
       -> 5-second countdown -> capture/save photo 2
       -> 5-second countdown -> capture/save photo 3
       -> Review button -> view photos -> Print (disabled)
```

Capture and save time is additional to the countdowns. A capture failure must
show an error, preserve completed photos, and allow a new session; it must not
claim that the session completed successfully.

## How Submit triggers capture

A touchscreen tap is a normal Tkinter button click. Its `command` callback
reads the selected options and starts the session. There is no need to run a
terminal command for every session or click a physical button for each photo.
Launch the LCD app once at the beginning of use; Submit starts each photo session.

The proposed split is:

| Program | Responsibility |
| --- | --- |
| `lcd_ui.py` (planned) | Own the Tkinter window, choices, Submit callback, countdown display, Review, photo display, and disabled Print option. |
| `capture.py` (planned) | Own Picamera2, camera preparation, the initial 10-second wait, the selected inter-photo waits, JPEG saving, and session results. No Tkinter window. |

Use Python's `subprocess.Popen` from the Submit callback to launch `capture.py`
with validated photo-count and interval arguments, plus a unique output folder.
Use `sys.executable` so both programs use the same Python installation, and pass
arguments as a list without `shell=True`.

The capture program should send newline-delimited JSON status messages over
standard output: preparation, countdown updates, saved-photo paths, and
completion with the ordered list of paths. Send diagnostics to standard error
and exit nonzero on failure. The UI should display Review only after a successful
exit with the expected number of saved photos.

Read process messages off the Tkinter thread and use a queue polled with
`root.after(...)` to update widgets. Do not use `time.sleep()`, blocking pipe
reads, or a blocking process wait inside the Submit callback: these would freeze
the screen. Drain standard error too, detect unexpected exits, and clean up the
capture process and camera when the LCD app closes. The capture program owns
timing; the LCD only displays its countdown messages so two timers cannot drift.

**This split and the fixed 10-second positioning stage are the next implementation
step, not features of the current code.** The planned filenames above do not
exist yet. The current program is described below.

## What works in the current code

- Choose 3 or 4 photos and a 5 or 10 second countdown.
- Press Start once. The app counts down before the first shot and before every
  subsequent shot, with no additional button presses.
- Press Review after capture, then use Next/Previous to view the photos in order,
  one at a time. A 3-photo session shows 3 photos, not 4.
- Print is visible but disabled. **Nothing is sent to a printer yet.**
- New session returns to the choices without deleting saved photos.

Currently, both the LCD interface and capture logic live in `photobooth.py`.
The Start button calls `PhotoBooth.start()`, which creates the session and begins
the countdown. It uses the chosen 5/10 seconds before the first shot too, rather
than the fixed 10-second positioning stage in the target design.

There is no physical GPIO button support, live camera preview, or retake button
in this first version. Use the LCD touchscreen or a mouse.

## Raspberry Pi setup

Use Raspberry Pi OS Bookworm or newer with a desktop session. Connect the camera
with the Pi powered off, then boot and verify it:

```sh
rpicam-still -o camera-test.jpg
sudo apt update
sudo apt install python3-picamera2 python3-pil python3-pil.imagetk python3-tk
```

Copy this folder onto the Pi, open a terminal on its desktop, and run:

```sh
cd portable-photobooth
python3 photobooth.py --fullscreen
```

Use the system Python, since Picamera2 is installed by apt. An SSH-only/headless
session cannot show the LCD interface without a configured graphical display.
Close other camera applications before starting.

Press Escape to leave fullscreen; close the window to quit.
Photos are saved under `photos/<timestamp>_<unique-id>/photo_01.jpg`, etc.,
beside the script. Each session has a separate folder. To choose another location:

```sh
python3 photobooth.py --output /home/pi/Pictures/photobooth
```

The timer starts again after each capture completes, so capture time is additional
to the selected delay. The first shot also includes about two seconds of camera
initialization/exposure settling. Capture runs off the UI thread to keep the
screen responsive. Failed captures display an error; completed photos remain on
disk. Photos are not automatically deleted, so monitor available storage.

## Printing later

Actual wireless printing requires the printer make/model and its supported
interface. Some portable printers use vendor-only apps rather than a standard
Linux print queue. Printing one composed strip and printing separate images are
also different operations: paper dimensions, margins, and cutting behavior must
be confirmed for that printer. This app currently saves individual JPEGs only;
it does not compose a strip or submit print jobs.

## Basic tests

```sh
python3 -m unittest -v
```

These tests check option validation, ordered saves, exact photo counts, and camera
failure handling without camera hardware. Touchscreen layout, actual countdown
timing, and Picamera2 capture still need testing on the Pi.

## Next milestones

Inspired by overtinker's portable photobooth, with different controls and flow.

1. Set up Raspberry Pi 5 access and test the camera and LCD independently.
2. Split the LCD and capture programs as described above, adding the fixed
   10-second positioning countdown and Submit-triggered sessions.
3. Test the complete 3/4-photo flow, countdowns, saved files, Review, and recovery
   from camera errors on the Pi.
4. Confirm the printer model and paper dimensions, then implement strip layout
   and wireless printing. Keep Print disabled until this works.
5. Build a ventilated case with a handle.

A physical GPIO start/confirm/reject button is a possible later addition, not
required for the touchscreen Submit flow. Retake and single/double-click
hardware controls are not implemented.