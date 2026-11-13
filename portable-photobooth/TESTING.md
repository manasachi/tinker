# Phased photobooth testing

Work through these phases in order. Record pass/fail, the selected settings, and
any error messages. Do not mark a hardware phase passed based only on unit tests.
See [README](./README.md) for setup and the latest target design.

**Current implementation:** one `photobooth.py` program, Start button, a fixed
15-second positioning countdown before photo 1, and the selected 5/10-second
delay only between subsequent photos.
Live preview and background camera preparation run during positioning and between
shots. **Planned:** separate LCD/capture programs and a Submit button. Phase 7
covers that future split.

## Phase 1: Pi, LCD, and camera setup

Use Raspberry Pi OS Bookworm or newer with a desktop session.

1. Current hardware is Pi 3B+ + Keyestudio KS0214 (480 x 320 GPIO shield).
   Power off and unplug before adjusting the shield or camera ribbon.
   Pi 3B+ uses the standard 15-pin camera cable. Only Pi 5 needs the 22-pin adapter.
2. Boot the Pi and check that the LCD shows the desktop. A white backlight is
   not a pass. Before installing a driver, identify the OS/kernel with
   `cat /etc/os-release` and `uname -r`; follow the README's KS0214 guidance.
3. Check that touchscreen taps select desktop controls. A mouse can be used
   temporarily to distinguish touchscreen problems from app problems.
4. Open a terminal on the Pi desktop and install dependencies:

   ```sh
   sudo apt update
   sudo apt install python3-picamera2 python3-pil python3-pil.imagetk python3-tk python3-cups
   ```

5. Test the camera separately:

   ```sh
   rpicam-still -o "$HOME/camera-test.jpg"
   ```

6. Open the saved image. Check orientation, recognizable detail, and exposure.
   Close the camera test before starting the booth.

**Pass:** LCD, touch input, and a saved camera image work independently.
If the camera is not detected, shut down before checking cables; do not hot-plug
the camera.

### Phase 1A: four pictures in memory, no camera required

On the Pi desktop:

```sh
sudo apt update
sudo apt install python3-tk python3-pil python3-pil.imagetk
cd ~/portable-photobooth
python3 display_test.py
```

- [ ] A 480 x 320 test window fits and all text/buttons are visible.
- [ ] Tap Simulate 4 photos; the counter advances to four without more taps.
- [ ] Review appears only after all four images have been generated in RAM.
- [ ] Review shows PHOTO 1 through PHOTO 4 in order using Next/Previous.
- [ ] Previous/Next are disabled at the appropriate ends.
- [ ] New test clears the images and returns to the start screen.
- [ ] No photos or print jobs are created.

On a configured TFT desktop, repeat with `python3 display_test.py --fullscreen`
and use touch instead of the mouse. Test optional input files with
`--images photo1.jpg photo2.jpg photo3.jpg photo4.jpg`.
With both HDMI and the LCD connected, use `python3 display_test.py --lcd` to
target the LCD explicitly. Confirm that only the borderless test UI covers it,
and that portrait rotation is detected. Review should have no top counter.

**Pass:** actual image display and touch work on the TFT. Passing on HDMI only
checks the program, not the TFT driver. A camera is not required for this phase.

On the current Pi 3B+/Trixie setup, the DRM driver, 480 x 320 `SPI-1` output,
and four-image RAM capture/review have been verified over SSH, including a
screenshot of the TFT output. Physical stylus calibration and button interaction
have subsequently been confirmed. Post-reboot startup still needs a separate
check; it is not covered by that rendering test.

## Phase 2: Automated logic checks

From the copied project folder:

```sh
cd ~/portable-photobooth
python3 -m unittest -v
```

For real Tk layout checks in a desktop session, also run:

```sh
PHOTOBOOTH_GUI_TESTS=1 python3 -m unittest -v
```

These optional tests check options, countdown/preview controls, and print choices at
480 x 320, 320 x 480 portrait, and 800 x 480; ordinary headless runs skip them.
LCD-targeting tests check rotation, exact output bounds, and explicit errors
for an absent, disabled, or unconfigured LCD.
Error tests check that LCD-mode dialogs stay in the LCD's bounds, and that
an undetected camera produces an actionable error rather than a failed capture.

Headless tests do not require a camera or a running graphical display, but Python
must have Tkinter installed because the application imports it.

**Pass:** all tests pass. They cover:

- All four valid photo-count/interval combinations.
- Strip quantities of 1 through 8, a default of 2, rejection of unsupported
  quantities, and ceiling-rounded sheet counts without extra captures.
- Read-only copies dropdown at all three display sizes, exact PDF page counts
  for odd quantities, decoded final-page images with blank right halves,
  unchanged original PNGs, and one CUPS submission with correct copy settings.
- Exactly 3 or 4 saved paths, ordered filenames, and rejection of an extra shot.
- Rejection of unsupported options.
- A simulated failed capture not being added to the saved-photo list, followed by a
  successful retry.
- Print-sheet dimensions/DPI, matching left/right strips, photo order, black
  gaps, EXIF orientation, and unchanged original files for 3/4-photo layouts.
- Optional message layout: 1,457 pixels for photos and 291 for text;
  blank/whitespace text restores the full 1,748-pixel photo region. Both strip
  copies match; text wrapping/fit, long-message rejection, and host launch
  configuration are checked.
- Incomplete/unreadable inputs and visible layout failure handling.
- A simulated clock verifies the first capture waits 15 seconds for all four
  settings combinations, followed by the selected inter-photo countdowns.
- Preview rendering/polling, camera startup failure, stale callbacks, camera
  readiness, and shared preview/still camera setup with continuous autofocus.
- Live preview retained after the last capture; no Review or Retake controls.
- A valid short PCM shutter click, playback errors, and sound triggered only
  after successful captures without aborting photography on audio failure.

The session unit-test camera writes placeholder bytes, not real JPEGs. The
optional GUI integration test uses generated frames and JPEGs with accelerated
countdowns to verify live-view updates after 3/4 captures and returning to
options without deleting saved files.
Tests do not verify image quality, real-world countdown timing, physical
touchscreen operation, autofocus, or printing. Layout tests use images generated by Pillow,
which must be installed.

## Phase 3: LCD controls and one complete session

Run from the Pi's desktop terminal, not an ordinary SSH-only terminal:

```sh
cd ~/portable-photobooth
python3 photobooth.py --compact --fullscreen --output "$HOME/Pictures/photobooth-test"
```

- [ ] Options fit the LCD and can be selected by touch.
- [ ] While still on HDMI, verify the small-window layout first using
      `python3 photobooth.py --compact` without fullscreen.
- [ ] Options show "Make a little memory" as a large green heading; selected
      choices are highlighted in lime and have a pressed appearance.
- [ ] Changing any choice updates the photo-count/countdown/strip summary.
- [ ] The copies dropdown offers 1 through 8 individual strips and defaults
      to 2. The summary shows 1 sheet for 1 or 2 strips, 2 for 3 or 4 strips,
      3 for 5 or 6 strips, and 4 for 7 or 8 strips.
- [ ] Tap Strip text and enter a message using the touchscreen keyboard.
      Check case, number/symbol switching, Space, and Back.
- [ ] Save returns to options without resetting photo, timer, or strip choices.
- [ ] Cancel discards edits; Clear followed by Save disables the footer.
- [ ] Overlong text shows an error without silently truncating or saving it.
- [ ] Select 3 photos and 5 seconds; tap Start once.
- [ ] Choices disappear and the countdown remains responsive and readable.
- [ ] A 15-second positioning countdown appears for either interval selection.
- [ ] After camera startup, live images appear below the timer. Move your hand
      and verify the image updates during positioning and between shots.
- [ ] Preview has correct colors/orientation and is not stretched or mirrored.
- [ ] A brief preview pause at the shutter is acceptable; no frozen UI or second
      camera window appears.
- [ ] Three shots are taken automatically, with no extra taps.
- [ ] Live preview continues after the last shot; move your hand to verify
      that the print-choice screen is live, not a saved image.
- [ ] A preparing-strips message appears while the print layout is composed.
- [ ] After layout preparation, only Print / Don't print choices appear.
- [ ] There is no Review, Previous/Next, or Retake control in the guest flow.
- [ ] Print is visible and enabled after a successful layout. Do not tap it
      during a capture-only test: it submits a real job when the printer is ready.
- [ ] The Print button includes the strip quantity chosen before Start.
- [ ] Don't print returns to the choices without deleting the saved session.
- [ ] Escape exits fullscreen; closing the window exits the app.

**Pass:** the entire session works using the LCD without terminal interaction.
If controls are clipped on the actual LCD resolution, record that as a failure.

Check `print_layout.png` for both 3- and 4-photo sessions, with and without a
message. Text must occupy only the bottom 291 pixels of each 1,748-pixel strip.
Borders, inter-photo gaps, and footer backgrounds must be black; footer text
must be white. Original camera images and the LCD theme must remain unchanged.
When blank, the last photo must extend into that former footer area. The message
should be reused on the next session until edited/cleared, while existing saved
layouts remain unchanged. Actual printed inch measurements depend on paper and
driver scaling; Canon's 148 mm height is shorter than a true 6-inch sheet.

For the first printer test, run `python3 print_test.py` to generate circle
samples instead of reading personal images. Inspect its generated PNG, then
print just one sheet using the printer's advertised postcard media settings.
The next test has **no footer text** by default, using full-height photos.
An explicit `--strip-text` option still enables a footer.
Check that the entire PHOTO
label is visible in all four sample slots; samples must fit without cropping.
Verify that each strip's outer 18 pixels are black on every side, with 12-pixel
inter-photo gaps and a 36-pixel center gutter. Circle samples should have no
extra black letterboxing inside their slots. Four-photo slots should be
555 x 346 with text, or 555 x 419 without text, retaining the first print's
overall 50 x 148 mm strip size with an approximately 1.5 mm black frame.
The 1,182 x 1,748 sheet should match 100 x 148 mm within
0.1 mm at 300 DPI. Physical borderless trimming still needs a later print;
do not submit another job until requested.
The command itself must not send a print job. See the README's CP1500 setup
section; a generated layout does not verify connectivity or actual output.

### Optional shutter audio

1. Connect a powered speaker to the Pi's 3.5 mm jack, use a supported USB audio
   device, or use HDMI speakers. Select that output in the desktop audio settings.
2. Run `python3 photobooth.py --test-sound`. Confirm one short click is audible.
   The command requires neither a camera nor a graphical session.
3. Run `python3 photobooth.py --lcd --shutter-sound` with a working camera.
   Confirm one click follows each successful capture, with no click during
   countdowns or failed captures.
4. Confirm preview and countdowns remain responsive during playback.
5. If playback fails, expect a terminal warning and **Sound unavailable** on
   the LCD. Photos should continue, without repeated audio attempts until the
   next session. Starting without `--shutter-sound` must require no audio device.

**Pass:** actual audible clicks follow successful captures. A valid WAV file,
successful software playback, or a mocked test does not prove audibility.

## Phase 4: Settings, timing, and saved files

Repeat a complete session for every row:

| Photos | Delay | Expected JPEGs | Result |
| --- | --- | --- | --- |
| 3 | 5 seconds | 3 | Not tested |
| 3 | 10 seconds | 3 | Not tested |
| 4 | 5 seconds | 4 | Not tested |
| 4 | 10 seconds | 4 | Not tested |

For each session:

1. Use a stopwatch or phone video to check the displayed countdown. Each step
   should last approximately one second; investigate consistently skipped,
   stalled, or noticeably inaccurate steps.
2. Verify a fixed 15-second positioning countdown runs before photo 1, with no
   additional selected 5/10-second delay. Subsequent photos use the selected delay.
   Camera setup and exposure settling run during the initial countdown. If not
   ready at zero, expect "Waiting for camera..." and no premature capture.
   Later countdowns start after the previous save
   completes, not at the previous shutter instant.
3. Check the new session folder under `~/Pictures/photobooth-test`.
   Expect `photo_01.jpg` through `photo_03.jpg` or `photo_04.jpg`, plus one
   `print_layout.png`. The layout is not an extra captured photo.
4. Open every JPEG outside the app and confirm it is readable. Pose differently
   for each shot to verify that saved-file order matches capture order.
5. Start another session and verify its folder is distinct and earlier photos
   have not been overwritten.
6. Open `print_layout.png`. Check that it is 1,182 x 1,748 pixels with two
   identical strips side by side, each containing exactly the selected number
   of photos in order. Check black borders/gaps and the center crop of each
   photo. Original JPEGs should retain their full captured framing.

**Pass:** every combination produces the correct count, ordered readable files,
matching duplicate strips, and countdown behavior matching the current
implementation.

## Phase 5: Image quality and framing

Test in the lighting and at the distances expected at an event:

- [ ] One person, a couple, and a group fit the intended frame.
- [ ] Faces are sharp when viewed at the intended small-print size.
- [ ] Faces have natural colors and are not too dark or washed out.
- [ ] Camera orientation is correct.
- [ ] Faces near the edges of the wide lens are not unacceptably stretched.
- [ ] People moving into position between shots remain acceptably sharp.

Use soft visible lighting in front of people. The regular Camera Module 3 Wide
is the intended color-photo camera, not NoIR.

**Pass:** saved images meet your visual quality expectations. Continuous autofocus
is enabled on cameras exposing `AfMode`, including Camera Module 3. Check that
focus adjusts when people change distance; hardware focus quality is not proven
by the mocked tests. There is no zoom choice, person detection, or print-crop
guide. The unmirrored live view shows full capture framing, not the tighter print
crop.

## Phase 6: Errors, shutdown, and repeated use

Use test photos and a separate test output folder.

1. **Camera unavailable:** close the app, shut down the Pi, disconnect the camera,
   and boot again. Start a session. Expect a visible camera preview error, no success or
   print-choice screen for that failed session, and a return to the choices.
   Shut down before reconnecting the camera.
2. **Save failure:** on Raspberry Pi OS, launch as your normal user with an
   unwritable destination:

   ```sh
   python3 photobooth.py --output /proc/photobooth-test
   ```

   Start a session. Expect a visible error and a return to the choices, not a
   success screen. Do not run this test with `sudo`.
3. **Repeated taps:** tap Start rapidly. Confirm that only one session runs and
   only the selected number of photos is saved.
4. **Shutdown:** leave fullscreen and close the window during a countdown, then
   repeat during a capture. A capture already in progress may finish before the
   process exits. Relaunch the app and confirm the camera is available again.
5. **Repeated use:** complete at least five sessions, mixing the settings.
   Check for frozen screens, mixed-up photos, overwritten files, or camera-busy
   errors. Check free disk space:

   ```sh
   df -h "$HOME"
   ```

**Pass:** failures are visible, ordinary sessions can be run again after fixing
the cause, shutdown releases the camera, and prior photos remain intact.
The unit tests cover partial-session bookkeeping; hardware recovery after a
mid-session failure still needs separate verification. Never unplug a running
camera to simulate it.

## Phase 7: Separate programs (future)

**Blocked until implemented.** The planned `lcd_ui.py` and `capture.py` do not
exist yet. Do not use the current Start behavior as evidence that this phase
passes.

After implementation, repeat Phases 3, 4, and 6 with these additional checks:

- [ ] Launch the LCD once. Submit starts a capture session, not a second window.
- [ ] Both 5-second and 10-second selections preserve the same 15-second
      positioning countdown.
- [ ] Photo 1 follows that countdown once the camera is ready, with no extra
      selected 5/10-second delay. A preparation message appears if needed.
- [ ] Only subsequent photos use the selected interval.
- [ ] Submit and choices cannot start overlapping sessions.
- [ ] Countdown/status messages update the LCD without freezing it.
- [ ] Print choices appear only after a successful capture-complete message
      contains exactly the requested number of saved-photo paths. The camera
      process stays available for live preview until the session ends.
- [ ] A capture-process failure or unexpected exit shows an error, not success.
- [ ] Closing the LCD also cleans up the capture process and releases the camera.
- [ ] A new session works without restarting the LCD program.

**Pass:** the target flow in the README is implemented and verified on the Pi.

## Phase 8: Wireless printing and automatic startup

Guest printing and portrait LCD autostart are implemented. Unit tests and
CUPS-reported completion do not substitute for these physical checks:

1. Confirm printer model, Linux support, paper size, margins, and strip/cutting
   behavior.
2. Print a test strip with numbered images. Check order, orientation, cropping,
   dimensions, and readable faces for both 3-photo and 4-photo layouts.
3. Confirm one tap submits one job; repeated taps do not duplicate prints.
   For an authorized odd-quantity test, confirm that only the left strip is
   printed on the last sheet and that the right half is blank. The printer
   still consumes a full sheet and ribbon pass. This new behavior has local
   software coverage and is deployed, but has not yet been physically tested.
4. Test printer offline, paper out, and lost wireless connection. Failures must
   be visible and saved photos must remain available.
5. Verify the app distinguishes a job being accepted from a physical print
   completing, according to what the printer actually reports.
6. Install startup using `python3 booth_startup.py --install`, then
   `python3 booth_startup.py --start-service` on the Pi desktop. Check
   `systemctl --user status photobooth.service`. The system journal should
   contain `Photobooth UI ready` with portrait 320 x 480 geometry.
7. Shut down the Pi cleanly, disconnect power, power off the printer, then
   start the printer in Direct Connection mode before powering the Pi.
   Without a laptop or HDMI monitor, confirm the booth appears on the LCD
   and a guest session prints. The currently missing camera must be connected
   with the Pi powered off before verifying actual captures.
8. A failed or uncertain submission must show an error and keep Print disabled.
   Inspect the saved `print-job.json` and CUPS before any manual reprint.
   A pending job must block another submission; it may still print later.

**Pass:** correct physical output and explicit error handling, not merely a
successful software submission.

### Router-free connection acceptance test

Use the README's `portable_setup.py` steps for one-time SELPHY Direct Connection
configuration. Do not switch networks through the only SSH management link.

- [ ] With the printer still on home Wi-Fi, `portable_setup.py check` fails
      explicitly instead of claiming offline readiness. It must not print.
- [ ] Enable the printer's Direct Connection network and connect the Pi.
- [ ] The check confirms the `photobooth-selphy-direct` profile, obtains the
      printer address from the direct-network DHCP server identifier, and
      verifies a direct route through `wlan0` without a gateway. It must not
      depend on `.local` name resolution, which failed in the real direct test.
- [ ] Check the printer screen to confirm Direct Connection, not router mode.
- [ ] Switch off the home router. Repeat `check`; it must still succeed.
- [ ] Only after authorizing a sheet, use `check --print-test`. Expect one
      monochrome four-circle sheet, two strips, no footer, and no duplicate job.
- [ ] Turn both devices off, then start the printer and Pi again. Confirm
      saved-network reconnection and repeat `check` without changing credentials.
- [ ] Turn the printer off. Expect an explicit connection/IPP failure, not a
      successful offline claim or a silently queued test.
- [ ] Existing saved Wi-Fi profiles remain available for recovery.

Unit tests cover connection settings, no password in command arguments, wrong
profile/router-hop rejection, printer identity/readiness errors, explicit
submission only, DHCP address changes, independence from mDNS, and pending-job
protection. Mocked success is not a physical
router-free print or cold-boot acceptance result.

Recorded live direct test: `SELPHY_CP1500_Direct-4` used the guest submission
backend with a generated monochrome, no-footer sheet. CUPS reported
`job-completed-successfully`, one completed sheet, and one completed impression.
The Pi had only the printer's local Wi-Fi route, no external-router route.
The test restored home Wi-Fi for management. Physical sheet inspection and
power-off/startup confirmation must be recorded separately.
The user subsequently confirmed the sheet printed and the options appeared
automatically after the clean shutdown and physical power cycle. A reported
large-memory warning before UI startup remains unresolved. Camera capture,
HDMI-disconnected operation, and post-cold-start printer communication were
not independently verified during that observation.

After restoring management access, the copies dropdown, odd-copy documents,
and lighter startup launcher were deployed. All 92 tests passed natively on
the Pi. The service-only launcher avoids GUI/camera imports; measured peak
import memory decreased from 20,240 KiB to 12,468 KiB. System memory inspection
showed over 500 MiB available with no swap use and about 30 MiB booth RSS.
This does not identify or resolve the earlier desktop memory warning.
With the physical LCD removed, its logical output was disabled for the current
session and the booth was launched on HDMI. Camera auto-detection is already
enabled, but no sensor is currently detected; model/cable verification is needed
before a genuine capture test.

The camera was subsequently identified as an official Camera Module 3 Wide.
The official IMX708 driver and overlay are installed. An authorized temporary
`imx708` overlay probe failed to read sensor chip ID 708 with error -5, with
matching autofocus-controller I2C failures. The probe overlay was removed and
`camera_auto_detect=1` was left unchanged. This is a failed detection result,
not a completed camera setup. A powered-off cable/connector check is required
before retesting; no real capture succeeded during that first probe.

After the user flipped the ribbon, the sensor identified as `imx708_wide`,
4608 x 2592. A controlled reboot verified normal automatic detection with
no runtime probe overlay loaded and no permanent boot edits. However, the
production helper still timed out waiting for image frames. A separate
`rpicam-still` test at 1536 x 864 and 5 fps failed the same way. Both tests
were bounded; stalled test processes were cleaned up. `vcgencmd get_throttled`
returned `0x0`. The one-time home-network recovery unit and temporary SSH
credentials were removed after reboot verification. Camera capture remains
blocked on a powered-off cable/connector check or a compatible replacement
15-pin-to-15-pin ribbon; no successful photo has been verified.

Following a further powered-off reseat of the original 15-to-15 ribbon, boot
auto-detection still succeeded but the production capture again timed out.
The sensor-to-Unicam media links are enabled. A direct kernel V4L2 raw-frame
test allocated buffers and started streaming, but ended with `select timeout`
without returning a frame. Its process exit status was 0 despite the timeout;
this is not a successful capture. The one-time home-network recovery unit
removed itself on boot, and no capture test processes were left running.

Background-process isolation was also tested. PipeWire and WirePlumber had
camera handles open, so their services and sockets and the booth service
were temporarily stopped. `fuser` then reported no camera owners, but the
modern `rpicam-hello --nopreview --timeout 5000` test still failed with frontend
timeouts under a 12-second watchdog. All previously running services were
restored afterward. This does not support those services being the sole cause.

The OS is Debian 13 Trixie with Raspberry Pi kernel 6.18.50 and the modern
camera stack, not a legacy-camera OS. After explicit user approval, APT
metadata was refreshed and the coordinated dependency plan rechecked.
The update upgraded 22 packages, replaced libcamera0.7 with libcamera0.8,
and preserved the PipeWire camera integration. Installed versions are
rpicam-apps 1.15.0, libcamera 0.8.0+rpt20261104, and PipeWire 1.4.2-1+rpt5;
Picamera2 remains 0.3.39. The package audit was clean. No kernel, firmware,
or full OS upgrade was performed.

Post-update verification still failed to receive a frame. The production
Picamera2 helper timed out under a 25-second watchdog. A separate modern
`rpicam-hello --nopreview --timeout 5000` test also produced frontend timeouts
under a 12-second watchdog after the booth, PipeWire, and WirePlumber services
and sockets were stopped and `fuser` reported no camera owners. Both watchdogs
returned 124. All six previously active user services/sockets were restored.
The updated stack still reports missing static properties for `imx708_wide`;
that warning alone does not establish the cause. No preview frame or saved
photo has been verified, and no print job was submitted.

The first post-update 92-test run reported two landscape-layout assertion
failures: the current desktop exposes only the logical 320 x 480 portrait LCD,
so automatic portrait selection overrode the tests' landscape assumptions.
The multi-size GUI checks now simulate each intended screen size during app
construction and assert the resulting layout mode, following the existing
automatic-display test pattern. Production display detection is unchanged.
After that fixture correction, all 92 tests passed natively on the Pi with
the current portrait desktop and updated camera/media packages.
These GUI tests use synthetic captures and cannot establish camera readiness.

Further isolated tests compared normal capture with the IMX708 sensor's
built-in color-bar control. Both `rpicam-still` attempts timed out under
12-second watchdogs without saving a JPEG. The requested test-pattern control
was readable as 0 and 1 respectively during the attempts. This confirms the
driver accepted the setting, not that the sensor emitted a pattern.

A separate direct V4L2 color-bar stream bypassed Picamera2 and libcamera.
The first attempt was rejected before streaming because the sensor and
receiver Bayer formats differed after libcamera closed; that rejection is
not evidence of a hardware fault. After explicitly matching sensor
SRGGB10_1X10 and receiver `pRAA` at 2304 x 1296, buffer allocation, queueing,
and STREAMON all succeeded. The stream then reported `select timeout`,
transferring 0 of the expected 3,732,480 bytes. Its exit status was 0 despite
the failed transfer; no raw frame was verified.

During that valid direct stream, three live receiver snapshots showed
stride 2880, detected resolution 0 x 0, and an unchanged write pointer.
The Unicam interrupt count remained zero before, during, and after streaming.
The actual sensor and receiver device-tree endpoints both use data lanes
[1, 2], clock lane [0], and noncontinuous clock mode. Power status was
`throttled=0x0`. These observations narrow the fault below the userspace
camera applications, but cannot distinguish the ribbon, connectors, sensor
output, Pi receiver, or kernel driver. They do not prove a defective cable.
Normal test-pattern mode, the previous receiver format, and all six
previously active booth/media services and sockets were restored; temporary
raw output was removed. No print job or boot-setting change was made.
Further discriminating tests include an independent supported OS on a spare
SD card, or continuity/short testing of the fully disconnected ribbon.
Passing a continuity test does not guarantee high-speed signal integrity.

Another direct test explicitly selected each supported sensor mode instead
of reusing the last libcamera configuration: 1536 x 864, 2304 x 1296, and
4608 x 2592. Each used matching RGGB10 formats, its mode's default vertical
blanking (2755, 1198, and 58 respectively), exposure 100, and color bars.
All three successfully started streaming but timed out with zero raw bytes
and zero Unicam interrupts. Expected frame sizes were 1,658,880, 3,732,480,
and 14,929,920 bytes. Live status showed no detected image size, and the
sensor's runtime-power state was active during each stream. Runtime-power
state is a driver report, not a physical voltage measurement.
The original mode, receiver format, vertical blanking 13673, exposure 66,
test-pattern mode 0, and all six user services/sockets were restored.
Temporary raw output was removed. Resetting mode/timing did not produce
a frame; the kernel and physical image-data path remain unverified.

A read-only kernel-update review found installed kernel 6.18.50 and candidate
6.18.60. `raspi-firmware` is already at its repository candidate version.
APT simulations for both the v8 meta-package and a versioned v8 image install
require the same coordinated kernel-family plan: 7 upgrades, 8 new packages,
and no removals, including v8/2712 images, headers, and supporting packages.
Available space was 7.6 GiB on root and 416 MiB on the boot partition.
No kernel packages were installed, no autoremove was run, and no reboot was
performed. A kernel comparison needs explicit approval, a fresh plan check,
boot-file backup, and a one-time home-Wi-Fi recovery plan before rebooting;
otherwise the printer profile may take management access offline again.

Recorded reboot test: after a real Pi reboot, NetworkManager automatically
selected `photobooth-selphy-direct`; IPP verification passed with no gateway.
Desktop autostart launched the user service, and the Tk event loop logged
portrait 320 x 480 readiness on SPI-1. The test restored home Wi-Fi for SSH
and removed its temporary boot/recovery units. This verifies reboot behavior,
not unplug/replug behavior or HDMI-disconnected startup. All 87 tests passed
on the Pi, including the actual guest button callback flow with mocked printer
responses. No camera was detected; those GUI tests used synthetic captures.

## Test record

Copy this entry for each test run:

```text
Date:
Pi / Raspberry Pi OS version:
Camera / LCD / printer models:
Code version or copy date:
Phase and photo-count/interval settings:
Pass / fail / blocked:
Output folder:
Observed timing or image issues:
Exact error message:
Next action:
```


```
scp -r /Users/manasachinta/go/src/repos/tinker/portable-photobooth manasachi@172.16.249.89:~/

cd ~/portable-photobooth
python3 -m unittest -v
python3 photobooth.py --fullscreen


ssh into the pi:

ssh manasachi@172.16.249.89
```