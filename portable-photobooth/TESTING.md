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
   sudo apt install python3-picamera2 python3-pil python3-pil.imagetk python3-tk
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

These optional tests check options, countdown/preview controls, and Review at
480 x 320, 320 x 480 portrait, and 800 x 480; ordinary headless runs skip them.
LCD-targeting tests check rotation, exact output bounds, and explicit errors
for an absent, disabled, or unconfigured LCD.
Error tests check that LCD-mode dialogs stay in the LCD's bounds, and that
an undetected camera produces an actionable error rather than a failed capture.

These tests do not require a camera or a running graphical display, but Python
must have Tkinter installed because the application imports it.

**Pass:** all tests pass. They cover:

- All four valid photo-count/interval combinations.
- Exactly 3 or 4 saved paths, ordered filenames, and rejection of an extra shot.
- Rejection of unsupported options.
- A simulated failed capture not being added to the review list, followed by a
  successful retry.
- Print-sheet dimensions/DPI, matching left/right strips, photo order, white
  gaps, EXIF orientation, and unchanged original files for 3/4-photo layouts.
- Incomplete/unreadable inputs and visible layout failure handling.
- A simulated clock verifies the first capture waits 15 seconds for all four
  settings combinations, followed by the selected inter-photo countdowns.
- Preview rendering/polling, camera startup failure, stale callbacks, camera
  readiness, and shared preview/still camera setup with continuous autofocus.

The fake camera writes placeholder bytes, not real JPEGs. These tests do not
verify image quality, countdown timing, touchscreen rendering, autofocus, or
physical printing. Layout tests use separate real images generated by Pillow,
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
- [ ] Changing either choice updates the photo-count/countdown summary.
- [ ] Select 3 photos and 5 seconds; tap Start once.
- [ ] Choices disappear and the countdown remains responsive and readable.
- [ ] A 15-second positioning countdown appears for either interval selection.
- [ ] After camera startup, live images appear below the timer. Move your hand
      and verify the image updates during positioning and between shots.
- [ ] Preview has correct colors/orientation and is not stretched or mirrored.
- [ ] A brief preview pause at the shutter is acceptable; no frozen UI or second
      camera window appears.
- [ ] Three shots are taken automatically, with no extra taps.
- [ ] Live preview stops after the last shot and does not replace Review photos.
- [ ] A preparing-strips message appears while the print layout is composed.
- [ ] After the final save, the screen offers Review instead of opening photos
      automatically.
- [ ] Tap Review. Exactly three images appear, one at a time, in capture order.
- [ ] Previous is disabled on the first image; Next is disabled on the last.
- [ ] Print is visible, disabled, and sends no print job.
- [ ] New session returns to the choices.
- [ ] Escape exits fullscreen; closing the window exits the app.

**Pass:** the entire session works using the LCD without terminal interaction.
If controls are clipped on the actual LCD resolution, record that as a failure.

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
   for each shot to verify that review order matches capture order.
5. Start another session and verify its folder is distinct and earlier photos
   have not been overwritten.
6. Open `print_layout.png`. Check that it is 1,200 x 1,800 pixels with two
   identical strips side by side, each containing exactly the selected number
   of photos in order. Check white borders/gaps and the center crop of each
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
   Review screen for that failed session, and a return to the choices.
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
- [ ] Review appears only after the capture process exits successfully and
      returns exactly the requested number of saved-photo paths.
- [ ] A capture-process failure or unexpected exit shows an error, not success.
- [ ] Closing the LCD also cleans up the capture process and releases the camera.
- [ ] A new session works without restarting the LCD program.

**Pass:** the target flow in the README is implemented and verified on the Pi.

## Phase 8: Wireless printing (future)

**Blocked until the printer and print integration are available.** For now,
checking that Print is disabled is sufficient; it does not verify printing.

When implemented:

1. Confirm printer model, Linux support, paper size, margins, and strip/cutting
   behavior.
2. Print a test strip with numbered images. Check order, orientation, cropping,
   dimensions, and readable faces for both 3-photo and 4-photo layouts.
3. Confirm one tap submits one job; repeated taps do not duplicate prints.
4. Test printer offline, paper out, and lost wireless connection. Failures must
   be visible and saved photos must remain available.
5. Verify the app distinguishes a job being accepted from a physical print
   completing, according to what the printer actually reports.

**Pass:** correct physical output and explicit error handling, not merely a
successful software submission.

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