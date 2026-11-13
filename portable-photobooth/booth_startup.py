"""Install desktop startup, or wait for the LCD and launch the booth."""

import argparse
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import time

SERVICE = "photobooth.service"


def install(home: Path, project: Path) -> None:
    units = home / ".config/systemd/user"
    desktop = home / ".config/autostart"
    units.mkdir(parents=True, exist_ok=True)
    desktop.mkdir(parents=True, exist_ok=True)
    script = json.dumps(str(project / "booth_startup.py")).replace("%", "%%")
    (units / SERVICE).write_text(
        "[Unit]\nDescription=Portable photobooth LCD\n"
        "StartLimitIntervalSec=600\nStartLimitBurst=3\n\n"
        "[Service]\nType=simple\n"
        f"ExecStart=/usr/bin/python3 {script} --run\n"
        "Restart=on-failure\nRestartSec=10\n"
        "TimeoutStopSec=15\n"
    )
    launcher = str(project / "booth_startup.py")
    # Desktop Exec has its own quoting rules, including doubled literal percent signs.
    quoted = '"' + launcher.replace("\\", "\\\\").replace('"', '\\"').replace(
        "`", "\\`",
    ).replace("$", "\\$").replace("%", "%%") + '"'
    (desktop / "photobooth.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Portable Photobooth\n"
        f"Exec=/usr/bin/python3 {quoted} --start-service\nTerminal=false\n"
    )


def wait_for_lcd(timeout: int = 90) -> None:
    from photobooth import lcd_geometry

    deadline = time.monotonic() + timeout
    while True:
        try:
            width, height, _, _ = lcd_geometry()
            if width >= height:
                raise ValueError("Waiting for the configured portrait LCD rotation.")
            return
        except (OSError, ValueError, KeyError, subprocess.CalledProcessError,
                subprocess.TimeoutExpired) as error:
            if time.monotonic() >= deadline:
                raise RuntimeError("LCD did not become ready within the startup timeout.") from error
            logging.warning("Waiting for the LCD: %s", error)
            time.sleep(2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--install", action="store_true")
    actions.add_argument("--start-service", action="store_true")
    actions.add_argument("--run", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if args.install:
        install(Path.home(), Path(__file__).resolve().parent)
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        print("Installed desktop autostart. Run booth_startup.py --start-service to start now.")
    elif args.start_service:
        variables = [key for key in ("DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "XAUTHORITY")
                     if key in os.environ]
        subprocess.run(["systemctl", "--user", "import-environment", *variables], check=True)
        subprocess.run(["systemctl", "--user", "start", SERVICE], check=True)
    else:
        wait_for_lcd()
        os.execv("/usr/bin/python3", [
            "/usr/bin/python3", str(Path(__file__).with_name("photobooth.py")), "--lcd",
        ])


if __name__ == "__main__":
    main()
