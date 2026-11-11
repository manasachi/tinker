# Portable photobooth

Basic Python touchscreen app for Raspberry Pi OS with Picamera2.

## Current hardware and small-screen mode

- **Pi:** Raspberry Pi 3B+ (not Pi 5).
- **Display:** Keyestudio KS0214 RPI TFT 3.5 Touch Shield, 480 x 320 pixels,
  resistive touch, connected through the GPIO header. An ILI9486-compatible
  DRM driver is verified on this unit; see the driver setup below.
- **Camera:** Raspberry Pi Camera Module 3 Wide. The Pi 3B+ uses the standard
  15-pin camera ribbon, not the Pi 5's 22-pin adapter.
- **Power:** use a suitable Pi 3B+ micro-USB supply; the official specification
  recommends 5.1 V / 2.5 A. The TFT takes power through its shield connection.

The app automatically chooses a compact layout on desktops smaller than
640 x 400. To test that layout as a 480 x 320 window on your HDMI monitor:

```sh
python3 photobooth.py --compact
```

Once the TFT shows a working desktop, launch from a terminal on that desktop:

```sh
python3 photobooth.py --compact --fullscreen
```

The compact layout uses pixel-sized fonts, smaller controls, and a
480 x 270 maximum camera preview, refreshed roughly three times per second
depending on processing speed. Original captures and print-layout resolution
are unchanged. If HDMI is the primary screen, automatic detection may see its
larger dimensions; use `--compact` explicitly. This flag changes layout only,
not which physical display the desktop uses.

### Show only the UI on the LCD

From a terminal in the Pi's graphical desktop session, run:

```sh
cd ~/portable-photobooth
python3 photobooth.py --lcd
```

`--lcd` reads the enabled `SPI-1` output's current position, dimensions, and
rotation, then fills only that LCD with a borderless UI. It does not move the
HDMI desktop, change display settings, or enable boot-time autostart. Escape
closes the LCD window. The desktop still runs underneath but is covered while
the program is open. If the LCD or Wayland output query is unavailable, the
program reports an error instead of silently opening on HDMI.
Errors also appear inside the LCD bounds with a touchscreen-sized **OK**
button, rather than opening a blocking dialog on HDMI.

The main booth needs a detected camera before it can capture. If camera
preparation fails, the countdown stops and an error is shown; acknowledging it
returns to the options. A paused countdown is not a successful photo session.
Use `display_test.py --lcd` for camera-free testing. Shut down and disconnect
power before connecting or reseating the camera's CSI ribbon.

Portrait outputs use a 320 x 480 compact layout with stacked option cards and
countdown text. For a portrait window without LCD targeting, use `--portrait`.
The guest flow has no saved-photo Review or Retake screen. It keeps the live
camera view through the final Print / Don't print choices. The separate
camera-free image tester still has navigation for checking supplied pictures.

The options include **2 or 4 photo strips**, defaulting to 2. Each printed
sheet contains two identical strips: 2 strips need 1 sheet, and 4 strips need
2 copies of the same sheet. Cut the sheets after printing. This quantity is
separate from the 3/4 photos on each strip and is retained in the session.
The summary shows both strip and sheet quantities; the disabled Print button
also shows the selected strip count. Actual printer integration is still pending.

Ordinary SSH sessions do not inherit the desktop environment. On the current
Pi, an SSH launch can use:

```sh
DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/$(id -u) WAYLAND_DISPLAY=wayland-0 python3 photobooth.py --lcd
```

### Test pictures without a camera

Install these on the Pi; Picamera2 is not needed for this test:

```sh
sudo apt update
sudo apt install python3-tk python3-pil python3-pil.imagetk
cd ~/portable-photobooth
python3 display_test.py
```

Press **Simulate 4 photos**. The test generates one numbered sample image per
second, keeps all four as Pillow images in RAM, and then offers **Review**.
Next/Previous show them one at a time; New test clears the images. Nothing is
saved or printed. To use your own four pictures instead:

```sh
python3 display_test.py --images photo1.jpg photo2.jpg photo3.jpg photo4.jpg
```

On a working TFT desktop, add `--fullscreen`. The test uses a 480 x 320 window
by default and does not modify display drivers or boot settings. Image data is
kept in memory, although supplied images are read from disk.

Use `python3 display_test.py --lcd` to put only the camera-free test UI on the
LCD, respecting portrait rotation. This opens the start screen; it does not
automatically simulate a session.

### White KS0214 screen: software prerequisites

A lit white panel is not yet a working graphical display. Tkinter and Pillow
cannot initialize the TFT controller: the OS needs a compatible display driver,
desktop output configuration, and touch driver/calibration.

The [manufacturer's guide](https://docs.keyestudio.com/projects/KS0214/en/latest/docs/KS0214.html)
identifies ILI9481 and gives legacy Pi 3/4 instructions using old images.
Do not flash its Jessie image for this project: it is obsolete and not the
modern Picamera2 environment used here.

Despite that guide's controller name, its official driver archive contains
a `waveshare35a` overlay declaring `ilitek,ili9486`, with reset on BCM GPIO25,
data/command on GPIO24, and ADS7846 touch interrupt on GPIO17. These match the
modern `piscreen` overlay's DRM option. The following setup was verified on
the current Pi 3B+ with Debian 13 Trixie and kernel `6.18.50+rpt-rpi-v8`:

```sh
/usr/sbin/modinfo -F filename ili9486
dtoverlay -h piscreen
sudo dtoverlay piscreen drm rotate=0 speed=15000000
```

Check that the driver exists and the overlay help lists `drm` before loading it.
This temporary test requires no reboot or boot-file edits. The overlay enables
SPI0 itself. Keep `vc4-kms-v3d` enabled: HDMI and the TFT can work together.
Do not load the overlay again if it is already active.

Verification:

```sh
dtoverlay -l
grep . /sys/class/graphics/fb*/name
wlr-randr
```

In the verified session, `fb1` was `ili9486drmfb` and the desktop exposed an
enabled `SPI-1` output at 480 x 320. The LCD showed the desktop, then all four
RAM-only test images rendered on that output with working-size review controls.
The ADS7846 touchscreen was subsequently calibrated using five physical stylus
taps, and button interaction was confirmed. Framebuffer numbers and output
positions can differ.

To keep the driver enabled after reboot, first back up
`/boot/firmware/config.txt` without overwriting an earlier backup:

```sh
sudo cp -n /boot/firmware/config.txt /boot/firmware/config.txt.before-ks0214
sudo nano /boot/firmware/config.txt
```

Add this line under the existing `[all]` section, once:

```ini
dtoverlay=piscreen,drm,rotate=0,speed=15000000
```

If the temporary overlay is already active, the boot-file change is for future
boots; there is no need to load it again. A reboot check is still required to
confirm startup behavior. To roll back, remove only that added overlay line
and reboot. A temporary-only load disappears on reboot.

With HDMI attached, the TFT may be an extended desktop rather than the primary
display. Move the test window onto the TFT before using fullscreen; fullscreen
alone does not select a physical display. Running the program on HDMI proves
the app works, not that the TFT is configured.

Keep HDMI and SSH available, and back up the SD card before driver/boot changes.
Shut down and disconnect power before adjusting the GPIO shield; match the
manufacturer's header alignment.

### Portrait rotation and touchscreen mapping

The current Pi uses the desktop's `kanshi` output manager for a 90-degree
rotation, leaving the kernel overlay at `rotate=0`. With HDMI connected, its
LCD profile is:

```text
profile photobooth-dual {
    output HDMI-A-1 enable position 0,0
    output SPI-1 enable position 1920,0 transform 90
}

profile photobooth-lcd {
    output SPI-1 enable position 0,0 transform 90
}
```

This is stored in `~/.config/kanshi/config`; the dual-display position matches
the current 1920-pixel-wide HDMI monitor. Back up existing settings before
changing them. Do not combine this desktop rotation with a second 90-degree
kernel rotation.

The KS0214 has a resistive screen: use a gentle, deliberate press with a plastic
stylus. A cursor moving on HDMI confirms input is present but mapped to the
wrong output. The current labwc session uses merged configuration (`labwc -m`);
the LCD-specific entry in `~/.config/labwc/rc.xml` is:

```xml
<labwc_config>
  <touch deviceName="ADS7846 Touchscreen" mapToOutput="SPI-1" mouseEmulation="yes" />
  <libinput>
    <device category="ADS7846 Touchscreen">
      <calibrationMatrix>1.13120444 -0.00563022 -0.06340731 -0.01122577 -1.11252436 1.07903350</calibrationMatrix>
    </device>
  </libinput>
</labwc_config>
```

Merge this entry with existing user settings rather than replacing them.
Mouse emulation delivers clicks to Tk buttons; output mapping keeps them on
the LCD. Rotation/alignment also needs the device's libinput
`calibrationMatrix`, under a device category named `ADS7846 Touchscreen`.
An initial rotation alone did not align this unit accurately enough to hit
buttons. The matrix above was calculated from five physical stylus taps on
this unit, with a maximum fitting error of about 2.1 pixels. It is specific
to this unit and the configured 90-degree desktop rotation; recalibrate if
the screen or rotation changes. The calculation accounts for the compositor's
output transform as well as libinput calibration; omitting the compositor
transform left presses inverted after the first calibration.
Verify button presses after applying it:
device detection or a rendered image alone is not a successful touch test.

Reload labwc using its supported `labwc --reconfigure` command from the
desktop session. Do not send SIGUSR1: that ended the session on this version.

## Target flow (latest design)

The LCD interface and camera capture should be separate programs. The LCD program
stays open for the entire session; its Submit button starts the capture program,
not another copy of the interface.

1. The LCD asks for **3 or 4 photos**, a **5 or 10 second interval between
   photos**, and **2 or 4 printed strips**.
2. The user taps **Submit** once. Lock the choices and disable Submit so another
   session cannot start while one is running.
3. Show **Get ready!** with a **15-second positioning countdown**, regardless of
   the selected interval. Prepare the camera during this stage; if it is not
   ready, show a preparation message rather than silently taking a failed shot.
4. Take and save photo 1 when the positioning countdown and camera preparation
   are complete. Do **not** add the selected 5/10-second interval before photo 1.
5. Show the selected 5/10-second countdown, then take and save the next photo.
   Repeat until exactly 3 or 4 photos have been saved. No further button presses
   are needed.
6. Compose a print image with two identical strips side by side. Keep the
   camera's live view on the LCD; do not switch to saved-photo review.
7. Offer **Print (coming soon)**, disabled until printing is configured, and
   **Don't print**. There is no Review, Previous/Next, or Retake option.
8. **Don't print** ends the session and returns to the choices without deleting
   saved photos. It does not replace or retake any photo in that session.

Example: with 3 photos and a 5-second interval, the sequence is:

```text
Submit -> 15-second positioning countdown -> capture/save photo 1
       -> 5-second countdown -> capture/save photo 2
       -> 5-second countdown -> capture/save photo 3
       -> live view + Print (disabled) / Don't print
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
| `lcd_ui.py` (planned) | Own the Tkinter window, choices, Submit callback, live-view display, countdowns, and Print / Don't print choices. |
| `capture.py` (planned) | Own Picamera2, camera preparation, preview, timed capture, JPEG saving, and session results. Keep preview available until the LCD ends the session. No Tkinter window. |

Use Python's `subprocess.Popen` from the Submit callback to launch `capture.py`
with validated photo-count and interval arguments, plus a unique output folder.
Use `sys.executable` so both programs use the same Python installation, and pass
arguments as a list without `shell=True`.

The capture program should send newline-delimited JSON status messages over
standard output: preparation, countdown updates, saved-photo paths, and
completion with the ordered list of paths. Send diagnostics to standard error
and exit nonzero on failure. The UI should display the print choices only after
a successful capture-complete message with the expected number of saved photos.
The camera process must remain available for live preview until the user ends
the session; capture completion is not the same as process shutdown.

Read process messages off the Tkinter thread and use a queue polled with
`root.after(...)` to update widgets. Do not use `time.sleep()`, blocking pipe
reads, or a blocking process wait inside the Submit callback: these would freeze
the screen. Drain standard error too, detect unexpected exits, and clean up the
capture process and camera when the LCD app closes. The capture program owns
timing; the LCD only displays its countdown messages so two timers cannot drift.

**The program split is planned, not implemented.** The fixed 15-second countdown,
camera preparation during that wait, and live view already work in the current
single program. The planned filenames above do not exist yet.

## What works in the current code

- A cream-and-green options screen with large photo/timer/strip-count choices, a live
  selection summary, and a Start photo session button. The palette uses
  `#386641`, `#6a994e`, `#a7c957`, `#f2e8cf`, and `#bc4749`.
- Choose 3 or 4 photos, a 5 or 10 second delay between photos, and 2 or 4 strips.
  The strip quantity is separate from the photo count; 4 strips require
  2 copies of the same two-strip print sheet, not extra camera captures.
- Press Start once. A fixed 15-second positioning countdown runs before photo 1.
  Only subsequent photos use the chosen 5/10-second delay, with no extra taps.
- The LCD shows a live camera view during positioning and between photos, with
  the countdown above it. Camera Module 3 continuous autofocus is enabled.
- After the final capture, automatically save `print_layout.png` containing two
  identical vertical strips side by side. Both 3-photo and 4-photo layouts use
  the same sheet size.
- Keep showing the live camera view after capture, alongside Print / Don't print.
  No saved-photo review or retake is offered to guests.
- Print is visible but disabled. **Nothing is sent to a printer yet.**
- Don't print returns to the choices without deleting saved photos.
- Optional shutter click after each successful capture; off by default.

Currently, both the LCD interface and capture logic live in `photobooth.py`.
The Start button calls `PhotoBooth.start()`, which creates the session and begins
the fixed 15-second positioning countdown. The selected interval applies only
between photos, not before photo 1.

There is no physical GPIO button support or retake button
in this first version. Use the LCD touchscreen or a mouse.

### What appears on the LCD?

**The LCD shows a live camera preview after Start**, during the 15-second
positioning countdown and between photos. The countdown stays above the image.
The camera starts on the background worker while the timer runs. If it is not
ready at zero, the screen says "Waiting for camera..." before taking photo 1.
The preview may pause briefly during a still capture or print-layout composition.
It continues after the final shot and alongside the print choices. It stops
when Don't print returns to the options, or when the app closes.

```text
CURRENT SCREEN FLOW
Options -> live view + 15-second countdown -> capture
        -> live view + 5/10-second countdown -> capture -> ...
        -> prepare print layout -> live view + Print / Don't print
```

The preview preserves the full captured aspect ratio without mirroring or
stretching. It is downsampled to at most 640 x 360 in standard mode or 480 x 270
in compact mode, refreshed approximately five or three times per second
respectively, depending on camera/processing speed. It is a framing aid,
not a guarantee of final exposure or focus. The print layout center-crops photos
further; print-crop guides are not implemented. Preview errors are displayed
explicitly and return to the options, preserving any completed photos.

### Optional shutter sound

The KS0214 has no speaker. The Pi 3B+ can output sound through its 3.5 mm jack,
a supported USB audio device, or HDMI. A small powered 3.5 mm speaker is enough
for a shutter click; no extra sound board or GPIO wiring is required. Select
the connected device in the Pi's audio settings. An available output does not
prove that a speaker is physically connected or audible.

The click uses `aplay` from `alsa-utils` (already installed on the current Pi).
If it is missing, install that package. Test one click without a camera or GUI:

```sh
python3 photobooth.py --test-sound
```

Enable clicks in the booth with:

```sh
python3 photobooth.py --lcd --shutter-sound
```

Audio is off by default. A short click is played after each successful photo
save, not at countdown zero or on failed captures. Playback runs on a separate
worker with a timeout, so it cannot block camera preview or the Tk event loop.
On playback failure, the UI shows **Sound unavailable**, the terminal logs the
reason, and capture continues without more audio attempts in that session.
The next session retries. Audible playback still needs a physical speaker test.

## DIY box layout

**Illustration below is the earlier Pi 5 + HDMI/USB display example, not the
current Pi 3B+ + KS0214 wiring.** For the current setup, the TFT plugs into the
GPIO header, the camera uses the Pi 3B+'s separate 15-pin CSI connector, and power
enters through micro-USB. HDMI is for the external setup monitor. Do not buy the
Pi 5 cables or cooler from this example for the Pi 3B+.

Start with a sturdy reused shipping box, reinforced with a second layer of
cardboard around the screen and mounting points. These are **concept sketches,
not measured cutting templates**. Measure the actual LCD, Pi/cooler, connectors,
and cables before choosing the box or cutting holes. Keep the printer external
for this first build.

![Photobooth front and labeled internal connection map: camera ribbon, HDMI video, USB touch, Pi USB-C power, fan lead, and optional LCD power.](./images/box-layout.png)

[Open the full-size illustration](./images/box-layout.svg).

### How to read the picture

- **Left: front view.** The camera and LCD both face the people. The lens sits
  just above the screen, near the front surface. Keep it near eye level when the
  box is on its table/stand. A deep or narrow opening can block a wide-angle
  view; check captured photos for dark corners.
- **Right: open back.** The camera board connects to the Pi with a gently curved
  ribbon. The screen sits behind the front panel. Put the Pi/cooler on a separate
  reinforced mount with air space and side vents; use the box depth so the screen
  and connectors do not collide. The drawing is not to scale.
- **Right-hand cable map:** each colored cable ends at a labeled connector.
  Letters A-E match the checklist below the drawing. Port locations are
  simplified to make the paths readable; this is not a physical Pi board map
  or ribbon-contact orientation guide.
- **Screen connections depend on the LCD.** The example specifically assumes
  an HDMI + USB touchscreen. A DSI screen uses a different connection plan;
  do not buy the illustrated display cables until the LCD model is confirmed.
- **Mounting:** support the LCD by its bezel or mounting points, not pressure on
  the glass. Use suitable Pi standoffs and camera board mounting points, keeping
  exposed contacts clear of metal. Do not press on the autofocus mechanism.
- **Access and power:** keep the back reopenable, allow access to the SD card
  and needed ports, and begin with external Pi power. Shut down and unplug before
  adjusting boards or cables. Do not sharply fold or pull the camera ribbon.

### Cables shown in the illustration

| Label | Connection | Cable / requirement |
| --- | --- | --- |
| A | Camera Module 3 Wide to Pi 5 CAM/DISP 0 or 1 | Pi 5-compatible **22-pin-to-15-pin camera ribbon**: 15-pin end at the camera, 22-pin end at the Pi. |
| B | Pi micro-HDMI 0 to LCD HDMI input | **micro-HDMI at the Pi**, with an HDMI connector matching the LCD at the other end. This carries the picture, not USB touch input or screen power. |
| C | Pi USB-A to LCD USB touch/data input | A **data-capable USB cable** with the correct screen-side connector. Depending on the LCD, this may also supply its power. |
| D | External supply to Pi USB-C power port | A properly rated Pi 5 supply; the official **27 W USB-C supply** is a straightforward starting point. |
| E | Active Cooler to Pi FAN header | The cooler's own fan lead; do not substitute a USB cable or improvise GPIO wiring. |
| Dashed | Optional external LCD supply to its power input | Only if required by that screen. Use its specified voltage, polarity, connector, and power rating; do not assume any USB port can power it. |

Use the camera and display manufacturers' installation guides for ribbon
orientation and port identification. A camera ribbon and a display ribbon are
not interchangeable just because their connectors look similar. The picture
does not specify mains wiring, a battery system, or a printer power connection.

### Build in this order

1. Lay the components on a table and connect/test them before enclosing anything.
2. Mark the front camera and screen positions on scrap cardboard. Check cable
   reach, finger access, and camera framing before cutting the final panel.
3. Reinforce the box, add mounts, and make the display, lens, cable, and vent
   openings. Cut/drill with all electronics removed; clear debris before assembly.
4. Install and secure the components, leaving the back open for the first tests.
   Start with the normal external Pi power supply rather than improvised wiring.
5. Test touch controls, captured-image framing, stability, and cooling with the
   box closed before carrying it around. Do not treat cardboard as weatherproof
   or leave a powered prototype unattended.

Do not add a carrying handle to thin cardboard without reinforcing its attachment
points. Carry the first prototype from underneath. A future integrated printer
would need a larger enclosure, separate power planning, service access, and the
manufacturer's required front/rear paper-path clearance.

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
to the selected delay. Camera initialization and about two seconds of exposure
settling happen during positioning. Slow initialization may extend the wait
beyond 15 seconds. Preview, capture, and cleanup share one worker thread so they
cannot access Picamera2 concurrently; Tk image updates happen on the UI thread.
Failed previews/captures display an error; completed photos remain on disk.
Photos are not automatically deleted, so monitor available storage.

## Print layout and future printing

Each completed session saves its original JPEGs plus `print_layout.png`: a
**1,200 x 1,800 pixel RGB image at 300 DPI**, intended for a 4 x 6-inch sheet in
portrait orientation. Each half is a 600 x 1,800 pixel strip (nominally 2 x 6
inches). Cut the printed sheet vertically down the center to separate the copies;
this is not continuous-roll printing or automatic cutting.

The photos appear top to bottom in capture order, with white borders and gaps.
Three-photo layouts use taller slots; four-photo layouts use shorter slots.
Photos are EXIF-oriented and center-cropped to fill their slots without stretching.
Keep faces near the center, as edges may be cropped. Original JPEGs are unchanged;
the live view shows camera framing rather than the print crop.

Composition runs on the camera worker after all captures, before print choices appear.
A layout failure displays an error but preserves the original files;
it does not indicate that a print layout was successfully generated.

Actual wireless printing requires the printer make/model and its supported
interface. Some portable printers use vendor-only apps rather than a standard
Linux print queue. Submit the composed sheet as **one print job**, not each photo
as a separate job. Paper dimensions, scaling, borderless overscan, margins, and
cutting behavior must be confirmed for the printer. DPI metadata alone does not
force physical print dimensions. Print remains disabled: no jobs are submitted.

## Basic tests

For step-by-step hardware and software checks, follow the
[phased testing guide](./TESTING.md). It separates current functionality from
future split-program and printer tests.

```sh
python3 -m unittest -v
```

These tests check option validation, ordered saves, exact photo counts, camera
failure handling, layout dimensions/DPI, duplicate strips, photo order,
orientation, preserved originals, and layout error handling without camera
hardware. Pillow and Tkinter must be installed. Touchscreen layout, actual
countdown timing, and Picamera2 capture still need testing on the Pi.

## Next milestones

Inspired by overtinker's portable photobooth, with different controls and flow.

1. Set up Raspberry Pi 5 access and test the camera and LCD independently.
2. Split the LCD and capture programs as described above, preserving the fixed
   15-second positioning countdown, live view, and background camera preparation.
3. Test the complete 3/4-photo flow, countdowns, saved files, print choices, and recovery
   from camera errors on the Pi.
4. Confirm the printer model and paper dimensions, test the composed strip
   layout on paper, and implement wireless printing. Keep Print disabled until
   this works.
5. Build a ventilated case with a handle.

A physical GPIO start/confirm/reject button is a possible later addition, not
required for the touchscreen Submit flow. Retake and single/double-click
hardware controls are not implemented.